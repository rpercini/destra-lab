# Destra Lab. · Sistema de embalagens e rótulos

Consolidação do handoff de 2026-09-04 (texto + artes `ref/`). Cada item está marcado como:

- **[C] confirmado** — informação dada como certa no handoff.
- **[D] decisão de design já tomada** — visível nas artes e não contradita pelo handoff.
- **[R] recomendação** — proposta ainda não aprovada.
- **[P] pendente** — dado que falta; nunca preencher com placeholder como se fosse final.

Fonte de verdade dos dados por SKU: `skus.json`. Artes de referência: `ref/` (Luva v4 DRAFT e Rótulo v3 DRAFT, ambos do EXPONENCIAL, 27/08/2026).

---

## 1. Embalagem física

- **[C]** Caixa fechada: **155 × 110 × 40 mm**. Substitui qualquer medida anterior.
- **[C]** O desenvolvimento **296 × 125 mm** (sangria 3 mm; aba 10 · lat. A 35 · frente 108 · lat. B 35 · verso 108) da luva v4 refere-se à caixa antiga e **não é definitivo**.
- **[D]** Mantém-se a ordem dos painéis (aba · lateral A · frente · lateral B · verso) e o sistema visual de cada um.
- **[P]** Faca definitiva da luva: depende da faca da gráfica, da folga de encaixe e da validação física.

### Proposta de desenvolvimento para 155 × 110 × 40 **[R]**

A luva v4 tem frente em retrato (108 largo × 125 alto). A leitura mais direta é a luva envolver a seção 110 × 40 com altura 155:

| painel | v4 (caixa antiga) | proposta (caixa 155×110×40) |
|---|---|---|
| aba (cola) | 10 | 10 |
| lateral A (lockup) | 35 | 40 |
| frente | 108 | 110 |
| lateral B (legais/EAN) | 35 | 40 |
| verso | 108 | 110 |
| **largura trim** | 296 | **310** (+ folga da gráfica) |
| **altura trim** | 125 | **155** (+ folga da gráfica) |
| página com sangria 3 mm | 302 × 131 | 316 × 161 |

Notas: (a) a v4 não informa a folga usada; a nova folga é **[P]** (gráfica). (b) A alternativa de envolver a seção 155 × 40 daria frente paisagem 155 × 110, incompatível com a composição vertical já decidida; só considerar se o frasco/caixa exigir. (c) Laterais passam de 35 para 40 mm: o lockup horizontal (lateral A) e o EAN (lateral B) ganham 5 mm; a altura +30 mm folga o verso (curva olfativa), hoje o painel mais denso.

## 2. Luva · organização visual **[D]** (medido na v4, todas em mm a partir do canto da página)

| painel | conteúdo | orientação | medições na v4 |
|---|---|---|---|
| Aba | cola | — | 10 mm |
| Lateral A | ornamento + lockup horizontal `DESTRA LAB.` + `FORMULA Nº 02` | 90° horário, leitura de cima para baixo | lockup 13 pt Bold; fórmula 5,5 pt Light espaçado; ornamento vertical (unidade 0,24 mm) à esquerda do lockup; centralizado na altura |
| Frente | ornamento · lockup vertical · nome · `FORMULA Nº 02` · `PARFUM · 100 ML · 3.4 FL.OZ` · barra | normal | lockup 21 pt Bold; nome 32,75 pt SemiBold, largura **85,5 mm**; fórmula e volume 6,5 pt Light espaçados; **barra 60 × 2 mm** a 110 mm do topo, centralizada |
| Lateral B | EAN no topo (rotacionado, ~22 × 28 mm ≈ 80 % de ampliação) · `INGREDIENTES / INGREDIENTS` · INCI · fabricante/CNPJ/endereço · SAC · ANVISA · uso/conservação · caixa `LOTE / VAL.` (4,6 × 34 mm) | 90° anti-horário, leitura de baixo para cima | 4,4 pt Light; títulos 4,6 pt Medium espaçados |
| Verso | cabeçalho `FORMULA Nº 02` (esq.) / `DESTRA LAB.` (dir.) 5,5 pt · fio 92 mm · `EVOLUÇÃO OLFATIVA` 6,5 pt Medium · gráfico · fio · descritivo 7 pt Medium espaçado · frase 5 pt Light · modo de uso 5 pt Light · fio cinza · `FEITO POR BRASILEIROS` 5 pt Light espaçado | normal | margem interna 8 mm; área útil 92 mm |

