import os
import calendar
from app.i18n import weekdays_short
from reportlab.lib.pagesizes import landscape, A4
from reportlab.lib import colors
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm


MESES_PT = {
    1: "JANEIRO", 2: "FEVEREIRO", 3: "MARÇO", 4: "ABRIL",
    5: "MAIO", 6: "JUNHO", 7: "JULHO", 8: "AGOSTO",
    9: "SETEMBRO", 10: "OUTUBRO", 11: "NOVEMBRO", 12: "DEZEMBRO",
}

TIPOS_WELFARE = {
    "Welfare": ["cooking.png"],
    "Welfare Livre": ["cooking.png", "star.png"],
    "Welfare Aniversário": ["cooking.png", "cake.png"],
    "Welfare Outros": ["cooking.png", "cookingtree-dots.png"],
}


def gerar_pdf_mes(ano, mes, dados_mes, imagens_cache_path):
    output_dir = os.path.join(os.getcwd(), "exports")
    os.makedirs(output_dir, exist_ok=True)

    caminho_pdf = os.path.join(output_dir, f"SIGCP_{ano}_{mes:02d}.pdf")

    c = canvas.Canvas(caminho_pdf, pagesize=landscape(A4))
    largura, altura = landscape(A4)

    margem = 8 * mm
    sidebar_w = 25 * mm
    topo_h = 16 * mm
    notas_h = 14 * mm

    grid_x = margem + sidebar_w
    grid_y = margem + notas_h
    grid_w = largura - margem * 2 - sidebar_w
    grid_h = altura - margem * 2 - topo_h - notas_h

    col_w = grid_w / 7
    header_h = 10 * mm
    row_h = (grid_h - header_h) / 6

    cor_principal = colors.HexColor("#0b4b52")
    cor_vermelho = colors.HexColor("#b90f12")
    cor_weekend = colors.HexColor("#d8f1f4")
    cor_linha = colors.HexColor("#b7b7b7")
    cor_ementa = colors.HexColor("#008f3a")
    cor_refeicao = colors.HexColor("#1f73e8")

    # Sidebar
    c.setFillColor(cor_principal)
    c.rect(margem, margem, sidebar_w, altura - margem * 2, fill=1, stroke=0)

    c.setFillColor(cor_vermelho)
    c.rect(margem, altura - margem - 22 * mm, sidebar_w, 22 * mm, fill=1, stroke=0)

    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 18)
    c.drawCentredString(margem + sidebar_w / 2, altura - margem - 14 * mm, str(ano))

    c.saveState()
    c.translate(margem + sidebar_w / 2, altura / 2)
    c.rotate(90)
    c.setFont("Helvetica", 26)
    c.drawCentredString(0, -5, MESES_PT[mes])
    c.restoreState()

    # Cabeçalhos
    dias = weekdays_short()

    for i, dia in enumerate(dias):
        x = grid_x + i * col_w
        y = grid_y + 6 * row_h

        c.setFillColor(cor_principal)
        c.rect(x, y, col_w, header_h, fill=1, stroke=1)

        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 10)
        c.drawCentredString(x + col_w / 2, y + 3.5 * mm, dia)

    cal = calendar.Calendar(firstweekday=0)
    semanas = cal.monthdayscalendar(ano, mes)

    while len(semanas) < 6:
        semanas.append([0, 0, 0, 0, 0, 0, 0])

    for r, semana in enumerate(semanas):
        for col, dia in enumerate(semana):
            x = grid_x + col * col_w
            y = grid_y + (5 - r) * row_h

            if col in [5, 6]:
                c.setFillColor(cor_weekend)
            else:
                c.setFillColor(colors.white)

            c.rect(x, y, col_w, row_h, fill=1, stroke=1)

            if dia == 0:
                continue

            data_str = f"{ano}-{mes:02d}-{dia:02d}"
            welfares = dados_mes.get(data_str, [])

            c.setFillColor(colors.black)
            c.setFont("Helvetica", 8)
            c.drawString(x + 2 * mm, y + row_h - 5 * mm, str(dia))

            if not welfares:
                continue

            c.setStrokeColor(cor_linha)
            c.line(x + 2 * mm, y + row_h - 10 * mm, x + col_w - 2 * mm, y + row_h - 10 * mm)

            bloco_y = y + row_h - 17 * mm

            for welfare in welfares:
                refeicao = welfare["refeicao"]
                tipo = welfare["tipo"]
                obs = welfare.get("observacao") or ""
                prato = welfare.get("prato") or ""
                sobremesa = welfare.get("sobremesa") or ""

                c.setFillColor(cor_refeicao)
                c.setFont("Helvetica-Bold", 8)
                c.drawString(x + 3 * mm, bloco_y, refeicao.upper())

                icon_x = x + col_w - 8 * mm
                for icon in reversed(TIPOS_WELFARE.get(tipo, [])):
                    icon_path = os.path.join(imagens_cache_path, icon)
                    if os.path.exists(icon_path):
                        c.drawImage(icon_path, icon_x, bloco_y - 2 * mm, width=5 * mm, height=5 * mm, mask="auto")
                        icon_x -= 6 * mm

                bloco_y -= 4 * mm

                if obs:
                    c.setFillColor(colors.black)
                    c.setFont("Helvetica-Bold", 6.5)
                    c.drawString(x + 3 * mm, bloco_y, obs[:34])
                    bloco_y -= 4 * mm

                ementa = ""
                if prato and sobremesa:
                    ementa = f"{prato}/{sobremesa}"
                elif prato:
                    ementa = prato
                elif sobremesa:
                    ementa = sobremesa

                if ementa:
                    c.setFillColor(cor_ementa)
                    c.setFont("Helvetica", 6.5)
                    c.drawString(x + 3 * mm, bloco_y, ementa[:38])
                    bloco_y -= 5 * mm

                c.setStrokeColor(cor_linha)
                c.line(x + 3 * mm, bloco_y + 2 * mm, x + col_w - 3 * mm, bloco_y + 2 * mm)
                bloco_y -= 3 * mm

    # Notas / legenda
    c.setFillColor(colors.white)
    c.rect(grid_x, margem, grid_w, notas_h, fill=1, stroke=1)

    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(grid_x + 45 * mm, margem + 5 * mm, "NOTAS:")

    legendas = [
        ("Welfare", "cooking.png"),
        ("Aniversário", "cake.png"),
        ("Welfare Livre", "star.png"),
    ]

    lx = grid_x + 80 * mm
    for texto, icon in legendas:
        c.setFont("Helvetica", 9)
        c.drawString(lx, margem + 5 * mm, texto)

        icon_path = os.path.join(imagens_cache_path, icon)
        if os.path.exists(icon_path):
            c.drawImage(icon_path, lx + 22 * mm, margem + 3 * mm, width=6 * mm, height=6 * mm, mask="auto")

        lx += 55 * mm

    c.save()
    return caminho_pdf
