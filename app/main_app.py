import os
import calendar
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from datetime import date
from pathlib import Path

from PIL import Image, ImageTk

from app.admin import AdminWindow
from app.ferias import FeriasWindow
from app.individual import WelfareIndividualWindow
from app.calendar_cell import DiaCalendario
from app.config import (
    APP_NAME,
    COR_BRANCO,
    COR_CINZA,
    COR_PRINCIPAL,
    COR_VERMELHO,
    COR_WEEKEND,
    ACESSOS_EDITAM_EMENTAS_MENSAIS,
    ACESSOS_EDITAM_WELFARES_MENSAIS,
    ACESSOS_APAGAM_WELFARES_MENSAIS,
    ACESSOS_VEEM_BOTAO_EDITAR_WELFARES_MENSAIS,
    ACESSOS_VEEM_WELFARES_INDIVIDUAIS,
    ACESSOS_GEREM_FERIAS,
    DOCS_DIR,
    MESES_PT,
    REFEICOES,
    TIPOS_WELFARE,
)
from app.db import eliminar_welfare, get_welfare, get_welfares_mes, guardar_welfare, get_day_offs_mes, is_mes_trancado, set_mes_trancado, atualizar_password_utilizador
from app.print_utils import gerar_pdf_mes
from app.utils import aplicar_icone
from app.i18n import t, months, weekdays_short


