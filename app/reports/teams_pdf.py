"""Relatório A4 da constituição atual das equipas de Welfare."""

import os
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

from app.config import APP_FULL_NAME, APP_NAME, DOCS_DIR


NAVY = colors.HexColor("#073f46")
TEAL = colors.HexColor("#0b5961")
TEAL_LIGHT = colors.HexColor("#dceff0")
GOLD = colors.HexColor("#f3c742")
PAPER = colors.HexColor("#f5f8f8")
LINE = colors.HexColor("#c3d4d5")
MUTED = colors.HexColor("#5f7477")


def _name(person):
    return " ".join(
        str(person.get(field) or "").strip()
        for field in ("posto_portugal", "nome", "sobrenome")
        if str(person.get(field) or "").strip()
    )


def _fit(text, width, font="Helvetica", size=8):
    text = str(text or "")
    if stringWidth(text, font, size) <= width:
        return text
    suffix = "..."
    while text and stringWidth(text + suffix, font, size) > width:
        text = text[:-1]
    return text + suffix


def _section_label(pdf, title, x, y, width):
    pdf.setFillColor(TEAL_LIGHT)
    pdf.roundRect(x, y - 7 * mm, width, 7 * mm, 2 * mm, fill=1, stroke=0)
    pdf.setFillColor(NAVY)
    pdf.setFont("Helvetica-Bold", 9)
    pdf.drawString(x + 3 * mm, y - 4.7 * mm, title.upper())
    return y - 10 * mm


def _draw_team_card(pdf, team, x, top, width, height):
    pdf.setFillColor(colors.white)
    pdf.setStrokeColor(LINE)
    pdf.setLineWidth(0.7)
    pdf.roundRect(x, top - height, width, height, 2.5 * mm, fill=1, stroke=1)
    header_h = 11 * mm
    pdf.setFillColor(TEAL)
    pdf.roundRect(x, top - header_h, width, header_h, 2.5 * mm, fill=1, stroke=0)
    pdf.rect(x, top - header_h, width, 3 * mm, fill=1, stroke=0)
    pdf.setFillColor(colors.white)
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawCentredString(x + width / 2, top - 7.2 * mm, _fit(team["nome"], width - 8 * mm, "Helvetica-Bold", 11))

    members = team.get("membros", [])
    available_h = height - header_h - 5 * mm
    row_h = min(8 * mm, available_h / max(1, len(members)))
    font_size = max(7, min(10, row_h / mm * 1.45))
    if not members:
        pdf.setFillColor(MUTED)
        pdf.setFont("Helvetica-Oblique", 9)
        pdf.drawCentredString(x + width / 2, top - header_h - 9 * mm, "Sem elementos")
        return
    for index, member in enumerate(members):
        row_top = top - header_h - index * row_h
        if index % 2:
            pdf.setFillColor(PAPER)
            pdf.rect(x + 0.5, row_top - row_h, width - 1, row_h, fill=1, stroke=0)
        if index:
            pdf.setStrokeColor(LINE)
            pdf.line(x + 3 * mm, row_top, x + width - 3 * mm, row_top)
        pdf.setFillColor(NAVY)
        pdf.setFont("Helvetica-Bold", font_size)
        pdf.drawString(x + 4 * mm, row_top - row_h * 0.67, f"{index + 1:02d}")
        pdf.setFillColor(colors.black)
        pdf.setFont("Helvetica", font_size)
        pdf.drawString(x + 13 * mm, row_top - row_h * 0.67, _fit(_name(member), width - 18 * mm, size=font_size))


