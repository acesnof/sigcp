"""Regras e fluxos da área integrada de férias.

O registo principal continua a ser ``ferias``. Um pedido de alteração ou de
cancelamento guarda a proposta em colunas próprias, mantendo o período já
aprovado ativo até existir uma decisão. É esta garantia que permite ao Welfare
Individual refletir apenas ausências autorizadas sem perder o histórico.
"""

import calendar
import json
import math
from datetime import date, datetime, timedelta

from app import db
from app.person_order import (
    person_order_key,
    person_still_in_mission as member_still_in_mission,
)


STATUS_PENDING = "Pendente"
STATUS_APPROVED = "Aprovado"
STATUS_CHANGE_PENDING = "Alteração pendente"
STATUS_CANCEL_PENDING = "Cancelamento pendente"
STATUS_REJECTED = "Rejeitado"
STATUS_RETURNED = "Devolvido"
STATUS_ANNULLED = "Anulado"

ALL_STATUSES = (
    STATUS_PENDING,
    STATUS_APPROVED,
    STATUS_CHANGE_PENDING,
    STATUS_CANCEL_PENDING,
    STATUS_REJECTED,
    STATUS_RETURNED,
    STATUS_ANNULLED,
)
PLANNING_STATUSES = {
    STATUS_PENDING,
    STATUS_APPROVED,
    STATUS_CHANGE_PENDING,
    STATUS_CANCEL_PENDING,
}
PLANNING_STATUS_ORDER = (
    STATUS_PENDING,
    STATUS_APPROVED,
    STATUS_CHANGE_PENDING,
    STATUS_CANCEL_PENDING,
)
APPROVED_STATUSES = {
    STATUS_APPROVED,
    STATUS_CHANGE_PENDING,
    STATUS_CANCEL_PENDING,
}
ACTIONABLE_STATUSES = {
    STATUS_PENDING,
    STATUS_CHANGE_PENDING,
    STATUS_CANCEL_PENDING,
}
STATUS_FILTER_GROUPS = {
    "all": tuple(ALL_STATUSES),
    "pending": (
        STATUS_PENDING,
        STATUS_CHANGE_PENDING,
        STATUS_CANCEL_PENDING,
    ),
    "approved": (STATUS_APPROVED,),
    "annulled": (STATUS_ANNULLED,),
}
STATUS_FILTER_TITLES = {
    "all": "Lista de licenças",
    "pending": "Licenças pendentes de aprovação",
    "approved": "Licenças aprovadas",
    "annulled": "Licenças anuladas",
}

DEFAULT_SETTINGS = {
    "dias_por_mes": 2.5,
    "max_dias_ausencia": 21,
    "max_percentagem_area": 20,
    "hora_limite_chegada": "08:00",
    "dias_bloqueio_missao": 30,
    "max_periodos": 3,
    "modo_limite_area": "warning",
    "ano_calendario": date.today().year,
}

SETTING_KEYS = {
    "dias_por_mes": "ferias_dias_por_mes",
    "max_dias_ausencia": "ferias_max_dias_ausencia",
    "max_percentagem_area": "ferias_max_percentagem_area",
    "hora_limite_chegada": "ferias_hora_limite_chegada",
    "dias_bloqueio_missao": "ferias_dias_bloqueio_missao",
    "max_periodos": "ferias_max_periodos",
    "modo_limite_area": "ferias_modo_limite_area",
    "ano_calendario": "ferias_ano_calendario",
}


class VacationValidationError(ValueError):
    def __init__(self, message, *, errors=None, warnings=None, breakdown=None):
        super().__init__(message)
        self.errors = errors or []
        self.warnings = warnings or []
        self.breakdown = breakdown


def now_db():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def normalise_datetime(value):
    text_value = str(value or "").strip().replace("T", " ")
    for fmt, length in (("%Y-%m-%d %H:%M", 16), ("%Y-%m-%d %H:%M:%S", 19)):
        try:
            return datetime.strptime(text_value[:length], fmt).strftime("%Y-%m-%d %H:%M")
        except ValueError:
            continue
    raise VacationValidationError("Indica uma data e hora válidas.")


def parse_datetime(value):
    return datetime.strptime(normalise_datetime(value), "%Y-%m-%d %H:%M")


def _number(value, fallback, *, integer=False):
    try:
        result = float(str(value).replace(",", "."))
        return int(result) if integer else result
    except (TypeError, ValueError):
        return fallback


def get_settings():
    keys = tuple(SETTING_KEYS.values())
    placeholders = ",".join("?" for _ in keys)
    stored = {
        row["chave"]: row["valor"]
        for row in db.db_rows(
            f"SELECT chave, valor FROM app_settings WHERE chave IN ({placeholders})",
            keys,
        )
    }

    def setting(name):
        value = stored.get(SETTING_KEYS[name])
        return DEFAULT_SETTINGS[name] if value is None else value

    result = dict(DEFAULT_SETTINGS)
    result["dias_por_mes"] = _number(
        setting("dias_por_mes"),
        DEFAULT_SETTINGS["dias_por_mes"],
    )
    result["max_dias_ausencia"] = _number(
        setting("max_dias_ausencia"),
        DEFAULT_SETTINGS["max_dias_ausencia"],
        integer=True,
    )
    result["max_percentagem_area"] = _number(
        setting("max_percentagem_area"),
        DEFAULT_SETTINGS["max_percentagem_area"],
    )
    result["dias_bloqueio_missao"] = _number(
        setting("dias_bloqueio_missao"),
        DEFAULT_SETTINGS["dias_bloqueio_missao"],
        integer=True,
    )
    result["max_periodos"] = _number(
        setting("max_periodos"),
        DEFAULT_SETTINGS["max_periodos"],
        integer=True,
    )
    result["ano_calendario"] = _number(
        setting("ano_calendario"),
        DEFAULT_SETTINGS["ano_calendario"],
        integer=True,
    )
    cutoff = str(setting("hora_limite_chegada")).strip()
    try:
        datetime.strptime(cutoff, "%H:%M")
    except ValueError:
        cutoff = DEFAULT_SETTINGS["hora_limite_chegada"]
    result["hora_limite_chegada"] = cutoff
    mode = str(setting("modo_limite_area"))
    result["modo_limite_area"] = mode if mode in ("warning", "block") else "warning"
    return result


def save_settings(values):
    result = {
        "dias_por_mes": _number(values.get("dias_por_mes"), -1),
        "max_dias_ausencia": _number(values.get("max_dias_ausencia"), -1, integer=True),
        "max_percentagem_area": _number(values.get("max_percentagem_area"), -1),
        "dias_bloqueio_missao": _number(values.get("dias_bloqueio_missao"), -1, integer=True),
        "max_periodos": _number(values.get("max_periodos"), -1, integer=True),
        "ano_calendario": _number(values.get("ano_calendario"), -1, integer=True),
        "hora_limite_chegada": str(values.get("hora_limite_chegada") or "").strip(),
        "modo_limite_area": str(values.get("modo_limite_area") or "").strip(),
    }
    if not 0 < result["dias_por_mes"] <= 10:
        raise VacationValidationError("Os dias de férias por mês devem estar entre 0 e 10.")
    if not 1 <= result["max_dias_ausencia"] <= 180:
        raise VacationValidationError("O limite de ausência deve estar entre 1 e 180 dias.")
    if not 0 < result["max_percentagem_area"] <= 100:
        raise VacationValidationError("A percentagem máxima deve estar entre 0 e 100.")
    if not 0 <= result["dias_bloqueio_missao"] <= 180:
        raise VacationValidationError("O bloqueio da missão deve estar entre 0 e 180 dias.")
    if not 1 <= result["max_periodos"] <= 12:
        raise VacationValidationError("O máximo de períodos deve estar entre 1 e 12.")
    if not 2000 <= result["ano_calendario"] <= 2200:
        raise VacationValidationError("Indica um ano de calendário válido.")
    try:
        datetime.strptime(result["hora_limite_chegada"], "%H:%M")
    except ValueError as exc:
        raise VacationValidationError("A hora limite deve estar no formato HH:MM.") from exc
    if result["modo_limite_area"] not in ("warning", "block"):
        raise VacationValidationError("Seleciona um modo válido para o limite da área.")
    conn = db._connect()
    try:
        conn.executemany(
            """
            INSERT INTO app_settings (chave, valor, atualizado_em)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(chave)
            DO UPDATE SET valor=excluded.valor, atualizado_em=CURRENT_TIMESTAMP
            """,
            [(SETTING_KEYS[key], str(value)) for key, value in result.items()],
        )
        conn.commit()
    finally:
        conn.close()
    return get_settings()


