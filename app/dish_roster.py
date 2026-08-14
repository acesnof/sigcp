"""Escala de apoio à loiça aos fins de semana."""

import calendar
from datetime import date, datetime, timedelta
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app import db
from app.config import MESES_PT, POSTOS
from app.person_order import person_order_key
from app.vacation_service import APPROVED_STATUSES


LOW_RANK_ORDER = {rank: index for index, rank in enumerate(reversed(["OF-6", *POSTOS]))}


def _identificacao(person):
    return " ".join(
        part for part in (
            str(person.get("posto") or "").strip(),
            str(person.get("nome") or "").strip(),
            str(person.get("sobrenome") or "").strip(),
        ) if part
    )


def _date_text(value):
    return str(value or "").strip()[:10]


def _date_or_none(value):
    try:
        return date.fromisoformat(_date_text(value))
    except ValueError:
        return None


def range_dates(year, month):
    start = date(int(year), int(month), 1)
    end_month_index = start.month - 1 + 3
    end_year = start.year + end_month_index // 12
    end_month = end_month_index % 12 + 1
    end = date(end_year, end_month, calendar.monthrange(end_year, end_month)[1])
    return start, end


def weekends(year, month):
    start, end = range_dates(year, month)
    saturday = start + timedelta(days=(5 - start.weekday()) % 7)
    result = []
    while saturday <= end:
        result.append((saturday, saturday + timedelta(days=1)))
        saturday += timedelta(days=7)
    return result


def ensure_rows(year, month):
    for saturday, _sunday in weekends(year, month):
        db.db_execute(
            "INSERT OR IGNORE INTO escala_loica (fim_semana) VALUES (?)",
            (saturday.isoformat(),),
        )


def _people(*, include_departed=False):
    if include_departed:
        return db.db_rows("SELECT * FROM utilizadores WHERE master=0")
    today = date.today().isoformat()
    return db.db_rows("""
        SELECT * FROM utilizadores
        WHERE master=0
          AND COALESCE(data_chegada, '')<>''
          AND (
              COALESCE(data_partida, '')=''
              OR SUBSTR(data_partida, 1, 10)>=?
          )
    """, (today,))


def _vacations(start, end):
    states = tuple(APPROVED_STATUSES)
    placeholders = ",".join("?" for _ in states)
    return db.db_rows(f"""
        SELECT f.utilizador_id, f.data_hora_inicio, f.data_hora_fim,
               u.posto, u.posto_portugal, u.nome, u.sobrenome
        FROM ferias f JOIN utilizadores u ON u.id=f.utilizador_id
        WHERE u.master=0 AND f.estado IN ({placeholders})
          AND SUBSTR(f.data_hora_inicio, 1, 10)<=?
          AND SUBSTR(f.data_hora_fim, 1, 10)>=?
        ORDER BY f.data_hora_inicio
    """, (*states, end.isoformat(), start.isoformat()))


def _available(person, saturday, vacation_rows):
    arrival = _date_or_none(person.get("data_chegada"))
    departure = _date_or_none(person.get("data_partida"))
    if not arrival or saturday < arrival + timedelta(days=6):
        return False
    if departure and departure <= saturday:
        return False
    sunday = saturday + timedelta(days=1)
    for period in vacation_rows:
        if int(period["utilizador_id"]) != int(person["id"]):
            continue
        beginning = _date_or_none(period.get("data_hora_inicio"))
        ending = _date_or_none(period.get("data_hora_fim"))
        if beginning and ending and beginning <= sunday and ending >= saturday:
            return False
    return True


def _generation_order(person):
    arrival = str(person.get("data_chegada") or "").strip().replace("T", " ") or "9999-12-31 23:59"
    rank = LOW_RANK_ORDER.get(str(person.get("posto") or "").strip().upper(), 999)
    antiquity = _date_text(person.get("antiguidade")) or "9999-12-31"
    return arrival, rank, antiquity, str(person.get("sobrenome") or "").casefold()


