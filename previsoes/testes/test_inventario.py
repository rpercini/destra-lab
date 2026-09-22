"""Testes do 01_inventario.py — tudo offline, contra fixtures JSON."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import requests

from conftest import fixture_json


# --------------------------------------------------------------------------
# Parser de duração ISO 8601
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    "texto, esperado",
    [
        ("PT10S", 10),
        ("PT5M", 300),
        ("PT2H", 7200),
        ("PT1H2M10S", 3730),
        ("PT45M3S", 2703),
        ("PT3H15M", 11700),
        ("PT0S", 0),
        ("P0D", 0),                 # live em andamento
        ("P1D", 86400),
        ("P1DT2H3M4S", 93784),
        ("P1W", 604800),
        ("PT1M30.5S", 90),          # fração de segundo -> arredonda
        ("PT59M59S", 3599),
        ("  PT2H  ", 7200),         # espaços em volta
    ],
)
def test_parse_duracao(inv, texto, esperado):
    assert inv.parse_duracao_iso8601(texto) == esperado


@pytest.mark.parametrize("texto", ["", "PT", "P", "abc", "1H2M", "PT1X", None, "PTM"])
def test_parse_duracao_invalida(inv, texto):
    with pytest.raises(ValueError):
        inv.parse_duracao_iso8601(texto)


# --------------------------------------------------------------------------
# Conversão item -> Video
# --------------------------------------------------------------------------

def itens_videos() -> dict[str, dict]:
    return {item["id"]: item for item in fixture_json("videos.json")["items"]}


def test_detecta_video_comum(inv):
    v = inv.monta_video(itens_videos()["vidTeste001"])
    assert v.tipo == "video"
    assert v.duracao_s == 3730
    assert v.video_id == "vidTeste001"
    assert v.url == "https://www.youtube.com/watch?v=vidTeste001"
    assert v.publicado_em == "2024-05-02T18:00:00Z"
    assert v.visualizacoes == 48210
    assert v.tem_legenda_api is False
    assert v.legendas_disponiveis == []


def test_detecta_live_encerrada(inv):
    v = inv.monta_video(itens_videos()["vidTeste002"])
    assert v.tipo == "live"          # liveStreamingDetails sobrevive ao fim da live
    assert v.duracao_s == 11700


def test_detecta_live_em_andamento_sem_duracao(inv):
    v = inv.monta_video(itens_videos()["vidTeste005"])
    assert v.tipo == "live"
    assert v.duracao_s == 0          # "P0D"


def test_caption_string_true_vira_bool(inv):
    v = inv.monta_video(itens_videos()["vidTeste003"])
    assert v.tem_legenda_api is True
    assert isinstance(v.tem_legenda_api, bool)


def test_caption_ausente_vira_none(inv):
    item = dict(itens_videos()["vidTeste001"])
    item["contentDetails"] = {"duration": "PT1M"}
    assert inv.monta_video(item).tem_legenda_api is None


def test_statistics_vazio_nao_quebra(inv):
    v = inv.monta_video(itens_videos()["vidTeste004"])
    assert v.visualizacoes is None
    assert v.duracao_s == 10


def test_duracao_invalida_vira_zero(inv):
    item = dict(itens_videos()["vidTeste001"])
    item["contentDetails"] = {"duration": "xyz", "caption": "false"}
    assert inv.monta_video(item).duracao_s == 0


# --------------------------------------------------------------------------
# Sessão HTTP falsa
# --------------------------------------------------------------------------

class RespostaFalsa:
    def __init__(self, status: int, corpo: dict | None = None, texto: str = ""):
        self.status_code = status
        self._corpo = corpo
        self.text = texto or json.dumps(corpo or {})

    def json(self):
        if self._corpo is None:
            raise ValueError("sem json")
        return self._corpo


class SessaoFalsa:
    """Responde channels/playlistItems/videos a partir das fixtures."""

    def __init__(self, respostas_forcadas: list | None = None):
        self.chamadas: list[tuple[str, dict]] = []
        self.forcadas = list(respostas_forcadas or [])

    def get(self, url, params=None, timeout=None):
        params = params or {}
        self.chamadas.append((url, params))
        if self.forcadas:
            item = self.forcadas.pop(0)
            if isinstance(item, Exception):
                raise item
            return item

        if url.endswith("/channels"):
            return RespostaFalsa(200, fixture_json("channels.json"))
        if url.endswith("/playlistItems"):
            nome = (
                "playlist_pagina2.json"
                if params.get("pageToken") == "TOKEN_PAGINA_2"
                else "playlist_pagina1.json"
            )
            return RespostaFalsa(200, fixture_json(nome))
        if url.endswith("/videos"):
            pedidos = params["id"].split(",")
            todos = fixture_json("videos.json")["items"]
            itens = [i for i in todos if i["id"] in pedidos]
            return RespostaFalsa(200, {"kind": "youtube#videoListResponse", "items": itens})
        raise AssertionError(f"URL inesperada: {url}")


def cliente(inv, sessao, **kwargs):
    return inv.ClienteYouTube("CHAVE_FALSA", sessao=sessao, dormir=lambda s: None, **kwargs)


# --------------------------------------------------------------------------
# Coleta
# --------------------------------------------------------------------------

def test_playlist_de_uploads(inv):
    c = cliente(inv, SessaoFalsa())
    playlist, titulo = inv.playlist_de_uploads(c, "UCtest00000000000000000A")
    assert playlist == "UUtest00000000000000000A"
    assert titulo == "Canal de Teste"


def test_canal_inexistente(inv):
    c = cliente(inv, SessaoFalsa([RespostaFalsa(200, {"items": []})]))
    with pytest.raises(inv.ErroInventario, match="não encontrado"):
        inv.playlist_de_uploads(c, "UCtest00000000000000000A")


def test_paginacao_e_deduplicacao(inv):
    sessao = SessaoFalsa()
    c = cliente(inv, sessao)
    ids = inv.ids_da_playlist(c, "UUtest00000000000000000A")
    # vidTeste002 aparece nas duas páginas e só pode entrar uma vez
    assert ids == [
        "vidTeste001", "vidTeste002", "vidTeste003", "vidTeste004", "vidTeste005",
    ]
    pedidos = [p for u, p in sessao.chamadas if u.endswith("/playlistItems")]
    assert len(pedidos) == 2
    assert pedidos[0].get("pageToken") is None      # None é removido dos params
    assert pedidos[1]["pageToken"] == "TOKEN_PAGINA_2"
    assert pedidos[0]["maxResults"] == 50


def test_limite_corta_e_evita_paginas(inv):
    sessao = SessaoFalsa()
    c = cliente(inv, sessao)
    ids = inv.ids_da_playlist(c, "UUtest00000000000000000A", limite=2)
    assert ids == ["vidTeste001", "vidTeste002"]
    assert len([p for u, p in sessao.chamadas if u.endswith("/playlistItems")]) == 1


def test_lotes_de_50(inv):
    assert list(inv.lotes(list(range(120)), 50))[2] == list(range(100, 120))


def test_busca_metadados_um_lote(inv):
    sessao = SessaoFalsa()
    c = cliente(inv, sessao)
    ids = ["vidTeste001", "vidTeste002", "vidTeste003"]
    videos = inv.busca_metadados(c, ids)
    assert [v.video_id for v in videos] == ids
    chamada = [p for u, p in sessao.chamadas if u.endswith("/videos")][0]
    assert chamada["part"] == "snippet,contentDetails,statistics,liveStreamingDetails"
    assert chamada["id"] == ",".join(ids)


def test_video_indisponivel_e_ignorado(inv):
    c = cliente(inv, SessaoFalsa())
    videos = inv.busca_metadados(c, ["vidTeste001", "naoExisteXX"])
    assert [v.video_id for v in videos] == ["vidTeste001"]


# --------------------------------------------------------------------------
# Erros
# --------------------------------------------------------------------------

def test_quota_excedida(inv):
    sessao = SessaoFalsa([RespostaFalsa(403, fixture_json("erro_quota.json"))])
    c = cliente(inv, sessao)
    with pytest.raises(inv.ErroQuota) as exc:
        c.get("videos", id="x")
    assert "cota" in str(exc.value).lower()
    assert "quotaExceeded" in str(exc.value)


def test_chave_invalida(inv):
    sessao = SessaoFalsa([RespostaFalsa(400, fixture_json("erro_chave.json"))])
    c = cliente(inv, sessao)
    with pytest.raises(inv.ErroInventario, match="API key"):
        c.get("channels", id="x")


def test_retry_em_5xx(inv):
    esperas: list[float] = []
    sessao = SessaoFalsa([
        RespostaFalsa(503, None, "indisponível"),
        RespostaFalsa(500, None, "erro interno"),
        RespostaFalsa(200, {"items": ["ok"]}),
    ])
    c = inv.ClienteYouTube("CHAVE", sessao=sessao, dormir=esperas.append)
    assert c.get("videos", id="x") == {"items": ["ok"]}
    assert esperas == [2, 4]            # backoff exponencial
    assert c.chamadas == 1              # 5xx não conta quota


def test_retry_em_timeout(inv):
    sessao = SessaoFalsa([
        requests.Timeout("estourou"),
        RespostaFalsa(200, {"items": []}),
    ])
    c = inv.ClienteYouTube("CHAVE", sessao=sessao, dormir=lambda s: None)
    assert c.get("videos", id="x") == {"items": []}


def test_desiste_depois_das_tentativas(inv):
    sessao = SessaoFalsa([RespostaFalsa(500) for _ in range(3)])
    c = inv.ClienteYouTube("CHAVE", sessao=sessao, tentativas=3, dormir=lambda s: None)
    with pytest.raises(inv.ErroInventario, match="3 tentativas"):
        c.get("videos", id="x")


def test_chave_api_ausente(inv):
    with pytest.raises(inv.ErroInventario, match="YOUTUBE_API_KEY"):
        inv.chave_api({})
    with pytest.raises(inv.ErroInventario):
        inv.chave_api({"YOUTUBE_API_KEY": "   "})
    assert inv.chave_api({"YOUTUBE_API_KEY": " AIza123 "}) == "AIza123"


@pytest.mark.parametrize(
    "entrada",
    [
        "UCtest00000000000000000A",
        "https://www.youtube.com/channel/UCtest00000000000000000A",
        "youtube.com/channel/UCtest00000000000000000A/videos",
    ],
)
def test_normaliza_canal(inv, entrada):
    assert inv.normaliza_canal(entrada) == "UCtest00000000000000000A"


@pytest.mark.parametrize("entrada", ["@canal", "", "UC123"])
def test_normaliza_canal_invalido(inv, entrada):
    with pytest.raises(inv.ErroInventario):
        inv.normaliza_canal(entrada)


# --------------------------------------------------------------------------
# Saída
# --------------------------------------------------------------------------

def test_grava_jsonl_e_relê(inv, tmp_path: Path):
    from esquema import Video

    c = cliente(inv, SessaoFalsa())
    ids = inv.ids_da_playlist(c, "UU...")
    videos = inv.busca_metadados(c, ids)
    destino = tmp_path / "sub" / "inventario.jsonl"
    assert inv.grava_jsonl(videos, destino) == 5

    linhas = destino.read_text(encoding="utf-8").strip().split("\n")
    assert len(linhas) == 5
    relidos = [Video.model_validate_json(l) for l in linhas]
    assert [v.video_id for v in relidos] == [v.video_id for v in videos]
    assert json.loads(linhas[0])["tipo"] in {"video", "live"}
    assert not list(tmp_path.glob("**/*.tmp"))   # temporário foi renomeado


def test_resumo_tem_os_numeros(inv, tmp_path: Path):
    c = cliente(inv, SessaoFalsa())
    videos = inv.busca_metadados(c, inv.ids_da_playlist(c, "UU..."))
    videos.sort(key=lambda v: v.publicado_em)
    texto = inv.monta_resumo(videos, "Canal de Teste", tmp_path / "inv.jsonl", quota=4)

    assert "Total de vídeos ....... 5" in texto
    assert "2021-01-04 → 2024-05-02" in texto
    # 3 vídeos comuns (3730 + 2703 + 10 s) e 2 lives (11700 + 0 s)
    assert "1,8 h" in texto      # vídeos comuns (6443 s)
    assert "3,2 h" in texto      # lives (11700 s)
    assert "Com legenda (API) ..... 1 de 5" in texto
    assert "sinal fraco" in texto
    assert "10.000" in texto
    assert "Sem duração" in texto   # a live sem duração publicada


def test_main_sem_chave(inv, monkeypatch, capsys):
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    assert inv.main(["--canal", "UCtest00000000000000000A"]) == 1
    assert "YOUTUBE_API_KEY" in capsys.readouterr().err


def test_main_fluxo_completo(inv, monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("YOUTUBE_API_KEY", "CHAVE_FALSA")
    monkeypatch.setattr(inv.requests, "Session", lambda: SessaoFalsa())
    saida = tmp_path / "inventario.jsonl"
    codigo = inv.main([
        "--canal", "https://www.youtube.com/channel/UCtest00000000000000000A",
        "--saida", str(saida),
    ])
    assert codigo == 0
    assert len(saida.read_text(encoding="utf-8").strip().split("\n")) == 5
    saido = capsys.readouterr().out
    assert "INVENTÁRIO" in saido and "Total de vídeos ....... 5" in saido