def get_holidays(*, year=None, active_only=False):
    where = []
    params = []
    if year:
        where.append("SUBSTR(data, 1, 4) = ?")
        params.append(str(int(year)))
    if active_only:
        where.append("ativo = 1")
    clause = f"WHERE {' AND '.join(where)}" if where else ""
    return db.db_rows(
        f"SELECT * FROM feriados {clause} ORDER BY data, descricao COLLATE NOCASE",
        tuple(params),
    )


def _holiday_set():
    return {row["data"] for row in get_holidays(active_only=True)}


def _date_range(start, end):
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


def calculate_period(period, settings=None, holidays=None):
    cfg = settings or get_settings()
    start_dt = parse_datetime(period["data_hora_inicio"])
    end_dt = parse_datetime(period["data_hora_fim"])
    if end_dt < start_dt:
        raise VacationValidationError("A chegada não pode ser anterior à partida.")

    cutoff = datetime.strptime(cfg["hora_limite_chegada"], "%H:%M").time()
    excluded_arrival = end_dt.time() < cutoff
    effective_end = end_dt.date() - timedelta(days=1 if excluded_arrival else 0)
    if effective_end < start_dt.date():
        raise VacationValidationError(
            "A hora de chegada exclui todo o período de ausência indicado."
        )

    holiday_dates = set(holidays if holidays is not None else _holiday_set())
    travel_candidates = {
        start_dt.date(),
        start_dt.date() + timedelta(days=1),
        effective_end - timedelta(days=1),
        effective_end,
    }
    classifications = {}
    counts = {"F": 0, "TD": 0, "FS": 0}
    for current in _date_range(start_dt.date(), effective_end):
        iso = current.isoformat()
        if current.weekday() >= 5 or iso in holiday_dates:
            code = "FS"
        elif current in travel_candidates:
            code = "TD"
        else:
            code = "F"
        counts[code] += 1
        classifications[iso] = code

    return {
        "fim_efetivo": effective_end.isoformat(),
        "dia_chegada_excluido": excluded_arrival,
        "dias_ferias": counts["F"],
        "dias_viagem": counts["TD"],
        "dias_fim_semana_feriado": counts["FS"],
        "dias_ausencia": len(classifications),
        "classificacoes": classifications,
    }


def _last_day_february(value):
    return value.month == 2 and (value + timedelta(days=1)).month != value.month


def days_360_us(start, end):
    d1, d2 = start.day, end.day
    if _last_day_february(start) or d1 == 31:
        d1 = 30
    if _last_day_february(end) and d1 >= 30:
        d2 = 30
    elif d2 == 31 and d1 >= 30:
        d2 = 30
    return (end.year - start.year) * 360 + (end.month - start.month) * 30 + d2 - d1


def calculate_entitlement(member, settings=None):
    override = member.get("ferias_direito_override")
    if override not in (None, ""):
        return float(override)
    mission_start = str(member.get("data_chegada") or "")[:10]
    mission_end = str(member.get("data_partida") or "")[:10]
    if not mission_start or not mission_end:
        return None
    try:
        start = date.fromisoformat(mission_start)
        end = date.fromisoformat(mission_end)
    except ValueError:
        return None
    if end < start:
        return None
    cfg = settings or get_settings()
    return math.floor((days_360_us(start, end) * cfg["dias_por_mes"] / 30) + 0.5)


def _member(user_id):
    return db.db_one(
        "SELECT * FROM utilizadores WHERE id = ? AND master = 0", (int(user_id),)
    )


def _identification(member):
    rank = str(member.get("posto_portugal") or member.get("posto") or "").strip()
    surname = str(member.get("sobrenome") or "").strip().upper()
    name = str(member.get("nome") or "").strip().upper()
    return f"{rank} {surname or name}".strip() or str(member.get("nim") or "Utilizador")


def _planning_rows(member_id, exclude_id=None):
    params = [int(member_id), *PLANNING_STATUS_ORDER]
    exclude = ""
    if exclude_id:
        exclude = "AND id <> ?"
        params.append(int(exclude_id))
    placeholders = ",".join("?" for _ in PLANNING_STATUS_ORDER)
    return db.db_rows(
        f"""
        SELECT * FROM ferias
        WHERE utilizador_id = ? AND estado IN ({placeholders}) {exclude}
        ORDER BY data_hora_inicio
        """,
        tuple(params),
    )


def _active_member_on(member, day):
    start = str(member.get("data_chegada") or "")[:10]
    end = str(member.get("data_partida") or "")[:10]
    iso = day.isoformat()
    return (not start or start <= iso) and (not end or end >= iso)


def _functional_area_warnings(member, candidate, breakdown, current_id, cfg, holidays):
    area = str(member.get("area_funcional") or "").strip()
    if not area or area.casefold() == "não definido":
        return [
            "A área funcional não está definida; não foi possível verificar o limite de ausentes."
        ]
    members = db.db_rows(
        """
        SELECT * FROM utilizadores
        WHERE master = 0 AND LOWER(TRIM(COALESCE(area_funcional, ''))) = LOWER(?)
        """,
        (area,),
    )
    placeholders = ",".join("?" for _ in PLANNING_STATUS_ORDER)
    params = [*PLANNING_STATUS_ORDER]
    exclude = ""
    if current_id:
        exclude = "AND f.id <> ?"
        params.append(int(current_id))
    rows = db.db_rows(
        f"""
        SELECT f.* FROM ferias f
        WHERE f.estado IN ({placeholders}) {exclude}
        """,
        tuple(params),
    )
    prepared = []
    member_ids = {int(item["id"]) for item in members}
    for row in rows:
        if int(row["utilizador_id"]) not in member_ids:
            continue
        try:
            prepared.append((row, calculate_period(row, cfg, holidays)))
        except VacationValidationError:
            continue

    violations = []
    start = parse_datetime(candidate["data_hora_inicio"]).date()
    effective_end = date.fromisoformat(breakdown["fim_efetivo"])
    for day in _date_range(start, effective_end):
        active = [item for item in members if _active_member_on(item, day)]
        if not active:
            continue
        active_ids = {int(item["id"]) for item in active}
        absent = {int(member["id"])}
        iso = day.isoformat()
        for row, other in prepared:
            if int(row["utilizador_id"]) in active_ids:
                other_start = str(row["data_hora_inicio"])[:10]
                if other_start <= iso <= other["fim_efetivo"]:
                    absent.add(int(row["utilizador_id"]))
        percentage = len(absent) * 100 / len(active)
        if percentage > cfg["max_percentagem_area"]:
            violations.append((iso, len(absent), len(active), percentage))
    if not violations:
        return []
    first = violations[0]
    peak = max(violations, key=lambda item: item[3])
    return [
        f"O limite de {cfg['max_percentagem_area']:g}% na área «{area}» é ultrapassado "
        f"em {len(violations)} dia(s), a partir de {format_date(first[0])}; máximo de "
        f"{peak[1]}/{peak[2]} ausentes ({round(peak[3])}%)."
    ]