def generate(year, month, rebuild_forecast=False):
    """Refaz a previsão pela folga apurada nos serviços validados."""
    ensure_rows(year, month)
    start, end = range_dates(year, month)
    people = sorted(_people(), key=_generation_order)
    people_by_id = {int(item["id"]): item for item in people}
    vacations = _vacations(start, end + timedelta(days=1))
    rows = db.db_rows(
        "SELECT * FROM escala_loica WHERE fim_semana BETWEEN ? AND ? ORDER BY fim_semana",
        (start.isoformat(), end.isoformat()),
    )
    previous = db.db_one("""
        SELECT * FROM escala_loica
        WHERE validada=1
        ORDER BY fim_semana DESC LIMIT 1
    """)

    # A folga nasce apenas de serviços efetivamente validados. Quem nunca fez
    # serviço tem prioridade sobre quem já fez.
    last_service = {person_id: None for person_id in people_by_id}
    if previous:
        history = db.db_rows("""
            SELECT fim_semana, militar_1_id, militar_2_id
            FROM escala_loica
            WHERE validada=1 AND fim_semana<=?
            ORDER BY fim_semana
        """, (previous["fim_semana"],))
        for service in history:
            service_date = date.fromisoformat(service["fim_semana"])
            for person_id in (service.get("militar_1_id"), service.get("militar_2_id")):
                if person_id and int(person_id) in last_service:
                    last_service[int(person_id)] = service_date

    def rested_order(person):
        person_id = int(person["id"])
        last = last_service[person_id]
        return (last is not None, last or date.min, _generation_order(person))

    for row in rows:
        saturday = date.fromisoformat(row["fim_semana"])
        if int(row.get("validada") or 0):
            continue
        if previous and row["fim_semana"] <= previous["fim_semana"]:
            continue
        if not rebuild_forecast and int(row.get("manual") or 0):
            selected = [
                int(person_id) for person_id in (
                    row.get("militar_1_id"), row.get("militar_2_id")
                ) if person_id and int(person_id) in people_by_id
                and _available(people_by_id[int(person_id)], saturday, vacations)
            ]
            if selected:
                selected += [None] * (2 - len(selected))
                db.db_execute("""
                    UPDATE escala_loica SET militar_1_id=?, militar_2_id=?,
                        assinatura_1=0, assinatura_2=0, atualizado_em=CURRENT_TIMESTAMP
                    WHERE fim_semana=? AND validada=0
                """, (selected[0], selected[1], row["fim_semana"]))
                for person_id in selected:
                    if person_id:
                        last_service[person_id] = saturday
                continue
            # Corrige linhas vazias que versões anteriores marcaram como manuais.
            db.db_execute(
                "UPDATE escala_loica SET manual=0 WHERE fim_semana=? AND validada=0",
                (row["fim_semana"],),
            )

        eligible = [
            person for person in people
            if _available(person, saturday, vacations)
        ]
        selected = [
            int(person["id"])
            for person in sorted(eligible, key=rested_order)[:2]
        ]
        for person_id in selected:
            last_service[person_id] = saturday
        selected += [None] * (2 - len(selected))
        db.db_execute("""
            UPDATE escala_loica SET militar_1_id=?, militar_2_id=?,
                assinatura_1=0, assinatura_2=0, manual=0,
                atualizado_em=CURRENT_TIMESTAMP
            WHERE fim_semana=? AND validada=0
        """, (selected[0], selected[1], row["fim_semana"]))
    return payload(year, month)


def save_rows(year, month, values):
    ensure_rows(year, month)
    allowed = {item[0].isoformat() for item in weekends(year, month)}
    people = {int(item["id"]): item for item in _people()}
    start, end = range_dates(year, month)
    vacations = _vacations(start, end + timedelta(days=1))
    for item in values:
        weekend = str(item.get("fim_semana") or "")
        if weekend not in allowed:
            raise ValueError("Fim de semana inválido.")
        current = db.db_one("SELECT * FROM escala_loica WHERE fim_semana=?", (weekend,))
        if current and int(current.get("validada") or 0):
            raise ValueError("Uma linha validada não pode ser alterada.")
        chosen = []
        for key in ("militar_1_id", "militar_2_id"):
            raw = item.get(key)
            person_id = int(raw) if raw not in (None, "") else None
            if person_id:
                person = people.get(person_id)
                if not person or not _available(person, date.fromisoformat(weekend), vacations):
                    raise ValueError("A pessoa selecionada não está disponível neste fim de semana.")
            chosen.append(person_id)
        if chosen[0] and chosen[0] == chosen[1]:
            raise ValueError("Seleciona duas pessoas diferentes.")
        db.db_execute("""
            UPDATE escala_loica SET militar_1_id=?, militar_2_id=?, manual=?,
                assinatura_1=0, assinatura_2=0, atualizado_em=CURRENT_TIMESTAMP
            WHERE fim_semana=? AND validada=0
        """, (chosen[0], chosen[1], 1 if any(chosen) else 0, weekend))
    return payload(year, month)


