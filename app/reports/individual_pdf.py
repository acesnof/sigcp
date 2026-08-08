from reportlab.lib.pagesizes import landscape, A4
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.units import mm


COR_PRINCIPAL = colors.HexColor("#0b4b52")
COR_LINHA = colors.HexColor("#b7b7b7")
COR_WEEKEND = colors.HexColor("#d8f1f4")
COR_FERIAS = colors.HexColor("#78dafa")
COR_INATIVO = colors.HexColor("#888888")
COR_BRANCO = colors.white
COR_VERMELHO = colors.HexColor("#b90f12")
COR_TOTAL = colors.HexColor("#e8f4f6")


def _hex_color(value, default=COR_BRANCO):
    if not value:
        return default
    try:
        return colors.HexColor(value)
    except Exception:
        return default


def _fmt(valor):
    try:
        return f"{int(valor):,}".replace(",", ".")
    except Exception:
        return str(valor or "")



def gerar_pdf_welfare_individual(caminho_pdf, titulo, periodo, dias, rows, totais_dfac, day_offs=None, modo_paginas=1):
    """
    Gera a tabela Welfare Individual em A4 horizontal.

    modo_paginas:
        1 -> mês inteiro numa página
        2 -> duas páginas: dias 1-15 e dias restantes
    """
    day_offs = day_offs or set()

    c = canvas.Canvas(caminho_pdf, pagesize=landscape(A4))
    page_w, page_h = landscape(A4)

    cor_marcado = colors.HexColor("#b41617")

    def normalizar_fill(fill_value):
        """No PDF, DFAC é branco; welfare/ausência DFAC marcada é #b41617."""
        if not fill_value:
            return colors.white
        valor = str(fill_value).lower()
        if valor in ("#b90f12", "#b41617"):
            return cor_marcado
        if valor in ("#ffffff", "#fff", "white", "#d8f1f4"):
            return colors.white
        return _hex_color(fill_value, colors.white)

    def calcular_totais_resumo():
        total_welfares_geral = 0
        total_reimbursement = 0
        for row in rows:
            welfare_total = int(row.get("welfare_total") or 0)
            cohesion_total = int(row.get("cohesion_total") or 0)
            total_welfares_geral += welfare_total + cohesion_total
            total_reimbursement += int(row.get("reimbursement") or 0)
        return total_welfares_geral, total_reimbursement

    total_welfares_geral, total_reimbursement = calcular_totais_resumo()

    if int(modo_paginas or 1) == 2 and len(dias) > 15:
        paginas = [dias[:15], dias[15:]]
    else:
        paginas = [dias]

    # Em duas folhas, a altura das linhas tem de ser calculada uma unica vez.
    # A primeira pagina reserva espaco para a identificacao e a segunda nao;
    # alem disso, as metades podem ter numeros de dias diferentes. Calcular a
    # altura em cada pagina faria as pessoas deixarem de alinhar lado a lado.
    row_h_duas_paginas = None
    if len(paginas) == 2:
        margem_calculo = 4 * mm
        usable_w_calculo = page_w - 2 * margem_calculo
        usable_h_calculo = page_h - 2 * margem_calculo
        available_rows_h_calculo = usable_h_calculo - 13 * mm - 5.0 * mm - 4.0 * mm - 6.2 * mm
        n_rows_calculo = max(1, len(rows))

        larguras_celula = []
        for indice, dias_pagina in enumerate(paginas, start=1):
            ident_w_calculo = 50 * mm if indice == 1 else 0
            larguras_celula.append(
                (usable_w_calculo - ident_w_calculo) / max(1, len(dias_pagina) * 3)
            )

        row_h_duas_paginas = min(
            min(larguras_celula),
            available_rows_h_calculo / n_rows_calculo,
        )
        row_h_duas_paginas = max(2.35 * mm, row_h_duas_paginas)

    def desenhar_pagina(dias_pagina, indice_pagina, total_paginas):
        c.setLineWidth(0.10)

        margem = 4 * mm
        usable_w = page_w - 2 * margem
        usable_h = page_h - 2 * margem

        titulo_h = 13 * mm
        header_h1 = 5.0 * mm
        header_h2 = 4.0 * mm
        total_h = 6.2 * mm

        # Impressão em 2 páginas:
        # - Página 1: identificação + primeiros dias.
        # - Página 2: restantes dias, sem Identificação, para poder encostar as folhas.
        # As colunas Total Welfares/Reembolso foram removidas da impressão.
        mostrar_identificacao = not (total_paginas > 1 and indice_pagina == 2)
        mostrar_resumo = False

        # A identificação fica mais larga para os nomes caberem numa só linha.
        ident_w = 50 * mm if mostrar_identificacao else 0
        total_welfares_w = 0
        reimbursement_w = 0
        resumo_w = 0

        dias_w = usable_w - ident_w - resumo_w
        cell_w = dias_w / max(1, len(dias_pagina) * 3)

        n_rows = max(1, len(rows))
        available_rows_h = usable_h - titulo_h - header_h1 - header_h2 - total_h

        # Em 2 páginas as células ficam naturalmente maiores.
        if row_h_duas_paginas is not None:
            row_h = row_h_duas_paginas
        else:
            row_h = min(cell_w, available_rows_h / n_rows)
            row_h = max(2.35 * mm, row_h)

        if len(dias_pagina) <= 7:
            # Impressão de uma semana: aproveitar melhor a folha e tornar o texto mais legível.
            row_h = min(available_rows_h / n_rows, cell_w * 1.35)
            row_h = max(4.2 * mm, row_h)
            font_row = max(5.0, min(8.8, row_h / mm * 1.18))
            font_ident = max(5.0, min(8.4, row_h / mm * 1.10))
            font_dia = 8.6
            font_semana = 6.6
            font_ref = 6.2
            font_total = 7.2
        else:
            font_row = max(2.9, min(5.8, row_h / mm * 1.10))
            font_ident = max(3.0, min(5.6, row_h / mm * 1.05))
            font_dia = 5.8 if len(dias_pagina) <= 15 else 5.2
            font_semana = 4.6 if len(dias_pagina) <= 15 else 4.1
            font_ref = 4.7 if len(dias_pagina) <= 15 else 3.8
            font_total = 5.7 if len(dias_pagina) <= 15 else 4.8

        def _fit_font_size(texto, largura, tamanho_base, minimo=2.4, fonte="Helvetica"):
            texto = str(texto or "")
            tamanho = float(tamanho_base)
            while tamanho > minimo and c.stringWidth(texto, fonte, tamanho) > largura:
                tamanho -= 0.2
            return max(minimo, tamanho)

        x0 = margem
        y_top = page_h - margem

        titulo_export = titulo or "Contingente Português - Welfares/Marcações Individuais"

        c.setFillColor(COR_PRINCIPAL)
        c.setFont("Helvetica", 10)
        c.drawCentredString(page_w / 2, y_top - 5 * mm, titulo_export)
        c.setFont("Helvetica", 7)
        sufixo = periodo
        if total_paginas > 1:
            sufixo = f"{periodo}  |  {indice_pagina}/{total_paginas}"
        c.drawRightString(page_w - margem, y_top - 5 * mm, sufixo)

        # Legenda Welfare, por cima da tabela, encostada à esquerda.
        legend_y = y_top - 10.2 * mm
        legend_size = 3.4 * mm
        c.setFillColor(colors.HexColor("#b01b1b"))
        c.rect(x0, legend_y, legend_size, legend_size, fill=1, stroke=0)
        c.setFillColor(colors.black)
        c.setFont("Helvetica", 7)
        c.drawString(x0 + legend_size + 1.5 * mm, legend_y + 0.55 * mm, "Wellfare")

        y = y_top - titulo_h

        # Cabeçalho identificação
        if mostrar_identificacao:
            c.setFillColor(COR_PRINCIPAL)
            c.rect(x0, y - header_h1 - header_h2, ident_w, header_h1 + header_h2, fill=1, stroke=1)
            c.setFillColor(colors.white)
            c.setFont("Helvetica", 6.0 if len(dias_pagina) <= 7 else 5.5)
            c.drawCentredString(x0 + ident_w / 2, y - (header_h1 + header_h2) / 2 - 1.5, "IDENTIFICAÇÃO")

        # Cabeçalhos dias
        x = x0 + ident_w
        for dia_info in dias_pagina:
            dia = dia_info["dia"]
            weekday = dia_info.get("weekday", "")
            especial = dia_info.get("especial", False)
            fill = COR_WEEKEND if especial else COR_PRINCIPAL
            c.setFillColor(fill)
            c.rect(x, y - header_h1, cell_w * 3, header_h1, fill=1, stroke=1)
            c.setFillColor(colors.white if not especial else COR_PRINCIPAL)
            c.setFont("Helvetica-Bold", font_dia)
            c.drawCentredString(x + 1.5 * cell_w, y - 2.7 * mm, str(dia))
            c.setFont("Helvetica", font_semana)
            c.drawCentredString(x + 1.5 * cell_w, y - 4.55 * mm, weekday)

            for idx, label in enumerate(("PA", "AL", "JA")):
                cx = x + idx * cell_w
                c.setFillColor(COR_WEEKEND if especial else colors.white)
                c.rect(cx, y - header_h1 - header_h2, cell_w, header_h2, fill=1, stroke=1)
                c.setFillColor(COR_PRINCIPAL)
                c.setFont("Helvetica-Bold", font_ref)
                c.drawCentredString(cx + cell_w / 2, y - header_h1 - 2.8 * mm, label)
            x += cell_w * 3

        # Cabeçalhos resumo removidos da impressão.
        resumo_x = x0 + ident_w + cell_w * len(dias_pagina) * 3

        y_data_top = y - header_h1 - header_h2
        y = y_data_top

        # Linhas de pessoas
        for row in rows:
            y -= row_h
            ident = row.get("identificacao", "")
            if mostrar_identificacao:
                c.setFillColor(colors.white)
                c.rect(x0, y, ident_w, row_h, fill=1, stroke=1)
                c.setFillColor(colors.black)
                font_ident_fit = _fit_font_size(ident, ident_w - 1.6 * mm, font_ident, minimo=2.4)
                c.setFont("Helvetica", font_ident_fit)
                c.drawString(x0 + 0.7 * mm, y + row_h / 2 - font_ident_fit / 2 + 1, ident)

            x = x0 + ident_w
            cells = row.get("cells", {})
            for dia_info in dias_pagina:
                dia = dia_info["dia"]
                data_key = dia_info.get("data_str", dia)
                dia_cells = cells.get(data_key, cells.get(dia, {}))
                for key in ("pa", "al", "ja"):
                    info = dia_cells.get(key, {})
                    fill = normalizar_fill(info.get("fill"))
                    c.setFillColor(fill)
                    c.rect(x, y, cell_w, row_h, fill=1, stroke=1)
                    txt = info.get("text", "")
                    if txt:
                        c.setFillColor(COR_PRINCIPAL if txt == "F" else colors.white)
                        c.setFont("Helvetica", font_row)
                        c.drawCentredString(x + cell_w / 2, y + row_h / 2 - font_row / 2 + 1, txt)
                    x += cell_w

            welfare_total = int(row.get("welfare_total") or 0)
            cohesion_total = int(row.get("cohesion_total") or 0)
            total_welfares = welfare_total + cohesion_total
            reimbursement = int(row.get("reimbursement") or 0)

            if mostrar_resumo:
                for valor, largura in ((total_welfares, total_welfares_w), (_fmt(reimbursement), reimbursement_w)):
                    c.setFillColor(colors.white)
                    c.rect(x, y, largura, row_h, fill=1, stroke=1)
                    c.setFillColor(colors.black)
                    c.setFont("Helvetica", font_row)
                    c.drawCentredString(x + largura / 2, y + row_h / 2 - font_row / 2 + 1, str(valor))
                    x += largura

        # Linha TOTAL DFAC
        y -= total_h
        if mostrar_identificacao:
            c.setFillColor(COR_TOTAL)
            c.rect(x0, y, ident_w, total_h, fill=1, stroke=1)
            c.setFillColor(COR_PRINCIPAL)
            c.setFont("Helvetica-Bold", font_total)
            c.drawString(x0 + 0.7 * mm, y + total_h / 2 - font_total / 2 + 1, "TOTAL DFAC")

        x = x0 + ident_w
        for dia_info in dias_pagina:
            dia = dia_info["dia"]
            data_key = dia_info.get("data_str", dia)
            vals = totais_dfac.get(data_key, totais_dfac.get(dia, {"pa": 0, "al": 0, "ja": 0}))
            for key in ("pa", "al", "ja"):
                c.setFillColor(COR_TOTAL)
                c.rect(x, y, cell_w, total_h, fill=1, stroke=1)
                c.setFillColor(COR_PRINCIPAL)
                c.setFont("Helvetica-Bold", font_total)
                c.drawCentredString(x + cell_w / 2, y + total_h / 2 - font_total / 2 + 1, str(vals.get(key, 0)))
                x += cell_w

        # Totais resumo
        if mostrar_resumo:
            for valor, largura in ((total_welfares_geral, total_welfares_w), (_fmt(total_reimbursement), reimbursement_w)):
                c.setFillColor(COR_TOTAL)
                c.rect(x, y, largura, total_h, fill=1, stroke=1)
                c.setFillColor(COR_PRINCIPAL)
                c.setFont("Helvetica-Bold", 4.4)
                c.drawCentredString(x + largura / 2, y + total_h / 2 - 1.5, str(valor))
                x += largura

        # Separadores verticais mais visíveis por dia:
        # esquerda do PA e direita do JA.
        c.setStrokeColor(COR_PRINCIPAL)
        c.setLineWidth(0.45)
        y_sep_top = y_data_top + header_h1 + header_h2
        y_sep_bottom = y
        for idx in range(len(dias_pagina) + 1):
            x_sep = x0 + ident_w + idx * cell_w * 3
            c.line(x_sep, y_sep_bottom, x_sep, y_sep_top)
        c.setStrokeColor(COR_LINHA)
        c.setLineWidth(0.10)

    for idx, dias_pagina in enumerate(paginas, start=1):
        if idx > 1:
            c.showPage()
        desenhar_pagina(dias_pagina, idx, len(paginas))

    c.save()
    return caminho_pdf