def generate_pdf(output_path, teams, cooks, vacations, printed_at=None):
    """Cria uma única página A4 horizontal no tema visual do SIGCP."""
    printed_at = printed_at or datetime.now()
    pdf = canvas.Canvas(output_path, pagesize=landscape(A4))
    width, height = landscape(A4)
    margin = 11 * mm
    usable = width - 2 * margin

    pdf.setTitle(f"{APP_NAME} - Constituição atual das equipas de Welfare")
    pdf.setAuthor(APP_NAME)
    pdf.setFillColor(PAPER)
    pdf.rect(0, 0, width, height, fill=1, stroke=0)
    header_h = 32 * mm
    pdf.setFillColor(NAVY)
    pdf.rect(0, height - header_h, width, header_h, fill=1, stroke=0)
    pdf.setFillColor(GOLD)
    pdf.rect(0, height - header_h, width, 1.4 * mm, fill=1, stroke=0)
    logo_path = os.path.join(DOCS_DIR, "logo_eutm_rca_prt.png")
    if os.path.isfile(logo_path):
        pdf.drawImage(logo_path, margin, height - 27 * mm, width=22 * mm, height=22 * mm, mask="auto", preserveAspectRatio=True)
    title_x = margin + 28 * mm
    pdf.setFillColor(GOLD)
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(title_x, height - 11 * mm, APP_NAME)
    pdf.setFillColor(colors.white)
    pdf.setFont("Helvetica-Bold", 17)
    pdf.drawString(title_x, height - 19 * mm, "CONSTITUIÇÃO ATUAL DAS EQUIPAS")
    pdf.setFillColor(colors.HexColor("#c7e1e3"))
    pdf.setFont("Helvetica", 7.5)
    pdf.drawString(title_x, height - 25 * mm, APP_FULL_NAME)

    y = _section_label(pdf, "Equipa de Cozinheiros", margin, height - header_h - 6 * mm, usable)
    cook_text = "  |  ".join(_name(person) for person in cooks) or "Sem cozinheiros nomeados."
    pdf.setFillColor(colors.white)
    pdf.setStrokeColor(LINE)
    pdf.roundRect(margin, y - 9 * mm, usable, 10 * mm, 2 * mm, fill=1, stroke=1)
    pdf.setFillColor(NAVY if cooks else MUTED)
    cook_font = "Helvetica-Bold" if cooks else "Helvetica-Oblique"
    pdf.setFont(cook_font, 10)
    pdf.drawCentredString(width / 2, y - 5.5 * mm, _fit(cook_text, usable - 8 * mm, cook_font, 10))

    teams_top = y - 15 * mm
    team_count = max(1, len(teams))
    columns = min(3, team_count)
    rows_count = (team_count + columns - 1) // columns
    gap = 5 * mm
    cards_width = min(usable, columns * 82 * mm + (columns - 1) * gap)
    card_width = (cards_width - (columns - 1) * gap) / columns
    cards_x = (width - cards_width) / 2
    vacations_h = 35 * mm
    cards_bottom = margin + vacations_h + 9 * mm
    cards_area_h = teams_top - cards_bottom
    card_height = (cards_area_h - (rows_count - 1) * gap) / rows_count
    if teams:
        for index, team in enumerate(teams):
            row, col = divmod(index, columns)
            _draw_team_card(pdf, team, cards_x + col * (card_width + gap), teams_top - row * (card_height + gap), card_width, card_height)
    else:
        pdf.setFillColor(colors.white)
        pdf.setStrokeColor(LINE)
        pdf.roundRect(cards_x, teams_top - 25 * mm, cards_width, 25 * mm, 2.5 * mm, fill=1, stroke=1)
        pdf.setFillColor(MUTED)
        pdf.setFont("Helvetica-Oblique", 10)
        pdf.drawCentredString(width / 2, teams_top - 14 * mm, "Ainda não existem Teams.")

    vacation_y = _section_label(pdf, "Férias em curso e futuras do contingente", margin, margin + vacations_h, usable)
    if vacations:
        vacation_col = usable / 3
        vacation_rows = (len(vacations) + 2) // 3
        vacation_height = min(5 * mm, 23 * mm / max(1, vacation_rows))
        vacation_font = max(6.2, min(8.2, vacation_height / mm * 1.45))
        for index, item in enumerate(vacations):
            col, row = index // vacation_rows, index % vacation_rows
            x = margin + col * vacation_col + 2 * mm
            line = f"{_name(item)}  |  {item['inicio']} - {item['fim']}"
            pdf.setFillColor(colors.black)
            pdf.setFont("Helvetica", vacation_font)
            pdf.drawString(x, vacation_y - row * vacation_height, _fit(line, vacation_col - 5 * mm, size=vacation_font))
    else:
        pdf.setFillColor(MUTED)
        pdf.setFont("Helvetica-Oblique", 8.5)
        pdf.drawString(margin + 2 * mm, vacation_y, "Não existem períodos de férias em curso ou futuros registados.")

    pdf.setFillColor(MUTED)
    pdf.setFont("Helvetica", 7)
    pdf.drawString(margin, 5 * mm, f"Impresso em {printed_at.strftime('%d/%m/%Y às %H:%M')}")
    pdf.drawRightString(width - margin, 5 * mm, f"{APP_NAME} | documento gerado automaticamente | 1/1")
    pdf.showPage()
    pdf.save()
