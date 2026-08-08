import json
import hashlib
import ctypes
import os
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import tkinter as tk
import urllib.request
import webbrowser
from datetime import datetime
from pathlib import Path

import app.config as config


_backup_lock = threading.Lock()
DEFAULT_SERVER_PORT = 52147


def _utilizador_real_windows():
    """Obtém o utilizador do token, sem depender do ambiente do processo."""
    if os.name != "nt":
        return ""
    try:
        tamanho = ctypes.c_uint32(256)
        buffer = ctypes.create_unicode_buffer(tamanho.value)
        if ctypes.windll.advapi32.GetUserNameW(buffer, ctypes.byref(tamanho)):
            return buffer.value
    except (AttributeError, OSError, ValueError):
        pass
    return ""


def _ambiente_de_reabertura_legada():
    """Reconhece o ambiente mutilado por Start-Process -UseNewEnvironment."""
    if os.name != "nt":
        return False
    utilizador_ambiente = str(os.environ.get("USERNAME") or "").strip()
    utilizador_real = _utilizador_real_windows().strip()
    return bool(
        utilizador_ambiente.casefold() == "system"
        and utilizador_real
        and utilizador_real.casefold() != "system"
        and not os.environ.get("LOCALAPPDATA")
        and not os.environ.get("USERPROFILE")
    )


def _interromper_reabertura_de_atualizador_antigo():
    """Não arranca a app quando uma versão antiga a relança apó a cópia."""
    if not getattr(sys, "frozen", False):
        return False
    # O bootloader consome PYINSTALLER_RESET_ENVIRONMENT antes de executar
    # Python. A versão antiga usava -UseNewEnvironment, cuja assinatura real
    # é USERNAME=SYSTEM sem o perfil do utilizador, embora o token continue a
    # pertencer ao utilizador que iniciou o SIGCP.
    if not _ambiente_de_reabertura_legada():
        return False
    config.messagebox.showinfo(
        "Atualização do SIGCP",
        "A atualização foi concluída.\n\n"
        "Já pode abrir normalmente a nova versão do SIGCP.",
    )
    return True


def _hash_ficheiro(caminho, bloco=1024 * 1024):
    digest = hashlib.sha256()
    with open(caminho, "rb") as ficheiro:
        while True:
            dados = ficheiro.read(bloco)
            if not dados:
                break
            digest.update(dados)
    return digest.hexdigest()


def _ps_literal(valor):
    return "'" + str(valor).replace("'", "''") + "'"


