"""Camada de Batch API da Anthropic.

Todas as etapas de LLM deste pipeline passam por aqui. A Batch API custa metade
do preço normal e processa até 100.000 requisições por lote — e como nada neste
pipeline é interativo, não há razão para pagar preço cheio em lugar nenhum.

O estado do lote é gravado em disco assim que o lote é criado. Se o processo
morrer durante a espera (e esperar 1h é normal), `--retomar` recupera o lote em
vez de gastar de novo.
"""

from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator, Optional

import anthropic
from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
from anthropic.types.messages.batch_create_params import Request

# Preços por milhão de tokens (Claude API, tabela de referência).
# A Batch API aplica 50% de desconto sobre estes valores.
PRECOS: dict[str, tuple[float, float]] = {
    "claude-haiku-4-5": (1.00, 5.00),
    "claude-sonnet-5": (2.00, 10.00),
    "claude-opus-5": (5.00, 25.00),
}

DESCONTO_BATCH = 0.5

# Um lote aceita até 100.000 requisições, mas fatiar em pedaços menores dá
# progresso visível e limita o retrabalho quando algo dá errado.
TAMANHO_LOTE = 2000


def custo(modelo: str, tokens_entrada: int, tokens_saida: int, batch: bool = True) -> float:
    """Custo em dólares de um uso já consumado."""
    if modelo not in PRECOS:
        return 0.0
    preco_in, preco_out = PRECOS[modelo]
    fator = DESCONTO_BATCH if batch else 1.0
    return (tokens_entrada / 1e6 * preco_in + tokens_saida / 1e6 * preco_out) * fator


@dataclass
class Uso:
    """Acumulador de consumo, para fechar a conta ao final de cada etapa."""

    modelo: str
    entrada: int = 0
    saida: int = 0
    cache_leitura: int = 0
    requisicoes: int = 0
    erros: int = 0

    def soma(self, usage: Any) -> None:
        self.entrada += getattr(usage, "input_tokens", 0) or 0
        self.saida += getattr(usage, "output_tokens", 0) or 0
        self.cache_leitura += getattr(usage, "cache_read_input_tokens", 0) or 0
        self.requisicoes += 1

    @property
    def dolares(self) -> float:
        # Leituras de cache custam 10% do preço de entrada.
        base = custo(self.modelo, self.entrada, self.saida)
        preco_in = PRECOS.get(self.modelo, (0.0, 0.0))[0]
        cache = self.cache_leitura / 1e6 * preco_in * 0.1 * DESCONTO_BATCH
        return base + cache

    def relatorio(self) -> str:
        linhas = [
            f"  modelo            {self.modelo}",
            f"  requisições       {self.requisicoes:,}".replace(",", "."),
            f"  tokens entrada    {self.entrada:,}".replace(",", "."),
            f"  tokens saída      {self.saida:,}".replace(",", "."),
        ]
        if self.cache_leitura:
            linhas.append(
                f"  leitura de cache  {self.cache_leitura:,}".replace(",", ".")
            )
        if self.erros:
            linhas.append(f"  erros             {self.erros}")
        linhas.append(f"  custo             US$ {self.dolares:.2f}")
        return "\n".join(linhas)


def cliente() -> anthropic.Anthropic:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit(
            "ANTHROPIC_API_KEY não está definida.\n"
            "Crie uma chave em console.anthropic.com e exporte:\n"
            "  export ANTHROPIC_API_KEY=sk-ant-..."
        )
    return anthropic.Anthropic()


def requisicao(
    custom_id: str,
    modelo: str,
    prompt: str,
    schema: dict,
    max_tokens: int = 4096,
    sistema: Optional[list[dict]] = None,
    pensamento: bool = False,
    esforco: Optional[str] = None,
) -> Request:
    """Monta uma requisição de saída estruturada para o lote.

    `schema` entra em output_config.format, o que garante que a resposta traz um
    bloco de texto com JSON válido contra o schema — sem precisar de parsing
    tolerante nem de retry por JSON quebrado.
    """
    output_config: dict[str, Any] = {"format": {"type": "json_schema", "schema": schema}}
    if esforco:
        output_config["effort"] = esforco

    params: dict[str, Any] = {
        "model": modelo,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
        "output_config": output_config,
    }
    if sistema:
        params["system"] = sistema
    if pensamento:
        # Pensamento adaptativo: o modelo decide sozinho quando e quanto pensar.
        params["thinking"] = {"type": "adaptive"}

    return Request(
        custom_id=custom_id,
        params=MessageCreateParamsNonStreaming(**params),
    )


def _estado_path(etapa: str) -> Path:
    p = Path("dados/lotes")
    p.mkdir(parents=True, exist_ok=True)
    return p / f"{etapa}.json"


