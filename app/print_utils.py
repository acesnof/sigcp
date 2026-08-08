import os
import calendar
from app.i18n import weekdays_short
import platform
import subprocess
from datetime import datetime

from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.lib.utils import ImageReader

from app.config import (
    BASE_DIR,
    DOCS_DIR,
    COR_PRINCIPAL,
    COR_VERMELHO,
    COR_WEEKEND,
    COR_BRANCO,
    COR_LINHA,
    COR_LINHA_INTERNA,
    COR_AZUL_REFEICAO,
    COR_EMENTA,
    COR_OBS,
    MESES_PT,
    TIPOS_WELFARE,
)
from app.db import get_welfares_mes, get_day_offs_mes


PDF_DIR = os.path.join(BASE_DIR, "docs", "exports")
COR_REBORDO_WELFARE = "#b51618"
COR_SUPERFICIE_SUAVE = "#f4f8f8"
COR_TEXTO_SUAVE = "#587077"


def _hex_color(c):
    return c


def _draw_image(c, path, x, y, w, h):
    if not os.path.exists(path):
        return False
    try:
        c.drawImage(ImageReader(path), x, y, width=w, height=h, preserveAspectRatio=True, mask="auto")
        return True
    except Exception:
        return False


def _wrap_text(text, font_name, font_size, max_width):
    if not text:
        return []

    linhas = []
    for original in str(text).splitlines():
        words = original.split()
        if not words:
            linhas.append("")
            continue

        atual = ""
        for word in words:
            teste = word if not atual else f"{atual} {word}"
            if stringWidth(teste, font_name, font_size) <= max_width:
                atual = teste
            else:
                if atual:
                    linhas.append(atual)
                atual = word
        if atual:
            linhas.append(atual)

    return linhas


def _draw_wrapped(c, text, x, y_top, max_width, font_name, font_size, fill, line_gap=1.2, max_lines=None):
    linhas = _wrap_text(text, font_name, font_size, max_width)
    if max_lines is not None:
        linhas = linhas[:max_lines]

    c.setFillColor(fill)
    c.setFont(font_name, font_size)
    line_h = font_size + line_gap

    y = y_top
    for linha in linhas:
        c.drawString(x, y, linha)
        y -= line_h

    return y


def _texto_ementa(welfare):
    prato = (welfare.get("prato") or "").strip()
    sobremesa = (welfare.get("sobremesa") or "").strip()

    if prato and sobremesa:
        return f"{prato} / {sobremesa}"
    if prato:
        return prato
    if sobremesa:
        return sobremesa
    return ""


def _texto_local_team(welfare):
    """Representação compacta usada no calendário e no PDF mensal."""
    local = (welfare.get("local") or "").strip()
    team = (welfare.get("team_nome") or "").strip()
    return " · ".join(item for item in (local, team) if item)


def _draw_welfare_icons(c, welfare, right_x, top_y, icon_size, gap):
    ficheiros = TIPOS_WELFARE.get(welfare.get("tipo"), [])
    x = right_x - icon_size

    for ficheiro in reversed(ficheiros):
        path = os.path.join(DOCS_DIR, ficheiro)
        ok = _draw_image(c, path, x, top_y - icon_size + 2, icon_size, icon_size)
        if not ok:
            c.setFillColor(COR_VERMELHO)
            c.setFont("Helvetica-Bold", icon_size)
            c.drawCentredString(x + icon_size / 2, top_y - icon_size + 3, "*")
        x -= (icon_size + gap)