def validate_request(values, *, current_id=None):
    errors = []
    warnings = []
    try:
        member_id = int(values.get("utilizador_id"))
    except (TypeError, ValueError, AttributeError):
        raise VacationValidationError("Seleciona uma pessoa.")
    member = _member(member_id)
    if not member:
        raise VacationValidationError("Pessoa não encontrada.")
    candidate = {
        "utilizador_id": member_id,
        "data_hora_inicio": normalise_datetime(values.get("data_hora_inicio")),
        "data_hora_fim": normalise_datetime(values.get("data_hora_fim")),
        "observacao": str(values.get("observacao") or "").strip()[:1000],
        "companhia_aerea": str(values.get("companhia_aerea") or "").strip()[:120],
    }
    cfg = get_settings()
    holidays = _holiday_set()
    try:
        breakdown = calculate_period(candidate, cfg, holidays)
    except VacationValidationError as exc:
        errors.append(str(exc))
        return candidate, {"errors": errors, "warnings": warnings, "breakdown": None}

    start_dt = parse_datetime(candidate["data_hora_inicio"])
    end_dt = parse_datetime(candidate["data_hora_fim"])
    mission_start_text = str(member.get("data_chegada") or "")[:10]
    mission_end_text = str(member.get("data_partida") or "")[:10]
    mission_start = date.fromisoformat(mission_start_text) if mission_start_text else None
    mission_end = date.fromisoformat(mission_end_text) if mission_end_text else None

    if mission_start and start_dt.date() < mission_start:
        errors.append("O período começa antes do início da missão.")
    if mission_end and end_dt.date() > mission_end:
        errors.append("O período termina depois do fim previsto da missão.")
    if not mission_start or not mission_end:
        warnings.append(
            "As datas de início/fim da missão não estão completas; o direito e os bloqueios de missão não foram integralmente verificados."
        )
    if breakdown["dias_ausencia"] > cfg["max_dias_ausencia"]:
        errors.append(
            f"A ausência tem {breakdown['dias_ausencia']} dias; o limite configurado é "
            f"{cfg['max_dias_ausencia']}."
        )
    block_days = cfg["dias_bloqueio_missao"]
    if mission_start and start_dt.date() < mission_start + timedelta(days=block_days):
        errors.append(f"As férias não podem ocorrer nos primeiros {block_days} dias da missão.")
    effective_end = date.fromisoformat(breakdown["fim_efetivo"])
    if mission_end and effective_end > mission_end - timedelta(days=block_days):
        errors.append(f"As férias não podem ocorrer nos últimos {block_days} dias da missão.")

    existing = _planning_rows(member_id, current_id)
    prepared = []
    for row in existing:
        try:
            prepared.append((row, calculate_period(row, cfg, holidays)))
        except VacationValidationError:
            continue
    if len(existing) >= cfg["max_periodos"]:
        errors.append(
            f"Já existem {len(existing)} períodos; o máximo configurado é {cfg['max_periodos']}."
        )
    if len(existing) >= 2 and not int(member.get("missao_prorrogada") or 0):
        warnings.append(
            "Este será o terceiro período e a missão não está assinalada como prorrogada."
        )
    for row, other in prepared:
        other_start = date.fromisoformat(str(row["data_hora_inicio"])[:10])
        other_end = date.fromisoformat(other["fim_efetivo"])
        if start_dt.date() <= other_end and other_start <= effective_end:
            errors.append(
                "O período sobrepõe-se a outro período da mesma pessoa: "
                f"{format_date(row['data_hora_inicio'])}–{format_date(row['data_hora_fim'])}."
            )
            break

    entitlement = calculate_entitlement(member, cfg)
    planned = breakdown["dias_ferias"] + sum(item[1]["dias_ferias"] for item in prepared)
    if entitlement is not None and planned > entitlement:
        errors.append(
            f"O total planeado seria {planned} dias de férias, acima do direito de {entitlement:g}."
        )
    area_warnings = _functional_area_warnings(
        member, candidate, breakdown, current_id, cfg, holidays
    )
    if cfg["modo_limite_area"] == "block":
        errors.extend(message for message in area_warnings if message.startswith("O limite de"))
        warnings.extend(message for message in area_warnings if not message.startswith("O limite de"))
    else:
        warnings.extend(area_warnings)
    if breakdown["dia_chegada_excluido"]:
        warnings.append(
            f"O dia {format_date(candidate['data_hora_fim'])} não conta como ausência porque "
            f"a chegada é anterior às {cfg['hora_limite_chegada']}."
        )
    return candidate, {"errors": errors, "warnings": warnings, "breakdown": breakdown}


def require_valid(values, *, current_id=None, accept_warnings=False):
    candidate, validation = validate_request(values, current_id=current_id)
    if validation["errors"]:
        raise VacationValidationError(
            "O pedido não respeita as regras de planeamento.",
            errors=validation["errors"],
            warnings=validation["warnings"],
            breakdown=validation["breakdown"],
        )
    if validation["warnings"] and not accept_warnings:
        raise VacationValidationError(
            "O pedido contém avisos que devem ser confirmados.",
            warnings=validation["warnings"],
            breakdown=validation["breakdown"],
        )
    return candidate, validation


def _history(conn, vacation_id, actor_id, action, old_status, new_status, note="", details=None):
    conn.execute(
        """
        INSERT INTO ferias_historico (
            feria_id, utilizador_id, acao, estado_anterior, estado_novo,
            nota, detalhes, criado_em
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            vacation_id,
            actor_id,
            action,
            old_status,
            new_status,
            str(note or "")[:1000],
            json.dumps(details or {}, ensure_ascii=False),
            now_db(),
        ),
    )


def _notify(
    conn, user_ids, vacation_id, kind, title, message, actor_id=None,
    channel="pessoal"
):
    for user_id in set(int(item) for item in user_ids if item is not None):
        if actor_id is not None and user_id == int(actor_id):
            continue
        conn.execute(
            """
            INSERT INTO ferias_notificacoes (
                utilizador_id, feria_id, tipo, canal, titulo, mensagem, criado_em
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id, vacation_id, kind, channel,
                title[:160], message[:500], now_db(),
            ),
        )


def _snr_ids(conn, *, exclude_user_id=None):
    today = date.today().isoformat()
    rows = conn.execute(
        """
        SELECT DISTINCT u.id
        FROM utilizadores u
        WHERE u.master = 0
          AND COALESCE(u.snr_substituto, 0) = 1
          AND SUBSTR(COALESCE(u.snr_substituto_inicio, ''), 1, 10) <= ?
          AND SUBSTR(COALESCE(u.snr_substituto_fim, ''), 1, 10) >= ?
        """,
        (today, today),
    ).fetchall()
    if not rows:
        rows = conn.execute(
            """
            SELECT DISTINCT u.id
            FROM utilizadores u
            WHERE u.master = 0 AND COALESCE(u.snr, 0) = 1
            """
        ).fetchall()
    excluded = int(exclude_user_id) if exclude_user_id is not None else None
    return [row[0] for row in rows if excluded is None or int(row[0]) != excluded]


def _record(conn, vacation_id):
    row = conn.execute("SELECT * FROM ferias WHERE id = ?", (int(vacation_id),)).fetchone()
    return dict(row) if row else None


