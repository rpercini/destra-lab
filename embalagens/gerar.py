#!/usr/bin/env python3
"""Gerador paramétrico das artes Destra Lab. — luva e rótulo do frasco, 4 SKUs.

Uso:  python3 gerar.py            (gera PDFs em out/ e previews PNG em out/preview/)

Todas as medidas em mm. Cor: 100 % preto, uma tinta (DeviceCMYK, só K).
Regras do sistema em README.md; dados por SKU em skus.json.
"""
import json, os, sys
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
MM = 72 / 25.4  # pt por mm

# ----------------------------------------------------------------------------
# PARÂMETROS DO SISTEMA (ver README.md)
# ----------------------------------------------------------------------------
CAIXA = (155, 110, 40)          # [C] caixa fechada
SANGRIA = 3
LUVA = dict(aba=10, latA=40, frente=110, latB=40, verso=110, altura=155)  # [R] proposta p/ 155x110x40
ROTULO = dict(w=45, h=60, raio=3, seguranca=3)  # [C] 45 largo x 60 alto (confirmado 2026-09-04)

CAP = 0.742                     # caixa alta = 0,742 x corpo
TRACK_DESTRA = 0.028            # x corpo
PESO_DESTRA, PESO_LAB = "LF-700", "LF-300"  # [C] logo: DESTRA Bold 700, LAB. Light 300 (ref/destra-lab-logo-pura.svg)
LAB_RATIO = 0.70                # largura LAB. = 0,70 Wd
ORN_W = 0.40                    # ornamento largura = 0,40 Wd
ORN_H = 0.42                    # ornamento altura = 0,42 caixa alta
ORN_GAP = 0.50                  # distância acima de DESTRA = 0,50 caixa alta
ENTRELINHA = 1.62               # x caixa alta
ORN_SEQ = [2,1,1,2,1,3,1,1,2,1,1,3,2,1,1,2,1,1,3,1,2,1,1,2]  # vãos de 1

NOME_LARGURA_LUVA = 86          # [C] referência do sistema
NOME_LARGURA_ROTULO = 33        # [R] 48 x (45/65) — proporcional à nova largura do rótulo
NOME_BASE = "EXPONENCIAL"       # define o corpo; os demais herdam
DESC_ROTULO = dict(size=4.2, track=0.22, max_w=37.0)  # descritivo no rótulo; track é reduzido p/ o SKU mais longo caber (calculado em main)

BARRA = (60, 2)                 # frente da luva
EIXO_MARCOS = ["0", "15min", "30min", "1h", "2h", "4h", "8h", "12h+"]
EIXO_POS = [0, 8, 14, 21, 28, 37, 46, 58]
RETICULA = {100: 1.0, 70: 0.7, 40: 0.4}

FORMULA_LABEL = "FÓRMULA Nº"    # [P] artes v4/v3 usam "FORMULA" sem acento; handoff escreve "FÓRMULA"
VOLUME = "PARFUM  ·  100 ML  ·  3.4 FL.OZ"
EAN_MAG = 1.0                   # ampliação do EAN-13 na lateral B (nominal 37,29 x 25,93 mm)

# textos comuns [D] (presentes na luva v4 do EXPONENCIAL; aplicados a todos os SKUs — ver README)
MODO_DE_USO = ["Aplicar nos pontos de pulso e pescoço.", "Manter em local fresco e protegido da luz."]
RODAPE = "FEITO POR BRASILEIROS"
LEGAIS_LUVA = {  # PLACEHOLDERS — dados legais pendentes por SKU
    "titulo": "INGREDIENTES / INGREDIENTS",
    "inci": "ALCOHOL DENAT., PARFUM (FRAGRANCE), AQUA (WATER), [LISTA INCI COMPLETA A INSERIR]",
    "fabricante": "INDÚSTRIA BRASILEIRA",  # razão social / CNPJ / endereço removidos a pedido (2026-09-04)
    "sac": "SAC [0000 000 0000] · Produto notificado na ANVISA sob nº [00000000000] · Uso externo. Manter em local fresco, ao abrigo da luz.",
}
LEGAIS_ROTULO = ["INDÚSTRIA BRASILEIRA"]  # razão social / CNPJ e lote removidos a pedido (2026-09-04)

# ----------------------------------------------------------------------------
# fontes
# ----------------------------------------------------------------------------
for w, n in [(300, "Light"), (400, "Regular"), (500, "Medium"), (600, "SemiBold"), (700, "Bold")]:
    pdfmetrics.registerFont(TTFont(f"LF-{w}", os.path.join(HERE, "fonts", f"LibreFranklin-{n}.ttf")))