def _draw_welfare_block(c, welfare, x, y, width, height, compacto=False):
    refeicao = welfare["refeicao"].upper()

    titulo_size = 6.8 if compacto else 8.0
    obs_size = 5.4 if compacto else 6.4
    ementa_size = 5.4 if compacto else 6.5
    icon_size = 12.0 if compacto else 15.0
    padding = 4.0

    c.setFillColor(COR_BRANCO)
    c.setStrokeColor("#d5e1e3")
    c.setLineWidth(0.45)
    c.roundRect(x, y, width, height, 3.2, fill=1, stroke=1)

    titulo_y = y + height - (8.2 if compacto else 10.0)
    c.setFillColor(COR_AZUL_REFEICAO)
    c.setFont("Helvetica-Bold", titulo_size)
    c.drawString(x + padding, titulo_y, refeicao)

    _draw_welfare_icons(
        c,
        welfare,
        x + width - padding,
        y + height - 2,
        icon_size,
        2.5,
    )

    obs = (welfare.get("observacao") or "").strip()
    ementa = _texto_ementa(welfare)
    local_team = _texto_local_team(welfare)
    texto_y = titulo_y - (8.0 if compacto else 10.0)
    text_width = max(width - (padding * 2), 20)

    if local_team:
        texto_y = _draw_wrapped(
            c,
            local_team,
            x + padding,
            texto_y,
            text_width,
            "Helvetica-Bold",
            5.2 if compacto else 6.0,
            COR_PRINCIPAL,
            line_gap=0.5,
            max_lines=1,
        )
        texto_y -= 0.5 if compacto else 1.0

    if obs:
        texto_y = _draw_wrapped(
            c,
            obs,
            x + padding,
            texto_y,
            text_width,
            "Helvetica-Bold",
            obs_size,
            COR_OBS,
            line_gap=0.8,
            max_lines=1 if compacto else 2,
        )
        texto_y -= 0.5 if compacto else 1.2

    if ementa:
        _draw_wrapped(
            c,
            ementa,
            x + padding,
            texto_y,
            text_width,
            "Helvetica",
            ementa_size,
            COR_EMENTA,
            line_gap=0.7,
            max_lines=1 if compacto else 2,
        )


def _draw_day_cell(c, dia, welfares_dia, x, y, w, h, bg, is_day_off=False):
    c.setFillColor(bg)
    c.rect(x, y, w, h, fill=1, stroke=0)

    c.setStrokeColor(COR_LINHA)
    c.setLineWidth(0.35)
    c.rect(x, y, w, h, fill=0, stroke=1)

    if welfares_dia:
        c.setStrokeColor(COR_REBORDO_WELFARE)
        c.setLineWidth(1.15)
        c.rect(x + 0.8, y + 0.8, w - 1.6, h - 1.6, fill=0, stroke=1)

    c.setFillColor(COR_REBORDO_WELFARE if is_day_off else "#172b30")
    c.setFont("Helvetica-Bold" if welfares_dia or is_day_off else "Helvetica", 7.0)
    texto_dia = f"{dia} · DAY OFF" if is_day_off else str(dia)
    c.drawString(x + 3.8, y + h - 9.2, texto_dia)

    almoco = next((a for a in welfares_dia if a["refeicao"] == "Almoço"), None)
    jantar = next((a for a in welfares_dia if a["refeicao"] == "Jantar"), None)
    itens = [item for item in (almoco, jantar) if item]
    if not itens:
        return

    margem_x = 4.0
    content_y = y + 3.5
    content_h = h - 17.0
    gap = 2.5
    if len(itens) == 2:
        bloco_h = (content_h - gap) / 2
        _draw_welfare_block(
            c,
            itens[0],
            x + margem_x,
            content_y + bloco_h + gap,
            w - (margem_x * 2),
            bloco_h,
            compacto=True,
        )
        _draw_welfare_block(
            c,
            itens[1],
            x + margem_x,
            content_y,
            w - (margem_x * 2),
            bloco_h,
            compacto=True,
        )
    else:
        _draw_welfare_block(
            c,
            itens[0],
            x + margem_x,
            content_y,
            w - (margem_x * 2),
            content_h,
            compacto=False,
        )


