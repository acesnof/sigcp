import json
import ctypes
import os
import sqlite3
import sys
from pathlib import Path
from tkinter import filedialog, messagebox
from urllib.parse import quote

APP_NAME = "SIGCP"
APP_FULL_NAME = "Sistema Integrado de Gestão do Contingente Português"
APP_VERSION = "2.5.2"
LEGACY_APP_NAME = "PRT Welfare"


def _runtime_dirs():
    """
    Em desenvolvimento:
        raiz do projeto

    Compilado:
        pasta onde está o executável e pasta temporária dos recursos internos
    """
    if getattr(sys, "frozen", False):
        app_dir = os.path.dirname(sys.executable)
        resource_dir = getattr(sys, "_MEIPASS", app_dir)
        return app_dir, app_dir, resource_dir

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return base_dir, base_dir, base_dir


APP_DIR, BASE_DIR, RESOURCE_DIR = _runtime_dirs()
DOCS_DIR = os.path.join(RESOURCE_DIR, "docs")
FAVICON_PATH = os.path.join(DOCS_DIR, "favico.ico")

def _pasta_documentos_utilizador():
    """Obtém a pasta Documentos real do perfil Windows, com fallback portátil."""
    if os.name == "nt":
        try:
            buffer = ctypes.create_unicode_buffer(32768)
            # CSIDL_PERSONAL identifica a pasta Documentos mesmo quando foi movida.
            if ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buffer) == 0:
                if buffer.value:
                    return buffer.value
        except (AttributeError, OSError):
            pass
    perfil = os.environ.get("USERPROFILE") or str(Path.home())
    return os.path.join(perfil, "Documents")


# O caminho selecionado para a base de dados pertence ao utilizador e fica nos
# seus Documentos. Os locais antigos continuam a ser lidos para migração.
documentos_dir = _pasta_documentos_utilizador()
CONFIG_PATH = os.path.join(documentos_dir, APP_NAME, "sigcp_config.json")
legacy_local_dir = os.path.join(os.environ.get("LOCALAPPDATA", APP_DIR), LEGACY_APP_NAME)
LEGACY_CONFIG_PATH = os.path.join(legacy_local_dir, "prt_welfare_config.json")
ADDITIONAL_CONFIG_PATHS = (
    os.path.join(os.environ.get("LOCALAPPDATA", APP_DIR), APP_NAME, "sigcp_config.json"),
    os.path.join(APP_DIR, "prt_welfare_config.json"),
)
DB_FILENAME = "database.sqlite3"
DB_PATH = os.path.join(BASE_DIR, DB_FILENAME)
DATABASE_MODE = "local"
DEFAULT_SUPABASE_URL = "https://oggfcqjczjuzfomtzydq.supabase.co"
DEFAULT_SUPABASE_KEY = "sb_publishable_Rinaat-q346H5Xqkg8DoCg_yncNNf4h"
SUPABASE_URL = DEFAULT_SUPABASE_URL
SUPABASE_KEY = DEFAULT_SUPABASE_KEY
SUPABASE_OFFLINE = False
DATABASE_OFFLINE = False


class _VSFixedFileInfo(ctypes.Structure):
    _fields_ = [
        ("dwSignature", ctypes.c_uint32), ("dwStrucVersion", ctypes.c_uint32),
        ("dwFileVersionMS", ctypes.c_uint32), ("dwFileVersionLS", ctypes.c_uint32),
        ("dwProductVersionMS", ctypes.c_uint32), ("dwProductVersionLS", ctypes.c_uint32),
        ("dwFileFlagsMask", ctypes.c_uint32), ("dwFileFlags", ctypes.c_uint32),
        ("dwFileOS", ctypes.c_uint32), ("dwFileType", ctypes.c_uint32),
        ("dwFileSubtype", ctypes.c_uint32), ("dwFileDateMS", ctypes.c_uint32),
        ("dwFileDateLS", ctypes.c_uint32),
    ]


def get_executable_version(caminho):
    """Lê a versão incorporada num executável Windows sem o executar."""
    if os.name != "nt" or not caminho:
        return ""
    try:
        version = ctypes.windll.version
        handle = ctypes.c_uint32(0)
        size = version.GetFileVersionInfoSizeW(str(caminho), ctypes.byref(handle))
        if not size:
            return ""
        buffer = ctypes.create_string_buffer(size)
        if not version.GetFileVersionInfoW(str(caminho), 0, size, buffer):
            return ""
        pointer = ctypes.c_void_p()
        length = ctypes.c_uint(0)
        if not version.VerQueryValueW(buffer, "\\", ctypes.byref(pointer), ctypes.byref(length)):
            return ""
        info = ctypes.cast(pointer, ctypes.POINTER(_VSFixedFileInfo)).contents
        parts = [
            info.dwProductVersionMS >> 16,
            info.dwProductVersionMS & 0xFFFF,
            info.dwProductVersionLS >> 16,
            info.dwProductVersionLS & 0xFFFF,
        ]
        while len(parts) > 2 and parts[-1] == 0:
            parts.pop()
        return ".".join(str(item) for item in parts)
    except (AttributeError, OSError, ValueError):
        return ""


