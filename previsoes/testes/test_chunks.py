"""Testes da etapa 3 (03_chunks.py).

As fixtures são json3 inline, no formato exato que o yt-dlp grava — inclusive
com as sujeiras das legendas automáticas: evento sem `segs`, segmento só com
"\\n", `tOffsetMs` ausente e duplicação por rolagem.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from conftest import carrega

# "03_chunks" não é um identificador Python válido, então o módulo é carregado
# pelo caminho — o mesmo helper que o conftest usa para as outras etapas.
chunks = carrega("03_chunks.py", "chunks_script")

MIN = 60_000  # um minuto em ms


# --------------------------------------------------------------------------
# Auxiliares
# --------------------------------------------------------------------------

def textos(palavras) -> str:
    return " ".join(p.texto for p in palavras)


def tempos(palavras) -> list[int]:
    return [p.inicio_ms for p in palavras]


# --------------------------------------------------------------------------
# 1. Caso feliz
# --------------------------------------------------------------------------

FELIZ = {
    "events": [
        {
            "tStartMs": 1234,
            "dDurationMs": 500,
            "segs": [
                {"utf8": "palavra", "tOffsetMs": 0},
                {"utf8": " outra", "tOffsetMs": 120},
            ],
        },
        {
            "tStartMs": 2000,
            "dDurationMs": 800,
            "segs": [{"utf8": "mais"}],
        },
    ]
}


def test_caso_feliz_achata_com_tempo_absoluto():
    palavras, duplicadas = chunks.parse_json3(FELIZ)

    assert textos(palavras) == "palavra outra mais"
    # tStartMs + tOffsetMs, com tOffsetMs ausente valendo 0.
    assert tempos(palavras) == [1234, 1354, 2000]
    # fim = tStartMs + dDurationMs.
    assert [p.fim_ms for p in palavras] == [1734, 1734, 2800]
    assert duplicadas == 0


def test_seg_com_duas_palavras_herda_o_tempo_do_seg():
    dados = {"events": [{"tStartMs": 500, "dDurationMs": 400,
                         "segs": [{"utf8": "bom dia", "tOffsetMs": 100}]}]}
    palavras, _ = chunks.parse_json3(dados)
    assert textos(palavras) == "bom dia"
    assert tempos(palavras) == [600, 600]


# --------------------------------------------------------------------------
# 2. Eventos sem `segs`
# --------------------------------------------------------------------------

SEM_SEGS = {
    "events": [
        {"tStartMs": 0, "dDurationMs": 1000},                       # sem segs
        {"tStartMs": 0, "wWinId": 1},                               # evento de janela
        {"tStartMs": 1000, "dDurationMs": 500, "segs": []},         # segs vazio
        {"tStartMs": 2000, "dDurationMs": 500, "segs": None},       # segs nulo
        {"tStartMs": 3000, "dDurationMs": 500, "segs": [{"utf8": "sobrevivi"}]},
    ]
}


def test_eventos_sem_segs_sao_pulados():
    palavras, _ = chunks.parse_json3(SEM_SEGS)
    assert textos(palavras) == "sobrevivi"
    assert tempos(palavras) == [3000]


def test_arquivo_sem_events_nao_explode():
    assert chunks.parse_json3({}) == ([], 0)
    assert chunks.parse_json3({"events": None}) == ([], 0)


# --------------------------------------------------------------------------
# 3. Segmentos vazios / só espaço em branco
# --------------------------------------------------------------------------

VAZIOS = {
    "events": [
        {
            "tStartMs": 0,
            "dDurationMs": 1000,
            "segs": [
                {"utf8": "\n"},
                {"utf8": " ", "tOffsetMs": 10},
                {"utf8": "", "tOffsetMs": 20},
                {"utf8": "olha", "tOffsetMs": 30},
                {"utf8": "\n", "tOffsetMs": 40},
                {"utf8": "  só  ", "tOffsetMs": 50},
                {"utf8": None, "tOffsetMs": 60},
                {"utf8": "isso", "tOffsetMs": 70},
            ],
        }
    ]
}


def test_segmentos_em_branco_sao_descartados():
    palavras, _ = chunks.parse_json3(VAZIOS)
    assert textos(palavras) == "olha só isso"
    assert tempos(palavras) == [30, 50, 70]


def test_sem_dDurationMs_o_fim_vira_o_proprio_inicio():
    dados = {"events": [{"tStartMs": 7000, "segs": [{"utf8": "sozinha"}]}]}
    palavras, _ = chunks.parse_json3(dados)
    assert palavras[0].inicio_ms == 7000
    assert palavras[0].fim_ms == 7000


# --------------------------------------------------------------------------
# 4. Deduplicação da rolagem (o caso mais importante do parser)
# --------------------------------------------------------------------------

ROLAGEM = {
    "events": [
        {"tStartMs": 0, "dDurationMs": 2000,
         "segs": [{"utf8": "o dólar", "tOffsetMs": 0}]},
        # o evento seguinte reimprime "o dólar" e acrescenta duas palavras
        {"tStartMs": 2000, "dDurationMs": 2000,
         "segs": [{"utf8": "o dólar", "tOffsetMs": 0},
                  {"utf8": " vai", "tOffsetMs": 500},
                  {"utf8": " subir", "tOffsetMs": 900}]},
        # e este reimprime "vai subir" e acrescenta mais duas
        {"tStartMs": 4000, "dDurationMs": 2000,
         "segs": [{"utf8": "vai subir", "tOffsetMs": 0},
                  {"utf8": " até", "tOffsetMs": 300},
                  {"utf8": " dezembro", "tOffsetMs": 700}]},
    ]
}


def test_rolagem_parcial_perde_so_o_prefixo_repetido():
    palavras, duplicadas = chunks.parse_json3(ROLAGEM)

    assert textos(palavras) == "o dólar vai subir até dezembro"
    assert duplicadas == 4  # "o dólar" + "vai subir"
    # As palavras novas mantêm o tempo do evento em que apareceram pela
    # primeira vez como texto novo — não o do evento que as reimprimiu.
    assert tempos(palavras) == [0, 0, 2500, 2900, 4300, 4700]


def test_evento_inteiramente_repetido_desaparece():
    dados = {
        "events": [
            {"tStartMs": 0, "dDurationMs": 1500,
             "segs": [{"utf8": "a inflação cede"}]},
            {"tStartMs": 1500, "dDurationMs": 1500,
             "segs": [{"utf8": "a inflação cede"}]},
        ]
    }
    palavras, duplicadas = chunks.parse_json3(dados)
    assert textos(palavras) == "a inflação cede"
    assert duplicadas == 3


def test_rolagem_ignora_caixa_e_pontuacao():
    dados = {
        "events": [
            {"tStartMs": 0, "dDurationMs": 1000, "segs": [{"utf8": "O dólar vai"}]},
            {"tStartMs": 1000, "dDurationMs": 1000,
             "segs": [{"utf8": "o dólar, vai subir"}]},
        ]
    }
    palavras, duplicadas = chunks.parse_json3(dados)
    assert textos(palavras) == "O dólar vai subir"
    assert duplicadas == 3


def test_rolagem_pega_repeticao_de_dois_eventos_atras():
    # roll-up de duas linhas: o evento novo repete o fim de dois eventos.
    dados = {
        "events": [
            {"tStartMs": 0, "dDurationMs": 1000, "segs": [{"utf8": "primeira linha"}]},
            {"tStartMs": 1000, "dDurationMs": 1000, "segs": [{"utf8": "segunda linha"}]},
            {"tStartMs": 2000, "dDurationMs": 1000,
             "segs": [{"utf8": "primeira linha segunda linha terceira"}]},
        ]
    }
    palavras, duplicadas = chunks.parse_json3(dados)
    assert textos(palavras) == "primeira linha segunda linha terceira"
    assert duplicadas == 4


def test_texto_novo_nao_e_cortado_por_engano():
    dados = {
        "events": [
            {"tStartMs": 0, "dDurationMs": 1000, "segs": [{"utf8": "o congresso aprovou"}]},
            {"tStartMs": 1000, "dDurationMs": 1000, "segs": [{"utf8": "a reforma passou"}]},
        ]
    }
    palavras, duplicadas = chunks.parse_json3(dados)
    assert textos(palavras) == "o congresso aprovou a reforma passou"
    assert duplicadas == 0


def test_corta_sobreposicao_prefere_a_repeticao_mais_longa():
    novas = [chunks.Palavra(0, 0, t) for t in ["vai", "cair", "vai", "cair", "mesmo"]]
    cortadas = chunks.corta_sobreposicao(["hoje", "vai", "cair"], novas)
    # A cauda termina em "vai cair"; o corte tira 2 palavras, não só "vai".
    assert [p.texto for p in cortadas] == ["vai", "cair", "mesmo"]


# --------------------------------------------------------------------------
# 5. Timestamps absolutos depois do chunking com sobreposição
# --------------------------------------------------------------------------

def legenda_minuto_a_minuto(n_minutos: int, deslocamento_ms: int = 0) -> dict:
    """Uma palavra por minuto: `m0 m1 m2 ...`, cada evento com 1s de duração."""
    return {
        "events": [
            {
                "tStartMs": deslocamento_ms + m * MIN,
                "dDurationMs": 1000,
                "segs": [{"utf8": f"m{m}", "tOffsetMs": 0}],
            }
            for m in range(n_minutos)
        ]
    }


def test_chunking_com_overlap_tem_timestamps_absolutos_exatos():
    # 41 palavras, uma por minuto, de 0min a 40min.
    palavras, _ = chunks.parse_json3(legenda_minuto_a_minuto(41))
    resultado = chunks.monta_chunks("vid123", palavras, janela_ms=15 * MIN,
                                    overlap_ms=2 * MIN)

    # passo = 15 - 2 = 13 min. Janelas: [0,15), [13,28), [26,41).
    # A quarta janela começaria em 39min e só conteria m39/m40, já entregues
    # pela terceira — logo é descartada.
    assert len(resultado) == 3

    assert [c.inicio_ms for c in resultado] == [0, 13 * MIN, 26 * MIN]
    # fim = tempo da última palavra do chunk + 1s de duração do evento.
    assert [c.fim_ms for c in resultado] == [
        14 * MIN + 1000,
        27 * MIN + 1000,
        40 * MIN + 1000,
    ]

    assert resultado[0].texto.split()[0] == "m0"
    assert resultado[0].texto.split()[-1] == "m14"
    assert resultado[1].texto.split()[0] == "m13"
    assert resultado[1].texto.split()[-1] == "m27"
    assert resultado[2].texto.split()[0] == "m26"
    assert resultado[2].texto.split()[-1] == "m40"

    # A sobreposição é de 2 minutos de fala, nas duas fronteiras.
    assert resultado[0].texto.split()[-2:] == ["m13", "m14"]
    assert resultado[1].texto.split()[:2] == ["m13", "m14"]
    assert resultado[1].texto.split()[-2:] == ["m26", "m27"]
    assert resultado[2].texto.split()[:2] == ["m26", "m27"]

    # O passo entre chunks consecutivos é exatamente janela - overlap.
    assert resultado[1].inicio_ms - resultado[0].inicio_ms == 13 * MIN
    assert resultado[2].inicio_ms - resultado[1].inicio_ms == 13 * MIN

    assert [c.chunk_id for c in resultado] == [
        "vid123#0000", "vid123#0001", "vid123#0002",
    ]
    assert [c.indice for c in resultado] == [0, 1, 2]
    assert [c.n_palavras for c in resultado] == [15, 15, 15]


def test_chunking_ancora_no_inicio_real_da_fala():
    # A legenda só começa em 5min37s: os timestamps do chunk têm que refletir
    # o vídeo, não uma linha do tempo que começa no zero.
    deslocamento = 5 * MIN + 37_000
    palavras, _ = chunks.parse_json3(legenda_minuto_a_minuto(41, deslocamento))
    resultado = chunks.monta_chunks("vid123", palavras, janela_ms=15 * MIN,
                                    overlap_ms=2 * MIN)

    assert [c.inicio_ms for c in resultado] == [
        deslocamento,
        deslocamento + 13 * MIN,
        deslocamento + 26 * MIN,
    ]
    assert resultado[0].fim_ms == deslocamento + 14 * MIN + 1000


def test_nenhuma_palavra_se_perde_entre_os_chunks():
    palavras, _ = chunks.parse_json3(legenda_minuto_a_minuto(41))
    resultado = chunks.monta_chunks("v", palavras, janela_ms=15 * MIN, overlap_ms=2 * MIN)
    cobertas = set()
    for c in resultado:
        cobertas.update(c.texto.split())
    assert cobertas == {f"m{m}" for m in range(41)}


def test_chunk_unico_quando_o_video_e_mais_curto_que_a_janela():
    palavras, _ = chunks.parse_json3(legenda_minuto_a_minuto(10))
    resultado = chunks.monta_chunks("curto", palavras, janela_ms=15 * MIN,
                                    overlap_ms=2 * MIN)
    assert len(resultado) == 1
    assert resultado[0].inicio_ms == 0
    assert resultado[0].fim_ms == 9 * MIN + 1000
    assert resultado[0].n_palavras == 10


def test_parametros_de_janela_customizados():
    palavras, _ = chunks.parse_json3(legenda_minuto_a_minuto(21))
    resultado = chunks.monta_chunks("v", palavras, janela_ms=10 * MIN, overlap_ms=1 * MIN)
    # passo = 9 min: janelas [0,10), [9,19), [18,28).
    assert [c.inicio_ms for c in resultado] == [0, 9 * MIN, 18 * MIN]
    assert resultado[-1].texto.split()[-1] == "m20"


def test_sem_palavras_nao_gera_chunk():
    assert chunks.monta_chunks("v", [], janela_ms=15 * MIN, overlap_ms=2 * MIN) == []


def test_texto_do_chunk_normaliza_espacos():
    dados = {"events": [{"tStartMs": 0, "dDurationMs": 100,
                         "segs": [{"utf8": "  muito   espaço \n aqui  "}]}]}
    palavras, _ = chunks.parse_json3(dados)
    resultado = chunks.monta_chunks("v", palavras, janela_ms=MIN, overlap_ms=0)
    assert resultado[0].texto == "muito espaço aqui"
    assert resultado[0].n_palavras == 3


# --------------------------------------------------------------------------
# Seleção de idioma
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    "arquivos,esperado",
    [
        (["v.pt.json3", "v.pt-BR.json3", "v.pt-orig.json3"], "pt-BR"),
        (["v.pt.json3", "v.pt-orig.json3"], "pt"),
        (["v.pt-orig.json3", "v.en.json3"], "pt-orig"),
        (["v.pt-BR-orig.json3", "v.pt.json3"], "pt"),     # manual pt bate auto pt-BR
        (["v.en.json3", "v.es.json3"], "en"),             # nada em português
    ],
)
def test_ordem_de_preferencia_de_idioma(arquivos, esperado):
    _, lang = chunks.escolhe_legenda([Path(a) for a in arquivos])
    assert lang == esperado


def test_marca_de_legenda_automatica():
    assert chunks.e_automatica("pt-orig")
    assert chunks.e_automatica("a.pt")
    assert not chunks.e_automatica("pt-BR")


def test_decompoe_nome():
    assert chunks.decompoe_nome(Path("dQw4w9WgXcQ.pt-BR.json3")) == ("dQw4w9WgXcQ", "pt-BR")
    assert chunks.decompoe_nome(Path("sem_idioma.json3")) is None
    assert chunks.decompoe_nome(Path("outra.coisa.txt")) is None


# --------------------------------------------------------------------------
# Custo
# --------------------------------------------------------------------------

def test_preco_efetivo_do_batch():
    # Haiku 4.5: US$ 1,00/Mtok de entrada, 50% de desconto na Batch API.
    assert chunks.PRECO_EFETIVO_POR_MILHAO == pytest.approx(0.50)
    # 1M de palavras -> 1,8M tokens -> US$ 0,90.
    tokens = 1_000_000 * chunks.TOKENS_POR_PALAVRA
    assert tokens / 1_000_000 * chunks.PRECO_EFETIVO_POR_MILHAO == pytest.approx(0.90)


# --------------------------------------------------------------------------
# Ponta a ponta
# --------------------------------------------------------------------------

def test_main_grava_jsonl_valido(tmp_path, capsys):
    legendas = tmp_path / "legendas"
    legendas.mkdir()
    (legendas / "aaaaaaaaaaa.pt-BR.json3").write_text(
        json.dumps(legenda_minuto_a_minuto(20)), encoding="utf-8")
    (legendas / "aaaaaaaaaaa.pt-orig.json3").write_text(
        json.dumps(legenda_minuto_a_minuto(3)), encoding="utf-8")
    (legendas / "bbbbbbbbbbb.pt-orig.json3").write_text(
        json.dumps(ROLAGEM), encoding="utf-8")

    inventario = tmp_path / "inventario.jsonl"
    inventario.write_text(
        "\n".join(
            json.dumps(v) for v in [
                {"video_id": "aaaaaaaaaaa", "titulo": "A", "url": "https://x/a",
                 "publicado_em": "2022-01-01T00:00:00Z", "duracao_s": 1200,
                 "tipo": "video", "legendas_disponiveis": ["pt-BR"]},
                {"video_id": "bbbbbbbbbbb", "titulo": "B", "url": "https://x/b",
                 "publicado_em": "2022-02-01T00:00:00Z", "duracao_s": 10,
                 "tipo": "live", "legendas_disponiveis": ["pt-orig"]},
                {"video_id": "ccccccccccc", "titulo": "C (sem legenda)",
                 "url": "https://x/c", "publicado_em": "2022-03-01T00:00:00Z",
                 "duracao_s": 600, "tipo": "video"},
            ]
        ) + "\n",
        encoding="utf-8",
    )

    saida = tmp_path / "chunks.jsonl"
    codigo = chunks.main([
        "--entrada", str(legendas),
        "--saida", str(saida),
        "--inventario", str(inventario),
        "--minutos", "15",
        "--overlap", "2",
    ])
    assert codigo == 0

    linhas = saida.read_text(encoding="utf-8").strip().splitlines()
    lidos = [chunks.Chunk.model_validate_json(linha) for linha in linhas]

    por_video: dict[str, list] = {}
    for c in lidos:
        por_video.setdefault(c.video_id, []).append(c)

    # O vídeo de 20 min vira 2 chunks (janelas [0,15) e [13,28)).
    assert [c.inicio_ms for c in por_video["aaaaaaaaaaa"]] == [0, 13 * MIN]
    # Usou a legenda manual (20 palavras), não a automática de 3.
    assert por_video["aaaaaaaaaaa"][0].n_palavras == 15

    assert len(por_video["bbbbbbbbbbb"]) == 1
    assert por_video["bbbbbbbbbbb"][0].texto == "o dólar vai subir até dezembro"

    saida_texto = capsys.readouterr().out
    assert "CUSTO ESTIMADO DA TRIAGEM" in saida_texto
    assert "claude-haiku-4-5" in saida_texto
    assert "Vídeos sem legenda (pulados) " in saida_texto
    assert "pt-BR (manual)" in saida_texto
    assert "pt-orig (automática)" in saida_texto


def test_main_recusa_overlap_maior_que_a_janela(tmp_path, capsys):
    codigo = chunks.main(["--minutos", "5", "--overlap", "5",
                          "--entrada", str(tmp_path)])
    assert codigo == 2
    assert "overlap" in capsys.readouterr().err


def test_main_sem_legendas_retorna_erro(tmp_path, capsys):
    codigo = chunks.main(["--entrada", str(tmp_path / "nao_existe"),
                          "--saida", str(tmp_path / "out.jsonl")])
    assert codigo == 1
    assert "nenhuma legenda" in capsys.readouterr().err
