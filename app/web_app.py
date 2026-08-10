"""Aplicação web local do SIGCP."""

import calendar
import filecmp
import io
import os
import secrets
import sqlite3
import sys
import tempfile
import json
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta
from functools import wraps
from pathlib import Path
from tkinter import Tk, filedialog

from flask import (
    Flask,
    g,
    jsonify,
    render_template,
    request,
    send_file,
    send_from_directory,
    session,
)

import app.config as app_config
from app.config import (
    ACESSOS_APAGAM_WELFARES_MENSAIS,
    ACESSOS_EDITAM_EMENTAS_MENSAIS,
    ACESSOS_EDITAM_WELFARES_MENSAIS,
    ACESSOS_GEREM_FERIAS,
    ACESSOS_VEEM_WELFARES_INDIVIDUAIS,
    APP_FULL_NAME,
    APP_NAME,
    DOCS_DIR,
    MASTER_NIM,
    MASTER_PASSWORD,
    POSTOS,
    TIPOS_ACESSO,
    TIPOS_ACESSO_DESCRICAO,
    TIPOS_WELFARE,
)
from app.db import (
    autenticar_utilizador,
    atualizar_password_utilizador,
    db_execute,
    db_execute_return_id,
    db_one,
    db_rows,
    eliminar_day_off,
    eliminar_feria,
    eliminar_welfare,
    enriquecer_user_com_acessos,
    exportar_base_dados_json,
    init_db,
    get_day_off,
    get_day_offs,
    get_day_offs_mes,
    get_feria,
    get_horario_dfac,
    get_inicio_semana,
    get_lingua,
    get_nome_cos,
    get_responsavel_welfare_mais_antigo_ativo,
    get_setting,
    get_snr_unico_para_assinatura,
    get_teams,
    get_utilizador_acessos,
    get_valor_caixa,
    get_valor_welfare,
    get_welfare,
    get_welfares_mes,
    guardar_day_off,
    guardar_feria,
    guardar_welfare,
    reset_welfares_individuais_mes,
    set_horario_dfac,
    set_inicio_semana,
    set_setting,
    set_lingua,
    set_mes_trancado,
    set_nome_cos,
    set_utilizador_acessos,
    set_valor_caixa,
    set_valor_welfare,
    set_welfares_individuais,
)
from app.i18n import months, weekdays_short
from app.person_order import person_order_key
from app.print_utils import gerar_pdf_mes
from app.reports.individual_pdf import gerar_pdf_welfare_individual
from app.reports.reimbursement_xlsx import gerar_reembolso_mensal
from app.reports.request_docx import (
    gerar_request_welfare_meals,
    gerar_request_welfare_meals_hoto,
)
from app.reports.service_note_docx import gerar_service_note
from app.reports.weekly_xlsx import gerar_meals_request_weekly
from app.reports.vacations_xlsx import generate_vacations_xlsx
from app.security import hash_password
from app import audit_service as audit
from app import vacation_service as vacations
from app import dish_roster
from app import cash_service
from app.web_services import IndividualService, calcular_distribuicao_xfa
from app.supabase_store import SupabaseUnavailable


class ApiError(Exception):
    def __init__(self, mensagem, status=400, codigo="erro", details=None):
        super().__init__(mensagem)
        self.mensagem = mensagem
        self.status = status
        self.codigo = codigo
        self.details = details or {}


def _resource_dir():
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "app"
    return Path(__file__).resolve().parent


def _json_ok(**dados):
    return jsonify({"ok": True, **dados})


def _body():
    dados = request.get_json(silent=True)
    if not isinstance(dados, dict):
        raise ApiError("Pedido inválido.")
    return dados


def _current_user():
    if session.get("superadmin") is True:
        return _superadmin_user()
    user_id = session.get("user_id")
    if not user_id:
        return None
    user = db_one("SELECT * FROM utilizadores WHERE id = ?", (user_id,))
    if not user:
        session.clear()
        return None
    return enriquecer_user_com_acessos(user)


def _superadmin_user():
    # A autenticação não depende deste registo. Quando a cache está disponível,
    # o id técnico permite apenas satisfazer relações opcionais de auditoria e
    # férias; init_db mantém o registo oculto da listagem normal.
    try:
        tecnico = db_one("SELECT id FROM utilizadores WHERE master=1 LIMIT 1")
        tecnico_id = tecnico["id"] if tecnico else 0
    except Exception:
        tecnico_id = 0
    return {
        "id": tecnico_id, "nim": MASTER_NIM, "posto": "", "nome": "Super",
        "sobrenome": "Administrador", "tipo_acesso": "Administrador",
        "acessos": ["Administrador"], "master": 1, "virtual_master": True,
        "snr": 0, "snr_substituto": 0, "responsavel_welfare": 0,
    }


def _acessos(user):
    if not user:
        return set()
    acessos = user.get("acessos") or []
    if not acessos and user.get("tipo_acesso"):
        acessos = [
            acesso.strip()
            for acesso in str(user["tipo_acesso"]).split(",")
            if acesso.strip()
        ]
    return set(acessos)


def _is_admin(user):
    return "Administrador" in _acessos(user)


def _is_snr_titular(user):
    try:
        return int(user.get("snr") or 0) == 1
    except (TypeError, ValueError, AttributeError):
        return False


def _is_snr_substituto_ativo(user, referencia=None):
    try:
        if int(user.get("snr_substituto") or 0) != 1:
            return False
        inicio = date.fromisoformat(str(user.get("snr_substituto_inicio") or "")[:10])
        fim = date.fromisoformat(str(user.get("snr_substituto_fim") or "")[:10])
    except (TypeError, ValueError, AttributeError):
        return False
    referencia = referencia or date.today()
    return inicio <= referencia <= fim


def _is_snr(user):
    return _is_snr_titular(user) or _is_snr_substituto_ativo(user)


def _pode_gerir_pessoal(user):
    return _is_admin(user) or bool(_acessos(user) & ACESSOS_GEREM_FERIAS)


def _pode_ver_pessoal(user):
    return _pode_gerir_pessoal(user) or _is_snr(user)


def _pode_nomear_substituto_snr(user):
    return _is_admin(user) or _is_snr_titular(user)


def _pode_gerir_ferias(user):
    return _is_admin(user) or _is_snr(user) or bool(
        _acessos(user) & ACESSOS_GEREM_FERIAS
    )


def _pode_atualizar_horas_ferias(user):
    return _is_admin(user) or bool(
        _acessos(user) & {"Pessoal/Gestão Férias", "Gestão Welfare Individual"}
    )


def _pode_ver_gestao_ferias(user):
    return _pode_gerir_ferias(user) or _pode_atualizar_horas_ferias(user)


def _pode_decidir_ferias(user):
    return _is_admin(user) or _is_snr(user)


def _pode_ver_individual(user):
    return _is_admin(user) or _is_responsavel_welfare(user) or bool(
        _acessos(user) & ACESSOS_VEEM_WELFARES_INDIVIDUAIS
    )


def _pode_editar_welfare(user):
    return _is_admin(user) or _is_responsavel_welfare(user) or bool(
        _acessos(user) & ACESSOS_EDITAM_WELFARES_MENSAIS
    )


def _pode_gerir_teams(user):
    """Teams pertencem ao Administrador, SNR e Gestão Welfare Mensal."""
    return _is_admin(user) or _is_snr(user) or "Gestão Welfare Mensal" in _acessos(user)


def _pode_gerir_escala_loica(user):
    return _is_admin(user) or "Gestão Welfare Mensal" in _acessos(user)


def _pode_gerir_caixa(user):
    return _is_admin(user) or "Gestão Caixa" in _acessos(user)


def _pode_editar_ementa(user):
    return _is_admin(user) or _is_responsavel_welfare(user) or bool(
        _acessos(user) & ACESSOS_EDITAM_EMENTAS_MENSAIS
    )


def _pode_apagar_welfare(user):
    return _is_admin(user) or _is_responsavel_welfare(user) or bool(
        _acessos(user) & ACESSOS_APAGAM_WELFARES_MENSAIS
    )


def _is_responsavel_welfare(user):
    try:
        if int(user.get("responsavel_welfare") or 0) != 1:
            return False
    except (TypeError, ValueError, AttributeError):
        return False
    partida = (user.get("data_partida") or "").strip()
    if partida:
        try:
            return datetime.strptime(partida[:10], "%Y-%m-%d").date() >= date.today()
        except ValueError:
            pass
    return True


def _pode_trancar_individual(user):
    return _is_admin(user) or _is_responsavel_welfare(user)


def _identificacao(user):
    posto = (user.get("posto") or "").strip()
    sobrenome = (user.get("sobrenome") or "").strip().upper()
    nome = (user.get("nome") or "").strip().upper()
    return f"{posto} {sobrenome or nome}".strip() or user.get("nim") or "Utilizador"


def _safe_user(user):
    acessos = (
        user.get("acessos", [])
        if user.get("virtual_master")
        else get_utilizador_acessos(user["id"])
    )
    return {
        "id": user["id"],
        "nim": user.get("nim") or "",
        "posto": user.get("posto") or "",
        "nome": user.get("nome") or "",
        "sobrenome": user.get("sobrenome") or "",
        "data_nascimento": user.get("data_nascimento") or "",
        "antiguidade": user.get("antiguidade") or "",
        "data_chegada": user.get("data_chegada") or "",
        "data_partida": user.get("data_partida") or "",
        "snr": bool(int(user.get("snr") or 0)),
        "snr_substituto": bool(int(user.get("snr_substituto") or 0)),
        "snr_substituto_inicio": user.get("snr_substituto_inicio") or "",
        "snr_substituto_fim": user.get("snr_substituto_fim") or "",
        "snr_substituto_ativo": _is_snr_substituto_ativo(user),
        "telemovel_servico": user.get("telemovel_servico") or "",
        "responsavel_welfare": bool(int(user.get("responsavel_welfare") or 0)),
        "area_funcional": user.get("area_funcional") or "Não definido",
        "posicao_numero": user.get("posicao_numero") or "",
        "ferias_direito_override": user.get("ferias_direito_override"),
        "missao_prorrogada": bool(int(user.get("missao_prorrogada") or 0)),
        "notas_ferias": user.get("notas_ferias") or "",
        "master": bool(int(user.get("master") or 0)),
        "acessos": acessos
        or [
            acesso.strip()
            for acesso in str(user.get("tipo_acesso") or "").split(",")
            if acesso.strip()
        ],
        "identificacao": _identificacao(user),
    }


def _login_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        user = _current_user()
        if not user:
            raise ApiError("Sessão terminada. Inicia sessão novamente.", 401, "sessao")
        g.audit_user = user
        return func(user, *args, **kwargs)

    return wrapper


def _admin_required(func):
    @wraps(func)
    @_login_required
    def wrapper(user, *args, **kwargs):
        if not _is_admin(user):
            raise ApiError("Não tens permissão para esta operação.", 403, "permissao")
        return func(user, *args, **kwargs)

    return wrapper


def _superadmin_required(func):
    @wraps(func)
    @_login_required
    def wrapper(user, *args, **kwargs):
        if not user.get("virtual_master"):
            raise ApiError(
                "Esta operação está reservada ao superadministrador.",
                403,
                "superadmin",
            )
        return func(user, *args, **kwargs)

    return wrapper


def _personnel_required(func):
    @wraps(func)
    @_login_required
    def wrapper(user, *args, **kwargs):
        if not _pode_gerir_pessoal(user):
            raise ApiError("Não tens permissão para esta operação.", 403, "permissao")
        return func(user, *args, **kwargs)

    return wrapper


def _personnel_view_required(func):
    @wraps(func)
    @_login_required
    def wrapper(user, *args, **kwargs):
        if not _pode_ver_pessoal(user):
            raise ApiError("Não tens permissão para consultar o Pessoal.", 403, "permissao")
        return func(user, *args, **kwargs)

    return wrapper


def _vacation_manager_required(func):
    @wraps(func)
    @_login_required
    def wrapper(user, *args, **kwargs):
        if not _pode_gerir_ferias(user):
            raise ApiError("Não tens permissão para gerir férias.", 403, "permissao")
        return func(user, *args, **kwargs)

    return wrapper


def _vacation_decision_required(func):
    @wraps(func)
    @_login_required
    def wrapper(user, *args, **kwargs):
        if not _pode_decidir_ferias(user):
            raise ApiError("A decisão pertence a um Administrador ou SNR.", 403, "permissao")
        return func(user, *args, **kwargs)

    return wrapper


def _periodo(ano=None, mes=None):
    try:
        ano = int(ano if ano is not None else request.args.get("ano"))
        mes = int(mes if mes is not None else request.args.get("mes"))
    except (TypeError, ValueError):
        raise ApiError("Indica um mês e ano válidos.")
    if not 2000 <= ano <= 2200 or not 1 <= mes <= 12:
        raise ApiError("Indica um mês e ano válidos.")
    return ano, mes


