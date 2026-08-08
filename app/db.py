import calendar
import base64
import json
import os
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from app.config import DB_PATH, MASTER_NIM, MASTER_PASSWORD, TIPOS_ACESSO
from app import config as app_config
from app.person_order import person_order_key
from app.security import hash_password, verificar_password


class _OnlineConnection(sqlite3.Connection):
    _sigcp_online_lock = None

    def commit(self):
        super().commit()
        if app_config.DATABASE_MODE == "supabase" and not app_config.SUPABASE_OFFLINE:
            from app.supabase_store import enviar
            enviar()

    def close(self):
        lock, self._sigcp_online_lock = self._sigcp_online_lock, None
        try:
            super().close()
        finally:
            if lock is not None:
                lock.release()


def _connect():
    """Ligação SQLite com timeout maior para uso em pasta partilhada.

    Não muda o formato da base de dados. Apenas evita falhas/esperas curtas
    quando outro posto está temporariamente a escrever.
    """
    online_ativo = app_config.DATABASE_MODE == "supabase" and not app_config.SUPABASE_OFFLINE
    if online_ativo:
        from app.supabase_store import LOCK, descarregar
        LOCK.acquire()
        try:
            descarregar(criar_se_vazio=True)
        except Exception:
            LOCK.release()
            raise
    factory = _OnlineConnection if online_ativo else sqlite3.Connection
    caminho = app_config.DB_PATH if app_config.DATABASE_MODE == "supabase" else DB_PATH
    try:
        conn = sqlite3.connect(caminho, timeout=30, factory=factory)
    except Exception:
        if online_ativo:
            LOCK.release()
        raise
    if online_ativo:
        conn._sigcp_online_lock = LOCK
    try:
        conn.execute("PRAGMA busy_timeout = 30000")
        conn.execute("PRAGMA foreign_keys = ON")
    except sqlite3.Error:
        pass
    return conn


