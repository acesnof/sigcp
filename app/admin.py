import sqlite3
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from datetime import date, datetime

from app.config import COR_PRINCIPAL, COR_VERMELHO, POSTOS, TIPOS_ACESSO, TIPOS_ACESSO_DESCRICAO, DOCS_DIR
from app.datepicker import DateEntry, DateTimeEntry
from app.db import (
    db_execute, db_execute_return_id, db_one, db_rows,
    get_utilizador_acessos, set_utilizador_acessos,
    get_valor_welfare, set_valor_welfare, get_valor_caixa, set_valor_caixa,
    get_day_offs, get_day_off, guardar_day_off, eliminar_day_off,
    get_inicio_semana, set_inicio_semana,
    get_nome_cos, set_nome_cos,
    get_lingua, set_lingua,
    get_horario_dfac, set_horario_dfac,
    exportar_base_dados_json,
)
from app.security import hash_password
from app.person_order import person_order_key
from app.utils import aplicar_icone
from app.i18n import t
from PIL import Image, ImageTk
import os

def manter_janela_em_frente(janela):
    try:
        janela.lift()
        janela.focus_force()
        janela.grab_set()
    except tk.TclError:
        pass


def avisar_parent(janela, tipo, titulo, mensagem):
    if tipo == "erro":
        messagebox.showerror(titulo, mensagem, parent=janela)
    elif tipo == "info":
        messagebox.showinfo(titulo, mensagem, parent=janela)
    else:
        messagebox.showwarning(titulo, mensagem, parent=janela)
    manter_janela_em_frente(janela)