def _ler_config_local():
    for caminho in dict.fromkeys(
        (CONFIG_PATH, LEGACY_CONFIG_PATH, *ADDITIONAL_CONFIG_PATHS)
    ):
        try:
            if not os.path.exists(caminho):
                continue
            with open(caminho, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            continue
    return {}


def _guardar_config_local(config):
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


def set_db_path(caminho):
    global DB_PATH
    DB_PATH = os.path.abspath(caminho)
    return DB_PATH


def guardar_db_path(caminho):
    """Guarda o caminho para ser usado no próximo arranque da aplicação."""
    caminho = set_db_path(caminho)
    config = _ler_config_local()
    config["database_path"] = caminho
    _guardar_config_local(config)
    return caminho


def aplicar_configuracao_base_dados(config=None):
    """Aplica localmente o backend persistido, sem escrever no ficheiro."""
    global DATABASE_MODE, SUPABASE_URL, SUPABASE_KEY, DB_PATH
    config = config or _ler_config_local()
    DATABASE_MODE = str(config.get("database_mode") or "local").lower()
    if DATABASE_MODE not in ("local", "supabase"):
        DATABASE_MODE = "local"
    SUPABASE_URL = str(config.get("supabase_url") or DEFAULT_SUPABASE_URL).rstrip("/")
    SUPABASE_KEY = str(config.get("supabase_key") or DEFAULT_SUPABASE_KEY).strip()
    if DATABASE_MODE == "supabase":
        cache_dir = os.path.dirname(CONFIG_PATH)
        DB_PATH = os.path.join(cache_dir, "supabase_cache.sqlite3")
    elif config.get("database_path"):
        set_db_path(config["database_path"])
    return DATABASE_MODE


def _sqlite_readonly_uri(caminho):
    """Constrói um URI SQLite read-only, incluindo caminhos UNC do Windows."""
    caminho_uri = os.path.abspath(str(caminho)).replace("\\", "/")
    if caminho_uri.startswith("//"):
        # Mantém a authority vazia: file:////servidor/partilha/ficheiro.
        # file://servidor/... é rejeitado por builds SQLite sem
        # SQLITE_ALLOW_URI_AUTHORITY.
        caminho_uri = "//" + caminho_uri
    return f"file:{quote(caminho_uri, safe='/:')}?mode=ro"


def abrir_base_dados_somente_leitura(caminho, timeout=5):
    return sqlite3.connect(
        _sqlite_readonly_uri(caminho),
        uri=True,
        timeout=timeout,
    )


def validar_base_dados(caminho):
    """Valida, sem escrever, se o caminho aponta para uma base SQLite legível."""
    caminho = os.path.abspath(os.path.expandvars(os.path.expanduser(str(caminho or ""))))
    if not caminho or not os.path.isfile(caminho):
        return False, "O ficheiro indicado não existe."

    ligacao = None
    try:
        ligacao = abrir_base_dados_somente_leitura(caminho)
        ligacao.execute("SELECT name FROM sqlite_master LIMIT 1").fetchone()
        return True, ""
    except sqlite3.Error as exc:
        return False, f"O ficheiro não é uma base SQLite válida: {exc}"
    finally:
        if ligacao is not None:
            ligacao.close()


def get_backup_dir():
    """
    A pasta db_backup fica sempre ao lado da base de dados.
    """
    return os.path.join(os.path.dirname(DB_PATH), "db_backup")


def garantir_base_dados_configurada(parent=None):
    """
    Garante que existe uma base de dados configurada localmente.
    Se não existir ou se o caminho guardado deixar de ser válido,
    pede ao utilizador para escolher o ficheiro database.sqlite3.
    """
    config = _ler_config_local()
    caminho_guardado = config.get("database_path")

    valido, _erro = validar_base_dados(caminho_guardado)
    if valido:
        set_db_path(caminho_guardado)
        return True

    if caminho_guardado:
        mensagem = (
            "A base de dados configurada deixou de estar disponível:\n\n"
            f"{caminho_guardado}\n\n"
            "Selecione a localização atual da base de dados."
        )
        pasta_inicial = os.path.dirname(caminho_guardado)
    else:
        mensagem = (
            "Este é o primeiro arranque da aplicação.\n\n"
            "Selecione a base de dados SQLite que pretende utilizar."
        )
        pasta_inicial = APP_DIR

    messagebox.showinfo("Base de dados", mensagem, parent=parent)

    while True:
        caminho = filedialog.askopenfilename(
            parent=parent,
            title="Selecionar base de dados SIGCP",
            initialdir=pasta_inicial if os.path.isdir(pasta_inicial) else APP_DIR,
            filetypes=[
                ("Base de dados SQLite", "*.sqlite3"),
                ("Todos os ficheiros", "*.*"),
            ],
        )

        if not caminho:
            return False

        if os.path.basename(caminho).lower() != DB_FILENAME.lower():
            continuar = messagebox.askyesno(
                "Confirmar base de dados",
                "O ficheiro selecionado não se chama database.sqlite3.\n\nQueres usar este ficheiro na mesma?",
                parent=parent,
            )
            if not continuar:
                continue

        valido, erro = validar_base_dados(caminho)
        if not valido:
            messagebox.showerror("Base de dados inválida", erro, parent=parent)
            continue

        set_db_path(caminho)
        config["database_path"] = DB_PATH
        try:
            _guardar_config_local(config)
        except OSError as exc:
            messagebox.showerror(
                "Erro de configuração",
                f"Não foi possível guardar o caminho da base de dados:\n{exc}",
                parent=parent,
            )
            return False
        return True



COR_PRINCIPAL = "#0b4b52"
COR_PRINCIPAL_ESCURO = "#083b41"
COR_WEEKEND = "#d8f1f4"
COR_FERIAS = "#78dafa"
COR_BRANCO = "#ffffff"
COR_LINHA = "#b7b7b7"
COR_LINHA_INTERNA = "#a6a6a6"
COR_AZUL_REFEICAO = "#1f73e8"
COR_EMENTA = "#008f3a"
COR_OBS = "#111111"
COR_VERMELHO = "#b90f12"
COR_CINZA = "#777777"

MASTER_NIM = "admin"
MASTER_PASSWORD = "Bangui123#"

MESES_PT = {
    1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril",
    5: "Maio", 6: "Junho", 7: "Julho", 8: "Agosto",
    9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro",
}

REFEICOES = ["Almoço", "Jantar"]

POSTOS = [
    "OF-6", "OF-5", "OF-4", "OF-3", "OF-2", "OF-1",
    "OR-9", "OR-8", "OR-7", "OR-6", "OR-5", "OR-4", "OR-3", "OR-2", "OR-1"
]

TIPOS_ACESSO = [
    "Administrador",
    "Gestão Welfare Mensal",
    "Gestão Ementa",
    "Gestão Welfare Individual",
    "Gestão Caixa",
    "Leitura",
    "Pessoal/Gestão Férias",
]

TIPOS_WELFARE = {
    "Welfare": ["cooking.png"],
    "Welfare Livre": ["cooking.png", "star.png"],
    "Welfare Aniversário": ["cooking.png", "cake.png"],
    "Welfare Outros": ["cooking.png", "three-dots.png"],
}


TIPOS_ACESSO_DESCRICAO = {
    "Administrador": "Acesso total",
    "Gestão Welfare Mensal": "Elabora o plano mensal de Welfare.",
    "Gestão Ementa": "Consulta a ementa mensal; a edição é reservada à Gestão Welfare Mensal, Administrador ou Responsável Welfare.",
    "Gestão Welfare Individual": "Gere os Welfares Individuais do contingente.",
    "Gestão Caixa": "Gere entradas, saídas e balanços da Caixa.",
    "Leitura": "Acesso em modo de Leitura/Consulta.",
    "Pessoal/Gestão Férias": "Gere as férias do pessoal do contingente.",
}

ACESSOS_EDITAM_WELFARES_MENSAIS = {"Administrador", "Gestão Welfare Mensal"}
ACESSOS_APAGAM_WELFARES_MENSAIS = {"Administrador", "Gestão Welfare Mensal"}
ACESSOS_EDITAM_EMENTAS_MENSAIS = {"Administrador", "Gestão Welfare Mensal"}

ACESSOS_VEEM_BOTAO_EDITAR_WELFARES_MENSAIS = {"Administrador", "Gestão Welfare Mensal"}


ACESSOS_EDITAM_WELFARES_INDIVIDUAIS = {"Administrador", "Gestão Welfare Individual"}
ACESSOS_VEEM_WELFARES_INDIVIDUAIS = {"Administrador", "Gestão Welfare Individual", "Leitura"}
ACESSOS_GEREM_FERIAS = {"Administrador", "Pessoal/Gestão Férias"}