def init_db():
    conn = _connect()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS welfares (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            data TEXT NOT NULL,
            refeicao TEXT NOT NULL,
            tipo TEXT NOT NULL,
            prato TEXT,
            sobremesa TEXT,
            observacao TEXT,
            recanto INTEGER NOT NULL DEFAULT 0,
            local TEXT NOT NULL DEFAULT '',
            criado_em TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(data, refeicao)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS utilizadores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nim TEXT NOT NULL UNIQUE,
            posto TEXT,
            nome TEXT,
            sobrenome TEXT,
            data_nascimento TEXT,
            data_chegada TEXT,
            data_partida TEXT,
            antiguidade TEXT,
            snr INTEGER DEFAULT 0,
            snr_substituto INTEGER DEFAULT 0,
            snr_substituto_inicio TEXT,
            snr_substituto_fim TEXT,
            telemovel_servico TEXT,
            responsavel_welfare INTEGER DEFAULT 0,
            posicao_numero TEXT,
            tipo_acesso TEXT NOT NULL,
            password_salt TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            master INTEGER DEFAULT 0,
            criado_em TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Migração automática para bases de dados criadas antes do campo antiguidade.
    cur.execute("PRAGMA table_info(utilizadores)")
    colunas_utilizadores = {row[1] for row in cur.fetchall()}
    if "data_nascimento" not in colunas_utilizadores:
        cur.execute("ALTER TABLE utilizadores ADD COLUMN data_nascimento TEXT")
    if "antiguidade" not in colunas_utilizadores:
        cur.execute("ALTER TABLE utilizadores ADD COLUMN antiguidade TEXT")
    if "snr" not in colunas_utilizadores:
        cur.execute("ALTER TABLE utilizadores ADD COLUMN snr INTEGER DEFAULT 0")
    if "snr_substituto" not in colunas_utilizadores:
        cur.execute(
            "ALTER TABLE utilizadores ADD COLUMN snr_substituto INTEGER DEFAULT 0"
        )
    if "snr_substituto_inicio" not in colunas_utilizadores:
        cur.execute("ALTER TABLE utilizadores ADD COLUMN snr_substituto_inicio TEXT")
    if "snr_substituto_fim" not in colunas_utilizadores:
        cur.execute("ALTER TABLE utilizadores ADD COLUMN snr_substituto_fim TEXT")
    if "telemovel_servico" not in colunas_utilizadores:
        cur.execute("ALTER TABLE utilizadores ADD COLUMN telemovel_servico TEXT")
    if "responsavel_welfare" not in colunas_utilizadores:
        cur.execute("ALTER TABLE utilizadores ADD COLUMN responsavel_welfare INTEGER DEFAULT 0")
    if "area_funcional" not in colunas_utilizadores:
        cur.execute("ALTER TABLE utilizadores ADD COLUMN area_funcional TEXT DEFAULT 'Não definido'")
    if "posicao_numero" not in colunas_utilizadores:
        cur.execute("ALTER TABLE utilizadores ADD COLUMN posicao_numero TEXT")
    if "ferias_direito_override" not in colunas_utilizadores:
        cur.execute("ALTER TABLE utilizadores ADD COLUMN ferias_direito_override REAL")
    if "missao_prorrogada" not in colunas_utilizadores:
        cur.execute("ALTER TABLE utilizadores ADD COLUMN missao_prorrogada INTEGER DEFAULT 0")
    if "notas_ferias" not in colunas_utilizadores:
        cur.execute("ALTER TABLE utilizadores ADD COLUMN notas_ferias TEXT")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS utilizadores_acessos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            utilizador_id INTEGER NOT NULL,
            tipo_acesso TEXT NOT NULL,
            criado_em TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(utilizador_id, tipo_acesso),
            FOREIGN KEY(utilizador_id) REFERENCES utilizadores(id) ON DELETE CASCADE
        )
    """)

    # Migração dos nomes antigos dos tipos de acesso para os nomes atuais.
    acessos_migracao = {
        "Escrita 1": "Gestão Welfare Mensal",
        "Escrita 2": "Gestão Ementa",
        "Escrita 3": "Gestão Welfare Individual",
        "Leitura 1": "Leitura",
        "Leitura 2": "Leitura",
        "Gestão Férias": "Pessoal/Gestão Férias",
    }
    for antigo, novo in acessos_migracao.items():
        cur.execute("SELECT utilizador_id FROM utilizadores_acessos WHERE tipo_acesso = ?", (antigo,))
        for (utilizador_id,) in cur.fetchall():
            cur.execute("""
                INSERT OR IGNORE INTO utilizadores_acessos (utilizador_id, tipo_acesso)
                VALUES (?, ?)
            """, (utilizador_id, novo))
        cur.execute("DELETE FROM utilizadores_acessos WHERE tipo_acesso = ?", (antigo,))
        cur.execute(
            "UPDATE utilizadores SET tipo_acesso = REPLACE(tipo_acesso, ?, ?)",
            (antigo, novo)
        )


    cur.execute("""
        CREATE TABLE IF NOT EXISTS welfares_individuais (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            utilizador_id INTEGER NOT NULL,
            data TEXT NOT NULL,
            refeicao TEXT NOT NULL,
            marcado INTEGER NOT NULL DEFAULT 1,
            criado_em TEXT DEFAULT CURRENT_TIMESTAMP,
            atualizado_em TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(utilizador_id, data, refeicao),
            FOREIGN KEY(utilizador_id) REFERENCES utilizadores(id) ON DELETE CASCADE
        )
    """)


    cur.execute("""
        CREATE TABLE IF NOT EXISTS app_settings (
            chave TEXT PRIMARY KEY,
            valor TEXT,
            atualizado_em TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS day_offs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            data TEXT NOT NULL UNIQUE,
            observacao TEXT,
            criado_em TEXT DEFAULT CURRENT_TIMESTAMP,
            atualizado_em TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS ferias (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            utilizador_id INTEGER NOT NULL,
            data_hora_inicio TEXT NOT NULL,
            data_hora_fim TEXT NOT NULL,
            observacao TEXT,
            companhia_aerea TEXT,
            estado TEXT NOT NULL DEFAULT 'Aprovado',
            submetido_por INTEGER,
            submetido_em TEXT,
            decidido_por INTEGER,
            decidido_em TEXT,
            nota_decisao TEXT,
            proposta_data_hora_inicio TEXT,
            proposta_data_hora_fim TEXT,
            proposta_observacao TEXT,
            proposta_companhia_aerea TEXT,
            motivo_fluxo TEXT,
            fluxo_pedido_por INTEGER,
            fluxo_pedido_em TEXT,
            avisos_aceites TEXT,
            anulado_por INTEGER,
            anulado_em TEXT,
            motivo_anulacao TEXT,
            criado_em TEXT DEFAULT CURRENT_TIMESTAMP,
            atualizado_em TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(utilizador_id) REFERENCES utilizadores(id) ON DELETE CASCADE
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS teams (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL UNIQUE COLLATE NOCASE,
            criado_em TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS team_membros (
            team_id INTEGER NOT NULL,
            utilizador_id INTEGER NOT NULL UNIQUE,
            criado_em TEXT DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (team_id, utilizador_id),
            FOREIGN KEY(team_id) REFERENCES teams(id) ON DELETE CASCADE,
            FOREIGN KEY(utilizador_id) REFERENCES utilizadores(id) ON DELETE CASCADE
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS escala_loica (
            fim_semana TEXT PRIMARY KEY,
            militar_1_id INTEGER,
            militar_2_id INTEGER,
            assinatura_1 INTEGER NOT NULL DEFAULT 0,
            assinatura_2 INTEGER NOT NULL DEFAULT 0,
            validada INTEGER NOT NULL DEFAULT 0,
            manual INTEGER NOT NULL DEFAULT 0,
            atualizado_em TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(militar_1_id) REFERENCES utilizadores(id) ON DELETE SET NULL,
            FOREIGN KEY(militar_2_id) REFERENCES utilizadores(id) ON DELETE SET NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS caixa_movimentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tipo TEXT NOT NULL CHECK(tipo IN ('entrada', 'saida')),
            data TEXT NOT NULL,
            pessoa_gasto TEXT NOT NULL DEFAULT '',
            local TEXT NOT NULL DEFAULT '',
            valor REAL NOT NULL CHECK(valor > 0),
            descritivo TEXT NOT NULL,
            observacoes TEXT NOT NULL DEFAULT '',
            criado_por_id INTEGER,
            criado_por_nome TEXT NOT NULL DEFAULT '',
            criado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            atualizado_por_id INTEGER,
            atualizado_por_nome TEXT NOT NULL DEFAULT '',
            atualizado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(criado_por_id) REFERENCES utilizadores(id) ON DELETE SET NULL,
            FOREIGN KEY(atualizado_por_id) REFERENCES utilizadores(id) ON DELETE SET NULL
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_caixa_data ON caixa_movimentos(data, id)")

    cur.execute("PRAGMA table_info(welfares)")
    colunas_welfares = {row[1] for row in cur.fetchall()}
    if "team_id" not in colunas_welfares:
        cur.execute("ALTER TABLE welfares ADD COLUMN team_id INTEGER REFERENCES teams(id) ON DELETE SET NULL")
    if "recanto" not in colunas_welfares:
        cur.execute("ALTER TABLE welfares ADD COLUMN recanto INTEGER NOT NULL DEFAULT 0")
        cur.execute("""
            UPDATE welfares SET recanto=1
            WHERE tipo IN ('Welfare', 'Welfare Aniversário')
        """)
    if "local" not in colunas_welfares:
        cur.execute("ALTER TABLE welfares ADD COLUMN local TEXT NOT NULL DEFAULT ''")
        cur.execute("UPDATE welfares SET local='Recanto' WHERE COALESCE(recanto, 0)=1")

    # Migração não destrutiva da antiga tabela de férias. Os períodos que já
    # existiam eram autorizações efetivas, por isso entram no novo fluxo como
    # aprovados e continuam imediatamente refletidos no Welfare Individual.
    cur.execute("PRAGMA table_info(ferias)")
    colunas_ferias = {row[1] for row in cur.fetchall()}
    novas_colunas_ferias = {
        "companhia_aerea": "TEXT",
        "estado": "TEXT NOT NULL DEFAULT 'Aprovado'",
        "submetido_por": "INTEGER",
        "submetido_em": "TEXT",
        "decidido_por": "INTEGER",
        "decidido_em": "TEXT",
        "nota_decisao": "TEXT",
        "proposta_data_hora_inicio": "TEXT",
        "proposta_data_hora_fim": "TEXT",
        "proposta_observacao": "TEXT",
        "proposta_companhia_aerea": "TEXT",
        "motivo_fluxo": "TEXT",
        "fluxo_pedido_por": "INTEGER",
        "fluxo_pedido_em": "TEXT",
        "avisos_aceites": "TEXT",
        "anulado_por": "INTEGER",
        "anulado_em": "TEXT",
        "motivo_anulacao": "TEXT",
    }
    for nome_coluna, definicao in novas_colunas_ferias.items():
        if nome_coluna not in colunas_ferias:
            cur.execute(f"ALTER TABLE ferias ADD COLUMN {nome_coluna} {definicao}")

    cur.execute("""
        UPDATE ferias
        SET estado = COALESCE(NULLIF(TRIM(estado), ''), 'Aprovado'),
            submetido_por = COALESCE(submetido_por, utilizador_id),
            submetido_em = COALESCE(submetido_em, criado_em)
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS ferias_historico (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            feria_id INTEGER NOT NULL,
            utilizador_id INTEGER,
            acao TEXT NOT NULL,
            estado_anterior TEXT,
            estado_novo TEXT,
            nota TEXT,
            detalhes TEXT,
            criado_em TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(feria_id) REFERENCES ferias(id) ON DELETE CASCADE,
            FOREIGN KEY(utilizador_id) REFERENCES utilizadores(id) ON DELETE SET NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS ferias_notificacoes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            utilizador_id INTEGER NOT NULL,
            feria_id INTEGER,
            tipo TEXT NOT NULL,
            canal TEXT NOT NULL DEFAULT 'pessoal',
            titulo TEXT NOT NULL,
            mensagem TEXT,
            lida INTEGER NOT NULL DEFAULT 0,
            criado_em TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(utilizador_id) REFERENCES utilizadores(id) ON DELETE CASCADE,
            FOREIGN KEY(feria_id) REFERENCES ferias(id) ON DELETE CASCADE
        )
    """)

    cur.execute("PRAGMA table_info(ferias_notificacoes)")
    colunas_notificacoes = {row[1] for row in cur.fetchall()}
    if "canal" not in colunas_notificacoes:
        cur.execute(
            "ALTER TABLE ferias_notificacoes "
            "ADD COLUMN canal TEXT NOT NULL DEFAULT 'pessoal'"
        )
        cur.execute(
            """
            UPDATE ferias_notificacoes
            SET canal='gestao'
            WHERE tipo IN ('pedido', 'alteracao', 'cancelamento')
            """
        )

    cur.execute("""
        CREATE TABLE IF NOT EXISTS auditoria (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            criado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            utilizador_id INTEGER,
            utilizador_nim TEXT NOT NULL DEFAULT '',
            utilizador_identificacao TEXT NOT NULL DEFAULT '',
            acao TEXT NOT NULL,
            metodo TEXT NOT NULL,
            rota TEXT NOT NULL,
            entidade TEXT,
            entidade_id TEXT,
            detalhes TEXT NOT NULL DEFAULT '{}',
            endereco_ip TEXT,
            FOREIGN KEY(utilizador_id) REFERENCES utilizadores(id) ON DELETE SET NULL
        )
    """)
    fts_auditoria_existia = cur.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='auditoria_fts'"
    ).fetchone()
    try:
        cur.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS auditoria_fts USING fts5(
                utilizador_nim,
                utilizador_identificacao,
                acao,
                rota,
                entidade_id,
                detalhes,
                tokenize='unicode61 remove_diacritics 2'
            )
        """)
        cur.executescript("""
            CREATE TRIGGER IF NOT EXISTS auditoria_fts_ai
            AFTER INSERT ON auditoria BEGIN
                INSERT INTO auditoria_fts (
                    rowid, utilizador_nim, utilizador_identificacao,
                    acao, rota, entidade_id, detalhes
                ) VALUES (
                    new.id, new.utilizador_nim, new.utilizador_identificacao,
                    new.acao, new.rota, new.entidade_id, new.detalhes
                );
            END;
            CREATE TRIGGER IF NOT EXISTS auditoria_fts_ad
            AFTER DELETE ON auditoria BEGIN
                DELETE FROM auditoria_fts WHERE rowid=old.id;
            END;
            CREATE TRIGGER IF NOT EXISTS auditoria_fts_au
            AFTER UPDATE ON auditoria BEGIN
                DELETE FROM auditoria_fts WHERE rowid=old.id;
                INSERT INTO auditoria_fts (
                    rowid, utilizador_nim, utilizador_identificacao,
                    acao, rota, entidade_id, detalhes
                ) VALUES (
                    new.id, new.utilizador_nim, new.utilizador_identificacao,
                    new.acao, new.rota, new.entidade_id, new.detalhes
                );
            END;
        """)
        if not fts_auditoria_existia:
            cur.execute("""
                INSERT INTO auditoria_fts (
                    rowid, utilizador_nim, utilizador_identificacao,
                    acao, rota, entidade_id, detalhes
                )
                SELECT id, utilizador_nim, utilizador_identificacao,
                       acao, rota, entidade_id, detalhes
                FROM auditoria
            """)
    except sqlite3.OperationalError:
        # O filtro continua funcional por LIKE em builds SQLite sem FTS5.
        pass

    cur.execute("""
        CREATE TABLE IF NOT EXISTS feriados (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            data TEXT NOT NULL UNIQUE,
            descricao TEXT NOT NULL,
            ativo INTEGER NOT NULL DEFAULT 1,
            criado_em TEXT DEFAULT CURRENT_TIMESTAMP,
            atualizado_em TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        INSERT INTO ferias_historico (
            feria_id, utilizador_id, acao, estado_anterior, estado_novo,
            nota, criado_em
        )
        SELECT f.id, f.submetido_por, 'Migração', NULL, 'Aprovado',
               'Período existente preservado como aprovado.',
               COALESCE(f.criado_em, CURRENT_TIMESTAMP)
        FROM ferias f
        WHERE f.estado = 'Aprovado'
          AND NOT EXISTS (
            SELECT 1 FROM ferias_historico h WHERE h.feria_id = f.id
        )
    """)



    cur.execute("""
        CREATE TABLE IF NOT EXISTS meses_trancados (
            mes TEXT PRIMARY KEY,
            trancado INTEGER NOT NULL DEFAULT 0,
            atualizado_em TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Índices para acelerar leituras mensais em SQLite, sobretudo em pasta partilhada.
    cur.execute("CREATE INDEX IF NOT EXISTS idx_welfares_data ON welfares(data)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_welfares_team ON welfares(team_id, data)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_team_membros_team ON team_membros(team_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_escala_loica_militar1 ON escala_loica(militar_1_id, fim_semana)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_escala_loica_militar2 ON escala_loica(militar_2_id, fim_semana)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_welfares_individuais_mes ON welfares_individuais(data)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_welfares_individuais_user_data ON welfares_individuais(utilizador_id, data)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_ferias_periodo ON ferias(data_hora_inicio, data_hora_fim)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_ferias_fim_inicio ON ferias(data_hora_fim, data_hora_inicio)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_ferias_user ON ferias(utilizador_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_ferias_estado ON ferias(estado)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_ferias_historico_feria ON ferias_historico(feria_id, criado_em)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_ferias_notificacoes_user ON ferias_notificacoes(utilizador_id, lida, criado_em)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_ferias_notificacoes_canal ON ferias_notificacoes(utilizador_id, canal, lida, id DESC)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_feriados_data ON feriados(data)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_utilizadores_partida ON utilizadores(data_partida)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_utilizadores_ordenacao ON utilizadores(posto, antiguidade, sobrenome, nome)")
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_utilizadores_snr_substituto "
        "ON utilizadores(snr_substituto, snr_substituto_inicio, snr_substituto_fim)"
    )
    cur.execute("CREATE INDEX IF NOT EXISTS idx_auditoria_data ON auditoria(criado_em DESC, id DESC)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_auditoria_user ON auditoria(utilizador_id, id DESC)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_auditoria_metodo ON auditoria(metodo, id DESC)")

    salt, pwd_hash = hash_password(MASTER_PASSWORD)

    cur.execute("""
        INSERT OR IGNORE INTO utilizadores (
            nim, posto, nome, sobrenome, data_chegada, data_partida, antiguidade, snr,
            telemovel_servico, responsavel_welfare,
            tipo_acesso, password_salt, password_hash, master
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
    """, (
        MASTER_NIM,
        "",
        "Administrador",
        "Mestre",
        "",
        "",
        "",
        0,
        "",
        0,
        "Administrador",
        salt,
        pwd_hash,
    ))

    # Migração automática: copia o antigo campo tipo_acesso para a nova tabela multi-acesso.
    cur.execute("SELECT id, tipo_acesso, master FROM utilizadores")
    for user_id, tipo_acesso, master in cur.fetchall():
        if master:
            cur.execute("""
                INSERT OR IGNORE INTO utilizadores_acessos (utilizador_id, tipo_acesso)
                VALUES (?, ?)
            """, (user_id, "Administrador"))
        elif tipo_acesso:
            for acesso in str(tipo_acesso).split(","):
                acesso = acesso.strip()
                if acesso in TIPOS_ACESSO:
                    cur.execute("""
                        INSERT OR IGNORE INTO utilizadores_acessos (utilizador_id, tipo_acesso)
                        VALUES (?, ?)
                    """, (user_id, acesso))

    conn.commit()
    conn.close()


def db_rows(query, params=()):
    conn = _connect()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(query, params)
    rows = [dict(row) for row in cur.fetchall()]
    conn.close()
    return rows


def db_one(query, params=()):
    rows = db_rows(query, params)
    return rows[0] if rows else None


def db_execute(query, params=()):
    conn = _connect()
    cur = conn.cursor()
    cur.execute(query, params)
    conn.commit()
    conn.close()


def db_execute_return_id(query, params=()):
    conn = _connect()
    cur = conn.cursor()
    cur.execute(query, params)
    conn.commit()
    last_id = cur.lastrowid
    conn.close()
    return last_id


def _valor_compativel_com_json(valor):
    """Converte os tipos devolvidos pelo SQLite para valores JSON."""
    if isinstance(valor, bytes):
        return {
            "__tipo__": "bytes",
            "base64": base64.b64encode(valor).decode("ascii"),
        }
    return valor


def exportar_base_dados_json(caminho):
    """Exporta todas as tabelas da aplicação para um ficheiro JSON."""
    conn = _connect()
    conn.row_factory = sqlite3.Row

    try:
        conn.execute("BEGIN")
        tabelas_db = conn.execute("""
            SELECT name, sql
            FROM sqlite_master
            WHERE type = 'table'
              AND name NOT LIKE 'sqlite_%'
              AND name NOT LIKE 'auditoria_fts%'
            ORDER BY name
        """).fetchall()

        tabelas = {}
        total_registos = 0

        for tabela_db in tabelas_db:
            nome = tabela_db["name"]
            nome_sql = '"' + nome.replace('"', '""') + '"'

            colunas = [
                {
                    "nome": coluna["name"],
                    "tipo": coluna["type"],
                    "obrigatoria": bool(coluna["notnull"]),
                    "valor_predefinido": coluna["dflt_value"],
                    "chave_primaria": bool(coluna["pk"]),
                }
                for coluna in conn.execute(f"PRAGMA table_info({nome_sql})").fetchall()
            ]

            registos = []
            for row in conn.execute(f"SELECT * FROM {nome_sql}").fetchall():
                registos.append({
                    chave: _valor_compativel_com_json(row[chave])
                    for chave in row.keys()
                })

            tabelas[nome] = {
                "sql_criacao": tabela_db["sql"],
                "colunas": colunas,
                "registos": registos,
            }
            total_registos += len(registos)

        dados = {
            "formato": "prt_welfare_database_export",
            "versao": 1,
            "exportado_em": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "base_dados": Path(DB_PATH).name,
            "tabelas": tabelas,
        }
    finally:
        conn.close()

    destino = Path(caminho)
    destino.parent.mkdir(parents=True, exist_ok=True)
    caminho_temporario = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=destino.parent,
            prefix=f".{destino.name}.",
            suffix=".tmp",
            delete=False,
        ) as ficheiro:
            caminho_temporario = ficheiro.name
            json.dump(dados, ficheiro, ensure_ascii=False, indent=2)
            ficheiro.write("\n")

        os.replace(caminho_temporario, destino)
    except Exception:
        if caminho_temporario:
            try:
                os.remove(caminho_temporario)
            except OSError:
                pass
        raise

    return {
        "tabelas": len(tabelas),
        "registos": total_registos,
    }


def get_utilizador_acessos(utilizador_id):
    rows = db_rows("""
        SELECT tipo_acesso
        FROM utilizadores_acessos
        WHERE utilizador_id = ?
        ORDER BY
            CASE tipo_acesso
                WHEN 'Administrador' THEN 1
                WHEN 'Gestão Welfare Mensal' THEN 2
                WHEN 'Gestão Ementa' THEN 3
                WHEN 'Gestão Welfare Individual' THEN 4
                WHEN 'Leitura' THEN 5
                WHEN 'Pessoal/Gestão Férias' THEN 6
                ELSE 99
            END
    """, (utilizador_id,))
    return [row["tipo_acesso"] for row in rows]


def set_utilizador_acessos(utilizador_id, acessos):
    acessos_validos = [a for a in acessos if a in TIPOS_ACESSO]

    conn = _connect()
    cur = conn.cursor()
    cur.execute("DELETE FROM utilizadores_acessos WHERE utilizador_id = ?", (utilizador_id,))

    for acesso in acessos_validos:
        cur.execute("""
            INSERT OR IGNORE INTO utilizadores_acessos (utilizador_id, tipo_acesso)
            VALUES (?, ?)
        """, (utilizador_id, acesso))

    tipo_legacy = ", ".join(acessos_validos) if acessos_validos else "Leitura"
    cur.execute("UPDATE utilizadores SET tipo_acesso = ? WHERE id = ?", (tipo_legacy, utilizador_id))

    conn.commit()
    conn.close()


def atualizar_password_utilizador(utilizador_id, password):
    salt, pwd_hash = hash_password(password)
    db_execute("""
        UPDATE utilizadores
        SET password_salt = ?, password_hash = ?
        WHERE id = ?
    """, (salt, pwd_hash, utilizador_id))


def enriquecer_user_com_acessos(user):
    if not user:
        return None

    acessos = get_utilizador_acessos(user["id"])

    if user.get("master") and "Administrador" not in acessos:
        acessos.insert(0, "Administrador")

    if not acessos and user.get("tipo_acesso"):
        acessos = [a.strip() for a in str(user["tipo_acesso"]).split(",") if a.strip()]

    user["acessos"] = acessos
    user["tipo_acesso"] = ", ".join(acessos) if acessos else user.get("tipo_acesso", "")
    return user


def autenticar_utilizador(nim, password):
    user = db_one("SELECT * FROM utilizadores WHERE nim = ?", (nim.strip(),))

    if not user:
        return None

    if verificar_password(password, user["password_salt"], user["password_hash"]):
        return enriquecer_user_com_acessos(user)

    return None



def get_snr_utilizadores():
    """Devolve todos os utilizadores marcados como SNR/Sénior, excluindo o utilizador mestre."""
    return sorted(db_rows("""
        SELECT *
        FROM utilizadores
        WHERE master = 0 AND COALESCE(snr, 0) = 1
        ORDER BY
            CASE posto
                WHEN 'OF-6' THEN 1
                WHEN 'OF-5' THEN 2
                WHEN 'OF-4' THEN 3
                WHEN 'OF-3' THEN 4
                WHEN 'OF-2' THEN 5
                WHEN 'OF-1' THEN 6
                WHEN 'OR-9' THEN 7
                WHEN 'OR-8' THEN 8
                WHEN 'OR-7' THEN 9
                WHEN 'OR-6' THEN 10
                WHEN 'OR-5' THEN 11
                WHEN 'OR-4' THEN 12
                WHEN 'OR-3' THEN 13
                WHEN 'OR-2' THEN 14
                WHEN 'OR-1' THEN 15
                ELSE 99
            END,
            CASE
                WHEN antiguidade IS NULL OR TRIM(antiguidade) = '' THEN '9999-12-31'
                ELSE SUBSTR(antiguidade, 1, 10)
            END ASC,
            sobrenome COLLATE NOCASE,
            nome COLLATE NOCASE
    """), key=person_order_key)


def _ativo_hoje_sql_condicao(alias=""):
    prefixo = f"{alias}." if alias else ""
    return f"({prefixo}data_partida IS NULL OR TRIM({prefixo}data_partida) = '' OR SUBSTR({prefixo}data_partida, 1, 10) >= ?)"


def get_snr_utilizadores_ativos():
    """Devolve o substituto ativo ou, na sua ausência, os SNR titulares ativos."""
    from datetime import date
    hoje = date.today().isoformat()
    return db_rows("""
        SELECT *
        FROM utilizadores
        WHERE master = 0
          AND (
              (
                  COALESCE(snr_substituto, 0) = 1
                  AND SUBSTR(COALESCE(snr_substituto_inicio, ''), 1, 10) <= ?
                  AND SUBSTR(COALESCE(snr_substituto_fim, ''), 1, 10) >= ?
              )
              OR (
                  COALESCE(snr, 0) = 1
                  AND NOT EXISTS (
                      SELECT 1 FROM utilizadores substituto
                      WHERE substituto.master = 0
                        AND COALESCE(substituto.snr_substituto, 0) = 1
                        AND SUBSTR(COALESCE(substituto.snr_substituto_inicio, ''), 1, 10) <= ?
                        AND SUBSTR(COALESCE(substituto.snr_substituto_fim, ''), 1, 10) >= ?
                  )
              )
          )
          AND (data_partida IS NULL OR TRIM(data_partida) = '' OR SUBSTR(data_partida, 1, 10) >= ?)
        ORDER BY
            CASE posto
                WHEN 'OF-6' THEN 1
                WHEN 'OF-5' THEN 2
                WHEN 'OF-4' THEN 3
                WHEN 'OF-3' THEN 4
                WHEN 'OF-2' THEN 5
                WHEN 'OF-1' THEN 6
                WHEN 'OR-9' THEN 7
                WHEN 'OR-8' THEN 8
                WHEN 'OR-7' THEN 9
                WHEN 'OR-6' THEN 10
                WHEN 'OR-5' THEN 11
                WHEN 'OR-4' THEN 12
                WHEN 'OR-3' THEN 13
                WHEN 'OR-2' THEN 14
                WHEN 'OR-1' THEN 15
                ELSE 99
            END,
            CASE
                WHEN antiguidade IS NULL OR TRIM(antiguidade) = '' THEN '9999-12-31'
                ELSE SUBSTR(antiguidade, 1, 10)
            END ASC,
            sobrenome COLLATE NOCASE,
            nome COLLATE NOCASE
    """, (hoje, hoje, hoje, hoje, hoje))


def get_snr_unico_ativo_para_assinatura():
    seniors = get_snr_utilizadores_ativos()
    return seniors[0] if len(seniors) == 1 else None


def get_responsaveis_welfare_ativos():
    """Devolve responsáveis Welfare ativos hoje, excluindo mestre, ordenados por posto e antiguidade."""
    from datetime import date
    hoje = date.today().isoformat()
    return db_rows("""
        SELECT *
        FROM utilizadores
        WHERE master = 0
          AND COALESCE(responsavel_welfare, 0) = 1
          AND (data_partida IS NULL OR TRIM(data_partida) = '' OR SUBSTR(data_partida, 1, 10) >= ?)
        ORDER BY
            CASE posto
                WHEN 'OF-6' THEN 1
                WHEN 'OF-5' THEN 2
                WHEN 'OF-4' THEN 3
                WHEN 'OF-3' THEN 4
                WHEN 'OF-2' THEN 5
                WHEN 'OF-1' THEN 6
                WHEN 'OR-9' THEN 7
                WHEN 'OR-8' THEN 8
                WHEN 'OR-7' THEN 9
                WHEN 'OR-6' THEN 10
                WHEN 'OR-5' THEN 11
                WHEN 'OR-4' THEN 12
                WHEN 'OR-3' THEN 13
                WHEN 'OR-2' THEN 14
                WHEN 'OR-1' THEN 15
                ELSE 99
            END,
            CASE
                WHEN antiguidade IS NULL OR TRIM(antiguidade) = '' THEN '9999-12-31'
                ELSE SUBSTR(antiguidade, 1, 10)
            END ASC,
            sobrenome COLLATE NOCASE,
            nome COLLATE NOCASE
    """, (hoje,))


def get_responsavel_welfare_mais_antigo_ativo():
    responsaveis = get_responsaveis_welfare_ativos()
    return responsaveis[0] if responsaveis else None

def get_snr_unico_para_assinatura():
    # Compatibilidade: agora só considera SNR ativos hoje.
    return get_snr_unico_ativo_para_assinatura()

def get_welfares_mes(ano, mes):
    ultimo_dia = calendar.monthrange(ano, mes)[1]
    inicio = f"{ano}-{mes:02d}-01"
    fim = f"{ano}-{mes:02d}-{ultimo_dia:02d}"

    rows = db_rows("""
        SELECT welfares.*, teams.nome AS team_nome
        FROM welfares
        LEFT JOIN teams ON teams.id = welfares.team_id
        WHERE data BETWEEN ? AND ?
        ORDER BY data,
            CASE refeicao
                WHEN 'Almoço' THEN 1
                WHEN 'Jantar' THEN 2
                ELSE 3
            END
    """, (inicio, fim))

    dados = {}
    for row in rows:
        dados.setdefault(row["data"], []).append(row)

    return dados


def get_welfare(data_str, refeicao):
    return db_one("""
        SELECT welfares.*, teams.nome AS team_nome
        FROM welfares
        LEFT JOIN teams ON teams.id = welfares.team_id
        WHERE data = ? AND refeicao = ?
    """, (data_str, refeicao))


def guardar_welfare(
    data_str, refeicao, tipo, prato, sobremesa, observacao,
    team_id=None, local=None,
):
    if local is None:
        local = "Recanto" if tipo in ("Welfare", "Welfare Aniversário") else ""
    local = str(local).strip()
    if local not in ("", "Recanto", "Restaurante", "Outro"):
        local = ""
    if local != "Recanto":
        team_id = None
    db_execute("""
        INSERT INTO welfares (
            data, refeicao, tipo, prato, sobremesa, observacao, team_id, recanto, local
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(data, refeicao)
        DO UPDATE SET
            tipo = excluded.tipo,
            prato = excluded.prato,
            sobremesa = excluded.sobremesa,
            observacao = excluded.observacao,
            team_id = excluded.team_id,
            recanto = excluded.recanto,
            local = excluded.local
    """, (
        data_str,
        refeicao,
        tipo,
        prato,
        sobremesa,
        observacao,
        team_id,
        1 if local == "Recanto" else 0,
        local,
    ))


def get_teams():
    teams = db_rows("SELECT id, nome, criado_em FROM teams ORDER BY nome COLLATE NOCASE")
    hoje = datetime.now().date().isoformat()
    membros = db_rows("""
        SELECT tm.team_id, u.id, u.nim, u.posto, u.nome, u.sobrenome, u.antiguidade,
               u.data_chegada, u.data_partida
        FROM team_membros tm
        JOIN utilizadores u ON u.id=tm.utilizador_id
        WHERE COALESCE(u.data_partida, '')='' OR u.data_partida>=?
        ORDER BY tm.team_id
    """, (hoje,))
    por_team = {}
    for membro in membros:
        por_team.setdefault(membro.pop("team_id"), []).append(membro)
    for team in teams:
        team["membros"] = sorted(
            por_team.get(team["id"], []), key=person_order_key
        )
    return teams


def eliminar_welfare(data_str, refeicao):
    db_execute("""
        DELETE FROM welfares
        WHERE data = ? AND refeicao = ?
    """, (data_str, refeicao))


def get_utilizadores_ativos_para_welfare_individual(ano=None, mes=None):
    """
    Devolve utilizadores para a grelha de Welfare Individual no mês indicado.

    Regras mensais:
    - quem ainda não chegou só aparece a partir do mês da chegada;
    - quem já partiu aparece apenas até ao mês da partida inclusive;
    - o utilizador mestre nunca aparece.

    Se ano/mes não forem indicados, mantém compatibilidade com a regra antiga
    baseada na data de hoje.
    """
    from datetime import date

    if ano is not None and mes is not None:
        ultimo_dia = calendar.monthrange(int(ano), int(mes))[1]
        inicio_mes = f"{int(ano)}-{int(mes):02d}-01"
        fim_mes = f"{int(ano)}-{int(mes):02d}-{ultimo_dia:02d}"
        where_periodo = """
          AND (
                data_chegada IS NULL
                OR TRIM(data_chegada) = ''
                OR SUBSTR(data_chegada, 1, 10) <= ?
          )
          AND (
                data_partida IS NULL
                OR TRIM(data_partida) = ''
                OR SUBSTR(data_partida, 1, 10) >= ?
          )
        """
        params = (fim_mes, inicio_mes)
    else:
        hoje = date.today().isoformat()
        where_periodo = """
          AND (
                data_partida IS NULL
                OR TRIM(data_partida) = ''
                OR SUBSTR(data_partida, 1, 10) >= ?
          )
        """
        params = (hoje,)

    rows = db_rows(f"""
        SELECT *
        FROM utilizadores
        WHERE master = 0
        {where_periodo}
        ORDER BY
            CASE posto
                WHEN 'OF-6' THEN 1
                WHEN 'OF-5' THEN 2
                WHEN 'OF-4' THEN 3
                WHEN 'OF-3' THEN 4
                WHEN 'OF-2' THEN 5
                WHEN 'OF-1' THEN 6
                WHEN 'OR-9' THEN 7
                WHEN 'OR-8' THEN 8
                WHEN 'OR-7' THEN 9
                WHEN 'OR-6' THEN 10
                WHEN 'OR-5' THEN 11
                WHEN 'OR-4' THEN 12
                WHEN 'OR-3' THEN 13
                WHEN 'OR-2' THEN 14
                WHEN 'OR-1' THEN 15
                ELSE 99
            END,
            CASE
                WHEN antiguidade IS NULL OR TRIM(antiguidade) = '' THEN '9999-12-31'
                ELSE SUBSTR(antiguidade, 1, 10)
            END ASC,
            sobrenome COLLATE NOCASE,
            nome COLLATE NOCASE
    """, params)
    return sorted(rows, key=person_order_key)


def get_welfares_individuais_mes(ano, mes):
    ultimo_dia = calendar.monthrange(ano, mes)[1]
    inicio = f"{ano}-{mes:02d}-01"
    fim = f"{ano}-{mes:02d}-{ultimo_dia:02d}"

    rows = db_rows("""
        SELECT utilizador_id, data, refeicao, marcado
        FROM welfares_individuais
        WHERE data BETWEEN ? AND ?
    """, (inicio, fim))

    dados = {}
    for row in rows:
        dados[(row["utilizador_id"], row["data"], row["refeicao"])] = int(row["marcado"])

    return dados


def set_welfare_individual(utilizador_id, data_str, refeicao, marcado):
    db_execute("""
        INSERT INTO welfares_individuais (
            utilizador_id, data, refeicao, marcado, atualizado_em
        )
        VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(utilizador_id, data, refeicao)
        DO UPDATE SET
            marcado = excluded.marcado,
            atualizado_em = CURRENT_TIMESTAMP
    """, (
        utilizador_id,
        data_str,
        refeicao,
        1 if marcado else 0,
    ))


def set_welfares_individuais(alteracoes):
    """Guarda várias alterações individuais numa única transação."""
    conn = _connect()
    try:
        conn.executemany("""
            INSERT INTO welfares_individuais (
                utilizador_id, data, refeicao, marcado, atualizado_em
            )
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(utilizador_id, data, refeicao)
            DO UPDATE SET
                marcado = excluded.marcado,
                atualizado_em = CURRENT_TIMESTAMP
        """, [
            (
                utilizador_id,
                data_str,
                refeicao,
                1 if marcado else 0,
            )
            for utilizador_id, data_str, refeicao, marcado in alteracoes
        ])
        conn.commit()
    finally:
        conn.close()



def reset_welfares_individuais_mes(ano, mes):
    ultimo_dia = calendar.monthrange(ano, mes)[1]
    inicio = f"{ano}-{mes:02d}-01"
    fim = f"{ano}-{mes:02d}-{ultimo_dia:02d}"

    db_execute("""
        DELETE FROM welfares_individuais
        WHERE data BETWEEN ? AND ?
    """, (inicio, fim))


def get_setting(chave, default=""):
    row = db_one("SELECT valor FROM app_settings WHERE chave = ?", (chave,))
    if not row:
        return default
    return row.get("valor") if row.get("valor") is not None else default


def set_setting(chave, valor):
    db_execute("""
        INSERT INTO app_settings (chave, valor, atualizado_em)
        VALUES (?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(chave)
        DO UPDATE SET
            valor = excluded.valor,
            atualizado_em = CURRENT_TIMESTAMP
    """, (chave, str(valor)))


def get_valor_welfare():
    return get_setting("valor_welfare", "")


def set_valor_welfare(valor):
    set_setting("valor_welfare", valor)


def get_valor_caixa():
    return get_setting("valor_caixa", "")


def set_valor_caixa(valor):
    set_setting("valor_caixa", valor)



DEFAULT_HORARIO_DFAC = {
    "normal": {
        "pequeno_almoco": {"abertura": "07:00", "fecho": "09:00"},
        "almoco": {"abertura": "12:00", "fecho": "14:00"},
        "jantar": {"abertura": "18:00", "fecho": "20:00"},
    },
    "especial": {
        "pequeno_almoco": {"abertura": "07:00", "fecho": "09:00"},
        "almoco": {"abertura": "12:00", "fecho": "14:00"},
        "jantar": {"abertura": "18:00", "fecho": "20:00"},
    },
}


def get_horario_dfac():
    raw = get_setting("horario_dfac", "")
    if not raw:
        return json.loads(json.dumps(DEFAULT_HORARIO_DFAC))
    try:
        dados = json.loads(raw)
    except Exception:
        return json.loads(json.dumps(DEFAULT_HORARIO_DFAC))

    # Garante sempre todas as chaves, mesmo em bases antigas/incompletas.
    resultado = json.loads(json.dumps(DEFAULT_HORARIO_DFAC))
    for tipo in ("normal", "especial"):
        for refeicao in ("pequeno_almoco", "almoco", "jantar"):
            for campo in ("abertura", "fecho"):
                valor = (((dados or {}).get(tipo) or {}).get(refeicao) or {}).get(campo)
                if isinstance(valor, str) and valor.strip():
                    resultado[tipo][refeicao][campo] = valor.strip()[:5]
    return resultado


def set_horario_dfac(dados):
    set_setting("horario_dfac", json.dumps(dados, ensure_ascii=False))

def get_day_offs(mostrar_todos=False):
    from datetime import date

    hoje = date.today().isoformat()

    if mostrar_todos:
        return db_rows("""
            SELECT *
            FROM day_offs
            ORDER BY data DESC
        """)

    return db_rows("""
        SELECT *
        FROM day_offs
        WHERE data >= ?
        ORDER BY data DESC
    """, (hoje,))


def get_day_off(day_off_id):
    return db_one("SELECT * FROM day_offs WHERE id = ?", (day_off_id,))


def guardar_day_off(data_str, observacao="", day_off_id=None):
    if day_off_id:
        db_execute("""
            UPDATE day_offs
            SET data = ?, observacao = ?, atualizado_em = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (data_str, observacao, day_off_id))
    else:
        db_execute("""
            INSERT INTO day_offs (data, observacao, atualizado_em)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(data)
            DO UPDATE SET
                observacao = excluded.observacao,
                atualizado_em = CURRENT_TIMESTAMP
        """, (data_str, observacao))


def eliminar_day_off(day_off_id):
    db_execute("DELETE FROM day_offs WHERE id = ?", (day_off_id,))


def get_day_offs_mes(ano, mes):
    ultimo_dia = calendar.monthrange(ano, mes)[1]
    inicio = f"{ano}-{mes:02d}-01"
    fim = f"{ano}-{mes:02d}-{ultimo_dia:02d}"

    rows = db_rows("""
        SELECT data
        FROM day_offs
        WHERE data BETWEEN ? AND ?
    """, (inicio, fim))

    return {row["data"] for row in rows}


def get_nome_cos():
    return get_setting("nome_cos", "")

def set_nome_cos(nome):
    set_setting("nome_cos", nome)


def get_inicio_semana():
    return get_setting("inicio_semana", "")


def set_inicio_semana(data_str):
    set_setting("inicio_semana", data_str or "")


def get_lingua():
    return get_setting("lingua", "pt")


def set_lingua(valor):
    valor = valor if valor in ("pt", "en") else "pt"
    set_setting("lingua", valor)



def get_ferias(mostrar_todas=False):
    from datetime import datetime
    hoje = datetime.now().strftime("%Y-%m-%d %H:%M")
    if mostrar_todas:
        return db_rows("""
            SELECT f.*, u.posto, u.nome, u.sobrenome, u.antiguidade
            FROM ferias f
            JOIN utilizadores u ON u.id = f.utilizador_id
            ORDER BY f.data_hora_inicio DESC
        """)
    return db_rows("""
        SELECT f.*, u.posto, u.nome, u.sobrenome, u.antiguidade
        FROM ferias f
        JOIN utilizadores u ON u.id = f.utilizador_id
        WHERE f.data_hora_fim >= ?
        ORDER BY f.data_hora_inicio DESC
    """, (hoje,))


def get_feria(feria_id):
    return db_one("""
        SELECT f.*, u.posto, u.nome, u.sobrenome
        FROM ferias f
        JOIN utilizadores u ON u.id = f.utilizador_id
        WHERE f.id = ?
    """, (feria_id,))


def guardar_feria(utilizador_id, data_hora_inicio, data_hora_fim, observacao="", feria_id=None):
    if feria_id:
        db_execute("""
            UPDATE ferias
            SET utilizador_id = ?, data_hora_inicio = ?, data_hora_fim = ?,
                observacao = ?, atualizado_em = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (utilizador_id, data_hora_inicio, data_hora_fim, observacao, feria_id))
    else:
        db_execute("""
            INSERT INTO ferias (utilizador_id, data_hora_inicio, data_hora_fim, observacao, atualizado_em)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, (utilizador_id, data_hora_inicio, data_hora_fim, observacao))


def eliminar_feria(feria_id):
    db_execute("DELETE FROM ferias WHERE id = ?", (feria_id,))


def get_ferias_mes(ano, mes):
    ultimo_dia = calendar.monthrange(ano, mes)[1]
    inicio = f"{ano}-{mes:02d}-01 00:00"
    fim = f"{ano}-{mes:02d}-{ultimo_dia:02d} 23:59"
    rows = db_rows("""
        SELECT *
        FROM ferias
        WHERE data_hora_inicio <= ? AND data_hora_fim >= ?
          AND estado IN ('Aprovado', 'Alteração pendente', 'Cancelamento pendente')
        ORDER BY utilizador_id, data_hora_inicio
    """, (fim, inicio))
    dados = {}
    for row in rows:
        dados.setdefault(row["utilizador_id"], []).append(row)
    return dados


def normalizar_mes_chave(ano, mes):
    return f"{int(ano):04d}-{int(mes):02d}"


def is_mes_trancado(ano, mes):
    chave = normalizar_mes_chave(ano, mes)
    row = db_one("SELECT trancado FROM meses_trancados WHERE mes = ?", (chave,))
    return bool(row and int(row.get("trancado") or 0) == 1)


def set_mes_trancado(ano, mes, trancado):
    chave = normalizar_mes_chave(ano, mes)
    db_execute("""
        INSERT INTO meses_trancados (mes, trancado, atualizado_em)
        VALUES (?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(mes)
        DO UPDATE SET
            trancado = excluded.trancado,
            atualizado_em = CURRENT_TIMESTAMP
    """, (chave, 1 if trancado else 0))
