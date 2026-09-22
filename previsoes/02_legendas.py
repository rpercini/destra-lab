#!/usr/bin/env python3
"""Etapa 2 — download das legendas com yt-dlp.

Lê o inventário da etapa 1, baixa para cada vídeo as legendas em português
(manuais e automáticas) no formato json3 — que traz timing por palavra, o que
a etapa 3 usa para cortar os chunks — e reescreve o inventário com o campo
`legendas_disponiveis` preenchido. Essa é a confirmação real de quem tem
legenda: o `tem_legenda_api` da etapa 1 é só um palpite.

Não usa a YouTube Data API (nenhuma quota é gasta aqui). Usa o binário
`yt-dlp`, que o usuário instala por fora:  pipx install yt-dlp

O script é RETOMÁVEL: vídeos que já têm arquivo de legenda no disco são
pulados. Pode interromper com Ctrl+C e rodar de novo.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
from esquema import Video  # noqa: E402

SUB_LANGS_PADRAO = "pt.*,pt-BR,pt-orig"
SLEEP_PADRAO = 2.0
TENTATIVAS_PADRAO = 3
TIMEOUT_PADRAO = 300

# Trechos que o YouTube devolve quando começa a barrar o IP. Quando aparecem,
# não adianta insistir rápido: o script espera mais antes da próxima tentativa.
SINAIS_BLOQUEIO = (
    "http error 429",
    "too many requests",
    "sign in to confirm",
    "confirm you're not a bot",
    "rate-limit",
    "rate limit",
    "temporarily blocked",
)


class ErroLegendas(Exception):
    """Erro previsto, exibido ao usuário sem traceback."""


# --------------------------------------------------------------------------
# Inventário
# --------------------------------------------------------------------------

def le_inventario(caminho: Path) -> list[Video]:
    if not caminho.exists():
        raise ErroLegendas(
            f"Inventário não encontrado em {caminho}.\n"
            "Rode antes:  python 01_inventario.py --canal UCxxxx"
        )
    videos: list[Video] = []
    with caminho.open(encoding="utf-8") as fh:
        for n, linha in enumerate(fh, start=1):
            linha = linha.strip()
            if not linha:
                continue
            try:
                videos.append(Video.model_validate_json(linha))
            except Exception as exc:  # pydantic.ValidationError e JSON inválido
                raise ErroLegendas(
                    f"Linha {n} de {caminho} não bate com o modelo Video: {exc}"
                ) from None
    if not videos:
        raise ErroLegendas(f"{caminho} está vazio.")
    return videos


def grava_inventario(videos: Iterable[Video], caminho: Path) -> None:
    """Reescrita atômica: grava num .tmp e só então substitui o original."""
    caminho.parent.mkdir(parents=True, exist_ok=True)
    temporario = caminho.with_suffix(caminho.suffix + ".tmp")
    with temporario.open("w", encoding="utf-8") as fh:
        for v in videos:
            fh.write(json.dumps(v.model_dump(), ensure_ascii=False) + "\n")
    temporario.replace(caminho)


# --------------------------------------------------------------------------
# Arquivos de legenda no disco
# --------------------------------------------------------------------------

def idiomas_no_disco(video_id: str, dir_legendas: Path) -> list[str]:
    """Idiomas já baixados, lidos do nome dos arquivos <id>.<lang>.json3."""
    if not dir_legendas.exists():
        return []
    idiomas: list[str] = []
    for arquivo in sorted(dir_legendas.glob(f"{video_id}.*.json3")):
        if arquivo.stat().st_size == 0:
            continue
        miolo = arquivo.name[len(video_id) + 1 : -len(".json3")]
        if miolo:
            idiomas.append(miolo)
    return idiomas


# --------------------------------------------------------------------------
# Chamada ao yt-dlp
# --------------------------------------------------------------------------

def monta_comando(
    video_id: str,
    dir_legendas: Path,
    *,
    yt_dlp: str = "yt-dlp",
    sub_langs: str = SUB_LANGS_PADRAO,
    sleep_requests: float = SLEEP_PADRAO,
    max_attempts: int = TENTATIVAS_PADRAO,
) -> list[str]:
    return [
        yt_dlp,
        "--skip-download",
        "--write-auto-subs",   # legendas automáticas (ASR) — a maioria do acervo
        "--write-subs",        # legendas manuais, quando existirem
        "--sub-langs", sub_langs,
        "--sub-format", "json3",  # json3 = timing por palavra
        "--sleep-requests", str(sleep_requests),
        "--retries", str(max_attempts),
        "--extractor-retries", str(max_attempts),
        "--no-warnings",
        "--no-progress",
        "--ignore-config",     # ignora ~/.config/yt-dlp/config do usuário
        "-o", f"{dir_legendas}/%(id)s.%(ext)s",
        f"https://www.youtube.com/watch?v={video_id}",
    ]


@dataclass
class Resultado:
    video_id: str
    estado: str           # "baixado" | "pulado" | "sem_legenda" | "erro"
    idiomas: list[str] = field(default_factory=list)
    detalhe: str = ""


def _resumo_erro(texto: str, limite: int = 200) -> str:
    linhas = [l.strip() for l in (texto or "").splitlines() if l.strip()]
    relevantes = [l for l in linhas if l.upper().startswith("ERROR")] or linhas
    return (relevantes[-1] if relevantes else "falha sem mensagem")[:limite]


def baixa_legenda(
    video: Video,
    dir_legendas: Path,
    *,
    yt_dlp: str = "yt-dlp",
    sub_langs: str = SUB_LANGS_PADRAO,
    sleep_requests: float = SLEEP_PADRAO,
    max_attempts: int = TENTATIVAS_PADRAO,
    timeout: int = TIMEOUT_PADRAO,
    forcar: bool = False,
    executor: Callable[..., subprocess.CompletedProcess] = subprocess.run,
    dormir: Callable[[float], None] = time.sleep,
) -> Resultado:
    """Baixa (ou confirma) as legendas de um vídeo. Nunca levanta exceção."""
    existentes = idiomas_no_disco(video.video_id, dir_legendas)
    if existentes and not forcar:
        return Resultado(video.video_id, "pulado", existentes)

    dir_legendas.mkdir(parents=True, exist_ok=True)
    comando = monta_comando(
        video.video_id,
        dir_legendas,
        yt_dlp=yt_dlp,
        sub_langs=sub_langs,
        sleep_requests=sleep_requests,
        max_attempts=max_attempts,
    )

    ultimo_detalhe = ""
    for tentativa in range(1, max_attempts + 1):
        if tentativa > 1:
            # Backoff exponencial; bem mais longo se o YouTube sinalizou bloqueio.
            espera = sleep_requests * (2 ** (tentativa - 1))
            if any(s in ultimo_detalhe.lower() for s in SINAIS_BLOQUEIO):
                espera = max(espera, 30.0) * tentativa
            dormir(espera)
        try:
            proc = executor(
                comando,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            ultimo_detalhe = f"timeout de {timeout}s no yt-dlp"
            continue
        except FileNotFoundError:
            raise ErroLegendas(
                f"Binário '{yt_dlp}' não encontrado. Instale com: pipx install yt-dlp"
            ) from None

        saida = f"{proc.stdout or ''}\n{proc.stderr or ''}"
        if proc.returncode == 0:
            idiomas = idiomas_no_disco(video.video_id, dir_legendas)
            if idiomas:
                return Resultado(video.video_id, "baixado", idiomas)
            # yt-dlp terminou bem mas não havia legenda em português:
            # o vídeo vai para a fila do Whisper.
            return Resultado(
                video.video_id, "sem_legenda", [], "sem legenda em português"
            )
        ultimo_detalhe = _resumo_erro(saida)

        # Vídeo removido/privado/bloqueado: insistir não resolve.
        baixo = ultimo_detalhe.lower()
        if any(
            s in baixo
            for s in ("private video", "video unavailable", "removed by the uploader",
                      "members-only", "this video is not available")
        ):
            return Resultado(video.video_id, "erro", [], ultimo_detalhe)

    return Resultado(video.video_id, "erro", [], ultimo_detalhe or "falhou")


# --------------------------------------------------------------------------
# Laço principal
# --------------------------------------------------------------------------

class Progresso:
    """Contador thread-safe, sem dependência externa."""

    def __init__(self, total: int) -> None:
        self.total = total
        self.feitos = 0
        self._trava = threading.Lock()
        self._largura = len(str(total))

    def registra(self, resultado: Resultado) -> None:
        with self._trava:
            self.feitos += 1
            n = self.feitos
        marca = {
            "baixado": "ok",
            "pulado": "já existia",
            "sem_legenda": "SEM LEGENDA",
            "erro": "ERRO",
        }[resultado.estado]
        detalhe = ""
        if resultado.idiomas:
            detalhe = f" [{', '.join(resultado.idiomas)}]"
        elif resultado.detalhe:
            detalhe = f" — {resultado.detalhe}"
        print(
            f"[{n:>{self._largura}}/{self.total}] {resultado.video_id}  "
            f"{marca}{detalhe}",
            flush=True,
        )


def processa(
    videos: list[Video],
    dir_legendas: Path,
    *,
    jobs: int = 1,
    pausa_entre_videos: float = SLEEP_PADRAO,
    **kwargs,
) -> dict[str, Resultado]:
    """Processa a lista e devolve {video_id: Resultado}. Respeita Ctrl+C."""
    progresso = Progresso(len(videos))
    resultados: dict[str, Resultado] = {}

    def tarefa(video: Video) -> Resultado:
        resultado = baixa_legenda(video, dir_legendas, **kwargs)
        progresso.registra(resultado)
        # Pausa só depois de bater no YouTube de verdade (pular é de graça).
        if resultado.estado != "pulado" and pausa_entre_videos > 0:
            kwargs.get("dormir", time.sleep)(pausa_entre_videos)
        return resultado

    if jobs <= 1:
        for video in videos:
            resultados[video.video_id] = tarefa(video)
        return resultados

    with ThreadPoolExecutor(max_workers=jobs) as pool:
        futuros = {pool.submit(tarefa, v): v for v in videos}
        try:
            for futuro in as_completed(futuros):
                video = futuros[futuro]
                resultados[video.video_id] = futuro.result()
        except KeyboardInterrupt:
            for f in futuros:
                f.cancel()
            raise
    return resultados


def aplica_resultados(
    videos: list[Video], resultados: dict[str, Resultado]
) -> list[Video]:
    for video in videos:
        resultado = resultados.get(video.video_id)
        if resultado is not None:
            video.legendas_disponiveis = resultado.idiomas
    return videos


def monta_resumo(
    resultados: dict[str, Resultado], total: int, arquivo_sem_legenda: Path
) -> str:
    contagem = {"baixado": 0, "pulado": 0, "sem_legenda": 0, "erro": 0}
    for r in resultados.values():
        contagem[r.estado] += 1
    pendentes = total - len(resultados)
    sem_legenda = contagem["sem_legenda"] + contagem["erro"]

    linhas = [
        "=" * 58,
        "LEGENDAS",
        "=" * 58,
        f"Processados ........... {len(resultados)} de {total}",
        f"  baixados agora ...... {contagem['baixado']}",
        f"  já existiam ......... {contagem['pulado']}",
        f"  sem legenda em pt ... {contagem['sem_legenda']}",
        f"  erros ............... {contagem['erro']}",
    ]
    if pendentes:
        linhas.append(
            f"Não processados ....... {pendentes} (rode de novo para continuar)"
        )
    linhas += [
        f"Para o Whisper ........ {sem_legenda} vídeos → {arquivo_sem_legenda}",
        "=" * 58,
    ]
    return "\n".join(linhas)


def grava_sem_legenda(
    resultados: dict[str, Resultado], caminho: Path
) -> list[str]:
    ids = sorted(
        vid for vid, r in resultados.items() if r.estado in {"sem_legenda", "erro"}
    )
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text("\n".join(ids) + ("\n" if ids else ""), encoding="utf-8")
    return ids


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def monta_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="02_legendas.py",
        description=(
            "Baixa as legendas em português (automáticas e manuais) de todos os "
            "vídeos do inventário, via yt-dlp, no formato json3."
        ),
        epilog=(
            "Requer o binário yt-dlp no PATH:  pipx install yt-dlp\n"
            "Nenhuma quota da YouTube Data API é gasta aqui.\n\n"
            "RETOMÁVEL: vídeos que já têm arquivo em dados/legendas/ são pulados,\n"
            "então pode interromper com Ctrl+C e rodar de novo quando quiser.\n\n"
            "RITMO: o padrão (--sleep-requests 2 --jobs 1) leva várias horas para\n"
            "875 vídeos, e é assim de propósito. Acelerar demais faz o YouTube\n"
            "responder 429 / 'Sign in to confirm you're not a bot' e derrubar o\n"
            "restante da fila.\n\n"
            "Exemplos:\n"
            "  python 02_legendas.py\n"
            "  python 02_legendas.py --limite 5            # teste\n"
            "  python 02_legendas.py --jobs 2 --sleep-requests 3\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--inventario",
        type=Path,
        default=Path("dados/inventario.jsonl"),
        help="inventário da etapa 1 (padrão: dados/inventario.jsonl)",
    )
    p.add_argument(
        "--dir-legendas",
        type=Path,
        default=Path("dados/legendas"),
        help="onde gravar os .json3 (padrão: dados/legendas)",
    )
    p.add_argument(
        "--sem-legenda",
        type=Path,
        default=Path("dados/sem_legenda.txt"),
        help="lista de IDs que vão para o Whisper (padrão: dados/sem_legenda.txt)",
    )
    p.add_argument(
        "--sleep-requests",
        type=float,
        default=SLEEP_PADRAO,
        metavar="SEG",
        help=(
            "pausa entre requisições, repassada ao yt-dlp e também usada entre "
            f"vídeos (padrão: {SLEEP_PADRAO:g}s). Não abaixe sem motivo"
        ),
    )
    p.add_argument(
        "--max-attempts",
        type=int,
        default=TENTATIVAS_PADRAO,
        metavar="N",
        help=(
            "tentativas por vídeo, com backoff exponencial "
            f"(padrão: {TENTATIVAS_PADRAO})"
        ),
    )
    p.add_argument(
        "--jobs",
        type=int,
        default=1,
        metavar="N",
        help="downloads em paralelo (padrão: 1). Acima de 3 o bloqueio é quase certo",
    )
    p.add_argument(
        "--limite",
        type=int,
        default=None,
        metavar="N",
        help="processa no máximo N vídeos do inventário — para testar",
    )
    p.add_argument(
        "--timeout",
        type=int,
        default=TIMEOUT_PADRAO,
        help=f"timeout de cada chamada ao yt-dlp, em segundos (padrão: {TIMEOUT_PADRAO})",
    )
    p.add_argument(
        "--sub-langs",
        default=SUB_LANGS_PADRAO,
        help=f"idiomas pedidos ao yt-dlp (padrão: {SUB_LANGS_PADRAO})",
    )
    p.add_argument(
        "--yt-dlp",
        default="yt-dlp",
        help="caminho do binário yt-dlp (padrão: yt-dlp)",
    )
    p.add_argument(
        "--forcar",
        action="store_true",
        help="rebaixa mesmo quem já tem arquivo no disco",
    )
    return p


def main(argv: Optional[list[str]] = None) -> int:
    args = monta_parser().parse_args(argv)
    try:
        if shutil.which(args.yt_dlp) is None and not Path(args.yt_dlp).exists():
            raise ErroLegendas(
                f"Binário '{args.yt_dlp}' não encontrado no PATH.\n"
                "Instale com:  pipx install yt-dlp   (ou: pip install -U yt-dlp)"
            )
        if args.jobs < 1:
            raise ErroLegendas("--jobs precisa ser pelo menos 1.")

        videos = le_inventario(args.inventario)
        alvo = videos[: args.limite] if args.limite else videos
        args.dir_legendas.mkdir(parents=True, exist_ok=True)

        ja_no_disco = sum(
            1 for v in alvo if idiomas_no_disco(v.video_id, args.dir_legendas)
        )
        print(
            f"{len(alvo)} vídeos na fila ({ja_no_disco} já com legenda no disco, "
            f"serão pulados)\n"
            f"yt-dlp: {args.yt_dlp} | jobs: {args.jobs} | "
            f"pausa: {args.sleep_requests:g}s | tentativas: {args.max_attempts}\n",
            flush=True,
        )

        resultados: dict[str, Resultado] = {}
        try:
            resultados = processa(
                alvo,
                args.dir_legendas,
                jobs=args.jobs,
                pausa_entre_videos=args.sleep_requests,
                yt_dlp=args.yt_dlp,
                sub_langs=args.sub_langs,
                sleep_requests=args.sleep_requests,
                max_attempts=args.max_attempts,
                timeout=args.timeout,
                forcar=args.forcar,
            )
        except KeyboardInterrupt:
            print(
                "\nInterrompido. Gravando o que já foi feito — "
                "rode de novo para continuar de onde parou.",
                file=sys.stderr,
            )

        # Mesmo interrompido, o inventário é reescrito com o que se sabe até aqui.
        aplica_resultados(videos, resultados)
        grava_inventario(videos, args.inventario)
        grava_sem_legenda(resultados, args.sem_legenda)

        print()
        print(monta_resumo(resultados, len(alvo), args.sem_legenda))
        print(f"Inventário atualizado: {args.inventario}")
        return 0
    except ErroLegendas as exc:
        print(f"\nERRO: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
