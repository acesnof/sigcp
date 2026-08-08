"""Sincronização do SQLite do SIGCP com um documento versionado no Supabase."""
import base64
import json
import os
import sqlite3
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from app import config

LOCK = threading.RLock()
_revision = None
_last_download = 0.0
SYNC_INTERVAL_SECONDS = 10.0

TABLES = (
    "utilizadores", "app_settings", "teams", "welfares", "team_membros",
    "escala_loica", "caixa_movimentos", "day_offs", "feriados",
    "meses_trancados", "sigcp_plus_meta", "utilizadores_acessos",
    "welfares_individuais", "ferias", "ferias_historico",
    "ferias_notificacoes", "sigcp_plus_recovery", "auditoria",
)


class SupabaseUnavailable(RuntimeError):
    pass


def _request(method, path, payload=None, extra_headers=None):
    url = f"{config.SUPABASE_URL}/rest/v1/{path}"
    body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {
        "apikey": config.SUPABASE_KEY,
        "Authorization": f"Bearer {config.SUPABASE_KEY}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    headers.update(extra_headers or {})
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=body, headers=headers, method=method), timeout=12) as response:
            raw = response.read()
            return json.loads(raw.decode("utf-8")) if raw else None
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise SupabaseUnavailable(f"O Supabase recusou o pedido ({exc.code}). Confirme o URL, a chave e se executou a query SQL. {detail[:250]}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise SupabaseUnavailable(
            "Não foi possível ligar à base de dados online. Verifique a ligação à Internet e tente mais tarde."
        ) from exc


def _get_all(nome):
    resultado = []
    offset = 0
    while True:
        separador = "&" if "?" in nome else "?"
        lote = _request("GET", f"{nome}{separador}limit=1000&offset={offset}") or []
        resultado.extend(lote)
        if len(lote) < 1000:
            return resultado
        offset += len(lote)


def _decode(value):
    if isinstance(value, dict) and value.get("__tipo__") == "bytes":
        return base64.b64decode(value.get("base64") or "")
    return value


def aplicar_json_sqlite(dados, caminho=None):
    if dados.get("formato") != "prt_welfare_database_export" or not isinstance(dados.get("tabelas"), dict):
        raise ValueError("O ficheiro não é uma exportação JSON válida do SIGCP.")
    destino = Path(caminho or config.DB_PATH)
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporario = destino.with_suffix(destino.suffix + ".import")
    if temporario.exists():
        temporario.unlink()
    conn = sqlite3.connect(temporario)
    try:
        conn.execute("PRAGMA foreign_keys=OFF")
        for nome, tabela in dados["tabelas"].items():
            if nome.startswith("sqlite_") or nome.startswith("auditoria_fts"):
                continue
            sql = tabela.get("sql_criacao")
            if sql:
                conn.execute(sql)
        for nome, tabela in dados["tabelas"].items():
            registos = tabela.get("registos") or []
            if not registos or nome.startswith("sqlite_") or nome.startswith("auditoria_fts"):
                continue
            colunas = list(registos[0])
            quoted = ','.join('"' + c.replace('"', '""') + '"' for c in colunas)
            placeholders = ','.join('?' for _ in colunas)
            conn.executemany(f'INSERT INTO "{nome.replace(chr(34), chr(34)*2)}" ({quoted}) VALUES ({placeholders})', [tuple(_decode(r.get(c)) for c in colunas) for r in registos])
        conn.commit()
    except Exception:
        conn.close()
        temporario.unlink(missing_ok=True)
        raise
    conn.close()
    os.replace(temporario, destino)