class AdminWindow:
    def __init__(self, app, modo_pessoal=False):
        self.app = app
        self.modo_pessoal = modo_pessoal
        self.mostrar_todos_utilizadores = False
        self.btn_mostrar_todos = None
        self.lbl_filtro_utilizadores = None
        self.lbl_valor_welfare = None
        self.lbl_valor_caixa = None
        self.icones_tabela = {}
        self.labels_icones_tabela = []

        self.janela = tk.Toplevel(app.root)
        aplicar_icone(self.janela)
        self.app.registar_janela(self.janela, "pessoal" if self.modo_pessoal else "administracao")

        self.janela.title(t("personnel") if self.modo_pessoal else t("admin_title"))
        self.janela.geometry("1100x650")
        self.janela.minsize(1000, 600)
        self.janela.configure(bg="white")
        try:
            self.janela.state("zoomed")
        except tk.TclError:
            self.janela.attributes("-zoomed", True)

        self.criar_layout()

    def criar_layout(self):
        topo = tk.Frame(self.janela, bg=COR_PRINCIPAL, height=55)
        topo.pack(fill="x")
        topo.pack_propagate(False)

        tk.Label(
            topo,
            text=t("personnel") if self.modo_pessoal else t("admin_title"),
            bg=COR_PRINCIPAL,
            fg="white",
            font=("Arial", 17, "bold")
        ).pack(side="left", padx=20)

        frame = tk.Frame(self.janela, bg="white", padx=20, pady=20)
        frame.pack(fill="both", expand=True)

        barra_acoes = tk.Frame(frame, bg="white")
        barra_acoes.pack(fill="x", pady=(0, 10))

        tk.Button(
            barra_acoes,
            text=t("new_user"),
            bg=COR_PRINCIPAL,
            fg="white",
            font=("Arial", 10, "bold"),
            relief="flat",
            padx=14,
            pady=6,
            command=lambda: self.abrir_form_utilizador(None)
        ).pack(side="left")

        self.btn_mostrar_todos = tk.Button(
            barra_acoes,
            text=t("show_all"),
            bg="white",
            fg=COR_PRINCIPAL,
            activebackground="white",
            activeforeground=COR_PRINCIPAL,
            font=("Arial", 10, "bold"),
            relief="solid",
            bd=1,
            padx=14,
            pady=5,
            command=self.alternar_filtro_utilizadores
        )
        self.btn_mostrar_todos.pack(side="left", padx=(10, 0))

        self.lbl_filtro_utilizadores = tk.Label(
            barra_acoes,
            text=t("showing_active_users"),
            bg="white",
            fg="#555555",
            font=("Arial", 9)
        )
        self.lbl_filtro_utilizadores.pack(side="left", padx=(12, 0))

        if not self.modo_pessoal:
            tk.Button(
                barra_acoes,
                text=t("welfare_value"),
                bg=COR_PRINCIPAL,
                fg="white",
                font=("Arial", 10, "bold"),
                relief="flat",
                padx=14,
                pady=6,
                command=self.abrir_valor_welfare
            ).pack(side="left", padx=(12, 0))

            self.lbl_valor_welfare = tk.Label(
                barra_acoes,
                text=self.texto_valor_welfare(),
                bg="white",
                fg=COR_PRINCIPAL,
                font=("Arial", 10, "bold")
            )
            self.lbl_valor_welfare.pack(side="left", padx=(10, 0))

            tk.Button(
                barra_acoes,
                text=t("box_value"),
                bg=COR_PRINCIPAL,
                fg="white",
                font=("Arial", 10, "bold"),
                relief="flat",
                padx=14,
                pady=6,
                command=self.abrir_valor_caixa
            ).pack(side="left", padx=(12, 0))

            self.lbl_valor_caixa = tk.Label(
                barra_acoes,
                text=self.texto_valor_caixa(),
                bg="white",
                fg=COR_PRINCIPAL,
                font=("Arial", 10, "bold")
            )
            self.lbl_valor_caixa.pack(side="left", padx=(10, 0))

            tk.Button(
                barra_acoes,
                text=t("cos_name"),
                bg="white",
                fg=COR_PRINCIPAL,
                activebackground="white",
                activeforeground=COR_PRINCIPAL,
                font=("Arial", 10, "bold"),
                relief="solid",
                bd=1,
                padx=14,
                pady=5,
                command=self.abrir_nome_cos
            ).pack(side="left", padx=(10, 0))

            tk.Button(
                barra_acoes,
                text=t("days_off"),
                bg="white",
                fg=COR_PRINCIPAL,
                activebackground="white",
                activeforeground=COR_PRINCIPAL,
                font=("Arial", 10, "bold"),
                relief="solid",
                bd=1,
                padx=14,
                pady=5,
                command=self.abrir_day_offs
            ).pack(side="left", padx=(10, 0))



            tk.Button(
                barra_acoes,
                text="Horário DFAC",
                bg="white",
                fg=COR_PRINCIPAL,
                activebackground="white",
                activeforeground=COR_PRINCIPAL,
                font=("Arial", 10, "bold"),
                relief="solid",
                bd=1,
                padx=14,
                pady=5,
                command=self.abrir_horario_dfac
            ).pack(side="left", padx=(10, 0))

            tk.Button(
                barra_acoes,
                text=t("week_start"),
                bg="white",
                fg=COR_PRINCIPAL,
                activebackground="white",
                activeforeground=COR_PRINCIPAL,
                font=("Arial", 10, "bold"),
                relief="solid",
                bd=1,
                padx=14,
                pady=5,
                command=self.abrir_inicio_semana
            ).pack(side="left", padx=(10, 0))

            tk.Button(
                barra_acoes,
                text=t("language"),
                bg="white",
                fg=COR_PRINCIPAL,
                activebackground="white",
                activeforeground=COR_PRINCIPAL,
                font=("Arial", 10, "bold"),
                relief="solid",
                bd=1,
                padx=14,
                pady=5,
                command=self.abrir_lingua
            ).pack(side="left", padx=(10, 0))

            tk.Button(
                barra_acoes,
                text=t("export_json"),
                bg="white",
                fg=COR_PRINCIPAL,
                activebackground="white",
                activeforeground=COR_PRINCIPAL,
                font=("Arial", 10, "bold"),
                relief="solid",
                bd=1,
                padx=14,
                pady=5,
                command=self.exportar_json
            ).pack(side="left", padx=(10, 0))

        colunas = (
            "nim",
            "posto",
            "antiguidade",
            "snr",
            "responsavel_welfare",
            "nome",
            "sobrenome",
            "data_chegada",
            "data_partida",
            "tipo_acesso",
            "master",
        )

        style = ttk.Style(self.janela)
        style.configure("Admin.Treeview", rowheight=52, font=("Arial", 11))
        style.configure("Admin.Treeview.Heading", font=("Arial", 10, "bold"), anchor="center")

        self.tabela = ttk.Treeview(frame, columns=colunas, show="headings", height=20, style="Admin.Treeview")

        headers = {
            "nim": "NIM (Utilizador)",
            "posto": "Posto",
            "antiguidade": "Antiguidade",
            "snr": "SNR",
            "responsavel_welfare": "Welfare",
            "nome": "Nome",
            "sobrenome": "Sobrenome",
            "data_chegada": "Data Chegada",
            "data_partida": "Data Partida",
            "tipo_acesso": "Tipos de Acesso",
            "master": "Mestre",
        }

        widths = {
            "nim": 100,
            "posto": 80,
            "antiguidade": 105,
            "snr": 70,
            "responsavel_welfare": 85,
            "nome": 150,
            "sobrenome": 160,
            "data_chegada": 110,
            "data_partida": 110,
            "tipo_acesso": 260,
            "master": 70,
        }

        for col in colunas:
            self.tabela.heading(col, text=headers[col], anchor="center")
            self.tabela.column(col, width=widths[col], anchor="center")

        self.tabela.tag_configure("par", background="#f8fbfc")
        self.tabela.tag_configure("impar", background="white")

        # Barra inferior fixa: fica sempre visível, mesmo com a janela maximizada
        # e com a Treeview cheia de registos.
        botoes = tk.Frame(frame, bg="white", pady=10)
        botoes.pack(side="bottom", fill="x")

        self.btn_editar_utilizador = tk.Button(
            botoes,
            text=t("edit_change_password"),
            bg=COR_PRINCIPAL,
            fg="white",
            font=("Arial", 10, "bold"),
            relief="flat",
            width=24,
            command=self.editar
        )
        self.btn_editar_utilizador.pack(side="left", padx=(0, 10))

        self.btn_eliminar_utilizador = tk.Button(
            botoes,
            text=t("delete"),
            bg=COR_VERMELHO,
            fg="white",
            font=("Arial", 10, "bold"),
            relief="flat",
            width=14,
            command=self.eliminar
        )
        self.btn_eliminar_utilizador.pack(side="left")

        self.tabela.pack(side="top", fill="both", expand=True)
        self.tabela.bind("<Configure>", lambda e: self.janela.after(80, self.atualizar_icones_tabela))
        self.tabela.bind("<Expose>", lambda e: self.janela.after(80, self.atualizar_icones_tabela))
        self.tabela.bind("<MouseWheel>", lambda e: self.janela.after(80, self.atualizar_icones_tabela))
        self.tabela.bind("<ButtonRelease-1>", lambda e: self.janela.after(80, self.atualizar_icones_tabela))

        self.carregar_tabela()


    def carregar_icones_tabela(self):
        """Carrega ícones da lista de utilizadores.
        SNR usa docs/snr.png; Responsável Welfare usa docs/cook.png.
        Se algum ficheiro não existir, usa um fallback visual.
        """
        self.icones_tabela = {"snr": None, "welfare": None}

        ficheiros = {
            "snr": ["snr.png", "star.png"],
            "welfare": ["cook.png", "cooking.png"],
        }

        for chave, nomes in ficheiros.items():
            for nome in nomes:
                caminho = os.path.join(DOCS_DIR, nome)
                if os.path.exists(caminho):
                    try:
                        img = Image.open(caminho).convert("RGBA")
                        img.thumbnail((40, 40), Image.LANCZOS)
                        self.icones_tabela[chave] = ImageTk.PhotoImage(img)
                        break
                    except Exception:
                        self.icones_tabela[chave] = None

    def limpar_icones_tabela(self):
        for lbl in getattr(self, "labels_icones_tabela", []):
            try:
                lbl.destroy()
            except tk.TclError:
                pass
        self.labels_icones_tabela = []

    def atualizar_icones_tabela(self):
        """Desenha ícones dentro das colunas SNR/Welfare.
        O ttk.Treeview não suporta imagens por célula em show='headings',
        por isso os ícones são labels sobrepostos nas células visíveis.
        """
        if not getattr(self, "tabela", None):
            return

        self.limpar_icones_tabela()
        self.tabela.update_idletasks()

        for item in self.tabela.get_children():
            tags = set(tag for tag in (self.tabela.item(item, "tags") or []) if tag)
            row_bg = "#f8fbfc" if "par" in tags else "white"

            if "snr_icon" in tags:
                self._colocar_icone_tabela(item, "snr", self.icones_tabela.get("snr"), "★", row_bg)

            if "welfare_icon" in tags:
                self._colocar_icone_tabela(item, "responsavel_welfare", self.icones_tabela.get("welfare"), "🍴", row_bg)

    def _colocar_icone_tabela(self, item, coluna, imagem, fallback, bg):
        try:
            bbox = self.tabela.bbox(item, coluna)
        except tk.TclError:
            bbox = None

        if not bbox:
            return

        x, y, w, h = bbox

        if imagem:
            lbl = tk.Label(self.tabela, image=imagem, bg=bg, bd=0)
        else:
            lbl = tk.Label(self.tabela, text=fallback, bg=bg, fg=COR_PRINCIPAL, font=("Arial", 21, "bold"), bd=0)

        lbl.place(x=x + (w // 2), y=y + (h // 2), anchor="center")
        self.labels_icones_tabela.append(lbl)

    def texto_valor_welfare(self):
        valor = (get_valor_welfare() or "").strip()
        return f"{t('current_welfare_value')}: {valor}" if valor else f"{t('current_welfare_value')}: -"

    def atualizar_label_valor_welfare(self):
        if self.lbl_valor_welfare:
            self.lbl_valor_welfare.config(text=self.texto_valor_welfare())

    def texto_valor_caixa(self):
        valor = (get_valor_caixa() or "").strip()
        return f"{t('current_box_value')}: {valor}" if valor else f"{t('current_box_value')}: -"

    def atualizar_label_valor_caixa(self):
        if self.lbl_valor_caixa:
            self.lbl_valor_caixa.config(text=self.texto_valor_caixa())

    def abrir_valor_welfare(self):
        if self.app.trazer_janela_tipo("valor_welfare"):
            return
        janela = tk.Toplevel(self.app.root)
        aplicar_icone(janela)
        self.app.registar_janela(janela, "valor_welfare")

        janela.title(t("welfare_value"))
        janela.geometry("380x190")
        janela.resizable(False, False)
        janela.configure(bg="white")
        janela.grab_set()

        tk.Label(
            janela,
            text=t("current_welfare_value_title"),
            bg="white",
            fg=COR_PRINCIPAL,
            font=("Arial", 15, "bold")
        ).pack(pady=(18, 12))

        frame = tk.Frame(janela, bg="white", padx=30)
        frame.pack(fill="x")

        tk.Label(frame, text=t("value"), bg="white", font=("Arial", 10, "bold")).pack(anchor="w")
        entry_valor = tk.Entry(frame, width=32)
        entry_valor.insert(0, get_valor_welfare() or "")
        entry_valor.pack(anchor="w", pady=(3, 14), ipady=4)
        entry_valor.focus_set()

        def guardar():
            valor = entry_valor.get().strip()
            if valor:
                try:
                    int(valor)
                except ValueError:
                    avisar_parent(janela, "aviso", t("validation"), t("only_numbers_welfare"))
                    return

            set_valor_welfare(valor)
            self.atualizar_label_valor_welfare()
            avisar_parent(janela, "info", t("saved"), t("welfare_value_saved"))
            janela.destroy()

        botoes = tk.Frame(janela, bg="white")
        botoes.pack(fill="x", pady=(0, 10))

        tk.Button(
            botoes,
            text=t("save"),
            bg=COR_PRINCIPAL,
            fg="white",
            font=("Arial", 10, "bold"),
            relief="flat",
            width=12,
            command=guardar
        ).pack(side="left", padx=(70, 10))

        tk.Button(
            botoes,
            text=t("close"),
            bg="#777",
            fg="white",
            font=("Arial", 10, "bold"),
            relief="flat",
            width=12,
            command=janela.destroy
        ).pack(side="left")


    def abrir_nome_cos(self):
        if self.app.trazer_janela_tipo("nome_cos"):
            return

        janela = tk.Toplevel(self.app.root)
        aplicar_icone(janela)
        self.app.registar_janela(janela, "nome_cos")

        janela.title(t("cos_name_title"))
        janela.geometry("520x230")
        janela.resizable(False, False)
        janela.configure(bg="white")
        janela.grab_set()

        tk.Label(
            janela,
            text=t("cos_name_title"),
            bg="white",
            fg=COR_PRINCIPAL,
            font=("Arial", 15, "bold")
        ).pack(pady=(18, 8))

        tk.Label(
            janela,
            text=t("cos_name_help"),
            bg="white",
            fg="#555555",
            font=("Arial", 9),
            wraplength=440,
            justify="left"
        ).pack(padx=30, anchor="w")

        frame = tk.Frame(janela, bg="white", padx=30)
        frame.pack(fill="x", pady=(10, 0))

        tk.Label(frame, text=t("cos_name") + ":", bg="white", font=("Arial", 10, "bold")).pack(anchor="w")
        entry_nome = tk.Entry(frame, width=58)
        entry_nome.insert(0, get_nome_cos() or "")
        entry_nome.pack(anchor="w", pady=(3, 14), ipady=4)
        entry_nome.focus_set()

        def guardar():
            set_nome_cos(entry_nome.get().strip())
            avisar_parent(janela, "info", t("saved"), t("cos_name_saved"))
            janela.destroy()

        botoes = tk.Frame(janela, bg="white")
        botoes.pack(fill="x", pady=(0, 10))

        tk.Button(
            botoes,
            text=t("save"),
            bg=COR_PRINCIPAL,
            fg="white",
            font=("Arial", 10, "bold"),
            relief="flat",
            width=12,
            command=guardar
        ).pack(side="left", padx=(130, 10))

        tk.Button(
            botoes,
            text=t("close"),
            bg="#777",
            fg="white",
            font=("Arial", 10, "bold"),
            relief="flat",
            width=12,
            command=janela.destroy
        ).pack(side="left")

    def abrir_valor_caixa(self):
        if self.app.trazer_janela_tipo("valor_caixa"):
            return
        janela = tk.Toplevel(self.app.root)
        aplicar_icone(janela)
        self.app.registar_janela(janela, "valor_caixa")

        janela.title(t("box_value"))
        janela.geometry("380x190")
        janela.resizable(False, False)
        janela.configure(bg="white")
        janela.grab_set()

        tk.Label(
            janela,
            text=t("current_box_value_title"),
            bg="white",
            fg=COR_PRINCIPAL,
            font=("Arial", 15, "bold")
        ).pack(pady=(18, 12))

        frame = tk.Frame(janela, bg="white", padx=30)
        frame.pack(fill="x")

        tk.Label(frame, text=t("value"), bg="white", font=("Arial", 10, "bold")).pack(anchor="w")
        entry_valor = tk.Entry(frame, width=32)
        entry_valor.insert(0, get_valor_caixa() or "")
        entry_valor.pack(anchor="w", pady=(3, 14), ipady=4)
        entry_valor.focus_set()

        def guardar():
            valor = entry_valor.get().strip()
            if valor:
                try:
                    int(valor)
                except ValueError:
                    avisar_parent(janela, "aviso", t("validation"), t("only_numbers_welfare"))
                    return

            set_valor_caixa(valor)
            self.atualizar_label_valor_caixa()
            avisar_parent(janela, "info", t("saved"), t("box_value_saved"))
            janela.destroy()

        botoes = tk.Frame(janela, bg="white")
        botoes.pack(fill="x", pady=(0, 10))

        tk.Button(
            botoes,
            text=t("save"),
            bg=COR_PRINCIPAL,
            fg="white",
            font=("Arial", 10, "bold"),
            relief="flat",
            width=12,
            command=guardar
        ).pack(side="left", padx=(75, 10))

        tk.Button(
            botoes,
            text=t("close"),
            bg="#777777",
            fg="white",
            font=("Arial", 10, "bold"),
            relief="flat",
            width=12,
            command=janela.destroy
        ).pack(side="left", padx=10)

        janela.update_idletasks()
        x = self.janela.winfo_x() + (self.janela.winfo_width() // 2) - (janela.winfo_width() // 2)
        y = self.janela.winfo_y() + (self.janela.winfo_height() // 2) - (janela.winfo_height() // 2)
        janela.geometry(f"+{x}+{y}")

    def abrir_day_offs(self):
        if self.app.trazer_janela_tipo("days_off"):
            return
        DayOffWindow(self)


    def abrir_horario_dfac(self):
        if self.app.trazer_janela_tipo("horario_dfac"):
            return
        HorarioDfacWindow(self)

    def abrir_inicio_semana(self):
        if self.app.trazer_janela_tipo("inicio_semana"):
            return

        janela = tk.Toplevel(self.app.root)
        aplicar_icone(janela)
        self.app.registar_janela(janela, "inicio_semana")

        janela.title(t("week_start_title"))
        janela.geometry("460x260")
        janela.resizable(False, False)
        janela.configure(bg="white")
        janela.grab_set()

        tk.Label(
            janela,
            text=t("week_start_title"),
            bg="white",
            fg=COR_PRINCIPAL,
            font=("Arial", 15, "bold")
        ).pack(pady=(18, 8))

        tk.Label(
            janela,
            text=t("week_start_help"),
            bg="white",
            fg="#555555",
            font=("Arial", 9),
            wraplength=390,
            justify="left"
        ).pack(pady=(0, 12))

        frame = tk.Frame(janela, bg="white", padx=35)
        frame.pack(fill="x")

        tk.Label(frame, text=t("date"), bg="white", font=("Arial", 10, "bold")).pack(anchor="w")
        entry_data = DateEntry(frame, get_inicio_semana() or "")
        entry_data.pack(anchor="w", pady=(3, 14))

        def guardar():
            valor = entry_data.get().strip()
            if valor:
                try:
                    date.fromisoformat(valor)
                except ValueError:
                    avisar_parent(janela, "aviso", t("validation"), t("date_format"))
                    return

            set_inicio_semana(valor)
            avisar_parent(janela, "info", t("saved"), t("week_start_saved"))
            janela.destroy()

        botoes = tk.Frame(janela, bg="white", pady=12)
        botoes.pack(fill="x")

        tk.Button(
            botoes,
            text=t("save"),
            bg=COR_PRINCIPAL,
            fg="white",
            font=("Arial", 10, "bold"),
            relief="flat",
            width=12,
            command=guardar
        ).pack(side="left", padx=(110, 10))

        tk.Button(
            botoes,
            text=t("close"),
            bg="#777",
            fg="white",
            font=("Arial", 10, "bold"),
            relief="flat",
            width=12,
            command=janela.destroy
        ).pack(side="left")

    def exportar_json(self):
        caminho = filedialog.asksaveasfilename(
            parent=self.janela,
            title=t("export_json_title"),
            initialdir=DOCS_DIR,
            initialfile=f"sigcp_export_{datetime.now():%Y%m%d_%H%M%S}.json",
            defaultextension=".json",
            filetypes=[
                (t("json_files"), "*.json"),
                (t("all_files"), "*.*"),
            ],
        )
        if not caminho:
            return

        try:
            resumo = exportar_base_dados_json(caminho)
        except Exception as exc:
            avisar_parent(
                self.janela,
                "erro",
                t("error"),
                t("export_json_error", erro=str(exc)),
            )
            return

        avisar_parent(
            self.janela,
            "info",
            t("export_json_done"),
            t(
                "export_json_success",
                tabelas=resumo["tabelas"],
                registos=resumo["registos"],
                caminho=caminho,
            ),
        )

    def abrir_lingua(self):
        if self.app.trazer_janela_tipo("lingua"):
            return
        janela = tk.Toplevel(self.app.root)
        aplicar_icone(janela)
        self.app.registar_janela(janela, "lingua")

        janela.title(t("language_title"))
        janela.geometry("420x230")
        janela.resizable(False, False)
        janela.configure(bg="white")
        janela.grab_set()

        tk.Label(
            janela,
            text=t("language_title"),
            bg="white",
            fg=COR_PRINCIPAL,
            font=("Arial", 15, "bold")
        ).pack(pady=(18, 12))

        var_lingua = tk.StringVar(value=get_lingua())

        frame = tk.Frame(janela, bg="white", padx=35)
        frame.pack(fill="x")

        tk.Radiobutton(
            frame,
            text=t("portuguese"),
            variable=var_lingua,
            value="pt",
            bg="white",
            font=("Arial", 10)
        ).pack(anchor="w", pady=4)

        tk.Radiobutton(
            frame,
            text=t("english"),
            variable=var_lingua,
            value="en",
            bg="white",
            font=("Arial", 10)
        ).pack(anchor="w", pady=4)

        def guardar():
            set_lingua(var_lingua.get())
            avisar_parent(janela, "info", t("saved"), t("language_saved"))
            janela.destroy()

        botoes = tk.Frame(janela, bg="white", pady=18)
        botoes.pack(fill="x")

        tk.Button(
            botoes,
            text=t("save"),
            bg=COR_PRINCIPAL,
            fg="white",
            font=("Arial", 10, "bold"),
            relief="flat",
            width=12,
            command=guardar
        ).pack(side="left", padx=(90, 10))

        tk.Button(
            botoes,
            text=t("close"),
            bg="#777",
            fg="white",
            font=("Arial", 10, "bold"),
            relief="flat",
            width=12,
            command=janela.destroy
        ).pack(side="left")

    def alternar_filtro_utilizadores(self):
        self.mostrar_todos_utilizadores = not self.mostrar_todos_utilizadores
        self.carregar_tabela()

    def carregar_tabela(self):
        for item in self.tabela.get_children():
            self.tabela.delete(item)

        hoje = date.today().isoformat()

        condicao_ativo = "(data_partida IS NULL OR TRIM(data_partida) = '' OR SUBSTR(data_partida, 1, 10) >= ?)"

        if self.mostrar_todos_utilizadores:
            users = db_rows("SELECT * FROM utilizadores")

            if self.btn_mostrar_todos:
                self.btn_mostrar_todos.config(text=t("show_active_only"))
            if self.lbl_filtro_utilizadores:
                self.lbl_filtro_utilizadores.config(
                    text=t("showing_all_users")
                )
        else:
            users = db_rows(f"""
                SELECT *
                FROM utilizadores
                WHERE {condicao_ativo}
            """, (hoje,))

            if self.btn_mostrar_todos:
                self.btn_mostrar_todos.config(text=t("show_all"))
            if self.lbl_filtro_utilizadores:
                self.lbl_filtro_utilizadores.config(text=t("showing_active_users"))

        users.sort(key=person_order_key)
        for idx, user in enumerate(users):
            tag_linha = "par" if idx % 2 == 0 else "impar"
            self.tabela.insert(
                "",
                "end",
                values=(
                    user["nim"],
                    user["posto"],
                    user.get("antiguidade") or "",
                    "",
                    "",
                    user["nome"],
                    user["sobrenome"],
                    user["data_chegada"],
                    user["data_partida"],
                    ", ".join(get_utilizador_acessos(user["id"])) or user["tipo_acesso"],
                    "Sim" if user["master"] else "Não",
                ),
                tags=(
                    str(user["id"]),
                    tag_linha,
                    "snr_icon" if int(user.get("snr") or 0) == 1 else "",
                    "welfare_icon" if int(user.get("responsavel_welfare") or 0) == 1 else "",
                )
            )

        self.janela.after(120, self.atualizar_icones_tabela)

    def get_selected_user(self):
        selected = self.tabela.selection()

        if not selected:
            messagebox.showwarning("Seleção", "Seleciona um utilizador.", parent=self.janela)
            manter_janela_em_frente(self.janela)
            return None

        user_id = self.tabela.item(selected[0], "tags")[0]
        return db_one("SELECT * FROM utilizadores WHERE id = ?", (user_id,))

    def editar(self):
        user = self.get_selected_user()
        if user:
            self.abrir_form_utilizador(user)

    def eliminar(self):
        user = self.get_selected_user()

        if not user:
            return

        if user["master"]:
            messagebox.showwarning("Protegido", "O utilizador mestre não pode ser eliminado.", parent=self.janela)
            manter_janela_em_frente(self.janela)
            return

        confirmar = messagebox.askyesno(
            "Eliminar",
            f"Queres eliminar o utilizador {user['nim']}?"
        )

        if not confirmar:
            return

        db_execute("DELETE FROM utilizadores WHERE id = ?", (user["id"],))
        self.carregar_tabela()

    def abrir_form_utilizador(self, user):
        janela = tk.Toplevel(self.app.root)
        aplicar_icone(janela)
        self.app.registar_janela(janela)

        editar = user is not None
        master = bool(user and user["master"])

        janela.title("Utilizador")
        janela.geometry("900x800")
        janela.resizable(False, True)
        janela.configure(bg="white")
        janela.grab_set()

        titulo = "Editar Utilizador" if editar else "Novo Utilizador"

        tk.Label(
            janela,
            text=titulo,
            bg="white",
            fg=COR_PRINCIPAL,
            font=("Arial", 16, "bold")
        ).pack(pady=(15, 10))

        corpo = tk.Frame(janela, bg="white", padx=25)
        corpo.pack(fill="both", expand=True)

        frame = tk.Frame(corpo, bg="white")
        frame.pack(side="left", fill="both", expand=True)

        if not self.modo_pessoal:
            lateral = tk.Frame(
                corpo,
                bg="#f7fbfb",
                highlightthickness=1,
                highlightbackground="#d5e6e6",
                padx=14,
                pady=12,
                width=315
            )
            lateral.pack(side="right", fill="y", padx=(22, 0))
            lateral.pack_propagate(False)

            tk.Label(
                lateral,
                text="Tipos de Acesso",
                bg="#f7fbfb",
                fg=COR_PRINCIPAL,
                font=("Arial", 12, "bold")
            ).pack(anchor="w", pady=(0, 10))

            for tipo in TIPOS_ACESSO:
                tk.Label(
                    lateral,
                    text=tipo,
                    bg="#f7fbfb",
                    fg="#111111",
                    font=("Arial", 9, "bold")
                ).pack(anchor="w", pady=(6, 0))
                tk.Label(
                    lateral,
                    text=TIPOS_ACESSO_DESCRICAO.get(tipo, ""),
                    bg="#f7fbfb",
                    fg="#333333",
                    font=("Arial", 8),
                    wraplength=280,
                    justify="left"
                ).pack(anchor="w")


        else:
            lateral = None

        def label(text):
            tk.Label(frame, text=text, bg="white", font=("Arial", 9, "bold")).pack(anchor="w")

        def entry(valor=""):
            e = tk.Entry(frame, width=45)
            e.insert(0, valor or "")
            e.pack(anchor="w", pady=(2, 8), ipady=3)
            return e

        label("NIM (Utilizador):")
        entry_nim = entry(user["nim"] if user else "")

        linha_posto_antiguidade = tk.Frame(frame, bg="white")
        linha_posto_antiguidade.pack(anchor="w", fill="x", pady=(0, 8))

        bloco_posto = tk.Frame(linha_posto_antiguidade, bg="white")
        bloco_posto.pack(side="left")
        tk.Label(bloco_posto, text="Posto:", bg="white", font=("Arial", 9, "bold")).pack(anchor="w")
        combo_posto = ttk.Combobox(bloco_posto, state="readonly", values=POSTOS, width=16)
        combo_posto.set(user["posto"] if user else POSTOS[0])
        combo_posto.pack(anchor="w", pady=(2, 0), ipady=3)

        bloco_antiguidade = tk.Frame(linha_posto_antiguidade, bg="white")
        bloco_antiguidade.pack(side="left", padx=(22, 0))
        tk.Label(bloco_antiguidade, text="Antiguidade:", bg="white", font=("Arial", 9, "bold")).pack(anchor="w")
        entry_antiguidade = DateEntry(bloco_antiguidade, user.get("antiguidade") if user else "")
        entry_antiguidade.pack(anchor="w", pady=(2, 0))

        var_snr = tk.BooleanVar(value=bool(user and int(user.get("snr") or 0) == 1))
        chk_snr = tk.Checkbutton(
            linha_posto_antiguidade,
            text="SNR",
            variable=var_snr,
            bg="white",
            activebackground="white",
            font=("Arial", 9, "bold"),
            anchor="w"
        )
        chk_snr.pack(side="left", padx=(22, 0), pady=(18, 0))

        linha_servico = tk.Frame(
            frame,
            bg="#f7fbfb",
            highlightthickness=1,
            highlightbackground="#d5e6e6",
            padx=10,
            pady=8,
        )
        linha_servico.pack(anchor="w", fill="x", pady=(0, 10))

        bloco_telemovel = tk.Frame(linha_servico, bg="#f7fbfb")
        bloco_telemovel.pack(side="left")
        tk.Label(
            bloco_telemovel,
            text=t("service_mobile"),
            bg="#f7fbfb",
            fg=COR_PRINCIPAL,
            font=("Arial", 9, "bold")
        ).pack(anchor="w")
        entry_telemovel_servico = tk.Entry(bloco_telemovel, width=28)
        entry_telemovel_servico.insert(0, (user.get("telemovel_servico") or "") if user else "")
        entry_telemovel_servico.pack(anchor="w", pady=(2, 0), ipady=3)

        var_responsavel_welfare = tk.BooleanVar(value=bool(user and int(user.get("responsavel_welfare") or 0) == 1))
        chk_responsavel_welfare = tk.Checkbutton(
            linha_servico,
            text=t("welfare_responsible"),
            variable=var_responsavel_welfare,
            bg="#f7fbfb",
            activebackground="#f7fbfb",
            fg=COR_PRINCIPAL,
            font=("Arial", 10, "bold"),
            anchor="w"
        )
        chk_responsavel_welfare.pack(side="left", padx=(24, 0), pady=(19, 0))

        label("Nome:")
        entry_nome = entry(user["nome"] if user else "")

        label("Sobrenome:")
        entry_sobrenome = entry(user["sobrenome"] if user else "")

        label("Data Chegada:")
        entry_chegada = DateTimeEntry(frame, user["data_chegada"] if user else "")
        entry_chegada.pack(anchor="w", pady=(2, 8))

        label("Data Partida:")
        entry_partida = DateTimeEntry(frame, user["data_partida"] if user else "")
        entry_partida.pack(anchor="w", pady=(2, 8))

        label("Tipos de Acesso:")

        acessos_atuais = set(get_utilizador_acessos(user["id"])) if user else {"Leitura"}
        frame_acessos = tk.Frame(frame, bg="white")
        frame_acessos.pack(anchor="w", pady=(2, 8), fill="x")

        acesso_vars = {}
        if self.modo_pessoal:
            texto_acessos = ", ".join(sorted(acessos_atuais)) if editar else "Leitura"
            tk.Label(
                frame_acessos,
                text=texto_acessos + "  (apenas o Administrador altera Tipos de Acesso)",
                bg="white",
                fg="#555555",
                font=("Arial", 9, "bold"),
                anchor="w"
            ).pack(anchor="w")
            for tipo in TIPOS_ACESSO:
                acesso_vars[tipo] = tk.BooleanVar(value=(tipo in acessos_atuais if editar else tipo == "Leitura"))
        else:
            for idx, tipo in enumerate(TIPOS_ACESSO):
                var = tk.BooleanVar(value=tipo in acessos_atuais)
                acesso_vars[tipo] = var
                chk = tk.Checkbutton(
                    frame_acessos,
                    text=tipo,
                    variable=var,
                    bg="white",
                    activebackground="white",
                    font=("Arial", 9),
                    anchor="w"
                )
                chk.grid(row=idx // 2, column=idx % 2, sticky="w", padx=(0, 20), pady=1)

        label("Password:")
        entry_password = tk.Entry(frame, width=45, show="*")
        entry_password.pack(anchor="w", pady=(2, 8), ipady=3)

        label("Confirmar Password:")
        entry_password2 = tk.Entry(frame, width=45, show="*")
        entry_password2.pack(anchor="w", pady=(2, 8), ipady=3)

        if editar:
            tk.Label(
                frame,
                text="Deixa a password em branco para manter a atual.",
                bg="white",
                fg="#666",
                font=("Arial", 8)
            ).pack(anchor="w", pady=(0, 8))

        if master:
            entry_nim.config(state="disabled")
            combo_posto.config(state="disabled")
            entry_antiguidade.config_state("disabled")
            chk_snr.config(state="disabled")
            entry_telemovel_servico.config(state="disabled")
            chk_responsavel_welfare.config(state="disabled")
            entry_nome.config(state="disabled")
            entry_sobrenome.config(state="disabled")
            entry_chegada.config_state("disabled")
            entry_partida.config_state("disabled")
            for child in frame_acessos.winfo_children():
                child.config(state="disabled")
            entry_password.config(state="disabled")
            entry_password2.config(state="disabled")

        botoes = tk.Frame(janela, bg="white", pady=15)
        botoes.pack(fill="x")

        def guardar():
            if master:
                avisar_parent(janela, "aviso", "Protegido", "O utilizador mestre é inalterável.")
                return

            nim = entry_nim.get().strip()
            posto = combo_posto.get().strip()
            antiguidade = entry_antiguidade.get()
            snr = 1 if var_snr.get() else 0
            telemovel_servico = entry_telemovel_servico.get().strip()
            responsavel_welfare = 1 if var_responsavel_welfare.get() else 0
            nome = entry_nome.get().strip()
            sobrenome = entry_sobrenome.get().strip()
            data_chegada = entry_chegada.get()
            data_partida = entry_partida.get()
            if self.modo_pessoal:
                acessos_selecionados = list(get_utilizador_acessos(user["id"])) if editar else ["Leitura"]
                if not acessos_selecionados:
                    acessos_selecionados = ["Leitura"]
            else:
                acessos_selecionados = [tipo for tipo, var in acesso_vars.items() if var.get()]
            tipo_acesso = ", ".join(acessos_selecionados)
            password = entry_password.get()
            password2 = entry_password2.get()

            if not nim:
                avisar_parent(janela, "aviso", "Validação", "O NIM é obrigatório.")
                return

            if not acessos_selecionados:
                avisar_parent(janela, "aviso", "Validação", "Seleciona pelo menos um Tipo de Acesso.")
                return

            if responsavel_welfare and not telemovel_servico:
                avisar_parent(janela, "aviso", "Validação", t("welfare_responsible_missing_phone"))
                return

            if password or password2:
                if password != password2:
                    avisar_parent(janela, "aviso", "Validação", "As passwords não coincidem.")
                    return

            if not editar and not password:
                avisar_parent(janela, "aviso", "Validação", "A password é obrigatória para novo utilizador.")
                return

            try:
                if editar:
                    if password:
                        salt, pwd_hash = hash_password(password)
                        db_execute("""
                            UPDATE utilizadores
                            SET nim = ?, posto = ?, antiguidade = ?, snr = ?, telemovel_servico = ?, responsavel_welfare = ?,
                                nome = ?, sobrenome = ?, data_chegada = ?, data_partida = ?, tipo_acesso = ?,
                                password_salt = ?, password_hash = ?
                            WHERE id = ? AND master = 0
                        """, (
                            nim, posto, antiguidade, snr, telemovel_servico, responsavel_welfare,
                            nome, sobrenome, data_chegada, data_partida, tipo_acesso, salt, pwd_hash, user["id"],
                        ))
                        set_utilizador_acessos(user["id"], acessos_selecionados)
                    else:
                        db_execute("""
                            UPDATE utilizadores
                            SET nim = ?, posto = ?, antiguidade = ?, snr = ?, telemovel_servico = ?, responsavel_welfare = ?,
                                nome = ?, sobrenome = ?, data_chegada = ?, data_partida = ?, tipo_acesso = ?
                            WHERE id = ? AND master = 0
                        """, (
                            nim, posto, antiguidade, snr, telemovel_servico, responsavel_welfare,
                            nome, sobrenome, data_chegada, data_partida, tipo_acesso, user["id"],
                        ))
                        set_utilizador_acessos(user["id"], acessos_selecionados)
                else:
                    salt, pwd_hash = hash_password(password)
                    novo_id = db_execute_return_id("""
                        INSERT INTO utilizadores (
                            nim, posto, antiguidade, snr, telemovel_servico, responsavel_welfare,
                            nome, sobrenome, data_chegada, data_partida,
                            tipo_acesso, password_salt, password_hash, master
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                    """, (
                        nim, posto, antiguidade, snr, telemovel_servico, responsavel_welfare,
                        nome, sobrenome, data_chegada, data_partida,
                        tipo_acesso, salt, pwd_hash,
                    ))
                    set_utilizador_acessos(novo_id, acessos_selecionados)

            except sqlite3.IntegrityError:
                avisar_parent(janela, "erro", "Erro", "Já existe um utilizador com esse NIM.")
                return

            self.carregar_tabela()
            janela.destroy()

        tk.Button(
            botoes,
            text=t("save"),
            bg=COR_PRINCIPAL,
            fg="white",
            font=("Arial", 10, "bold"),
            relief="flat",
            width=14,
            command=guardar,
            state="disabled" if master else "normal"
        ).pack(side="left", padx=(330, 10))

        tk.Button(
            botoes,
            text=t("close"),
            bg="#777",
            fg="white",
            font=("Arial", 10, "bold"),
            relief="flat",
            width=14,
            command=janela.destroy
        ).pack(side="left", padx=10)



class HorarioDfacWindow:
    REFEICOES = [
        ("pequeno_almoco", "Pequeno-Almoço"),
        ("almoco", "Almoço"),
        ("jantar", "Jantar"),
    ]
    TIPOS = [
        ("normal", "Dias normais"),
        ("especial", "Domingo/Day Off"),
    ]

    def __init__(self, admin):
        self.admin = admin
        self.app = admin.app
        self.entries = {}

        self.janela = tk.Toplevel(self.app.root)
        aplicar_icone(self.janela)
        self.app.registar_janela(self.janela, "horario_dfac")
        self.janela.title("Horário DFAC")
        self.janela.geometry("620x560")
        self.janela.minsize(620, 560)
        self.janela.resizable(False, False)
        self.janela.configure(bg="white")
        self.janela.grab_set()

        self.criar_layout()
        self.centrar()

    def centrar(self):
        self.janela.update_idletasks()
        x = self.admin.janela.winfo_x() + (self.admin.janela.winfo_width() // 2) - (self.janela.winfo_width() // 2)
        y = self.admin.janela.winfo_y() + (self.admin.janela.winfo_height() // 2) - (self.janela.winfo_height() // 2)
        self.janela.geometry(f"+{x}+{y}")

    def criar_layout(self):
        tk.Label(
            self.janela,
            text="Horário DFAC",
            bg="white",
            fg=COR_PRINCIPAL,
            font=("Arial", 16, "bold")
        ).pack(pady=(18, 4))

        tk.Label(
            self.janela,
            text="Indique as horas no formato HH:MM. Dias normais = Segunda-feira a Sábado. Domingo e Day Off usam o horário especial.",
            bg="white",
            fg="#444444",
            font=("Arial", 9),
            wraplength=540,
            justify="center"
        ).pack(pady=(0, 12))

        dados = get_horario_dfac()
        wrapper = tk.Frame(self.janela, bg="white", padx=18)
        wrapper.pack(fill="x", expand=False)

        for tipo_key, tipo_label in self.TIPOS:
            frame = tk.LabelFrame(
                wrapper,
                text=tipo_label,
                bg="white",
                fg=COR_PRINCIPAL,
                font=("Arial", 10, "bold"),
                padx=10,
                pady=8
            )
            frame.pack(fill="x", pady=(0, 10))

            tk.Label(frame, text="Refeição", bg="white", font=("Arial", 9, "bold"), width=18, anchor="w").grid(row=0, column=0, padx=4, pady=3)
            tk.Label(frame, text="Abertura", bg="white", font=("Arial", 9, "bold"), width=12).grid(row=0, column=1, padx=4, pady=3)
            tk.Label(frame, text="Fecho", bg="white", font=("Arial", 9, "bold"), width=12).grid(row=0, column=2, padx=4, pady=3)

            for row, (ref_key, ref_label) in enumerate(self.REFEICOES, start=1):
                tk.Label(frame, text=ref_label, bg="white", font=("Arial", 9), width=18, anchor="w").grid(row=row, column=0, padx=4, pady=3)

                ent_abre = tk.Entry(frame, width=12, justify="center")
                ent_abre.insert(0, dados[tipo_key][ref_key]["abertura"])
                ent_abre.grid(row=row, column=1, padx=4, pady=3, ipady=3)

                ent_fecha = tk.Entry(frame, width=12, justify="center")
                ent_fecha.insert(0, dados[tipo_key][ref_key]["fecho"])
                ent_fecha.grid(row=row, column=2, padx=4, pady=3, ipady=3)

                self.entries[(tipo_key, ref_key, "abertura")] = ent_abre
                self.entries[(tipo_key, ref_key, "fecho")] = ent_fecha

        botoes = tk.Frame(self.janela, bg="white")
        botoes.pack(fill="x", side="bottom", pady=(10, 18))

        tk.Button(
            botoes,
            text="Gravar",
            bg=COR_PRINCIPAL,
            fg="white",
            font=("Arial", 10, "bold"),
            relief="flat",
            width=12,
            command=self.guardar
        ).pack(side="left", padx=(190, 10))

        tk.Button(
            botoes,
            text=t("close"),
            bg="#777777",
            fg="white",
            font=("Arial", 10, "bold"),
            relief="flat",
            width=12,
            command=self.janela.destroy
        ).pack(side="left", padx=10)

    def _validar_hora(self, valor):
        valor = (valor or "").strip()
        partes = valor.split(":")
        if len(partes) != 2:
            return None
        try:
            h = int(partes[0])
            m = int(partes[1])
        except ValueError:
            return None
        if not (0 <= h <= 23 and 0 <= m <= 59):
            return None
        return f"{h:02d}:{m:02d}"

    def guardar(self):
        dados = {"normal": {}, "especial": {}}
        for tipo_key, _tipo_label in self.TIPOS:
            for ref_key, _ref_label in self.REFEICOES:
                abertura = self._validar_hora(self.entries[(tipo_key, ref_key, "abertura")].get())
                fecho = self._validar_hora(self.entries[(tipo_key, ref_key, "fecho")].get())
                if not abertura or not fecho:
                    avisar_parent(self.janela, "aviso", t("validation"), "As horas devem estar no formato HH:MM.")
                    return
                dados[tipo_key][ref_key] = {"abertura": abertura, "fecho": fecho}

        set_horario_dfac(dados)
        avisar_parent(self.janela, "info", t("saved"), "Horário DFAC guardado com sucesso.")
        self.janela.destroy()


class DayOffWindow:
    def __init__(self, admin_window):
        self.admin_window = admin_window
        self.app = admin_window.app
        self.mostrar_todos = False

        self.janela = tk.Toplevel(self.app.root)
        aplicar_icone(self.janela)
        self.app.registar_janela(self.janela, "days_off")

        self.janela.title(t("days_off"))
        self.janela.geometry("760x520")
        self.janela.minsize(700, 460)
        self.janela.configure(bg="white")

        self.criar_layout()
        self.carregar_tabela()

    def criar_layout(self):
        topo = tk.Frame(self.janela, bg=COR_PRINCIPAL, height=55)
        topo.pack(fill="x")
        topo.pack_propagate(False)

        tk.Label(
            topo,
            text=t("days_off"),
            bg=COR_PRINCIPAL,
            fg="white",
            font=("Arial", 17, "bold")
        ).pack(side="left", padx=20)

        frame = tk.Frame(self.janela, bg="white", padx=20, pady=18)
        frame.pack(fill="both", expand=True)

        barra = tk.Frame(frame, bg="white")
        barra.pack(fill="x", pady=(0, 10))

        tk.Button(
            barra,
            text=t("new_day_off"),
            bg=COR_PRINCIPAL,
            fg="white",
            font=("Arial", 10, "bold"),
            relief="flat",
            padx=14,
            pady=6,
            command=lambda: self.abrir_form_day_off(None)
        ).pack(side="left")

        self.btn_mostrar = tk.Button(
            barra,
            text=t("show_all"),
            bg="white",
            fg=COR_PRINCIPAL,
            activebackground="white",
            activeforeground=COR_PRINCIPAL,
            font=("Arial", 10, "bold"),
            relief="solid",
            bd=1,
            padx=14,
            pady=5,
            command=self.alternar_mostrar_todos
        )
        self.btn_mostrar.pack(side="left", padx=(10, 0))

        self.lbl_estado = tk.Label(
            barra,
            text=t("future_days_off"),
            bg="white",
            fg="#555555",
            font=("Arial", 9)
        )
        self.lbl_estado.pack(side="left", padx=(12, 0))

        colunas = ("data", "observacao")
        self.tabela = ttk.Treeview(frame, columns=colunas, show="headings", height=14)
        self.tabela.heading("data", text="Data")
        self.tabela.heading("observacao", text="Observação")
        self.tabela.column("data", width=130, anchor="w")
        self.tabela.column("observacao", width=500, anchor="w")
        self.tabela.pack(fill="both", expand=True)
        self.tabela.bind("<Configure>", lambda e: self.janela.after(80, self.atualizar_icones_tabela))
        self.tabela.bind("<Expose>", lambda e: self.janela.after(80, self.atualizar_icones_tabela))
        self.tabela.bind("<MouseWheel>", lambda e: self.janela.after(80, self.atualizar_icones_tabela))
        self.tabela.bind("<ButtonRelease-1>", lambda e: self.janela.after(80, self.atualizar_icones_tabela))

        botoes = tk.Frame(frame, bg="white", pady=10)
        botoes.pack(fill="x")

        tk.Button(
            botoes,
            text=t("edit"),
            bg=COR_PRINCIPAL,
            fg="white",
            font=("Arial", 10, "bold"),
            relief="flat",
            width=14,
            command=self.editar
        ).pack(side="left", padx=(0, 10))

        tk.Button(
            botoes,
            text=t("delete"),
            bg=COR_VERMELHO,
            fg="white",
            font=("Arial", 10, "bold"),
            relief="flat",
            width=14,
            command=self.eliminar
        ).pack(side="left")

    def alternar_mostrar_todos(self):
        self.mostrar_todos = not self.mostrar_todos
        self.carregar_tabela()

    def carregar_tabela(self):
        for item in self.tabela.get_children():
            self.tabela.delete(item)

        rows = get_day_offs(self.mostrar_todos)

        if self.mostrar_todos:
            self.btn_mostrar.config(text=t("show_future"))
            self.lbl_estado.config(text=t("all_days_off"))
        else:
            self.btn_mostrar.config(text=t("show_all"))
            self.lbl_estado.config(text=t("future_days_off"))

        for row in rows:
            self.tabela.insert(
                "",
                "end",
                values=(row["data"], row.get("observacao") or ""),
                tags=(str(row["id"]),)
            )

    def get_selected(self):
        selected = self.tabela.selection()
        if not selected:
            messagebox.showwarning("Seleção", t("select_day_off"), parent=self.janela)
            manter_janela_em_frente(self.janela)
            return None

        day_off_id = int(self.tabela.item(selected[0], "tags")[0])
        return get_day_off(day_off_id)

    def editar(self):
        row = self.get_selected()
        if row:
            self.abrir_form_day_off(row)

    def eliminar(self):
        row = self.get_selected()
        if not row:
            return

        confirmar = messagebox.askyesno(
            t("delete"),
            t("delete_day_off_question", data=row['data'])
        )

        if not confirmar:
            return

        eliminar_day_off(row["id"])
        self.carregar_tabela()
        self.app.carregar_calendario()

    def abrir_form_day_off(self, row):
        janela = tk.Toplevel(self.app.root)
        aplicar_icone(janela)
        self.app.registar_janela(janela)

        editar = row is not None
        janela.title(t("edit_day_off") if editar else t("new_day_off"))
        janela.geometry("520x260")
        janela.resizable(False, False)
        janela.configure(bg="white")
        janela.grab_set()

        tk.Label(
            janela,
            text=t("edit_day_off") if editar else t("new_day_off"),
            bg="white",
            fg=COR_PRINCIPAL,
            font=("Arial", 15, "bold")
        ).pack(pady=(18, 12))

        frame = tk.Frame(janela, bg="white", padx=30)
        frame.pack(fill="x")

        tk.Label(frame, text=t("date"), bg="white", font=("Arial", 10, "bold")).pack(anchor="w")
        entry_data = DateEntry(frame, row["data"] if row else "")
        entry_data.pack(anchor="w", pady=(3, 10))

        tk.Label(frame, text=t("observation"), bg="white", font=("Arial", 10, "bold")).pack(anchor="w")
        entry_obs = tk.Entry(frame, width=62)
        entry_obs.insert(0, row.get("observacao") or "" if row else "")
        entry_obs.pack(anchor="w", pady=(3, 12), ipady=4)

        def guardar():
            data_str = entry_data.get().strip()
            obs = entry_obs.get().strip()

            if not data_str:
                avisar_parent(janela, "aviso", t("validation"), t("date_required"))
                return

            try:
                date.fromisoformat(data_str)
            except ValueError:
                avisar_parent(janela, "aviso", t("validation"), t("date_format"))
                return

            try:
                guardar_day_off(data_str, obs, row["id"] if row else None)
            except sqlite3.IntegrityError:
                avisar_parent(janela, "erro", "Erro", t("day_off_exists"))
                return

            self.carregar_tabela()
            self.app.carregar_calendario()
            janela.destroy()

        botoes = tk.Frame(janela, bg="white", pady=12)
        botoes.pack(fill="x")

        tk.Button(
            botoes,
            text=t("save"),
            bg=COR_PRINCIPAL,
            fg="white",
            font=("Arial", 10, "bold"),
            relief="flat",
            width=14,
            command=guardar
        ).pack(side="left", padx=(125, 10))

        tk.Button(
            botoes,
            text=t("close"),
            bg="#777",
            fg="white",
            font=("Arial", 10, "bold"),
            relief="flat",
            width=14,
            command=janela.destroy
        ).pack(side="left", padx=10)
