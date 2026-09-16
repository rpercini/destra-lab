#!/usr/bin/env python3
"""Gera os PDFs dos rotulos Destra Lab prontos para grafica.

Formato: 45 x 60 mm de faca, raio 3 mm, sangria 3 mm (pagina 51 x 66 mm),
margem de seguranca 3 mm. Preto em 100% K, textos vetoriais com fonte
embutida (Libre Franklin).

Pagina 1 = arte + quadrado preto da faca (prova de corte)
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
RADIUS = 3 * mm
SAFE = 3 * mm
CX = PAGE_W / 2

PRETO = CMYKColor(0, 0, 0, 1)

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


def tracking_comum(textos, fonte, corpo, tracking_em, largura_max):
    """Entreletra unica para varios textos: a maior que serve para todos."""
    limites = [(largura_max - pdfmetrics.stringWidth(t, fonte, corpo))
               / max(len(t) - 1, 1) for t in textos]
    return min(tracking_em * corpo, *limites)


def centrado(c, blocos, base_top_down):
    """Centra na pagina uma sequencia de trechos (texto, fonte, corpo, track).

    Varios trechos permitem tirar a entreletra antes de um caractere — o ponto
    de "LAB." fica colado no B, como na logo.
    """
    larguras = [largura(txt, fnt, cp, tr) for txt, fnt, cp, tr in blocos]
    x = CX - sum(larguras) / 2
    t = c.beginText()
    t.setFillColor(PRETO)
    for (txt, fnt, cp, tr), w in zip(blocos, larguras):
        t.setFont(fnt, cp)
        t.setCharSpace(tr)
        t.setTextOrigin(x, y(base_top_down))
        t.textOut(txt)
        x += w
    c.drawText(t)


def simples(c, texto, fonte, corpo, tracking, base_top_down):
    centrado(c, [(texto, fonte, corpo, tracking)], base_top_down)


def linha_base(topo, corpo):
    """Linha de base a partir do topo da caixa do texto."""
    return topo + ASCENDER * corpo


# ------------------------------------------------------------------- layout --
# Bloco da marca (posicoes originais preservadas)
DESTRA_BASE = linha_base(32.220, 8.5)      # 40.43
LAB_BASE = linha_base(44.440, 8.5)         # 52.65
# Filete: agora logo abaixo da logo (antes ficava acima de PARFUM)
FILETE_Y = 62.0
FILETE_W = 35.433                          # 12,5 mm
# Nome do perfume: fonte fina, caixa alta, entreletra larga
NOME_BASE = 102.0
NOME_CORPO = 13.0
NOME_TRACKING = 0.22                       # em
NOME_LARGURA_MAX = 102.0
# Notas olfativas separadas por bullet
NOTAS_BASE = 123.0
NOTAS_CORPO = 4.2
NOTAS_TRACKING = 0.22                      # em
NOTAS_LARGURA_MAX = 106.0
# Bloco inferior (posicoes originais preservadas)
PARFUM_BASE = linha_base(140.570, 5.5)     # 145.88
VOLUME_BASE = linha_base(156.300, 5.0)     # 161.13


def notas_tracking():
    """Entreletra das notas: a mesma nos quatro rotulos."""
    return tracking_comum([" • ".join(n) for _, _, n in ROTULOS], LIGHT,
                          NOTAS_CORPO, NOTAS_TRACKING, NOTAS_LARGURA_MAX)


def desenhar_arte(c, nome, notas):
    # codigo de barras decorativo
    c.setFillColor(PRETO)
    for x0, w in BARRAS:
        c.rect(x0, y(BARRAS_Y1), w, BARRAS_Y1 - BARRAS_Y0, stroke=0, fill=1)

    # DESTRA / L A B.  (medidas da logo original preservadas)
    simples(c, "DESTRA", BOLD, 8.5,
            tracking_para("DESTRA", BOLD, 8.5, 37.370), DESTRA_BASE)
    lab_track = (26.150 - pdfmetrics.stringWidth("LAB.", LIGHT, 8.5)) / 2
    centrado(c, [("LAB", LIGHT, 8.5, lab_track), (".", LIGHT, 8.5, 0.0)],
             LAB_BASE)

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
    simples(c, " • ".join(notas), LIGHT, NOTAS_CORPO, notas_tracking(),
            NOTAS_BASE)

    # PARFUM
    simples(c, "PARFUM", MEDIUM, 5.5,
            tracking_para("PARFUM", MEDIUM, 5.5, 32.370), PARFUM_BASE)

    # volume
    volume = "100 ML · 3.4 FL.OZ"
    simples(c, volume, LIGHT, 5.0,
            tracking_para(volume, LIGHT, 5.0, 64.210), VOLUME_BASE)


def desenhar_faca(c):
    """Quadrado preto da faca (linha de corte) + ficha tecnica na sangria."""
    c.setStrokeColor(PRETO)
    c.setLineWidth(0.4)
    c.roundRect(BLEED, BLEED, TRIM_W, TRIM_H, RADIUS, stroke=1, fill=0)

    ficha = "FACA 45 x 60 mm · raio 3 · sangria 3 · seg. 3"
    simples(c, ficha, LIGHT, 3.8, 0.0, linha_base(2.570, 3.8))


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
            desenhar_faca(c)
        c.showPage()

    c.save()
    return caminho


if __name__ == "__main__":
    for indice, nome, notas in ROTULOS:
        print("gerado:", gerar(indice, nome, notas).name)
