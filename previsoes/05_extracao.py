#!/usr/bin/env python3
"""Etapa 5 — extração: transforma os trechos marcados em previsões estruturadas.

Roda Sonnet 5 em Batch API só sobre o que a triagem marcou. Cada previsão sai
com timestamp absoluto (de onde vem o corte), prazo resolvido em data, e as notas
de ousadia e especificidade que depois decidem a pauta.

Duas coisas acontecem aqui que valem atenção:

1. Previsões não-falseáveis ("as coisas vão piorar") são separadas, não
   descartadas — vão para previsoes_vagas.jsonl. Elas não podem ser julgadas
   contra fatos, mas fazem parte do registro.
2. Os chunks se sobrepõem em 2 minutos, então a mesma fala é analisada duas
   vezes. A deduplicação no fim do arquivo resolve isso; sem ela o banco fica com
   pares quase idênticos e o placar final sai inflado.
"""

from __future__ import annotations

import argparse
import sys
from difflib import SequenceMatcher

import lote
from esquema import SCHEMA_EXTRACAO, valida_intervalo

MODELO = "claude-sonnet-5"

INSTRUCOES = """\
Você cataloga previsões feitas por um comentarista político brasileiro, a partir \
da transcrição automática do canal dele. O objetivo é um registro completo e \
honesto: entram tanto as previsões que vieram a se confirmar quanto as que não \
vieram. Você NÃO julga se a previsão acertou — isso é feito depois, contra \
fontes. Aqui você só registra o que foi afirmado.

O trecho abaixo é de um vídeo publicado em {data}. Tudo que se refere a depois \
dessa data é futuro; tudo antes é passado.

Para cada afirmação distinta sobre o futuro, extraia um registro. Observe:

- `afirmacao`: reescreva como proposição única e verificável, que se sustente \
sozinha. "Ele vai ser preso" vira "Fulano de Tal será preso até o fim de 2023".
- `citacao`: o que foi dito, literal. A transcrição é automática e tem erros; \
copie mesmo assim, sem corrigir. O corte final usa áudio limpo.
- `prazo_limite`: converta o prazo para AAAA-MM-DD contando a partir de {data}. \
"Ano que vem" num vídeo de março de 2022 vira 2023-12-31. "Até a eleição" vira a \
data da eleição em questão. Se a fala não permitir inferir data alguma, deixe \
string vazia — não invente prazo.
- `falseavel`: falso quando nenhum fato poderia contradizer a afirmação. \
"O Brasil vai piorar" não é falseável; "o dólar passa de 6 reais em 2024" é. \
Registre os dois, mas marque a diferença.
- `ousadia` (1 a 5): o quanto a afirmação contrariava o que se dizia NA ÉPOCA da \
fala, não o que sabemos hoje. Não deixe o desfecho conhecido contaminar a nota — \
uma previsão que hoje parece óbvia podia ser ousada em 2019.
- `especificidade` (1 a 5): 1 é genérico, 5 nomeia pessoa, número e data.
- `tema`: slug do EVENTO tratado, não do assunto amplo. Prefira \
"eleicao-presidencial-2022" a "politica". Previsões sobre o mesmo acontecimento \
precisam receber o mesmo slug, porque é por ele que se agrupam os dossiês de \
verificação depois.
- `offset_inicio_s` / `offset_fim_s`: segundos desde o INÍCIO DESTE TRECHO. \
Inclua alguns segundos de contexto antes da frase — o corte de vídeo sai daqui e \
uma previsão que começa sem preâmbulo fica incompreensível.

Se o trecho não contiver nenhuma afirmação sobre o futuro, devolva lista vazia.

--- TRECHO ---
{texto}
--- FIM DO TRECHO ---\
"""