def sw(s, font, size):
    """largura de string em mm (sem tracking)."""
    return pdfmetrics.stringWidth(s, font, size) / MM

def cap_mm(size):
    return CAP * size / MM

def tracked_w(s, font, size, track_em):
    return sw(s, font, size) + (len(s) - 1) * track_em * size / MM


class Pen:
    """canvas em mm, origem inferior-esquerda, só K."""
    def __init__(self, c):
        self.c = c
    def k(self, k=1.0):
        self.c.setFillColorCMYK(0, 0, 0, k); self.c.setStrokeColorCMYK(0, 0, 0, k)
    def magenta(self):
        self.c.setStrokeColorCMYK(0, 1, 0, 0); self.c.setFillColorCMYK(0, 1, 0, 0)
    def rect(self, x, y, w, h, fill=1, stroke=0):
        self.c.rect(x * MM, y * MM, w * MM, h * MM, fill=fill, stroke=stroke)
    def line(self, x0, y0, x1, y1, width_pt=0.5, dash=None):
        self.c.setLineWidth(width_pt)
        self.c.setDash(dash or [])
        self.c.line(x0 * MM, y0 * MM, x1 * MM, y1 * MM)
        self.c.setDash([])
    def text(self, x, y, s, font, size, track_em=0.0, align="left"):
        """desenha texto; retorna largura em mm."""
        w = tracked_w(s, font, size, track_em)
        if align == "center": x -= w / 2
        elif align == "right": x -= w
        self.c.setFont(font, size)
        if not track_em:
            self.c.drawString(x * MM, y * MM, s)
        else:  # tracking manual, caractere a caractere
            for ch in s:
                self.c.drawString(x * MM, y * MM, ch)
                x += sw(ch, font, size) + track_em * size / MM
        return w
    def wrap(self, s, font, size, track_em, max_w):
        words, lines, cur = s.split(" "), [], ""
        for wd in words:
            t = (cur + " " + wd).strip()
            if tracked_w(t, font, size, track_em) <= max_w or not cur: cur = t
            else: lines.append(cur); cur = wd
        if cur: lines.append(cur)
        return lines


# ----------------------------------------------------------------------------
# elementos do sistema
# ----------------------------------------------------------------------------
def ornamento(p, cx, y_bottom, width, height):
    """ornamento horizontal centrado em cx, base em y_bottom."""
    units = sum(ORN_SEQ) + (len(ORN_SEQ) - 1)
    u = width / units
    x = cx - width / 2
    for i, n in enumerate(ORN_SEQ):
        p.rect(x, y_bottom, n * u, height)
        x += (n + 1) * u

def lockup_vertical(p, cx, baseline, size):
    """DESTRA / LAB. empilhados + ornamento. baseline = linha de base de DESTRA. Retorna dict de métricas."""
    f, fl = PESO_DESTRA, PESO_LAB; cap = cap_mm(size)
    wd = tracked_w("DESTRA", f, size, TRACK_DESTRA)
    p.text(cx, baseline, "DESTRA", f, size, TRACK_DESTRA, "center")
    # LAB. em Light: largura 0,70 Wd; gap = (0,70 Wd − natural) / 2, ponto colado ao B
    parts = ["L", "A", "B."]
    nat = sum(sw(t, fl, size) for t in parts)
    target = LAB_RATIO * wd
    gap = (target - nat) / 2
    x = cx - target / 2
    y2 = baseline - ENTRELINHA * cap
    for t in parts:
        p.text(x, y2, t, fl, size); x += sw(t, fl, size) + gap
    # ornamento
    orn_h = ORN_H * cap
    orn_bottom = baseline + cap + ORN_GAP * cap
    ornamento(p, cx, orn_bottom, ORN_W * wd, orn_h)
    return dict(wd=wd, cap=cap, top=orn_bottom + orn_h, lab_baseline=y2, bottom=y2 - 0.246 * size / MM)