class PRTWelfareApp:
    def __init__(self, root, current_user):
        self.root = root
        self.current_user = current_user

        self.root.title(APP_NAME)
        aplicar_icone(self.root)
        self.root.geometry("1500x900")
        self.root.minsize(1250, 760)
        self.root.configure(bg="white")
        self.root.protocol("WM_DELETE_WINDOW", self.fechar_aplicacao)

        hoje = date.today()
        self.ano_atual = hoje.year
        self.mes_atual = hoje.month

        self.imagens_cache = {}
        self.janelas_abertas = []
        self.janelas_por_tipo = {}
        self.janelas_edicao_welfare = {}
        self.lbl_total_welfare = None
        self.lbl_total_welfare_icone = None
        self.btn_trancar_mes = None
        self.total_welfare_atual = 0

        self.carregar_imagens()
        self.criar_layout()
        self.carregar_calendario()

    def fechar_aplicacao(self):
        for janela in list(self.janelas_abertas):
            try:
                janela.destroy()
            except tk.TclError:
                pass

        self.root.destroy()

    def registar_janela(self, janela, tipo=None):
        self.janelas_abertas.append(janela)
        if tipo:
            self.janelas_por_tipo[tipo] = janela

        def ao_fechar():
            if janela in self.janelas_abertas:
                self.janelas_abertas.remove(janela)
            if tipo and self.janelas_por_tipo.get(tipo) == janela:
                self.janelas_por_tipo.pop(tipo, None)
            janela.destroy()

        janela.protocol("WM_DELETE_WINDOW", ao_fechar)
        return ao_fechar

    def trazer_janela_tipo(self, tipo):
        janela = self.janelas_por_tipo.get(tipo)
        if janela and janela.winfo_exists():
            try:
                janela.deiconify()
                janela.lift()
                janela.focus_force()
            except tk.TclError:
                pass
            return True
        self.janelas_por_tipo.pop(tipo, None)
        return False

    def acessos(self):
        acessos = self.current_user.get("acessos") or []
        if not acessos and self.current_user.get("tipo_acesso"):
            acessos = [a.strip() for a in str(self.current_user.get("tipo_acesso", "")).split(",") if a.strip()]
        return set(acessos)

    def tem_acesso(self, acesso):
        return "Administrador" in self.acessos() or acesso in self.acessos()

    def is_admin(self):
        return "Administrador" in self.acessos()

    def is_snr(self):
        try:
            return int(self.current_user.get("snr") or 0) == 1
        except (TypeError, ValueError):
            return False

    def is_responsavel_welfare(self):
        try:
            return int(self.current_user.get("responsavel_welfare") or 0) == 1
        except (TypeError, ValueError):
            return False

    def pode_trancar_mes(self):
        return self.is_admin() or self.is_snr()

    def pode_adicionar_editar_welfare_mensal(self):
        return (
            bool(self.acessos() & ACESSOS_EDITAM_WELFARES_MENSAIS)
            or self.is_admin()
            or self.is_responsavel_welfare()
        )

    def pode_eliminar_welfare_mensal(self):
        return (
            bool(self.acessos() & ACESSOS_APAGAM_WELFARES_MENSAIS)
            or self.is_admin()
            or self.is_responsavel_welfare()
        )

    def pode_ver_botao_editar_welfare_mensal(self):
        return (
            bool(self.acessos() & ACESSOS_VEEM_BOTAO_EDITAR_WELFARES_MENSAIS)
            or self.is_admin()
            or self.is_responsavel_welfare()
        )

    def pode_editar_ementa_mensal(self):
        return (
            bool(self.acessos() & ACESSOS_EDITAM_EMENTAS_MENSAIS)
            or self.is_admin()
            or self.is_responsavel_welfare()
        )

    def pode_ver_welfare_individual(self):
        return bool(self.acessos() & ACESSOS_VEEM_WELFARES_INDIVIDUAIS) or self.is_admin()

    def pode_gerir_ferias(self):
        return bool(self.acessos() & ACESSOS_GEREM_FERIAS) or self.is_admin()

    def pode_ver_pessoal(self):
        return self.pode_gerir_ferias()


    def carregar_imagens(self):
        ficheiros = set()
        for lista in TIPOS_WELFARE.values():
            ficheiros.update(lista)

        ficheiros.add("editar.png")
        ficheiros.add("impressora.png")
        ficheiros.add("cog.png")
        ficheiros.add("favicon.ico")

        for ficheiro in ficheiros:
            caminho = os.path.join(DOCS_DIR, ficheiro)

            if not os.path.exists(caminho):
                self.imagens_cache[ficheiro] = None
                continue

            img = Image.open(caminho).convert("RGBA")

            if ficheiro == "editar.png":
                img.thumbnail((25, 25), Image.LANCZOS)
            elif ficheiro == "impressora.png":
                img.thumbnail((18, 18), Image.LANCZOS)
            elif ficheiro == "cog.png":
                img.thumbnail((28, 28), Image.LANCZOS)
            elif ficheiro == "favicon.ico":
                img.thumbnail((14, 14), Image.LANCZOS)
            else:
                img.thumbnail((24, 24), Image.LANCZOS)

            self.imagens_cache[ficheiro] = ImageTk.PhotoImage(img)

    def criar_layout(self):
        self.container = tk.Frame(self.root, bg="white")
        self.container.pack(fill="both", expand=True)

        self.sidebar = tk.Frame(self.container, bg=COR_PRINCIPAL, width=140)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)

        self.lbl_ano_lateral = tk.Label(
            self.sidebar,
            text=str(self.ano_atual),
            bg=COR_VERMELHO,
            fg="white",
            font=("Arial", 22, "bold"),
            height=3
        )
        self.lbl_ano_lateral.pack(fill="x", padx=0, pady=(0, 25))

        self.lbl_mes_lateral = tk.Label(
            self.sidebar,
            text="\n".join(months()[self.mes_atual].upper()),
            bg=COR_PRINCIPAL,
            fg="white",
            font=("Arial", 28),
            justify="center"
        )
        self.lbl_mes_lateral.pack(expand=True)

        self.area = tk.Frame(self.container, bg="white")
        self.area.pack(side="left", fill="both", expand=True)

        filtros = tk.Frame(self.area, bg="white", height=75)
        filtros.pack(fill="x")
        filtros.pack_propagate(False)

        tk.Label(filtros, text=t("month"), bg="white", font=("Arial", 13, "bold")).pack(side="left", padx=(28, 8))

        self.combo_mes = ttk.Combobox(
            filtros,
            state="readonly",
            width=18,
            values=[months()[i] for i in range(1, 13)]
        )
        self.combo_mes.current(self.mes_atual - 1)
        self.combo_mes.pack(side="left", ipady=5)

        tk.Label(filtros, text=t("year"), bg="white", font=("Arial", 13, "bold")).pack(side="left", padx=(25, 8))

        anos = list(range(self.ano_atual - 5, self.ano_atual + 11))

        self.combo_ano = ttk.Combobox(
            filtros,
            state="readonly",
            width=8,
            values=anos
        )
        self.combo_ano.set(self.ano_atual)
        self.combo_ano.pack(side="left", ipady=5)

        tk.Button(
            filtros,
            text=t("update"),
            bg=COR_PRINCIPAL,
            fg="white",
            activebackground="#1ab394",
            activeforeground="white",
            font=("Arial", 11, "bold"),
            relief="flat",
            width=14,
            padx=8,
            pady=5,
            command=self.atualizar_mes_ano
        ).pack(side="left", padx=(25, 8))

        img_impressora = self.imagens_cache.get("impressora.png")
        btn_imprimir = tk.Button(
            filtros,
            text=t("print") if img_impressora else "🖨  " + t("print").strip(),
            image=img_impressora,
            compound="left",
            bg="white",
            fg=COR_PRINCIPAL,
            activebackground="white",
            activeforeground=COR_PRINCIPAL,
            font=("Arial", 11, "bold"),
            relief="solid",
            bd=1,
            highlightthickness=1,
            highlightbackground=COR_PRINCIPAL,
            highlightcolor=COR_PRINCIPAL,
            width=14,
            padx=8,
            pady=5,
            command=self.imprimir_mes_atual
        )
        btn_imprimir.image = img_impressora
        btn_imprimir.pack(side="left", padx=(0, 8))

        if self.pode_ver_welfare_individual():
            tk.Button(
                filtros,
                text=t("welfare_individual"),
                bg="white",
                fg=COR_PRINCIPAL,
                activebackground="white",
                activeforeground=COR_PRINCIPAL,
                font=("Arial", 11, "bold"),
                relief="solid",
                bd=1,
                highlightthickness=1,
                highlightbackground=COR_PRINCIPAL,
                highlightcolor=COR_PRINCIPAL,
                padx=14,
                pady=5,
                command=self.abrir_welfare_individual
            ).pack(side="left", padx=(0, 25))
        else:
            tk.Frame(filtros, bg="white", width=17).pack(side="left")

        self.criar_perfil_utilizador_topo(filtros)

        if self.is_admin():
            tk.Button(
                filtros,
                text=t("administration"),
                bg=COR_VERMELHO,
                fg="white",
                activebackground="#8f0b0d",
                activeforeground="white",
                font=("Arial", 11, "bold"),
                relief="flat",
                padx=18,
                pady=5,
                command=self.abrir_administracao
            ).pack(side="right", padx=(0, 8))

        if self.pode_gerir_ferias():
            tk.Button(
                filtros,
                text=t("vacation_management"),
                bg="#d8f1f4",
                fg=COR_PRINCIPAL,
                activebackground="#cce9ed",
                activeforeground=COR_PRINCIPAL,
                font=("Arial", 11, "bold"),
                relief="solid",
                bd=1,
                padx=18,
                pady=5,
                command=self.abrir_gestao_ferias
            ).pack(side="right", padx=(0, 8))

        if self.pode_ver_pessoal():
            tk.Button(
                filtros,
                text=t("personnel"),
                bg="#d8f1f4",
                fg=COR_PRINCIPAL,
                activebackground="#cce9ed",
                activeforeground=COR_PRINCIPAL,
                font=("Arial", 11, "bold"),
                relief="solid",
                bd=1,
                padx=18,
                pady=5,
                command=self.abrir_pessoal
            ).pack(side="right", padx=(0, 8))

        self.frame_calendario = tk.Frame(self.area, bg="white", padx=0, pady=0)
        self.frame_calendario.pack(fill="both", expand=True)


    def identificacao_utilizador_logado(self):
        posto = (self.current_user.get("posto") or "").strip()
        sobrenome = (self.current_user.get("sobrenome") or "").strip().upper()
        nome = (self.current_user.get("nome") or "").strip().upper()

        if posto and sobrenome:
            return f"{posto} {sobrenome}"

        if posto and nome:
            return f"{posto} {nome}"

        if sobrenome:
            return sobrenome

        if nome:
            return nome

        return (self.current_user.get("nim") or "Utilizador").strip()

    def criar_perfil_utilizador_topo(self, parent):
        frame = tk.Frame(parent, bg="white", cursor="hand2")
        frame.pack(side="right", padx=(8, 18))

        img_cog = self.imagens_cache.get("cog.png")

        if img_cog:
            lbl_icon = tk.Label(frame, image=img_cog, bg="white", cursor="hand2")
            lbl_icon.image = img_cog
            lbl_icon.pack(side="left", padx=(0, 6))
        else:
            lbl_icon = tk.Label(
                frame,
                text="⚙",
                bg="white",
                fg=COR_PRINCIPAL,
                font=("Arial", 18, "bold"),
                cursor="hand2"
            )
            lbl_icon.pack(side="left", padx=(0, 6))

        lbl_nome = tk.Label(
            frame,
            text=self.identificacao_utilizador_logado(),
            bg="white",
            fg=COR_PRINCIPAL,
            font=("Arial", 11, "bold"),
            cursor="hand2"
        )
        lbl_nome.pack(side="left")

        for widget in (frame, lbl_icon, lbl_nome):
            widget.bind("<Button-1>", lambda e: self.abrir_popup_alterar_password())


    def _centrar_janela_no_monitor(self, janela, largura, altura):
        janela.update_idletasks()
        x = int((janela.winfo_screenwidth() - largura) / 2)
        y = int((janela.winfo_screenheight() - altura) / 2)
        janela.geometry(f"{largura}x{altura}+{x}+{y}")

    def abrir_popup_alterar_password(self):
        if self.trazer_janela_tipo("alterar_password"):
            return

        janela = tk.Toplevel(self.root)
        self.registar_janela(janela, tipo="alterar_password")
        aplicar_icone(janela)

        janela.title("Perfil / Alterar Password")
        janela.geometry("460x360")
        self._centrar_janela_no_monitor(janela, 460, 360)
        janela.resizable(False, False)
        janela.configure(bg="white")
        janela.transient(self.root)
        janela.grab_set()

        tk.Label(
            janela,
            text=self.identificacao_utilizador_logado(),
            bg="white",
            fg=COR_PRINCIPAL,
            font=("Arial", 16, "bold")
        ).pack(pady=(18, 4))

        acessos_txt = ", ".join(self.acessos()) if self.acessos() else "-"
        frame_perfil = tk.Frame(janela, bg="#f5fbfc", highlightthickness=1, highlightbackground="#cfe5e8")
        frame_perfil.pack(fill="x", padx=28, pady=(8, 16))

        tk.Label(
            frame_perfil,
            text="Perfil atribuído:",
            bg="#f5fbfc",
            fg=COR_PRINCIPAL,
            font=("Arial", 10, "bold")
        ).pack(anchor="w", padx=12, pady=(10, 2))

        tk.Label(
            frame_perfil,
            text=acessos_txt,
            bg="#f5fbfc",
            fg="#222222",
            font=("Arial", 9),
            wraplength=390,
            justify="left"
        ).pack(anchor="w", padx=12, pady=(0, 10))

        form = tk.Frame(janela, bg="white")
        form.pack(fill="x", padx=28)

        tk.Label(form, text="Nova password:", bg="white", font=("Arial", 10, "bold")).pack(anchor="w")
        entry_password = tk.Entry(form, show="*", width=48)
        entry_password.pack(anchor="w", pady=(3, 10), ipady=3)

        tk.Label(form, text="Confirmar password:", bg="white", font=("Arial", 10, "bold")).pack(anchor="w")
        entry_confirmar = tk.Entry(form, show="*", width=48)
        entry_confirmar.pack(anchor="w", pady=(3, 12), ipady=3)

        botoes = tk.Frame(janela, bg="white")
        botoes.pack(fill="x", pady=(6, 0))

        def manter_frente():
            try:
                janela.lift()
                janela.focus_force()
                janela.grab_set()
            except tk.TclError:
                pass

        def guardar():
            password = entry_password.get()
            confirmar = entry_confirmar.get()

            if not password:
                messagebox.showwarning("Validação", "Indica a nova password.", parent=janela)
                manter_frente()
                return

            if password != confirmar:
                messagebox.showerror("Erro", "As passwords não são iguais!", parent=janela)
                manter_frente()
                return

            atualizar_password_utilizador(self.current_user["id"], password)
            messagebox.showinfo("Guardado", "Password alterada com sucesso.", parent=janela)
            janela.destroy()

        tk.Button(
            botoes,
            text="Guardar",
            bg=COR_PRINCIPAL,
            fg="white",
            font=("Arial", 10, "bold"),
            relief="flat",
            width=14,
            command=guardar
        ).pack(side="left", padx=(90, 10))

        tk.Button(
            botoes,
            text="Fechar",
            bg="#777777",
            fg="white",
            font=("Arial", 10, "bold"),
            relief="flat",
            width=14,
            command=janela.destroy
        ).pack(side="left", padx=10)

        entry_password.focus_set()

    def atualizar_mes_ano(self):
        mes_nome = self.combo_mes.get()
        self.mes_atual = list(months().values()).index(mes_nome) + 1
        self.ano_atual = int(self.combo_ano.get())

        self.lbl_ano_lateral.config(text=str(self.ano_atual))
        self.lbl_mes_lateral.config(text="\n".join(months()[self.mes_atual].upper()))

        self.carregar_calendario()

    def carregar_calendario(self):
        for widget in self.frame_calendario.winfo_children():
            widget.destroy()
        self.lbl_total_welfare = None
        self.lbl_total_welfare_icone = None

        dados_mes = get_welfares_mes(self.ano_atual, self.mes_atual)
        day_offs_mes = get_day_offs_mes(self.ano_atual, self.mes_atual)
        self.atualizar_total_welfare_mes(dados_mes)

        dias_semana = weekdays_short()

        for col, dia in enumerate(dias_semana):
            tk.Label(
                self.frame_calendario,
                text=dia,
                bg=COR_PRINCIPAL,
                fg="white",
                font=("Arial", 13, "bold"),
                height=2,
                bd=1,
                relief="solid"
            ).grid(row=0, column=col, sticky="nsew")

        cal = calendar.Calendar(firstweekday=0)
        semanas = cal.monthdayscalendar(self.ano_atual, self.mes_atual)

        while len(semanas) < 6:
            semanas.append([0, 0, 0, 0, 0, 0, 0])

        for row_idx, semana in enumerate(semanas, start=1):
            for col_idx, dia in enumerate(semana):
                fim_semana = col_idx in [5, 6]
                data_str_loop = f"{self.ano_atual}-{self.mes_atual:02d}-{dia:02d}" if dia else ""
                is_day_off = bool(data_str_loop and data_str_loop in day_offs_mes)
                bg = COR_WEEKEND if (fim_semana or is_day_off) else COR_BRANCO

                if dia == 0:
                    frame_vazio = tk.Frame(
                        self.frame_calendario,
                        bg=bg,
                        bd=0,
                        highlightthickness=1,
                        highlightbackground="#b7b7b7"
                    )
                    frame_vazio.grid(row=row_idx, column=col_idx, sticky="nsew")
                    continue

                data_str = f"{self.ano_atual}-{self.mes_atual:02d}-{dia:02d}"
                welfares_dia = dados_mes.get(data_str, [])

                celula = DiaCalendario(
                    parent=self.frame_calendario,
                    app=self,
                    dia=dia,
                    data_str=data_str,
                    welfares_dia=welfares_dia,
                    bg=bg,
                    is_day_off=is_day_off
                )
                celula.grid(row=row_idx, column=col_idx, sticky="nsew")

        self.criar_linha_notas()

        for i in range(7):
            self.frame_calendario.grid_columnconfigure(i, weight=1, uniform="dias")

        for i in range(1, 7):
            self.frame_calendario.grid_rowconfigure(i, weight=1, uniform="semanas")

        self.frame_calendario.grid_rowconfigure(7, weight=0, minsize=70)

    def atualizar_total_welfare_mes(self, dados_mes):
        total = sum(len(welfares) for welfares in dados_mes.values())
        self.total_welfare_atual = total

        if self.lbl_total_welfare:
            self.lbl_total_welfare.config(text=f"Total Welfare: {total}")

        if self.lbl_total_welfare_icone:
            img = self.imagens_cache.get("cooking.png")
            if img:
                self.lbl_total_welfare_icone.config(image=img, text="")
                self.lbl_total_welfare_icone.image = img
            else:
                self.lbl_total_welfare_icone.config(text="🍽", fg=COR_PRINCIPAL, font=("Arial", 14))

    def criar_linha_notas(self):
        notas = tk.Frame(
            self.frame_calendario,
            bg="white",
            bd=0,
            highlightthickness=1,
            highlightbackground="#b7b7b7"
        )
        notas.grid(row=7, column=0, columnspan=7, sticky="nsew")

        frame_versao = tk.Frame(notas, bg="white")
        frame_versao.pack(side="left", padx=(8, 20), pady=15)

        img_app = self.imagens_cache.get("favicon.ico")
        if img_app:
            lbl_icone_app = tk.Label(frame_versao, image=img_app, bg="white")
            lbl_icone_app.image = img_app
            lbl_icone_app.pack(side="left", padx=(0, 4))

        tk.Label(
            frame_versao,
            text="SIGCP v1.0 @ 2026",
            bg="white",
            fg="#333333",
            font=("Arial", 8)
        ).pack(side="left")

        tk.Label(
            notas,
            text=t("notes"),
            bg="white",
            fg="black",
            font=("Arial", 10, "bold")
        ).pack(side="left", padx=(80, 80))

        self.criar_legenda(notas, "Welfare", "cooking.png")
        self.criar_legenda(notas, "Aniversário", "cake.png")
        self.criar_legenda(notas, "Welfare Livre", "star.png")

        if self.pode_trancar_mes():
            self.btn_trancar_mes = tk.Button(
                notas,
                text=t("unlock_month") if is_mes_trancado(self.ano_atual, self.mes_atual) else t("lock_month"),
                bg=COR_VERMELHO if not is_mes_trancado(self.ano_atual, self.mes_atual) else COR_PRINCIPAL,
                fg="white",
                activebackground="#8f0b0d",
                activeforeground="white",
                font=("Arial", 10, "bold"),
                relief="flat",
                padx=14,
                pady=5,
                command=self.alternar_trancar_mes
            )
            self.btn_trancar_mes.pack(side="right", padx=(0, 18), pady=15)

        self.frame_total_welfare = tk.Frame(notas, bg="white")
        self.frame_total_welfare.pack(side="right", padx=(0, 18), pady=15)

        self.lbl_total_welfare_icone = tk.Label(self.frame_total_welfare, bg="white")
        self.lbl_total_welfare_icone.pack(side="left", padx=(0, 6))

        self.lbl_total_welfare = tk.Label(
            self.frame_total_welfare,
            text=f"Total Welfare: {getattr(self, 'total_welfare_atual', 0)}",
            bg="white",
            fg=COR_PRINCIPAL,
            font=("Arial", 11, "bold")
        )
        self.lbl_total_welfare.pack(side="left")
        self.atualizar_total_welfare_mes(get_welfares_mes(self.ano_atual, self.mes_atual))


    def alternar_trancar_mes(self):
        atual = is_mes_trancado(self.ano_atual, self.mes_atual)
        pergunta = t("unlock_month_question") if atual else t("lock_month_question")
        if not messagebox.askyesno(t("unlock_month") if atual else t("lock_month"), pergunta, parent=self.root):
            return

        set_mes_trancado(self.ano_atual, self.mes_atual, not atual)
        self.carregar_calendario()

        janela_individual = self.janelas_por_tipo.get("welfare_individual")
        if janela_individual and janela_individual.winfo_exists():
            try:
                if hasattr(janela_individual, "_welfare_individual_ref"):
                    janela_individual._welfare_individual_ref.carregar_dados()
                    janela_individual._welfare_individual_ref.desenhar_grelha()
            except tk.TclError:
                pass

    def criar_legenda(self, parent, texto, ficheiro):
        frame = tk.Frame(parent, bg="white")
        frame.pack(side="left", padx=40)

        tk.Label(frame, text=texto, bg="white", fg="black", font=("Arial", 10)).pack(side="left", padx=6)

        img = self.imagens_cache.get(ficheiro)

        if img:
            tk.Label(frame, image=img, bg="white").pack(side="left")
        else:
            tk.Label(frame, text="★", bg="white", fg=COR_VERMELHO, font=("Arial", 24, "bold")).pack(side="left")

    def abrir_janela_dia(self, data_str, refeicao_inicial="Almoço", modo="editar"):
        """
        Regras de acesso aos Welfares mensais:
        - Administrador / Gestão Welfare Mensal: adiciona, edita e elimina Welfares mensais;
        - Gestão Ementa: edita apenas a ementa de Welfares já existentes;
        - Gestão Welfare Individual / Leitura: apenas consulta.
        """
        mes_trancado = is_mes_trancado(self.ano_atual, self.mes_atual)
        if mes_trancado and modo == "adicionar":
            messagebox.showwarning(t("month_locked"), t("month_locked_warning"), parent=self.root)
            return

        existentes = {
            welfare["refeicao"]
            for welfare in get_welfares_mes(self.ano_atual, self.mes_atual).get(data_str, [])
        }

        pode_full = self.pode_adicionar_editar_welfare_mensal() and not mes_trancado
        pode_apagar = self.pode_eliminar_welfare_mensal() and not mes_trancado
        pode_ementa = self.pode_editar_ementa_mensal() and not mes_trancado

        if modo == "adicionar":
            if not pode_full:
                return

            if "Almoço" in existentes and "Jantar" in existentes:
                return

            if refeicao_inicial in existentes:
                refeicao_inicial = "Jantar" if "Almoço" in existentes else "Almoço"

            refeicoes_disponiveis = [r for r in REFEICOES if r not in existentes]
            if not refeicoes_disponiveis:
                return

            modo_visual = "adicionar"
            titulo_modo = t("add_welfare")

        else:
            refeicoes_disponiveis = [refeicao_inicial]
            modo_visual = "editar" if pode_full else "ementa" if pode_ementa else "consulta"
            titulo_modo = t("edit_welfare") if pode_full else t("edit_menu") if pode_ementa else t("view_welfare")

        chave = (data_str, refeicao_inicial, modo_visual)

        janela_existente = self.janelas_edicao_welfare.get(chave)
        if janela_existente and janela_existente.winfo_exists():
            janela_existente.lift()
            janela_existente.focus_force()
            return

        janela = tk.Toplevel(self.root)
        aplicar_icone(janela)
        self.janelas_edicao_welfare[chave] = janela
        self.registar_janela(janela)

        def fechar_janela():
            self.janelas_edicao_welfare.pop(chave, None)
            if janela in self.janelas_abertas:
                self.janelas_abertas.remove(janela)
            janela.destroy()

        janela.protocol("WM_DELETE_WINDOW", fechar_janela)

        janela.title(f"{titulo_modo} - {self.formatar_data_pt(data_str)}")
        janela.geometry("760x560")
        janela.resizable(False, False)
        janela.grab_set()

        tk.Label(
            janela,
            text=f"{titulo_modo} - {self.formatar_data_pt(data_str)}",
            font=("Arial", 16, "bold"),
            fg=COR_PRINCIPAL
        ).pack(pady=(15, 10))

        frame = tk.Frame(janela, padx=40, pady=10)
        frame.pack(fill="both", expand=True)

        tk.Label(frame, text=t("meal"), font=("Arial", 10, "bold")).grid(row=0, column=0, sticky="w", pady=7)

        combo_refeicao = ttk.Combobox(
            frame,
            state="readonly" if modo_visual == "adicionar" else "disabled",
            values=refeicoes_disponiveis,
            width=48
        )
        combo_refeicao.set(refeicao_inicial)
        combo_refeicao.grid(row=0, column=1, sticky="w", pady=7)

        tk.Label(frame, text=t("type"), font=("Arial", 10, "bold")).grid(row=1, column=0, sticky="w", pady=7)

        combo_tipo = ttk.Combobox(frame, state="readonly" if pode_full else "disabled", values=list(TIPOS_WELFARE.keys()), width=48)
        combo_tipo.set("Welfare")
        combo_tipo.grid(row=1, column=1, sticky="w", pady=7)

        tk.Label(frame, text=t("dish"), font=("Arial", 10, "bold")).grid(row=2, column=0, sticky="w", pady=7)

        entry_prato = tk.Entry(frame, width=70)
        entry_prato.grid(row=2, column=1, sticky="w", pady=7)

        tk.Label(frame, text=t("dessert"), font=("Arial", 10, "bold")).grid(row=3, column=0, sticky="w", pady=7)

        entry_sobremesa = tk.Entry(frame, width=70)
        entry_sobremesa.grid(row=3, column=1, sticky="w", pady=7)

        tk.Label(frame, text=t("observation"), font=("Arial", 10, "bold")).grid(row=4, column=0, sticky="nw", pady=7)

        txt_observacao = tk.Text(frame, width=53, height=8)
        txt_observacao.grid(row=4, column=1, sticky="w", pady=7)

        def aplicar_permissoes_campos():
            if modo_visual == "consulta":
                combo_tipo.config(state="disabled")
                entry_prato.config(state="disabled")
                entry_sobremesa.config(state="disabled")
                txt_observacao.config(state="disabled")
            elif modo_visual == "ementa":
                combo_tipo.config(state="disabled")
                txt_observacao.config(state="disabled")
            else:
                combo_tipo.config(state="readonly")
                entry_prato.config(state="normal")
                entry_sobremesa.config(state="normal")
                txt_observacao.config(state="normal")

        def carregar_dados_refeicao(event=None):
            refeicao = combo_refeicao.get()
            welfare = get_welfare(data_str, refeicao)

            entry_prato.config(state="normal")
            entry_sobremesa.config(state="normal")
            txt_observacao.config(state="normal")

            entry_prato.delete(0, tk.END)
            entry_sobremesa.delete(0, tk.END)
            txt_observacao.delete("1.0", tk.END)

            if welfare:
                combo_tipo.set(welfare["tipo"])
                entry_prato.insert(0, welfare["prato"] or "")
                entry_sobremesa.insert(0, welfare["sobremesa"] or "")
                txt_observacao.insert("1.0", welfare["observacao"] or "")
            else:
                combo_tipo.set("Welfare")

            aplicar_permissoes_campos()

        def guardar():
            refeicao = combo_refeicao.get()
            atual = get_welfare(data_str, refeicao)

            if modo_visual == "consulta":
                return

            if modo_visual == "adicionar" and get_welfare(data_str, refeicao):
                messagebox.showwarning(
                    "Já existe",
                    f"Já existe Welfare para {refeicao} neste dia. Usa o botão de edição."
                )
                fechar_janela()
                return

            if modo_visual == "ementa" and not atual:
                messagebox.showwarning("Sem Welfare", "Só podes editar ementas de Welfares já existentes.")
                fechar_janela()
                return

            tipo = combo_tipo.get()
            observacao = txt_observacao.get("1.0", tk.END).strip()

            if modo_visual == "ementa" and atual:
                tipo = atual["tipo"]
                observacao = atual["observacao"] or ""

            guardar_welfare(
                data_str=data_str,
                refeicao=refeicao,
                tipo=tipo,
                prato=entry_prato.get().strip(),
                sobremesa=entry_sobremesa.get().strip(),
                observacao=observacao
            )

            self.carregar_calendario()
            messagebox.showinfo(t("saved"), t("welfare_saved"))
            fechar_janela()

        def eliminar():
            if not pode_apagar:
                return

            refeicao = combo_refeicao.get()

            confirmar = messagebox.askyesno(
                t("delete"),
                t("delete_welfare_question", refeicao=refeicao)
            )

            if not confirmar:
                return

            eliminar_welfare(data_str, refeicao)
            self.carregar_calendario()
            messagebox.showinfo(t("deleted"), t("welfare_deleted"))
            fechar_janela()

        combo_refeicao.bind("<<ComboboxSelected>>", carregar_dados_refeicao)

        botoes = tk.Frame(janela, pady=15)
        botoes.pack(fill="x")

        if modo_visual != "consulta":
            tk.Button(
                botoes,
                text=t("save"),
                bg=COR_PRINCIPAL,
                fg="white",
                font=("Arial", 10, "bold"),
                relief="flat",
                width=14,
                command=guardar
            ).pack(side="left", padx=(230, 10))

        if modo_visual == "editar" and pode_apagar:
            tk.Button(
                botoes,
                text=t("delete"),
                bg=COR_VERMELHO,
                fg="white",
                font=("Arial", 10, "bold"),
                relief="flat",
                width=14,
                command=eliminar
            ).pack(side="left", padx=10)

        tk.Button(
            botoes,
            text=t("close"),
            bg=COR_CINZA,
            fg="white",
            font=("Arial", 10, "bold"),
            relief="flat",
            width=14,
            command=fechar_janela
        ).pack(side="left", padx=10)

        carregar_dados_refeicao()

    def imprimir_mes_atual(self):
        nome_ficheiro = f"SIGCP_{self.ano_atual}_{self.mes_atual:02d}.pdf"
        pasta_downloads = Path.home() / "Downloads"

        destino = filedialog.asksaveasfilename(
            title=t("save_pdf_month"),
            initialdir=str(pasta_downloads) if pasta_downloads.exists() else str(Path.home()),
            initialfile=nome_ficheiro,
            defaultextension=".pdf",
            filetypes=[(t("pdf_files"), "*.pdf")],
            parent=self.root,
        )

        if not destino:
            return

        try:
            pdf_path = gerar_pdf_mes(self.ano_atual, self.mes_atual, output_path=destino)
            messagebox.showinfo("PDF", f"{t("pdf_saved")}\n\n{pdf_path}")
        except Exception as exc:
            messagebox.showerror(t("print").strip(), f"Erro ao gerar PDF:\n{exc}")

    def abrir_welfare_individual(self):
        if not self.pode_ver_welfare_individual():
            return
        if self.trazer_janela_tipo("welfare_individual"):
            return
        WelfareIndividualWindow(self)

    def abrir_gestao_ferias(self):
        if not self.pode_gerir_ferias():
            return
        if self.trazer_janela_tipo("gestao_ferias"):
            return
        FeriasWindow(self)

    def refresh_welfare_individual_if_open(self):
        janela = self.janelas_por_tipo.get("welfare_individual")
        if janela and janela.winfo_exists() and hasattr(janela, "_welfare_individual_ref"):
            ref = janela._welfare_individual_ref
            ref.carregar_dados()
            ref.desenhar_grelha()

    def abrir_administracao(self):
        if self.trazer_janela_tipo("administracao"):
            return
        AdminWindow(self)

    def abrir_pessoal(self):
        if self.trazer_janela_tipo("pessoal"):
            return
        AdminWindow(self, modo_pessoal=True)


    def formatar_data_pt(self, data_str):
        ano, mes, dia = data_str.split("-")
        return f"{dia}/{mes}/{ano}"