def _agendar_substituicao_executavel(origem, destino):
    pasta_updates = Path(config.CONFIG_PATH).parent / "updates"
    pasta_updates.mkdir(parents=True, exist_ok=True)
    copia_local = pasta_updates / "SIGCP.exe.new"
    shutil.copy2(origem, copia_local)
    if _hash_ficheiro(copia_local) != _hash_ficheiro(origem):
        copia_local.unlink(missing_ok=True)
        raise RuntimeError("A cópia da atualização não passou a verificação de integridade.")

    caminho_log = pasta_updates / "update.log"
    script = (
        "$ErrorActionPreference='Stop'; Start-Sleep -Milliseconds 800; "
        f"$src={_ps_literal(copia_local)}; $dst={_ps_literal(destino)}; "
        f"$log={_ps_literal(caminho_log)}; "
        "$tmp=$dst+'.update'; $ok=$false; $detail=''; "
        "for($i=0;$i -lt 60;$i++){ try { "
        "Copy-Item -LiteralPath $src -Destination $tmp -Force -ErrorAction Stop; "
        "$srcHash=(Get-FileHash -LiteralPath $src -Algorithm SHA256).Hash; "
        "$tmpHash=(Get-FileHash -LiteralPath $tmp -Algorithm SHA256).Hash; "
        "if($srcHash -ne $tmpHash){ throw 'A cópia temporária falhou a verificação.' }; "
        "Move-Item -LiteralPath $tmp -Destination $dst -Force -ErrorAction Stop; "
        "$dstHash=(Get-FileHash -LiteralPath $dst -Algorithm SHA256).Hash; "
        "if($srcHash -ne $dstHash){ throw 'O executável final falhou a verificação.' }; "
        "$ok=$true; break } catch { $detail=$_.Exception.Message; "
        "Start-Sleep -Milliseconds 500 } }; "
        "Remove-Item -LiteralPath $tmp -Force -ErrorAction SilentlyContinue; "
        "if($ok){ Remove-Item -LiteralPath $src -Force -ErrorAction SilentlyContinue; "
        "$message='A atualização foi concluída. Pode abrir normalmente a aplicação SIGCP.'; "
        "$icon='Information'; $status='SUCESSO' } else { "
        "$message='Não foi possível concluir a atualização do SIGCP.'; "
        "$icon='Error'; $status='ERRO: '+$detail }; "
        "try { Add-Content -LiteralPath $log -Value "
        "((Get-Date -Format 'yyyy-MM-dd HH:mm:ss')+' '+$status) -Encoding UTF8 "
        "} catch {}; "
        "try { Add-Type -AssemblyName System.Windows.Forms; "
        "[System.Windows.Forms.MessageBox]::Show($message, 'Atualização do SIGCP', "
        "[System.Windows.Forms.MessageBoxButtons]::OK, "
        "[System.Windows.Forms.MessageBoxIcon]$icon) | Out-Null "
        "} catch { try { $shell=New-Object -ComObject WScript.Shell; "
        "$shell.Popup($message, 0, 'Atualização do SIGCP', 0) | Out-Null } catch {} }"
    )
    ambiente = {
        chave: valor
        for chave, valor in os.environ.items()
        if not chave.startswith("_PYI_") and chave != "_MEIPASS2"
    }
    argumentos = [
        os.path.join(
            os.environ.get("SystemRoot") or os.environ.get("windir") or r"C:\Windows",
            "System32", "WindowsPowerShell", "v1.0", "powershell.exe",
        ),
        "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden",
        "-Command", script,
    ]

    # O bootloader onefile chama SetDllDirectoryW(_MEIPASS), e o Windows passa
    # esse estado aos subprocessos. Um PowerShell com essa pesquisa de DLL
    # contaminada pode falhar ao carregar WinForms/Winsock. Limpa-a apenas
    # durante a criação do helper externo e restaura-a logo depois.
    restaurar_dll_dir = str(getattr(sys, "_MEIPASS", "") or "")
    dll_dir_limpa = False
    if os.name == "nt" and getattr(sys, "frozen", False):
        try:
            dll_dir_limpa = bool(ctypes.windll.kernel32.SetDllDirectoryW(None))
        except (AttributeError, OSError):
            dll_dir_limpa = False
    try:
        processo = subprocess.Popen(
            argumentos,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            close_fds=True,
            env=ambiente,
        )
    finally:
        if dll_dir_limpa and restaurar_dll_dir:
            ctypes.windll.kernel32.SetDllDirectoryW(restaurar_dll_dir)
    return processo


