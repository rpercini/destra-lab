# Banco de previsões

Pipeline que varre o acervo de um canal de YouTube e cataloga **todas** as
previsões feitas pelo apresentador — as que se confirmaram, as que passaram
perto e as que não aconteceram — com timestamp exato para gerar os cortes.

Dimensionado para ~875 vídeos / ~563 horas de gravação.

## A ideia central

O acervo inteiro é analisado **em texto**, nunca em vídeo. As legendas dos 875
vídeos somam ~200 MB; os vídeos somariam 1 a 2 TB. Só depois que uma previsão é
identificada é que se baixa mídia — e mesmo aí, apenas o intervalo daquele
trecho, não o arquivo inteiro.

O custo segue a mesma lógica de afunilamento: o modelo barato lê tudo, o modelo
caro lê só o que sobrou.

```
875 vídeos → legendas → ~2.250 trechos → Haiku lê todos          ~US$ 7
                                       → Sonnet lê os marcados   ~US$ 14
                                       → Opus monta ~100 dossiês ~US$ 30
                                       → Sonnet julga contra eles ~US$ 25
```

## Instalação

```bash
pip install -r requirements.txt
pipx install yt-dlp          # ou: pip install yt-dlp

export YOUTUBE_API_KEY=...   # console.cloud.google.com → YouTube Data API v3
export ANTHROPIC_API_KEY=... # console.anthropic.com
```

As duas chaves são cobranças separadas e independentes. A YouTube Data API é
gratuita dentro da cota diária de 10.000 unidades — este pipeline usa ~40.

## As etapas

### 1. Inventário — grátis, minutos

```bash
python 01_inventario.py --canal UCGXu9Ny9A0Tm_sc1iI0q7SQ
```

Lista todos os vídeos com data, duração e tipo (vídeo ou live). Não baixa nada.
O resumo impresso ao final é o que transforma a estimativa de custo em conta
fechada — rode isto antes de qualquer outra coisa.

### 2. Legendas — grátis, algumas horas

```bash
python 02_legendas.py --jobs 2 --sleep 2
```

Baixa as legendas em formato `json3`, que traz timing palavra por palavra. É
retomável: se interromper, rode de novo e ele continua de onde parou. **Não
aumente `--jobs` sem necessidade** — o YouTube bloqueia por excesso de
requisições, e aí a pausa é de horas.

Os vídeos sem legenda disponível vão para `dados/sem_legenda.txt`; esses
precisam de Whisper (ver *Plano B* abaixo).

### 3. Chunks — grátis, minutos

```bash
python 03_chunks.py --minutos 15 --overlap 2
```

Quebra as transcrições em janelas de 15 minutos com 2 de sobreposição. A
sobreposição evita que uma previsão seja cortada ao meio na fronteira; as
duplicatas que ela gera são removidas na etapa 5.

Imprime a estimativa de custo da etapa seguinte.

### 4. Triagem — ~US$ 7

```bash
python 04_triagem.py
```

Haiku 4.5 lê todos os chunks e marca os que contêm afirmações sobre o futuro.
É a única etapa que lê as 563 horas inteiras.

A triagem é deliberadamente generosa: na dúvida, marca. Um falso positivo custa
frações de centavo na etapa seguinte; um falso negativo é uma previsão perdida
para sempre.

### 5. Extração — ~US$ 14

```bash
python 05_extracao.py
```

Sonnet 5 transforma os trechos marcados em previsões estruturadas: afirmação
canônica, citação literal, prazo convertido em data, notas de ousadia e
especificidade, e o slug de tema que agrupa os dossiês depois.

Gera dois arquivos: `previsoes.jsonl` (verificáveis) e `previsoes_vagas.jsonl`
(retórica que nenhum fato poderia contradizer). As vagas ficam no registro, mas
não vão a julgamento.

### 6 a 8 — a construir

Dossiês por tema (Opus 5 + busca web), julgamento contra os dossiês, e geração
dos cortes com ffmpeg. Desenhados, mas ainda não escritos: fazem mais sentido
depois de ver os dados reais da etapa 5 — o número de temas distintos e o
formato das previsões é que definem como o dossiê precisa ser montado.

## Rode o piloto antes do acervo inteiro

Todos os scripts aceitam `--limite N`:

```bash
python 01_inventario.py --canal UC... --limite 20
python 02_legendas.py
python 03_chunks.py
python 04_triagem.py
python 05_extracao.py
```

Custa menos de US$ 3 e responde a pergunta que decide o projeto: **quantas
previsões verificáveis existem por hora de gravação?** Pode ser 1, pode ser 8 —
e a diferença define se vale a revisão humana das 563 horas.

Com o resultado do piloto em mãos, calibre os prompts em `04_triagem.py` e
`05_extracao.py` antes de disparar o acervo completo.

## Vereditos

Definidos em `esquema.py`. O que distingue este catálogo de uma seleção de
acertos:

| Veredito | Significado |
|---|---|
| `concretizou` | aconteceu como descrito, no prazo |
| `concretizou_parcial` | o núcleo aconteceu, os detalhes não |
| `passou_perto` | quase — ver `eixo_erro` |
| `nao_concretizou` | o prazo venceu sem o evento, ou veio o oposto |
| `em_aberto` | o prazo ainda não venceu: pauta futura |
| `indeterminado` | sem fonte datada suficiente para julgar |

O `eixo_erro` é o que torna "passou perto" utilizável: `prazo` (errou por quantos
dias), `magnitude` (direção certa, número errado), `ator` (evento certo,
protagonista errado), `mecanismo` (chegou lá por outro caminho), `quase_evento`
(estava em curso e foi revertido).

`indeterminado` é a válvula de segurança. Na etapa de julgamento o modelo é
instruído a usá-lo sempre que o dossiê não trouxer fonte datada posterior ao
vídeo — nunca a preencher a lacuna com conhecimento próprio. Sem essa regra, um
LLM julga qualquer previsão como acerto com uma confiança desconfortável.

## Plano B: vídeos sem legenda

Lives longas às vezes não geram legenda automática. Para os IDs em
`dados/sem_legenda.txt`:

```bash
yt-dlp -f bestaudio --extract-audio --audio-format opus -o "audio/%(id)s.%(ext)s" \
  --batch-file dados/sem_legenda.txt
```

E então `faster-whisper` com o modelo `large-v3`. Numa GPU alugada (RunPod, Vast)
são ~15 horas e ~US$ 10 para o acervo inteiro — mas provavelmente só uma fração
vai precisar disso.

## Estrutura

```
previsoes/
├── esquema.py         contrato de dados — todo o resto depende dele
├── lote.py            camada de Batch API (50% de desconto, retomável)
├── 01_inventario.py   YouTube Data API v3 → dados/inventario.jsonl
├── 02_legendas.py     yt-dlp → dados/legendas/*.json3
├── 03_chunks.py       json3 → dados/chunks.jsonl
├── 04_triagem.py      Haiku 4.5 → dados/triagem.jsonl
├── 05_extracao.py     Sonnet 5 → dados/previsoes.jsonl
└── testes/            pytest, tudo offline
```

## Custo e retomada

Cada etapa imprime o consumo real ao terminar — tokens e dólares, não estimativa.

Os lotes são gravados em `dados/lotes/<etapa>.json` assim que são criados,
**antes** da espera. Se o processo morrer durante o processamento (esperar uma
hora é normal), `--retomar` recupera o lote já pago em vez de gastar de novo:

```bash
python 04_triagem.py --retomar
```
