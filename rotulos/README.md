# Rótulos Destra Lab — arquivos para gráfica

Quatro rótulos de perfume, um PDF por fragrância.

## Especificação

| Item | Valor |
|---|---|
| Faca (corte final) | 45 × 60 mm, cantos com raio 3 mm |
| Sangria | 3 mm em cada lado → página de 51 × 66 mm |
| Margem de segurança | 3 mm para dentro da faca |
| Cor | somente preto, 100% K (sem RGB, sem preto composto) |
| Tipografia | Libre Franklin, vetorial e embutida no PDF (não precisa enviar fonte) |
| Corpos | DESTRA / LAB. 10,6 pt, nome 13 pt (reduz nos nomes longos), PARFUM e volume 4,2 pt |
| Moldura | retângulo preto de 0,4 pt, 3 mm para dentro da faca — é arte, sai impressa |
| Caixas do PDF | BleedBox = página inteira, TrimBox e ArtBox = faca |

Cada arquivo tem **duas páginas**:

1. **Arte + faca** — a arte com o retângulo magenta da faca (45 × 60 mm) e a
   ficha técnica na área de sangria. Serve de prova de corte.
2. **Arte final** — só a arte, sem marca nenhuma. É esta a página que vai para
   impressão.

A moldura preta aparece nas duas páginas: ela é elemento de arte, não marca
de corte.

## Arquivos

- `Rotulo_01_LIVE.pdf`
- `Rotulo_02_EXPONENCIAL.pdf`
- `Rotulo_03_AMADA.pdf`
- `Rotulo_04_MITO.pdf`

As notas olfativas de cada fragrância continuam registradas em `ROTULOS`, mas
não são impressas. Para trazê-las de volta, basta `NOTAS_VISIVEIS = True`.

## Como regerar

```bash
pip install reportlab
python3 gerar_rotulos.py
```

O layout inteiro fica em `gerar_rotulos.py`: medidas, linhas de base e
entreletras no topo do arquivo, textos de cada rótulo na lista `ROTULOS`.

## Fontes

`fonts/` traz Libre Franklin (Light 300, Medium 500, Bold 700), baixada do
Google Fonts e distribuída sob a SIL Open Font License 1.1
(<https://openfontlicense.org>).