def _confirmar_atualizacao_obrigatoria():
    """Permite fechar a aplicação ou voltar atrás e atualizar."""
    resultado = {"atualizar": False}
    raiz = tk.Tk()
    raiz.withdraw()
    janela = tk.Toplevel(raiz)
    janela.title("Atualização obrigatória do SIGCP")
    janela.resizable(False, False)
    janela.transient(raiz)

    corpo = tk.Frame(janela, padx=24, pady=20)
    corpo.pack(fill="both", expand=True)
    tk.Label(
        corpo,
        text=(
            "A aplicação tem de ser atualizada para poder ser utilizada.\n\n"
            "Pode fechar agora ou voltar atrás e fazer a atualização."
        ),
        justify="left",
        wraplength=430,
    ).pack(anchor="w")

    botoes = tk.Frame(corpo)
    botoes.pack(anchor="e", pady=(22, 0))

    def concluir(atualizar):
        resultado["atualizar"] = atualizar
        janela.destroy()

    tk.Button(
        botoes, text="Fechar", width=12, command=lambda: concluir(False)
    ).pack(side="left", padx=(0, 10))
    botao_atualizar = tk.Button(
        botoes, text="Atualizar", width=12, command=lambda: concluir(True)
    )
    botao_atualizar.pack(side="left")
    janela.protocol("WM_DELETE_WINDOW", lambda: concluir(False))
    janela.bind("<Escape>", lambda _event: concluir(False))
    janela.bind("<Return>", lambda _event: concluir(True))
    janela.update_idletasks()
    x = max(0, (janela.winfo_screenwidth() - janela.winfo_width()) // 2)
    y = max(0, (janela.winfo_screenheight() - janela.winfo_height()) // 2)
    janela.geometry(f"+{x}+{y}")
    janela.grab_set()
    botao_atualizar.focus_set()
    raiz.wait_window(janela)
    raiz.destroy()
    return resultado["atualizar"]


def verificar_atualizacao():
    """Compara o executável local com o publicado e agenda a troca se aceite."""
    if not getattr(sys, "frozen", False):
        return False
    configuracao = config._ler_config_local()
    pasta_raw = ""
    conn = None
    try:
        conn = sqlite3.connect(config.DB_PATH, timeout=5)
        row = conn.execute(
            "SELECT valor FROM app_settings WHERE chave='update_folder'"
        ).fetchone()
        pasta_raw = str(row[0] if row else "").strip()
    except sqlite3.Error:
        pasta_raw = ""
    finally:
        if conn is not None:
            conn.close()
    pasta_raw = pasta_raw or str(configuracao.get("update_folder") or "").strip()
    if not pasta_raw:
        return False
    pasta = os.path.abspath(
        os.path.expandvars(os.path.expanduser(pasta_raw))
    )
    publicado = Path(pasta) / "SIGCP.exe"
    local = Path(sys.executable)
    try:
        if not publicado.is_file() or publicado.resolve() == local.resolve():
            return False
        if publicado.stat().st_size == local.stat().st_size:
            if _hash_ficheiro(publicado) == _hash_ficheiro(local):
                return False
    except OSError:
        # Uma partilha temporariamente indisponível não impede o arranque.
        return False

    versao_disponivel = config.get_executable_version(publicado) or "desconhecida"
    atualizar = config.messagebox.askyesno(
        f"{config.APP_NAME} {config.APP_VERSION}",
        "A versão instalada está desatualizada.\n\n"
        f"Versão instalada: {config.APP_VERSION}\n"
        f"Versão disponível: {versao_disponivel}\n\n"
        "Deseja atualizar agora?\n\n"
        f"Origem: {publicado}",
    )
    if not atualizar:
        atualizar = _confirmar_atualizacao_obrigatoria()
        if not atualizar:
            # A atualização é obrigatória: interrompe sempre o arranque.
            return True
    try:
        _agendar_substituicao_executavel(publicado, local)
    except Exception as exc:
        config.messagebox.showerror(
            "Atualização do SIGCP",
            f"Não foi possível preparar a atualização:\n\n{exc}",
        )
        # Não inicia uma versão que já se sabe estar desatualizada.
        return True
    return True


def _browser_automatico_ativo():
    return (
        os.environ.get("SIGCP_NO_BROWSER") != "1"
        and os.environ.get("PRT_WELFARE_NO_BROWSER") != "1"
    )


def _porta_servidor():
    valor = str(os.environ.get("SIGCP_PORT") or DEFAULT_SERVER_PORT).strip()
    try:
        porta = int(valor)
    except ValueError as exc:
        raise RuntimeError("A porta configurada para o SIGCP não é válida.") from exc
    if not 0 <= porta <= 65535:
        raise RuntimeError("A porta configurada para o SIGCP não é válida.")
    return porta


def _endereco_servidor(porta):
    return f"http://127.0.0.1:{int(porta)}/"


def _instancia_sigcp_ativa(porta, timeout=0.35):
    if not porta:
        return False
    try:
        with urllib.request.urlopen(
            f"{_endereco_servidor(porta)}api/instance", timeout=timeout
        ) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return bool(
            payload.get("ok")
            and payload.get("application") == config.APP_NAME
            and payload.get("instance") is True
        )
    except Exception:
        return False


def _aguardar_instancia_sigcp(porta, timeout=4.0):
    limite = time.monotonic() + max(0.1, float(timeout))
    while time.monotonic() < limite:
        if _instancia_sigcp_ativa(porta):
            return True
        time.sleep(0.12)
    return False


def _abrir_endereco(endereco):
    if _browser_automatico_ativo():
        webbrowser.open(endereco, new=2)


def _reservar_porta(porta):
    """Reserva a porta antes da inicialização para impedir arranques em corrida."""
    if not porta:
        return None
    reserva = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            reserva.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        reserva.bind(("127.0.0.1", int(porta)))
        return reserva
    except OSError:
        reserva.close()
        return None


def _numero_ambiente(nome, predefinido, minimo):
    try:
        return max(float(minimo), float(os.environ.get(nome, predefinido)))
    except (TypeError, ValueError):
        return float(predefinido)


class BrowserLifecycle:
    """Encerra o servidor quando o último separador SIGCP desaparece."""

    def __init__(
        self,
        shutdown_callback,
        *,
        stale_after=180.0,
        close_grace=2.5,
        clock=time.monotonic,
    ):
        self._shutdown_callback = shutdown_callback
        self._stale_after = max(1.0, float(stale_after))
        self._close_grace = max(0.1, float(close_grace))
        self._clock = clock
        self._lock = threading.Lock()
        self._tabs = {}
        self._browser_seen = False
        self._empty_since = None
        self._shutdown_sent = False

    def signal(self, tab_id, event="heartbeat"):
        tab_id = str(tab_id or "").strip()[:120]
        if not tab_id:
            return
        now = self._clock()
        with self._lock:
            if self._shutdown_sent:
                return
            if event == "close":
                self._tabs.pop(tab_id, None)
                if self._browser_seen and not self._tabs and self._empty_since is None:
                    self._empty_since = now
                return
            self._browser_seen = True
            self._tabs[tab_id] = now
            self._empty_since = None

    def poll(self):
        now = self._clock()
        should_shutdown = False
        with self._lock:
            if self._shutdown_sent:
                return True
            stale = [
                tab_id
                for tab_id, last_seen in self._tabs.items()
                if now - last_seen >= self._stale_after
            ]
            for tab_id in stale:
                self._tabs.pop(tab_id, None)
            if self._tabs or not self._browser_seen:
                self._empty_since = None
                return False
            if self._empty_since is None:
                self._empty_since = now
                return False
            if now - self._empty_since >= self._close_grace:
                self._shutdown_sent = True
                should_shutdown = True
        if should_shutdown:
            self._shutdown_callback()
        return should_shutdown

    def watch(self, stop_event, interval=0.5):
        while not stop_event.wait(max(0.05, float(interval))):
            if self.poll():
                return


def _criar_snapshot_sqlite(origem, destino_local):
    """Cria localmente uma cópia SQLite consistente da base de dados."""
    origem_conn = None
    destino_conn = None
    try:
        # Usa o mesmo formato de caminho da aplicação. Isto é mais compatível
        # com unidades de rede/UNC do Windows do que construir manualmente um URI.
        origem_conn = sqlite3.connect(str(origem), timeout=30)
        origem_conn.execute("PRAGMA busy_timeout = 30000")
        destino_conn = sqlite3.connect(str(destino_local), timeout=30)
        origem_conn.backup(destino_conn)
        destino_conn.commit()
        resultado = destino_conn.execute("PRAGMA quick_check").fetchone()
        if not resultado or str(resultado[0]).lower() != "ok":
            raise sqlite3.DatabaseError("o snapshot SQLite não passou a verificação")
    finally:
        if destino_conn is not None:
            destino_conn.close()
        if origem_conn is not None:
            origem_conn.close()


def _criar_pasta_backup_data(pasta_backup):
    """Reserva atomicamente uma pasta com o formato data_hora pedido."""
    while True:
        nome_pasta = datetime.now().strftime("%d%m%Y_%H%M%S")
        destino_dir = pasta_backup / nome_pasta
        try:
            destino_dir.mkdir()
            return destino_dir
        except FileExistsError:
            # Dois logins no mesmo segundo não podem usar a mesma pasta.
            time.sleep(0.05)


def _limpar_backups_antigos(pasta_backup, max_backups):
    """Tenta aplicar a retenção sem invalidar um backup já concluído."""
    backups = []
    try:
        pastas = list(pasta_backup.iterdir())
    except OSError:
        # Alguns servidores permitem criar ficheiros mas não listar/apagar.
        return

    for pasta in pastas:
        try:
            if not pasta.is_dir():
                continue
            instante = datetime.strptime(pasta.name, "%d%m%Y_%H%M%S")
        except (OSError, ValueError):
            continue
        backups.append((instante, pasta))
    backups.sort(key=lambda item: item[0], reverse=True)

    for _instante, antigo in backups[max_backups:]:
        try:
            shutil.rmtree(antigo)
        except OSError:
            # O comportamento antigo também não fazia falhar o login quando
            # o servidor recusava a eliminação de uma cópia antiga.
            continue


def configurar_base_dados():
    """Carrega a base guardada ou pede ao utilizador para a selecionar."""
    caminho_teste = os.environ.get("SIGCP_DB_PATH") or os.environ.get(
        "PRT_WELFARE_DB_PATH"
    )
    if caminho_teste:
        valido, erro = config.validar_base_dados(caminho_teste)
        if not valido:
            raise RuntimeError(erro)
        config.set_db_path(caminho_teste)
        return True

    configuracao = config._ler_config_local()
    config.SUPABASE_URL = str(configuracao.get("supabase_url") or config.DEFAULT_SUPABASE_URL).rstrip("/")
    config.SUPABASE_KEY = str(configuracao.get("supabase_key") or config.DEFAULT_SUPABASE_KEY).strip()
    if str(configuracao.get("database_mode") or "local").lower() == "supabase":
        config.aplicar_configuracao_base_dados(configuracao)
        from app.supabase_store import descarregar
        try:
            descarregar(criar_se_vazio=True, force=True)
        except Exception as exc:
            config.SUPABASE_OFFLINE = True
            config.DATABASE_OFFLINE = True
            config.messagebox.showwarning(
                config.APP_NAME,
                f"{exc}\n\nA aplicação será aberta em modo offline. "
                "A conta de superadministrador continua disponível, mas não "
                "será possível alterar os dados online até a ligação regressar.",
            )
        return True
    caminho_guardado = configuracao.get("database_path")

    valido, _erro = config.validar_base_dados(caminho_guardado)
    if valido:
        config.set_db_path(caminho_guardado)
        return True

    # Se o ficheiro foi movido, apagado ou a partilha deixou de estar acessível,
    # volta a pedir a localização. A função persiste a nova escolha em Documentos.
    config.DATABASE_OFFLINE = False
    return config.garantir_base_dados_configurada()


def criar_backup_base_dados(max_backups=20):
    """Cria um snapshot consistente e copia-o para a pasta junto à base."""
    max_backups = max(1, int(max_backups))
    origem = Path(os.path.abspath(config.DB_PATH))
    if not origem.is_file():
        raise FileNotFoundError(f"A base de dados não foi encontrada: {origem}")

    pasta_backup = origem.parent / "db_backup"
    try:
        pasta_backup.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise RuntimeError(
            f"Não foi possível aceder à pasta de backups '{pasta_backup}': {exc}"
        ) from exc

    with _backup_lock:
        with tempfile.TemporaryDirectory(prefix="sigcp_backup_") as temp_dir:
            snapshot_local = Path(temp_dir) / config.DB_FILENAME
            try:
                _criar_snapshot_sqlite(origem, snapshot_local)
            except Exception as exc:
                raise RuntimeError(
                    f"Não foi possível criar o snapshot da base de dados: {exc}"
                ) from exc

            try:
                destino_dir = _criar_pasta_backup_data(pasta_backup)
            except OSError as exc:
                raise RuntimeError(
                    f"Não foi possível criar uma pasta em '{pasta_backup}': {exc}"
                ) from exc

            destino = destino_dir / config.DB_FILENAME
            try:
                # O servidor recebe uma cópia normal de um snapshot já
                # fechado. Não se abre uma segunda base SQLite na rede.
                shutil.copyfile(snapshot_local, destino)
            except Exception as exc:
                shutil.rmtree(destino_dir, ignore_errors=True)
                raise RuntimeError(
                    f"Não foi possível copiar o backup para '{destino}': {exc}"
                ) from exc

        _limpar_backups_antigos(pasta_backup, max_backups)
        return destino


def main():
    if _interromper_reabertura_de_atualizador_antigo():
        return
    porta = _porta_servidor()
    endereco_previsto = _endereco_servidor(porta) if porta else ""
    if porta and _instancia_sigcp_ativa(porta):
        _abrir_endereco(endereco_previsto)
        return

    reserva = _reservar_porta(porta)
    if porta and reserva is None:
        if _aguardar_instancia_sigcp(porta):
            _abrir_endereco(endereco_previsto)
            return
        # O processo anterior pode ter terminado durante a espera.
        reserva = _reservar_porta(porta)
        if reserva is None:
            raise RuntimeError(
                f"A porta local {porta} já está a ser utilizada por outra aplicação."
            )

    server = None
    lifecycle_stop = threading.Event()
    lifecycle_thread = None
    try:
        if not configurar_base_dados():
            return

        # Estes módulos só podem ser carregados depois de DB_PATH estar configurado.
        from app.db import init_db
        from app.web_app import create_web_app
        from werkzeug.serving import make_server

        init_db()
        if verificar_atualizacao():
            return
        web_app = create_web_app()
        web_app.config["BACKUP_CALLBACK"] = criar_backup_base_dados

        if reserva is not None:
            reserva.close()
            reserva = None
        try:
            server = make_server("127.0.0.1", porta, web_app, threaded=True)
        except OSError as exc:
            if porta and _aguardar_instancia_sigcp(porta):
                _abrir_endereco(endereco_previsto)
                return
            raise RuntimeError(
                f"Não foi possível iniciar o serviço local na porta {porta}: {exc}"
            ) from exc

        shutdown_requested = threading.Event()

        def encerrar_servidor():
            if shutdown_requested.is_set():
                return
            shutdown_requested.set()
            threading.Timer(0.15, server.shutdown).start()

        lifecycle = BrowserLifecycle(
            encerrar_servidor,
            stale_after=_numero_ambiente(
                "SIGCP_BROWSER_STALE_SECONDS", 180.0, 5.0
            ),
            close_grace=_numero_ambiente(
                "SIGCP_BROWSER_CLOSE_GRACE_SECONDS", 2.5, 0.2
            ),
        )
        web_app.config["SHUTDOWN_CALLBACK"] = encerrar_servidor
        web_app.config["BROWSER_LIFECYCLE_CALLBACK"] = lifecycle.signal
        lifecycle_thread = threading.Thread(
            target=lifecycle.watch,
            args=(lifecycle_stop,),
            name="sigcp-browser-watchdog",
            daemon=True,
        )
        lifecycle_thread.start()

        endereco = _endereco_servidor(server.server_port)
        if _browser_automatico_ativo():
            # Dá tempo ao servidor para ficar disponível antes de abrir o browser.
            threading.Timer(0.45, lambda: _abrir_endereco(endereco)).start()

        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        lifecycle_stop.set()
        if lifecycle_thread is not None:
            lifecycle_thread.join(timeout=1.0)
        if server is not None:
            server.server_close()
        if reserva is not None:
            reserva.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        try:
            config.messagebox.showerror(
                config.APP_NAME,
                f"Não foi possível iniciar a aplicação:\n\n{exc}",
            )
        except Exception:
            raise
