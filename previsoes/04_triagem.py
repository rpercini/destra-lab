#!/usr/bin/env python3
"""Etapa 4 — triagem: quais trechos contêm afirmações sobre o futuro.

Roda Haiku 4.5 em Batch API sobre TODOS os chunks do acervo. É a única etapa que
lê as 563 horas inteiras, e por isso precisa ser a mais barata do pipeline.

A triagem é deliberadamente generosa. Um falso positivo custa uma fração de
centavo na etapa seguinte, que vai descartá-lo; um falso negativo é uma previsão
perdida para sempre, porque nada depois volta a olhar o chunk. Na dúvida, marca.
"""

from __future__ import annotations

import argparse
import sys

import lote
from esquema import SCHEMA_TRIAGEM

MODELO = "claude-haiku-4-5"

INSTRUCOES = """\
Você analisa a transcrição de um canal de comentário político brasileiro. Sua \
tarefa é decidir se o trecho abaixo contém alguma AFIRMAÇÃO SOBRE O FUTURO — \
algo que o apresentador diz que vai (ou não vai) acontecer.

Conta como afirmação sobre o futuro:
- Previsão explícita: "o X vai ser preso", "isso não passa no Congresso".
- Previsão com prazo: "até o fim do ano", "antes da eleição".
- Previsão condicional: "se A acontecer, então B".
- Aposta ou desafio: "pode marcar o que eu estou dizendo", "anota aí".
- Negação de possibilidade: "isso nunca vai acontecer", "não tem chance".

NÃO conta:
- Descrição do presente ou do passado.
- Opinião sem afirmação factual: "acho ele despreparado".
- Desejo ou apelo: "espero que melhore", "precisamos reagir".
- Hipótese explicitamente rotulada como exercício: "imagine se...".

Em caso de dúvida, marque como tendo previsão. Um trecho marcado por engano é \
descartado na etapa seguinte a custo irrisório; um trecho não marcado nunca mais \
será examinado.

Responda apenas com o JSON pedido.

--- TRECHO (vídeo de {data}) ---
{texto}
--- FIM DO TRECHO ---\
"""


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Triagem de chunks com Haiku 4.5 via Batch API.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Custo típico: ~US$ 7 para as 563h completas.",
    )
    ap.add_argument("--chunks", default="dados/chunks.jsonl")
    ap.add_argument("--inventario", default="dados/inventario.jsonl")
    ap.add_argument("--saida", default="dados/triagem.jsonl")
    ap.add_argument("--limite", type=int, help="Processa só os N primeiros (piloto).")
    ap.add_argument("--retomar", action="store_true",
                    help="Recupera um lote já enviado em vez de gastar de novo.")
    ap.add_argument("--intervalo", type=int, default=60,
                    help="Segundos entre verificações de progresso.")
    args = ap.parse_args()

    # A data de publicação entra no prompt: sem ela o modelo não distingue
    # "vai acontecer" de algo que, na data da fala, já era passado.
    datas = {
        v["video_id"]: v["publicado_em"][:10]
        for v in lote.le_jsonl(args.inventario)
    }

    chunks = list(lote.le_jsonl(args.chunks))
    if args.limite:
        chunks = chunks[: args.limite]
    if not chunks:
        sys.exit("Nenhum chunk encontrado. Rode 03_chunks.py antes.")

    requisicoes = [
        lote.requisicao(
            custom_id=c["chunk_id"],
            modelo=MODELO,
            prompt=INSTRUCOES.format(
                data=datas.get(c["video_id"], "data desconhecida"),
                texto=c["texto"],
            ),
            schema=SCHEMA_TRIAGEM,
            max_tokens=512,  # a resposta é um JSON de quatro campos
        )
        for c in chunks
    ]

    print(f"Triagem de {len(requisicoes):,} chunks.".replace(",", "."))
    res, uso = lote.executa(
        "triagem", requisicoes, MODELO,
        retomar=args.retomar, intervalo=args.intervalo,
    )

    por_id = {c["chunk_id"]: c for c in chunks}
    marcados: list[dict] = []
    total = 0

    for chunk_id, dados in res:
        total += 1
        if not dados.get("tem_previsao"):
            continue
        c = por_id.get(chunk_id)
        if c is None:
            continue
        marcados.append({**c, "triagem": dados})

    marcados.sort(key=lambda m: (-m["triagem"]["confianca"], m["chunk_id"]))
    n = lote.grava_jsonl(args.saida, marcados)

    previstas = sum(m["triagem"].get("quantidade", 0) for m in marcados)
    taxa = (n / total * 100) if total else 0.0

    print("\n" + "=" * 58)
    print("TRIAGEM CONCLUÍDA")
    print("=" * 58)
    print(f"  chunks analisados   {total:,}".replace(",", "."))
    print(f"  chunks com previsão {n:,}  ({taxa:.1f}%)".replace(",", "."))
    print(f"  previsões estimadas {previstas:,}".replace(",", "."))
    print(uso.relatorio())
    print(f"\n  → {args.saida}")

    if n:
        horas = sum(m["fim_ms"] - m["inicio_ms"] for m in marcados) / 3_600_000
        print(f"\n  A etapa 5 vai processar {horas:.1f}h de fala marcada.")
    else:
        print("\n  Nenhum chunk marcado — revise o prompt de triagem antes de seguir.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