Na v4 a frente contém **um só lockup vertical** (ornamento, DESTRA, LAB.). O handoff lista "Lockup vertical" e "Fórmula"; ambos estão na arte.

## 3. Rótulo do frasco

- **[C]** Nova medida: **60 × 45 mm**. Substitui integralmente 65 × 80 mm.
- **[C]** Faca com raio 3 mm · sangria 3 mm · margem de segurança 3 mm.
- **[P]** Orientação (60 largo × 45 alto ou 45 largo × 60 alto) — deve respeitar o layout das imagens e a aplicação no frasco.
- **[D]** Composição v3 (65 × 80, retrato, tudo centralizado): ornamento · DESTRA / LAB. (12,2 pt Bold) · EXPONENCIAL (18,25 pt SemiBold, **47,6 mm**) · `FORMULA Nº 02` (6 pt Light) · descritivo (5 pt Light) · fio 18 × 0,5 mm · `PARFUM` (7 pt Medium) · `100 ML · 3.4 FL.OZ` (6,5 pt Light) · fio cinza · legais 2 linhas (4,2 pt Light).

### Impacto da redução para 60 × 45 **[R]**

Área de segurança cai de 59 × 74 mm para **54 × 39 mm** (se 60 largo) ou **39 × 54 mm** (se 45 largo). A pilha vertical da v3 ocupa ~70 mm; não cabe em nenhuma orientação sem rehierarquizar.

Recomendação: **60 largo × 45 alto**, porque é a única orientação em que um nome de ~44–48 mm cabe dentro da margem de segurança. Nome escalado proporcionalmente à largura do rótulo: 48 × (60 ÷ 65) ≈ **44 mm** (o corpo dos demais SKUs herda, como hoje). Pilha proposta, com o lockup escalado na mesma proporção (≈ 11,3 pt) e estimativa de altura ≈ 33 mm dentro dos 39 mm úteis:

1. ornamento + DESTRA / LAB.
2. EXPONENCIAL
3. FÓRMULA Nº 02
4. PARFUM · 100 ML · 3.4 FL.OZ (uma linha, como na frente da luva)
5. legais em 1–2 linhas

Elementos que provavelmente saem do rótulo (ficam na luva): descritivo e fio central. **Isso altera a v3 e precisa de aprovação.** Quais dados legais são obrigatórios na embalagem primária quando há embalagem secundária é **[P]** (verificação regulatória).

## 4. Tipografia **[C]**

- Libre Franklin · pesos 300, 400, 500, 600, 700 · caixa alta = 0,742 × corpo.
- Uso observado na v4/v3 **[D]**: 700 lockup · 600 nome · 500 títulos, descritivo, PARFUM · 300 textos corridos e etiquetas. O 400 aparece só nas anotações técnicas fora da arte.

## 5. Lockup DESTRA LAB. · razão B **[C]**, verificado na arte ✔

| parâmetro | regra | luva v4 (21,01 pt) | rótulo v3 (12,22 pt) |
|---|---|---|---|
| Wd (largura DESTRA) | — | 32,58 mm | 18,96 mm |
| tracking DESTRA | 0,028 × corpo | ok | ok |
| largura LAB. | 0,70 × Wd | 22,81 ✔ | 13,27 ✔ |
| tracking LAB. | (0,70 Wd − largura natural) ÷ 2, ponto colado ao B | ✔ | ✔ |
| ornamento largura | 0,40 × Wd | 13,03 ✔ | 7,58 ✔ |
| ornamento altura | 0,42 × caixa alta | 2,31 ✔ | 1,34 ✔ |
| ornamento acima de DESTRA | 0,50 × caixa alta | ✔ | ✔ |
| entrelinha | 1,62 × caixa alta | 8,91 ✔ | 5,19 ✔ |
| sequência | 2 1 1 2 1 3 1 1 2 1 1 3 2 1 1 2 1 1 3 1 2 1 1 2, vãos de 1 | unidade 0,217 mm ✔ | unidade 0,126 mm ✔ |

Lockup horizontal (lateral A): `DESTRA LAB.` em uma linha, 13 pt Bold, com o ornamento na vertical ao lado — **[D]**; os parâmetros do horizontal não constam do handoff **[P]**.

## 6. Corpo do nome **[C]**