def lockup_horizontal(p, cx, baseline, size):
    """DESTRA LAB. em uma linha + ornamento acima. [D] parâmetros observados na v4; não formalizados no handoff."""
    f, fl = PESO_DESTRA, PESO_LAB; cap = cap_mm(size)
    sp = sw(" ", f, size) + 2 * TRACK_DESTRA * size / MM
    w1, w2 = tracked_w("DESTRA", f, size, TRACK_DESTRA), tracked_w("LAB.", fl, size, TRACK_DESTRA)
    w = w1 + sp + w2
    p.text(cx - w / 2, baseline, "DESTRA", f, size, TRACK_DESTRA)
    p.text(cx - w / 2 + w1 + sp, baseline, "LAB.", fl, size, TRACK_DESTRA)
    orn_h = ORN_H * cap
    ornamento(p, cx, baseline + cap + ORN_GAP * cap, ORN_W * w, orn_h)
    return dict(w=w, cap=cap, top=baseline + cap + ORN_GAP * cap + orn_h)

def fit_nome(target_mm):
    return target_mm * MM / pdfmetrics.stringWidth(NOME_BASE, "LF-600", 1)

def grafico_olfativo(p, x0, y_top, width, curva, ky=1.0):
    """gráfico de barras temporal. x0 = margem esquerda do bloco (coluna de etiquetas); retorna y do fundo."""
    col = 31 * (width / 92)  # coluna de etiquetas proporcional à área útil (v4: 31 de 92)
    gx0, gw = x0 + col, width - col
    def X(u): return gx0 + gw * u / 58
    # rhythm (v4, escalado verticalmente por ky)
    r_first, r_bar, r_title, r_pitch, r_end = 2.95 * ky, 3.55 * ky, 5.25 * ky, 3.4 * ky, 6.1 * ky
    bar_h = 2.6
    # eixo
    p.k(1.0)
    for m, u in zip(EIXO_MARCOS, EIXO_POS):
        p.text(X(u), y_top + 3.0, m, "LF-300", 4.4, 0, "center")
    fases = []
    for n in curva:
        if not fases or fases[-1][0] != n["fase"]: fases.append((n["fase"], []))
        fases[-1][1].append(n)
    y = y_top
    last_center = None
    for i, (fase, notas) in enumerate(fases):
        y_title = (y_top - r_first) if i == 0 else (last_center - r_title)
        p.k(1.0); p.text(x0, y_title, fase.upper(), "LF-500", 4.8, 0.35)
        yc = y_title - r_bar
        for n in notas:
            p.k(1.0); p.text(x0 + 1.5, yc - 0.55, n["nota"].upper(), "LF-300", 4.2, 0.10)
            p.k(RETICULA[n["reticula"]]); p.rect(X(n["inicio"]), yc - bar_h / 2, X(n["fim"]) - X(n["inicio"]), bar_h)
            last_center = yc; yc -= r_pitch
    y_bottom = last_center - r_end
    # grade (K15, atrás visualmente é aceitável: linhas finas; desenhadas por último para simplicidade)
    p.k(0.15)
    for u in EIXO_POS: p.line(X(u), y_top, X(u), y_bottom, 0.25)
    p.k(1.0)
    return y_bottom

# ----------------------------------------------------------------------------
# EAN-13 (placeholder — número definitivo por SKU pendente)
# ----------------------------------------------------------------------------
_L = ["0001101","0011001","0010011","0111101","0100011","0110001","0101111","0111011","0110111","0001011"]
_G = ["0100111","0110011","0011011","0100001","0011101","0111001","0000101","0010001","0001001","0010111"]
_R = [s.translate(str.maketrans("01","10")) for s in _L]
_PAR = ["LLLLLL","LLGLGG","LLGGLG","LLGGGL","LGLLGG","LGGLLG","LGGGLL","LGLGLG","LGLGGL","LGGLGL"]

def ean13_check(d12):
    s = sum(int(c) * (3 if i % 2 else 1) for i, c in enumerate(d12))
    return str((10 - s % 10) % 10)

def ean13_modules(d13):
    assert len(d13) == 13 and ean13_check(d13[:12]) == d13[12]
    bits = "101"
    for i, ch in enumerate(d13[1:7]):
        bits += (_L if _PAR[int(d13[0])][i] == "L" else _G)[int(ch)]
    bits += "01010"
    for ch in d13[7:]: bits += _R[int(ch)]
    return bits + "101"

