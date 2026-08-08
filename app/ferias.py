import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime, date

from app.config import COR_PRINCIPAL, COR_VERMELHO, COR_LINHA, COR_WEEKEND
from app.datepicker import DateTimeEntry
from app.db import (
    db_rows, get_feria, guardar_feria, eliminar_feria
)
from app.person_order import person_order_key
from app.utils import aplicar_icone
from app.i18n import t


def _identificacao(user):
    posto = (user.get("posto") or "").strip()
    sobrenome = (user.get("sobrenome") or "").strip().upper()
    nome = (user.get("nome") or "").strip().upper()
    if sobrenome and nome:
        return f"{posto} {sobrenome}, {nome}".strip()
    return f"{posto} {sobrenome or nome}".strip()


def _periodo_texto(row):
    inicio = row.get("data_hora_inicio") or ""
    fim = row.get("data_hora_fim") or ""
    obs = (row.get("observacao") or "").strip()
    txt = f"▶ {inicio}    ■ {fim}"
    if obs:
        txt += f"   |   {obs}"
    return txt


def _dt_ok(valor):
    try:
        return datetime.strptime(valor, "%Y-%m-%d %H:%M")
    except Exception:
        return None


class FeriasWindow:
    def __init__(self, app):
        self.app = app
        self.mostrar_todas = False
        self.utilizadores = self._get_utilizadores_ativos()
        self.periodos_por_user = {}

        self.janela = tk.Toplevel(app.root)
        aplicar_icone(self.janela)
        self.app.registar_janela(self.janela, "gestao_ferias")

        self.janela.title(t("vacation_management"))
        self.janela.geometry("1300x760")
        self.janela.minsize(1050, 640)
        self.janela.configure(bg="white")
        self._centrar_janela(1300, 760)

        self.criar_layout()
        self.carregar_tabela()

    def _centrar_janela(self, largura, altura):
        self.janela.update_idletasks()
        sw = self.janela.winfo_screenwidth()
        sh = self.janela.winfo_screenheight()
        x = max((sw - largura) // 2, 0)
        y = max((sh - altura) // 2, 0)
        self.janela.geometry(f"{largura}x{altura}+{x}+{y}")

    def _get_utilizadores_ativos(self):
        """Só mostra pessoal que ainda não partiu: sem data_partida ou data_partida >= hoje."""
        hoje = date.today().isoformat()
        users = db_rows("""
            SELECT *
            FROM utilizadores
            WHERE master = 0
              AND (data_partida IS NULL OR TRIM(data_partida) = '' OR SUBSTR(data_partida, 1, 10) >= ?)
        """, (hoje,))
        return sorted(users, key=person_order_key)

    def _get_periodos_por_user(self):
        hoje_agora = datetime.now().strftime("%Y-%m-%d %H:%M")
        filtro = "" if self.mostrar_todas else "AND f.data_hora_fim >= ?"
        params = () if self.mostrar_todas else (hoje_agora,)
        rows = db_rows(f"""
            SELECT f.*, u.posto, u.nome, u.sobrenome, u.antiguidade
            FROM ferias f
            JOIN utilizadores u ON u.id = f.utilizador_id
            WHERE u.master = 0
              AND (u.data_partida IS NULL OR TRIM(u.data_partida) = '' OR SUBSTR(u.data_partida, 1, 10) >= DATE('now'))
              {filtro}
            ORDER BY f.utilizador_id, f.data_hora_inicio DESC
        """, params)

        dados = {}
        for row in rows:
            dados.setdefault(row["utilizador_id"], []).append(row)
        return dados

    def criar_layout(self):
        topo = tk.Frame(self.janela, bg=COR_PRINCIPAL, height=58)
        topo.pack(fill="x")
        topo.pack_propagate(False)

        tk.Label(
            topo,
            text=t("vacation_management"),
            bg=COR_PRINCIPAL,
            fg="white",
            font=("Arial", 17, "bold")
        ).pack(side="left", padx=20)

        corpo = tk.Frame(self.janela, bg="white", padx=18, pady=16)
        corpo.pack(fill="both", expand=True)

        info_horas = tk.Label(
            corpo,
            text="A hora de partida e a hora de chegada que coloca nas férias, é relativamente à saída da base pois essa hora influencia na marcação das refeições.",
            bg="#f7f4a8",
            fg="#111111",
            font=("Arial", 10, "bold"),
            anchor="w",
            justify="left",
            padx=12,
            pady=8,
            wraplength=1180
        )
        info_horas.pack(fill="x", pady=(0, 10))

        barra = tk.Frame(corpo, bg="white")
        barra.pack(fill="x", pady=(0, 10))

        self.btn_mostrar = tk.Button(
            barra,
            text=t("show_all_vacations"),
            bg="white",
            fg=COR_PRINCIPAL,
            font=("Arial", 10, "bold"),
            relief="solid",
            bd=1,
            padx=14,
            pady=5,
            command=self.alternar_mostrar
        )
        self.btn_mostrar.pack(side="left")

        self.lbl_estado = tk.Label(
            barra,
            text=t("future_vacations"),
            bg="white",
            fg="#555",
            font=("Arial", 10, "bold")
        )
        self.lbl_estado.pack(side="left", padx=18)

        style = ttk.Style(self.janela)
        style.configure("Ferias.Treeview", rowheight=34, font=("Arial", 10))
        style.configure("Ferias.Treeview.Heading", font=("Arial", 10, "bold"))

        colunas = ("pessoa", "adicionar", "periodos")
        self.tabela = ttk.Treeview(corpo, columns=colunas, show="headings", style="Ferias.Treeview")
        headers = {
            "pessoa": t("identification"),
            "adicionar": "+ Adicionar",
            "periodos": "▶ Início        ■ Fim        Observações",
        }
        widths = {"pessoa": 320, "adicionar": 135, "periodos": 820}
        for col in colunas:
            self.tabela.heading(col, text=headers[col], anchor="center")
            self.tabela.column(col, width=widths[col], anchor=("w" if col == "pessoa" else "center"))
        self.tabela.pack(fill="both", expand=True)

        self.tabela.tag_configure("odd", background="#ffffff")
        self.tabela.tag_configure("even", background="#f8fbfb")
        self.tabela.tag_configure("hover", background="#fff2cc")

        self._hover_item = None
        self.tabela.bind("<Motion>", self._hover_tabela)
        self.tabela.bind("<Leave>", self._limpar_hover_tabela)
        self.tabela.bind("<ButtonRelease-1>", self._clique_tabela)
        self.tabela.bind("<Double-1>", self._clique_tabela)

        ajuda = tk.Label(
            corpo,
            text="Clique em + Adicionar para criar período. Clique nos períodos para editar/apagar.",
            bg="white",
            fg="#555",
            font=("Arial", 9)
        )
        ajuda.pack(anchor="w", pady=(8, 0))

    def _hover_tabela(self, event):
        item = self.tabela.identify_row(event.y)
        col = self.tabela.identify_column(event.x)
        self.tabela.configure(cursor="hand2" if col in ("#2", "#3") and item else "")
        if item == self._hover_item:
            return
        self._limpar_hover_tabela()
        if item:
            tags = list(self.tabela.item(item, "tags"))
            if "hover" not in tags:
                tags.append("hover")
            self.tabela.item(item, tags=tags)
            self._hover_item = item

    def _limpar_hover_tabela(self, event=None):
        if self._hover_item:
            tags = [t for t in self.tabela.item(self._hover_item, "tags") if t != "hover"]
            self.tabela.item(self._hover_item, tags=tags)
            self._hover_item = None
        self.tabela.configure(cursor="")

    def alternar_mostrar(self):
        self.mostrar_todas = not self.mostrar_todas
        self.carregar_tabela()

    def carregar_tabela(self):
        for item in self.tabela.get_children():
            self.tabela.delete(item)

        self.utilizadores = self._get_utilizadores_ativos()
        self.periodos_por_user = self._get_periodos_por_user()

        if self.mostrar_todas:
            self.btn_mostrar.config(text=t("show_future_vacations"))
            self.lbl_estado.config(text=t("all_vacations"))
        else:
            self.btn_mostrar.config(text=t("show_all_vacations"))
            self.lbl_estado.config(text=t("future_vacations"))

        for user in self.utilizadores:
            periodos = self.periodos_por_user.get(user["id"], [])
            periodos_txt = "\n".join(_periodo_texto(p) for p in periodos)
            idx = len(self.tabela.get_children())
            zebra = "even" if idx % 2 == 0 else "odd"
            self.tabela.insert(
                "",
                "end",
                values=(
                    _identificacao(user),
                    "+ Adicionar",
                    periodos_txt,
                ),
                tags=(str(user["id"]), zebra)
            )

    def _user_from_item(self, item_id):
        try:
            user_id = int(self.tabela.item(item_id, "tags")[0])
        except Exception:
            return None
        for user in self.utilizadores:
            if int(user["id"]) == user_id:
                return user
        return None

    def _clique_tabela(self, event):
        item = self.tabela.identify_row(event.y)
        col = self.tabela.identify_column(event.x)
        if not item:
            return

        user = self._user_from_item(item)
        if not user:
            return

        if col == "#2":
            self.abrir_form(None, user)
        elif col == "#3":
            periodos = self.periodos_por_user.get(user["id"], [])
            if not periodos:
                return
            if len(periodos) == 1:
                self.abrir_form(periodos[0], user)
            else:
                self.abrir_seletor_periodos(user, periodos)

    def abrir_seletor_periodos(self, user, periodos):
        janela = tk.Toplevel(self.janela)
        aplicar_icone(janela)
        self.app.registar_janela(janela)
        janela.title("Períodos")
        janela.geometry("850x360")
        janela.configure(bg="white")
        janela.transient(self.janela)
        janela.grab_set()

        tk.Label(
            janela,
            text=_identificacao(user),
            bg="white",
            fg=COR_PRINCIPAL,
            font=("Arial", 14, "bold")
        ).pack(pady=(15, 8))

        cols = ("inicio", "fim", "observacao")
        tabela = ttk.Treeview(janela, columns=cols, show="headings", height=8)
        for col, title, width in [
            ("inicio", t("start_datetime").replace(":", ""), 170),
            ("fim", t("end_datetime").replace(":", ""), 170),
            ("observacao", t("observation").replace(":", ""), 430),
        ]:
            tabela.heading(col, text=title, anchor="center")
            tabela.column(col, width=width, anchor="center")
        tabela.pack(fill="both", expand=True, padx=18, pady=8)

        for p in periodos:
            tabela.insert("", "end", values=(p.get("data_hora_inicio") or "", p.get("data_hora_fim") or "", p.get("observacao") or ""), tags=(str(p["id"]),))

        def editar_periodo(event=None):
            selected = tabela.selection()
            if not selected:
                return
            pid = int(tabela.item(selected[0], "tags")[0])
            row = get_feria(pid)
            janela.destroy()
            self.abrir_form(row, user)

        tabela.bind("<Double-1>", editar_periodo)

        botoes = tk.Frame(janela, bg="white", pady=10)
        botoes.pack(fill="x")
        tk.Button(
            botoes,
            text=t("edit"),
            bg=COR_PRINCIPAL,
            fg="white",
            font=("Arial", 10, "bold"),
            relief="flat",
            width=14,
            command=editar_periodo
        ).pack(side="left", padx=(270, 10))
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

    def abrir_form(self, row=None, user_preselecionado=None):
        janela = tk.Toplevel(self.janela)
        aplicar_icone(janela)
        self.app.registar_janela(janela)
        editar = row is not None

        janela.title(t("edit_vacation") if editar else t("new_vacation"))
        janela.geometry("720x430")
        janela.resizable(False, False)
        janela.configure(bg="white")
        janela.transient(self.janela)
        janela.grab_set()

        tk.Label(
            janela,
            text=t("edit_vacation") if editar else t("new_vacation"),
            bg="white",
            fg=COR_PRINCIPAL,
            font=("Arial", 15, "bold")
        ).pack(pady=(18, 12))

        frame = tk.Frame(janela, bg="white", padx=32)
        frame.pack(fill="both", expand=True)

        tk.Label(frame, text=t("person"), bg="white", font=("Arial", 10, "bold")).grid(row=0, column=0, sticky="w", pady=(0, 4))
        valores = [_identificacao(u) for u in self.utilizadores]
        ids_por_valor = {_identificacao(u): u["id"] for u in self.utilizadores}
        combo = ttk.Combobox(frame, values=valores, state="readonly", width=55)
        combo.grid(row=1, column=0, columnspan=2, sticky="w", pady=(0, 10))

        if row:
            pessoa_atual = f"{row.get('posto') or ''} {(row.get('sobrenome') or '').upper()}, {(row.get('nome') or '').upper()}".strip()
            combo.set(pessoa_atual)
        elif user_preselecionado:
            combo.set(_identificacao(user_preselecionado))
        elif valores:
            combo.current(0)

        tk.Label(frame, text=t("start_datetime"), bg="white", font=("Arial", 10, "bold")).grid(row=2, column=0, sticky="w", pady=(0, 4))
        entry_inicio = DateTimeEntry(frame, (row.get("data_hora_inicio") if row else "") or "")
        entry_inicio.grid(row=3, column=0, sticky="w", pady=(0, 10))

        tk.Label(frame, text=t("end_datetime"), bg="white", font=("Arial", 10, "bold")).grid(row=2, column=1, sticky="w", pady=(0, 4), padx=(20, 0))
        entry_fim = DateTimeEntry(frame, (row.get("data_hora_fim") if row else "") or "")
        entry_fim.grid(row=3, column=1, sticky="w", pady=(0, 10), padx=(20, 0))

        tk.Label(frame, text=t("observation"), bg="white", font=("Arial", 10, "bold")).grid(row=4, column=0, sticky="w", pady=(0, 4))
        txt_obs = tk.Text(frame, width=72, height=6)
        txt_obs.grid(row=5, column=0, columnspan=2, sticky="w")
        if row and row.get("observacao"):
            txt_obs.insert("1.0", row.get("observacao") or "")

        botoes = tk.Frame(janela, bg="white", pady=14)
        botoes.pack(fill="x")

        def guardar():
            pessoa_txt = combo.get().strip()
            inicio = entry_inicio.get().strip()
            fim = entry_fim.get().strip()
            obs = txt_obs.get("1.0", tk.END).strip()

            if not pessoa_txt or not inicio or not fim:
                messagebox.showwarning(t("validation"), t("vacation_required"), parent=janela)
                janela.lift()
                janela.focus_force()
                return

            dt_inicio = _dt_ok(inicio)
            dt_fim = _dt_ok(fim)
            if not dt_inicio or not dt_fim:
                messagebox.showwarning(t("validation"), t("date_format"), parent=janela)
                janela.lift()
                janela.focus_force()
                return
            if dt_fim < dt_inicio:
                messagebox.showwarning(t("validation"), t("vacation_dates_invalid"), parent=janela)
                janela.lift()
                janela.focus_force()
                return

            guardar_feria(ids_por_valor[pessoa_txt], inicio, fim, obs, row["id"] if row else None)
            self.carregar_tabela()
            try:
                self.app.refresh_welfare_individual_if_open()
            except Exception:
                pass
            messagebox.showinfo(t("saved"), t("vacation_saved"), parent=janela)
            janela.destroy()
            self.janela.lift()
            self.janela.focus_force()

        def apagar():
            if not row:
                return
            confirmar = messagebox.askyesno(t("delete"), t("delete_vacation_question"), parent=janela)
            if not confirmar:
                janela.lift()
                janela.focus_force()
                return
            eliminar_feria(row["id"])
            self.carregar_tabela()
            try:
                self.app.refresh_welfare_individual_if_open()
            except Exception:
                pass
            janela.destroy()
            self.janela.lift()
            self.janela.focus_force()

        tk.Button(
            botoes,
            text=t("save"),
            bg=COR_PRINCIPAL,
            fg="white",
            font=("Arial", 10, "bold"),
            relief="flat",
            width=14,
            command=guardar
        ).pack(side="left", padx=(170, 10))

        if editar:
            tk.Button(
                botoes,
                text=t("delete"),
                bg=COR_VERMELHO,
                fg="white",
                font=("Arial", 10, "bold"),
                relief="flat",
                width=14,
                command=apagar
            ).pack(side="left", padx=10)

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
