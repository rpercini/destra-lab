"""Contrato de dados do pipeline de previsões.

Todas as etapas leem e escrevem os tipos definidos aqui. Os schemas JSON são
declarados explicitamente (e não gerados a partir do Pydantic) porque a API de
saída estruturada exige `additionalProperties: false` e schemas planos, sem
`$ref`/`$defs`. Os modelos Pydantic servem para validar o que volta do modelo.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

# --------------------------------------------------------------------------
# Vocabulários controlados
# --------------------------------------------------------------------------

Veredito = Literal[
    "concretizou",          # aconteceu como descrito, dentro do prazo
    "concretizou_parcial",  # o núcleo aconteceu, detalhes não
    "passou_perto",         # quase — ver eixo_erro para saber em quê
    "nao_concretizou",      # o prazo venceu sem o evento, ou veio o oposto
    "em_aberto",            # o prazo ainda não venceu: pauta futura
    "indeterminado",        # sem fonte datada suficiente para julgar
]

VEREDITOS: tuple[str, ...] = (
    "concretizou", "concretizou_parcial", "passou_perto",
    "nao_concretizou", "em_aberto", "indeterminado",
)

EixoErro = Literal[
    "prazo",        # aconteceu, mas fora da janela prevista
    "magnitude",    # direção certa, número errado
    "ator",         # o evento veio, protagonista diferente
    "mecanismo",    # o resultado veio por outro caminho
    "quase_evento", # chegou a estar em curso e foi revertido
    "nenhum",       # acerto limpo, ou erro sem quase-acerto
]

EIXOS_ERRO: tuple[str, ...] = (
    "prazo", "magnitude", "ator", "mecanismo", "quase_evento", "nenhum",
)

TipoVideo = Literal["video", "live"]


# --------------------------------------------------------------------------
# Etapa 1 — inventário
# --------------------------------------------------------------------------

class Video(BaseModel):
    video_id: str
    titulo: str
    url: str
    publicado_em: str                      # ISO 8601, âncora temporal de tudo
    duracao_s: int
    tipo: TipoVideo
    tem_legenda_api: Optional[bool] = None  # sinal do campo contentDetails.caption
    legendas_disponiveis: list[str] = Field(default_factory=list)  # confirmado via yt-dlp
    visualizacoes: Optional[int] = None


# --------------------------------------------------------------------------
# Etapa 3 — chunks de transcrição
# --------------------------------------------------------------------------

class Chunk(BaseModel):
    chunk_id: str          # "{video_id}#{indice:04d}"
    video_id: str
    indice: int
    inicio_ms: int
    fim_ms: int
    texto: str
    n_palavras: int


# --------------------------------------------------------------------------
# Etapa 4 — triagem (Haiku): o chunk contém afirmação sobre o futuro?
# --------------------------------------------------------------------------

SCHEMA_TRIAGEM: dict = {
    "type": "object",
    "properties": {
        "tem_previsao": {
            "type": "boolean",
            "description": "Verdadeiro se o trecho contém ao menos uma afirmação "
                           "sobre evento futuro que possa ser verificada depois.",
        },
        "confianca": {
            "type": "number",
            "description": "0.0 a 1.0.",
        },
        "quantidade": {
            "type": "integer",
            "description": "Quantas afirmações distintas sobre o futuro aparecem.",
        },
        "resumo": {
            "type": "string",
            "description": "Uma linha descrevendo o que é previsto. String vazia se "
                           "tem_previsao for falso.",
        },
    },
    "required": ["tem_previsao", "confianca", "quantidade", "resumo"],
    "additionalProperties": False,
}


class Triagem(BaseModel):
    tem_previsao: bool
    confianca: float
    quantidade: int
    resumo: str


# --------------------------------------------------------------------------
# Etapa 5 — extração (Sonnet): a previsão canônica
# --------------------------------------------------------------------------

SCHEMA_EXTRACAO: dict = {
    "type": "object",
    "properties": {
        "previsoes": {
            "type": "array",
            "description": "Uma entrada por afirmação distinta sobre o futuro. "
                           "Array vazio se o trecho não contiver nenhuma.",
            "items": {
                "type": "object",
                "properties": {
                    "afirmacao": {
                        "type": "string",
                        "description": "A previsão reescrita como proposição única e "
                                       "verificável, sem depender do contexto.",
                    },
                    "citacao": {
                        "type": "string",
                        "description": "Transcrição literal do que foi dito, sem edição.",
                    },
                    "sujeito": {
                        "type": "string",
                        "description": "Pessoa, instituição ou indicador de que se fala.",
                    },
                    "evento_previsto": {
                        "type": "string",
                        "description": "O que se afirma que vai acontecer.",
                    },
                    "prazo_declarado": {
                        "type": "string",
                        "description": "O prazo tal como foi dito ('até a eleição', "
                                       "'ano que vem'). Vazio se não houve prazo.",
                    },
                    "prazo_limite": {
                        "type": "string",
                        "description": "O prazo convertido para AAAA-MM-DD, resolvido "
                                       "contra a data de publicação do vídeo. String "
                                       "vazia se a fala não permitir inferir uma data.",
                    },
                    "condicional": {
                        "type": "boolean",
                        "description": "Verdadeiro se a previsão depende de uma condição "
                                       "declarada ('se X acontecer, então Y').",
                    },
                    "falseavel": {
                        "type": "boolean",
                        "description": "Falso para retórica vaga que nenhum fato poderia "
                                       "contradizer ('as coisas vão piorar').",
                    },
                    "ousadia": {
                        "type": "integer",
                        "description": "1 a 5. Quanto a previsão contrariava o consenso "
                                       "na data em que foi feita. 1 = todos diziam o "
                                       "mesmo; 5 = ia contra o consenso da época.",
                    },
                    "especificidade": {
                        "type": "integer",
                        "description": "1 a 5. 1 = genérica; 5 = nomeia pessoa, número "
                                       "e data.",
                    },
                    "tema": {
                        "type": "string",
                        "description": "Slug curto do evento tratado, em minúsculas com "
                                       "hífens (ex.: 'eleicao-presidencial-2022'). É a "
                                       "chave de agrupamento para os dossiês, então use "
                                       "o mesmo slug para previsões sobre o mesmo evento.",
                    },
                    "offset_inicio_s": {
                        "type": "integer",
                        "description": "Segundos desde o início do chunk em que a fala "
                                       "começa.",
                    },
                    "offset_fim_s": {
                        "type": "integer",
                        "description": "Segundos desde o início do chunk em que termina.",
                    },
                },
                "required": [
                    "afirmacao", "citacao", "sujeito", "evento_previsto",
                    "prazo_declarado", "prazo_limite", "condicional", "falseavel",
                    "ousadia", "especificidade", "tema",
                    "offset_inicio_s", "offset_fim_s",
                ],
                "additionalProperties": False,
            },
        },
    },
    "required": ["previsoes"],
    "additionalProperties": False,
}


class PrevisaoExtraida(BaseModel):
    afirmacao: str
    citacao: str
    sujeito: str
    evento_previsto: str
    prazo_declarado: str
    prazo_limite: str
    condicional: bool
    falseavel: bool
    ousadia: int
    especificidade: int
    tema: str
    offset_inicio_s: int
    offset_fim_s: int


class Extracao(BaseModel):
    previsoes: list[PrevisaoExtraida]


# --------------------------------------------------------------------------
# Etapa 7 — julgamento contra o dossiê do tema
# --------------------------------------------------------------------------

SCHEMA_JULGAMENTO: dict = {
    "type": "object",
    "properties": {
        "veredito": {
            "type": "string",
            "enum": list(VEREDITOS),
            "description": "Use 'indeterminado' sempre que o dossiê não trouxer fonte "
                           "datada posterior ao vídeo que sustente um julgamento. Nunca "
                           "preencha a lacuna com conhecimento próprio.",
        },
        "eixo_erro": {
            "type": "string",
            "enum": list(EIXOS_ERRO),
            "description": "Em que dimensão a previsão errou. 'nenhum' para acerto "
                           "limpo ou para erro sem quase-acerto.",
        },
        "distancia_valor": {
            "type": "number",
            "description": "O tamanho do erro, quando mensurável: dias de diferença "
                           "para eixo 'prazo', pontos de diferença para 'magnitude'. "
                           "Use 0 quando não se aplica.",
        },
        "distancia_unidade": {
            "type": "string",
            "description": "Unidade de distancia_valor ('dias', 'pontos_percentuais', "
                           "'assentos'...). String vazia quando não se aplica.",
        },
        "justificativa": {
            "type": "string",
            "description": "2 a 3 frases ligando a previsão ao que de fato ocorreu.",
        },
        "evidencias": {
            "type": "array",
            "description": "Itens do dossiê que sustentam o veredito. Deixe vazio "
                           "apenas quando o veredito for 'indeterminado' ou 'em_aberto'.",
            "items": {
                "type": "object",
                "properties": {
                    "fato": {"type": "string"},
                    "data": {"type": "string", "description": "AAAA-MM-DD"},
                    "fonte": {"type": "string", "description": "URL ou veículo"},
                },
                "required": ["fato", "data", "fonte"],
                "additionalProperties": False,
            },
        },
        "confianca": {"type": "number", "description": "0.0 a 1.0."},
    },
    "required": [
        "veredito", "eixo_erro", "distancia_valor", "distancia_unidade",
        "justificativa", "evidencias", "confianca",
    ],
    "additionalProperties": False,
}


class Evidencia(BaseModel):
    fato: str
    data: str
    fonte: str


class Julgamento(BaseModel):
    veredito: Veredito
    eixo_erro: EixoErro
    distancia_valor: float
    distancia_unidade: str
    justificativa: str
    evidencias: list[Evidencia]
    confianca: float


# --------------------------------------------------------------------------
# Registro final — uma linha por previsão no banco
# --------------------------------------------------------------------------

class Previsao(PrevisaoExtraida):
    """Previsão extraída, ancorada no vídeo e (depois da etapa 7) julgada."""

    previsao_id: str
    video_id: str
    video_titulo: str
    video_url: str
    publicado_em: str
    inicio_ms: int          # absoluto no vídeo — é daqui que sai o corte
    fim_ms: int
    julgamento: Optional[Julgamento] = None

    @property
    def url_com_tempo(self) -> str:
        return f"{self.video_url}&t={self.inicio_ms // 1000}s"


def valida_intervalo(nome: str, valor: int, minimo: int, maximo: int) -> int:
    """Prende um inteiro na faixa esperada — o modelo ocasionalmente extrapola."""
    if valor < minimo or valor > maximo:
        return max(minimo, min(maximo, valor))
    return valor
