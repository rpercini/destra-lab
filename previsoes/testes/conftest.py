"""Carrega os scripts numerados como módulos (o nome começa com dígito, então
`import 01_inventario` não funciona) e expõe os fixtures JSON offline."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

RAIZ = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures"

if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))


def carrega(nome_arquivo: str, nome_modulo: str) -> ModuleType:
    caminho = RAIZ / nome_arquivo
    spec = importlib.util.spec_from_file_location(nome_modulo, caminho)
    assert spec and spec.loader, f"não consegui carregar {caminho}"
    modulo = importlib.util.module_from_spec(spec)
    sys.modules[nome_modulo] = modulo
    spec.loader.exec_module(modulo)
    return modulo


inventario = carrega("01_inventario.py", "inventario_script")
legendas = carrega("02_legendas.py", "legendas_script")


@pytest.fixture
def inv() -> ModuleType:
    return inventario


@pytest.fixture
def leg() -> ModuleType:
    return legendas


def fixture_json(nome: str) -> dict:
    return json.loads((FIXTURES / nome).read_text(encoding="utf-8"))