def _data_iso(valor, obrigatoria=False):
    valor = (valor or "").strip()
    if not valor:
        if obrigatoria:
            raise ApiError("A data é obrigatória.")
        return ""
    try:
        return date.fromisoformat(valor[:10]).isoformat()
    except ValueError:
        raise ApiError("A data deve estar no formato AAAA-MM-DD.")


def _valores_substituicao_snr(current, person, dados):
    atuais = (
        1 if person and int(person.get("snr_substituto") or 0) else 0,
        (person or {}).get("snr_substituto_inicio") or "",
        (person or {}).get("snr_substituto_fim") or "",
    )
    campos = {
        "snr_substituto",
        "snr_substituto_inicio",
        "snr_substituto_fim",
    }
    if not any(campo in dados for campo in campos):
        return atuais
    if not _pode_nomear_substituto_snr(current):
        raise ApiError(
            "Apenas um Administrador ou o SNR titular pode nomear um substituto.",
            403,
            "permissao",
        )

    nomeado = 1 if dados.get("snr_substituto") else 0
    if not nomeado:
        return 0, "", ""
    if not person:
        raise ApiError("Guarda primeiro a pessoa antes de a nomear como substituto SNR.")
    if int(person.get("master") or 0):
        raise ApiError("O utilizador mestre não pode ser substituto SNR.")
    if int(person.get("snr") or 0):
        raise ApiError("Esta pessoa já é SNR titular.")
    if int(person.get("id") or 0) == int(current.get("id") or 0):
        raise ApiError("O SNR deve escolher outra pessoa como substituto.")

    inicio = _data_iso(dados.get("snr_substituto_inicio"), obrigatoria=True)
    fim = _data_iso(dados.get("snr_substituto_fim"), obrigatoria=True)
    if fim < inicio:
        raise ApiError("O fim da substituição não pode anteceder o início.")

    sobreposto = db_one(
        """
        SELECT * FROM utilizadores
        WHERE id<>? AND master=0 AND COALESCE(snr_substituto, 0)=1
          AND COALESCE(snr_substituto_inicio, '')<>''
          AND COALESCE(snr_substituto_fim, '')<>''
          AND SUBSTR(snr_substituto_inicio, 1, 10) <= ?
          AND SUBSTR(snr_substituto_fim, 1, 10) >= ?
        LIMIT 1
        """,
        (person["id"], fim, inicio),
    )
    if sobreposto:
        raise ApiError(
            f"{_identificacao(sobreposto)} já está nomeado como substituto nesse período."
        )
    return 1, inicio, fim


def _data_hora(valor, obrigatoria=False):
    valor = (valor or "").strip().replace("T", " ")
    if not valor:
        if obrigatoria:
            raise ApiError("A data e hora são obrigatórias.")
        return ""
    formatos = ("%Y-%m-%d %H:%M", "%Y-%m-%d")
    for formato in formatos:
        try:
            dt = datetime.strptime(valor[:16] if " " in valor else valor[:10], formato)
            return (
                dt.strftime("%Y-%m-%d %H:%M")
                if formato.endswith("%H:%M")
                else dt.strftime("%Y-%m-%d")
            )
        except ValueError:
            continue
    raise ApiError("A data/hora deve estar no formato AAAA-MM-DD HH:MM.")


def _validar_hora(valor):
    valor = (valor or "").strip()
    try:
        hora = datetime.strptime(valor, "%H:%M")
    except ValueError:
        raise ApiError("As horas devem estar no formato HH:MM.")
    return hora.strftime("%H:%M")


def _download_gerado(nome, sufixo, mimetype, gerador):
    with tempfile.TemporaryDirectory() as pasta:
        caminho = Path(pasta) / f"ficheiro{sufixo}"
        gerador(str(caminho))
        conteudo = caminho.read_bytes()
    return send_file(
        io.BytesIO(conteudo),
        mimetype=mimetype,
        as_attachment=True,
        download_name=nome,
        max_age=0,
    )


def _nome_mes_en(mes):
    return [
        "Jan",
        "Feb",
        "Mar",
        "Apr",
        "May",
        "Jun",
        "Jul",
        "Aug",
        "Sep",
        "Oct",
        "Nov",
        "Dec",
    ][mes - 1]