- Dimensionar pela largura, não pelo corpo. EXPONENCIAL define a base; nomes mais curtos herdam o corpo.
- Alvos de referência: luva 86 mm (v4 mede 85,5) · frasco 48 mm (v3 mede 47,6).
- **[R]** Luva: manter 86 mm (frente 108 → 110 é variação < 2 %). Rótulo: ver §3 (≈ 44 mm).

## 7. Cor **[C]**

100 % preto, uma tinta. Retículas 40 / 70 / 100 %. Sem gradientes. Na v4 as barras usam K100, K70 e K40 ✔.

## 8. Gráfico olfativo **[C]** + construção **[D]** (v4)

- Marcos 0 · 15min · 30min · 1h · 2h · 4h · 8h · 12h+ → posições 0 · 8 · 14 · 21 · 28 · 37 · 46 · 58.
- Na v4: área do gráfico 61 mm de largura (1,052 mm por unidade), 54 mm de altura; linhas de grade K15 0,25 pt; barras 2,6 mm altas com passo 3,4 mm; etiquetas de nota 4,2 pt Light à esquerda (coluna de 30 mm); títulos de fase 4,8 pt Medium espaçados; marcos 4,4 pt Light.

## 9. Dados por SKU

Ver `skus.json`. Numeração: 01 LIVE · **02 EXPONENCIAL** · 03 AMADA · 04 MITO. O nº 02 do EXPONENCIAL vem das artes (`FORMULA Nº 02`), não do texto do handoff.

### EXPONENCIAL — o que as artes fornecem **[D]**
- Descritivo: *Especiado. Amadeirado. Profundo.*
- Frase: *Uma presença que se impõe sem pedir licença.*
- Modo de uso: *Aplicar nos pontos de pulso e pescoço. Manter em local fresco e protegido da luz.*
- Rodapé do verso: *FEITO POR BRASILEIROS* (só na luva; pendente decidir se vale para todos os SKUs **[P]**).
- Curva: topo Especiado quente / Fresco especiado / Lavanda · coração Oud / Patchouli / Almíscar / Metálico · fundo Amadeirado / Couro / Terroso (tempos e retículas em `skus.json`).
- Legais e EAN da arte são **placeholders** **[P]**.

## 10. Inconsistências identificadas

1. **Fonte da curva.** EXPONENCIAL usa descritores de acorde (Especiado quente, Metálico, Amadeirado…); LIVE/AMADA/MITO usam matérias-primas (Cidra, Néroli, Akigalawood…). Isso é a pendência 1 do handoff tornada visível no gráfico: além da fonte, o **nível de nomenclatura** também precisa ser unificado.
2. **Acento em FÓRMULA.** As artes escrevem `FORMULA Nº 02` (sem acento) em todas as ocorrências; o handoff escreve `FÓRMULA`. Decidir uma grafia **[P]**.
3. **Rótulo 60 × 45 vs. composição v3.** Ver §3: não cabe sem rehierarquizar.
4. **Brand book do site** (`brand-book.html`, `logos.html` na raiz do repositório) descreve outra identidade: Montserrat, cobre + preto, "Parfums Exclusifs", Exponencial N°001 e Live N°002. Conflita com o sistema de embalagem (Libre Franklin, K100, Live 01 / Exponencial 02). Não alterado; registrar qual prevalece **[P]**.
5. **MITO** fica mais esparso (8 barras contra 10). Handoff deixa em aberto aceitar a assimetria ou desdobrar categorias; desdobramento só com autorização e marcado como interpretação **[P]**.

## 11. Pendências consolidadas **[P]**

1. Regra única de fonte da curva (inspiração × fórmula real) e nível de nomenclatura das notas — igual para os 4 SKUs.
2. Aprovação final dos descritivos e frases dos 4 SKUs.
3. Validação prática dos tempos das notas (pele / fórmula final).
4. Faca da luva compatibilizada com 155 × 110 × 40 (folga, faca da gráfica).
5. Orientação e rehierarquia do rótulo 60 × 45; corpo do nome no rótulo.
6. Dados legais por SKU: INCI, fabricante, SAC, ANVISA, lote, EAN (um por SKU), demais exigências; quais itens são obrigatórios no rótulo primário.
7. Parâmetros do lockup horizontal (lateral A).
8. Grafia FÓRMULA / FORMULA; uso de "FEITO POR BRASILEIROS" nos demais SKUs; ampliação do EAN na lateral de 40 mm.
9. Qual identidade prevalece entre o brand book do site e o sistema de embalagens.