def deduplica(previsoes: list[dict], limiar: float = 0.82) -> tuple[list[dict], int]:
    """Remove previsões repetidas pela sobreposição entre chunks.

    Duas entradas são a mesma fala quando estão no mesmo vídeo, começam a menos
    de 90 segundos uma da outra, e as afirmações são textualmente parecidas.
    Mantém a de maior especificidade.
    """
    por_video: dict[str, list[dict]] = {}
    for p in previsoes:
        por_video.setdefault(p["video_id"], []).append(p)

    mantidas: list[dict] = []
    removidas = 0

    for entradas in por_video.values():
        entradas.sort(key=lambda p: p["inicio_ms"])
        aceitas: list[dict] = []

        for p in entradas:
            duplicada = False
            # Percorre de trás para frente: como `entradas` está ordenado por
            # tempo, as candidatas próximas são as últimas aceitas.
            for idx in range(len(aceitas) - 1, -1, -1):
                a = aceitas[idx]
                if p["inicio_ms"] - a["inicio_ms"] > 90_000:
                    break  # o resto está longe demais
                similaridade = SequenceMatcher(
                    None, a["afirmacao"].lower(), p["afirmacao"].lower()
                ).ratio()
                if similaridade >= limiar:
                    duplicada = True
                    if p["especificidade"] > a["especificidade"]:
                        aceitas[idx] = p  # fica a versão mais específica
                    break
            if duplicada:
                removidas += 1
            else:
                aceitas.append(p)

        mantidas.extend(aceitas)

    mantidas.sort(key=lambda p: (p["publicado_em"], p["inicio_ms"]))
    return mantidas, removidas


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Extrai previsões estruturadas dos trechos marcados.",
        epilog="Custo típico: ~US$ 14 sobre o acervo completo.",
    )
    ap.add_argument("--triagem", default="dados/triagem.jsonl")
    ap.add_argument("--inventario", default="dados/inventario.jsonl")
    ap.add_argument("--saida", default="dados/previsoes.jsonl")
    ap.add_argument("--vagas", default="dados/previsoes_vagas.jsonl")
    ap.add_argument("--limite", type=int)
    ap.add_argument("--retomar", action="store_true")
    ap.add_argument("--intervalo", type=int, default=60)
    ap.add_argument("--confianca-minima", type=float, default=0.0,
                    help="Ignora trechos cuja triagem teve confiança abaixo disso.")
    args = ap.parse_args()

    videos = {v["video_id"]: v for v in lote.le_jsonl(args.inventario)}

    chunks = [
        c for c in lote.le_jsonl(args.triagem)
        if c.get("triagem", {}).get("confianca", 1.0) >= args.confianca_minima
    ]
    if args.limite:
        chunks = chunks[: args.limite]
    if not chunks:
        sys.exit("Nenhum trecho marcado. Rode 04_triagem.py antes.")

    requisicoes = [
        lote.requisicao(
            custom_id=c["chunk_id"],
            modelo=MODELO,
            prompt=INSTRUCOES.format(
                data=videos.get(c["video_id"], {}).get("publicado_em", "")[:10],
                texto=c["texto"],
            ),
            schema=SCHEMA_EXTRACAO,
            max_tokens=8192,
            pensamento=True,   # a resolução de prazo e a nota de ousadia pedem raciocínio
            esforco="low",     # mas é trabalho de extração, não precisa de mais que isso
        )
        for c in chunks
    ]

    print(f"Extração sobre {len(requisicoes):,} trechos.".replace(",", "."))
    res, uso = lote.executa(
        "extracao", requisicoes, MODELO,
        retomar=args.retomar, intervalo=args.intervalo,
    )

    por_id = {c["chunk_id"]: c for c in chunks}
    falseaveis: list[dict] = []
    vagas: list[dict] = []

    for chunk_id, dados in res:
        chunk = por_id.get(chunk_id)
        if chunk is None:
            continue
        video = videos.get(chunk["video_id"], {})
        duracao_chunk_s = (chunk["fim_ms"] - chunk["inicio_ms"]) // 1000

        for i, p in enumerate(dados.get("previsoes", [])):
            # Os offsets vêm relativos ao trecho; o corte precisa do absoluto.
            ini = valida_intervalo("offset_inicio_s", p["offset_inicio_s"], 0, duracao_chunk_s)
            fim = valida_intervalo("offset_fim_s", p["offset_fim_s"], ini, duracao_chunk_s)

            registro = {
                **p,
                "ousadia": valida_intervalo("ousadia", p["ousadia"], 1, 5),
                "especificidade": valida_intervalo("especificidade", p["especificidade"], 1, 5),
                "previsao_id": f"{chunk_id}:{i}",
                "video_id": chunk["video_id"],
                "video_titulo": video.get("titulo", ""),
                "video_url": video.get("url", ""),
                "publicado_em": video.get("publicado_em", ""),
                "inicio_ms": chunk["inicio_ms"] + ini * 1000,
                "fim_ms": chunk["inicio_ms"] + fim * 1000,
                "julgamento": None,
            }
            (falseaveis if p.get("falseavel") else vagas).append(registro)

        por_id.pop(chunk_id, None)

    falseaveis, repetidas = deduplica(falseaveis)
    vagas, _ = deduplica(vagas)

    n = lote.grava_jsonl(args.saida, falseaveis)
    n_vagas = lote.grava_jsonl(args.vagas, vagas)

    temas: dict[str, int] = {}
    for p in falseaveis:
        temas[p["tema"]] = temas.get(p["tema"], 0) + 1

    sem_prazo = sum(1 for p in falseaveis if not p["prazo_limite"])

    print("\n" + "=" * 58)
    print("EXTRAÇÃO CONCLUÍDA")
    print("=" * 58)
    print(f"  previsões verificáveis  {n:,}".replace(",", "."))
    print(f"  afirmações vagas        {n_vagas:,}  → {args.vagas}".replace(",", "."))
    print(f"  duplicatas removidas    {repetidas:,}".replace(",", "."))
    print(f"  temas distintos         {len(temas):,}".replace(",", "."))
    print(f"  sem prazo inferível     {sem_prazo:,}".replace(",", "."))
    print(uso.relatorio())
    print(f"\n  → {args.saida}")

    if temas:
        print("\n  Temas mais recorrentes (viram dossiê na etapa 6):")
        for tema, qtd in sorted(temas.items(), key=lambda kv: -kv[1])[:12]:
            print(f"    {qtd:4d}  {tema}")
        print(f"\n  {len(temas)} dossiês a montar — estimativa: "
              f"US$ {len(temas) * 0.30:.2f} na etapa 6.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
