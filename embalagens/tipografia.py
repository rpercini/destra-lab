#!/usr/bin/env python3
"""Gera out/Tipografia_DestraLab.pdf — especificação tipográfica da luva e do rótulo."""
import os
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.pagesizes import A4

HERE = os.path.dirname(os.path.abspath(__file__))
MM = 72 / 25.4
for w, n in [(300, "Light"), (400, "Regular"), (500, "Medium"), (600, "SemiBold"), (700, "Bold")]:
    pdfmetrics.registerFont(TTFont(f"LF-{w}", os.path.join(HERE, "fonts", f"LibreFranklin-{n}.ttf")))

ROWS = [
    (700, "Bold", ["DESTRA (lockup vertical e horizontal)"]),
    (600, "SemiBold", ["Nome da fragrância (EXPONENCIAL, LIVE, AMADA, MITO)"]),
    (500, "Medium", ["PARFUM no rótulo",
                     "Na luva: “EVOLUÇÃO OLFATIVA”, títulos de fase (01 TOPO…), descritivo,",
                     "“DESTRA LAB.” do cabeçalho do verso e “INGREDIENTES / INGREDIENTS”"]),
    (400, "Regular", ["Só nos dígitos do EAN-13 e nas anotações técnicas em magenta da página de guias"]),
    (300, "Light", ["LAB. do lockup, FÓRMULA Nº, volume, descritivo e “INDÚSTRIA BRASILEIRA”",
                    "no rótulo, marcos do eixo, nomes das notas, frase, modo de uso,",
                    "“FEITO POR BRASILEIROS” e textos legais da lateral B"]),
]

W, H = A4
out = os.path.join(HERE, "out", "Tipografia_DestraLab.pdf")
c = canvas.Canvas(out, pagesize=A4)
c.setTitle("Destra Lab. · Tipografia das embalagens"); c.setAuthor("Destra Lab.")
c.setFillColorCMYK(0, 0, 0, 1)
m = 22 * MM
y = H - 28 * MM

def t(x, y, s, font, size, track=0):
    c.setFont(font, size)
    if not track: c.drawString(x, y, s); return
    for ch in s:
        c.drawString(x, y, ch); x += pdfmetrics.stringWidth(ch, font, size) + track * size

t(m, y, "DESTRA LAB.", "LF-700", 9, 0.28); y -= 11 * MM
t(m, y, "Tipografia da luva e do rótulo", "LF-600", 22); y -= 7 * MM
t(m, y, "Família única: Libre Franklin (Google Fonts, licença OFL). Caixa alta = 0,742 × corpo.", "LF-300", 9.5); y -= 4.5 * MM
t(m, y, "Impressão em 100 % preto, uma tinta. Fontes embutidas nos PDFs em embalagens/out/.", "LF-300", 9.5); y -= 12 * MM

c.setLineWidth(0.6); c.line(m, y, W - m, y); y -= 7 * MM
t(m, y, "PESO", "LF-500", 7, 0.25); t(m + 50 * MM, y, "ONDE É USADO", "LF-500", 7, 0.25); y -= 3.5 * MM
c.setLineWidth(0.3); c.setStrokeColorCMYK(0, 0, 0, 0.3); c.line(m, y, W - m, y); c.setStrokeColorCMYK(0, 0, 0, 1); y -= 9 * MM

for w, name, lines in ROWS:
    f = f"LF-{w}"
    t(m, y, f"{w}", f, 20)
    t(m, y - 5 * MM, name, f, 9)
    t(m, y - 10 * MM, "DESTRA LAB. Aa 0123", f, 9)
    yy = y
    for ln in lines:
        t(m + 50 * MM, yy, ln, f, 9.5); yy -= 5 * MM
    y -= max(16, 5 * len(lines) + 2) * MM
    c.setLineWidth(0.3); c.setStrokeColorCMYK(0, 0, 0, 0.3); c.line(m, y + 4 * MM, W - m, y + 4 * MM); c.setStrokeColorCMYK(0, 0, 0, 1)
    y -= 5 * MM

y -= 4 * MM
t(m, y, "OBSERVAÇÕES", "LF-500", 7, 0.25); y -= 5.5 * MM
for ln in [
    "1. A logo original (destra-lab-logo-pura.svg) declara Helvetica Neue. Nas artes o lockup é reconstruído",
    "    em Libre Franklin, conforme o handoff e a razão B. Para reprodução literal, vetorizar o lockup como forma.",
    "2. Os dígitos do EAN-13 deveriam estar em OCR-B, fonte padrão do código. Pendência registrada.",
    "3. Tracking: DESTRA 0,028 × corpo; LAB. = (0,70 Wd − largura natural) ÷ 2; demais textos espaçados",
    "    entre 0,08 e 0,55 × corpo conforme a função (ver gerar.py).",
]:
    t(m, y, ln, "LF-300", 8.5); y -= 4.5 * MM

t(m, 15 * MM, "Destra Lab. · Sistema de embalagens · 2026-10-21 · DRAFT", "LF-300", 7, 0.15)
c.showPage(); c.save(); print(out)
