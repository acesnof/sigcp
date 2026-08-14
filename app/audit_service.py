"""Registo e consulta paginada da auditoria da aplicação."""

import json
import re
from datetime import datetime, timedelta

from app import db


SENSITIVE_PARTS = (
    "password",
    "senha",
    "confirmar",
    "token",
    "csrf",
    "secret",
    "salt",
    "hash",
)
VALID_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
MAX_DETAIL_TEXT = 12_000

ACTION_LABELS = {
    "api_login": "Início de sessão",
    "api_logout": "Fim de sessão",
    "api_shutdown": "Encerramento da aplicação",
    "api_profile_password": "Alteração da password pessoal",
    "api_save_welfare": "Welfare guardado",
    "api_delete_welfare": "Welfare eliminado",
    "api_month_lock": "Bloqueio mensal alterado",
    "api_create_user": "Utilizador criado",
    "api_update_user": "Utilizador alterado",
    "api_delete_user": "Utilizador eliminado",
    "api_save_settings": "Configuração alterada",
    "api_create_vacation": "Pedido de férias criado",
    "api_update_vacation": "Pedido de férias alterado",
    "api_delete_vacation": "Pedido de férias removido",
    "api_withdraw_vacation": "Pedido de férias retirado",
    "api_vacation_decision": "Decisão de férias registada",
    "api_vacation_change_request": "Alteração de férias pedida",
    "api_vacation_change_decision": "Alteração de férias decidida",
    "api_vacation_cancellation_request": "Cancelamento de férias pedido",
    "api_vacation_cancellation_decision": "Cancelamento de férias decidido",
    "api_vacation_annul": "Período de férias anulado",
    "api_vacation_restore": "Anulação de férias revertida",
    "api_save_vacation_settings": "Regras de férias alteradas",
    "api_save_vacation_person": "Dados de férias da pessoa alterados",
    "api_create_vacation_holiday": "Feriado de férias criado",
    "api_update_vacation_holiday": "Feriado de férias alterado",
    "api_delete_vacation_holiday": "Feriado de férias eliminado",
    "api_read_vacation_notifications": "Notificações de férias lidas",
    "api_delete_vacation_notification": "Notificação de férias eliminada",
    "api_individual_markings": "Marcações individuais alteradas",
    "api_create_day_off": "Day Off criado",
    "api_update_day_off": "Day Off alterado",
    "api_delete_day_off": "Day Off eliminado",
}


def _is_sensitive(key):
    lowered = str(key or "").casefold()
    return any(part in lowered for part in SENSITIVE_PARTS)


def sanitize(value, *, key="", depth=0):
    """Remove segredos e limita estruturas grandes antes de as persistir."""
    if _is_sensitive(key):
        return "[OCULTO]"
    if depth >= 5:
        return "[CONTEÚDO PROFUNDO OMITIDO]"
    if isinstance(value, dict):
        items = list(value.items())
        result = {
            str(item_key): sanitize(item_value, key=item_key, depth=depth + 1)
            for item_key, item_value in items[:80]
        }
        if len(items) > 80:
            result["_omitidos"] = len(items) - 80
        return result
    if isinstance(value, (list, tuple)):
        result = [sanitize(item, depth=depth + 1) for item in value[:40]]
        if len(value) > 40:
            result.append(f"[{len(value) - 40} elementos omitidos]")
        return result
    if value is None or isinstance(value, (bool, int, float)):
        return value
    text = str(value)
    return text if len(text) <= 600 else f"{text[:600]}… [truncado]"


def _details_json(details):
    safe = sanitize(details or {})
    encoded = json.dumps(safe, ensure_ascii=False, separators=(",", ":"))
    if len(encoded) <= MAX_DETAIL_TEXT:
        return encoded
    return json.dumps(
        {"truncado": True, "conteudo": encoded[: MAX_DETAIL_TEXT - 100]},
        ensure_ascii=False,
        separators=(",", ":"),
    )


