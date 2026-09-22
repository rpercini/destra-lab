"""Testes do 02_legendas.py — o yt-dlp é sempre um dublê; nada vai à rede."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from esquema import Video

# Uma resposta json3 mínima, no formato que o yt-dlp grava (events com wSegs).
JSON3_EXEMPLO = {
    "wireMagic": "pb3",
    "events": [
        {
            "tStartMs": 1200,
            "dDurationMs": 2600,
            "segs": [
                {"utf8": "a inflação", "tOffsetMs": 0},
                {"utf8": " vai cair", "tOffsetMs": 900},
            ],
        }
    ],
}


def faz_video(video_id: str = "vidTeste001", **kw) -> Video:
    base = dict(
        video_id=video_id,
        titulo="Título de teste",
        url=f"https://www.youtube.com/watch?v={video_id}",
        publicado_em="2024-05-02T18:00:00Z",
        duracao_s=3730,
        tipo="video",
        tem_legenda_api=False,
    )
    base.update(kw)
    return Video(**base)


def escreve_legenda(dir_legendas: Path, video_id: str, lang: str = "pt") -> Path:
    dir_legendas.mkdir(parents=True, exist_ok=True)
    arquivo = dir_legendas / f"{video_id}.{lang}.json3"
    arquivo.write_text(json.dumps(JSON3_EXEMPLO), encoding="utf-8")
    return arquivo


class ExecutorFalso:
    """Substitui subprocess.run. `roteiro` define o que cada chamada faz."""

    def __init__(self, roteiro=None, dir_legendas: Path | None = None):
        # roteiro: lista de (returncode, [langs a criar], mensagem_stderr)
        self.roteiro = list(roteiro or [(0, ["pt"], "")])
        self.dir_legendas = dir_legendas
        self.comandos: list[list[str]] = []

    def __call__(self, comando, capture_output=True, text=True, timeout=None):
        self.comandos.append(comando)
        passo = self.roteiro[min(len(self.comandos) - 1, len(self.roteiro) - 1)]
        if isinstance(passo, Exception):
            raise passo
        rc, langs, erro = passo
        video_id = comando[-1].split("v=")[-1]
        for lang in langs:
            escreve_legenda(self.dir_legendas, video_id, lang)
        return subprocess.CompletedProcess(comando, rc, stdout="", stderr=erro)


# --------------------------------------------------------------------------
# Arquivos no disco
# --------------------------------------------------------------------------

def test_idiomas_no_disco(leg, tmp_path):
    escreve_legenda(tmp_path, "vidTeste001", "pt")
    escreve_legenda(tmp_path, "vidTeste001", "pt-BR")
    escreve_legenda(tmp_path, "outroVideo1", "pt")
    assert leg.idiomas_no_disco("vidTeste001", tmp_path) == ["pt", "pt-BR"]
    assert leg.idiomas_no_disco("naoExiste00", tmp_path) == []


def test_idiomas_ignora_arquivo_vazio(leg, tmp_path):
    (tmp_path / "vidTeste001.pt.json3").write_text("", encoding="utf-8")
    assert leg.idiomas_no_disco("vidTeste001", tmp_path) == []


def test_idiomas_diretorio_inexistente(leg, tmp_path):
    assert leg.idiomas_no_disco("vidTeste001", tmp_path / "nao_existe") == []


# --------------------------------------------------------------------------
# Comando do yt-dlp
# --------------------------------------------------------------------------

def test_monta_comando(leg, tmp_path):
    cmd = leg.monta_comando(
        "vidTeste001", tmp_path, sleep_requests=3, max_attempts=4
    )
    assert cmd[0] == "yt-dlp"
    assert "--skip-download" in cmd
    assert "--write-auto-subs" in cmd and "--write-subs" in cmd
    assert cmd[cmd.index("--sub-langs") + 1] == "pt.*,pt-BR,pt-orig"
    assert cmd[cmd.index("--sub-format") + 1] == "json3"
    assert cmd[cmd.index("--sleep-requests") + 1] == "3"
    assert cmd[cmd.index("--retries") + 1] == "4"
    assert cmd[cmd.index("-o") + 1] == f"{tmp_path}/%(id)s.%(ext)s"
    assert cmd[-1] == "https://www.youtube.com/watch?v=vidTeste001"


# --------------------------------------------------------------------------
# Download de um vídeo
# --------------------------------------------------------------------------

def test_baixa_com_sucesso(leg, tmp_path):
    executor = ExecutorFalso([(0, ["pt", "pt-orig"], "")], tmp_path)
    r = leg.baixa_legenda(faz_video(), tmp_path, executor=executor, dormir=lambda s: None)
    assert r.estado == "baixado"
    assert r.idiomas == ["pt", "pt-orig"]
    assert len(executor.comandos) == 1


def test_pula_quem_ja_tem_arquivo(leg, tmp_path):
    escreve_legenda(tmp_path, "vidTeste001", "pt")
    executor = ExecutorFalso(dir_legendas=tmp_path)
    r = leg.baixa_legenda(faz_video(), tmp_path, executor=executor)
    assert r.estado == "pulado"
    assert r.idiomas == ["pt"]
    assert executor.comandos == []      # retomável: nem chamou o yt-dlp


def test_forcar_rebaixa(leg, tmp_path):
    escreve_legenda(tmp_path, "vidTeste001", "pt")
    executor = ExecutorFalso([(0, ["pt"], "")], tmp_path)
    r = leg.baixa_legenda(
        faz_video(), tmp_path, executor=executor, forcar=True, dormir=lambda s: None
    )
    assert r.estado == "baixado"
    assert len(executor.comandos) == 1


def test_sucesso_sem_legenda_em_portugues(leg, tmp_path):
    executor = ExecutorFalso([(0, [], "")], tmp_path)
    r = leg.baixa_legenda(faz_video(), tmp_path, executor=executor, dormir=lambda s: None)
    assert r.estado == "sem_legenda"
    assert r.idiomas == []


def test_retenta_e_depois_acerta(leg, tmp_path):
    esperas: list[float] = []
    executor = ExecutorFalso(
        [(1, [], "ERROR: unable to download video data: HTTP Error 429"),
         (0, ["pt"], "")],
        tmp_path,
    )
    r = leg.baixa_legenda(
        faz_video(), tmp_path, executor=executor,
        sleep_requests=2, max_attempts=3, dormir=esperas.append,
    )
    assert r.estado == "baixado"
    assert len(executor.comandos) == 2
    # sinal de bloqueio (429) => espera longa antes de tentar de novo
    assert esperas and esperas[0] >= 30


def test_desiste_depois_das_tentativas(leg, tmp_path):
    executor = ExecutorFalso([(1, [], "ERROR: algo deu errado")], tmp_path)
    r = leg.baixa_legenda(
        faz_video(), tmp_path, executor=executor, max_attempts=3, dormir=lambda s: None
    )
    assert r.estado == "erro"
    assert "algo deu errado" in r.detalhe
    assert len(executor.comandos) == 3


def test_video_privado_nao_retenta(leg, tmp_path):
    executor = ExecutorFalso([(1, [], "ERROR: Private video. Sign in ...")], tmp_path)
    r = leg.baixa_legenda(
        faz_video(), tmp_path, executor=executor, max_attempts=3, dormir=lambda s: None
    )
    assert r.estado == "erro"
    assert len(executor.comandos) == 1   # insistir não resolveria


def test_timeout_vira_erro(leg, tmp_path):
    executor = ExecutorFalso(
        [subprocess.TimeoutExpired(cmd="yt-dlp", timeout=1)] * 2, tmp_path
    )
    r = leg.baixa_legenda(
        faz_video(), tmp_path, executor=executor, max_attempts=2, dormir=lambda s: None
    )
    assert r.estado == "erro"
    assert "timeout" in r.detalhe


def test_binario_ausente(leg, tmp_path):
    def sem_binario(*a, **k):
        raise FileNotFoundError("yt-dlp")

    with pytest.raises(leg.ErroLegendas, match="yt-dlp"):
        leg.baixa_legenda(faz_video(), tmp_path, executor=sem_binario)


# --------------------------------------------------------------------------
# Laço, inventário e saídas
# --------------------------------------------------------------------------

def test_processa_sequencial_e_mistura_de_estados(leg, tmp_path, capsys):
    videos = [faz_video(f"vidTeste00{i}") for i in range(1, 5)]
    escreve_legenda(tmp_path, "vidTeste002", "pt")   # já existia
    roteiro = [(0, ["pt"], ""), (0, [], ""), (1, [], "ERROR: falhou feio")]
    executor = ExecutorFalso(roteiro, tmp_path)
    resultados = leg.processa(
        videos, tmp_path, jobs=1, pausa_entre_videos=0,
        executor=executor, max_attempts=1, dormir=lambda s: None,
    )
    estados = {vid: r.estado for vid, r in resultados.items()}
    assert estados["vidTeste001"] == "baixado"
    assert estados["vidTeste002"] == "pulado"
    assert estados["vidTeste003"] == "sem_legenda"
    assert estados["vidTeste004"] == "erro"
    saida = capsys.readouterr().out
    assert "[1/4]" in saida and "[4/4]" in saida   # contador de progresso


def test_processa_em_paralelo(leg, tmp_path):
    videos = [faz_video(f"vidTest{i:04d}") for i in range(6)]
    executor = ExecutorFalso([(0, ["pt"], "")], tmp_path)
    resultados = leg.processa(
        videos, tmp_path, jobs=3, pausa_entre_videos=0,
        executor=executor, dormir=lambda s: None,
    )
    assert len(resultados) == 6
    assert all(r.estado == "baixado" for r in resultados.values())


def test_le_e_grava_inventario(leg, tmp_path):
    caminho = tmp_path / "inventario.jsonl"
    videos = [faz_video("vidTeste001"), faz_video("vidTeste002", tipo="live")]
    leg.grava_inventario(videos, caminho)
    relidos = leg.le_inventario(caminho)
    assert [v.video_id for v in relidos] == ["vidTeste001", "vidTeste002"]
    assert relidos[1].tipo == "live"
    assert not list(tmp_path.glob("*.tmp"))


def test_inventario_ausente(leg, tmp_path):
    with pytest.raises(leg.ErroLegendas, match="01_inventario"):
        leg.le_inventario(tmp_path / "nao_existe.jsonl")


def test_inventario_corrompido(leg, tmp_path):
    caminho = tmp_path / "inventario.jsonl"
    caminho.write_text('{"video_id": "x"}\n', encoding="utf-8")
    with pytest.raises(leg.ErroLegendas, match="Linha 1"):
        leg.le_inventario(caminho)


def test_aplica_resultados_atualiza_legendas_disponiveis(leg, tmp_path):
    videos = [faz_video("vidTeste001"), faz_video("vidTeste002")]
    resultados = {
        "vidTeste001": leg.Resultado("vidTeste001", "baixado", ["pt", "pt-BR"]),
        "vidTeste002": leg.Resultado("vidTeste002", "sem_legenda", []),
    }
    leg.aplica_resultados(videos, resultados)
    assert videos[0].legendas_disponiveis == ["pt", "pt-BR"]
    assert videos[1].legendas_disponiveis == []


def test_grava_sem_legenda(leg, tmp_path):
    resultados = {
        "a": leg.Resultado("a", "baixado", ["pt"]),
        "b": leg.Resultado("b", "sem_legenda", []),
        "c": leg.Resultado("c", "erro", [], "falhou"),
        "d": leg.Resultado("d", "pulado", ["pt"]),
    }
    destino = tmp_path / "sub" / "sem_legenda.txt"
    ids = leg.grava_sem_legenda(resultados, destino)
    assert ids == ["b", "c"]
    assert destino.read_text(encoding="utf-8").split() == ["b", "c"]


def test_resumo_final(leg, tmp_path):
    resultados = {
        "a": leg.Resultado("a", "baixado", ["pt"]),
        "b": leg.Resultado("b", "pulado", ["pt"]),
        "c": leg.Resultado("c", "sem_legenda", []),
        "d": leg.Resultado("d", "erro", [], "falhou"),
    }
    texto = leg.monta_resumo(resultados, total=6, arquivo_sem_legenda=tmp_path / "s.txt")
    assert "baixados agora ...... 1" in texto
    assert "já existiam ......... 1" in texto
    assert "sem legenda em pt ... 1" in texto
    assert "erros ............... 1" in texto
    assert "Não processados ....... 2" in texto
    assert "Para o Whisper ........ 2" in texto


def test_main_ponta_a_ponta(leg, tmp_path, monkeypatch, capsys):
    inventario = tmp_path / "inventario.jsonl"
    dir_legendas = tmp_path / "legendas"
    leg.grava_inventario(
        [faz_video("vidTeste001"), faz_video("vidTeste002"), faz_video("vidTeste003")],
        inventario,
    )
    escreve_legenda(dir_legendas, "vidTeste002", "pt")
    executor = ExecutorFalso(
        [(0, ["pt"], ""), (1, [], "ERROR: video unavailable")], dir_legendas
    )
    monkeypatch.setattr(leg.shutil, "which", lambda nome: "/usr/bin/yt-dlp")
    monkeypatch.setattr(leg.subprocess, "run", executor)
    monkeypatch.setattr(leg.time, "sleep", lambda s: None)

    codigo = leg.main([
        "--inventario", str(inventario),
        "--dir-legendas", str(dir_legendas),
        "--sem-legenda", str(tmp_path / "sem_legenda.txt"),
        "--sleep-requests", "0",
        "--max-attempts", "1",
    ])
    assert codigo == 0

    relidos = {v.video_id: v for v in leg.le_inventario(inventario)}
    assert relidos["vidTeste001"].legendas_disponiveis == ["pt"]
    assert relidos["vidTeste002"].legendas_disponiveis == ["pt"]   # pulado, confirmado
    assert relidos["vidTeste003"].legendas_disponiveis == []
    assert (tmp_path / "sem_legenda.txt").read_text().split() == ["vidTeste003"]
    assert "LEGENDAS" in capsys.readouterr().out


def test_main_sem_yt_dlp(leg, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(leg.shutil, "which", lambda nome: None)
    assert leg.main(["--inventario", str(tmp_path / "x.jsonl")]) == 1
    assert "pipx install yt-dlp" in capsys.readouterr().err