def gerar_pdf_mes(ano, mes, output_path=None):
    nome_mes = MESES_PT[mes]
    if output_path is None:
        os.makedirs(PDF_DIR, exist_ok=True)
        output_path = os.path.join(PDF_DIR, f"SIGCP_{ano}_{mes:02d}.pdf")

    page_w, page_h = landscape(A4)
    margem = 5 * mm

    c = canvas.Canvas(output_path, pagesize=landscape(A4))
    c.setTitle(f"SIGCP - {nome_mes} {ano}")
    c.setAuthor("Contingente Português · EUTM RCA")

    left = margem
    bottom = margem
    usable_w = page_w - 2 * margem
    usable_h = page_h - 2 * margem

    sidebar_w = 20 * mm
    header_h = 14 * mm
    legenda_h = 13 * mm

    cal_x = left + sidebar_w
    cal_w = usable_w - sidebar_w
    cal_y = bottom + legenda_h
    cal_h = usable_h - header_h - legenda_h

    dados_mes = get_welfares_mes(ano, mes)
    day_offs_mes = get_day_offs_mes(ano, mes)
    total = sum(len(v) for v in dados_mes.values())

    # Fundo geral
    c.setFillColor(COR_BRANCO)
    c.rect(0, 0, page_w, page_h, fill=1, stroke=0)

    # Barra lateral
    c.setFillColor(COR_PRINCIPAL)
    c.rect(left, bottom, sidebar_w, usable_h, fill=1, stroke=0)

    year_h = 18 * mm
    c.setFillColor(COR_VERMELHO)
    c.rect(left, bottom + usable_h - year_h, sidebar_w, year_h, fill=1, stroke=0)
    c.setFillColor("white")
    c.setFont("Helvetica-Bold", 14)
    c.drawCentredString(left + sidebar_w / 2, bottom + usable_h - year_h / 2 - 4, str(ano))

    c.saveState()
    c.translate(left + sidebar_w / 2, bottom + usable_h / 2)
    c.rotate(90)
    c.setFont("Helvetica", 27)
    c.setFillColor("white")
    c.drawCentredString(0, -7, nome_mes.upper())
    c.restoreState()

    # Cabeçalho
    header_y = bottom + usable_h - header_h
    c.setFillColor(COR_BRANCO)
    c.rect(cal_x, header_y, cal_w, header_h, fill=1, stroke=0)
    c.setFillColor(COR_REBORDO_WELFARE)
    c.rect(cal_x, header_y, 1.5 * mm, header_h, fill=1, stroke=0)

    title_x = cal_x + 5 * mm
    c.setFillColor(COR_TEXTO_SUAVE)
    c.setFont("Helvetica-Bold", 5.8)
    c.drawString(
        title_x,
        header_y + header_h - 9,
        "CONTINGENTE PORTUGUÊS · EUTM RCA",
    )
    c.setFillColor(COR_PRINCIPAL)
    c.setFont("Helvetica-Bold", 11.5)
    c.drawString(title_x, header_y + 9, "PLANO MENSAL DE WELFARE")

    icon_path = os.path.join(DOCS_DIR, "cooking.png")
    total_text = f"TOTAL DE WELFARES  ·  {total}"
    total_font = 8.2
    total_icon = 14.0
    c.setFont("Helvetica-Bold", total_font)
    tw = stringWidth(total_text, "Helvetica-Bold", total_font)
    pill_w = tw + total_icon + 18
    pill_h = 8 * mm
    pill_x = cal_x + cal_w - pill_w - 5 * mm
    pill_y = header_y + (header_h - pill_h) / 2
    c.setFillColor(COR_SUPERFICIE_SUAVE)
    c.setStrokeColor("#cfe0e2")
    c.setLineWidth(0.5)
    c.roundRect(pill_x, pill_y, pill_w, pill_h, 6, fill=1, stroke=1)
    _draw_image(
        c,
        icon_path,
        pill_x + 6,
        pill_y + (pill_h - total_icon) / 2,
        total_icon,
        total_icon,
    )
    c.setFillColor(COR_PRINCIPAL)
    c.drawString(
        pill_x + total_icon + 11,
        pill_y + (pill_h - total_font) / 2 + 1,
        total_text,
    )

    # Cabeçalhos dos dias
    dias_semana = weekdays_short()
    head_h = 9 * mm
    cell_w = cal_w / 7
    grid_h = cal_h - head_h
    cell_h = grid_h / 6

    head_y = cal_y + grid_h
    for i, nome in enumerate(dias_semana):
        x = cal_x + i * cell_w
        c.setFillColor(COR_PRINCIPAL)
        c.rect(x, head_y, cell_w, head_h, fill=1, stroke=0)
        c.setStrokeColor("#3b6c71")
        c.setLineWidth(0.35)
        c.rect(x, head_y, cell_w, head_h, fill=0, stroke=1)
        c.setFillColor("white")
        c.setFont("Helvetica-Bold", 7.8)
        c.drawCentredString(x + cell_w / 2, head_y + head_h / 2 - 2.8, nome.upper())

    semanas = calendar.Calendar(firstweekday=0).monthdayscalendar(ano, mes)
    while len(semanas) < 6:
        semanas.append([0, 0, 0, 0, 0, 0, 0])

    for row_idx, semana in enumerate(semanas):
        y = cal_y + grid_h - (row_idx + 1) * cell_h
        for col_idx, dia in enumerate(semana):
            x = cal_x + col_idx * cell_w
            data_str = f"{ano}-{mes:02d}-{dia:02d}" if dia else ""
            is_day_off = bool(data_str and data_str in day_offs_mes)
            bg = COR_WEEKEND if (col_idx in [5, 6] or is_day_off) else COR_BRANCO
            if dia == 0:
                c.setFillColor(bg)
                c.rect(x, y, cell_w, cell_h, fill=1, stroke=0)
                c.setStrokeColor(COR_LINHA)
                c.setLineWidth(0.35)
                c.rect(x, y, cell_w, cell_h, fill=0, stroke=1)
            else:
                _draw_day_cell(c, dia, dados_mes.get(data_str, []), x, y, cell_w, cell_h, bg, is_day_off=is_day_off)

    # Legenda
    leg_y = bottom
    c.setFillColor(COR_BRANCO)
    c.rect(cal_x, leg_y, cal_w, legenda_h, fill=1, stroke=0)
    c.setStrokeColor(COR_LINHA)
    c.setLineWidth(0.35)
    c.rect(cal_x, leg_y, cal_w, legenda_h, fill=0, stroke=1)

    c.setFillColor(COR_PRINCIPAL)
    c.setFont("Helvetica-Bold", 7.5)
    legend_x = cal_x + 5 * mm
    legend_center_y = leg_y + legenda_h / 2
    c.drawString(legend_x, legend_center_y - 2.5, "LEGENDA")

    legenda = [
        ("Welfare", "cooking.png"),
        ("Aniversário", "cake.png"),
        ("Welfare Livre", "star.png"),
    ]

    item_x = legend_x + 18 * mm
    legend_font = 7.2
    legend_icon = 13.5
    c.setFont("Helvetica", legend_font)
    for texto, img in legenda:
        _draw_image(
            c,
            os.path.join(DOCS_DIR, img),
            item_x,
            legend_center_y - legend_icon / 2,
            legend_icon,
            legend_icon,
        )
        text_x = item_x + legend_icon + 4
        c.setFillColor("#263b40")
        c.drawString(text_x, legend_center_y - 2.4, texto)
        item_x = text_x + stringWidth(texto, "Helvetica", legend_font) + 14 * mm

    swatch = 11.5
    c.setFillColor(COR_WEEKEND)
    c.setStrokeColor("#bdd0d3")
    c.roundRect(
        item_x,
        legend_center_y - swatch / 2,
        swatch,
        swatch,
        2,
        fill=1,
        stroke=1,
    )
    c.setFillColor("#263b40")
    c.drawString(
        item_x + swatch + 5,
        legend_center_y - 2.4,
        "Fim de semana / Day Off",
    )

    c.showPage()
    c.save()

    return output_path


def imprimir_pdf(pdf_path):
    sistema = platform.system().lower()

    try:
        if sistema == "windows":
            os.startfile(pdf_path, "print")
            return True, "Enviado para impressão."
        if sistema == "darwin":
            subprocess.Popen(["open", pdf_path])
            return True, "PDF aberto para impressão."
        subprocess.Popen(["xdg-open", pdf_path])
        return True, "PDF aberto para impressão."
    except Exception as exc:
        return False, str(exc)
