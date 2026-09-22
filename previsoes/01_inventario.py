#!/usr/bin/env python3
"""Etapa 1 — inventário do acervo de um canal do YouTube.

Percorre a playlist de uploads do canal via YouTube Data API v3 e grava um
`Video` (ver `esquema.py`) por linha em JSONL. É a âncora de todo o pipeline:
nada aqui depende de legendas, só de metadados.

Custo de quota (cota diária padrão: 10.000 unidades):
  channels.list        1 unidade
  playlistItems.list   1 unidade por página de 50 vídeos  (~18 para 875 vídeos)
  videos.list          1 unidade por lote de 50 IDs       (~18 para 875 vídeos)
Total para um canal de ~875 vídeos: ~40 unidades. Dá para rodar o dia inteiro.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Iterable, Iterator, Optional

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from esquema import Video  # noqa: E402

API_BASE = "https://www.googleapis.com/youtube/v3"
TIMEOUT_PADRAO = 30
TENTATIVAS_PADRAO = 5


# --------------------------------------------------------------------------
# Erros
# --------------------------------------------------------------------------

class ErroInventario(Exception):
    """Erro previsto, exibido ao usuário sem traceback."""


class ErroQuota(ErroInventario):
    """A cota diária da API acabou."""


# --------------------------------------------------------------------------
# Duração ISO 8601 -> segundos
# --------------------------------------------------------------------------

# A API devolve durações como "PT1H2M10S". Lives em andamento podem vir como
# "P0D". Semanas/dias aparecem raramente, mas o parser aceita.
_RE_DURACAO = re.compile(
    r"^P"
    r"(?:(?P<semanas>\d+)W)?"
    r"(?:(?P<dias>\d+)D)?"
    r"(?:T"
    r"(?:(?P<horas>\d+)H)?"
    r"(?:(?P<minutos>\d+)M)?"
    r"(?:(?P<segundos>\d+(?:[.,]\d+)?)S)?"
    r")?$"
)

_PESOS = {
    "semanas": 604800,
    "dias": 86400,
    "horas": 3600,
    "minutos": 60,
    "segundos": 1,
}


def parse_duracao_iso8601(texto: str) -> int:
    """Converte uma duração ISO 8601 em segundos inteiros.

    >>> parse_duracao_iso8601("PT1H2M10S")
    3730
    >>> parse_duracao_iso8601("PT10S")
    10
    >>> parse_duracao_iso8601("P0D")
    0

    Levanta ValueError para entradas que não são duração ("", "abc", "PT").
    """
    if not isinstance(texto, str):
        raise ValueError(f"duração não é texto: {texto!r}")
    bruto = texto.strip()
    m = _RE_DURACAO.match(bruto)
    if not m or not any(m.group(nome) for nome in _PESOS):
        raise ValueError(f"duração ISO 8601 inválida: {texto!r}")

    total = 0.0
    for nome, peso in _PESOS.items():
        valor = m.group(nome)
        if valor:
            total += float(valor.replace(",", ".")) * peso
    return int(round(total))


# --------------------------------------------------------------------------
# Cliente HTTP
# --------------------------------------------------------------------------

class ClienteYouTube:
    """Wrapper fino sobre requests com retry exponencial em 5xx e timeout."""

    def __init__(
        self,
        api_key: str,
        sessao: Optional[requests.Session] = None,
        timeout: int = TIMEOUT_PADRAO,
        tentativas: int = TENTATIVAS_PADRAO,
        dormir=time.sleep,
    ) -> None:
        self.api_key = api_key
        self.sessao = sessao or requests.Session()
        self.timeout = timeout
        self.tentativas = max(1, tentativas)
        self.dormir = dormir
        self.chamadas = 0  # unidades de quota gastas (1 por chamada nestes endpoints)

    def get(self, recurso: str, **params: Any) -> dict:
        params = {k: v for k, v in params.items() if v is not None}
        params["key"] = self.api_key
        url = f"{API_BASE}/{recurso}"

        ultimo_erro: Optional[Exception] = None
        for tentativa in range(self.tentativas):
            if tentativa:
                espera = min(2 ** tentativa, 32)
                print(
                    f"  ... nova tentativa em {espera}s "
                    f"({tentativa + 1}/{self.tentativas}): {ultimo_erro}",
                    file=sys.stderr,
                )
                self.dormir(espera)
            try:
                resposta = self.sessao.get(url, params=params, timeout=self.timeout)
            except (requests.Timeout, requests.ConnectionError) as exc:
                ultimo_erro = exc
                continue

            if resposta.status_code >= 500:
                ultimo_erro = RuntimeError(
                    f"HTTP {resposta.status_code} em {recurso}"
                )
                continue

            self.chamadas += 1
            if resposta.status_code >= 400:
                self._erro_cliente(recurso, resposta)
            return resposta.json()

        raise ErroInventario(
            f"Falha ao chamar {recurso} depois de {self.tentativas} tentativas: "
            f"{ultimo_erro}"
        )

    @staticmethod
    def _erro_cliente(recurso: str, resposta: requests.Response) -> None:
        try:
            corpo = resposta.json()
        except ValueError:
            corpo = {}
        erro = corpo.get("error", {}) if isinstance(corpo, dict) else {}
        detalhes = erro.get("errors") or [{}]
        motivo = detalhes[0].get("reason", "")
        mensagem = erro.get("message", resposta.text[:300])

        if motivo in {"quotaExceeded", "dailyLimitExceeded", "rateLimitExceeded"}:
            raise ErroQuota(
                "A cota diária da YouTube Data API acabou (motivo: "
                f"{motivo}).\n"
                "A cota zera à meia-noite no horário do Pacífico (≈04:00 ou "
                "05:00 em Brasília).\n"
                "Opções: esperar a virada, usar outra API key ou pedir aumento "
                "de quota no Google Cloud Console.\n"
                f"Mensagem da API: {mensagem}"
            )
        if motivo in {"keyInvalid", "badRequest"} or resposta.status_code == 400:
            raise ErroInventario(
                "A API key foi recusada. Confira o valor de YOUTUBE_API_KEY e "
                "se a 'YouTube Data API v3' está ativada no projeto do Google "
                f"Cloud.\nMensagem da API: {mensagem}"
            )
        if motivo in {"ipRefererBlocked", "forbidden"} or resposta.status_code == 403:
            raise ErroInventario(
                "Acesso negado pela API (403). Se a key tem restrição de "
                "referer/IP, remova-a para uso em linha de comando.\n"
                f"Motivo: {motivo or 'desconhecido'} — {mensagem}"
            )
        if resposta.status_code == 404:
            raise ErroInventario(
                f"Recurso não encontrado em {recurso}: {mensagem}"
            )
        raise ErroInventario(
            f"HTTP {resposta.status_code} em {recurso}: {mensagem}"
        )


# --------------------------------------------------------------------------
# Passos da coleta
# --------------------------------------------------------------------------

_RE_CANAL = re.compile(r"(UC[0-9A-Za-z_-]{22})")


def normaliza_canal(valor: str) -> str:
    """Aceita o ID cru ou uma URL que contenha o ID (UC...)."""
    m = _RE_CANAL.search(valor or "")
    if not m:
        raise ErroInventario(
            f"'{valor}' não parece um ID de canal. Use o formato UCxxxxxxxx "
            "(24 caracteres começando em UC) ou uma URL /channel/UC..."
        )
    return m.group(1)


def playlist_de_uploads(cliente: ClienteYouTube, canal_id: str) -> tuple[str, str]:
    """Devolve (playlist_id_de_uploads, titulo_do_canal)."""
    dados = cliente.get("channels", part="contentDetails,snippet", id=canal_id)
    itens = dados.get("items") or []
    if not itens:
        raise ErroInventario(
            f"Canal {canal_id} não encontrado (ou sem vídeos públicos). "
            "Confira o ID."
        )
    item = itens[0]
    try:
        playlist = item["contentDetails"]["relatedPlaylists"]["uploads"]
    except KeyError:
        raise ErroInventario(
            f"O canal {canal_id} não expõe a playlist de uploads."
        ) from None
    titulo = (item.get("snippet") or {}).get("title", canal_id)
    return playlist, titulo


def ids_da_playlist(
    cliente: ClienteYouTube, playlist_id: str, limite: Optional[int] = None
) -> list[str]:
    """Pagina playlistItems.list e devolve os video IDs, do mais novo ao mais antigo."""
    ids: list[str] = []
    vistos: set[str] = set()
    token: Optional[str] = None
    pagina = 0

    while True:
        pagina += 1
        dados = cliente.get(
            "playlistItems",
            part="contentDetails",
            playlistId=playlist_id,
            maxResults=50,
            pageToken=token,
        )
        for item in dados.get("items", []):
            vid = (item.get("contentDetails") or {}).get("videoId")
            if vid and vid not in vistos:
                vistos.add(vid)
                ids.append(vid)
        print(f"  página {pagina}: {len(ids)} vídeos acumulados", file=sys.stderr)

        if limite is not None and len(ids) >= limite:
            return ids[:limite]
        token = dados.get("nextPageToken")
        if not token:
            return ids


def lotes(itens: list[str], tamanho: int = 50) -> Iterator[list[str]]:
    for i in range(0, len(itens), tamanho):
        yield itens[i : i + tamanho]


def monta_video(item: dict) -> Video:
    """Converte um item de videos.list no modelo `Video`."""
    snippet = item.get("snippet") or {}
    detalhes = item.get("contentDetails") or {}
    stats = item.get("statistics") or {}
    video_id = item.get("id", "")

    try:
        duracao = parse_duracao_iso8601(detalhes.get("duration", ""))
    except ValueError:
        # Lives em andamento e alguns vídeos sem duração publicada caem aqui.
        duracao = 0

    visualizacoes: Optional[int]
    try:
        visualizacoes = int(stats["viewCount"])
    except (KeyError, TypeError, ValueError):
        visualizacoes = None

    # contentDetails.caption chega como a STRING "true"/"false" — nunca bool.
    # SINAL FRACO: legendas automáticas (ASR) costumam vir como "false" mesmo
    # quando existem. Quem confirma de verdade é o 02_legendas.py, que pergunta
    # ao yt-dlp e preenche `legendas_disponiveis`.
    tem_legenda_api: Optional[bool]
    bruto_caption = detalhes.get("caption")
    if isinstance(bruto_caption, bool):
        tem_legenda_api = bruto_caption
    elif isinstance(bruto_caption, str):
        tem_legenda_api = bruto_caption.strip().lower() == "true"
    else:
        tem_legenda_api = None

    return Video(
        video_id=video_id,
        titulo=snippet.get("title", ""),
        url=f"https://www.youtube.com/watch?v={video_id}",
        publicado_em=snippet.get("publishedAt", ""),
        duracao_s=duracao,
        # A presença de liveStreamingDetails é o que separa live de vídeo comum:
        # sobrevive ao fim da transmissão (o VOD da live mantém o bloco).
        tipo="live" if item.get("liveStreamingDetails") else "video",
        tem_legenda_api=tem_legenda_api,
        legendas_disponiveis=[],
        visualizacoes=visualizacoes,
    )


def busca_metadados(cliente: ClienteYouTube, ids: list[str]) -> list[Video]:
    videos: list[Video] = []
    total_lotes = (len(ids) + 49) // 50
    for i, lote in enumerate(lotes(ids, 50), start=1):
        dados = cliente.get(
            "videos",
            part="snippet,contentDetails,statistics,liveStreamingDetails",
            id=",".join(lote),
            maxResults=50,
        )
        itens = dados.get("items", [])
        videos.extend(monta_video(item) for item in itens)
        faltando = len(lote) - len(itens)
        extra = f" ({faltando} indisponíveis)" if faltando else ""
        print(
            f"  lote {i}/{total_lotes}: {len(videos)} com metadados{extra}",
            file=sys.stderr,
        )
    return videos


# --------------------------------------------------------------------------
# Saída
# --------------------------------------------------------------------------

def grava_jsonl(videos: Iterable[Video], destino: Path) -> int:
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporario = destino.with_suffix(destino.suffix + ".tmp")
    n = 0
    with temporario.open("w", encoding="utf-8") as fh:
        for v in videos:
            fh.write(json.dumps(v.model_dump(), ensure_ascii=False) + "\n")
            n += 1
    temporario.replace(destino)
    return n


def _horas(segundos: int) -> str:
    return f"{segundos / 3600:.1f}".replace(".", ",")


def _pct(parte: int, total: int) -> str:
    if not total:
        return "0,0%"
    return f"{100 * parte / total:.1f}".replace(".", ",") + "%"


def monta_resumo(videos: list[Video], canal: str, destino: Path, quota: int = 0) -> str:
    """Bloco compacto para o usuário colar de volta no chat."""
    total = len(videos)
    comuns = [v for v in videos if v.tipo == "video"]
    lives = [v for v in videos if v.tipo == "live"]
    seg_total = sum(v.duracao_s for v in videos)
    seg_comuns = sum(v.duracao_s for v in comuns)
    seg_lives = sum(v.duracao_s for v in lives)
    com_legenda = sum(1 for v in videos if v.tem_legenda_api)
    sem_duracao = sum(1 for v in videos if v.duracao_s == 0)

    datas = sorted(v.publicado_em[:10] for v in videos if v.publicado_em)
    periodo = f"{datas[0]} → {datas[-1]}" if datas else "—"
    media_min = (seg_total / total / 60) if total else 0

    linhas = [
        "=" * 58,
        f"INVENTÁRIO — {canal}",
        "=" * 58,
        f"Total de vídeos ....... {total}",
        f"  vídeos comuns ....... {len(comuns):>5}   {_horas(seg_comuns):>8} h",
        f"  lives ............... {len(lives):>5}   {_horas(seg_lives):>8} h",
        f"Duração total ......... {_horas(seg_total)} h "
        f"(média {f'{media_min:.1f}'.replace('.', ',')} min por vídeo)",
        f"Período ............... {periodo}",
        f"Com legenda (API) ..... {com_legenda} de {total} "
        f"({_pct(com_legenda, total)}) — sinal fraco, o passo 2 confirma",
    ]
    if sem_duracao:
        linhas.append(
            f"Sem duração publicada .. {sem_duracao} (lives em andamento ou "
            "vídeos indisponíveis)"
        )
    linhas += [
        f"Arquivo ............... {destino}",
        f"Quota gasta ........... ~{quota} de 10.000 unidades/dia",
        "=" * 58,
    ]
    return "\n".join(linhas)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def monta_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="01_inventario.py",
        description=(
            "Lista TODOS os vídeos de um canal do YouTube (incluindo lives) e "
            "grava um inventário JSONL para as etapas seguintes do pipeline."
        ),
        epilog=(
            "Requer a variável de ambiente YOUTUBE_API_KEY (API key da YouTube "
            "Data API v3).\n"
            "QUOTA: a API dá 10.000 unidades por dia. Este fluxo gasta ~40 "
            "unidades para um canal de ~875 vídeos (1 em channels.list + 1 por "
            "página de 50 na playlist + 1 por lote de 50 em videos.list), ou "
            "seja, menos de 0,5% da cota diária.\n\n"
            "Exemplos:\n"
            "  export YOUTUBE_API_KEY=AIza...\n"
            "  python 01_inventario.py --canal UCxxxxxxxxxxxxxxxxxxxxxx\n"
            "  python 01_inventario.py --canal UCxxxx --limite 10   # teste rápido\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--canal",
        required=True,
        metavar="UCxxxx",
        help="ID do canal (UC... com 24 caracteres) ou URL /channel/UC...",
    )
    p.add_argument(
        "--saida",
        default="dados/inventario.jsonl",
        type=Path,
        help="arquivo JSONL de saída (padrão: dados/inventario.jsonl)",
    )
    p.add_argument(
        "--limite",
        type=int,
        default=None,
        metavar="N",
        help="processa no máximo N vídeos (os mais recentes) — para testar",
    )
    p.add_argument(
        "--timeout",
        type=int,
        default=TIMEOUT_PADRAO,
        help=f"timeout de cada requisição, em segundos (padrão: {TIMEOUT_PADRAO})",
    )
    p.add_argument(
        "--tentativas",
        type=int,
        default=TENTATIVAS_PADRAO,
        help=(
            "tentativas por requisição, com backoff exponencial em erros 5xx "
            f"(padrão: {TENTATIVAS_PADRAO})"
        ),
    )
    return p


def chave_api(ambiente: Optional[dict] = None) -> str:
    env = os.environ if ambiente is None else ambiente
    chave = (env.get("YOUTUBE_API_KEY") or "").strip()
    if not chave:
        raise ErroInventario(
            "A variável de ambiente YOUTUBE_API_KEY não está definida.\n"
            "Crie uma API key em https://console.cloud.google.com/apis/credentials "
            "(com a 'YouTube Data API v3' ativada) e exporte:\n"
            "    export YOUTUBE_API_KEY='AIza...'\n"
            "Para deixar permanente, acrescente essa linha ao ~/.bashrc ou ~/.zshrc."
        )
    return chave


def main(argv: Optional[list[str]] = None) -> int:
    args = monta_parser().parse_args(argv)
    try:
        chave = chave_api()
        canal_id = normaliza_canal(args.canal)
        cliente = ClienteYouTube(
            chave, timeout=args.timeout, tentativas=args.tentativas
        )

        print(f"Canal: {canal_id}", file=sys.stderr)
        playlist, titulo = playlist_de_uploads(cliente, canal_id)
        print(f"Uploads: {playlist} ({titulo})", file=sys.stderr)

        print("Listando IDs...", file=sys.stderr)
        ids = ids_da_playlist(cliente, playlist, limite=args.limite)
        if not ids:
            raise ErroInventario("Nenhum vídeo encontrado na playlist de uploads.")

        print(f"Buscando metadados de {len(ids)} vídeos...", file=sys.stderr)
        videos = busca_metadados(cliente, ids)

        # Do mais antigo para o mais novo: a ordem cronológica é a que interessa
        # para as etapas seguintes.
        videos.sort(key=lambda v: v.publicado_em)
        grava_jsonl(videos, args.saida)

        print()
        print(monta_resumo(videos, f"{titulo} ({canal_id})", args.saida, cliente.chamadas))
        return 0
    except ErroInventario as exc:
        print(f"\nERRO: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nInterrompido pelo usuário.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
