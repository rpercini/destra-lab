#!/usr/bin/env python3
"""Gera os PDFs dos rotulos Destra Lab prontos para grafica.

Formato: 45 x 60 mm de faca, raio 3 mm, sangria 3 mm (pagina 51 x 66 mm),
margem de seguranca 3 mm. Preto em 100% K, textos vetoriais com fonte
embutida (Libre Franklin).

Pagina 1 = arte + marcas (faca em magenta, corte em preto)
Pagina 2 = arte final, sem marcas
"""

from pathlib import Path

from reportlab.lib.colors import CMYKColor
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

BASE = Path(__file__).resolve().parent
FONTS = BASE / "fonts"
OUT = BASE

# ---------------------------------------------------------------- formato ---
BLEED = 3 * mm
TRIM_W, TRIM_H = 45 * mm, 60 * mm
PAGE_W, PAGE_H = TRIM_W + 2 * BLEED, TRIM_H + 2 * BLEED
SAFE = 3 * mm
CX = PAGE_W / 2

PRETO = CMYKColor(0, 0, 0, 1)
MAGENTA = CMYKColor(0, 1, 0, 0)  # so nas marcas tecnicas, nunca na arte

# --------------------------------------------------------------- tipografia --
LIGHT, MEDIUM, BOLD = "LF-Light", "LF-Medium", "LF-Bold"
for nome, arquivo in ((LIGHT, "LibreFranklin-300.ttf"),
                      (MEDIUM, "LibreFranklin-500.ttf"),
                      (BOLD, "LibreFranklin-700.ttf")):
    pdfmetrics.registerFont(TTFont(nome, str(FONTS / arquivo)))

ASCENDER = 0.966  # Libre Franklin, fracao do corpo

# ------------------------------------------------------------------ rotulos --
ROTULOS = [
    ("01", "LIVE", ["CÍTRICO", "AROMÁTICO", "LUMINOSO"]),
    ("02", "EXPONENCIAL", ["ESPECIADO", "AMADEIRADO", "PROFUNDO"]),
    ("03", "AMADA", ["FLORAL", "ALMISCARADO", "AVELUDADO"]),
    ("04", "MITO", ["TABACO", "BAUNILHA", "ESPECIADO"]),
]

# Codigo de barras decorativo do topo: (x inicial, largura) de cada barra,
# preservado do layout original.
BARRAS = [
    (64.810, 0.498), (65.558, 0.249), (66.056, 0.249), (66.554, 0.498),
    (67.301, 0.249), (67.800, 0.747), (68.796, 0.249), (69.294, 0.249),
    (69.792, 0.498), (70.540, 0.249), (71.038, 0.249), (71.536, 0.747),
    (72.533, 0.498), (73.280, 0.249), (73.778, 0.249), (74.276, 0.498),
    (75.024, 0.249), (75.522, 0.249), (76.020, 0.747), (77.016, 0.249),
    (77.515, 0.498), (78.262, 0.249), (78.760, 0.249), (79.258, 0.498),
]
BARRAS_Y0, BARRAS_Y1 = 26.474, 29.123  # medidos do topo da pagina

# ------------------------------------------------------------------ helpers --


def y(top_down):
    """Converte Y medido do topo (como no layout) para o eixo do PDF."""
    return PAGE_H - top_down


def largura(texto, fonte, corpo, tracking):
    """Largura optica: o tracking depois do ultimo glifo nao conta."""
    base = pdfmetrics.stringWidth(texto, fonte, corpo)
    return base + tracking * max(len(texto) - 1, 0)


def tracking_para(texto, fonte, corpo, alvo):
    """Tracking que faz o texto medir exatamente `alvo`."""
    base = pdfmetrics.stringWidth(texto, fonte, corpo)
    return (alvo - base) / max(len(texto) - 1, 1)


def corpo_para_caber(texto, fonte, corpo, tracking_em, largura_max):
    """Maior corpo <= `corpo` que cabe em `largura_max` mantendo o tracking.

    A entreletra acompanha o corpo, entao a largura e linear no corpo: assim
    todos os nomes ficam com a mesma entreletra optica, so mudando o tamanho.
    """
    por_ponto = (pdfmetrics.stringWidth(texto, fonte, 1.0)
                 + tracking_em * max(len(texto) - 1, 0))
    return min(corpo, largura_max / por_ponto)