def create_web_app():
    recursos = _resource_dir()
    app = Flask(
        __name__,
        template_folder=str(recursos / "templates"),
        static_folder=str(recursos / "static"),
        static_url_path="/static",
    )
    app.secret_key = secrets.token_bytes(32)
    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Strict",
        SESSION_COOKIE_SECURE=False,
        MAX_CONTENT_LENGTH=4 * 1024 * 1024,
        JSON_AS_ASCII=False,
    )

    @app.after_request
    def security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' data:; "
            "style-src 'self' 'unsafe-inline'; script-src 'self'; "
            "connect-src 'self'; object-src 'none'; frame-ancestors 'none'"
        )
        return response

    @app.after_request
    def audit_successful_mutation(response):
        if (
            request.path.startswith("/api/")
            and request.method in audit.VALID_METHODS
            and request.endpoint != "api_browser_lifecycle"
            and 200 <= response.status_code < 400
        ):
            try:
                actor = getattr(g, "audit_user", None) or _current_user()
                if actor and actor.get("virtual_master"):
                    actor = {**actor, "id": None}
                response_data = response.get_json(silent=True) if response.is_json else None
                result = None
                if isinstance(response_data, dict) and response_data.get("message"):
                    result = {"mensagem": response_data["message"]}
                audit.record(
                    user=actor,
                    endpoint=request.endpoint or "",
                    method=request.method,
                    route=request.path,
                    view_args=request.view_args,
                    payload=request.get_json(silent=True),
                    query=request.args.to_dict(flat=False),
                    result=result,
                    address=request.remote_addr or "",
                    action=getattr(g, "audit_action", None),
                    extra=getattr(g, "audit_extra", None),
                )
            except Exception:
                app.logger.exception("Não foi possível registar a auditoria")
        return response

    @app.before_request
    def csrf_protection():
        if (
            request.path.startswith("/api/")
            and request.method in ("POST", "PUT", "PATCH", "DELETE")
            and request.endpoint not in {"api_login", "api_browser_lifecycle"}
            and (session.get("user_id") or session.get("superadmin") is True)
        ):
            recebido = request.headers.get("X-CSRF-Token", "")
            esperado = session.get("csrf_token", "")
            if not esperado or not secrets.compare_digest(recebido, esperado):
                raise ApiError("Pedido de segurança inválido.", 403, "csrf")

        if (
            app_config.DATABASE_OFFLINE
            and request.method in ("POST", "PUT", "PATCH", "DELETE")
            and request.endpoint not in {
                "api_login", "api_logout", "api_shutdown",
                "api_browser_lifecycle", "api_update_settings",
            }
        ):
            raise ApiError(
                "A base de dados online está indisponível. Tente mais tarde.",
                503,
                "base_online_indisponivel",
            )

    @app.errorhandler(ApiError)
    def handle_api_error(exc):
        payload = {
            "ok": False,
            "error": exc.mensagem,
            "code": exc.codigo,
        }
        payload.update(exc.details)
        return (
            jsonify(payload),
            exc.status,
        )

    @app.errorhandler(vacations.VacationValidationError)
    def handle_vacation_validation_error(exc):
        status = 422 if exc.errors else 409 if exc.warnings else 400
        return (
            jsonify(
                {
                    "ok": False,
                    "error": str(exc),
                    "code": "ferias_validacao",
                    "errors": exc.errors,
                    "warnings": exc.warnings,
                    "breakdown": exc.breakdown,
                }
            ),
            status,
        )

    @app.errorhandler(SupabaseUnavailable)
    def handle_supabase_unavailable(exc):
        return jsonify({"ok": False, "error": str(exc), "code": "base_online_indisponivel"}), 503

    @app.errorhandler(PermissionError)
    def handle_permission_error(exc):
        if request.path.startswith("/api/vacations"):
            return jsonify({"ok": False, "error": str(exc), "code": "permissao"}), 403
        return handle_server_error(exc)

    @app.errorhandler(404)
    def handle_not_found(_exc):
        if request.path.startswith("/api/"):
            return jsonify({"ok": False, "error": "Recurso não encontrado."}), 404
        return render_template(
            "index.html", app_name=APP_NAME, app_full_name=APP_FULL_NAME,
            app_version=app_config.APP_VERSION,
        )

    @app.errorhandler(500)
    def handle_server_error(exc):
        app.logger.exception("Erro interno", exc_info=exc)
        if request.path.startswith("/api/"):
            return (
                jsonify(
                    {
                        "ok": False,
                        "error": "Ocorreu um erro interno. Consulta o registo da aplicação.",
                    }
                ),
                500,
            )
        return "Erro interno", 500

    @app.get("/")
    def index():
        return render_template(
            "index.html", app_name=APP_NAME, app_full_name=APP_FULL_NAME,
            app_version=app_config.APP_VERSION,
        )

    @app.get("/api/instance")
    def api_instance():
        """Identifica com segurança o serviço local para a instância seguinte."""
        return _json_ok(application=APP_NAME, instance=True)

    @app.post("/api/lifecycle")
    def api_browser_lifecycle():
        dados = request.get_json(silent=True) or {}
        tab_id = str(dados.get("tab_id") or "").strip()
        event = str(dados.get("event") or "heartbeat").strip().lower()
        if not tab_id or len(tab_id) > 120 or event not in {"heartbeat", "close"}:
            raise ApiError("Sinal de ciclo de vida inválido.")
        callback = app.config.get("BROWSER_LIFECYCLE_CALLBACK")
        if callback:
            callback(tab_id, event)
        return _json_ok()

    @app.get("/favicon.ico")
    def favicon():
        return send_from_directory(DOCS_DIR, "favicon.ico", mimetype="image/x-icon")

    @app.get("/assets/<path:nome>")
    def assets(nome):
        return send_from_directory(DOCS_DIR, nome, max_age=3600)

    @app.post("/api/login")
    def api_login():
        dados = _body()
        nim = str(dados.get("nim") or "").strip()
        password = str(dados.get("password") or "")
        if not nim or not password:
            raise ApiError("Indica o utilizador e a password.")

        superadmin = secrets.compare_digest(nim, MASTER_NIM) and secrets.compare_digest(password, MASTER_PASSWORD)
        user = _superadmin_user() if superadmin else autenticar_utilizador(nim, password)
        if not user:
            raise ApiError("Utilizador ou password incorretos.", 401, "credenciais")

        backup = {"attempted": False, "ok": True, "message": ""}
        backup_callback = app.config.get("BACKUP_CALLBACK")
        if backup_callback and not app_config.DATABASE_OFFLINE:
            backup["attempted"] = True
            try:
                backup_callback()
            except Exception as exc:
                backup["ok"] = False
                detalhe = str(exc).strip()
                backup["message"] = (
                    "A sessão foi iniciada, mas não foi possível criar o backup "
                    "da base de dados."
                )
                if detalhe:
                    backup["message"] += f" Detalhe: {detalhe}"
                app.logger.exception("Erro ao criar backup no login", exc_info=exc)

        session.clear()
        if superadmin:
            session["superadmin"] = True
        else:
            session["user_id"] = user["id"]
        session["csrf_token"] = secrets.token_urlsafe(32)
        return _json_ok(backup=backup)

    @app.post("/api/logout")
    @_login_required
    def api_logout(_user):
        session.clear()
        return _json_ok()

    @app.post("/api/shutdown")
    @_login_required
    def api_shutdown(_user):
        callback = app.config.get("SHUTDOWN_CALLBACK")
        if callback:
            callback()
        session.clear()
        return _json_ok(message="Aplicação encerrada.")

    @app.get("/api/bootstrap")
    def api_bootstrap():
        user = _current_user()
        if not user:
            return _json_ok(authenticated=False)

        acessos = sorted(_acessos(user))
        unread_vacations = db_rows(
            """
            SELECT canal, COUNT(*) AS total
            FROM ferias_notificacoes
            WHERE utilizador_id=? AND lida=0
            GROUP BY canal
            """,
            (user["id"],),
        )
        unread_by_channel = {
            row["canal"]: int(row.get("total") or 0) for row in unread_vacations
        }
        return _json_ok(
            authenticated=True,
            csrf_token=session.get("csrf_token"),
            language=get_lingua(),
            user={
                **_safe_user(user),
                "acessos": acessos,
            },
            permissions={
                "superadmin": bool(user.get("virtual_master")),
                "admin": _is_admin(user),
                "snr": _is_snr(user),
                "snr_titular": _is_snr_titular(user),
                "snr_substituicao": _pode_nomear_substituto_snr(user),
                "trancar_mes": _pode_trancar_individual(user),
                "editar_welfare": _pode_editar_welfare(user),
                "teams": _pode_gerir_teams(user),
                "escala_loica_gerir": _pode_gerir_escala_loica(user),
                "caixa": _pode_gerir_caixa(user),
                "editar_ementa": _pode_editar_ementa(user),
                "apagar_welfare": _pode_apagar_welfare(user),
                "individual": _pode_ver_individual(user),
                "ferias": _pode_ver_gestao_ferias(user),
                "ferias_gerir": _pode_gerir_ferias(user),
                "ferias_atualizar_horas": _pode_atualizar_horas_ferias(user),
                "ferias_privadas": not bool(int(user.get("master") or 0)),
                "ferias_decidir": _pode_decidir_ferias(user),
                "pessoal": _pode_ver_pessoal(user),
                "pessoal_editar": _pode_gerir_pessoal(user),
                "responsavel_welfare": _is_responsavel_welfare(user),
            },
            notifications={
                "ferias_pessoais_nao_lidas": unread_by_channel.get("pessoal", 0),
                "ferias_gestao_nao_lidas": (
                    unread_by_channel.get("gestao", 0) if _is_snr(user) else 0
                ),
            },
            config={
                "postos": POSTOS,
                "tipos_acesso": TIPOS_ACESSO,
                "tipos_acesso_descricao": TIPOS_ACESSO_DESCRICAO,
                "tipos_welfare": list(TIPOS_WELFARE),
                "meses": months(),
                "dias_semana": weekdays_short(),
                "today": date.today().isoformat(),
                "version": f"{app_config.APP_VERSION} Web",
            },
        )

    @app.put("/api/profile/password")
    @_login_required
    def api_profile_password(user):
        dados = _body()
        password = str(dados.get("password") or "")
        confirmar = str(dados.get("confirmar") or "")
        if not password:
            raise ApiError("Indica a nova password.")
        if password != confirmar:
            raise ApiError("As passwords não coincidem.")
        atualizar_password_utilizador(user["id"], password)
        return _json_ok(message="Password alterada com sucesso.")

    @app.get("/api/calendar")
    @_login_required
    def api_calendar(user):
        ano, mes = _periodo()
        dados_mes = get_welfares_mes(ano, mes)
        for lista in dados_mes.values():
            for welfare in lista:
                welfare["icones"] = TIPOS_WELFARE.get(welfare.get("tipo"), [])

        aniversarios = {}
        pessoas = db_rows(
            """
            SELECT id, nim, posto, nome, sobrenome, data_nascimento,
                   data_chegada, data_partida, antiguidade
            FROM utilizadores
            WHERE master=0 AND COALESCE(data_nascimento, '')<>''
            """
        )
        pessoas.sort(key=person_order_key)
        for pessoa in pessoas:
            try:
                nascimento = date.fromisoformat(str(pessoa["data_nascimento"])[:10])
                aniversario = date(ano, mes, nascimento.day)
            except (TypeError, ValueError):
                continue
            if nascimento.month != mes:
                continue
            chegada = str(pessoa.get("data_chegada") or "")[:10]
            partida = str(pessoa.get("data_partida") or "")[:10]
            data_str = aniversario.isoformat()
            if (chegada and data_str < chegada) or (partida and data_str > partida):
                continue
            aniversarios.setdefault(data_str, []).append(
                {"id": pessoa["id"], "identificacao": _identificacao(pessoa)}
            )
        return _json_ok(
            ano=ano, mes=mes,
            semanas=calendar.Calendar(firstweekday=0).monthdayscalendar(ano, mes),
            welfares=dados_mes,
            day_offs=sorted(get_day_offs_mes(ano, mes)),
            aniversarios=aniversarios,
            total=sum(len(lista) for lista in dados_mes.values()),
            teams=get_teams(),
            permissions={
                "editar": _pode_editar_welfare(user),
                "ementa": _pode_editar_ementa(user),
                "apagar": _pode_apagar_welfare(user),
            },
        )

    @app.get("/api/dashboard")
    @_login_required
    def api_dashboard(_user):
        hoje = date.today().isoformat()
        proximos = db_rows("""
            SELECT w.id, w.data, w.refeicao, w.tipo, w.prato, w.sobremesa,
                   w.local, w.recanto,
                   w.observacao, w.team_id, t.nome AS team_nome
            FROM welfares w LEFT JOIN teams t ON t.id=w.team_id
            WHERE w.data >= ?
            ORDER BY w.data, CASE w.refeicao WHEN 'Almoço' THEN 1 ELSE 2 END
            LIMIT 3
        """, (hoje,))
        teams = get_teams()
        membros_ids = [membro["id"] for team in teams for membro in team["membros"]]
        ferias_atuais = {}
        if membros_ids:
            membros_sql = ",".join("?" for _ in membros_ids)
            estados_atuais = tuple(vacations.APPROVED_STATUSES)
            estados_atuais_sql = ",".join("?" for _ in estados_atuais)
            periodos = db_rows(f"""
                SELECT utilizador_id, data_hora_inicio, data_hora_fim
                FROM ferias
                WHERE utilizador_id IN ({membros_sql})
                  AND estado IN ({estados_atuais_sql})
                  AND SUBSTR(data_hora_inicio, 1, 10)<=?
                  AND SUBSTR(data_hora_fim, 1, 10)>=?
                ORDER BY data_hora_inicio
            """, (*membros_ids, *estados_atuais, hoje, hoje))
            ferias_atuais = {
                periodo["utilizador_id"]: periodo for periodo in periodos
            }
        for team in teams:
            for membro in team["membros"]:
                periodo = ferias_atuais.get(membro["id"])
                membro["ferias"] = bool(periodo)
                membro["ferias_inicio"] = (periodo or {}).get("data_hora_inicio")
                membro["ferias_fim"] = (periodo or {}).get("data_hora_fim")
        teams_by_id = {team["id"]: team for team in teams}
        estados_ferias = tuple(vacations.APPROVED_STATUSES)
        placeholders = ",".join("?" for _ in estados_ferias)
        for welfare in proximos:
            welfare["icones"] = TIPOS_WELFARE.get(welfare.get("tipo"), [])
            # Uma Team de apoio só se aplica a refeições elaboradas no Recanto.
            if welfare.get("local") != "Recanto":
                welfare["team_id"] = None
                welfare["team_nome"] = None
                welfare["membros"] = []
                continue
            team = teams_by_id.get(welfare.get("team_id"))
            membros = [dict(item) for item in (team or {}).get("membros", [])]
            if membros:
                ids = [item["id"] for item in membros]
                ids_placeholders = ",".join("?" for _ in ids)
                ausentes = db_rows(f"""
                    SELECT DISTINCT utilizador_id FROM ferias
                    WHERE utilizador_id IN ({ids_placeholders})
                      AND estado IN ({placeholders})
                      AND SUBSTR(data_hora_inicio, 1, 10)<=?
                      AND SUBSTR(data_hora_fim, 1, 10)>=?
                """, (*ids, *estados_ferias, welfare["data"], welfare["data"]))
                ids_ferias = {item["utilizador_id"] for item in ausentes}
                for membro in membros:
                    membro["ferias"] = membro["id"] in ids_ferias
            welfare["membros"] = membros
        proximo_welfare = proximos[0] if proximos else None
        agora = datetime.now()
        hoje_data = agora.date().isoformat()
        service = IndividualService(agora.year, agora.month, _user, "welfare")
        individual_payload = service.para_payload()
        linha_pessoal = next(
            (linha for linha in individual_payload["linhas"] if int(linha["id"]) == int(_user["id"])),
            None,
        )
        estados = tuple(vacations.APPROVED_STATUSES)
        estados_sql = ",".join("?" for _ in estados)
        proximas_ferias = db_one(f"""
            SELECT id, data_hora_inicio, data_hora_fim, estado
            FROM ferias
            WHERE utilizador_id=? AND estado IN ({estados_sql})
              AND SUBSTR(data_hora_fim, 1, 10)>=?
            ORDER BY data_hora_inicio LIMIT 1
        """, (_user["id"], *estados, hoje_data))
        proximo_servico = db_one("""
            SELECT w.data, w.refeicao, w.tipo, w.local, t.id AS team_id,
                   t.nome AS team_nome
            FROM team_membros tm
            JOIN teams t ON t.id=tm.team_id
            JOIN welfares w ON w.team_id=t.id
            WHERE tm.utilizador_id=? AND w.data>=? AND w.local='Recanto'
            ORDER BY w.data, CASE w.refeicao WHEN 'Almoço' THEN 1 ELSE 2 END
            LIMIT 1
        """, (_user["id"], hoje_data))
        # Ao domingo, o fim de semana em curso começou no dia anterior. Nos
        # restantes dias procuramos a partir de hoje.
        inicio_escala = agora.date() - timedelta(days=1) if agora.weekday() == 6 else agora.date()
        proxima_loica = db_one("""
            SELECT fim_semana, militar_1_id, militar_2_id, validada
            FROM escala_loica
            WHERE fim_semana>=? AND (militar_1_id=? OR militar_2_id=?)
            ORDER BY fim_semana
            LIMIT 1
        """, (inicio_escala.isoformat(), _user["id"], _user["id"]))
        proximo_sabado = agora.date() + timedelta(days=(5 - agora.weekday()) % 7)
        if agora.weekday() == 6:
            proximo_sabado = agora.date() - timedelta(days=1)
        if proxima_loica:
            sabado_loica = date.fromisoformat(proxima_loica["fim_semana"])
            proxima_loica["domingo"] = (sabado_loica + timedelta(days=1)).isoformat()
            proxima_loica["posicao"] = (
                1 if int(proxima_loica.get("militar_1_id") or 0) == int(_user["id"]) else 2
            )
        resumo_pessoal = (linha_pessoal or {}).get("resumo") or {}
        caixa_resumo = cash_service.dashboard_summary(hoje_data)
        caixa_resumo["previsao_mes"] = (individual_payload.get("totais") or {}).get("caixa", 0)
        return _json_ok(
            proximos_welfares=proximos,
            teams=teams,
            proxima_team=proximo_welfare,
            proximo_welfare=proximo_welfare,
            pessoal={
                "proximo_servico": proximo_servico,
                "servico_hoje": bool(proximo_servico and proximo_servico["data"] == hoje_data),
                "proxima_loica": proxima_loica,
                "loica_proximo_fim_semana": bool(
                    proxima_loica
                    and proxima_loica["fim_semana"] == proximo_sabado.isoformat()
                ),
                "proximas_ferias": proximas_ferias,
                "welfares_mes": (
                    resumo_pessoal.get("welfare", 0)
                    + resumo_pessoal.get("cohesion", 0)
                ),
                "reembolso_mes": resumo_pessoal.get("reimbursement", 0),
                "caixa_mes": resumo_pessoal.get("caixa", 0),
            },
            caixa=caixa_resumo,
            regras_ferias=vacations.get_settings(),
        )

    def _periodo_caixa():
        hoje = date.today()
        inicio_padrao = hoje.replace(day=1)
        if hoje.month == 12:
            fim_padrao = date(hoje.year, 12, 31)
        else:
            fim_padrao = date(hoje.year, hoje.month + 1, 1) - timedelta(days=1)
        inicio = _data_iso(request.args.get("inicio") or inicio_padrao.isoformat(), obrigatoria=True)
        fim = _data_iso(request.args.get("fim") or fim_padrao.isoformat(), obrigatoria=True)
        if inicio > fim:
            raise ApiError("A data inicial não pode ser posterior à data final.")
        return inicio, fim

    @app.get("/api/cash")
    @_login_required
    def api_cash(user):
        if not _pode_gerir_caixa(user):
            raise ApiError("Não tens acesso à Gestão Caixa.", 403, "permissao")
        inicio, fim = _periodo_caixa()
        report = cash_service.balance(inicio, fim)
        service = IndividualService(int(inicio[:4]), int(inicio[5:7]), user, "welfare")
        report["previsao_mes"] = (service.para_payload().get("totais") or {}).get("caixa", 0)
        hoje = date.today().isoformat()
        pessoas = db_rows("""
            SELECT id, nim, posto, nome, sobrenome, antiguidade
            FROM utilizadores
            WHERE master=0
              AND COALESCE(data_chegada, '')<>''
              AND SUBSTR(data_chegada, 1, 10)<=?
              AND (COALESCE(data_partida, '')='' OR SUBSTR(data_partida, 1, 10)>=?)
        """, (hoje, hoje))
        pessoas.sort(key=person_order_key)
        report["pessoas"] = [
            {"id": pessoa["id"], "identificacao": _identificacao(pessoa)}
            for pessoa in pessoas
        ]
        return _json_ok(data=report)

    @app.get("/api/cash/consultation")
    @_login_required
    def api_cash_consultation(_user):
        inicio, fim = _periodo_caixa()
        return _json_ok(data=cash_service.balance(inicio, fim))

    @app.post("/api/cash")
    @_login_required
    def api_cash_create(user):
        if not _pode_gerir_caixa(user):
            raise ApiError("Não tens permissão para gerir a Caixa.", 403, "permissao")
        try:
            movement_id = cash_service.save(_body(), user)
        except ValueError as exc:
            raise ApiError(str(exc))
        return _json_ok(message="Movimento registado.", id=movement_id)

    @app.put("/api/cash/<int:movement_id>")
    @_login_required
    def api_cash_update(user, movement_id):
        if not _pode_gerir_caixa(user):
            raise ApiError("Não tens permissão para gerir a Caixa.", 403, "permissao")
        try:
            cash_service.save(_body(), user, movement_id)
        except ValueError as exc:
            raise ApiError(str(exc))
        return _json_ok(message="Movimento atualizado.")

    @app.delete("/api/cash/<int:movement_id>")
    @_login_required
    def api_cash_delete(user, movement_id):
        if not _pode_gerir_caixa(user):
            raise ApiError("Não tens permissão para gerir a Caixa.", 403, "permissao")
        try:
            cash_service.delete(movement_id)
        except ValueError as exc:
            raise ApiError(str(exc), 404)
        return _json_ok(message="Movimento eliminado.")

    @app.get("/api/cash.pdf")
    @_login_required
    def api_cash_pdf(user):
        if not _pode_gerir_caixa(user):
            raise ApiError("Não tens acesso à exportação da Caixa.", 403, "permissao")
        inicio, fim = _periodo_caixa()
        return _download_gerado(
            f"Balanco_Caixa_{inicio}_{fim}.pdf", ".pdf", "application/pdf",
            lambda caminho: cash_service.generate_pdf(inicio, fim, caminho),
        )

    def _team_payload():
        teams = get_teams()
        atribuidos = {m["id"] for team in teams for m in team["membros"]}
        hoje = date.today().isoformat()
        pessoas = db_rows("""
            SELECT id, nim, posto, nome, sobrenome, antiguidade,
                   data_chegada, data_partida
            FROM utilizadores
            WHERE master=0
              AND COALESCE(data_chegada, '')<>'' AND data_chegada<=?
              AND (COALESCE(data_partida, '')='' OR data_partida>=?)
        """, (hoje, hoje))
        pessoas.sort(key=person_order_key)
        for pessoa in pessoas:
            pessoa["identificacao"] = _identificacao(pessoa)
            pessoa["atribuido"] = pessoa["id"] in atribuidos
        return teams, pessoas

    @app.get("/api/teams")
    @_login_required
    def api_teams(_user):
        if not _pode_gerir_teams(_user):
            raise ApiError("Não tens permissão para gerir Teams.", 403, "permissao")
        teams, pessoas = _team_payload()
        return _json_ok(teams=teams, pessoas=pessoas)

    @app.post("/api/teams")
    @_login_required
    def api_create_team(user):
        if not _pode_gerir_teams(user):
            raise ApiError("Não tens permissão para gerir Teams.", 403, "permissao")
        nome = str(_body().get("nome") or "").strip()
        if not nome:
            raise ApiError("Indica o nome da Team.")
        try:
            team_id = db_execute_return_id("INSERT INTO teams (nome) VALUES (?)", (nome,))
        except sqlite3.IntegrityError:
            raise ApiError("Já existe uma Team com esse nome.", 409)
        return _json_ok(message="Team criada com sucesso.", id=team_id)

    @app.put("/api/teams/<int:team_id>")
    @_login_required
    def api_update_team(user, team_id):
        if not _pode_gerir_teams(user):
            raise ApiError("Não tens permissão para gerir Teams.", 403, "permissao")
        dados = _body()
        team = db_one("SELECT id FROM teams WHERE id=?", (team_id,))
        if not team:
            raise ApiError("Team não encontrada.", 404)
        nome = str(dados.get("nome") or "").strip()
        membros = dados.get("membros") or []
        try:
            membros = sorted({int(item) for item in membros})
        except (TypeError, ValueError):
            raise ApiError("Lista de elementos inválida.")
        if not nome:
            raise ApiError("Indica o nome da Team.")
        hoje = date.today().isoformat()
        # Uma pessoa deixa automaticamente a Team depois da data de partida.
        db_execute("""
            DELETE FROM team_membros
            WHERE utilizador_id IN (
                SELECT id FROM utilizadores
                WHERE COALESCE(data_partida, '')<>'' AND data_partida<?
            )
        """, (hoje,))
        if membros:
            placeholders = ",".join("?" for _ in membros)
            validos = db_rows(f"""
                SELECT id FROM utilizadores WHERE id IN ({placeholders}) AND master=0
                AND COALESCE(data_chegada, '')<>'' AND data_chegada<=?
                AND (COALESCE(data_partida, '')='' OR data_partida>=?)
            """, (*membros, hoje, hoje))
            if len(validos) != len(membros):
                raise ApiError("Só podes adicionar pessoas atualmente na missão.")
            conflito = db_one(f"""
                SELECT tm.utilizador_id, t.nome FROM team_membros tm
                JOIN teams t ON t.id=tm.team_id
                WHERE tm.utilizador_id IN ({placeholders}) AND tm.team_id<>? LIMIT 1
            """, (*membros, team_id))
            if conflito:
                raise ApiError(f"Um dos elementos já pertence à {conflito['nome']}.", 409)
        try:
            db_execute("UPDATE teams SET nome=? WHERE id=?", (nome, team_id))
            db_execute("DELETE FROM team_membros WHERE team_id=?", (team_id,))
            for membro_id in membros:
                db_execute("INSERT INTO team_membros (team_id, utilizador_id) VALUES (?, ?)", (team_id, membro_id))
        except sqlite3.IntegrityError:
            raise ApiError("Nome ou elemento já atribuído a outra Team.", 409)
        return _json_ok(message="Team atualizada com sucesso.")

    @app.delete("/api/teams/<int:team_id>")
    @_login_required
    def api_delete_team(user, team_id):
        if not _pode_gerir_teams(user):
            raise ApiError("Não tens permissão para gerir Teams.", 403, "permissao")
        db_execute("DELETE FROM teams WHERE id=?", (team_id,))
        return _json_ok(message="Team eliminada com sucesso.")

    @app.post("/api/welfares")
    @_login_required
    def api_save_welfare(user):
        dados = _body()
        data_str = _data_iso(dados.get("data"), obrigatoria=True)
        refeicao = str(dados.get("refeicao") or "")
        if refeicao not in ("Almoço", "Jantar"):
            raise ApiError("Refeição inválida.")
        tipo = str(dados.get("tipo") or "Welfare")
        if tipo not in TIPOS_WELFARE:
            raise ApiError("Tipo de Welfare inválido.")

        atual = get_welfare(data_str, refeicao)
        pode_completo = _pode_editar_welfare(user)
        pode_ementa = _pode_editar_ementa(user)
        if not pode_completo and not (pode_ementa and atual):
            raise ApiError("Não tens permissão para esta operação.", 403, "permissao")

        observacao = str(dados.get("observacao") or "").strip()
        local_raw = dados.get("local")
        local = (
            "Recanto" if tipo in ("Welfare", "Welfare Aniversário") else ""
        ) if local_raw is None else str(local_raw).strip()
        if local not in ("", "Recanto", "Restaurante", "Outro"):
            raise ApiError("Local inválido.")
        team_id = dados.get("team_id")
        try:
            team_id = int(team_id) if team_id not in (None, "") else None
        except (TypeError, ValueError):
            raise ApiError("Team inválida.")
        if team_id is not None and not db_one("SELECT id FROM teams WHERE id=?", (team_id,)):
            raise ApiError("Team inválida.")
        if not pode_completo:
            tipo = atual["tipo"]
            observacao = atual.get("observacao") or ""
            team_id = atual.get("team_id")
            local = atual.get("local") or ""

        guardar_welfare(
            data_str,
            refeicao,
            tipo,
            str(dados.get("prato") or "").strip(),
            str(dados.get("sobremesa") or "").strip(),
            observacao,
            team_id,
            local,
        )
        return _json_ok(message="Welfare guardado com sucesso.")

    @app.delete("/api/welfares")
    @_login_required
    def api_delete_welfare(user):
        dados = _body()
        data_str = _data_iso(dados.get("data"), obrigatoria=True)
        refeicao = str(dados.get("refeicao") or "")
        if refeicao not in ("Almoço", "Jantar"):
            raise ApiError("Refeição inválida.")
        if not _pode_apagar_welfare(user):
            raise ApiError("Não tens permissão para eliminar.", 403, "permissao")
        eliminar_welfare(data_str, refeicao)
        return _json_ok(message="Welfare eliminado com sucesso.")

    @app.post("/api/individual/month-lock")
    @_login_required
    def api_month_lock(user):
        if not _pode_trancar_individual(user):
            raise ApiError(
                "Apenas Administradores e Responsáveis Welfare podem trancar meses.",
                403,
                "permissao",
            )
        dados = _body()
        ano, mes = _periodo(dados.get("ano"), dados.get("mes"))
        trancado = bool(dados.get("trancado"))
        set_mes_trancado(ano, mes, trancado)
        return _json_ok(trancado=trancado)

    @app.get("/api/export/month.pdf")
    @_login_required
    def api_export_month(_user):
        ano, mes = _periodo()
        nome = f"SIGCP_{ano}_{mes:02d}.pdf"
        return _download_gerado(
            nome,
            ".pdf",
            "application/pdf",
            lambda caminho: gerar_pdf_mes(ano, mes, output_path=caminho),
        )

    @app.get("/api/dish-roster")
    @_login_required
    def api_dish_roster(user):
        ano, mes = _periodo()
        return _json_ok(data=dish_roster.payload(
            ano, mes, current_user_id=user["id"],
            manager=_pode_gerir_escala_loica(user),
            administrator=_is_admin(user),
        ))

    @app.put("/api/dish-roster")
    @_login_required
    def api_save_dish_roster(user):
        if not _pode_gerir_escala_loica(user):
            raise ApiError("Não tens permissão para alterar a Escala Loiça.", 403, "permissao")
        dados = _body()
        ano, mes = _periodo(dados.get("ano"), dados.get("mes"))
        linhas = dados.get("linhas")
        if not isinstance(linhas, list) or len(linhas) > 30:
            raise ApiError("Lista da escala inválida.")
        try:
            dish_roster.save_rows(ano, mes, linhas)
            dish_roster.generate(ano, mes)
        except (TypeError, ValueError) as exc:
            raise ApiError(str(exc))
        return _json_ok(message="Escala Loiça guardada com sucesso.")

    @app.post("/api/dish-roster/generate")
    @_login_required
    def api_generate_dish_roster(user):
        if not _pode_gerir_escala_loica(user):
            raise ApiError("Não tens permissão para atualizar a previsão.", 403, "permissao")
        dados = _body()
        ano, mes = _periodo(dados.get("ano"), dados.get("mes"))
        dish_roster.generate(ano, mes, rebuild_forecast=True)
        return _json_ok(message="Escala refeita a partir da última validação em vigor.")

    @app.put("/api/dish-roster/<weekend>/validation")
    @_login_required
    def api_validate_dish_roster(user, weekend):
        if not _pode_gerir_escala_loica(user):
            raise ApiError("Não tens permissão para validar a escala.", 403, "permissao")
        weekend = _data_iso(weekend, obrigatoria=True)
        row = dish_roster.get_row(weekend)
        if not row:
            raise ApiError("Fim de semana não encontrado.", 404)
        validada = bool(_body().get("validada"))
        dish_roster.set_validation(weekend, validada)
        return _json_ok(message="Validação atualizada.")

    @app.put("/api/dish-roster/<weekend>/signature/<int:slot>")
    @_login_required
    def api_sign_dish_roster(user, weekend, slot):
        weekend = _data_iso(weekend, obrigatoria=True)
        if slot not in (1, 2):
            raise ApiError("Assinatura inválida.")
        row = dish_roster.get_row(weekend)
        if not row:
            raise ApiError("Fim de semana não encontrado.", 404)
        if not _is_admin(user) and date.today().isoformat() != weekend:
            raise ApiError("A assinatura só fica disponível no sábado do serviço.", 403)
        assigned = row.get(f"militar_{slot}_id")
        if not (_pode_gerir_escala_loica(user) or assigned and int(assigned) == int(user["id"])):
            raise ApiError("Não tens permissão para esta assinatura.", 403, "permissao")
        dish_roster.set_signature(weekend, slot, bool(_body().get("assinada")))
        return _json_ok(message="Assinatura atualizada.")

    @app.get("/api/dish-roster.pdf")
    @_login_required
    def api_dish_roster_pdf(_user):
        ano, mes = _periodo()
        return _download_gerado(
            f"Escala_Loica_{ano}_{mes:02d}.pdf", ".pdf", "application/pdf",
            lambda caminho: dish_roster.generate_pdf(ano, mes, caminho),
        )

    def listar_utilizadores(mostrar_todos):
        hoje = date.today().isoformat()
        ativo = (
            "(data_partida IS NULL OR TRIM(data_partida) = '' "
            "OR SUBSTR(data_partida, 1, 10) >= ?)"
        )
        if mostrar_todos:
            rows = db_rows("SELECT * FROM utilizadores")
        else:
            rows = db_rows(
                f"""
                SELECT * FROM utilizadores
                WHERE {ativo}
                """,
                (hoje,),
            )
        rows.sort(key=person_order_key)
        return [_safe_user(row) for row in rows]

    @app.get("/api/users")
    @_personnel_view_required
    def api_users(_user):
        mostrar_todos = request.args.get("todos", "0").lower() in ("1", "true", "yes")
        return _json_ok(users=listar_utilizadores(mostrar_todos))

    @app.get("/api/users/<int:user_id>")
    @_personnel_view_required
    def api_user(_current, user_id):
        user = db_one("SELECT * FROM utilizadores WHERE id = ?", (user_id,))
        if not user:
            raise ApiError("Utilizador não encontrado.", 404)
        return _json_ok(user=_safe_user(user))

    def guardar_utilizador(current, user_id=None):
        dados = _body()
        existente = (
            db_one("SELECT * FROM utilizadores WHERE id = ?", (user_id,))
            if user_id
            else None
        )
        if user_id and not existente:
            raise ApiError("Utilizador não encontrado.", 404)
        if existente and int(existente.get("master") or 0):
            raise ApiError("O utilizador mestre é inalterável.", 403, "protegido")

        nim = str(dados.get("nim") or "").strip()
        if not nim:
            raise ApiError("O NIM é obrigatório.")
        posto = str(dados.get("posto") or "").strip()
        if posto and posto not in POSTOS:
            raise ApiError("Posto inválido.")
        antiguidade = _data_iso(dados.get("antiguidade"))
        data_nascimento = _data_iso(dados.get("data_nascimento"))
        chegada = _data_hora(dados.get("data_chegada"))
        partida = _data_hora(dados.get("data_partida"))
        if _is_admin(current):
            snr = 1 if dados.get("snr") else 0
            responsavel = 1 if dados.get("responsavel_welfare") else 0
        else:
            # Estas funções só podem ser atribuídas por um Administrador.
            snr = int((existente or {}).get("snr") or 0)
            responsavel = int((existente or {}).get("responsavel_welfare") or 0)
        snr_substituto, snr_substituto_inicio, snr_substituto_fim = (
            _valores_substituicao_snr(current, existente, dados)
        )
        telemovel = str(dados.get("telemovel_servico") or "").strip()
        area_funcional = str(dados.get("area_funcional") or "Não definido").strip()[:120]
        area_funcional = area_funcional or "Não definido"
        posicao_numero = str(dados.get("posicao_numero") or "").strip()[:40]
        direito_raw = dados.get("ferias_direito_override")
        if direito_raw in (None, ""):
            direito_override = None
        else:
            try:
                direito_override = float(str(direito_raw).replace(",", "."))
            except (TypeError, ValueError):
                raise ApiError("O Total de dias Férias (manual) deve ser um número.")
            if not 0 <= direito_override <= 365:
                raise ApiError("O Total de dias Férias (manual) deve estar entre 0 e 365 dias.")
        missao_prorrogada = 1 if dados.get("missao_prorrogada") else 0
        notas_ferias = str(dados.get("notas_ferias") or "").strip()[:1000]
        if responsavel and not telemovel:
            raise ApiError(
                "O Telemóvel Serviço é obrigatório para o Responsável Welfare."
            )

        if _is_admin(current):
            acessos = [
                acesso
                for acesso in dados.get("acessos", [])
                if acesso in TIPOS_ACESSO
            ]
            if not acessos:
                raise ApiError("Seleciona pelo menos um Tipo de Acesso.")
        elif existente:
            acessos = get_utilizador_acessos(existente["id"]) or ["Leitura"]
        else:
            acessos = ["Leitura"]

        password = str(dados.get("password") or "")
        confirmar = str(dados.get("confirmar_password") or "")
        if password != confirmar:
            raise ApiError("As passwords não coincidem.")
        if not existente and not password:
            raise ApiError("A password é obrigatória para um novo utilizador.")

        valores = (
            nim,
            posto,
            antiguidade,
            snr,
            snr_substituto,
            snr_substituto_inicio,
            snr_substituto_fim,
            telemovel,
            responsavel,
            area_funcional,
            posicao_numero,
            direito_override,
            missao_prorrogada,
            notas_ferias,
            str(dados.get("nome") or "").strip(),
            str(dados.get("sobrenome") or "").strip(),
            data_nascimento,
            chegada,
            partida,
            ", ".join(acessos),
        )
        try:
            if existente:
                if password:
                    salt, pwd_hash = hash_password(password)
                    db_execute(
                        """
                        UPDATE utilizadores SET
                            nim=?, posto=?, antiguidade=?, snr=?,
                            snr_substituto=?, snr_substituto_inicio=?, snr_substituto_fim=?,
                            telemovel_servico=?, responsavel_welfare=?,
                            area_funcional=?, posicao_numero=?, ferias_direito_override=?,
                            missao_prorrogada=?, notas_ferias=?,
                            nome=?, sobrenome=?, data_nascimento=?, data_chegada=?, data_partida=?,
                            tipo_acesso=?, password_salt=?, password_hash=?
                        WHERE id=? AND master=0
                        """,
                        valores + (salt, pwd_hash, existente["id"]),
                    )
                else:
                    db_execute(
                        """
                        UPDATE utilizadores SET
                            nim=?, posto=?, antiguidade=?, snr=?,
                            snr_substituto=?, snr_substituto_inicio=?, snr_substituto_fim=?,
                            telemovel_servico=?, responsavel_welfare=?,
                            area_funcional=?, posicao_numero=?, ferias_direito_override=?,
                            missao_prorrogada=?, notas_ferias=?,
                            nome=?, sobrenome=?, data_nascimento=?, data_chegada=?, data_partida=?,
                            tipo_acesso=?
                        WHERE id=? AND master=0
                        """,
                        valores + (existente["id"],),
                    )
                novo_id = existente["id"]
            else:
                salt, pwd_hash = hash_password(password)
                novo_id = db_execute_return_id(
                    """
                    INSERT INTO utilizadores (
                        nim, posto, antiguidade, snr,
                        snr_substituto, snr_substituto_inicio, snr_substituto_fim,
                        telemovel_servico,
                        responsavel_welfare, area_funcional,
                        posicao_numero, ferias_direito_override, missao_prorrogada, notas_ferias,
                        nome, sobrenome, data_nascimento, data_chegada,
                        data_partida, tipo_acesso, password_salt,
                        password_hash, master
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                    """,
                    valores + (salt, pwd_hash),
                )
            set_utilizador_acessos(novo_id, acessos)
        except sqlite3.IntegrityError:
            raise ApiError("Já existe um utilizador com esse NIM.", 409, "duplicado")

        return _safe_user(db_one("SELECT * FROM utilizadores WHERE id=?", (novo_id,)))

    @app.post("/api/users")
    @_personnel_required
    def api_create_user(current):
        return _json_ok(
            user=guardar_utilizador(current),
            message="Utilizador criado com sucesso.",
        )

    @app.put("/api/users/<int:user_id>")
    @_personnel_required
    def api_update_user(current, user_id):
        return _json_ok(
            user=guardar_utilizador(current, user_id),
            message="Utilizador guardado com sucesso.",
        )

    @app.put("/api/users/<int:user_id>/snr-substitution")
    @_login_required
    def api_update_snr_substitution(current, user_id):
        if not _pode_nomear_substituto_snr(current):
            raise ApiError(
                "Apenas um Administrador ou o SNR titular pode nomear um substituto.",
                403,
                "permissao",
            )
        person = db_one(
            "SELECT * FROM utilizadores WHERE id=? AND master=0", (user_id,)
        )
        if not person:
            raise ApiError("Pessoa não encontrada.", 404)
        nomeado, inicio, fim = _valores_substituicao_snr(
            current, person, _body()
        )
        db_execute(
            """
            UPDATE utilizadores
            SET snr_substituto=?, snr_substituto_inicio=?, snr_substituto_fim=?
            WHERE id=? AND master=0
            """,
            (nomeado, inicio, fim, user_id),
        )
        g.audit_action = (
            "Substituto SNR nomeado" if nomeado else "Substituição SNR limpa"
        )
        return _json_ok(
            user=_safe_user(db_one("SELECT * FROM utilizadores WHERE id=?", (user_id,))),
            message=(
                "Substituição do SNR guardada."
                if nomeado
                else "Substituição do SNR limpa."
            ),
        )

    @app.delete("/api/users/<int:user_id>")
    @_personnel_required
    def api_delete_user(_current, user_id):
        user = db_one("SELECT * FROM utilizadores WHERE id = ?", (user_id,))
        if not user:
            raise ApiError("Utilizador não encontrado.", 404)
        if int(user.get("master") or 0):
            raise ApiError("O utilizador mestre não pode ser eliminado.", 403)
        db_execute("DELETE FROM utilizadores WHERE id = ?", (user_id,))
        return _json_ok(message="Utilizador eliminado.")

    @app.get("/api/settings")
    @_admin_required
    def api_settings(_user):
        settings = {
                "valor_welfare": get_valor_welfare(),
                "valor_caixa": get_valor_caixa(),
                "nome_cos": get_nome_cos(),
                "inicio_semana": get_inicio_semana(),
                "lingua": get_lingua(),
                "horario_dfac": get_horario_dfac(),
                "update_folder": get_setting("update_folder", ""),
                "app_version": app_config.APP_VERSION,
        }
        if _user.get("virtual_master"):
            settings.update(
                database_path=app_config.DB_PATH,
                database_mode=app_config.DATABASE_MODE,
                supabase_url=app_config.SUPABASE_URL,
                supabase_key=app_config.SUPABASE_KEY,
            )
        return _json_ok(settings=settings)

    @app.put("/api/settings")
    @_admin_required
    def api_update_settings(_user):
        dados = _body()
        restart_required = False
        campos_base = {"database_mode", "database_path", "supabase_url", "supabase_key"}
        if campos_base.intersection(dados) and not _user.get("virtual_master"):
            raise ApiError(
                "A configuração da base de dados está reservada ao superadministrador.",
                403,
                "superadmin",
            )
        if any(k in dados for k in ("database_mode", "supabase_url", "supabase_key")):
            modo = str(dados.get("database_mode") or app_config.DATABASE_MODE).lower()
            if modo not in ("local", "supabase"):
                raise ApiError("Tipo de base de dados inválido.")
            url = str(dados.get("supabase_url") or "").strip().rstrip("/")
            chave = str(dados.get("supabase_key") or "").strip()
            if modo == "supabase" and (not url.startswith("https://") or not chave):
                raise ApiError("Indique um Project URL HTTPS e uma Publishable Key válidos.")
            local = app_config._ler_config_local()
            local.update(database_mode=modo, supabase_url=url, supabase_key=chave)
            app_config._guardar_config_local(local)
            restart_required = restart_required or modo != app_config.DATABASE_MODE or url != app_config.SUPABASE_URL or chave != app_config.SUPABASE_KEY
        if "valor_welfare" in dados:
            valor = str(dados["valor_welfare"] or "").strip()
            if valor and not valor.isdigit():
                raise ApiError("O Valor Welfare deve conter apenas números.")
            set_valor_welfare(valor)
        if "valor_caixa" in dados:
            valor = str(dados["valor_caixa"] or "").strip()
            if valor and not valor.isdigit():
                raise ApiError("O Valor Caixa deve conter apenas números.")
            set_valor_caixa(valor)
        if "nome_cos" in dados:
            set_nome_cos(str(dados["nome_cos"] or "").strip())
        if "inicio_semana" in dados:
            set_inicio_semana(_data_iso(dados["inicio_semana"]))
        if "lingua" in dados:
            lingua = str(dados["lingua"] or "")
            if lingua not in ("pt", "en"):
                raise ApiError("Língua inválida.")
            set_lingua(lingua)
        if "horario_dfac" in dados:
            recebido = dados["horario_dfac"]
            horario = {"normal": {}, "especial": {}}
            for tipo in horario:
                for refeicao in ("pequeno_almoco", "almoco", "jantar"):
                    valores = ((recebido or {}).get(tipo) or {}).get(refeicao) or {}
                    horario[tipo][refeicao] = {
                        "abertura": _validar_hora(valores.get("abertura")),
                        "fecho": _validar_hora(valores.get("fecho")),
                    }
            set_horario_dfac(horario)
        if "database_path" in dados:
            caminho_recebido = os.path.abspath(
                os.path.expandvars(str(dados["database_path"] or "").strip())
            )
            if not caminho_recebido or not os.path.isfile(caminho_recebido):
                raise ApiError("O ficheiro de base de dados indicado não existe.")
            try:
                conn_teste = app_config.abrir_base_dados_somente_leitura(
                    caminho_recebido
                )
                conn_teste.execute("SELECT name FROM sqlite_master LIMIT 1").fetchone()
                conn_teste.close()
            except sqlite3.Error as exc:
                raise ApiError(f"O ficheiro indicado não é uma base SQLite válida: {exc}")

            restart_required = os.path.normcase(caminho_recebido) != os.path.normcase(
                app_config.DB_PATH
            )
            if restart_required:
                config_local = app_config._ler_config_local()
                config_local["database_path"] = caminho_recebido
                app_config._guardar_config_local(config_local)

        if "update_folder" in dados:
            pasta_updates = os.path.abspath(
                os.path.expandvars(os.path.expanduser(str(dados["update_folder"] or "").strip()))
            ) if str(dados["update_folder"] or "").strip() else ""
            if pasta_updates:
                if not os.path.isdir(pasta_updates):
                    raise ApiError("A pasta partilhada das atualizações não existe.")
                executavel_publicado = os.path.join(pasta_updates, "SIGCP.exe")
                if not os.path.isfile(executavel_publicado):
                    raise ApiError("A pasta indicada não contém o ficheiro SIGCP.exe.")
            config_local = app_config._ler_config_local()
            config_local["update_folder"] = pasta_updates
            app_config._guardar_config_local(config_local)
            set_setting("update_folder", pasta_updates)

        return _json_ok(
            message="Configuração guardada com sucesso.",
            restart_required=restart_required,
        )

    @app.post("/api/settings/select-update-executable")
    @_admin_required
    def api_select_update_executable(_user):
        root = None
        try:
            root = Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            caminho = filedialog.askopenfilename(
                parent=root,
                title="Selecionar o SIGCP.exe publicado",
                filetypes=[("Executável SIGCP", "SIGCP.exe"), ("Executáveis", "*.exe")],
            )
        finally:
            if root is not None:
                root.destroy()
        if not caminho:
            return _json_ok(cancelled=True)
        caminho = os.path.abspath(caminho)
        if os.path.basename(caminho).lower() != "sigcp.exe":
            raise ApiError("Seleciona um ficheiro chamado SIGCP.exe.")
        pasta_updates = os.path.dirname(caminho)
        config_local = app_config._ler_config_local()
        config_local["update_folder"] = pasta_updates
        app_config._guardar_config_local(config_local)
        set_setting("update_folder", pasta_updates)
        comparison = "indisponivel"
        if getattr(sys, "frozen", False) and os.path.isfile(sys.executable):
            try:
                comparison = (
                    "igual"
                    if filecmp.cmp(caminho, sys.executable, shallow=False)
                    else "diferente"
                )
            except OSError:
                comparison = "indisponivel"
        return _json_ok(
            cancelled=False,
            executable_path=caminho,
            update_folder=pasta_updates,
            comparison=comparison,
            available_version=app_config.get_executable_version(caminho) or "desconhecida",
            installed_version=app_config.APP_VERSION,
            message="Localização das atualizações guardada.",
        )

    @app.get("/api/day-offs")
    @_admin_required
    def api_day_offs(_user):
        todos = request.args.get("todos", "0").lower() in ("1", "true")
        return _json_ok(day_offs=get_day_offs(todos))

    @app.post("/api/day-offs")
    @_admin_required
    def api_create_day_off(_user):
        dados = _body()
        try:
            guardar_day_off(
                _data_iso(dados.get("data"), obrigatoria=True),
                str(dados.get("observacao") or "").strip(),
            )
        except sqlite3.IntegrityError:
            raise ApiError("Já existe um Day Off nessa data.", 409, "duplicado")
        return _json_ok(message="Day Off guardado.")

    @app.put("/api/day-offs/<int:day_off_id>")
    @_admin_required
    def api_update_day_off(_user, day_off_id):
        if not get_day_off(day_off_id):
            raise ApiError("Day Off não encontrado.", 404)
        dados = _body()
        try:
            guardar_day_off(
                _data_iso(dados.get("data"), obrigatoria=True),
                str(dados.get("observacao") or "").strip(),
                day_off_id,
            )
        except sqlite3.IntegrityError:
            raise ApiError("Já existe um Day Off nessa data.", 409, "duplicado")
        return _json_ok(message="Day Off guardado.")

    @app.delete("/api/day-offs/<int:day_off_id>")
    @_admin_required
    def api_delete_day_off(_user, day_off_id):
        if not get_day_off(day_off_id):
            raise ApiError("Day Off não encontrado.", 404)
        eliminar_day_off(day_off_id)
        return _json_ok(message="Day Off eliminado.")

    def vacation_detail(vacation_id):
        rows = vacations.list_requests(vacation_id=vacation_id)
        return next((item for item in rows if item["id"] == int(vacation_id)), None)

    @app.get("/api/vacations/me")
    @_login_required
    def api_my_vacations(user):
        if int(user.get("master") or 0):
            raise ApiError("O utilizador mestre não possui uma área privada de férias.", 403)
        try:
            year = int(request.args.get("ano") or vacations.get_settings()["ano_calendario"])
        except ValueError:
            raise ApiError("Indica um ano válido.")
        show_all = request.args.get("todos", "").strip().lower() in {"1", "true", "sim"}
        return _json_ok(
            data=vacations.private_payload(user["id"], year, show_all=show_all)
        )

    @app.get("/api/vacations/manage")
    @_login_required
    def api_manage_vacations(_user):
        if not _pode_ver_gestao_ferias(_user):
            raise ApiError("Não tens permissão para consultar a gestão de férias.", 403, "permissao")
        try:
            year = int(request.args.get("ano") or vacations.get_settings()["ano_calendario"])
        except ValueError:
            raise ApiError("Indica um ano válido.")
        status = str(request.args.get("estado") or "").strip()
        show_all = request.args.get("todos", "").strip().lower() in {"1", "true", "sim"}
        return _json_ok(
            data=vacations.management_payload(
                year=year,
                status=status or None,
                status_group=str(request.args.get("grupo_estado") or "all"),
                search=str(request.args.get("pesquisa") or ""),
                area=str(request.args.get("area") or ""),
                show_all=show_all,
            )
        )

    # Compatibilidade com o endereço usado pela primeira versão web.
    @app.get("/api/vacations")
    @_vacation_manager_required
    def api_vacations_legacy(_user):
        return _json_ok(data=vacations.management_payload())

    @app.get("/api/vacations/calendar")
    @_login_required
    def api_vacations_calendar(user):
        ano, mes = _periodo()
        all_people = request.args.get("scope") == "all"
        if all_people and not _pode_ver_gestao_ferias(user):
            raise ApiError("Não tens acesso ao calendário global de férias.", 403)
        member_id = None if all_people else user["id"]
        if member_id and int(user.get("master") or 0):
            raise ApiError("O utilizador mestre não possui férias individuais.", 403)
        return _json_ok(data=vacations.calendar_payload(ano, mes, member_id=member_id))

    @app.get("/api/vacations/<int:feria_id>")
    @_login_required
    def api_vacation_detail(user, feria_id):
        item = vacation_detail(feria_id)
        if not item:
            raise ApiError("Pedido não encontrado.", 404)
        if int(item["utilizador_id"]) != int(user["id"]) and not _pode_ver_gestao_ferias(user):
            raise ApiError("Não tens acesso a este pedido.", 403)
        return _json_ok(data=item)

    @app.post("/api/vacations")
    @_login_required
    def api_create_vacation(user):
        dados = _body()
        target_id = dados.get("utilizador_id") or user["id"]
        try:
            target_id = int(target_id)
        except (TypeError, ValueError):
            raise ApiError("Seleciona uma pessoa.")
        if target_id != int(user["id"]) and not _pode_gerir_ferias(user):
            raise ApiError("Só podes criar pedidos para a tua área privada.", 403)
        if target_id == int(user["id"]) and int(user.get("master") or 0):
            raise ApiError("Seleciona uma pessoa para o pedido.")
        vacation_id, validation = vacations.create_request(
            user,
            target_id,
            dados,
            accept_warnings=bool(dados.get("accept_warnings")),
        )
        return _json_ok(
            id=vacation_id,
            warnings=validation["warnings"],
            message=(
                "Férias aprovadas automaticamente."
                if target_id == int(user["id"]) and _is_snr_titular(user)
                else "Pedido de férias submetido para aprovação."
            ),
        )

    @app.put("/api/vacations/<int:feria_id>")
    @_login_required
    def api_update_vacation(user, feria_id):
        dados = _body()
        validation = vacations.update_request(
            user,
            feria_id,
            dados,
            can_manage=_pode_gerir_ferias(user),
            accept_warnings=bool(dados.get("accept_warnings")),
        )
        return _json_ok(
            warnings=validation["warnings"],
            message="Pedido corrigido e submetido novamente.",
        )

    @app.delete("/api/vacations/<int:feria_id>")
    @_login_required
    def api_delete_vacation(user, feria_id):
        if _is_admin(user):
            item = vacation_detail(feria_id)
            if not item:
                raise ApiError("Pedido não encontrado.", 404)
            g.audit_action = "Período de férias apagado definitivamente"
            g.audit_extra = {
                "feria_id": item["id"],
                "utilizador_id": item["utilizador_id"],
                "pessoa": item.get("identificacao") or item.get("nim"),
                "inicio": item.get("data_hora_inicio"),
                "fim": item.get("data_hora_fim"),
                "estado": item.get("estado"),
            }
            vacations.delete_request(feria_id)
            return _json_ok(message="Período de férias apagado definitivamente.")
        vacations.withdraw_request(user, feria_id)
        return _json_ok(message="Pedido retirado.")

    @app.post("/api/vacations/<int:feria_id>/withdraw")
    @_login_required
    def api_withdraw_vacation(user, feria_id):
        dados = _body()
        vacations.withdraw_request(user, feria_id, dados.get("reason"))
        return _json_ok(message="Pedido retirado.")

    @app.post("/api/vacations/<int:feria_id>/decision")
    @_vacation_decision_required
    def api_vacation_decision(user, feria_id):
        dados = _body()
        vacations.decide_request(user, feria_id, dados.get("action"), dados.get("note"))
        return _json_ok(message="Decisão registada com sucesso.")

    @app.put("/api/vacations/<int:feria_id>/hours")
    @_login_required
    def api_vacation_update_hours(user, feria_id):
        if not _pode_atualizar_horas_ferias(user):
            raise ApiError("Não tens permissão para atualizar as horas das férias.", 403, "permissao")
        dados = _body()
        vacations.update_approved_times(
            user, feria_id, dados.get("hora_partida"), dados.get("hora_chegada")
        )
        return _json_ok(message="Horas do período de férias atualizadas.")

    @app.post("/api/vacations/<int:feria_id>/change-request")
    @_login_required
    def api_vacation_change_request(user, feria_id):
        dados = _body()
        periodo = db_one("SELECT utilizador_id FROM ferias WHERE id=?", (feria_id,))
        alteracao_propria_snr = bool(
            periodo
            and int(periodo["utilizador_id"]) == int(user["id"])
            and _is_snr_titular(user)
        )
        validation = vacations.request_change(
            user,
            feria_id,
            dados,
            dados.get("reason"),
            can_manage=_pode_gerir_ferias(user),
            accept_warnings=bool(dados.get("accept_warnings")),
        )
        return _json_ok(
            warnings=validation["warnings"],
            message=(
                "Alteração aprovada automaticamente."
                if alteracao_propria_snr
                else "Alteração submetida para aprovação."
            ),
        )

    @app.post("/api/vacations/<int:feria_id>/change-decision")
    @_vacation_decision_required
    def api_vacation_change_decision(user, feria_id):
        dados = _body()
        vacations.decide_change(user, feria_id, dados.get("action"), dados.get("note"))
        return _json_ok(message="Decisão sobre a alteração registada.")

    @app.post("/api/vacations/<int:feria_id>/cancellation-request")
    @_login_required
    def api_vacation_cancellation_request(user, feria_id):
        dados = _body()
        vacations.request_cancellation(
            user,
            feria_id,
            dados.get("reason"),
            can_manage=_pode_gerir_ferias(user),
        )
        return _json_ok(message="Cancelamento submetido para aprovação.")

    @app.post("/api/vacations/<int:feria_id>/cancellation-decision")
    @_vacation_decision_required
    def api_vacation_cancellation_decision(user, feria_id):
        dados = _body()
        vacations.decide_cancellation(
            user, feria_id, dados.get("action"), dados.get("note")
        )
        return _json_ok(message="Decisão sobre o cancelamento registada.")

    @app.post("/api/vacations/<int:feria_id>/annul")
    @_admin_required
    def api_vacation_annul(user, feria_id):
        dados = _body()
        vacations.annul_approved(user, feria_id, dados.get("reason"))
        return _json_ok(message="Período aprovado anulado.")

    @app.post("/api/vacations/<int:feria_id>/restore")
    @_vacation_decision_required
    def api_vacation_restore(user, feria_id):
        vacations.restore_annulled(user, feria_id)
        return _json_ok(message="Anulação revertida com sucesso.")

    @app.get("/api/vacations/settings")
    @_vacation_manager_required
    def api_vacation_settings(_user):
        return _json_ok(settings=vacations.get_settings())

    @app.put("/api/vacations/settings")
    @_admin_required
    def api_save_vacation_settings(_user):
        return _json_ok(
            settings=vacations.save_settings(_body()),
            message="Regras de férias guardadas.",
        )

    @app.put("/api/vacations/people/<int:user_id>")
    @_vacation_manager_required
    def api_save_vacation_person(current, user_id):
        person = db_one(
            "SELECT * FROM utilizadores WHERE id=? AND master=0", (user_id,)
        )
        if not person:
            raise ApiError("Pessoa não encontrada.", 404)
        dados = _body()
        mission_start = _data_hora(dados.get("data_chegada"))
        mission_end = _data_hora(dados.get("data_partida"))
        if mission_start and mission_end:
            start_dt = datetime.strptime(
                mission_start if len(mission_start) >= 16 else f"{mission_start} 00:00",
                "%Y-%m-%d %H:%M",
            )
            end_dt = datetime.strptime(
                mission_end if len(mission_end) >= 16 else f"{mission_end} 00:00",
                "%Y-%m-%d %H:%M",
            )
            if end_dt < start_dt:
                raise ApiError("O fim da missão não pode anteceder o início.")
        direito_raw = dados.get("ferias_direito_override")
        if direito_raw in (None, ""):
            direito = None
        else:
            try:
                direito = float(str(direito_raw).replace(",", "."))
            except (TypeError, ValueError):
                raise ApiError("O Total de dias Férias (manual) deve ser um número.")
            if not 0 <= direito <= 365:
                raise ApiError("O Total de dias Férias (manual) deve estar entre 0 e 365 dias.")
        area = str(dados.get("area_funcional") or "Não definido").strip()[:120]
        posicao_numero = str(dados.get("posicao_numero") or "").strip()[:40]
        snr_substituto, snr_substituto_inicio, snr_substituto_fim = (
            _valores_substituicao_snr(current, person, dados)
        )
        db_execute(
            """
            UPDATE utilizadores SET area_funcional=?, posicao_numero=?, data_chegada=?, data_partida=?,
                ferias_direito_override=?, missao_prorrogada=?, notas_ferias=?,
                snr_substituto=?, snr_substituto_inicio=?, snr_substituto_fim=?
            WHERE id=? AND master=0
            """,
            (
                area or "Não definido",
                posicao_numero,
                mission_start,
                mission_end,
                direito,
                1 if dados.get("missao_prorrogada") else 0,
                str(dados.get("notas_ferias") or "").strip()[:1000],
                snr_substituto,
                snr_substituto_inicio,
                snr_substituto_fim,
                user_id,
            ),
        )
        return _json_ok(message="Dados de férias da pessoa guardados.")

    @app.get("/api/vacations/holidays")
    @_login_required
    def api_vacation_holidays(_user):
        year = request.args.get("ano")
        try:
            year = int(year) if year else None
        except ValueError:
            raise ApiError("Indica um ano válido.")
        return _json_ok(holidays=vacations.get_holidays(year=year))

    @app.post("/api/vacations/holidays")
    @_vacation_manager_required
    def api_create_vacation_holiday(_user):
        dados = _body()
        holiday_date = _data_iso(dados.get("data"), obrigatoria=True)
        description = str(dados.get("descricao") or "").strip()
        if not description:
            raise ApiError("Indica a descrição do feriado.")
        try:
            holiday_id = db_execute_return_id(
                "INSERT INTO feriados (data, descricao, ativo) VALUES (?, ?, ?)",
                (holiday_date, description[:160], 1 if dados.get("ativo", True) else 0),
            )
        except sqlite3.IntegrityError:
            raise ApiError("Já existe um feriado nessa data.", 409, "duplicado")
        return _json_ok(id=holiday_id, message="Feriado criado.")

    @app.get("/api/vacations/holidays/import-preview")
    @_admin_required
    def api_preview_portugal_holidays(_user):
        try:
            year = int(request.args.get("ano") or date.today().year)
        except (TypeError, ValueError):
            raise ApiError("Indica um ano válido.")
        if year < 1900 or year > 2200:
            raise ApiError("O ano deve estar entre 1900 e 2200.")
        url = f"https://date.nager.at/api/v3/PublicHolidays/{year}/PT"
        try:
            req = urllib.request.Request(
                url,
                headers={"Accept": "application/json", "User-Agent": f"{APP_NAME}/1.0"},
            )
            with urllib.request.urlopen(req, timeout=10) as response:
                remote = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            app.logger.warning("Falha ao consultar feriados nacionais: %s", exc)
            raise ApiError(
                "Não foi possível consultar os feriados. Confirma a ligação à internet e tenta novamente.",
                502,
                "servico_feriados_indisponivel",
            )
        if not isinstance(remote, list):
            raise ApiError("O serviço de feriados devolveu uma resposta inválida.", 502)
        existing = {
            row["data"]: row for row in vacations.get_holidays(year=year)
        }
        holidays = []
        for item in remote:
            if not isinstance(item, dict):
                continue
            if item.get("global") is False or item.get("nationalHoliday") is False:
                continue
            holiday_types = item.get("types") or item.get("holidayTypes") or []
            if holiday_types and "Public" not in holiday_types:
                continue
            holiday_date = str(item.get("date") or "")[:10]
            try:
                parsed = date.fromisoformat(holiday_date)
            except ValueError:
                continue
            if parsed.year != year:
                continue
            description = str(
                item.get("localName") or item.get("name") or "Feriado nacional"
            ).strip()[:160]
            holidays.append({
                "data": holiday_date,
                "descricao": description,
                "existente": holiday_date in existing,
                "descricao_existente": (existing.get(holiday_date) or {}).get("descricao", ""),
            })
        holidays.sort(key=lambda item: item["data"])
        return _json_ok(
            data={"ano": year, "pais": "Portugal", "fonte": "Nager.Date", "feriados": holidays}
        )

    @app.post("/api/vacations/holidays/import")
    @_admin_required
    def api_import_portugal_holidays(_user):
        dados = _body()
        try:
            year = int(dados.get("ano"))
        except (TypeError, ValueError):
            raise ApiError("Indica um ano válido.")
        selected = dados.get("feriados") or []
        if not isinstance(selected, list) or len(selected) > 40:
            raise ApiError("A lista de feriados selecionados não é válida.")
        imported = 0
        skipped = 0
        for item in selected:
            if not isinstance(item, dict):
                raise ApiError("A lista de feriados selecionados não é válida.")
            holiday_date = _data_iso(item.get("data"), obrigatoria=True)
            if int(holiday_date[:4]) != year:
                raise ApiError("Todos os feriados devem pertencer ao ano selecionado.")
            description = str(item.get("descricao") or "").strip()[:160]
            if not description:
                raise ApiError("Todos os feriados devem ter uma descrição.")
            try:
                db_execute_return_id(
                    "INSERT INTO feriados (data, descricao, ativo) VALUES (?, ?, 1)",
                    (holiday_date, description),
                )
                imported += 1
            except sqlite3.IntegrityError:
                skipped += 1
        return _json_ok(
            imported=imported,
            skipped=skipped,
            message=(
                f"Importação concluída: {imported} feriado(s) adicionado(s)"
                + (f" e {skipped} já existente(s)." if skipped else ".")
            ),
        )

    @app.put("/api/vacations/holidays/<int:holiday_id>")
    @_vacation_manager_required
    def api_update_vacation_holiday(_user, holiday_id):
        if not db_one("SELECT id FROM feriados WHERE id=?", (holiday_id,)):
            raise ApiError("Feriado não encontrado.", 404)
        dados = _body()
        holiday_date = _data_iso(dados.get("data"), obrigatoria=True)
        description = str(dados.get("descricao") or "").strip()
        if not description:
            raise ApiError("Indica a descrição do feriado.")
        try:
            db_execute(
                "UPDATE feriados SET data=?, descricao=?, ativo=?, atualizado_em=CURRENT_TIMESTAMP WHERE id=?",
                (holiday_date, description[:160], 1 if dados.get("ativo", True) else 0, holiday_id),
            )
        except sqlite3.IntegrityError:
            raise ApiError("Já existe um feriado nessa data.", 409, "duplicado")
        return _json_ok(message="Feriado guardado.")

    @app.delete("/api/vacations/holidays/<int:holiday_id>")
    @_vacation_manager_required
    def api_delete_vacation_holiday(_user, holiday_id):
        if not db_one("SELECT id FROM feriados WHERE id=?", (holiday_id,)):
            raise ApiError("Feriado não encontrado.", 404)
        db_execute("DELETE FROM feriados WHERE id=?", (holiday_id,))
        return _json_ok(message="Feriado eliminado.")

    @app.post("/api/vacations/notifications/read")
    @_login_required
    def api_read_vacation_notifications(user):
        dados = _body()
        channel = str(dados.get("canal") or "pessoal").strip().lower()
        if channel not in {"pessoal", "gestao"}:
            raise ApiError("Canal de notificações inválido.")
        if channel == "gestao" and not _is_snr(user):
            raise ApiError("As notificações de gestão pertencem ao SNR.", 403, "permissao")
        notification_id = dados.get("id")
        if notification_id:
            db_execute(
                "UPDATE ferias_notificacoes SET lida=1 WHERE id=? AND utilizador_id=? AND canal=?",
                (int(notification_id), user["id"], channel),
            )
        else:
            db_execute(
                "UPDATE ferias_notificacoes SET lida=1 WHERE utilizador_id=? AND canal=?",
                (user["id"], channel),
            )
        return _json_ok(message="Notificações atualizadas.")

    @app.get("/api/vacations/notifications")
    @_login_required
    def api_vacation_notifications(user):
        channel = str(request.args.get("canal") or "pessoal").strip().lower()
        if channel not in {"pessoal", "gestao"}:
            raise ApiError("Canal de notificações inválido.")
        if channel == "gestao" and not _is_snr(user):
            raise ApiError("As notificações de gestão pertencem ao SNR.", 403, "permissao")
        return _json_ok(
            data=vacations.notification_payload(user["id"], channel=channel)
        )

    @app.delete("/api/vacations/notifications/<int:notification_id>")
    @_login_required
    def api_delete_vacation_notification(user, notification_id):
        channel = str(request.args.get("canal") or "pessoal").strip().lower()
        if channel not in {"pessoal", "gestao"}:
            raise ApiError("Canal de notificações inválido.")
        if channel == "gestao" and not _is_snr(user):
            raise ApiError("As notificações de gestão pertencem ao SNR.", 403, "permissao")
        notification = db_one(
            "SELECT id FROM ferias_notificacoes WHERE id=? AND utilizador_id=? AND canal=?",
            (notification_id, user["id"], channel),
        )
        if not notification:
            raise ApiError("Notificação não encontrada.", 404)
        db_execute(
            "DELETE FROM ferias_notificacoes WHERE id=? AND utilizador_id=? AND canal=?",
            (notification_id, user["id"], channel),
        )
        return _json_ok(message="Notificação apagada.")

    @app.get("/api/audit")
    @_admin_required
    def api_audit(_user):
        try:
            data = audit.list_entries(
                search=request.args.get("pesquisa") or "",
                method=request.args.get("metodo") or "",
                date_from=request.args.get("de") or "",
                date_to=request.args.get("ate") or "",
                before_id=request.args.get("cursor") or None,
                limit=request.args.get("limite") or 50,
            )
        except (TypeError, ValueError):
            raise ApiError("Os filtros da auditoria não são válidos.")
        return _json_ok(data=data)

    @app.get("/api/vacations/report.xlsx")
    @_vacation_manager_required
    def api_vacation_report(_user):
        try:
            year = int(request.args.get("ano") or vacations.get_settings()["ano_calendario"])
        except ValueError:
            raise ApiError("Indica um ano válido.")
        payload = vacations.management_payload(
            year=year,
            status=str(request.args.get("estado") or "") or None,
            status_group=str(request.args.get("grupo_estado") or "all"),
            search=str(request.args.get("pesquisa") or ""),
            area=str(request.args.get("area") or ""),
            show_all=str(request.args.get("todos") or "0") == "1",
            requests_year=year,
            export_only=True,
        )
        return send_file(
            generate_vacations_xlsx(payload),
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_attachment=True,
            download_name=f"SIGCP_Ferias_{year}.xlsx",
        )

    @app.get("/api/individual")
    @_login_required
    def api_individual(user):
        if not _pode_ver_individual(user):
            raise ApiError("Não tens acesso ao Welfare Individual.", 403)
        ano, mes = _periodo()
        modo = request.args.get("modo", "welfare")
        service = IndividualService(ano, mes, user, modo)
        return _json_ok(data=service.para_payload())

    @app.put("/api/individual/markings")
    @_login_required
    def api_individual_markings(user):
        if not _pode_ver_individual(user):
            raise ApiError("Não tens acesso ao Welfare Individual.", 403)
        dados = _body()
        ano, mes = _periodo(dados.get("ano"), dados.get("mes"))
        service = IndividualService(ano, mes, user)
        if not service.pode_editar():
            raise ApiError("Este mês está trancado ou não tens permissão.", 403)
        users = {int(item["id"]): item for item in service.utilizadores}
        changes = dados.get("changes")
        if not isinstance(changes, list) or len(changes) > 10000:
            raise ApiError("Lista de alterações inválida.")

        validadas = []
        for change in changes:
            try:
                user_id = int(change.get("user_id"))
            except (TypeError, ValueError, AttributeError):
                raise ApiError("Utilizador inválido numa alteração.")
            target = users.get(user_id)
            if not target:
                raise ApiError("Utilizador inválido numa alteração.")
            data_str = _data_iso(change.get("data"), obrigatoria=True)
            data_obj = date.fromisoformat(data_str)
            if (data_obj.year, data_obj.month) != (ano, mes):
                raise ApiError("Existe uma alteração fora do mês selecionado.")
            refeicao = str(change.get("refeicao") or "")
            marcado = 1 if change.get("marcado") else 0
            if refeicao == "Pequeno-Almoço":
                if not service.user_tem_pequeno_almoco_na_data(target, data_str):
                    raise ApiError("Não é possível alterar essa célula.")
            elif refeicao in ("Almoço", "Jantar"):
                if not service.user_tem_refeicao_na_data(
                    target, data_str, refeicao
                ) or service.user_em_ferias_na_refeicao(
                    target, data_str, refeicao
                ):
                    raise ApiError("Não é possível alterar essa célula.")
            else:
                raise ApiError("Refeição inválida.")
            validadas.append((user_id, data_str, refeicao, marcado))

        set_welfares_individuais(validadas)
        return _json_ok(
            message=f"{len(validadas)} alterações guardadas com sucesso."
        )

    @app.post("/api/individual/reset")
    @_login_required
    def api_individual_reset(user):
        dados = _body()
        ano, mes = _periodo(dados.get("ano"), dados.get("mes"))
        service = IndividualService(ano, mes, user)
        if not service.pode_editar():
            raise ApiError("Este mês está trancado ou não tens permissão.", 403)
        reset_welfares_individuais_mes(ano, mes)
        return _json_ok(message="Welfares Individuais repostos com sucesso.")

    @app.post("/api/individual/export")
    @_login_required
    def api_individual_export(user):
        if not _pode_ver_individual(user):
            raise ApiError("Não tens acesso ao Welfare Individual.", 403)
        dados = _body()
        ano, mes = _periodo(dados.get("ano"), dados.get("mes"))
        tipo = str(dados.get("tipo") or "")
        service = IndividualService(ano, mes, user)

        if tipo == "pdf_mes":
            modo_paginas = int(dados.get("modo_paginas") or 1)
            if modo_paginas not in (1, 2):
                raise ApiError("Formato de impressão inválido.")
            dias, rows, totais_dfac = service._dados_para_pdf_welfare_individual()
            nome = f"Welfare_Individual_{ano}_{mes:02d}.pdf"
            return _download_gerado(
                nome,
                ".pdf",
                "application/pdf",
                lambda caminho: gerar_pdf_welfare_individual(
                    caminho_pdf=caminho,
                    titulo="Contingente Português - Welfares/Marcações Individuais",
                    periodo=f"{months()[mes]} {ano}",
                    dias=dias,
                    rows=rows,
                    totais_dfac=totais_dfac,
                    day_offs=service.day_offs,
                    modo_paginas=modo_paginas,
                ),
            )

        if tipo in ("excel_semana", "pdf_semana"):
            if not service.pode_exportar_semanas():
                raise ApiError("Não tens permissão para exportar semanas.", 403)
            inicio_txt = _data_iso(dados.get("inicio_semana"), obrigatoria=True)
            inicio = date.fromisoformat(inicio_txt)
            numero = service.numero_semana_custom(inicio)
            if tipo == "excel_semana":
                totais = service._totais_semana_para_export(inicio)
                nome = f"W{numero}-{inicio.year} PT CN.xlsx"
                return _download_gerado(
                    nome,
                    ".xlsx",
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    lambda caminho: gerar_meals_request_weekly(
                        DOCS_DIR, caminho, totais, numero
                    ),
                )
            dias, rows, totais = service._dados_para_pdf_semana_completa(inicio)
            day_offs = set()
            for dia_info in dias:
                ref = date.fromisoformat(dia_info["data_str"])
                day_offs.update(service._ctx_para_data(ref).get("day_offs", set()))
            nome = f"W{numero}-{inicio.year}_Welfare_Individual.pdf"
            return _download_gerado(
                nome,
                ".pdf",
                "application/pdf",
                lambda caminho: gerar_pdf_welfare_individual(
                    caminho_pdf=caminho,
                    titulo="Contingente Português - Welfares/Marcações Individuais",
                    periodo=f"{service.prefixo_semana()}{numero} - {inicio.year}",
                    dias=dias,
                    rows=rows,
                    totais_dfac=totais,
                    day_offs=day_offs,
                    modo_paginas=1,
                ),
            )

        if not service.is_responsavel_welfare():
            raise ApiError(
                "Apenas o Responsável Welfare pode gerar este documento.",
                403,
                "permissao",
            )

        selecionados = None
        data_fim_override = None
        if tipo in ("excel_hoto", "request_hoto"):
            selecionados = service.validar_selecao_hoto(
                dados.get("utilizador_ids") or []
            )

        if tipo in ("excel_reembolso", "excel_hoto"):
            hoto = tipo == "excel_hoto"
            if hoto:
                data_fim_override = service._data_partida_hoto_excel(
                    selecionados[0]
                )
            linhas = service._dados_reembolso_para_export(
                hoto=hoto,
                utilizadores_override=selecionados if hoto else None,
            )
            if not linhas:
                raise ApiError("Não existem registos para exportar.")
            prefixo = "Meals_reimbursment_HOTO" if hoto else "Meals_reimbursment"
            nome = f"{prefixo}_{_nome_mes_en(mes)}{ano}.xlsx"
            return _download_gerado(
                nome,
                ".xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                lambda caminho: gerar_reembolso_mensal(
                    docs_dir=DOCS_DIR,
                    destino=caminho,
                    ano=ano,
                    mes=mes,
                    linhas=linhas,
                    senior_assinatura=get_snr_unico_para_assinatura(),
                    data_fim_override=data_fim_override,
                ),
            )

        if tipo == "service_note":
            dates_cohesion, individual_cohesion = service._dados_service_note()
            hoje = date.today()
            nome = (
                f"{hoje:%Y%m%d}_UNC_EDP_PT_SNR_SN_"
                "Welfare_Activities_Meals_Reimbursement.docx"
            )
            return _download_gerado(
                nome,
                ".docx",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                lambda caminho: gerar_service_note(
                    docs_dir=DOCS_DIR,
                    destino=caminho,
                    ano=ano,
                    mes=mes,
                    dates_cohesion=dates_cohesion,
                    individual_cohesion=individual_cohesion,
                    chief_of_staff_name=get_nome_cos(),
                ),
            )

        if tipo in ("request", "request_hoto"):
            responsavel = get_responsavel_welfare_mais_antigo_ativo()
            senior = get_snr_unico_para_assinatura()
            if tipo == "request":
                total_reimb, total_meals = service._totais_request_para_export()
                nome = f"_{mes:02d}_{str(ano)[-2:]}_Request Welfare meals.docx"
                gerador = lambda caminho: gerar_request_welfare_meals(
                    docs_dir=DOCS_DIR,
                    destino=caminho,
                    ano=ano,
                    mes=mes,
                    responsavel_welfare=service._identificacao_posto_nome_sobrenome(
                        responsavel
                    ),
                    telefone_servico=(
                        responsavel.get("telemovel_servico") if responsavel else ""
                    )
                    or "",
                    total_reimb=service._formatar_valor_espacos(total_reimb),
                    total_meals=total_meals,
                    senior_prt=service._identificacao_posto_nome_sobrenome(senior),
                )
            else:
                total_reimb = 0
                total_meals = 0
                for item in selecionados:
                    _welfare, _cohesion, reimbursement = (
                        service.calcular_resumo_user(item)
                    )
                    total_reimb += int(reimbursement or 0)
                    valor = service.valor_welfare_numero()
                    total_meals += int((reimbursement or 0) / valor) if valor else 0
                pessoas = "; ".join(
                    service.identificacao_curta(item) for item in selecionados
                ) + ";"
                partida = service._data_partida_hoto_formatada(selecionados[0])
                nome = (
                    f"_{mes:02d}_{str(ano)[-2:]}_Request Welfare meals HOTO.docx"
                )
                gerador = lambda caminho: gerar_request_welfare_meals_hoto(
                    docs_dir=DOCS_DIR,
                    destino=caminho,
                    ano=ano,
                    mes=mes,
                    responsavel_welfare=service._identificacao_posto_nome_sobrenome(
                        responsavel
                    ),
                    telefone_servico=(
                        responsavel.get("telemovel_servico") if responsavel else ""
                    )
                    or "",
                    total_reimb=service._formatar_valor_espacos(total_reimb),
                    total_meals=total_meals,
                    senior_prt=service._identificacao_posto_nome_sobrenome(senior),
                    pessoas_hoto=pessoas,
                    data_inicio_override=partida,
                )
            return _download_gerado(
                nome,
                ".docx",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                gerador,
            )

        raise ApiError("Tipo de exportação inválido.")

    @app.post("/api/xfa")
    @_login_required
    def api_xfa(user):
        if not _is_responsavel_welfare(user):
            raise ApiError(
                "Apenas o Responsável Welfare pode usar a Distribuição XFA.", 403
            )
        dados = _body()
        ano, mes = _periodo(dados.get("ano"), dados.get("mes"))
        service = IndividualService(ano, mes, user)
        resultado = calcular_distribuicao_xfa(
            service,
            dados.get("utilizador_ids") or [],
            dados.get("stock") or {},
            str(dados.get("tipo_valor") or "reembolso"),
            dados.get("valores_manuais"),
        )
        return _json_ok(data=resultado)

    @app.get("/api/export/database.json")
    @_superadmin_required
    def api_export_database(_user):
        nome = f"sigcp_export_{datetime.now():%Y%m%d_%H%M%S}.json"
        return _download_gerado(
            nome,
            ".json",
            "application/json",
            lambda caminho: exportar_base_dados_json(caminho),
        )

    @app.post("/api/import/database.json")
    @_superadmin_required
    def api_import_database(_user):
        dados = _body()
        removidos = 0
        try:
            from app.supabase_store import aplicar_json_sqlite, enviar
            aplicar_json_sqlite(dados)
            if app_config.DATABASE_MODE == "supabase":
                removidos = enviar(dados)
            init_db()
        except (ValueError, OSError, sqlite3.Error) as exc:
            raise ApiError(f"Não foi possível importar o ficheiro JSON: {exc}")
        aviso = (
            f" Foram ignoradas {removidos} relações órfãs sem registo principal."
            if removidos else ""
        )
        return _json_ok(message=f"Dados importados com sucesso.{aviso} Reinicie a aplicação.", restart_required=True)

    return app