def _substituir_registos_sqlite(registos_por_tabela):
    """Atualiza a cache SQLite preservando o esquema e índices locais."""
    conn = sqlite3.connect(config.DB_PATH)
    try:
        conn.execute("PRAGMA foreign_keys=OFF")
        # Tabelas auxiliares que podem existir na exportação/Supabase, mas que
        # não fazem parte das migrações históricas do núcleo da aplicação.
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sigcp_plus_meta (
                chave TEXT PRIMARY KEY, valor TEXT, atualizado_em TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sigcp_plus_recovery (
                user_id INTEGER PRIMARY KEY,
                recovery_salt TEXT NOT NULL,
                recovery_hash TEXT NOT NULL,
                created_at TEXT NOT NULL,
                used_at TEXT,
                FOREIGN KEY(user_id) REFERENCES utilizadores(id) ON DELETE CASCADE
            )
        """)
        conn.commit()
        conn.execute("BEGIN")
        tabelas_locais = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        # Uma cache de uma versão anterior pode ainda não ter todas as tabelas.
        # Essas tabelas são criadas por init_db e carregadas na sincronização
        # imediatamente seguinte.
        for nome in reversed(TABLES):
            if nome not in tabelas_locais:
                continue
            conn.execute(f'DELETE FROM "{nome}"')
        for nome in TABLES:
            if nome not in tabelas_locais:
                continue
            registos = registos_por_tabela.get(nome) or []
            if not registos:
                continue
            colunas_validas = {row[1] for row in conn.execute(f'PRAGMA table_info("{nome}")')}
            colunas = [col for col in registos[0] if col in colunas_validas]
            quoted = ','.join(f'"{col}"' for col in colunas)
            placeholders = ','.join('?' for _ in colunas)
            conn.executemany(
                f'INSERT INTO "{nome}" ({quoted}) VALUES ({placeholders})',
                [tuple(_decode(row.get(col)) for col in colunas) for row in registos],
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def exportar_json_sqlite(caminho=None):
    conn = sqlite3.connect(caminho or config.DB_PATH)
    conn.row_factory = sqlite3.Row
    tabelas = {}
    for row in conn.execute("SELECT name,sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name NOT LIKE 'auditoria_fts%' ORDER BY name"):
        nome = row["name"]
        cols = [dict(nome=c["name"], tipo=c["type"], obrigatoria=bool(c["notnull"]), valor_predefinido=c["dflt_value"], chave_primaria=bool(c["pk"])) for c in conn.execute(f'PRAGMA table_info("{nome}")')]
        regs = []
        for record in conn.execute(f'SELECT * FROM "{nome}"'):
            regs.append({k: ({"__tipo__":"bytes", "base64":base64.b64encode(record[k]).decode()} if isinstance(record[k], bytes) else record[k]) for k in record.keys()})
        tabelas[nome] = {"sql_criacao": row["sql"], "colunas": cols, "registos": regs}
    conn.close()
    return {"formato":"prt_welfare_database_export", "versao":1, "exportado_em":datetime.now(timezone.utc).isoformat(), "base_dados":"database.sqlite3", "tabelas":tabelas}


def normalizar_relacoes(dados):
    """Remove relações órfãs aceites por bases SQLite antigas.

    O Supabase aplica efetivamente as foreign keys, pelo que uma única relação
    órfã faria a transação inteira falhar. A função não altera o objeto recebido.
    """
    resultado = json.loads(json.dumps(dados, ensure_ascii=False))
    tabelas = resultado.get("tabelas") or {}

    def registos(nome):
        tabela = tabelas.get(nome) or {}
        rows = tabela.get("registos")
        return rows if isinstance(rows, list) else []

    utilizadores = {row.get("id") for row in registos("utilizadores")}
    ferias = {row.get("id") for row in registos("ferias")}
    removidos = 0

    for nome in ("utilizadores_acessos", "welfares_individuais", "ferias", "ferias_notificacoes", "sigcp_plus_recovery"):
        rows = registos(nome)
        chave = "user_id" if nome == "sigcp_plus_recovery" else "utilizador_id"
        validos = [row for row in rows if row.get(chave) in utilizadores]
        removidos += len(rows) - len(validos)
        if nome in tabelas:
            tabelas[nome]["registos"] = validos

    # O conjunto de férias pode ter diminuído por conter utilizadores órfãos.
    ferias = {row.get("id") for row in registos("ferias")}
    historico = registos("ferias_historico")
    historico_valido = [row for row in historico if row.get("feria_id") in ferias]
    removidos += len(historico) - len(historico_valido)
    if "ferias_historico" in tabelas:
        tabelas["ferias_historico"]["registos"] = historico_valido

    for nome in ("ferias_historico", "auditoria"):
        for row in registos(nome):
            if row.get("utilizador_id") not in utilizadores:
                row["utilizador_id"] = None
    for row in registos("ferias_notificacoes"):
        if row.get("feria_id") not in ferias:
            row["feria_id"] = None

    return resultado, removidos


def descarregar(criar_se_vazio=False, force=False):
    global _last_download
    agora = time.monotonic()
    if not force and _last_download and agora - _last_download < SYNC_INTERVAL_SECONDS:
        return False
    # As tabelas são independentes na leitura. Em paralelo, uma atualização da
    # cache demora aproximadamente o pedido mais lento em vez da soma de 14.
    with ThreadPoolExecutor(max_workers=6, thread_name_prefix="sigcp-supabase") as pool:
        futuros = {nome: pool.submit(_get_all, f"{nome}?select=*") for nome in TABLES}
        registos = {nome: futuros[nome].result() for nome in TABLES}
    if not os.path.isfile(config.DB_PATH):
        _last_download = time.monotonic()
        return True
    _substituir_registos_sqlite(registos)
    _last_download = time.monotonic()
    return True


def enviar(dados=None):
    global _last_download
    dados = dados or exportar_json_sqlite()
    dados, removidos = normalizar_relacoes(dados)
    _request("POST", "rpc/sigcp_import", {"p_payload": dados})
    # A cache acabou de originar o estado remoto; não é necessário voltar a
    # descarregar todas as tabelas na consulta imediatamente seguinte.
    _last_download = time.monotonic()
    return removidos