def ean13(p, x, y, d13, mag=1.0):
    """desenha EAN-13 com canto inferior-esquerdo da área nominal em (x, y). Nominal 37,29 x 25,93 mm."""
    mod = 0.33 * mag; qz = 11 * mod
    y_bar = y + (25.93 - 22.85) * mag       # barras-guarda: 22,85 mm; dígitos abaixo delas
    bits = ean13_modules(d13)
    p.k(1.0)
    bx = x + qz
    for i, b in enumerate(bits):
        guard = i < 3 or 45 <= i < 50 or i >= 92
        if b == "1":
            p.rect(bx + i * mod, y_bar + (0 if guard else 1.65 * mag), mod, 22.85 * mag - (0 if guard else 1.65 * mag))
    fs = 9.5 * mag  # dígitos (Libre Franklin Regular; OCR-B é a fonte padrão — [P])
    p.text(x + qz - 0.8 * mag, y + 0.4 * mag, d13[0], "LF-400", fs, 0, "right")
    p.text(bx + 3 * mod + 21 * mod, y + 0.4 * mag, d13[1:7], "LF-400", fs, 0.10, "center")
    p.text(bx + 50 * mod + 21 * mod, y + 0.4 * mag, d13[7:], "LF-400", fs, 0.10, "center")
    return 37.29 * mag, 25.93 * mag

# ----------------------------------------------------------------------------
# LUVA
# ----------------------------------------------------------------------------
def luva_panels():
    L = LUVA
    return [("aba", L["aba"]), ("latA", L["latA"]), ("frente", L["frente"]), ("latB", L["latB"]), ("verso", L["verso"])]

def luva_pagesize():
    return sum(w for _, w in luva_panels()) + 2 * SANGRIA, LUVA["altura"] + 2 * SANGRIA