def centrado(c, blocos, base_top_down, cor=PRETO):
    """Centra na pagina uma sequencia de trechos (texto, fonte, corpo, track).

    Varios trechos permitem tirar a entreletra antes de um caractere — o ponto
    de "LAB." fica colado no B, como na logo.
    """
    larguras = [largura(txt, fnt, cp, tr) for txt, fnt, cp, tr in blocos]
    x = CX - sum(larguras) / 2
    t = c.beginText()
    t.setFillColor(cor)
    for (txt, fnt, cp, tr), w in zip(blocos, larguras):
        t.setFont(fnt, cp)
        t.setCharSpace(tr)
        t.setTextOrigin(x, y(base_top_down))
        t.textOut(txt)
        x += w
    c.drawText(t)


def simples(c, texto, fonte, corpo, tracking, base_top_down, cor=PRETO):
    centrado(c, [(texto, fonte, corpo, tracking)], base_top_down, cor)


def linha_base(topo, corpo):
    """Linha de base a partir do topo da caixa do texto."""
    return topo + ASCENDER * corpo


# ------------------------------------------------------------------- layout --
# Bloco da marca. As medidas de referencia abaixo sao as do layout original;
# LOGO_ESCALA amplia o conjunto inteiro (barras + DESTRA + LAB. + filete) a
# partir do topo das barras, para a logo nao descer nem mudar de proporcao.
LOGO_ESCALA = 1.25
LOGO_ANCORA = 26.474                       # topo das barras, ponto fixo
DESTRA_TOPO, DESTRA_CORPO, DESTRA_W = 32.220, 8.5, 37.370
LAB_TOPO, LAB_CORPO, LAB_W = 44.440, 8.5, 26.150
FILETE_Y_REF = 62.0
FILETE_PROP = 0.75                         # do LAB.: o filete e mais curto


def escala_y(valor):
    """Aplica LOGO_ESCALA a um Y da logo, fixando o topo das barras."""
    return LOGO_ANCORA + (valor - LOGO_ANCORA) * LOGO_ESCALA


DESTRA_BASE = linha_base(escala_y(DESTRA_TOPO), DESTRA_CORPO * LOGO_ESCALA)
LAB_BASE = linha_base(escala_y(LAB_TOPO), LAB_CORPO * LOGO_ESCALA)
FILETE_Y = escala_y(FILETE_Y_REF)
FILETE_W = LAB_W * LOGO_ESCALA * FILETE_PROP
# Nome do perfume: fonte fina, caixa alta, entreletra larga
NOME_BASE = 102.0
NOME_CORPO = 13.0
NOME_TRACKING = 0.22                       # em
NOME_LARGURA_MAX = 102.0
# Notas olfativas separadas por bullet
NOTAS_BASE = 123.0
NOTAS_CORPO = 5.2                          # era 4.2: subiu para o corpo do PARFUM
NOTAS_TRACKING = 0.10                      # em
NOTAS_LARGURA_MAX = 106.0
# Bloco inferior: 1 ponto menor que as notas e entrelinha mais curta
RODAPE_CORPO = 4.2                         # 1 ponto menor que as notas
PARFUM_BASE = 150.0
PARFUM_TRACKING = 0.300                    # em, entreletra do layout original
VOLUME_BASE = 158.5
VOLUME_TRACKING = 0.249                    # em, entreletra do layout original


