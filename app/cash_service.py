"""Movimentos, saldos e relatório da Caixa do contingente."""

from datetime import date, datetime
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app import db


def _money(value):
    try:
        number = float(str(value).strip().replace(" ", "").replace(",", "."))
    except (TypeError, ValueError):
        raise ValueError("Indica um valor válido.")
    if number <= 0:
        raise ValueError("O valor tem de ser superior a zero.")
    return round(number, 2)


def _actor_name(user):
    rank = str(user.get("posto_portugal") or user.get("posto") or "").strip()
    return " ".join(filter(None, (rank, str(user.get("nome") or "").strip(), str(user.get("sobrenome") or "").strip()))).strip() or str(user.get("nim") or "")


def save(data, user, movement_id=None):
    kind = str(data.get("tipo") or "").strip().lower()
    if kind not in {"entrada", "saida"}:
        raise ValueError("Seleciona Entrada ou Saída.")
    try:
        movement_date = date.fromisoformat(str(data.get("data") or ""))
    except ValueError:
        raise ValueError("Indica uma data válida.")
    description = str(data.get("descritivo") or "").strip()
    if not description:
        raise ValueError("O descritivo é obrigatório.")
    amount = _money(data.get("valor"))
    person = str(data.get("pessoa_gasto") or "").strip() if kind == "saida" else ""
    place = str(data.get("local") or "").strip() if kind == "saida" else ""
    notes = str(data.get("observacoes") or "").strip()
    actor = _actor_name(user)
    if movement_id is None:
        return db.db_execute_return_id("""
            INSERT INTO caixa_movimentos (
                tipo, data, pessoa_gasto, local, valor, descritivo, observacoes,
                criado_por_id, criado_por_nome, atualizado_por_id, atualizado_por_nome
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (kind, movement_date.isoformat(), person, place, amount, description,
              notes, user.get("id"), actor, user.get("id"), actor))
    current = db.db_one("SELECT id FROM caixa_movimentos WHERE id=?", (movement_id,))
    if not current:
        raise ValueError("Movimento da Caixa não encontrado.")
    db.db_execute("""
        UPDATE caixa_movimentos SET tipo=?, data=?, pessoa_gasto=?, local=?,
            valor=?, descritivo=?, observacoes=?, atualizado_por_id=?,
            atualizado_por_nome=?, atualizado_em=CURRENT_TIMESTAMP
        WHERE id=?
    """, (kind, movement_date.isoformat(), person, place, amount, description,
          notes, user.get("id"), actor, movement_id))
    return int(movement_id)


def delete(movement_id):
    if not db.db_one("SELECT id FROM caixa_movimentos WHERE id=?", (movement_id,)):
        raise ValueError("Movimento da Caixa não encontrado.")
    db.db_execute("DELETE FROM caixa_movimentos WHERE id=?", (movement_id,))


def balance(start, end):
    start_text, end_text = str(start), str(end)
    opening = db.db_one("""
        SELECT COALESCE(SUM(CASE WHEN tipo='entrada' THEN valor ELSE -valor END), 0) AS saldo
        FROM caixa_movimentos WHERE data<?
    """, (start_text,))["saldo"]
    rows = db.db_rows("""
        SELECT * FROM caixa_movimentos WHERE data BETWEEN ? AND ?
        ORDER BY data, id
    """, (start_text, end_text))
    running = float(opening or 0)
    entries = exits = 0.0
    for row in rows:
        amount = float(row.get("valor") or 0)
        if row["tipo"] == "entrada":
            entries += amount
            running += amount
        else:
            exits += amount
            running -= amount
        row["saldo"] = round(running, 2)
    return {
        "inicio": start_text, "fim": end_text, "saldo_inicial": round(float(opening or 0), 2),
        "total_entradas": round(entries, 2), "total_saidas": round(exits, 2),
        "saldo_final": round(running, 2), "movimentos": rows,
    }


def dashboard_summary(today=None):
    today = today or date.today().isoformat()
    current = balance("0001-01-01", today)["saldo_final"]
    entries = db.db_rows("SELECT * FROM caixa_movimentos WHERE tipo='entrada' AND data<=? ORDER BY data DESC, id DESC LIMIT 3", (today,))
    exits = db.db_rows("SELECT * FROM caixa_movimentos WHERE tipo='saida' AND data<=? ORDER BY data DESC, id DESC LIMIT 3", (today,))
    return {"data": today, "saldo": current, "entradas": entries, "saidas": exits}


def generate_pdf(start, end, output_path):
    report = balance(start, end)
    styles = getSampleStyleSheet()
    normal = ParagraphStyle("cash-normal", parent=styles["Normal"], fontSize=7, leading=8.5)
    center = ParagraphStyle("cash-center", parent=normal, alignment=TA_CENTER)
    right = ParagraphStyle("cash-right", parent=normal, alignment=TA_RIGHT)
    title = ParagraphStyle("cash-title", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=13, textColor=colors.HexColor("#073f46"))
    eyebrow = ParagraphStyle("cash-eyebrow", parent=normal, fontName="Helvetica-Bold", fontSize=6, textColor=colors.HexColor("#587077"))
    doc = SimpleDocTemplate(output_path, pagesize=landscape(A4), leftMargin=10*mm, rightMargin=10*mm, topMargin=9*mm, bottomMargin=9*mm, title="Balanço da Caixa")
    header = Table([["", [Paragraph("CONTINGENTE PORTUGUÊS · EUTM RCA", eyebrow), Paragraph("BALANÇO DA CAIXA", title)], Paragraph(f"{start[8:10]}/{start[5:7]}/{start[:4]} — {end[8:10]}/{end[5:7]}/{end[:4]}", center)]], colWidths=[1.5*mm, 205.5*mm, 70*mm], rowHeights=[14*mm])
    header.setStyle(TableStyle([("BACKGROUND",(0,0),(0,0),colors.HexColor("#b51618")),("BACKGROUND",(2,0),(2,0),colors.HexColor("#f4f8f8")),("BOX",(2,0),(2,0),.5,colors.HexColor("#cfe0e2")),("VALIGN",(0,0),(-1,-1),"MIDDLE"),("LEFTPADDING",(1,0),(1,0),10)]))
    summary = Table([["SALDO INICIAL", "ENTRADAS", "SAÍDAS", f"SALDO EM {end[8:10]}/{end[5:7]}/{end[:4]}"], [f"{report['saldo_inicial']:,.2f} XAF", f"{report['total_entradas']:,.2f} XAF", f"{report['total_saidas']:,.2f} XAF", f"{report['saldo_final']:,.2f} XAF"]], colWidths=[69.25*mm]*4)
    summary.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#073f46")),("TEXTCOLOR",(0,0),(-1,0),colors.white),("FONTNAME",(0,0),(-1,-1),"Helvetica-Bold"),("ALIGN",(0,0),(-1,-1),"CENTER"),("GRID",(0,0),(-1,-1),.4,colors.HexColor("#cfe0e2")),("TOPPADDING",(0,0),(-1,-1),5),("BOTTOMPADDING",(0,0),(-1,-1),5)]))

    entries = [item for item in report["movimentos"] if item["tipo"] == "entrada"]
    exits = [item for item in report["movimentos"] if item["tipo"] == "saida"]

    def cells(item):
        if not item:
            return ["", "", "", "", ""]
        context = " · ".join(filter(None, [item.get("pessoa_gasto"), item.get("local")]))
        description = escape(item["descritivo"])
        if item.get("observacoes"):
            description += f"<br/><font color='#587077'>{escape(item['observacoes'])}</font>"
        registered = escape(item.get("criado_por_nome") or "")
        if item.get("criado_em"):
            registered += f"<br/><font color='#587077'>{escape(str(item['criado_em'])[:16].replace('T', ' '))}</font>"
        if item.get("atualizado_em") and item.get("atualizado_em") != item.get("criado_em"):
            registered += f"<br/><font color='#587077'>Editado: {escape(item.get('atualizado_por_nome') or '')} · {escape(str(item['atualizado_em'])[:16].replace('T', ' '))}</font>"
        return [
            Paragraph(f"{item['data'][8:10]}/{item['data'][5:7]}/{item['data'][:4]}", center),
            Paragraph(description, normal), Paragraph(escape(context), normal),
            Paragraph(registered, normal),
            Paragraph(f"{float(item['valor']):,.2f}", right),
        ]

    rows = [
        ["ENTRADAS", "", "", "", "", "SAÍDAS", "", "", "", ""],
        ["Data", "Descritivo", "Local", "Registado por", "Valor",
         "Data", "Descritivo", "Pessoa / Local", "Registado por", "Valor"],
    ]
    for index in range(max(1, len(entries), len(exits))):
        rows.append(cells(entries[index] if index < len(entries) else None) + cells(exits[index] if index < len(exits) else None))
    columns = Table(rows, colWidths=[18*mm, 41*mm, 33*mm, 30*mm, 16.5*mm] * 2, repeatRows=2)
    columns.setStyle(TableStyle([
        ("SPAN",(0,0),(4,0)), ("SPAN",(5,0),(9,0)),
        ("BACKGROUND",(0,0),(4,0),colors.HexColor("#278f73")),
        ("BACKGROUND",(5,0),(9,0),colors.HexColor("#c94c5b")),
        ("BACKGROUND",(0,1),(-1,1),colors.HexColor("#073f46")),
        ("TEXTCOLOR",(0,0),(-1,1),colors.white),
        ("FONTNAME",(0,0),(-1,1),"Helvetica-Bold"),
        ("ALIGN",(0,0),(-1,1),"CENTER"), ("VALIGN",(0,0),(-1,-1),"MIDDLE"),
        ("GRID",(0,1),(-1,-1),.35,colors.HexColor("#9db1b4")),
        ("ROWBACKGROUNDS",(0,2),(-1,-1),[colors.white,colors.HexColor("#f4f8f8")]),
        ("LINEBEFORE",(5,0),(5,-1),1.2,colors.white),
        ("LEFTPADDING",(0,0),(-1,-1),3), ("RIGHTPADDING",(0,0),(-1,-1),3),
        ("TOPPADDING",(0,0),(-1,-1),4), ("BOTTOMPADDING",(0,0),(-1,-1),4),
    ]))
    doc.build([header, Spacer(1,3*mm), summary, Spacer(1,4*mm), columns])
    return output_path