def create_request(actor, target_id, values, *, accept_warnings=False):
    payload = dict(values)
    payload["utilizador_id"] = int(target_id)
    candidate, validation = require_valid(
        payload, accept_warnings=accept_warnings
    )
    stamp = now_db()
    auto_approved = (
        int(target_id) == int(actor["id"])
        and int(actor.get("snr") or 0) == 1
    )
    initial_status = STATUS_APPROVED if auto_approved else STATUS_PENDING
    conn = db._connect()
    conn.row_factory = db.sqlite3.Row
    try:
        conn.execute("BEGIN IMMEDIATE")
        cursor = conn.execute(
            """
            INSERT INTO ferias (
                utilizador_id, data_hora_inicio, data_hora_fim, observacao,
                companhia_aerea, estado, submetido_por, submetido_em,
                decidido_por, decidido_em, nota_decisao,
                avisos_aceites, criado_em, atualizado_em
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                candidate["utilizador_id"],
                candidate["data_hora_inicio"],
                candidate["data_hora_fim"],
                candidate["observacao"],
                candidate["companhia_aerea"],
                initial_status,
                actor["id"],
                stamp,
                actor["id"] if auto_approved else None,
                stamp if auto_approved else None,
                "Aprovação automática das férias próprias do SNR." if auto_approved else None,
                json.dumps(validation["warnings"], ensure_ascii=False),
                stamp,
                stamp,
            ),
        )
        vacation_id = cursor.lastrowid
        _history(
            conn,
            vacation_id,
            actor["id"],
            "Submetido e aprovado automaticamente" if auto_approved else "Submetido",
            None,
            initial_status,
            details={"warnings": validation["warnings"]},
        )
        if not auto_approved:
            member = _member(target_id)
            _notify(
                conn,
                _snr_ids(conn, exclude_user_id=target_id),
                vacation_id,
                "pedido",
                "Novo pedido de férias",
                f"{_identification(member)} submeteu um período para decisão.",
                actor["id"],
                channel="gestao",
            )
        conn.commit()
        return vacation_id, validation
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def update_request(actor, vacation_id, values, *, can_manage=False, accept_warnings=False):
    existing = db.db_one("SELECT * FROM ferias WHERE id = ?", (int(vacation_id),))
    if not existing:
        raise VacationValidationError("Pedido não encontrado.")
    own = int(existing["utilizador_id"]) == int(actor["id"])
    if not own and not can_manage:
        raise PermissionError("Não podes alterar este pedido.")
    if existing["estado"] not in (STATUS_PENDING, STATUS_RETURNED):
        raise VacationValidationError("Apenas pedidos pendentes ou devolvidos podem ser corrigidos.")
    target_id = int(values.get("utilizador_id") or existing["utilizador_id"]) if can_manage else int(existing["utilizador_id"])
    payload = dict(values)
    payload["utilizador_id"] = target_id
    candidate, validation = require_valid(
        payload, current_id=vacation_id, accept_warnings=accept_warnings
    )
    stamp = now_db()
    conn = db._connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            """
            UPDATE ferias SET utilizador_id=?, data_hora_inicio=?, data_hora_fim=?,
                observacao=?, companhia_aerea=?, estado=?, submetido_por=?,
                submetido_em=?, decidido_por=NULL, decidido_em=NULL,
                nota_decisao=NULL, avisos_aceites=?, atualizado_em=?
            WHERE id=?
            """,
            (
                target_id,
                candidate["data_hora_inicio"],
                candidate["data_hora_fim"],
                candidate["observacao"],
                candidate["companhia_aerea"],
                STATUS_PENDING,
                actor["id"],
                stamp,
                json.dumps(validation["warnings"], ensure_ascii=False),
                stamp,
                vacation_id,
            ),
        )
        action = "Corrigido e reenviado" if existing["estado"] == STATUS_RETURNED else "Alterado"
        _history(conn, vacation_id, actor["id"], action, existing["estado"], STATUS_PENDING)
        member = _member(target_id)
        _notify(
            conn,
            _snr_ids(conn, exclude_user_id=target_id),
            vacation_id,
            "pedido",
            "Pedido de férias atualizado",
            f"{_identification(member)} reenviou um período para decisão.",
            actor["id"],
            channel="gestao",
        )
        conn.commit()
        return validation
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def decide_request(actor, vacation_id, action, note=""):
    decisions = {"approve": STATUS_APPROVED, "reject": STATUS_REJECTED, "return": STATUS_RETURNED}
    status = decisions.get(action)
    if not status:
        raise VacationValidationError("Decisão inválida.")
    note = str(note or "").strip()[:1000]
    if status != STATUS_APPROVED and not note:
        raise VacationValidationError("Indica o motivo da rejeição ou devolução.")
    conn = db._connect()
    conn.row_factory = db.sqlite3.Row
    try:
        conn.execute("BEGIN IMMEDIATE")
        existing = _record(conn, vacation_id)
        if not existing:
            raise VacationValidationError("Pedido não encontrado.")
        if existing["estado"] != STATUS_PENDING:
            raise VacationValidationError("Este pedido já não está pendente.")
        if int(existing["utilizador_id"]) == int(actor["id"]) or int(existing.get("submetido_por") or 0) == int(actor["id"]):
            raise VacationValidationError("Não podes decidir o teu próprio pedido.")
        stamp = now_db()
        conn.execute(
            """
            UPDATE ferias SET estado=?, decidido_por=?, decidido_em=?,
                nota_decisao=?, atualizado_em=? WHERE id=?
            """,
            (status, actor["id"], stamp, note, stamp, vacation_id),
        )
        _history(conn, vacation_id, actor["id"], status, STATUS_PENDING, status, note)
        _notify(
            conn,
            [existing["utilizador_id"]],
            vacation_id,
            "decisao",
            f"Pedido de férias {status.lower()}",
            note or "O pedido foi autorizado.",
            actor["id"],
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def update_approved_times(actor, vacation_id, departure_time, arrival_time):
    """Atualiza exclusivamente as horas de um período já aprovado."""
    try:
        departure = datetime.strptime(str(departure_time or ""), "%H:%M").time()
        arrival = datetime.strptime(str(arrival_time or ""), "%H:%M").time()
    except ValueError:
        raise VacationValidationError("Indica horas válidas para a partida e a chegada.")

    existing = db.db_one("SELECT * FROM ferias WHERE id=?", (int(vacation_id),))
    if not existing:
        raise VacationValidationError("Período de férias não encontrado.")
    if existing["estado"] != STATUS_APPROVED:
        raise VacationValidationError("Só é possível atualizar horas de férias aprovadas.")

    old_start = datetime.strptime(existing["data_hora_inicio"], "%Y-%m-%d %H:%M")
    old_end = datetime.strptime(existing["data_hora_fim"], "%Y-%m-%d %H:%M")
    new_start = datetime.combine(old_start.date(), departure).strftime("%Y-%m-%d %H:%M")
    new_end = datetime.combine(old_end.date(), arrival).strftime("%Y-%m-%d %H:%M")
    candidate = {
        "utilizador_id": existing["utilizador_id"],
        "data_hora_inicio": new_start,
        "data_hora_fim": new_end,
        "observacao": existing.get("observacao") or "",
        "companhia_aerea": existing.get("companhia_aerea") or "",
    }
    require_valid(candidate, current_id=vacation_id, accept_warnings=True)

    stamp = now_db()
    conn = db._connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            """
            UPDATE ferias SET data_hora_inicio=?, data_hora_fim=?,
                atualizado_em=? WHERE id=? AND estado=?
            """,
            (new_start, new_end, stamp, int(vacation_id), STATUS_APPROVED),
        )
        _history(
            conn, vacation_id, actor["id"], "Horas atualizadas",
            STATUS_APPROVED, STATUS_APPROVED,
            details={
                "antes": {"partida": existing["data_hora_inicio"], "chegada": existing["data_hora_fim"]},
                "depois": {"partida": new_start, "chegada": new_end},
            },
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def request_change(actor, vacation_id, values, reason, *, can_manage=False, accept_warnings=False):
    existing = db.db_one("SELECT * FROM ferias WHERE id = ?", (int(vacation_id),))
    if not existing:
        raise VacationValidationError("Pedido não encontrado.")
    if int(existing["utilizador_id"]) != int(actor["id"]) and not can_manage:
        raise PermissionError("Não podes pedir a alteração deste período.")
    if existing["estado"] != STATUS_APPROVED:
        raise VacationValidationError("Apenas períodos aprovados podem ser alterados.")
    reason = str(reason or "").strip()[:1000]
    if not reason:
        raise VacationValidationError("Indica o motivo da alteração.")
    payload = dict(values)
    payload["utilizador_id"] = existing["utilizador_id"]
    candidate, validation = require_valid(
        payload, current_id=vacation_id, accept_warnings=accept_warnings
    )
    stamp = now_db()
    auto_approved = (
        int(existing["utilizador_id"]) == int(actor["id"])
        and int(actor.get("snr") or 0) == 1
    )
    conn = db._connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        if auto_approved:
            conn.execute(
                """
                UPDATE ferias SET data_hora_inicio=?, data_hora_fim=?,
                    observacao=?, companhia_aerea=?, estado=?,
                    decidido_por=?, decidido_em=?, nota_decisao=?,
                    proposta_data_hora_inicio=NULL, proposta_data_hora_fim=NULL,
                    proposta_observacao=NULL, proposta_companhia_aerea=NULL,
                    motivo_fluxo=NULL, fluxo_pedido_por=NULL, fluxo_pedido_em=NULL,
                    avisos_aceites=?, atualizado_em=? WHERE id=?
                """,
                (
                    candidate["data_hora_inicio"], candidate["data_hora_fim"],
                    candidate["observacao"], candidate["companhia_aerea"],
                    STATUS_APPROVED, actor["id"], stamp,
                    "Alteração automática das férias próprias do SNR.",
                    json.dumps(validation["warnings"], ensure_ascii=False),
                    stamp, vacation_id,
                ),
            )
            _history(
                conn, vacation_id, actor["id"],
                "Alteração aprovada automaticamente", STATUS_APPROVED,
                STATUS_APPROVED, reason, {"proposta": candidate},
            )
        else:
            conn.execute(
                """
                UPDATE ferias SET estado=?, proposta_data_hora_inicio=?,
                proposta_data_hora_fim=?, proposta_observacao=?,
                proposta_companhia_aerea=?, motivo_fluxo=?, fluxo_pedido_por=?,
                fluxo_pedido_em=?, avisos_aceites=?, atualizado_em=? WHERE id=?
                """,
                (
                    STATUS_CHANGE_PENDING,
                    candidate["data_hora_inicio"], candidate["data_hora_fim"],
                    candidate["observacao"], candidate["companhia_aerea"],
                    reason, actor["id"], stamp,
                    json.dumps(validation["warnings"], ensure_ascii=False),
                    stamp, vacation_id,
                ),
            )
            _history(conn, vacation_id, actor["id"], "Pedido de alteração", STATUS_APPROVED, STATUS_CHANGE_PENDING, reason, {"proposta": candidate})
            member = _member(existing["utilizador_id"])
            _notify(
                conn, _snr_ids(conn, exclude_user_id=existing["utilizador_id"]),
                vacation_id, "alteracao", "Alteração de férias pendente",
                f"{_identification(member)} pediu uma alteração ao período aprovado.",
                actor["id"], channel="gestao",
            )
        conn.commit()
        return validation
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def decide_change(actor, vacation_id, action, note=""):
    if action not in ("approve", "reject"):
        raise VacationValidationError("Decisão inválida.")
    note = str(note or "").strip()[:1000]
    if action == "reject" and not note:
        raise VacationValidationError("Indica o motivo da rejeição da alteração.")
    conn = db._connect()
    conn.row_factory = db.sqlite3.Row
    try:
        conn.execute("BEGIN IMMEDIATE")
        existing = _record(conn, vacation_id)
        if not existing or existing["estado"] != STATUS_CHANGE_PENDING:
            raise VacationValidationError("Este pedido já não aguarda decisão de alteração.")
        if (
            int(existing["utilizador_id"]) == int(actor["id"])
            or int(existing.get("submetido_por") or 0) == int(actor["id"])
            or int(existing.get("fluxo_pedido_por") or 0) == int(actor["id"])
        ):
            raise VacationValidationError("A alteração tem de ser decidida por outro aprovador.")
        stamp = now_db()
        if action == "approve":
            proposed = {
                "utilizador_id": existing["utilizador_id"],
                "data_hora_inicio": existing["proposta_data_hora_inicio"],
                "data_hora_fim": existing["proposta_data_hora_fim"],
                "observacao": existing["proposta_observacao"],
                "companhia_aerea": existing["proposta_companhia_aerea"],
            }
            require_valid(proposed, current_id=vacation_id, accept_warnings=True)
            conn.execute(
                """
                UPDATE ferias SET data_hora_inicio=proposta_data_hora_inicio,
                    data_hora_fim=proposta_data_hora_fim,
                    observacao=proposta_observacao,
                    companhia_aerea=proposta_companhia_aerea,
                    estado=?, decidido_por=?, decidido_em=?, nota_decisao=?,
                    proposta_data_hora_inicio=NULL, proposta_data_hora_fim=NULL,
                    proposta_observacao=NULL, proposta_companhia_aerea=NULL,
                    motivo_fluxo=NULL, fluxo_pedido_por=NULL,
                    fluxo_pedido_em=NULL, atualizado_em=? WHERE id=?
                """,
                (STATUS_APPROVED, actor["id"], stamp, note, stamp, vacation_id),
            )
            label = "Alteração aprovada"
        else:
            conn.execute(
                """
                UPDATE ferias SET estado=?, decidido_por=?, decidido_em=?,
                    nota_decisao=?, proposta_data_hora_inicio=NULL,
                    proposta_data_hora_fim=NULL, proposta_observacao=NULL,
                    proposta_companhia_aerea=NULL, motivo_fluxo=NULL,
                    fluxo_pedido_por=NULL, fluxo_pedido_em=NULL,
                    atualizado_em=? WHERE id=?
                """,
                (STATUS_APPROVED, actor["id"], stamp, note, stamp, vacation_id),
            )
            label = "Alteração rejeitada"
        _history(conn, vacation_id, actor["id"], label, STATUS_CHANGE_PENDING, STATUS_APPROVED, note)
        _notify(conn, [existing["utilizador_id"]], vacation_id, "decisao", label, note or "A alteração foi autorizada.", actor["id"])
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def request_cancellation(actor, vacation_id, reason, *, can_manage=False):
    existing = db.db_one("SELECT * FROM ferias WHERE id = ?", (int(vacation_id),))
    if not existing:
        raise VacationValidationError("Pedido não encontrado.")
    if int(existing["utilizador_id"]) != int(actor["id"]) and not can_manage:
        raise PermissionError("Não podes pedir o cancelamento deste período.")
    if existing["estado"] != STATUS_APPROVED:
        raise VacationValidationError("Apenas períodos aprovados podem ser cancelados.")
    reason = str(reason or "").strip()[:1000]
    if not reason:
        raise VacationValidationError("Indica o motivo do cancelamento.")
    stamp = now_db()
    conn = db._connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            """
            UPDATE ferias SET estado=?, motivo_fluxo=?, fluxo_pedido_por=?,
                fluxo_pedido_em=?, atualizado_em=? WHERE id=?
            """,
            (STATUS_CANCEL_PENDING, reason, actor["id"], stamp, stamp, vacation_id),
        )
        _history(conn, vacation_id, actor["id"], "Pedido de cancelamento", STATUS_APPROVED, STATUS_CANCEL_PENDING, reason)
        member = _member(existing["utilizador_id"])
        _notify(
            conn,
            _snr_ids(conn, exclude_user_id=existing["utilizador_id"]),
            vacation_id,
            "cancelamento",
            "Cancelamento de férias pendente",
            f"{_identification(member)} pediu o cancelamento de um período aprovado.",
            actor["id"],
            channel="gestao",
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def decide_cancellation(actor, vacation_id, action, note=""):
    if action not in ("approve", "reject"):
        raise VacationValidationError("Decisão inválida.")
    note = str(note or "").strip()[:1000]
    if action == "reject" and not note:
        raise VacationValidationError("Indica o motivo da rejeição do cancelamento.")
    conn = db._connect()
    conn.row_factory = db.sqlite3.Row
    try:
        conn.execute("BEGIN IMMEDIATE")
        existing = _record(conn, vacation_id)
        if not existing or existing["estado"] != STATUS_CANCEL_PENDING:
            raise VacationValidationError("Este pedido já não aguarda decisão de cancelamento.")
        if (
            int(existing["utilizador_id"]) == int(actor["id"])
            or int(existing.get("submetido_por") or 0) == int(actor["id"])
            or int(existing.get("fluxo_pedido_por") or 0) == int(actor["id"])
        ):
            raise VacationValidationError("O cancelamento tem de ser decidido por outro aprovador.")
        approved = action == "approve"
        new_status = STATUS_ANNULLED if approved else STATUS_APPROVED
        stamp = now_db()
        conn.execute(
            """
            UPDATE ferias SET estado=?, decidido_por=?, decidido_em=?,
                nota_decisao=?, anulado_por=?, anulado_em=?, motivo_anulacao=?,
                motivo_fluxo=NULL, fluxo_pedido_por=NULL, fluxo_pedido_em=NULL,
                atualizado_em=? WHERE id=?
            """,
            (
                new_status,
                actor["id"],
                stamp,
                note,
                actor["id"] if approved else None,
                stamp if approved else None,
                existing["motivo_fluxo"] if approved else None,
                stamp,
                vacation_id,
            ),
        )
        label = "Cancelamento aprovado" if approved else "Cancelamento rejeitado"
        _history(conn, vacation_id, actor["id"], label, STATUS_CANCEL_PENDING, new_status, note)
        _notify(conn, [existing["utilizador_id"]], vacation_id, "decisao", label, note or "O cancelamento foi autorizado.", actor["id"])
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def withdraw_request(actor, vacation_id, reason=""):
    reason = str(reason or "").strip()[:1000] or "Retirado pelo titular."
    conn = db._connect()
    conn.row_factory = db.sqlite3.Row
    try:
        conn.execute("BEGIN IMMEDIATE")
        existing = _record(conn, vacation_id)
        if not existing:
            raise VacationValidationError("Pedido não encontrado.")
        if int(existing["utilizador_id"]) != int(actor["id"]):
            raise PermissionError("Não podes retirar este pedido.")
        if existing["estado"] not in (STATUS_PENDING, STATUS_RETURNED):
            raise VacationValidationError("Este pedido já não pode ser retirado.")
        stamp = now_db()
        conn.execute(
            "UPDATE ferias SET estado=?, anulado_por=?, anulado_em=?, motivo_anulacao=?, atualizado_em=? WHERE id=?",
            (STATUS_ANNULLED, actor["id"], stamp, reason, stamp, vacation_id),
        )
        _history(conn, vacation_id, actor["id"], "Retirado", existing["estado"], STATUS_ANNULLED, reason)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def delete_request(vacation_id):
    """Apaga definitivamente um período; a permissão é validada pela API."""
    conn = db._connect()
    conn.row_factory = db.sqlite3.Row
    try:
        conn.execute("BEGIN IMMEDIATE")
        existing = _record(conn, vacation_id)
        if not existing:
            raise VacationValidationError("Pedido não encontrado.")
        conn.execute("DELETE FROM ferias WHERE id=?", (int(vacation_id),))
        conn.commit()
        return existing
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def annul_approved(actor, vacation_id, reason):
    reason = str(reason or "").strip()[:1000]
    if not reason:
        raise VacationValidationError("Indica o motivo da anulação.")
    conn = db._connect()
    conn.row_factory = db.sqlite3.Row
    try:
        conn.execute("BEGIN IMMEDIATE")
        existing = _record(conn, vacation_id)
        if not existing or existing["estado"] != STATUS_APPROVED:
            raise VacationValidationError("Apenas períodos aprovados podem ser anulados.")
        if int(existing["utilizador_id"]) == int(actor["id"]):
            raise VacationValidationError("Não podes anular o teu próprio período.")
        stamp = now_db()
        conn.execute(
            "UPDATE ferias SET estado=?, anulado_por=?, anulado_em=?, motivo_anulacao=?, atualizado_em=? WHERE id=?",
            (STATUS_ANNULLED, actor["id"], stamp, reason, stamp, vacation_id),
        )
        _history(conn, vacation_id, actor["id"], "Anulado", STATUS_APPROVED, STATUS_ANNULLED, reason)
        _notify(conn, [existing["utilizador_id"]], vacation_id, "decisao", "Período de férias anulado", reason, actor["id"])
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def restore_annulled(actor, vacation_id):
    """Reverte uma anulação, preservando a origem correta do fluxo no histórico."""
    conn = db._connect()
    conn.row_factory = db.sqlite3.Row
    try:
        conn.execute("BEGIN IMMEDIATE")
        existing = _record(conn, vacation_id)
        if not existing or existing["estado"] != STATUS_ANNULLED:
            raise VacationValidationError("Apenas períodos anulados podem ser revertidos.")
        if (
            int(existing["utilizador_id"]) == int(actor["id"])
            or int(existing.get("submetido_por") or 0) == int(actor["id"])
            or int(existing.get("fluxo_pedido_por") or 0) == int(actor["id"])
        ):
            raise VacationValidationError("A reversão tem de ser efetuada por outro aprovador.")

        previous = conn.execute(
            """
            SELECT estado_anterior FROM ferias_historico
            WHERE feria_id=? AND estado_novo=?
            ORDER BY criado_em DESC, id DESC LIMIT 1
            """,
            (vacation_id, STATUS_ANNULLED),
        ).fetchone()
        old_status = previous["estado_anterior"] if previous else STATUS_APPROVED
        if old_status == STATUS_CANCEL_PENDING:
            restored_status = STATUS_APPROVED
        elif old_status in (STATUS_PENDING, STATUS_RETURNED, STATUS_APPROVED):
            restored_status = old_status
        else:
            restored_status = STATUS_APPROVED

        stamp = now_db()
        note = "Anulação revertida por Administrador/SNR."
        conn.execute(
            """
            UPDATE ferias SET estado=?, anulado_por=NULL, anulado_em=NULL,
                motivo_anulacao=NULL, motivo_fluxo=NULL, fluxo_pedido_por=NULL,
                fluxo_pedido_em=NULL, decidido_por=?, decidido_em=?,
                nota_decisao=?, atualizado_em=? WHERE id=?
            """,
            (restored_status, actor["id"], stamp, note, stamp, vacation_id),
        )
        _history(
            conn, vacation_id, actor["id"], "Anulação revertida",
            STATUS_ANNULLED, restored_status, note,
        )
        _notify(
            conn, [existing["utilizador_id"]], vacation_id, "decisao",
            "Anulação de férias revertida",
            "O período voltou ao estado anterior.", actor["id"],
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def format_date(value):
    text_value = str(value or "")[:10]
    try:
        return date.fromisoformat(text_value).strftime("%d/%m/%Y")
    except ValueError:
        return text_value


def _history_map(ids):
    if not ids:
        return {}
    placeholders = ",".join("?" for _ in ids)
    rows = db.db_rows(
        f"""
        SELECT h.*, u.posto AS ator_posto, u.posto_portugal AS ator_posto_portugal, u.nome AS ator_nome,
               u.sobrenome AS ator_sobrenome, u.nim AS ator_nim
        FROM ferias_historico h
        LEFT JOIN utilizadores u ON u.id = h.utilizador_id
        WHERE h.feria_id IN ({placeholders})
        ORDER BY h.criado_em DESC, h.id DESC
        """,
        tuple(ids),
    )
    result = {}
    for row in rows:
        try:
            row["detalhes"] = json.loads(row.get("detalhes") or "{}")
        except json.JSONDecodeError:
            row["detalhes"] = {}
        ator_posto = row.pop("ator_posto", "") or ""
        actor = {
            "posto": row.pop("ator_posto_portugal", "") or ator_posto,
            "nome": row.pop("ator_nome", "") or "",
            "sobrenome": row.pop("ator_sobrenome", "") or "",
            "nim": row.pop("ator_nim", "") or "",
        }
        row["ator"] = _identification(actor) if any(actor.values()) else "Sistema"
        result.setdefault(row["feria_id"], []).append(row)
    return result


def list_requests(
    *, member_id=None, vacation_id=None, year=None, status=None,
    status_group=None, search="", area="", future_only=False, settings=None,
    holidays=None, include_history=True
):
    where = []
    params = []
    if member_id is not None:
        where.append("f.utilizador_id = ?")
        params.append(int(member_id))
    if vacation_id is not None:
        where.append("f.id = ?")
        params.append(int(vacation_id))
    if year:
        start = f"{int(year):04d}-01-01"
        end = f"{int(year) + 1:04d}-01-01"
        where.append("f.data_hora_inicio < ? AND f.data_hora_fim >= ?")
        params.extend((end, start))
    if future_only:
        where.append("f.data_hora_fim >= ?")
        params.append(datetime.now().strftime("%Y-%m-%d %H:%M"))
    if status and status in ALL_STATUSES:
        where.append("f.estado = ?")
        params.append(status)
    elif status_group and status_group in STATUS_FILTER_GROUPS and status_group != "all":
        grouped_statuses = STATUS_FILTER_GROUPS[status_group]
        placeholders = ",".join("?" for _item in grouped_statuses)
        where.append(f"f.estado IN ({placeholders})")
        params.extend(grouped_statuses)
    if area:
        where.append("LOWER(TRIM(COALESCE(u.area_funcional,''))) = LOWER(?)")
        params.append(area.strip())
    if search:
        where.append(
            "LOWER(COALESCE(u.nim,'') || ' ' || COALESCE(u.posto,'') || ' ' || "
            "COALESCE(u.nome,'') || ' ' || COALESCE(u.sobrenome,'')) LIKE LOWER(?)"
        )
        params.append(f"%{search.strip()}%")
    clause = f"WHERE {' AND '.join(where)}" if where else ""
    rows = db.db_rows(
        f"""
        SELECT f.*, u.nim, u.posto, u.posto_portugal, u.nome, u.sobrenome, u.area_funcional,
               u.posicao_numero,
               u.data_chegada AS missao_inicio, u.data_partida AS missao_fim,
               u.ferias_direito_override, u.missao_prorrogada
        FROM ferias f
        JOIN utilizadores u ON u.id = f.utilizador_id
        {clause}
        ORDER BY f.data_hora_inicio ASC, f.data_hora_fim ASC, f.id ASC
        """,
        tuple(params),
    )
    histories = _history_map([row["id"] for row in rows]) if include_history else {}
    settings = settings or get_settings()
    holidays = _holiday_set() if holidays is None else set(holidays)
    for row in rows:
        row["identificacao"] = _identification(row)
        row["historico"] = histories.get(row["id"], [])
        try:
            row["resumo"] = calculate_period(row, settings, holidays)
        except VacationValidationError:
            row["resumo"] = None
        if row.get("proposta_data_hora_inicio") and row.get("proposta_data_hora_fim"):
            proposed = {
                "data_hora_inicio": row["proposta_data_hora_inicio"],
                "data_hora_fim": row["proposta_data_hora_fim"],
            }
            try:
                row["resumo_proposta"] = calculate_period(proposed, settings, holidays)
            except VacationValidationError:
                row["resumo_proposta"] = None
        else:
            row["resumo_proposta"] = None
        try:
            row["avisos_aceites"] = json.loads(row.get("avisos_aceites") or "[]")
        except json.JSONDecodeError:
            row["avisos_aceites"] = []
    return rows


def member_summary(member, requests=None, settings=None):
    cfg = settings or get_settings()
    items = requests if requests is not None else list_requests(member_id=member["id"])
    planning = [item for item in items if item["estado"] in PLANNING_STATUSES]
    approved = [item for item in items if item["estado"] in APPROVED_STATUSES]
    planned_days = sum((item.get("resumo") or {}).get("dias_ferias", 0) for item in planning)
    approved_days = sum((item.get("resumo") or {}).get("dias_ferias", 0) for item in approved)
    travel = sum((item.get("resumo") or {}).get("dias_viagem", 0) for item in planning)
    weekends = sum((item.get("resumo") or {}).get("dias_fim_semana_feriado", 0) for item in planning)
    entitlement = calculate_entitlement(member, cfg)
    return {
        "direito": entitlement,
        "planeados": planned_days,
        "aprovados": approved_days,
        "disponiveis": None if entitlement is None else entitlement - planned_days,
        "dias_viagem": travel,
        "fins_semana_feriados": weekends,
        "periodos": len(planning),
        "pendentes": sum(1 for item in planning if item["estado"] in ACTIONABLE_STATUSES),
    }


def safe_member(member):
    return {
        "id": member["id"],
        "nim": member.get("nim") or "",
        "posto": member.get("posto") or "",
        "posto_portugal": member.get("posto_portugal") or "",
        "nome": member.get("nome") or "",
        "sobrenome": member.get("sobrenome") or "",
        "identificacao": _identification(member),
        "antiguidade": member.get("antiguidade") or "",
        "area_funcional": member.get("area_funcional") or "Não definido",
        "posicao_numero": member.get("posicao_numero") or "",
        "data_chegada": member.get("data_chegada") or "",
        "data_partida": member.get("data_partida") or "",
        "telemovel_servico": member.get("telemovel_servico") or "",
        "ferias_direito_override": member.get("ferias_direito_override"),
        "missao_prorrogada": bool(int(member.get("missao_prorrogada") or 0)),
        "notas_ferias": member.get("notas_ferias") or "",
        "snr": bool(int(member.get("snr") or 0)),
        "snr_substituto": bool(int(member.get("snr_substituto") or 0)),
        "snr_substituto_inicio": member.get("snr_substituto_inicio") or "",
        "snr_substituto_fim": member.get("snr_substituto_fim") or "",
        "snr_substituto_ativo": bool(
            int(member.get("snr_substituto") or 0)
            and str(member.get("snr_substituto_inicio") or "")[:10]
            <= date.today().isoformat()
            <= str(member.get("snr_substituto_fim") or "")[:10]
        ),
        "responsavel_welfare": bool(int(member.get("responsavel_welfare") or 0)),
    }


def print_member_order_key(member):
    """Compatibilidade para relatórios: aplica a regra global das pessoas."""
    return person_order_key(member)


def notifications(user_id, limit=50, *, channel="pessoal"):
    return db.db_rows(
        """
        SELECT * FROM ferias_notificacoes
        WHERE utilizador_id = ? AND canal = ?
        ORDER BY lida ASC, criado_em DESC, id DESC LIMIT ?
        """,
        (int(user_id), channel, int(limit)),
    )


def notification_payload(user_id, limit=50, *, channel="pessoal"):
    """Obtém a lista e o total não lido numa única ligação à base de dados."""
    conn = db._connect()
    conn.row_factory = db.sqlite3.Row
    try:
        rows = [
            dict(row)
            for row in conn.execute(
                """
                SELECT * FROM ferias_notificacoes
                WHERE utilizador_id = ? AND canal = ?
                ORDER BY lida ASC, criado_em DESC, id DESC LIMIT ?
                """,
                (int(user_id), channel, int(limit)),
            ).fetchall()
        ]
        unread = conn.execute(
            """
            SELECT COUNT(*) FROM ferias_notificacoes
            WHERE utilizador_id = ? AND canal = ? AND lida = 0
            """,
            (int(user_id), channel),
        ).fetchone()[0]
        return {"notificacoes": rows, "nao_lidas": int(unread or 0)}
    finally:
        conn.close()


def private_payload(user_id, year=None, *, show_all=False):
    member = _member(user_id)
    if not member:
        raise VacationValidationError(
            "Esta conta não está associada a uma pessoa ativa na aplicação."
        )
    settings = get_settings()
    chosen_year = int(year or settings["ano_calendario"])
    holiday_rows = get_holidays(active_only=True)
    holiday_dates = {row["data"] for row in holiday_rows}
    requests = list_requests(
        member_id=user_id,
        future_only=not bool(show_all),
        settings=settings,
        holidays=holiday_dates,
        include_history=False,
    )
    all_requests = requests if show_all else list_requests(
        member_id=user_id,
        settings=settings,
        holidays=holiday_dates,
        include_history=False,
    )
    notification_data = notification_payload(user_id, channel="pessoal")
    return {
        "ano": chosen_year,
        "mostrar_tudo": bool(show_all),
        "pessoa": safe_member(member),
        "resumo": member_summary(member, all_requests, settings=settings),
        "pedidos": requests,
        **notification_data,
        "settings": settings,
        "feriados": [
            row for row in holiday_rows if str(row.get("data") or "").startswith(f"{chosen_year:04d}-")
        ],
    }


def management_payload(
    *, year=None, status=None, status_group="all", search="", area="",
    show_all=False, requests_year=None, export_only=False
):
    settings = get_settings()
    chosen_year = int(year or settings["ano_calendario"])
    holiday_rows = get_holidays()
    holiday_dates = {row["data"] for row in holiday_rows if int(row.get("ativo") or 0)}
    users = sorted(
        db.db_rows("SELECT * FROM utilizadores WHERE master=0"),
        key=person_order_key,
    )
    visible_users = users if show_all else [
        member for member in users if member_still_in_mission(member)
    ]
    visible_user_ids = {member["id"] for member in visible_users}
    all_for_year = list_requests(
        year=chosen_year,
        settings=settings,
        holidays=holiday_dates,
        include_history=False,
    )
    scoped_for_year = all_for_year if show_all else [
        item for item in all_for_year
        if item["utilizador_id"] in visible_user_ids
    ]
    print_users = [member for member in users if member_still_in_mission(member)]
    print_user_ids = {member["id"] for member in print_users}
    status_group = status_group if status_group in STATUS_FILTER_GROUPS else "all"
    if (
        requests_year == chosen_year
        and not status and status_group == "all" and not search and not area
    ):
        requests = all_for_year
    else:
        requests = list_requests(
            year=requests_year,
            status=status,
            status_group=status_group,
            search=search,
            area=area,
            future_only=requests_year is None and not bool(show_all),
            settings=settings,
            holidays=holiday_dates,
            include_history=False,
        )
    if not show_all:
        requests = [
            item for item in requests
            if item["utilizador_id"] in visible_user_ids
        ]
    print_requests = list_requests(
        year=chosen_year,
        status=status,
        status_group=status_group,
        search=search,
        area=area,
        settings=settings,
        holidays=holiday_dates,
        include_history=False,
    )
    print_requests = [
        item for item in print_requests
        if item["utilizador_id"] in print_user_ids
    ]
    print_owner_ids = {item["utilizador_id"] for item in print_requests}
    ordered_print_users = [
        member for member in print_users if member["id"] in print_owner_ids
    ]
    by_member = {}
    for item in scoped_for_year:
        by_member.setdefault(item["utilizador_id"], []).append(item)
    people = []
    payload_users = visible_users if export_only else users
    for member in payload_users:
        safe = safe_member(member)
        safe["pode_novo_pedido"] = member_still_in_mission(member)
        safe["resumo"] = member_summary(
            member, by_member.get(member["id"], []), settings=settings
        )
        people.append(safe)
    areas = sorted(
        {
            (item.get("area_funcional") or "Não definido").strip() or "Não definido"
            for item in users
        },
        key=str.casefold,
    )
    summary = {
        "pessoas": len(visible_users),
        "periodos": sum(1 for item in scoped_for_year if item["estado"] in PLANNING_STATUSES),
        "aprovados": sum(1 for item in scoped_for_year if item["estado"] in APPROVED_STATUSES),
        "pendentes": sum(1 for item in scoped_for_year if item["estado"] in ACTIONABLE_STATUSES),
        "dias_planeados": sum((item.get("resumo") or {}).get("dias_ferias", 0) for item in scoped_for_year if item["estado"] in PLANNING_STATUSES),
        "dias_disponiveis": sum(
            max(0, item["resumo"]["disponiveis"])
            for item in people
            if item["resumo"]["disponiveis"] is not None
        ),
    }
    return {
        "ano": chosen_year,
        "mostrar_tudo": bool(show_all),
        "pedidos": requests,
        "filtro_estado": status_group,
        "titulo_impressao": STATUS_FILTER_TITLES[status_group],
        "periodos_impressao": print_requests,
        "pessoas": people,
        "ordem_impressao": [
            member["id"]
            for member in sorted(ordered_print_users, key=print_member_order_key)
        ],
        "areas": areas,
        "estados": list(ALL_STATUSES),
        "resumo": summary,
        "settings": settings,
        "feriados": [
            row for row in holiday_rows if str(row.get("data") or "").startswith(f"{chosen_year:04d}-")
        ],
    }


def calendar_payload(year, month, *, member_id=None):
    year, month = int(year), int(month)
    last = calendar.monthrange(year, month)[1]
    month_start = f"{year:04d}-{month:02d}-01"
    month_end = f"{year:04d}-{month:02d}-{last:02d}"
    if member_id:
        members = [_member(member_id)]
    else:
        members = db.db_rows(
            """
            SELECT * FROM utilizadores WHERE master=0
              AND (data_chegada IS NULL OR TRIM(data_chegada)='' OR SUBSTR(data_chegada,1,10) <= ?)
              AND (data_partida IS NULL OR TRIM(data_partida)='' OR SUBSTR(data_partida,1,10) >= ?)
            """,
            (month_end, month_start),
        )
    members = [item for item in members if item]
    members.sort(key=print_member_order_key)
    member_ids = {int(item["id"]) for item in members}
    placeholders = ",".join("?" for _ in PLANNING_STATUS_ORDER)
    rows = db.db_rows(
        f"""
        SELECT * FROM ferias
        WHERE estado IN ({placeholders})
          AND SUBSTR(data_hora_inicio,1,10) <= ?
          AND SUBSTR(data_hora_fim,1,10) >= ?
        """,
        (*PLANNING_STATUS_ORDER, month_end, month_start),
    )
    cfg = get_settings()
    holidays = _holiday_set()
    grid = {item["id"]: {} for item in members}
    for row in rows:
        member_key = int(row["utilizador_id"])
        if member_key not in member_ids:
            continue
        try:
            breakdown = calculate_period(row, cfg, holidays)
        except VacationValidationError:
            continue
        for iso, code in breakdown["classificacoes"].items():
            if month_start <= iso <= month_end:
                grid[member_key][iso] = {
                    "codigo": code,
                    "estado": row["estado"],
                    "feria_id": row["id"],
                }
    days = [f"{year:04d}-{month:02d}-{day:02d}" for day in range(1, last + 1)]
    daily = {}
    for iso in days:
        day = date.fromisoformat(iso)
        active = [item for item in members if _active_member_on(item, day)]
        absent = sum(1 for item in active if grid[item["id"]].get(iso))
        daily[iso] = {
            "ausentes": absent,
            "ativos": len(active),
            "percentagem": absent * 100 / len(active) if active else 0,
        }
    return {
        "ano": year,
        "mes": month,
        "dias": days,
        "pessoas": [safe_member(item) for item in members],
        "grelha": grid,
        "diario": daily,
        "feriados": get_holidays(year=year, active_only=True),
    }