def luva(c, sku, guias):
    H = LUVA["altura"]; S = SANGRIA
    panels = luva_panels(); trim_w = sum(w for _, w in panels)
    p = Pen(c)
    ky = H / 125  # escala vertical das posições em relação à v4 (altura 125)
    px = {}; x = S
    for n, w in panels: px[n] = (x, w); x += w
    num = sku["numero"]; nome_size = nome_size_luva

    # ---- FRENTE (orientação normal)
    x0, w = px["frente"]; cx = x0 + w / 2; top = S + H
    lockup_vertical(p, cx, top - 25.0 * ky, 21.0)
    p.k(1.0)
    p.text(cx, top - 68.7 * ky, sku["nome"], "LF-600", nome_size, 0, "center")
    p.text(cx, top - 78.9 * ky, f"{FORMULA_LABEL} {num}", "LF-300", 6.5, 0.35, "center")
    p.text(cx, top - 97.9 * ky, VOLUME, "LF-300", 6.5, 0.22, "center")
    p.rect(cx - BARRA[0] / 2, top - 107 * ky - BARRA[1], BARRA[0], BARRA[1])

    # ---- LATERAL A (90° horário, leitura de cima para baixo): origem no canto superior-esquerdo
    x0, w = px["latA"]
    c.saveState(); c.translate(x0 * MM, top * MM); c.rotate(-90)
    # local: +x desce pelo painel, +y vai para a direita (topo das letras aponta para a direita)
    size = 13.0; cap = cap_mm(size)
    f_size = 5.5; f_cap = cap_mm(f_size)
    f_base_off = 2.0 * cap               # baseline da fórmula abaixo da baseline do lockup
    block_bottom = -f_base_off; block_top = cap + ORN_GAP * cap + ORN_H * cap
    base = w / 2 - (block_top + block_bottom) / 2
    lockup_horizontal(p, H / 2, base, size)
    p.k(1.0); p.text(H / 2, base - f_base_off, f"{FORMULA_LABEL} {num}", "LF-300", f_size, 0.35, "center")
    c.restoreState()

    # ---- LATERAL B (90° anti-horário, leitura de baixo para cima): origem no canto inferior-direito
    x0, w = px["latB"]
    c.saveState(); c.translate((x0 + w) * MM, S * MM); c.rotate(90)
    # local: +x sobe pelo painel, +y vai para a esquerda (topo das letras aponta para a esquerda)
    ean_w, ean_h = 37.29 * EAN_MAG, 25.93 * EAN_MAG
    ean_x = H - 8 - ean_w
    ean13(p, ean_x, (w - ean_h) / 2, sku["ean_placeholder"], EAN_MAG)
    fs, fL = 4.4, "LF-300"
    PITCH_LINHA, PITCH_PARA = 3.2, 4.4
    maxlen = ean_x - 6 - 6
    cols = [(LEGAIS_LUVA["titulo"], "LF-500", 4.6, 0.30, PITCH_PARA)]
    for key in ("inci", "fabricante", "sac"):
        lines = p.wrap(LEGAIS_LUVA[key], fL, fs, 0, maxlen)
        for j, ln in enumerate(lines):
            cols.append((ln, fL, fs, 0, PITCH_PARA if j == len(lines) - 1 else PITCH_LINHA))
    text_w = sum(cn[4] for cn in cols[:-1])          # da baseline da 1ª coluna à baseline da última
    block_w = cap_mm(4.6) + text_w                   # caixa alta do título à baseline da última coluna
    y = (w + block_w) / 2 - cap_mm(4.6)              # baseline da 1ª coluna (esquerda do painel = y maior)
    for t, f, s, tr, pitch in cols:
        p.k(1.0); p.text(6, y, t, f, s, tr); y -= pitch
    c.restoreState()

    # ---- VERSO (normal)
    x0, w = px["verso"]; m = 8; ax0, aw = x0 + m, w - 2 * m; cx = x0 + w / 2
    p.k(1.0)
    p.text(ax0, top - 9.95 * ky, f"{FORMULA_LABEL} {num}", "LF-300", 5.5, 0.35)
    p.text(ax0 + aw, top - 9.95 * ky, "DESTRA LAB.", "LF-500", 5.5, 0.35, "right")
    p.line(ax0, top - 13 * ky, ax0 + aw, top - 13 * ky, 0.5)
    p.text(cx, top - 19.9 * ky, "EVOLUÇÃO OLFATIVA", "LF-500", 6.5, 0.40, "center")
    y_bot = grafico_olfativo(p, ax0, top - 29 * ky, aw, sku["curva"], ky)
    # bloco inferior ancorado pela base (distâncias da v4 escaladas)
    bot = S
    p.text(cx, bot + 7.5 * ky, RODAPE, "LF-300", 5.0, 0.55, "center")
    p.k(0.15); p.line(ax0, bot + 11.5 * ky, ax0 + aw, bot + 11.5 * ky, 0.5); p.k(1.0)  # fio cinza
    y = bot + 15.5 * ky
    for ln in reversed(MODO_DE_USO):
        p.text(cx, y, ln, "LF-300", 5.0, 0.08, "center"); y += 4.7 * ky
    p.text(cx, bot + 29.0 * ky, sku["frase"], "LF-300", 5.0, 0.08, "center")
    p.text(cx, bot + 34.1 * ky, sku["descritivo"].upper(), "LF-500", 7.0, 0.30, "center")
    y_rule = bot + 40.0 * ky
    p.line(ax0, y_rule, ax0 + aw, y_rule, 0.5)
    if y_bot < y_rule + 1.5:
        print(f"  ! verso {sku['nome']}: gráfico termina em {y_bot:.1f}, fio em {y_rule:.1f} — sobreposição", file=sys.stderr)

    # ---- guias
    if guias:
        p.magenta(); c.setLineWidth(0.4)
        c.rect(S * MM, S * MM, trim_w * MM, H * MM, fill=0, stroke=1)
        for n, (x, w) in px.items():
            if n != "aba": p.line(x, S - 1, x, S + H + 1, 0.4, [1.5, 1.5])
            lab = {"aba": "ABA (COLA)", "latA": "LATERAL A", "frente": "FRENTE", "latB": "LATERAL B", "verso": "VERSO"}[n]
            p.text(x + w / 2, S + H + 1.2, f"{lab} {w}", "LF-400", 5, 0, "center")
        p.text(S, 0.8, f"LUVA · {num} {sku['nome']} · trim {trim_w} x {H} mm · sangria {S} mm · caixa {CAIXA[0]}x{CAIXA[1]}x{CAIXA[2]} mm · folga da gráfica não incluída · DRAFT", "LF-400", 5)
        p.k(1.0)
    c.showPage()

# ----------------------------------------------------------------------------
# RÓTULO
# ----------------------------------------------------------------------------
def rotulo_pagesize():
    return ROTULO["w"] + 2 * SANGRIA, ROTULO["h"] + 2 * SANGRIA