def salva_estado(etapa: str, ids: list[str]) -> None:
    _estado_path(etapa).write_text(json.dumps({"lotes": ids}, indent=2))


def carrega_estado(etapa: str) -> list[str]:
    p = _estado_path(etapa)
    if not p.exists():
        return []
    return json.loads(p.read_text()).get("lotes", [])


def envia(
    client: anthropic.Anthropic, etapa: str, requisicoes: list[Request]
) -> list[str]:
    """Cria os lotes e grava os IDs em disco ANTES de esperar por qualquer coisa."""
    ids: list[str] = []
    total = (len(requisicoes) + TAMANHO_LOTE - 1) // TAMANHO_LOTE

    for i in range(0, len(requisicoes), TAMANHO_LOTE):
        fatia = requisicoes[i : i + TAMANHO_LOTE]
        lote = client.messages.batches.create(requests=fatia)
        ids.append(lote.id)
        salva_estado(etapa, ids)  # grava a cada lote: um crash não perde o gasto
        print(
            f"  lote {len(ids)}/{total} enviado: {lote.id} "
            f"({len(fatia)} requisições)"
        )

    return ids


def aguarda(client: anthropic.Anthropic, ids: list[str], intervalo: int = 60) -> None:
    """Espera todos os lotes terminarem, mostrando progresso."""
    pendentes = set(ids)
    inicio = time.time()

    while pendentes:
        concluidos = set()
        em_processamento = 0

        for batch_id in sorted(pendentes):
            lote = client.messages.batches.retrieve(batch_id)
            if lote.processing_status == "ended":
                concluidos.add(batch_id)
            else:
                em_processamento += lote.request_counts.processing

        pendentes -= concluidos
        if not pendentes:
            break

        decorrido = int(time.time() - inicio)
        print(
            f"  [{decorrido // 60:02d}:{decorrido % 60:02d}] "
            f"{len(pendentes)} lote(s) em andamento, "
            f"{em_processamento} requisições processando...",
            flush=True,
        )
        time.sleep(intervalo)

    print(f"  todos os {len(ids)} lote(s) concluídos.")


def resultados(
    client: anthropic.Anthropic, ids: list[str], uso: Uso
) -> Iterator[tuple[str, dict]]:
    """Itera os resultados já decodificados, acumulando consumo.

    Os resultados voltam fora de ordem — por isso tudo é chaveado por custom_id,
    nunca por posição.
    """
    for batch_id in ids:
        for resultado in client.messages.batches.results(batch_id):
            tipo = resultado.result.type

            if tipo == "succeeded":
                msg = resultado.result.message
                uso.soma(msg.usage)
                texto = next(
                    (b.text for b in msg.content if b.type == "text"), None
                )
                if texto is None:
                    uso.erros += 1
                    continue
                try:
                    yield resultado.custom_id, json.loads(texto)
                except json.JSONDecodeError:
                    uso.erros += 1

            elif tipo == "errored":
                uso.erros += 1
                erro = resultado.result.error
                print(
                    f"  erro em {resultado.custom_id}: {getattr(erro, 'type', erro)}",
                    file=sys.stderr,
                )
            else:
                # canceled / expired — reenviar resolve
                uso.erros += 1


def executa(
    etapa: str,
    requisicoes: list[Request],
    modelo: str,
    retomar: bool = False,
    intervalo: int = 60,
) -> tuple[Iterator[tuple[str, dict]], Uso]:
    """Envia (ou retoma), espera e devolve os resultados com o consumo."""
    client = cliente()
    uso = Uso(modelo=modelo)

    if retomar:
        ids = carrega_estado(etapa)
        if not ids:
            sys.exit(f"Nada a retomar: dados/lotes/{etapa}.json não existe.")
        print(f"Retomando {len(ids)} lote(s) de '{etapa}'.")
    else:
        print(
            f"Enviando {len(requisicoes):,} requisições para {modelo}.".replace(",", ".")
        )
        ids = envia(client, etapa, requisicoes)

    aguarda(client, ids, intervalo)
    return resultados(client, ids, uso), uso


def grava_jsonl(caminho: str | Path, itens: Iterable[dict]) -> int:
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with caminho.open("w", encoding="utf-8") as f:
        for item in itens:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
            n += 1
    return n


def le_jsonl(caminho: str | Path) -> Iterator[dict]:
    caminho = Path(caminho)
    if not caminho.exists():
        sys.exit(f"Arquivo não encontrado: {caminho}")
    with caminho.open(encoding="utf-8") as f:
        for linha in f:
            linha = linha.strip()
            if linha:
                yield json.loads(linha)