def set_validation(weekend, validated):
    db.db_execute(
        "UPDATE escala_loica SET validada=?, atualizado_em=CURRENT_TIMESTAMP WHERE fim_semana=?",
        (1 if validated else 0, weekend),
    )


def set_signature(weekend, slot, signed):
    column = "assinatura_1" if int(slot) == 1 else "assinatura_2"
    db.db_execute(
        f"UPDATE escala_loica SET {column}=?, atualizado_em=CURRENT_TIMESTAMP WHERE fim_semana=?",
        (1 if signed else 0, weekend),
    )


def get_row(weekend):
    return db.db_one("SELECT * FROM escala_loica WHERE fim_semana=?", (weekend,))


def payload(year, month, current_user_id=None, manager=False, administrator=False):
    ensure_rows(year, month)
    start, end = range_dates(year, month)
    selectable_people = _people()
    all_people = _people(include_departed=True)
    people_by_id = {int(item["id"]): item for item in all_people}
    vacations = _vacations(start, end + timedelta(days=1))
    rows = db.db_rows("""
        SELECT * FROM escala_loica
        WHERE fim_semana BETWEEN ? AND ? ORDER BY fim_semana
    """, (start.isoformat(), end.isoformat()))
    result = []
    today = date.today()
    for row in rows:
        saturday = date.fromisoformat(row["fim_semana"])
        sunday = saturday + timedelta(days=1)
        observations = []
        for period in vacations:
            beginning = _date_or_none(period.get("data_hora_inicio"))
            ending = _date_or_none(period.get("data_hora_fim"))
            if beginning and ending and beginning <= sunday and ending >= saturday:
                observations.append({
                    "identificacao": _identificacao(period),
                    "inicio": _date_text(period["data_hora_inicio"]),
                    "fim": _date_text(period["data_hora_fim"]),
                })
        person1 = people_by_id.get(int(row["militar_1_id"])) if row.get("militar_1_id") else None
        person2 = people_by_id.get(int(row["militar_2_id"])) if row.get("militar_2_id") else None
        result.append({
            **row,
            "domingo": sunday.isoformat(),
            "militar_1": _identificacao(person1 or {}),
            "militar_2": _identificacao(person2 or {}),
            "observacoes": observations,
            "pode_assinar_1": bool(administrator or (
                today == saturday and (
                    manager or (person1 and int(person1["id"]) == int(current_user_id or 0))
                )
            )),
            "pode_assinar_2": bool(administrator or (
                today == saturday and (
                    manager or (person2 and int(person2["id"]) == int(current_user_id or 0))
                )
            )),
        })
    public_people = sorted(selectable_people, key=person_order_key)
    return {
        "ano": int(year), "mes": int(month), "inicio": start.isoformat(),
        "fim": end.isoformat(), "gestor": bool(manager), "linhas": result,
        "pessoas": [
            {"id": item["id"], "identificacao": _identificacao(item)}
            for item in public_people
        ],
    }