def rotulo(c, sku, guias):
    """rótulo 45 x 60 (retrato). Pilha da v3 sem FÓRMULA e sem razão social / lote; bloco centrado na altura."""
    R = ROTULO; S = SANGRIA; W, H = R["w"], R["h"]
    PW, PH = rotulo_pagesize()
    p = Pen(c)
    cx = PW / 2
    lk_size = 8.5; cap = cap_mm(lk_size)
    nome_cap = cap_mm(nome_size_rotulo)
    # alturas relativas (mm, do topo do ornamento para baixo)
    y_destra = ORN_H * cap + ORN_GAP * cap + cap
    y_lab = y_destra + ENTRELINHA * cap
    y_nome = y_lab + 7.7 + nome_cap
    y_desc = y_nome + 6.5
    y_rule = y_desc + 4.5
    y_parfum = y_rule + 5.5
    y_vol = y_parfum + 4.5
    y_rule2 = y_vol + 4.0
    y_legal = y_rule2 + 3.8
    block_h = y_legal
    top = S + H - (H - block_h) / 2            # topo do bloco (página, y para cima)
    Y = lambda d: top - d
    lockup_vertical(p, cx, Y(y_destra), lk_size)
    p.k(1.0)
    p.text(cx, Y(y_nome), sku["nome"], "LF-600", nome_size_rotulo, 0, "center")
    p.text(cx, Y(y_desc), sku["descritivo"].upper(), "LF-300", DESC_ROTULO["size"], DESC_ROTULO["track"], "center")
    p.line(cx - 6.25, Y(y_rule), cx + 6.25, Y(y_rule), 0.5)
    p.text(cx, Y(y_parfum), "PARFUM", "LF-500", 5.5, 0.30, "center")
    p.text(cx, Y(y_vol), "100 ML  ·  3.4 FL.OZ", "LF-300", 5.0, 0.20, "center")
    p.k(0.18); p.line(S + 4, Y(y_rule2), S + W - 4, Y(y_rule2), 0.4); p.k(1.0)
    p.text(cx, Y(y_legal), LEGAIS_ROTULO[0], "LF-300", 4.0, 0.02, "center")
    if guias:
        p.magenta(); c.setLineWidth(0.4)
        c.roundRect(S * MM, S * MM, W * MM, H * MM, R["raio"] * MM, fill=0, stroke=1)
        c.setDash([1.5, 1.5]); c.roundRect((S + 3) * MM, (S + 3) * MM, (W - 6) * MM, (H - 6) * MM, 1.5 * MM, fill=0, stroke=1); c.setDash([])
        p.text(PW / 2, PH - 2.2, f"FACA {W} x {H} mm · raio {R['raio']} · sangria {S} · seg. 3 · DRAFT", "LF-400", 3.8, 0, "center")
        p.k(1.0)
    c.showPage()

# ----------------------------------------------------------------------------
def main():
    global nome_size_luva, nome_size_rotulo
    nome_size_luva = fit_nome(NOME_LARGURA_LUVA)
    nome_size_rotulo = fit_nome(NOME_LARGURA_ROTULO)
    print(f"corpo do nome: luva {nome_size_luva:.2f} pt ({NOME_LARGURA_LUVA} mm) · rótulo {nome_size_rotulo:.2f} pt ({NOME_LARGURA_ROTULO} mm)")
    data = json.load(open(os.path.join(HERE, "skus.json"), encoding="utf-8"))
    # tracking do descritivo no rótulo: o maior valor (<= 0,22 em) em que o SKU mais longo cabe em max_w
    ds = DESC_ROTULO["size"]
    for sku in data["skus"]:
        t = sku["descritivo"].upper()
        fit = (DESC_ROTULO["max_w"] - sw(t, "LF-300", ds)) / ((len(t) - 1) * ds / MM)
        DESC_ROTULO["track"] = min(DESC_ROTULO["track"], round(fit, 3))
    print(f"descritivo do rótulo: {ds} pt, tracking {DESC_ROTULO['track']} em (limite {DESC_ROTULO['max_w']} mm)")
    os.makedirs(OUT, exist_ok=True)
    for sku in data["skus"]:
        base12 = f"78900000000{sku['numero'][-1]}"
        sku["ean_placeholder"] = base12 + ean13_check(base12)
        print(f"{sku['numero']} {sku['nome']}: nome luva {sw(sku['nome'],'LF-600',nome_size_luva):.1f} mm · rótulo {sw(sku['nome'],'LF-600',nome_size_rotulo):.1f} mm · EAN placeholder {sku['ean_placeholder']}")
        for kind, fn, ps in (("Luva", luva, luva_pagesize), ("Rotulo", rotulo, rotulo_pagesize)):
            path = os.path.join(OUT, f"{kind}_{sku['numero']}_{sku['nome']}_DRAFT.pdf")
            pw, ph = ps()
            c = canvas.Canvas(path, pagesize=(pw * MM, ph * MM))
            c.setTitle(f"Destra Lab · {kind} · {sku['numero']} {sku['nome']}"); c.setAuthor("Destra Lab.")
            fn(c, sku, True)    # página 1: com guias (faca, dobras, anotações)
            fn(c, sku, False)   # página 2: arte limpa
            c.save()

if __name__ == "__main__":
    main()