def actor_identification(user):
    if not user:
        return "Sistema"
    rank = str(user.get("posto_portugal") or user.get("posto") or "").strip()
    surname = str(user.get("sobrenome") or "").strip().upper()
    name = str(user.get("nome") or "").strip().upper()
    return f"{rank} {surname or name}".strip() or str(user.get("nim") or "Sistema")


def record(
    *, user, endpoint, method, route, view_args=None, payload=None,
    query=None, result=None, address="", action=None, extra=None
):
    method = str(method or "").upper()
    if method not in VALID_METHODS:
        return
    view_args = view_args or {}
    entity_id = ", ".join(
        f"{key}={value}" for key, value in view_args.items() if value is not None
    )
    details = {}
    if payload:
        details["pedido"] = payload
    if query:
        details["parametros"] = query
    if result:
        details["resultado"] = result
    if extra:
        details["contexto"] = extra
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = db._connect()
    try:
        conn.execute(
            """
            INSERT INTO auditoria (
                criado_em, utilizador_id, utilizador_nim,
                utilizador_identificacao, acao, metodo, rota,
                entidade, entidade_id, detalhes, endereco_ip
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                stamp,
                user.get("id") if user else None,
                str((user or {}).get("nim") or ""),
                actor_identification(user),
                str(action or ACTION_LABELS.get(endpoint) or f"{method} {endpoint or route}"),
                method,
                str(route or "")[:300],
                str(endpoint or "")[:160],
                entity_id[:300],
                _details_json(details),
                str(address or "")[:100],
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _iso_date(value, *, end=False):
    text = str(value or "").strip()[:10]
    if not text:
        return ""
    parsed = datetime.strptime(text, "%Y-%m-%d")
    if end:
        parsed += timedelta(days=1)
    return parsed.strftime("%Y-%m-%d")


def _fts_search(search):
    words = re.findall(r"[^\W_]+", search, flags=re.UNICODE)[:12]
    return " AND ".join(f'"{word.replace(chr(34), "")}"*' for word in words)


def list_entries(
    *, search="", method="", date_from="", date_to="", before_id=None,
    limit=50
):
    limit = max(10, min(int(limit or 50), 100))
    where = []
    params = []
    if before_id:
        where.append("id < ?")
        params.append(int(before_id))
    search = str(search or "").strip()[:160]
    if search:
        fts_query = _fts_search(search)
        fts_available = bool(
            db.db_one(
                "SELECT 1 AS available FROM sqlite_master "
                "WHERE type='table' AND name='auditoria_fts'"
            )
        )
        if fts_available and fts_query:
            where.append(
                "id IN (SELECT rowid FROM auditoria_fts "
                "WHERE auditoria_fts MATCH ?)"
            )
            params.append(fts_query)
        else:
            where.append(
                "LOWER(utilizador_nim || ' ' || utilizador_identificacao || ' ' || "
                "acao || ' ' || metodo || ' ' || rota || ' ' || "
                "COALESCE(entidade_id,'') || ' ' || detalhes) LIKE LOWER(?)"
            )
            params.append(f"%{search}%")
    method = str(method or "").upper()
    if method:
        if method not in VALID_METHODS:
            raise ValueError("Método de auditoria inválido.")
        where.append("metodo = ?")
        params.append(method)
    start = _iso_date(date_from)
    end = _iso_date(date_to, end=True)
    if start:
        where.append("criado_em >= ?")
        params.append(start)
    if end:
        where.append("criado_em < ?")
        params.append(end)
    clause = f"WHERE {' AND '.join(where)}" if where else ""
    rows = db.db_rows(
        f"""
        SELECT * FROM auditoria
        {clause}
        ORDER BY id DESC
        LIMIT ?
        """,
        tuple(params + [limit + 1]),
    )
    has_more = len(rows) > limit
    rows = rows[:limit]
    for row in rows:
        try:
            row["detalhes"] = json.loads(row.get("detalhes") or "{}")
        except json.JSONDecodeError:
            row["detalhes"] = {"conteudo": row.get("detalhes") or ""}
    return {
        "registos": rows,
        "tem_mais": has_more,
        "proximo_cursor": rows[-1]["id"] if has_more and rows else None,
        "limite": limit,
    }