def generate_pdf(year, month, output_path):
    data = payload(year, month)
    # A consulta no ecrã mantém quatro meses; a impressão usa apenas três para
    # dar mais altura às assinaturas e às observações em uma única folha A4.
    third_month_index = int(month) - 1 + 2
    third_year = int(year) + third_month_index // 12
    third_month = third_month_index % 12 + 1
    pdf_end = date(
        third_year,
        third_month,
        calendar.monthrange(third_year, third_month)[1],
    ).isoformat()
    data["linhas"] = [
        row for row in data["linhas"] if row["fim_semana"] <= pdf_end
    ]
    styles = getSampleStyleSheet()
    small = ParagraphStyle("dish-small", parent=styles["Normal"], fontSize=7.2, leading=8.7)
    center = ParagraphStyle("dish-center", parent=small, alignment=TA_CENTER)
    eyebrow = ParagraphStyle(
        "dish-header-eyebrow", parent=styles["Normal"], fontName="Helvetica-Bold",
        fontSize=5.8, leading=7, textColor=colors.HexColor("#587077"),
        spaceAfter=1.5,
    )
    heading = ParagraphStyle(
        "dish-header-title", parent=styles["Normal"], fontName="Helvetica-Bold",
        fontSize=11.5, leading=13, textColor=colors.HexColor("#073f46"),
    )
    summary = ParagraphStyle(
        "dish-header-summary", parent=styles["Normal"], fontName="Helvetica-Bold",
        fontSize=7.2, leading=9, alignment=TA_CENTER,
        textColor=colors.HexColor("#073f46"),
    )
    doc = SimpleDocTemplate(
        output_path, pagesize=landscape(A4), leftMargin=10 * mm,
        rightMargin=10 * mm, topMargin=10 * mm, bottomMargin=10 * mm,
        title="Escala Loiça - Fim de Semana",
    )
    first_month = MESES_PT[int(month)].upper()
    last_month = MESES_PT[third_month].upper()
    period = (
        f"{first_month} {int(year)} — {last_month} {third_year}<br/>"
        f"{len(data['linhas'])} FINS DE SEMANA"
    )
    header = Table(
        [[
            "",
            [
                Paragraph("CONTINGENTE PORTUGUÊS · EUTM RCA", eyebrow),
                Paragraph("ESCALA LOIÇA · FIM DE SEMANA", heading),
            ],
            Paragraph(period, summary),
        ]],
        colWidths=[1.5 * mm, 205.5 * mm, 70 * mm],
        rowHeights=[14 * mm],
    )
    header.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, 0), colors.HexColor("#b51618")),
        ("BACKGROUND", (1, 0), (1, 0), colors.white),
        ("BACKGROUND", (2, 0), (2, 0), colors.HexColor("#f4f8f8")),
        ("BOX", (2, 0), (2, 0), 0.5, colors.HexColor("#cfe0e2")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (0, 0), 0),
        ("RIGHTPADDING", (0, 0), (0, 0), 0),
        ("LEFTPADDING", (1, 0), (1, 0), 10),
        ("RIGHTPADDING", (1, 0), (1, 0), 6),
        ("LEFTPADDING", (2, 0), (2, 0), 6),
        ("RIGHTPADDING", (2, 0), (2, 0), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story = [header, Spacer(1, 3 * mm)]
    table_data = [[
        "Fim de Semana", "Militar 1", "Assinatura 1",
        "Militar 2", "Assinatura 2", "Observações",
    ]]
    for row in data["linhas"]:
        observations = "<br/>".join(
            f"Férias: {escape(item['identificacao'])} ({item['inicio'][8:10]}/{item['inicio'][5:7]}/{item['inicio'][:4]}–{item['fim'][8:10]}/{item['fim'][5:7]}/{item['fim'][:4]})"
            for item in row["observacoes"]
        )
        weekend_text = (
            f"Sábado {row['fim_semana'][8:10]}/{row['fim_semana'][5:7]}/{row['fim_semana'][:4]}<br/>"
            f"Domingo {row['domingo'][8:10]}/{row['domingo'][5:7]}/{row['domingo'][:4]}"
        )
        table_data.append([
            Paragraph(weekend_text, center), Paragraph(escape(row["militar_1"] or ""), center),
            Paragraph("Registado" if row["assinatura_1"] else "", center),
            Paragraph(escape(row["militar_2"] or ""), center),
            Paragraph("Registado" if row["assinatura_2"] else "", center),
            Paragraph(observations, small),
        ])
    table = Table(
        table_data, repeatRows=1,
        colWidths=[31 * mm, 46 * mm, 30 * mm, 46 * mm, 30 * mm, 84 * mm],
        rowHeights=[9 * mm] + [max(8 * mm, 150 * mm / max(1, len(data["linhas"]))) for _ in data["linhas"]],
    )
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0b4b52")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 8),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (5, 1), (5, -1), "LEFT"),
        ("GRID", (0, 0), (-1, -1), 0.55, colors.HexColor("#5f7479")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f4f8f8")]),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(table)
    doc.build(story)
    return output_path
