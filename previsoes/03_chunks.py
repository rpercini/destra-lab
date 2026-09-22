#!/usr/bin/env python3
"""Etapa 3 — transforma legendas json3 em chunks de transcrição.

Lê `dados/legendas/<video_id>.<lang>.json3` (saída do yt-dlp) e o inventário
`dados/inventario.jsonl` (etapa 1), e grava `dados/chunks.jsonl` — uma linha por
`Chunk`, pronto para a triagem por LLM.

Três decisões merecem leitura antes de mexer aqui:

1. Timestamps são ABSOLUTOS dentro do vídeo. `inicio_ms`/`fim_ms` de cada chunk
   saem direto dos segmentos da legenda, não de contagem de palavras. É desse
   número que sai o corte de vídeo no fim do pipeline.

2. Legenda automática do YouTube duplica texto por rolagem: o evento seguinte
   repete o fim do anterior para simular as linhas subindo na tela. A limpeza
   está em `corta_sobreposicao()` — ver o docstring de lá.

3. A janela de chunking é uma janela de TEMPO sobre a linha do tempo da fala,
   ancorada na primeira palavra do vídeo. Isso mantém os limites previsíveis e
   auditáveis: o chunk i começa em `primeira_palavra + i * passo`.

Uso:
    python 03_chunks.py [--minutos 15] [--overlap 2]
                        [--entrada dados/legendas] [--saida dados/chunks.jsonl]
                        [--inventario dados/inventario.jsonl]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from bisect import bisect_left
from dataclasses import dataclass
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from esquema import Chunk, Video  # noqa: E402

# --------------------------------------------------------------------------
# Constantes de custo — etapa 4 (triagem)
# --------------------------------------------------------------------------

MODELO_TRIAGEM = "claude-haiku-4-5"
TOKENS_POR_PALAVRA = 1.8          # português rende mais token por palavra que inglês
PRECO_ENTRADA_POR_MILHAO = 1.00   # US$/Mtok de entrada, Claude Haiku 4.5
DESCONTO_BATCH = 0.50             # Batch API: 50% de desconto
PRECO_EFETIVO_POR_MILHAO = PRECO_ENTRADA_POR_MILHAO * (1 - DESCONTO_BATCH)

# Quantas palavras já emitidas olhar para trás ao procurar duplicação de rolagem.
# Um evento de legenda automática raramente passa de ~20 palavras; 120 dá folga
# para rolagens que repetem duas ou três linhas de uma vez.
JANELA_DEDUP_PALAVRAS = 120


# --------------------------------------------------------------------------
# Modelo interno: a palavra é a unidade mínima, e carrega seu tempo
# --------------------------------------------------------------------------

@dataclass(slots=True)
class Palavra:
    """Uma palavra da legenda com o tempo absoluto em que foi dita."""

    inicio_ms: int
    fim_ms: int
    texto: str


# --------------------------------------------------------------------------
# Parser json3
# --------------------------------------------------------------------------

def _inteiro(valor, padrao: int = 0) -> int:
    """json3 traz int, str ou nada. Converte o que der; o resto vira `padrao`."""
    if valor is None:
        return padrao
    try:
        return int(valor)
    except (TypeError, ValueError):
        return padrao


def palavras_do_evento(evento: dict) -> list[Palavra]:
    """Achata um evento json3 em palavras com tempo absoluto.

    Casos reais tratados aqui:
      - evento sem a chave `segs` (existe: eventos de janela/estilo) -> ignorado;
      - `utf8` só com "\\n" ou espaço -> descartado;
      - `tOffsetMs` ausente -> 0;
      - `dDurationMs` ausente -> o fim da palavra vira o próprio início.
    """
    if not isinstance(evento, dict):
        return []
    segs = evento.get("segs")
    if not isinstance(segs, list):
        return []

    t_evento = _inteiro(evento.get("tStartMs"))
    duracao = evento.get("dDurationMs")
    fim_evento = t_evento + _inteiro(duracao) if duracao is not None else None

    palavras: list[Palavra] = []
    for seg in segs:
        if not isinstance(seg, dict):
            continue
        texto = seg.get("utf8")
        if not isinstance(texto, str) or not texto.strip():
            continue
        inicio = t_evento + _inteiro(seg.get("tOffsetMs"))
        fim = max(inicio, fim_evento) if fim_evento is not None else inicio
        # Um seg pode conter mais de uma palavra ("bom dia"); todas herdam o
        # tempo do seg, que é a melhor informação disponível.
        for palavra in texto.split():
            palavras.append(Palavra(inicio_ms=inicio, fim_ms=fim, texto=palavra))
    return palavras


_SO_LETRAS = re.compile(r"[^\w]+", re.UNICODE)


def _normaliza(palavra: str) -> str:
    """Forma de comparação: sem pontuação e sem caixa."""
    limpa = _SO_LETRAS.sub("", palavra).casefold()
    return limpa or palavra.casefold()


def corta_sobreposicao(cauda_norm: list[str], novas: list[Palavra]) -> list[Palavra]:
    """Remove a duplicação por rolagem no início de um evento.

    A legenda automática do YouTube funciona em modo "roll-up": o evento novo
    reimprime o fim do que já estava na tela e acrescenta o texto novo. Sem
    limpeza, "a economia vai" + "a economia vai cair" vira
    "a economia vai a economia vai cair" — inflando `n_palavras`, poluindo o
    texto enviado ao modelo e empurrando o custo para cima.

    A heurística: procurar o MAIOR k tal que as últimas k palavras já emitidas
    sejam iguais às primeiras k palavras do evento novo, e cortar essas k. Do
    maior para o menor, então a repetição mais longa ganha — o que evita casar
    um sufixo curto acidental quando existe uma sobreposição real maior.

    Três detalhes que importam:
      - compara contra a cauda do que JÁ FOI EMITIDO (não contra o evento
        anterior cru), porque a rolagem pode repetir texto de dois eventos atrás;
      - a comparação é normalizada (sem pontuação, sem caixa), já que a legenda
        automática oscila na capitalização;
      - se k == len(novas), o evento inteiro era repetição e some — é o caso do
        evento final que só reimprime a última linha.
    """
    if not cauda_norm or not novas:
        return novas
    novas_norm = [_normaliza(p.texto) for p in novas]
    limite = min(len(cauda_norm), len(novas_norm))
    for k in range(limite, 0, -1):
        if cauda_norm[-k:] == novas_norm[:k]:
            return novas[k:]
    return novas


def parse_json3(dados: dict) -> tuple[list[Palavra], int]:
    """Converte o json3 carregado em palavras limpas.

    Devolve `(palavras, n_palavras_descartadas_por_rolagem)`.
    """
    eventos = dados.get("events") if isinstance(dados, dict) else None
    if not isinstance(eventos, list):
        return [], 0

    emitidas: list[Palavra] = []
    cauda_norm: list[str] = []
    descartadas = 0

    for evento in eventos:
        brutas = palavras_do_evento(evento)
        if not brutas:
            continue
        limpas = corta_sobreposicao(cauda_norm, brutas)
        descartadas += len(brutas) - len(limpas)
        if not limpas:
            continue
        emitidas.extend(limpas)
        cauda_norm.extend(_normaliza(p.texto) for p in limpas)
        if len(cauda_norm) > JANELA_DEDUP_PALAVRAS:
            del cauda_norm[:-JANELA_DEDUP_PALAVRAS]

    # Legenda automática às vezes entrega eventos fora de ordem. Ordenação
    # estável: empates preservam a ordem original de fala.
    emitidas.sort(key=lambda p: p.inicio_ms)
    return emitidas, descartadas


def carrega_json3(caminho: Path) -> tuple[list[Palavra], int]:
    with caminho.open(encoding="utf-8") as fh:
        dados = json.load(fh)
    return parse_json3(dados)


# --------------------------------------------------------------------------
# Chunking
# --------------------------------------------------------------------------

_ESPACOS = re.compile(r"\s+")


def limpa_texto(partes: list[str]) -> str:
    return _ESPACOS.sub(" ", " ".join(partes)).strip()


def monta_chunks(
    video_id: str,
    palavras: list[Palavra],
    janela_ms: int,
    overlap_ms: int,
) -> list[Chunk]:
    """Agrupa palavras em janelas de tempo com sobreposição.

    A janela i cobre [base + i*passo, base + i*passo + janela), onde `base` é o
    tempo da primeira palavra e `passo = janela - overlap`. Uma palavra cai em
    duas janelas quando está na faixa de sobreposição — de propósito: é o que
    impede uma previsão de ser cortada ao meio na fronteira.

    `inicio_ms`/`fim_ms` do chunk NÃO são as bordas nominais da janela, e sim os
    tempos reais da primeira e da última palavra dentro dela. As bordas nominais
    cairiam em silêncio; os tempos reais apontam para fala.
    """
    if not palavras:
        return []

    passo_ms = janela_ms - overlap_ms
    inicios = [p.inicio_ms for p in palavras]
    base = inicios[0]
    ultimo = inicios[-1]

    chunks: list[Chunk] = []
    faixa_anterior: tuple[int, int] | None = None
    i = 0
    while True:
        ini_janela = base + i * passo_ms
        if ini_janela > ultimo:
            break
        a = bisect_left(inicios, ini_janela)
        b = bisect_left(inicios, ini_janela + janela_ms)
        if b > a:
            # A última janela costuma conter só a cauda já entregue pela janela
            # anterior. Um chunk cujo conteúdo é subconjunto do anterior não
            # acrescenta nada e custaria uma chamada de LLM à toa.
            subconjunto = (
                faixa_anterior is not None
                and a >= faixa_anterior[0]
                and b <= faixa_anterior[1]
            )
            if not subconjunto:
                fatia = palavras[a:b]
                texto = limpa_texto([p.texto for p in fatia])
                indice = len(chunks)
                chunks.append(
                    Chunk(
                        chunk_id=f"{video_id}#{indice:04d}",
                        video_id=video_id,
                        indice=indice,
                        inicio_ms=fatia[0].inicio_ms,
                        fim_ms=max(p.fim_ms for p in fatia),
                        texto=texto,
                        n_palavras=len(texto.split()),
                    )
                )
                faixa_anterior = (a, b)
        i += 1

    return chunks


# --------------------------------------------------------------------------
# Seleção de idioma
# --------------------------------------------------------------------------

SUFIXO_AUTO = "-orig"
PREFIXO_AUTO = "a."


def decompoe_nome(caminho: Path) -> tuple[str, str] | None:
    """`dQw4w9WgXcQ.pt-BR.json3` -> ("dQw4w9WgXcQ", "pt-BR")."""
    nome = caminho.name
    if not nome.endswith(".json3"):
        return None
    miolo = nome[: -len(".json3")]
    video_id, ponto, lang = miolo.partition(".")
    if not ponto or not video_id or not lang:
        return None
    return video_id, lang


def e_automatica(lang: str) -> bool:
    """yt-dlp marca legenda automática como `pt-orig` (ou `a.pt` em versões antigas)."""
    b = lang.lower()
    return b.endswith(SUFIXO_AUTO) or b.startswith(PREFIXO_AUTO)


def _codigo_base(lang: str) -> str:
    b = lang.lower()
    if b.startswith(PREFIXO_AUTO):
        b = b[len(PREFIXO_AUTO):]
    if b.endswith(SUFIXO_AUTO):
        b = b[: -len(SUFIXO_AUTO)]
    return b


def prioridade_idioma(lang: str) -> tuple:
    """Chave de ordenação: menor é melhor.

    Ordem pedida pelo pipeline:
        manual pt-BR > manual pt > manual pt-* > automática pt > outro idioma.
    """
    codigo = _codigo_base(lang)
    if codigo in ("pt-br", "pt_br"):
        rank_pt = 0
    elif codigo == "pt":
        rank_pt = 1
    elif codigo.startswith("pt"):
        rank_pt = 2
    else:
        rank_pt = 9
    outro_idioma = 0 if rank_pt < 9 else 1
    return (outro_idioma, 1 if e_automatica(lang) else 0, rank_pt, lang.lower())


def escolhe_legenda(caminhos: list[Path]) -> tuple[Path, str]:
    """Escolhe o melhor arquivo de legenda entre as variantes do mesmo vídeo."""
    pares = []
    for caminho in caminhos:
        partes = decompoe_nome(caminho)
        if partes is None:
            continue
        pares.append((prioridade_idioma(partes[1]), partes[1], caminho))
    if not pares:
        raise ValueError("nenhum arquivo com nome <video_id>.<lang>.json3")
    pares.sort(key=lambda t: t[0])
    _, lang, caminho = pares[0]
    return caminho, lang


def rotulo_idioma(lang: str) -> str:
    return f"{lang} ({'automática' if e_automatica(lang) else 'manual'})"


# --------------------------------------------------------------------------
# Inventário
# --------------------------------------------------------------------------

def carrega_inventario(caminho: Path) -> tuple[list[Video], list[str]]:
    """Lê o inventário da etapa 1. Linha inválida não derruba a etapa."""
    videos: list[Video] = []
    avisos: list[str] = []
    if not caminho.exists():
        avisos.append(
            f"inventário não encontrado em {caminho} — seguindo só com os "
            f"arquivos de legenda presentes."
        )
        return videos, avisos
    with caminho.open(encoding="utf-8") as fh:
        for n, linha in enumerate(fh, start=1):
            linha = linha.strip()
            if not linha:
                continue
            try:
                videos.append(Video.model_validate_json(linha))
            except Exception as erro:  # linha corrompida: registra e segue
                avisos.append(f"inventário linha {n} ignorada: {erro}")
    return videos, avisos


def indexa_legendas(entrada: Path) -> dict[str, list[Path]]:
    """Agrupa os arquivos de legenda por video_id."""
    por_video: dict[str, list[Path]] = {}
    if not entrada.exists():
        return por_video
    for caminho in sorted(entrada.glob("*.json3")):
        partes = decompoe_nome(caminho)
        if partes is None:
            continue
        por_video.setdefault(partes[0], []).append(caminho)
    return por_video


# --------------------------------------------------------------------------
# Relatório
# --------------------------------------------------------------------------

def fmt_int(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def fmt_dec(x: float, casas: int = 1) -> str:
    return f"{x:,.{casas}f}".replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def fmt_usd(x: float) -> str:
    return "US$ " + fmt_dec(x, 2)


def linha(rotulo: str, valor: str, largura: int = 42) -> str:
    return f"{rotulo} ".ljust(largura, ".") + f" {valor}"


def imprime_resumo(
    *,
    minutos: int,
    overlap: int,
    n_videos_inventario: int,
    processados: int,
    sem_legenda: list[str],
    sem_fala: list[str],
    fora_do_inventario: list[str],
    idiomas: dict[str, int],
    n_chunks: int,
    n_palavras: int,
    palavras_fala: int,
    palavras_duplicadas: int,
    saida: Path,
    avisos: list[str],
) -> None:
    media = n_palavras / n_chunks if n_chunks else 0.0
    tokens = int(round(n_palavras * TOKENS_POR_PALAVRA))
    custo = tokens / 1_000_000 * PRECO_EFETIVO_POR_MILHAO
    brutas = palavras_fala + palavras_duplicadas
    pct_dup = (palavras_duplicadas / brutas * 100) if brutas else 0.0

    print()
    print("=" * 64)
    print("  ETAPA 3 — CHUNKS DE TRANSCRIÇÃO")
    print("=" * 64)
    print(linha("Janela / sobreposição", f"{minutos} min / {overlap} min"))
    print(linha("Vídeos no inventário", fmt_int(n_videos_inventario)))
    print(linha("Vídeos processados", fmt_int(processados)))
    print(linha("Vídeos sem legenda (pulados)", fmt_int(len(sem_legenda))))
    if sem_fala:
        print(linha("Legendas vazias / ilegíveis", fmt_int(len(sem_fala))))
    if fora_do_inventario:
        print(linha("Legendas fora do inventário", fmt_int(len(fora_do_inventario))))
    print()
    print("  Idioma escolhido (manual tem prioridade sobre automática):")
    for lang, quantos in sorted(idiomas.items(), key=lambda kv: (-kv[1], kv[0])):
        print("  " + linha(f"  {lang}", fmt_int(quantos), largura=40))
    print()
    print(linha("Chunks gerados", fmt_int(n_chunks)))
    print(linha("Palavras de fala (após limpeza)", fmt_int(palavras_fala)))
    print(linha("Palavras nos chunks (c/ sobreposição)", fmt_int(n_palavras)))
    print(linha("Média de palavras por chunk", fmt_dec(media, 0)))
    print(
        linha(
            "Duplicação de rolagem removida",
            f"{fmt_int(palavras_duplicadas)} palavras ({fmt_dec(pct_dup)}%)",
        )
    )
    print(linha("Arquivo gerado", str(saida)))

    print()
    print("-" * 64)
    print(f"  ESTIMATIVA DA TRIAGEM — {MODELO_TRIAGEM} · Batch API")
    print("-" * 64)
    print(linha(f"  Tokens de entrada (~{fmt_dec(TOKENS_POR_PALAVRA)} tok/palavra)",
                fmt_int(tokens), largura=44))
    print(linha("  Preço de entrada",
                f"{fmt_usd(PRECO_ENTRADA_POR_MILHAO)}/Mtok − 50% batch = "
                f"{fmt_usd(PRECO_EFETIVO_POR_MILHAO)}/Mtok", largura=44))
    print()
    print(f"  >>> CUSTO ESTIMADO DA TRIAGEM: {fmt_usd(custo)} <<<")
    print()
    print("  (só o texto dos chunks; instruções do prompt e saída ficam de fora)")
    print("=" * 64)

    if avisos:
        print()
        print(f"Avisos ({fmt_int(len(avisos))}):")
        for aviso in avisos[:20]:
            print(f"  - {aviso}")
        if len(avisos) > 20:
            print(f"  ... e mais {fmt_int(len(avisos) - 20)} aviso(s).")

    if sem_legenda:
        print()
        amostra = ", ".join(sem_legenda[:10])
        reticencias = ", ..." if len(sem_legenda) > 10 else ""
        print(f"Sem legenda ({fmt_int(len(sem_legenda))}): {amostra}{reticencias}")


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def resolve(caminho: str | None, padrao: Path) -> Path:
    """Sem argumento, ancora no diretório do script; com argumento, no cwd."""
    return padrao if caminho is None else Path(caminho).expanduser()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Etapa 3 — transforma legendas json3 em chunks para a triagem.",
    )
    p.add_argument("--minutos", type=int, default=15,
                   help="minutos de fala por chunk (padrão: 15)")
    p.add_argument("--overlap", type=int, default=2,
                   help="minutos de sobreposição entre chunks (padrão: 2)")
    p.add_argument("--entrada", default=None,
                   help="diretório das legendas (padrão: dados/legendas)")
    p.add_argument("--saida", default=None,
                   help="arquivo de saída (padrão: dados/chunks.jsonl)")
    p.add_argument("--inventario", default=None,
                   help="inventário da etapa 1 (padrão: dados/inventario.jsonl)")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    if args.minutos <= 0:
        print("Erro: --minutos precisa ser maior que zero.", file=sys.stderr)
        return 2
    if args.overlap < 0:
        print("Erro: --overlap não pode ser negativo.", file=sys.stderr)
        return 2
    if args.overlap >= args.minutos:
        print(
            "Erro: --overlap precisa ser menor que --minutos "
            f"(recebi overlap={args.overlap} e minutos={args.minutos}); "
            "caso contrário as janelas não avançam.",
            file=sys.stderr,
        )
        return 2

    entrada = resolve(args.entrada, BASE_DIR / "dados" / "legendas")
    saida = resolve(args.saida, BASE_DIR / "dados" / "chunks.jsonl")
    inventario = resolve(args.inventario, BASE_DIR / "dados" / "inventario.jsonl")

    janela_ms = args.minutos * 60_000
    overlap_ms = args.overlap * 60_000

    videos, avisos = carrega_inventario(inventario)
    por_video = indexa_legendas(entrada)

    if not por_video:
        print(f"Erro: nenhuma legenda .json3 encontrada em {entrada}.", file=sys.stderr)
        return 1

    ordem = [v.video_id for v in videos]
    vistos = set(ordem)
    fora_do_inventario = sorted(vid for vid in por_video if vid not in vistos)
    ordem.extend(fora_do_inventario)
    if fora_do_inventario:
        avisos.append(
            f"{len(fora_do_inventario)} vídeo(s) com legenda não constam do "
            f"inventário; foram processados mesmo assim."
        )

    sem_legenda: list[str] = []
    sem_fala: list[str] = []
    idiomas: dict[str, int] = {}
    processados = 0
    n_chunks = 0
    n_palavras = 0
    palavras_fala = 0
    palavras_duplicadas = 0

    saida.parent.mkdir(parents=True, exist_ok=True)
    with saida.open("w", encoding="utf-8") as out:
        for video_id in ordem:
            caminhos = por_video.get(video_id)
            if not caminhos:
                sem_legenda.append(video_id)
                continue

            caminho, lang = escolhe_legenda(caminhos)
            if not _codigo_base(lang).startswith("pt"):
                avisos.append(
                    f"{video_id}: sem legenda em português; usando '{lang}'."
                )

            try:
                palavras, duplicadas = carrega_json3(caminho)
            except (OSError, json.JSONDecodeError, UnicodeDecodeError) as erro:
                avisos.append(f"{video_id}: falha ao ler {caminho.name}: {erro}")
                sem_fala.append(video_id)
                continue

            if not palavras:
                avisos.append(f"{video_id}: {caminho.name} não tem fala aproveitável.")
                sem_fala.append(video_id)
                continue

            chunks = monta_chunks(video_id, palavras, janela_ms, overlap_ms)
            for chunk in chunks:
                out.write(chunk.model_dump_json() + "\n")
                n_palavras += chunk.n_palavras
            n_chunks += len(chunks)
            palavras_fala += len(palavras)
            palavras_duplicadas += duplicadas
            idiomas[rotulo_idioma(lang)] = idiomas.get(rotulo_idioma(lang), 0) + 1
            processados += 1

    imprime_resumo(
        minutos=args.minutos,
        overlap=args.overlap,
        n_videos_inventario=len(videos),
        processados=processados,
        sem_legenda=sem_legenda,
        sem_fala=sem_fala,
        fora_do_inventario=fora_do_inventario,
        idiomas=idiomas,
        n_chunks=n_chunks,
        n_palavras=n_palavras,
        palavras_fala=palavras_fala,
        palavras_duplicadas=palavras_duplicadas,
        saida=saida,
        avisos=avisos,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
