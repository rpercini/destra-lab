"""Testes da deduplicação por sobreposição de chunks."""
import importlib.util
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

spec = importlib.util.spec_from_file_location("extracao", RAIZ / "05_extracao.py")
extracao = importlib.util.module_from_spec(spec)
spec.loader.exec_module(extracao)
deduplica = extracao.deduplica


def prev(vid, inicio_ms, afirmacao, espec=3):
    return {
        "video_id": vid, "inicio_ms": inicio_ms, "afirmacao": afirmacao,
        "especificidade": espec, "publicado_em": "2022-03-01",
    }


def test_remove_duplicata_da_sobreposicao():
    # Mesma fala captada nos dois chunks que se sobrepõem.
    p = [
        prev("v1", 600_000, "Fulano sera preso ate o fim de 2023"),
        prev("v1", 602_000, "Fulano sera preso ate o fim de 2023"),
    ]
    mantidas, removidas = deduplica(p)
    assert removidas == 1
    assert len(mantidas) == 1


def test_mantem_a_versao_mais_especifica():
    p = [
        prev("v1", 600_000, "Fulano sera preso ate o fim de 2023", espec=2),
        prev("v1", 601_000, "Fulano sera preso ate o fim de 2023", espec=5),
    ]
    mantidas, _ = deduplica(p)
    assert len(mantidas) == 1
    assert mantidas[0]["especificidade"] == 5


def test_preserva_falas_distintas_no_mesmo_instante():
    p = [
        prev("v1", 600_000, "O dolar passa de seis reais em 2024"),
        prev("v1", 601_000, "O Congresso rejeita a reforma da Previdencia"),
    ]
    mantidas, removidas = deduplica(p)
    assert removidas == 0
    assert len(mantidas) == 2


def test_preserva_repeticao_distante_no_tempo():
    # O apresentador repete a mesma previsao 40 minutos depois: sao duas
    # ocorrencias reais, nao artefato de chunking.
    p = [
        prev("v1", 600_000, "Fulano sera preso ate o fim de 2023"),
        prev("v1", 3_000_000, "Fulano sera preso ate o fim de 2023"),
    ]
    mantidas, removidas = deduplica(p)
    assert removidas == 0
    assert len(mantidas) == 2


def test_nao_mistura_videos():
    p = [
        prev("v1", 600_000, "Fulano sera preso ate o fim de 2023"),
        prev("v2", 600_000, "Fulano sera preso ate o fim de 2023"),
    ]
    mantidas, removidas = deduplica(p)
    assert removidas == 0
    assert len(mantidas) == 2


def test_ordena_por_data_e_tempo():
    p = [
        {**prev("v2", 500, "b"), "publicado_em": "2023-01-01"},
        {**prev("v1", 900, "a"), "publicado_em": "2022-01-01"},
        {**prev("v1", 100, "c"), "publicado_em": "2022-01-01"},
    ]
    mantidas, _ = deduplica(p)
    assert [m["afirmacao"] for m in mantidas] == ["c", "a", "b"]