def desenhar_arte(c, nome, notas):
    # codigo de barras decorativo, na mesma escala da logo
    c.setFillColor(PRETO)
    altura = (BARRAS_Y1 - BARRAS_Y0) * LOGO_ESCALA
    for x0, w in BARRAS:
        c.rect(CX + (x0 - CX) * LOGO_ESCALA, y(BARRAS_Y0 + altura),
               w * LOGO_ESCALA, altura, stroke=0, fill=1)

    # DESTRA / L A B.  (proporcoes da logo original, ampliadas)
    destra_corpo = DESTRA_CORPO * LOGO_ESCALA
    simples(c, "DESTRA", BOLD, destra_corpo,
            tracking_para("DESTRA", BOLD, destra_corpo,
                          DESTRA_W * LOGO_ESCALA), DESTRA_BASE)
    lab_corpo = LAB_CORPO * LOGO_ESCALA
    lab_track = (LAB_W * LOGO_ESCALA
                 - pdfmetrics.stringWidth("LAB.", LIGHT, lab_corpo)) / 2
    centrado(c, [("LAB", LIGHT, lab_corpo, lab_track),
                 (".", LIGHT, lab_corpo, 0.0)], LAB_BASE)

    # filete abaixo da logo
    c.setStrokeColor(PRETO)
    c.setLineWidth(0.5)
    c.setLineCap(0)
    c.line(CX - FILETE_W / 2, y(FILETE_Y), CX + FILETE_W / 2, y(FILETE_Y))

    # nome do perfume — entreletra igual em todos, corpo reduzido se preciso
    corpo = corpo_para_caber(nome, LIGHT, NOME_CORPO, NOME_TRACKING,
                             NOME_LARGURA_MAX)
    simples(c, nome, LIGHT, corpo, NOME_TRACKING * corpo, NOME_BASE)

    # notas olfativas separadas por bullet
    texto_notas = " • ".join(notas)
    corpo = corpo_para_caber(texto_notas, LIGHT, NOTAS_CORPO, NOTAS_TRACKING,
                             NOTAS_LARGURA_MAX)
    simples(c, texto_notas, LIGHT, corpo, NOTAS_TRACKING * corpo, NOTAS_BASE)

    # PARFUM
    simples(c, "PARFUM", MEDIUM, RODAPE_CORPO,
            PARFUM_TRACKING * RODAPE_CORPO, PARFUM_BASE)

    # volume
    simples(c, "100 ML · 3.4 FL.OZ", LIGHT, RODAPE_CORPO,
            VOLUME_TRACKING * RODAPE_CORPO, VOLUME_BASE)


def desenhar_marcas(c):
    """Marcas tecnicas da pagina de prova (nunca entram na arte final).

    Magenta = faca, como no layout original. O quadrado interno, que antes era
    pontilhado magenta, virou uma linha preta continua — ambos de canto reto.
    """
    c.setLineWidth(0.4)

    # faca 45 x 60 mm
    c.setStrokeColor(MAGENTA)
    c.rect(BLEED, BLEED, TRIM_W, TRIM_H, stroke=1, fill=0)

    # quadrado preto do corte, 3 mm para dentro da faca
    c.setStrokeColor(PRETO)
    c.rect(BLEED + SAFE, BLEED + SAFE, TRIM_W - 2 * SAFE, TRIM_H - 2 * SAFE,
           stroke=1, fill=0)

    ficha = "FACA 45 x 60 mm · raio 3 · sangria 3 · seg. 3"
    c.setFillColor(MAGENTA)
    simples(c, ficha, LIGHT, 3.8, 0.0, linha_base(2.570, 3.8), cor=MAGENTA)


def gerar(indice, nome, notas):
    caminho = OUT / f"Rotulo_{indice}_{nome}.pdf"
    c = canvas.Canvas(str(caminho), pagesize=(PAGE_W, PAGE_H),
                      # sem Helvetica sobrando no arquivo e tudo em CMYK
                      initialFontName=LIGHT, initialFontSize=13,
                      enforceColorSpace="cmyk")
    c.setTitle(f"Destra Lab — Rotulo {nome}")
    c.setSubject("45 x 60 mm · raio 3 mm · sangria 3 mm · 100% K")
    c.setCreator("Destra Lab")

    for pagina in ("faca", "final"):
        # Caixas do PDF: a grafica le a faca e a sangria direto do arquivo.
        c.setBleedBox((0, 0, PAGE_W, PAGE_H))
        c.setTrimBox((BLEED, BLEED, BLEED + TRIM_W, BLEED + TRIM_H))
        c.setArtBox((BLEED, BLEED, BLEED + TRIM_W, BLEED + TRIM_H))
        desenhar_arte(c, nome, notas)
        if pagina == "faca":
            desenhar_marcas(c)
        c.showPage()

    c.save()
    return caminho


if __name__ == "__main__":
    for indice, nome, notas in ROTULOS:
        print("gerado:", gerar(indice, nome, notas).name)
