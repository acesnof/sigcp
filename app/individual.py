import calendar
from datetime import datetime, time, timedelta, date
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from PIL import Image, ImageTk

from app.config import (
    DOCS_DIR,
    COR_BRANCO,
    COR_LINHA,
    COR_PRINCIPAL,
    COR_VERMELHO,
    COR_WEEKEND,
    COR_FERIAS,
)
from app.db import (
    get_utilizadores_ativos_para_welfare_individual,
    get_welfares_individuais_mes,
    get_welfares_mes,
    get_day_offs_mes,
    get_valor_welfare,
    get_valor_caixa,
    get_horario_dfac,
    get_nome_cos,
    set_welfare_individual,
    reset_welfares_individuais_mes,
    is_mes_trancado,
    get_inicio_semana,
    get_snr_unico_para_assinatura,
    get_responsavel_welfare_mais_antigo_ativo,
    get_ferias_mes,
)
from app.utils import aplicar_icone
from app.i18n import t, months, weekdays_short
from app.reports.weekly_xlsx import gerar_meals_request_weekly
from app.reports.reimbursement_xlsx import gerar_reembolso_mensal
from app.reports.service_note_docx import gerar_service_note, formatar_data_militar
from app.reports.request_docx import gerar_request_welfare_meals, gerar_request_welfare_meals_hoto
from app.reports.individual_pdf import gerar_pdf_welfare_individual


COR_COHESION = "#f3fbf4"
COR_RESUMO = "#f7f7f7"
COR_INATIVO = "#888888"
COR_TOTAL = "#e8f4f6"
COR_SEMANA = "#eef7f8"
COR_CHEGADA = "#c9f8ee"
COR_PARTIDA = "#ffbbbb"
COR_HOVER = "#fff2cc"
COR_HOVER_MARCADO = "#c40000"
COR_ALTERACAO = "#a5fa96"
COR_REEMBOLSO_FINAL_BG = "#caffc4"

REFEICOES_WELFARE = ["Almoço", "Jantar"]
REFEICAO_PEQUENO_ALMOCO = "Pequeno-Almoço"


class WelfareIndividualWindow:
    def __init__(self, app):
        self.app = app
        self.ano_atual = app.ano_atual
        self.mes_atual = app.mes_atual
        self.modo = "welfare"  # welfare | pequeno_almoco

        self.cell_w = 22
        self.row_h = 30
        self.header_h1 = 28
        self.header_h2 = 24
        self.ident_w = 260
        self.welfare_w = 70
        self.cohesion_w = 75
        self.reimbursement_w = 105
        self.caixa_w = 85
        self.reembolso_final_w = 115
        self.select_w = 80

        self.utilizadores = []
        self.mensais = {}
        self.individuais = {}
        self.day_offs = set()
        self.ferias = {}
        self.hover_row_idx = None
        self.hover_dia_idx = None
        self.alteracoes_pendentes = {}
        self.hoto_selecionados = set()

        # Caches locais para tornar a grelha muito mais leve, sobretudo com SQLite em pasta partilhada.
        self._valor_welfare_cache = 0
        self._valor_caixa_cache = 0
        self._horario_dfac_cache = {}
        self._inicio_semana_cache = ""
        self._mensais_set = set()
        self._day_infos = []
        self._ferias_intervalos = {}
        self._resumo_cache = {}
        self._dfac_cache = None
        self._redraw_after_id = None
        self._last_canvas_size = None

        self.janela = tk.Toplevel(app.root)
        aplicar_icone(self.janela)
        self.app.registar_janela(self.janela, "welfare_individual")
        self.janela._welfare_individual_ref = self

        self.janela.title(t("welfare_individual"))
        self.janela.geometry("1500x780")
        self.janela.minsize(1150, 650)
        self.janela.configure(bg="white")
        try:
            self.janela.state("zoomed")
        except tk.TclError:
            self.janela.attributes("-zoomed", True)

        self.criar_layout()
        self.carregar_dados()
        self.desenhar_grelha()

    def pode_editar(self):
        if is_mes_trancado(self.ano_atual, self.mes_atual):
            return False
        return self.app.is_admin() or "Gestão Welfare Individual" in self.app.acessos()

    def is_responsavel_welfare(self):
        """Só quem está designado como Responsável Welfare pode gerar documentos/exportações."""
        try:
            if int(self.app.current_user.get("responsavel_welfare") or 0) != 1:
                return False
        except (TypeError, ValueError, AttributeError):
            return False

        data_partida = (self.app.current_user.get("data_partida") or "").strip()
        if data_partida:
            try:
                if datetime.strptime(data_partida[:10], "%Y-%m-%d").date() < date.today():
                    return False
            except ValueError:
                pass

        return True

    def pode_exportar_semanas(self):
        return self.is_responsavel_welfare() or self.app.is_admin() or "Gestão Welfare Individual" in self.app.acessos()

    def criar_layout(self):
        topo = tk.Frame(self.janela, bg=COR_PRINCIPAL, height=58)
        topo.pack(fill="x")
        topo.pack_propagate(False)

        self.lbl_titulo = tk.Label(
            topo,
            text=t("welfare_individual"),
            bg=COR_PRINCIPAL,
            fg="white",
            font=("Arial", 17, "bold")
        )
        self.lbl_titulo.pack(side="left", padx=20)

        filtros = tk.Frame(self.janela, bg="white", height=64)
        filtros.pack(fill="x")
        filtros.pack_propagate(False)

        tk.Label(filtros, text=t("month"), bg="white", font=("Arial", 12, "bold")).pack(side="left", padx=(20, 8))

        self.combo_mes = ttk.Combobox(
            filtros,
            state="readonly",
            width=18,
            values=[months()[i] for i in range(1, 13)]
        )
        self.combo_mes.current(self.mes_atual - 1)
        self.combo_mes.pack(side="left", ipady=4)

        tk.Label(filtros, text=t("year"), bg="white", font=("Arial", 12, "bold")).pack(side="left", padx=(20, 8))

        anos = list(range(self.ano_atual - 5, self.ano_atual + 11))
        self.combo_ano = ttk.Combobox(filtros, state="readonly", width=8, values=anos)
        self.combo_ano.set(self.ano_atual)
        self.combo_ano.pack(side="left", ipady=4)

        self.btn_atualizar = tk.Button(
            filtros,
            text=t("update"),
            bg=COR_PRINCIPAL,
            fg="white",
            activebackground="#1ab394",
            activeforeground="white",
            font=("Arial", 10, "bold"),
            relief="flat",
            width=14,
            padx=8,
            pady=5,
            command=self.on_btn_atualizar
        )
        self.btn_atualizar.pack(side="left", padx=(22, 8))

        self.btn_imprimir = tk.Button(
            filtros,
            text=t("print").strip(),
            bg="white",
            fg=COR_PRINCIPAL,
            activebackground="#f2f2f2",
            activeforeground=COR_PRINCIPAL,
            font=("Arial", 10, "bold"),
            relief="solid",
            bd=1,
            width=14,
            padx=8,
            pady=5,
            command=self.imprimir_tabela
        )
        self.btn_imprimir.pack(side="left", padx=(30, 8))

        if self.pode_editar():
            self.btn_repor = tk.Button(
                filtros,
                text=t("reset"),
                bg="white",
                fg=COR_PRINCIPAL,
                activebackground="#f2f2f2",
                activeforeground=COR_PRINCIPAL,
                font=("Arial", 10, "bold"),
                relief="solid",
                bd=1,
                width=14,
                padx=8,
                pady=5,
                command=self.repor_welfares_origem
            )
            self.btn_repor.pack(side="left", padx=(0, 8))

        # Botões de exportação/documentos movidos para o footer.


        texto_modo = t("click_cell_mode") if self.pode_editar() else t("view_mode")
        self.lbl_modo = tk.Label(
            filtros,
            text=texto_modo,
            bg="white",
            fg="#555555",
            font=("Arial", 10, "bold")
        )
        self.lbl_modo.pack(side="left", padx=(12, 0))

        self.btn_pequeno_almoco = tk.Button(
            filtros,
            text=t("breakfast"),
            bg="white",
            fg=COR_PRINCIPAL,
            activebackground="#f2f2f2",
            activeforeground=COR_PRINCIPAL,
            font=("Arial", 10, "bold"),
            relief="solid",
            bd=1,
            width=18,
            padx=8,
            pady=5,
            command=self.alternar_modo
        )
        self.btn_pequeno_almoco.pack(side="right", padx=(8, 18))

        # Botão Distribuição XFA movido para o footer.



        self.atualizar_titulo_modo()

        area = tk.Frame(self.janela, bg="white", padx=12, pady=10)
        area.pack(fill="both", expand=True)

        self.canvas = tk.Canvas(area, bg="white", highlightthickness=1, highlightbackground=COR_LINHA)
        self.scroll_y = ttk.Scrollbar(area, orient="vertical", command=self.canvas.yview)
        self.scroll_x = ttk.Scrollbar(area, orient="horizontal", command=self.canvas.xview)

        self.canvas.configure(yscrollcommand=self.scroll_y.set, xscrollcommand=self.scroll_x.set)

        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.scroll_y.grid(row=0, column=1, sticky="ns")
        self.scroll_x.grid(row=1, column=0, sticky="ew")

        area.grid_rowconfigure(0, weight=1)
        area.grid_columnconfigure(0, weight=1)

        self.footer = tk.Frame(self.janela, bg="white", height=46)
        self.footer.pack(fill="x", padx=12, pady=(0, 8))
        self.footer.pack_propagate(False)

        self.footer_acoes = tk.Frame(self.footer, bg="white")
        self.footer_acoes.pack(side="left", padx=(0, 8))

        if self.is_responsavel_welfare():
            self.btn_excel_reembolso = tk.Button(
                self.footer_acoes,
                text=t("excel_reimbursement"),
                bg="#ffe699",
                fg="#111111",
                activebackground="#ffe08a",
                activeforeground="#111111",
                font=("Arial", 9, "bold"),
                relief="solid",
                bd=1,
                width=16,
                padx=6,
                pady=4,
                command=lambda: self.exportar_reembolso(hoto=False)
            )
            self.btn_excel_reembolso.pack(side="left", padx=(0, 6))

            self.btn_service_note = tk.Button(
                self.footer_acoes,
                text=t("service_note"),
                bg="#d8f1f4",
                fg="#111111",
                activebackground="#cce9ed",
                activeforeground="#111111",
                font=("Arial", 9, "bold"),
                relief="solid",
                bd=1,
                width=13,
                padx=6,
                pady=4,
                command=self.exportar_service_note
            )
            self.btn_service_note.pack(side="left", padx=(0, 6))

            self.btn_request = tk.Button(
                self.footer_acoes,
                text=t("request"),
                bg="#d8f1f4",
                fg="#111111",
                activebackground="#cce9ed",
                activeforeground="#111111",
                font=("Arial", 9, "bold"),
                relief="solid",
                bd=1,
                width=11,
                padx=6,
                pady=4,
                command=self.exportar_request
            )
            self.btn_request.pack(side="left", padx=(0, 6))

            self.btn_excel_hoto = tk.Button(
                self.footer_acoes,
                text=t("excel_hoto"),
                bg="#fff4d2",
                fg="#111111",
                activebackground="#ffedb3",
                activeforeground="#111111",
                font=("Arial", 9, "bold"),
                relief="solid",
                bd=1,
                width=22,
                padx=6,
                pady=4,
                command=lambda: self.exportar_reembolso(hoto=True)
            )
            self.btn_excel_hoto.pack(side="left", padx=(22, 6))

            self.btn_request_hoto = tk.Button(
                self.footer_acoes,
                text=t("request_hoto"),
                bg="#d8f1f4",
                fg="#111111",
                activebackground="#cce9ed",
                activeforeground="#111111",
                font=("Arial", 9, "bold"),
                relief="solid",
                bd=1,
                width=13,
                padx=6,
                pady=4,
                command=self.exportar_request_hoto
            )
            self.btn_request_hoto.pack(side="left", padx=(0, 6))

            self.btn_distribuicao_xfa = tk.Button(
                self.footer_acoes,
                text="Distribuição XFA",
                bg="#f2978c",
                fg="#111111",
                activebackground="#ec7f72",
                activeforeground="#111111",
                font=("Arial", 9, "bold"),
                relief="solid",
                bd=1,
                width=16,
                padx=6,
                pady=4,
                command=self.abrir_distribuicao_xfa
            )
            self.btn_distribuicao_xfa.pack(side="left", padx=(22, 6))

        self.lbl_dfac = tk.Label(
            self.footer,
            text="",
            bg="white",
            fg=COR_PRINCIPAL,
            font=("Arial", 10, "bold"),
            anchor="e"
        )
        self.lbl_dfac.pack(side="right", padx=10)

        self.canvas.bind("<Button-1>", self.on_canvas_click)
        self.canvas.bind("<Motion>", self.on_canvas_motion)
        self.canvas.bind("<Leave>", self.on_canvas_leave)
        self.canvas.bind("<Configure>", self._on_canvas_configure)

    def atualizar_titulo_modo(self):
        if self.modo == "pequeno_almoco":
            titulo = t("breakfast")
            botao = t("individual_welfare_mode")
        else:
            titulo = t("welfare_individual")
            botao = t("breakfast")

        self.janela.title(titulo)
        if hasattr(self, "lbl_titulo"):
            self.lbl_titulo.config(text=titulo)
        if hasattr(self, "btn_pequeno_almoco"):
            self.btn_pequeno_almoco.config(text=botao)
        if hasattr(self, "btn_repor"):
            self.btn_repor.config(text=t("reset"))

    def alternar_modo(self):
        self.modo = "pequeno_almoco" if self.modo == "welfare" else "welfare"
        self.atualizar_titulo_modo()
        self.carregar_dados()
        self.desenhar_grelha()
        self.janela.lift()
        self.janela.focus_force()

    def atualizar_estado_botao_atualizar(self):
        if not hasattr(self, "btn_atualizar"):
            return
        if self.alteracoes_pendentes:
            self.btn_atualizar.config(
                bg=COR_ALTERACAO,
                fg="#111111",
                activebackground=COR_ALTERACAO,
                activeforeground="#111111"
            )
        else:
            self.btn_atualizar.config(
                bg=COR_PRINCIPAL,
                fg="white",
                activebackground="#1ab394",
                activeforeground="white"
            )

    def on_btn_atualizar(self):
        if self.alteracoes_pendentes:
            self.confirmar_alteracoes_pendentes()
            return
        self.atualizar_mes_ano()

    def perguntar_guardar_alteracoes(self):
        resultado = {"valor": False}
        dlg = tk.Toplevel(self.janela)
        aplicar_icone(dlg)
        dlg.title(t("pending_changes_title"))
        dlg.geometry("420x160")
        dlg.resizable(False, False)
        dlg.configure(bg="white")
        dlg.transient(self.janela)
        dlg.grab_set()

        tk.Label(
            dlg,
            text=t("pending_changes_question"),
            bg="white",
            fg="#111111",
            font=("Arial", 11, "bold"),
            wraplength=360,
            justify="center"
        ).pack(fill="both", expand=True, padx=25, pady=(20, 10))

        botoes = tk.Frame(dlg, bg="white", pady=12)
        botoes.pack(fill="x")

        def sim():
            resultado["valor"] = True
            dlg.destroy()

        def anular():
            resultado["valor"] = False
            dlg.destroy()

        tk.Button(
            botoes,
            text=t("yes"),
            bg=COR_ALTERACAO,
            fg="#111111",
            font=("Arial", 10, "bold"),
            relief="flat",
            width=12,
            command=sim
        ).pack(side="left", padx=(80, 10))

        tk.Button(
            botoes,
            text=t("cancel_changes"),
            bg="#777777",
            fg="white",
            font=("Arial", 10, "bold"),
            relief="flat",
            width=12,
            command=anular
        ).pack(side="left", padx=10)

        dlg.protocol("WM_DELETE_WINDOW", anular)
        dlg.update_idletasks()
        x = self.janela.winfo_x() + (self.janela.winfo_width() // 2) - (dlg.winfo_width() // 2)
        y = self.janela.winfo_y() + (self.janela.winfo_height() // 2) - (dlg.winfo_height() // 2)
        dlg.geometry(f"+{x}+{y}")
        self.janela.wait_window(dlg)
        return resultado["valor"]

    def confirmar_alteracoes_pendentes(self):
        confirmar = self.perguntar_guardar_alteracoes()

        if confirmar:
            for (user_id, data_str, refeicao), marcado in list(self.alteracoes_pendentes.items()):
                set_welfare_individual(user_id, data_str, refeicao, marcado)
                self.individuais[(user_id, data_str, refeicao)] = 1 if marcado else 0
            self.alteracoes_pendentes.clear()
            self.atualizar_estado_botao_atualizar()
            self.carregar_dados()
            self.desenhar_grelha()
            messagebox.showinfo(t("saved"), t("pending_changes_saved"), parent=self.janela)
        else:
            self.alteracoes_pendentes.clear()
            self.atualizar_estado_botao_atualizar()
            self.combo_mes.current(self.mes_atual - 1)
            self.combo_ano.set(self.ano_atual)
            self.carregar_dados()
            self.desenhar_grelha()

        self.janela.lift()
        self.janela.focus_force()

    def atualizar_mes_ano(self):
        mes_nome = self.combo_mes.get()
        self.mes_atual = list(months().values()).index(mes_nome) + 1
        self.ano_atual = int(self.combo_ano.get())
        self.alteracoes_pendentes.clear()
        self.atualizar_estado_botao_atualizar()

        self.carregar_dados()
        self.desenhar_grelha()

    def repor_welfares_origem(self):
        if self.modo != "welfare":
            return

        if is_mes_trancado(self.ano_atual, self.mes_atual):
            messagebox.showwarning(t("month_locked"), t("month_locked_warning"), parent=self.janela)
            self.janela.lift()
            self.janela.focus_force()
            return

        confirmar = messagebox.askyesno(t("reset"), t("reset_question"), parent=self.janela)
        if not confirmar:
            self.janela.lift()
            self.janela.focus_force()
            return

        reset_welfares_individuais_mes(self.ano_atual, self.mes_atual)
        self.carregar_dados()
        self.desenhar_grelha()
        messagebox.showinfo(t("reset"), t("reset_done"), parent=self.janela)
        self.janela.lift()
        self.janela.focus_force()

    def carregar_dados(self):
        self._ctx_meses_export = {}
        self.utilizadores = get_utilizadores_ativos_para_welfare_individual(self.ano_atual, self.mes_atual)
        self.mensais = get_welfares_mes(self.ano_atual, self.mes_atual)
        self.individuais = get_welfares_individuais_mes(self.ano_atual, self.mes_atual)
        self.day_offs = get_day_offs_mes(self.ano_atual, self.mes_atual)
        self.ferias = get_ferias_mes(self.ano_atual, self.mes_atual)
        self._preparar_cache_mes()

    def _preparar_cache_mes(self):
        """Prepara todos os dados repetidos em memória.

        Isto evita dezenas/centenas de leituras e parses enquanto a grelha é
        redesenhada. É especialmente importante quando a base SQLite está numa
        pasta partilhada.
        """
        self._valor_welfare_cache = self._ler_valor_welfare_db()
        self._valor_caixa_cache = self._ler_valor_caixa_db()
        self._horario_dfac_cache = get_horario_dfac()
        self._inicio_semana_cache = (get_inicio_semana() or "").strip()

        self._mensais_set = {
            (data_str, welfare.get("refeicao"))
            for data_str, lista in (self.mensais or {}).items()
            for welfare in lista
        }

        dias = self.dias_mes()
        self._day_infos = []
        for dia in range(1, dias + 1):
            data_str = f"{self.ano_atual}-{self.mes_atual:02d}-{dia:02d}"
            weekday = calendar.weekday(self.ano_atual, self.mes_atual, dia)
            self._day_infos.append({
                "dia": dia,
                "data_str": data_str,
                "weekday": weekday,
                "fim_semana": weekday in [5, 6],
                "day_off": data_str in self.day_offs,
                "especial": weekday in [5, 6] or data_str in self.day_offs,
            })

        for user in self.utilizadores:
            chegada_raw = (user.get("data_chegada") or "").strip()
            partida_raw = (user.get("data_partida") or "").strip()
            user["_chegada_date"] = self._date_part(chegada_raw)
            user["_partida_date"] = self._date_part(partida_raw)
            user["_chegada_min"] = self._to_minutes(self._time_part(chegada_raw, "00:00"))
            user["_partida_min"] = self._to_minutes(self._time_part(partida_raw, "00:00"))

        self._ferias_intervalos = {}
        for user_id, periodos in (self.ferias or {}).items():
            lista = []
            for periodo in periodos:
                inicio = self._parse_dt_ferias(periodo.get("data_hora_inicio"), "00:00")
                fim = self._parse_dt_ferias(periodo.get("data_hora_fim"), "23:59")
                if not inicio or not fim:
                    continue
                lista.append((inicio, fim))
            self._ferias_intervalos[user_id] = lista

        self._limpar_caches_calculo()

    def _limpar_caches_calculo(self):
        self._resumo_cache = {}
        self._dfac_cache = None

    def _ler_valor_welfare_db(self):
        raw = (get_valor_welfare() or "0").strip().replace(".", "").replace(",", "")
        try:
            return int(raw)
        except ValueError:
            return 0

    def _ler_valor_caixa_db(self):
        raw = (get_valor_caixa() or "0").strip().replace(".", "").replace(",", "")
        try:
            return int(raw)
        except ValueError:
            return 0

    def _agendar_redesenho(self, delay=60):
        """Agrupa vários pedidos de redraw num só."""
        if self._redraw_after_id is not None:
            try:
                self.janela.after_cancel(self._redraw_after_id)
            except tk.TclError:
                pass
        self._redraw_after_id = self.janela.after(delay, self._executar_redesenho_agendado)

    def _executar_redesenho_agendado(self):
        self._redraw_after_id = None
        self.desenhar_grelha()

    def _on_canvas_configure(self, event):
        tamanho = (event.width, event.height)
        if tamanho == self._last_canvas_size:
            return
        self._last_canvas_size = tamanho
        self._agendar_redesenho(delay=40)

    def dias_mes(self):
        return calendar.monthrange(self.ano_atual, self.mes_atual)[1]

    def prefixo_semana(self):
        return "W" if getattr(self.app, "idioma", "PT") == "EN" else "S"

    def numero_semana_custom(self, data_ref):
        inicio = (self._inicio_semana_cache or "").strip()

        if inicio:
            try:
                data_inicio = datetime.strptime(inicio[:10], "%Y-%m-%d").date()
                delta = (data_ref - data_inicio).days
                if delta < 0:
                    return 0
                return (delta // 7) + 1
            except ValueError:
                pass

        return data_ref.isocalendar().week

    def semanas_visiveis_mes(self):
        cal = calendar.Calendar(firstweekday=0)
        semanas = []
        for semana_datas in cal.monthdatescalendar(self.ano_atual, self.mes_atual):
            dias_semana = [d.day if d.month == self.mes_atual else 0 for d in semana_datas]
            dias_validos = [dia for dia in dias_semana if dia != 0]
            if not dias_validos:
                continue
            numero_semana = self.numero_semana_custom(semana_datas[0])
            inicio_semana = semana_datas[0]
            semanas.append((dias_semana, numero_semana, inicio_semana, list(semana_datas)))
        return semanas

    def desenhar_linha_semanas(self, y_semana, dias, unidades_por_dia, resumo_x=None, total_w=None):
        self.canvas.create_rectangle(0, y_semana, self.ident_w, y_semana + self.row_h, fill=COR_SEMANA, outline=COR_LINHA)

        label_semana = "Week" if getattr(self.app, "idioma", "PT") == "EN" else "Semana"
        info_texto = (
            "Click Week to Generate ESG Meals Table"
            if getattr(self.app, "idioma", "PT") == "EN"
            else "Clique na Semana para Gerar Tabela Refeições ESG"
        )

        self.canvas.create_text(
            10,
            y_semana + 8,
            text=label_semana,
            anchor="w",
            fill=COR_PRINCIPAL,
            font=("Arial", 9, "bold")
        )
        if self.pode_exportar_semanas():
            self.canvas.create_text(
                10,
                y_semana + 22,
                text="ⓘ " + info_texto,
                anchor="w",
                fill="#555555",
                font=("Arial", 7)
            )

        for semana, numero_semana, inicio_semana, _semana_datas in self.semanas_visiveis_mes():
            dias_validos = [dia for dia in semana if 1 <= dia <= dias]
            if not dias_validos:
                continue

            dia_inicio = min(dias_validos)
            dia_fim = max(dias_validos)
            x1 = self.ident_w + (dia_inicio - 1) * unidades_por_dia * self.cell_w
            x2 = self.ident_w + dia_fim * unidades_por_dia * self.cell_w
            tag_semana = f"week|{inicio_semana.isoformat()}|{numero_semana}"

            self.canvas.create_rectangle(x1, y_semana, x2, y_semana + self.row_h, fill=COR_SEMANA, outline=COR_LINHA, tags=(tag_semana,))
            self.canvas.create_text(
                (x1 + x2) / 2,
                y_semana + self.row_h / 2,
                text=f"{self.prefixo_semana()}{numero_semana}",
                fill=COR_PRINCIPAL,
                font=("Arial", 10, "bold"),
                tags=(tag_semana,)
            )

        if resumo_x is not None and total_w is not None and total_w > resumo_x:
            self.canvas.create_rectangle(resumo_x, y_semana, total_w, y_semana + self.row_h, fill=COR_SEMANA, outline=COR_LINHA)

    def identificacao(self, user):
        posto = (user.get("posto") or "").strip()
        sobrenome = (user.get("sobrenome") or "").strip().upper()
        nome = (user.get("nome") or "").strip().upper()
        if sobrenome and nome:
            return f"{posto} {sobrenome}, {nome}".strip()
        return f"{posto} {sobrenome or nome}".strip()

    def _date_part(self, value):
        value = (value or "").strip()
        if not value:
            return ""

        parte = value.split()[0]

        # Formato normal da aplicação: YYYY-MM-DD ou YYYY-MM-DD HH:MM
        try:
            return datetime.strptime(parte, "%Y-%m-%d").date().isoformat()
        except ValueError:
            pass

        # Proteção para dados antigos/importados: DD/MM/YYYY ou DD-MM-YYYY
        for fmt in ("%d/%m/%Y", "%d-%m-%Y"):
            try:
                return datetime.strptime(parte, fmt).date().isoformat()
            except ValueError:
                pass

        return parte

    def _time_part(self, value, default="00:00"):
        value = (value or "").strip()
        if " " not in value:
            return default
        tval = value.split()[1][:5]
        return tval if len(tval) == 5 and tval[2] == ":" else default

    def _to_minutes(self, hhmm):
        try:
            h, m = [int(x) for x in hhmm.split(":")]
            return h * 60 + m
        except Exception:
            return 0

    def _parse_dt_ferias(self, value, default_time="00:00"):
        value = (value or "").strip()
        if not value:
            return None
        try:
            if " " in value:
                return datetime.strptime(value[:16], "%Y-%m-%d %H:%M")
            return datetime.strptime(value[:10] + " " + default_time, "%Y-%m-%d %H:%M")
        except Exception:
            return None

    def _refeicao_key(self, refeicao):
        if refeicao == REFEICAO_PEQUENO_ALMOCO:
            return "pequeno_almoco"
        if refeicao == "Almoço":
            return "almoco"
        if refeicao == "Jantar":
            return "jantar"
        return ""

    def _data_especial(self, data_str, ctx=None):
        """True apenas para Horário DFAC especial.

        Para efeitos de horário DFAC:
        - dias normais = Segunda-feira a Sábado;
        - horário especial = Domingo ou Day Off.

        Nota: isto não altera a cor/contabilização de fim de semana na grelha,
        apenas a escolha do horário usado nas regras de chegada/partida/férias.
        """
        try:
            data_obj = datetime.strptime(data_str[:10], "%Y-%m-%d").date()
        except Exception:
            return False
        day_offs = self.day_offs if ctx is None else ctx.get("day_offs", set())
        return data_obj.weekday() == 6 or data_str[:10] in day_offs

    def _horario_refeicao(self, data_str, refeicao, ctx=None):
        horario = self._horario_dfac_cache or get_horario_dfac()
        tipo = "especial" if self._data_especial(data_str, ctx) else "normal"
        ref_key = self._refeicao_key(refeicao)
        dados = (((horario or {}).get(tipo) or {}).get(ref_key) or {})
        defaults = {
            "pequeno_almoco": ("07:00", "09:00"),
            "almoco": ("12:00", "14:00"),
            "jantar": ("18:00", "20:00"),
        }
        abertura, fecho = defaults.get(ref_key, ("00:00", "23:59"))
        abertura = dados.get("abertura") or abertura
        fecho = dados.get("fecho") or fecho
        return self._to_minutes(abertura[:5]), self._to_minutes(fecho[:5])

    def _tem_refeicao_por_chegada(self, data_str, chegada_min, refeicao, ctx=None):
        # No dia da chegada, tem direito à refeição se chegar antes do fecho dessa refeição.
        _abertura, fecho = self._horario_refeicao(data_str, refeicao, ctx)
        return int(chegada_min or 0) < fecho

    def _tem_refeicao_por_partida(self, data_str, partida_min, refeicao, ctx=None):
        # No dia da partida, tem direito à refeição se ainda estiver na base quando essa refeição abre.
        abertura, _fecho = self._horario_refeicao(data_str, refeicao, ctx)
        return int(partida_min or 0) >= abertura

    def _intervalo_apanha_refeicao(self, data_str, inicio_min, fim_min, refeicao, ctx=None):
        abertura, fecho = self._horario_refeicao(data_str, refeicao, ctx)
        return int(inicio_min or 0) < fecho and int(fim_min or 0) >= abertura

    def user_em_ferias_na_data(self, user, data_str):
        user_id = user.get("id")
        for inicio, fim in self._ferias_intervalos.get(user_id, []):
            inicio_data = inicio.date().isoformat()
            fim_data = fim.date().isoformat()
            if inicio_data <= data_str <= fim_data:
                return True
        return False

    def user_em_ferias_na_refeicao(self, user, data_str, refeicao):
        """True quando esta refeição deve aparecer com F por férias.

        O dia de início das férias segue a mesma regra da partida da base.
        O dia de fim das férias segue a mesma regra da chegada à base.
        Os horários usados são os configurados em Horário DFAC, distinguindo
        dias normais de sábado/domingo/Day Off.
        """
        user_id = user.get("id")
        for inicio, fim in self._ferias_intervalos.get(user_id, []):
            inicio_data = inicio.date().isoformat()
            fim_data = fim.date().isoformat()
            if data_str < inicio_data or data_str > fim_data:
                continue

            inicio_min = self._to_minutes(inicio.strftime("%H:%M"))
            fim_min = self._to_minutes(fim.strftime("%H:%M"))

            if inicio_data == fim_data == data_str:
                return self._intervalo_apanha_refeicao(data_str, inicio_min, fim_min, refeicao)

            if data_str == inicio_data:
                return not self._tem_refeicao_por_partida(data_str, inicio_min, refeicao)

            if data_str == fim_data:
                return not self._tem_refeicao_por_chegada(data_str, fim_min, refeicao)

            return True

        return False

    def user_tem_pequeno_almoco_em_ferias_na_data(self, user, data_str):
        return not self.user_em_ferias_na_refeicao(user, data_str, REFEICAO_PEQUENO_ALMOCO)

    def user_ativo_na_data(self, user, data_str):
        chegada = user.get("_chegada_date") if "_chegada_date" in user else self._date_part(user.get("data_chegada"))
        partida = user.get("_partida_date") if "_partida_date" in user else self._date_part(user.get("data_partida"))
        if chegada and data_str < chegada:
            return False
        if partida and data_str > partida:
            return False
        return True

    def user_tem_refeicao_na_data(self, user, data_str, refeicao):
        chegada = user.get("_chegada_date") if "_chegada_date" in user else self._date_part(user.get("data_chegada"))
        partida = user.get("_partida_date") if "_partida_date" in user else self._date_part(user.get("data_partida"))

        if chegada and data_str < chegada:
            return False
        if partida and data_str > partida:
            return False

        if chegada and data_str == chegada:
            chegada_min = int(user.get("_chegada_min", 0) or 0)
            if not self._tem_refeicao_por_chegada(data_str, chegada_min, refeicao):
                return False

        if partida and data_str == partida:
            partida_min = int(user.get("_partida_min", 0) or 0)
            if not self._tem_refeicao_por_partida(data_str, partida_min, refeicao):
                return False

        return True

    def user_tem_pequeno_almoco_na_data(self, user, data_str):
        if not self.user_tem_refeicao_na_data(user, data_str, REFEICAO_PEQUENO_ALMOCO):
            return False
        if not self.user_tem_pequeno_almoco_em_ferias_na_data(user, data_str):
            return False
        return True

    def mensal_marcado(self, data_str, refeicao):
        return (data_str, refeicao) in self._mensais_set

    def valor_efetivo_base(self, utilizador_id, data_str, refeicao):
        chave = (utilizador_id, data_str, refeicao)
        if chave in self.individuais:
            return bool(self.individuais[chave])
        return self.mensal_marcado(data_str, refeicao)

    def valor_efetivo(self, utilizador_id, data_str, refeicao):
        chave = (utilizador_id, data_str, refeicao)
        if chave in self.alteracoes_pendentes:
            return bool(self.alteracoes_pendentes[chave])
        return self.valor_efetivo_base(utilizador_id, data_str, refeicao)

    def valor_pequeno_almoco_base(self, user, data_str):
        if not self.user_tem_pequeno_almoco_na_data(user, data_str):
            return False
        chave = (user["id"], data_str, REFEICAO_PEQUENO_ALMOCO)
        if chave in self.individuais:
            return bool(self.individuais[chave])
        return True

    def valor_pequeno_almoco(self, user, data_str):
        if not self.user_tem_pequeno_almoco_na_data(user, data_str):
            return False
        chave = (user["id"], data_str, REFEICAO_PEQUENO_ALMOCO)
        if chave in self.alteracoes_pendentes:
            return bool(self.alteracoes_pendentes[chave])
        return self.valor_pequeno_almoco_base(user, data_str)

    def is_fim_semana_ou_day_off(self, data_str):
        try:
            dia = int(data_str[-2:])
            info = self._day_infos[dia - 1]
            return bool(info["especial"])
        except Exception:
            _, mes, dia = data_str.split("-")
            weekday = calendar.weekday(self.ano_atual, int(mes), int(dia))
            return weekday in [5, 6] or data_str in self.day_offs

    def calcular_resumo_user(self, user):
        user_id = user["id"]
        cache_key = (user_id, tuple(sorted(self.alteracoes_pendentes.items())))
        if cache_key in self._resumo_cache:
            return self._resumo_cache[cache_key]

        welfare = 0
        cohesion = 0
        for info in self._day_infos:
            data_str = info["data_str"]
            especial = info["especial"]
            for refeicao in REFEICOES_WELFARE:
                if not self.user_tem_refeicao_na_data(user, data_str, refeicao) or self.user_em_ferias_na_refeicao(user, data_str, refeicao):
                    continue
                if self.valor_efetivo(user_id, data_str, refeicao):
                    if especial:
                        welfare += 1
                    else:
                        cohesion += 1
        valor = self.valor_welfare_numero()
        reimbursement = (welfare + cohesion) * valor
        result = (welfare, cohesion, reimbursement)
        self._resumo_cache[cache_key] = result
        return result

    def valor_welfare_numero(self):
        return int(self._valor_welfare_cache or 0)

    def valor_caixa_numero(self):
        return int(self._valor_caixa_cache or 0)

    def calcular_caixa_user(self, user):
        valor_caixa = self.valor_caixa_numero()
        if valor_caixa <= 0:
            return 0

        dias_caixa = 0
        chegada = user.get("_chegada_date") if "_chegada_date" in user else self._date_part(user.get("data_chegada"))
        partida = user.get("_partida_date") if "_partida_date" in user else self._date_part(user.get("data_partida"))

        for info in self._day_infos:
            data_str = info["data_str"]

            # Antes da chegada não conta. No próprio dia de chegada também não conta
            # para a Caixa, conforme o exemplo: chegada dia 12 num mês de 30 dias = 18 dias.
            if chegada and data_str <= chegada:
                continue

            # A data de partida conta para a Caixa, conforme o exemplo: partida dia 19 = 19 dias.
            if partida and data_str > partida:
                continue

            # Dias de férias não contam para a Caixa.
            if self.user_em_ferias_na_data(user, data_str):
                continue

            dias_caixa += 1

        # Se esteve o mês civil completo, recebe exatamente o Valor Caixa definido,
        # mesmo em meses com 28, 29 ou 31 dias. Nos restantes casos, aplica a
        # regra solicitada: Valor Caixa / 30 x dias contabilizados.
        if dias_caixa == self.dias_mes():
            return valor_caixa

        return int(round((valor_caixa / 30) * min(dias_caixa, 30)))

    def formatar_valor(self, valor):
        return f"{int(valor):,}".replace(",", ".")

    def calcular_dfac_welfare(self):
        cache_key = ("welfare", tuple(sorted(self.alteracoes_pendentes.items())))
        if self._dfac_cache and self._dfac_cache[0] == cache_key:
            return self._dfac_cache[1]

        almoco = 0
        jantar = 0
        for user in self.utilizadores:
            user_id = user["id"]
            for info in self._day_infos:
                data_str = info["data_str"]
                if self.user_tem_refeicao_na_data(user, data_str, "Almoço") and not self.user_em_ferias_na_refeicao(user, data_str, "Almoço") and not self.valor_efetivo(user_id, data_str, "Almoço"):
                    almoco += 1
                if self.user_tem_refeicao_na_data(user, data_str, "Jantar") and not self.user_em_ferias_na_refeicao(user, data_str, "Jantar") and not self.valor_efetivo(user_id, data_str, "Jantar"):
                    jantar += 1
        result = (almoco, jantar, almoco + jantar)
        self._dfac_cache = (cache_key, result)
        return result

    def calcular_dfac_pequeno_almoco(self):
        cache_key = ("pa", tuple(sorted(self.alteracoes_pendentes.items())))
        if self._dfac_cache and self._dfac_cache[0] == cache_key:
            return self._dfac_cache[1]

        total = 0
        for user in self.utilizadores:
            for info in self._day_infos:
                if self.valor_pequeno_almoco(user, info["data_str"]):
                    total += 1
        self._dfac_cache = (cache_key, total)
        return total

    def atualizar_footer_dfac(self):
        if not hasattr(self, "lbl_dfac"):
            return
        if self.modo == "pequeno_almoco":
            total = self.calcular_dfac_pequeno_almoco()
            texto = f"{t('dfac_breakfast')}: {total}"
        else:
            almoco, jantar, total = self.calcular_dfac_welfare()
            texto = f"{t('dfac_lunch')}: {almoco}   |   {t('dfac_dinner')}: {jantar}   |   {t('dfac_total')}: {total}"
        self.lbl_dfac.config(text=texto)

    def atualizar_larguras(self):
        dias = self.dias_mes()
        canvas_w = max(self.canvas.winfo_width(), 1)
        margem = 4
        if self.modo == "pequeno_almoco":
            summary_w = 0
            unidades_por_dia = 1
        else:
            summary_w = self.welfare_w + self.cohesion_w + self.reimbursement_w + self.caixa_w + self.reembolso_final_w + self.select_w
            unidades_por_dia = 2
        disponivel = canvas_w - self.ident_w - summary_w - margem
        if disponivel > 0:
            self.cell_w = max(14, int(disponivel / (dias * unidades_por_dia)))
        else:
            self.cell_w = 10

    def desenhar_grelha(self):
        if not hasattr(self, "canvas"):
            return
        if self.modo == "pequeno_almoco":
            self.desenhar_grelha_pequeno_almoco()
        else:
            self.desenhar_grelha_welfare()
        self.atualizar_footer_dfac()

    def desenhar_header_base(self, total_h, total_w, dias, unidades_por_dia=2):
        self.canvas.configure(scrollregion=(0, 0, total_w, total_h))
        self.canvas.create_rectangle(0, 0, self.ident_w, self.header_h1 + self.header_h2, fill=COR_PRINCIPAL, outline=COR_LINHA)
        self.canvas.create_text(12, (self.header_h1 + self.header_h2) / 2, text=t("identification"), anchor="w", fill="white", font=("Arial", 10, "bold"))

        dias_semana = weekdays_short()

        for dia in range(1, dias + 1):
            x = self.ident_w + (dia - 1) * unidades_por_dia * self.cell_w
            data_header = f"{self.ano_atual}-{self.mes_atual:02d}-{dia:02d}"
            weekday = calendar.weekday(self.ano_atual, self.mes_atual, dia)
            especial = weekday in [5, 6] or data_header in self.day_offs
            bg = COR_WEEKEND if especial else COR_BRANCO
            header_bg = COR_WEEKEND if especial else COR_PRINCIPAL
            header_fg = COR_PRINCIPAL if especial else "white"
            largura_dia = unidades_por_dia * self.cell_w

            if self.hover_dia_idx == dia:
                header_bg = "#9fc7cc" if especial else "#073b42"
                header_fg = COR_PRINCIPAL if especial else "white"

            self.canvas.create_rectangle(x, 0, x + largura_dia, self.header_h1, fill=header_bg, outline=COR_LINHA)
            self.canvas.create_text(x + largura_dia / 2, 9, text=str(dia), fill=header_fg, font=("Arial", 8, "bold"))
            self.canvas.create_text(x + largura_dia / 2, 21, text=dias_semana[weekday], fill=header_fg, font=("Arial", 5, "bold"))

            if self.modo == "pequeno_almoco":
                self.canvas.create_rectangle(x, self.header_h1, x + self.cell_w, self.header_h1 + self.header_h2, fill=bg, outline=COR_LINHA)
            else:
                for idx, letra in enumerate(["A", "J"]):
                    cx = x + idx * self.cell_w
                    self.canvas.create_rectangle(cx, self.header_h1, cx + self.cell_w, self.header_h1 + self.header_h2, fill=bg, outline=COR_LINHA)
                    self.canvas.create_text(cx + self.cell_w / 2, self.header_h1 + self.header_h2 / 2, text=letra, fill=COR_PRINCIPAL, font=("Arial", 7, "bold"))

    def desenhar_separadores_dias(self, dias, unidades_por_dia, y_final):
        """Desenha separadores verticais discretos entre dias.

        O separador deve agrupar as células do mesmo dia (A/J ou PA) mas
        não deve atravessar a linha de semanas, para manter cada semana como
        uma célula única no footer.
        """
        for dia in range(1, dias + 1):
            x_esq = self.ident_w + (dia - 1) * unidades_por_dia * self.cell_w
            x_dir = self.ident_w + dia * unidades_por_dia * self.cell_w
            for x in (x_esq, x_dir):
                self.canvas.create_line(
                    x,
                    0,
                    x,
                    y_final,
                    fill=COR_PRINCIPAL,
                    width=2
                )

    def desenhar_grelha_welfare(self):
        self.atualizar_larguras()
        self.canvas.delete("all")
        dias = self.dias_mes()
        dias_w = dias * 2 * self.cell_w
        resumo_x = self.ident_w + dias_w
        total_w = resumo_x + self.welfare_w + self.cohesion_w + self.reimbursement_w + self.caixa_w + self.reembolso_final_w + self.select_w
        # +3 linhas finais: totais DFAC por dia + soma dinâmica da seleção + botões/semana
        total_h = self.header_h1 + self.header_h2 + max(len(self.utilizadores) + 3, 3) * self.row_h
        self.desenhar_header_base(total_h, total_w, dias, unidades_por_dia=2)

        resumo_cols = [("Welfare", self.welfare_w), (t("cohesion"), self.cohesion_w), (t("reimbursement"), self.reimbursement_w), (t("caixa"), self.caixa_w), ("Reembolso Final", self.reembolso_final_w)]
        x = resumo_x
        for titulo, largura in resumo_cols:
            self.canvas.create_rectangle(x, 0, x + largura, self.header_h1 + self.header_h2, fill=COR_PRINCIPAL, outline=COR_LINHA)
            self.canvas.create_text(x + largura / 2, (self.header_h1 + self.header_h2) / 2, text=titulo, fill="white", font=("Arial", 8, "bold"))
            x += largura

        # Cabeçalho da coluna Selecionar com checkbox para marcar/desmarcar todos.
        tag_select_all = "select_hoto_all"
        todos_ids = {user.get("id") for user in self.utilizadores}
        todos_selecionados = bool(todos_ids) and todos_ids.issubset(self.hoto_selecionados)
        check_all = "☑" if todos_selecionados else "☐"
        self.canvas.create_rectangle(x, 0, x + self.select_w, self.header_h1 + self.header_h2, fill=COR_PRINCIPAL, outline=COR_LINHA, tags=(tag_select_all,))
        self.canvas.create_text(x + self.select_w / 2, 16, text=t("select"), fill="white", font=("Arial", 8, "bold"), tags=(tag_select_all,))
        self.canvas.create_text(x + self.select_w / 2, 39, text=check_all, fill="white", font=("Arial", 13, "bold"), tags=(tag_select_all,))
        x += self.select_w

        if not self.utilizadores:
            self.canvas.create_text(20, self.header_h1 + self.header_h2 + 20, text=t("no_active_users"), anchor="w", fill="#555555", font=("Arial", 11))
            return

        # Totais das refeições que serão tomadas no DFAC por dia/refeição.
        # Conta apenas utilizadores ativos nessa data e células SEM Welfare marcado.
        totais_dfac = {dia: {"Almoço": 0, "Jantar": 0} for dia in range(1, dias + 1)}

        for row_idx, user in enumerate(self.utilizadores):
            y = self.header_h1 + self.header_h2 + row_idx * self.row_h
            user_id = user["id"]
            fill_ident = self._cor_identificacao_user(user, row_idx)
            self.canvas.create_rectangle(0, y, self.ident_w, y + self.row_h, fill=fill_ident, outline=COR_LINHA)
            self.canvas.create_text(10, y + self.row_h / 2, text=self.identificacao(user), anchor="w", fill="#111111", font=("Arial", 9, "bold"))
            for info in self._day_infos:
                dia = info["dia"]
                data_str = info["data_str"]
                weekday = info["weekday"]
                fim_semana = info["fim_semana"]
                is_day_off = info["day_off"]
                ativo_data = self.user_ativo_na_data(user, data_str)
                base_dia = COR_WEEKEND if (fim_semana or is_day_off) else COR_BRANCO
                for idx, refeicao in enumerate(REFEICOES_WELFARE):
                    x = self.ident_w + (dia - 1) * 2 * self.cell_w + idx * self.cell_w
                    ativo_refeicao = self.user_tem_refeicao_na_data(user, data_str, refeicao)
                    ferias_refeicao = ativo_refeicao and self.user_em_ferias_na_refeicao(user, data_str, refeicao)
                    bg_base = base_dia
                    if not ativo_refeicao:
                        bg_base = COR_INATIVO
                    elif ferias_refeicao:
                        bg_base = COR_FERIAS
                    marcado = ativo_refeicao and not ferias_refeicao and self.valor_efetivo(user_id, data_str, refeicao)
                    if ativo_refeicao and not ferias_refeicao and not marcado:
                        totais_dfac[dia][refeicao] += 1
                    chave = (user_id, data_str, refeicao)
                    if chave in self.alteracoes_pendentes:
                        fill = COR_ALTERACAO
                    elif marcado:
                        fill = COR_VERMELHO
                    else:
                        # Hover apenas nas células normais, vazias e ativas.
                        # Não cobre fins de semana/Days Off nem células cinzentas de inatividade.
                        pode_hover = ativo_refeicao and not ferias_refeicao and not fim_semana and not is_day_off
                        fill = COR_HOVER if (self.hover_row_idx == row_idx and pode_hover) else bg_base
                    tag = f"cell|{user_id}|{data_str}|{refeicao}"
                    self.canvas.create_rectangle(x, y, x + self.cell_w, y + self.row_h, fill=fill, outline=COR_LINHA, tags=(tag,))
                    if ferias_refeicao:
                        self.canvas.create_text(
                            x + self.cell_w / 2,
                            y + self.row_h / 2,
                            text="F",
                            fill=COR_PRINCIPAL,
                            font=("Arial", 10, "bold"),
                            tags=(tag,)
                        )
            welfare, cohesion, reimbursement = self.calcular_resumo_user(user)
            caixa = self.calcular_caixa_user(user)
            reembolso_final = max(0, int(reimbursement or 0) - int(caixa or 0))
            x = resumo_x
            valores = [str(welfare), str(cohesion), self.formatar_valor(reimbursement), self.formatar_valor(caixa), self.formatar_valor(reembolso_final)]
            larguras = [self.welfare_w, self.cohesion_w, self.reimbursement_w, self.caixa_w, self.reembolso_final_w]
            linha_selecionada = user_id in self.hoto_selecionados
            for idx_resumo, (valor, largura) in enumerate(zip(valores, larguras)):
                # A coluna Reembolso Final só fica verde quando a linha está selecionada.
                # As restantes colunas mantêm o hover normal.
                if idx_resumo == 4 and linha_selecionada:
                    fill_resumo = COR_REEMBOLSO_FINAL_BG
                else:
                    fill_resumo = COR_HOVER if self.hover_row_idx == row_idx else COR_RESUMO
                self.canvas.create_rectangle(x, y, x + largura, y + self.row_h, fill=fill_resumo, outline=COR_LINHA)
                self.canvas.create_text(x + largura / 2, y + self.row_h / 2, text=valor, fill="#111111", font=("Arial", 9, "bold"))
                x += largura

            fill_sel = COR_HOVER if self.hover_row_idx == row_idx else COR_RESUMO
            tag_sel = f"select_hoto|{user_id}"
            self.canvas.create_rectangle(x, y, x + self.select_w, y + self.row_h, fill=fill_sel, outline=COR_LINHA, tags=(tag_sel,))
            check = "☑" if user_id in self.hoto_selecionados else "☐"
            self.canvas.create_text(x + self.select_w / 2, y + self.row_h / 2, text=check, fill=COR_PRINCIPAL, font=("Arial", 12, "bold"), tags=(tag_sel,))
            x += self.select_w

        # Linha final: refeições a consumir no DFAC por dia (A/J).
        y_total = self.header_h1 + self.header_h2 + len(self.utilizadores) * self.row_h
        self.canvas.create_rectangle(0, y_total, self.ident_w, y_total + self.row_h, fill=COR_TOTAL, outline=COR_LINHA)
        self.canvas.create_text(10, y_total + self.row_h / 2, text="TOTAL DFAC", anchor="w", fill=COR_PRINCIPAL, font=("Arial", 10, "bold"))

        for info in self._day_infos:
            dia = info["dia"]
            data_str = info["data_str"]
            weekday = info["weekday"]
            especial = info["especial"]
            bg_total = COR_WEEKEND if especial else COR_TOTAL
            for idx, refeicao in enumerate(REFEICOES_WELFARE):
                x = self.ident_w + (dia - 1) * 2 * self.cell_w + idx * self.cell_w
                self.canvas.create_rectangle(x, y_total, x + self.cell_w, y_total + self.row_h, fill=bg_total, outline=COR_LINHA)
                self.canvas.create_text(
                    x + self.cell_w / 2,
                    y_total + self.row_h / 2,
                    text=str(totais_dfac[dia][refeicao]),
                    fill=COR_PRINCIPAL,
                    font=("Arial", 10, "bold")
                )

        total_welfare = 0
        total_cohesion = 0
        total_reimbursement = 0
        total_caixa = 0
        total_reembolso_final = 0
        for user in self.utilizadores:
            w_total, c_total, r_total = self.calcular_resumo_user(user)
            total_welfare += w_total
            total_cohesion += c_total
            total_reimbursement += r_total
            caixa_user = self.calcular_caixa_user(user)
            total_caixa += caixa_user
            total_reembolso_final += max(0, int(r_total or 0) - int(caixa_user or 0))

        x = resumo_x
        resumo_footer = [
            (str(total_welfare), self.welfare_w),
            (str(total_cohesion), self.cohesion_w),
            (self.formatar_valor(total_reimbursement), self.reimbursement_w),
            (self.formatar_valor(total_caixa), self.caixa_w),
            (self.formatar_valor(total_reembolso_final), self.reembolso_final_w),
            ("", self.select_w),
        ]
        for valor, largura in resumo_footer:
            self.canvas.create_rectangle(x, y_total, x + largura, y_total + self.row_h, fill=COR_TOTAL, outline=COR_LINHA)
            if valor:
                self.canvas.create_text(
                    x + largura / 2,
                    y_total + self.row_h / 2,
                    text=valor,
                    fill=COR_PRINCIPAL,
                    font=("Arial", 10, "bold")
                )
            x += largura

        # Linha dinâmica: soma apenas das linhas selecionadas na coluna Selecionar.
        y_selecionado = y_total + self.row_h
        self.canvas.create_rectangle(0, y_selecionado, self.ident_w, y_selecionado + self.row_h, fill=COR_REEMBOLSO_FINAL_BG, outline=COR_LINHA)
        self.canvas.create_text(10, y_selecionado + self.row_h / 2, text="TOTAL SELECIONADO", anchor="w", fill=COR_PRINCIPAL, font=("Arial", 10, "bold"))

        # Mantém as colunas dos dias vazias nesta linha para não confundir com o TOTAL DFAC diário.
        for info in self._day_infos:
            dia = info["dia"]
            for idx in range(2):
                x_dia = self.ident_w + (dia - 1) * 2 * self.cell_w + idx * self.cell_w
                self.canvas.create_rectangle(x_dia, y_selecionado, x_dia + self.cell_w, y_selecionado + self.row_h, fill=COR_TOTAL, outline=COR_LINHA)

        sel_welfare = 0
        sel_cohesion = 0
        sel_reimbursement = 0
        sel_caixa = 0
        sel_reembolso_final = 0
        for user in self.utilizadores:
            if user.get("id") not in self.hoto_selecionados:
                continue
            w_total, c_total, r_total = self.calcular_resumo_user(user)
            caixa_user = self.calcular_caixa_user(user)
            sel_welfare += w_total
            sel_cohesion += c_total
            sel_reimbursement += r_total
            sel_caixa += caixa_user
            sel_reembolso_final += max(0, int(r_total or 0) - int(caixa_user or 0))

        x = resumo_x
        resumo_selecionado = [
            (str(sel_welfare), self.welfare_w),
            (str(sel_cohesion), self.cohesion_w),
            (self.formatar_valor(sel_reimbursement), self.reimbursement_w),
            (self.formatar_valor(sel_caixa), self.caixa_w),
            (self.formatar_valor(sel_reembolso_final), self.reembolso_final_w),
            ("", self.select_w),
        ]
        for valor, largura in resumo_selecionado:
            self.canvas.create_rectangle(x, y_selecionado, x + largura, y_selecionado + self.row_h, fill=COR_REEMBOLSO_FINAL_BG, outline=COR_LINHA)
            if valor:
                self.canvas.create_text(
                    x + largura / 2,
                    y_selecionado + self.row_h / 2,
                    text=valor,
                    fill=COR_PRINCIPAL,
                    font=("Arial", 10, "bold")
                )
            x += largura

        y_semana = y_selecionado + self.row_h
        self.desenhar_linha_semanas(
            y_semana=y_semana,
            dias=dias,
            unidades_por_dia=2,
            resumo_x=resumo_x,
            total_w=total_w
        )

        self.desenhar_separadores_dias(dias=dias, unidades_por_dia=2, y_final=y_semana)

    def desenhar_grelha_pequeno_almoco(self):
        self.atualizar_larguras()
        self.canvas.delete("all")
        dias = self.dias_mes()
        dias_w = dias * self.cell_w
        total_w = self.ident_w + dias_w
        total_h = self.header_h1 + self.header_h2 + (len(self.utilizadores) + 2) * self.row_h
        self.desenhar_header_base(total_h, total_w, dias, unidades_por_dia=1)

        if not self.utilizadores:
            self.canvas.create_text(20, self.header_h1 + self.header_h2 + 20, text=t("no_active_users"), anchor="w", fill="#555555", font=("Arial", 11))
            return

        totais_dia = {dia: 0 for dia in range(1, dias + 1)}
        for row_idx, user in enumerate(self.utilizadores):
            y = self.header_h1 + self.header_h2 + row_idx * self.row_h
            fill_ident = self._cor_identificacao_user(user, row_idx)
            self.canvas.create_rectangle(0, y, self.ident_w, y + self.row_h, fill=fill_ident, outline=COR_LINHA)
            self.canvas.create_text(10, y + self.row_h / 2, text=self.identificacao(user), anchor="w", fill="#111111", font=("Arial", 9, "bold"))
            for info in self._day_infos:
                dia = info["dia"]
                data_str = info["data_str"]
                weekday = info["weekday"]
                bg_base = COR_WEEKEND if info["especial"] else COR_BRANCO
                ferias_data = self.user_em_ferias_na_refeicao(user, data_str, REFEICAO_PEQUENO_ALMOCO)
                ativo = self.user_tem_pequeno_almoco_na_data(user, data_str)
                if not ativo:
                    bg_base = COR_FERIAS if ferias_data and self.user_ativo_na_data(user, data_str) else COR_INATIVO
                marcado = self.valor_pequeno_almoco(user, data_str)
                if marcado:
                    totais_dia[dia] += 1
                chave = (user["id"], data_str, REFEICAO_PEQUENO_ALMOCO)
                if chave in self.alteracoes_pendentes:
                    fill = COR_ALTERACAO
                elif not ativo:
                    fill = bg_base
                elif ferias_data:
                    fill = COR_FERIAS
                elif marcado:
                    # Vai ao DFAC
                    especial = info["especial"]
                    pode_hover = ativo and not ferias_data and not especial
                    fill = COR_HOVER if (self.hover_row_idx == row_idx and pode_hover) else bg_base
                else:
                    # Não vai ao DFAC
                    fill = COR_VERMELHO
                x = self.ident_w + (dia - 1) * self.cell_w
                self.canvas.create_rectangle(x, y, x + self.cell_w, y + self.row_h, fill=fill, outline=COR_LINHA)
                if ferias_data:
                    self.canvas.create_text(
                        x + self.cell_w / 2,
                        y + self.row_h / 2,
                        text="F",
                        fill=COR_PRINCIPAL,
                        font=("Arial", 10, "bold")
                    )

        y_total = self.header_h1 + self.header_h2 + len(self.utilizadores) * self.row_h
        self.canvas.create_rectangle(0, y_total, self.ident_w, y_total + self.row_h, fill=COR_TOTAL, outline=COR_LINHA)
        self.canvas.create_text(10, y_total + self.row_h / 2, text="TOTAL DFAC", anchor="w", fill=COR_PRINCIPAL, font=("Arial", 10, "bold"))
        for dia in range(1, dias + 1):
            x = self.ident_w + (dia - 1) * self.cell_w
            self.canvas.create_rectangle(x, y_total, x + self.cell_w, y_total + self.row_h, fill=COR_TOTAL, outline=COR_LINHA)
            self.canvas.create_text(x + self.cell_w / 2, y_total + self.row_h / 2, text=str(totais_dia[dia]), fill=COR_PRINCIPAL, font=("Arial", 10, "bold"))

        y_semana = y_total + self.row_h
        self.desenhar_linha_semanas(
            y_semana=y_semana,
            dias=dias,
            unidades_por_dia=1,
            resumo_x=None,
            total_w=total_w
        )

        self.desenhar_separadores_dias(dias=dias, unidades_por_dia=1, y_final=y_semana)

    def _semana_click_tag(self):
        item_atual = self.canvas.find_withtag("current")
        for item in item_atual:
            for tag in self.canvas.gettags(item):
                if tag.startswith("week|"):
                    partes = tag.split("|")
                    if len(partes) >= 3:
                        return partes[1], int(partes[2])
        return None, None

    def _select_hoto_all_click_tag(self):
        item_atual = self.canvas.find_withtag("current")
        for item in item_atual:
            if "select_hoto_all" in self.canvas.gettags(item):
                return True
        return False

    def _select_hoto_click_tag(self):
        item_atual = self.canvas.find_withtag("current")
        for item in item_atual:
            for tag in self.canvas.gettags(item):
                if tag.startswith("select_hoto|"):
                    partes = tag.split("|")
                    if len(partes) == 2:
                        try:
                            return int(partes[1])
                        except ValueError:
                            return None
        return None

    def alternar_selecao_hoto_todos(self):
        ids_visiveis = {user.get("id") for user in self.utilizadores if user.get("id") is not None}
        if not ids_visiveis:
            return

        if ids_visiveis.issubset(self.hoto_selecionados):
            self.hoto_selecionados.difference_update(ids_visiveis)
        else:
            self.hoto_selecionados.update(ids_visiveis)

        self.desenhar_grelha()


    def _dados_para_pdf_welfare_individual(self):
        dias_total = self.dias_mes()
        dias = []
        for dia in range(1, dias_total + 1):
            data_str = f"{self.ano_atual}-{self.mes_atual:02d}-{dia:02d}"
            weekday = calendar.weekday(self.ano_atual, self.mes_atual, dia)
            dias.append({
                "dia": dia,
                "data_str": data_str,
                "weekday": weekdays_short()[weekday],
                "especial": weekday in [5, 6] or data_str in self.day_offs,
            })

        rows = []
        totais_dfac = {dia: {"pa": 0, "al": 0, "ja": 0} for dia in range(1, dias_total + 1)}

        for user in self.utilizadores:
            row_cells = {}
            for dia_info in dias:
                dia = dia_info["dia"]
                data_str = dia_info["data_str"]
                especial = bool(dia_info["especial"])
                ferias_pa = self.user_em_ferias_na_refeicao(user, data_str, REFEICAO_PEQUENO_ALMOCO)
                ativo_pa = self.user_tem_pequeno_almoco_na_data(user, data_str)
                base = COR_WEEKEND if especial else COR_BRANCO

                # Pequeno-almoço
                if ferias_pa and self.user_ativo_na_data(user, data_str):
                    pa_fill = COR_FERIAS
                    pa_text = "F"
                elif not ativo_pa:
                    pa_fill = COR_INATIVO
                    pa_text = ""
                elif self.valor_pequeno_almoco(user, data_str):
                    # No PDF: se vai tomar pequeno-almoço no DFAC fica branco;
                    # se não vai, fica vermelho como os Welfares marcados.
                    pa_fill = base
                    pa_text = ""
                    totais_dfac[dia]["pa"] += 1
                else:
                    pa_fill = COR_VERMELHO
                    pa_text = ""

                row_cells[dia] = {
                    "pa": {"fill": pa_fill, "text": pa_text},
                }

                for key, refeicao in (("al", "Almoço"), ("ja", "Jantar")):
                    ativo_refeicao = self.user_tem_refeicao_na_data(user, data_str, refeicao)
                    ferias_refeicao = ativo_refeicao and self.user_em_ferias_na_refeicao(user, data_str, refeicao)
                    if ferias_refeicao:
                        fill = COR_FERIAS
                        text = "F"
                    elif not ativo_refeicao:
                        fill = COR_INATIVO
                        text = ""
                    else:
                        marcado = self.valor_efetivo(user["id"], data_str, refeicao)
                        if marcado:
                            fill = COR_VERMELHO
                            text = ""
                        else:
                            fill = base
                            text = ""
                            totais_dfac[dia][key] += 1

                    row_cells[dia][key] = {"fill": fill, "text": text}

            w_total, c_total, r_total = self.calcular_resumo_user(user)
            rows.append({
                "identificacao": self.identificacao(user),
                "cells": row_cells,
                "welfare_total": w_total,
                "cohesion_total": c_total,
                "reimbursement": r_total,
            })

        return dias, rows, totais_dfac

    def escolher_modo_impressao(self):
        """Pergunta se a impressão deve sair numa página ou em duas páginas."""
        escolha = {"valor": None}

        popup = tk.Toplevel(self.janela)
        aplicar_icone(popup)
        popup.title("Impressão")
        popup.geometry("420x190")
        popup.resizable(False, False)
        popup.configure(bg="white")
        popup.transient(self.janela)
        popup.grab_set()

        try:
            popup.update_idletasks()
            sw = popup.winfo_screenwidth()
            sh = popup.winfo_screenheight()
            ww = 420
            wh = 190
            popup.geometry(f"{ww}x{wh}+{int((sw - ww) / 2)}+{int((sh - wh) / 2)}")
        except Exception:
            pass

        tk.Label(
            popup,
            text="Escolhe o formato da impressão",
            bg="white",
            fg=COR_PRINCIPAL,
            font=("Arial", 13, "bold")
        ).pack(pady=(22, 6))

        tk.Label(
            popup,
            text="1 página: mais compacto. 2 páginas: maior e mais legível.",
            bg="white",
            fg="#444",
            font=("Arial", 9)
        ).pack(pady=(0, 18))

        botoes = tk.Frame(popup, bg="white")
        botoes.pack()

        def escolher(valor):
            escolha["valor"] = valor
            popup.destroy()

        tk.Button(
            botoes,
            text="1 Página",
            bg=COR_PRINCIPAL,
            fg="white",
            activebackground=COR_PRINCIPAL,
            activeforeground="white",
            relief="flat",
            width=13,
            font=("Arial", 10, "bold"),
            command=lambda: escolher(1)
        ).pack(side="left", padx=8)

        tk.Button(
            botoes,
            text="2 Páginas",
            bg=COR_PRINCIPAL,
            fg="white",
            activebackground=COR_PRINCIPAL,
            activeforeground="white",
            relief="flat",
            width=13,
            font=("Arial", 10, "bold"),
            command=lambda: escolher(2)
        ).pack(side="left", padx=8)

        tk.Button(
            botoes,
            text="Cancelar",
            bg="#777",
            fg="white",
            activebackground="#777",
            activeforeground="white",
            relief="flat",
            width=13,
            font=("Arial", 10, "bold"),
            command=lambda: escolher(None)
        ).pack(side="left", padx=8)

        popup.wait_window()
        self.janela.lift()
        self.janela.focus_force()
        return escolha["valor"]


    def imprimir_tabela(self):
        if self.alteracoes_pendentes:
            messagebox.showwarning(
                t("validation"),
                "Existem alterações pendentes. Grava ou anula as alterações antes de imprimir.",
                parent=self.janela
            )
            self.janela.lift()
            self.janela.focus_force()
            return

        modo_paginas = self.escolher_modo_impressao()
        if not modo_paginas:
            return

        nome = f"Welfare_Individual_{self.ano_atual}_{self.mes_atual:02d}.pdf"
        caminho = filedialog.asksaveasfilename(
            parent=self.janela,
            title=t("save_as"),
            initialfile=nome,
            defaultextension=".pdf",
            filetypes=[(t("pdf_files"), "*.pdf"), ("PDF", "*.pdf")]
        )
        if not caminho:
            self.janela.lift()
            self.janela.focus_force()
            return

        dias, rows, totais_dfac = self._dados_para_pdf_welfare_individual()
        periodo = f"{months()[self.mes_atual]} {self.ano_atual}"
        gerar_pdf_welfare_individual(
            caminho_pdf=caminho,
            titulo="Contingente Português - Welfares/Marcações Individuais",
            periodo=periodo,
            dias=dias,
            rows=rows,
            totais_dfac=totais_dfac,
            day_offs=self.day_offs,
            modo_paginas=modo_paginas,
        )

        messagebox.showinfo(t("saved"), t("pdf_saved"), parent=self.janela)
        self.janela.lift()
        self.janela.focus_force()


    def _ctx_mes_export(self, ano, mes):
        """Carrega em memória o contexto de qualquer mês para exportações semanais completas."""
        if not hasattr(self, "_ctx_meses_export"):
            self._ctx_meses_export = {}

        chave_mes = (int(ano), int(mes))
        if chave_mes in self._ctx_meses_export:
            return self._ctx_meses_export[chave_mes]

        mensais = get_welfares_mes(ano, mes)
        individuais = get_welfares_individuais_mes(ano, mes)
        day_offs = get_day_offs_mes(ano, mes)
        ferias_raw = get_ferias_mes(ano, mes)

        ferias_intervalos = {}
        for user_id, periodos in (ferias_raw or {}).items():
            lista = []
            for periodo in periodos:
                inicio = self._parse_dt_ferias(periodo.get("data_hora_inicio"), "00:00")
                fim = self._parse_dt_ferias(periodo.get("data_hora_fim"), "23:59")
                if inicio and fim:
                    lista.append((inicio, fim))
            ferias_intervalos[user_id] = lista

        ctx = {
            "mensais_set": {
                (data_str, welfare.get("refeicao"))
                for data_str, lista in (mensais or {}).items()
                for welfare in lista
            },
            "individuais": individuais or {},
            "day_offs": day_offs or set(),
            "ferias_intervalos": ferias_intervalos,
        }
        self._ctx_meses_export[chave_mes] = ctx
        return ctx

    def _ctx_para_data(self, data_ref):
        if data_ref.year == self.ano_atual and data_ref.month == self.mes_atual:
            return {
                "mensais_set": self._mensais_set,
                "individuais": self.individuais,
                "day_offs": self.day_offs,
                "ferias_intervalos": self._ferias_intervalos,
            }
        return self._ctx_mes_export(data_ref.year, data_ref.month)

    def _user_em_ferias_na_data_ctx(self, user, data_str, ctx):
        user_id = user.get("id")
        for inicio, fim in ctx.get("ferias_intervalos", {}).get(user_id, []):
            inicio_data = inicio.date().isoformat()
            fim_data = fim.date().isoformat()
            if inicio_data <= data_str <= fim_data:
                return True
        return False

    def _user_em_ferias_na_refeicao_ctx(self, user, data_str, refeicao, ctx):
        user_id = user.get("id")
        for inicio, fim in ctx.get("ferias_intervalos", {}).get(user_id, []):
            inicio_data = inicio.date().isoformat()
            fim_data = fim.date().isoformat()
            if data_str < inicio_data or data_str > fim_data:
                continue

            inicio_min = self._to_minutes(inicio.strftime("%H:%M"))
            fim_min = self._to_minutes(fim.strftime("%H:%M"))

            if inicio_data == fim_data == data_str:
                return self._intervalo_apanha_refeicao(data_str, inicio_min, fim_min, refeicao, ctx)

            if data_str == inicio_data:
                return not self._tem_refeicao_por_partida(data_str, inicio_min, refeicao, ctx)

            if data_str == fim_data:
                return not self._tem_refeicao_por_chegada(data_str, fim_min, refeicao, ctx)

            return True
        return False

    def _user_tem_pequeno_almoco_em_ferias_na_data_ctx(self, user, data_str, ctx):
        return not self._user_em_ferias_na_refeicao_ctx(user, data_str, REFEICAO_PEQUENO_ALMOCO, ctx)

    def _user_tem_pequeno_almoco_na_data_ctx(self, user, data_str, ctx):
        if not self._user_tem_refeicao_na_data_ctx(user, data_str, REFEICAO_PEQUENO_ALMOCO, ctx):
            return False
        if not self._user_tem_pequeno_almoco_em_ferias_na_data_ctx(user, data_str, ctx):
            return False
        return True

    def _user_tem_refeicao_na_data_ctx(self, user, data_str, refeicao, ctx):
        chegada = user.get("_chegada_date") if "_chegada_date" in user else self._date_part(user.get("data_chegada"))
        partida = user.get("_partida_date") if "_partida_date" in user else self._date_part(user.get("data_partida"))

        if chegada and data_str < chegada:
            return False
        if partida and data_str > partida:
            return False

        if chegada and data_str == chegada:
            chegada_min = int(user.get("_chegada_min", 0) or 0)
            if not self._tem_refeicao_por_chegada(data_str, chegada_min, refeicao, ctx):
                return False

        if partida and data_str == partida:
            partida_min = int(user.get("_partida_min", 0) or 0)
            if not self._tem_refeicao_por_partida(data_str, partida_min, refeicao, ctx):
                return False

        return True

    def _valor_efetivo_ctx(self, utilizador_id, data_str, refeicao, ctx):
        chave = (utilizador_id, data_str, refeicao)
        if chave in self.alteracoes_pendentes:
            return bool(self.alteracoes_pendentes[chave])
        if chave in ctx.get("individuais", {}):
            return bool(ctx["individuais"][chave])
        return (data_str, refeicao) in ctx.get("mensais_set", set())

    def _valor_pequeno_almoco_ctx(self, user, data_str, ctx):
        if not self._user_tem_pequeno_almoco_na_data_ctx(user, data_str, ctx):
            return False
        chave = (user["id"], data_str, REFEICAO_PEQUENO_ALMOCO)
        if chave in self.alteracoes_pendentes:
            return bool(self.alteracoes_pendentes[chave])
        if chave in ctx.get("individuais", {}):
            return bool(ctx["individuais"][chave])
        return True

    def _totais_semana_para_export(self, inicio_semana):
        totais = []
        for offset in range(7):
            data_ref = inicio_semana + timedelta(days=offset)
            data_str = data_ref.isoformat()
            ctx = self._ctx_para_data(data_ref)
            pequeno_almoco = 0
            almoco_dfac = 0
            jantar_dfac = 0

            for user in self.utilizadores:
                if self._valor_pequeno_almoco_ctx(user, data_str, ctx):
                    pequeno_almoco += 1

                user_id = user["id"]
                if self._user_tem_refeicao_na_data_ctx(user, data_str, "Almoço", ctx) and not self._user_em_ferias_na_refeicao_ctx(user, data_str, "Almoço", ctx) and not self._valor_efetivo_ctx(user_id, data_str, "Almoço", ctx):
                    almoco_dfac += 1
                if self._user_tem_refeicao_na_data_ctx(user, data_str, "Jantar", ctx) and not self._user_em_ferias_na_refeicao_ctx(user, data_str, "Jantar", ctx) and not self._valor_efetivo_ctx(user_id, data_str, "Jantar", ctx):
                    jantar_dfac += 1

            totais.append({
                "data": data_ref,
                "pequeno_almoco": pequeno_almoco,
                "almoco": almoco_dfac,
                "jantar": jantar_dfac,
            })
        return totais

    def exportar_semana(self, inicio_semana_str, numero_semana):
        try:
            inicio_semana = datetime.strptime(inicio_semana_str, "%Y-%m-%d").date()
        except ValueError:
            messagebox.showerror(t("error"), t("date_format"), parent=self.janela)
            self.janela.lift()
            self.janela.focus_force()
            return

        totais = self._totais_semana_para_export(inicio_semana)
        nome = f"W{numero_semana}-{inicio_semana.year} PT CN.xlsx"
        destino = filedialog.asksaveasfilename(
            parent=self.janela,
            title=t("save_as"),
            initialfile=nome,
            defaultextension=".xlsx",
            filetypes=[("Excel", "*.xlsx")],
        )
        if not destino:
            self.janela.lift()
            self.janela.focus_force()
            return

        try:
            gerar_meals_request_weekly(DOCS_DIR, destino, totais, numero_semana)
        except Exception as exc:
            messagebox.showerror(t("error"), str(exc), parent=self.janela)
            self.janela.lift()
            self.janela.focus_force()
            return

        messagebox.showinfo(t("saved"), destino, parent=self.janela)
        self.janela.lift()
        self.janela.focus_force()

    def mostrar_menu_semana(self, event, inicio_semana_str, numero_semana):
        """Mostra uma pequena dropdown com ações para a semana clicada."""
        menu = tk.Menu(self.janela, tearoff=0)
        menu.add_command(
            label="Exportar Excel",
            command=lambda: self.exportar_semana(inicio_semana_str, numero_semana)
        )
        menu.add_command(
            label="Imprimir Semana",
            command=lambda: self.imprimir_semana(inicio_semana_str, numero_semana)
        )
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _dias_semana_para_pdf(self, inicio_semana):
        """Devolve sempre os 7 dias completos da semana clicada."""
        dias_semana = []
        for offset in range(7):
            data_ref = inicio_semana + timedelta(days=offset)
            data_str = data_ref.isoformat()
            ctx = self._ctx_para_data(data_ref)
            weekday = calendar.weekday(data_ref.year, data_ref.month, data_ref.day)
            dias_semana.append({
                "dia": data_ref.day,
                "data_str": data_str,
                "weekday": weekdays_short()[weekday],
                "especial": weekday in [5, 6] or data_str in ctx.get("day_offs", set()),
            })
        return dias_semana

    def _dados_para_pdf_semana_completa(self, inicio_semana):
        dias = self._dias_semana_para_pdf(inicio_semana)
        totais_dfac = {dia_info["data_str"]: {"pa": 0, "al": 0, "ja": 0} for dia_info in dias}
        rows = []

        for user in self.utilizadores:
            row_cells = {}
            for dia_info in dias:
                data_str = dia_info["data_str"]
                ctx = self._ctx_para_data(datetime.strptime(data_str, "%Y-%m-%d").date())
                especial = bool(dia_info["especial"])
                ferias_pa = self._user_em_ferias_na_refeicao_ctx(user, data_str, REFEICAO_PEQUENO_ALMOCO, ctx)
                ativo_pa = self._user_tem_pequeno_almoco_na_data_ctx(user, data_str, ctx)
                base = COR_WEEKEND if especial else COR_BRANCO

                if ferias_pa and self.user_ativo_na_data(user, data_str):
                    pa_fill = COR_FERIAS
                    pa_text = "F"
                elif not ativo_pa:
                    pa_fill = COR_INATIVO
                    pa_text = ""
                elif self._valor_pequeno_almoco_ctx(user, data_str, ctx):
                    pa_fill = base
                    pa_text = ""
                    totais_dfac[data_str]["pa"] += 1
                else:
                    pa_fill = COR_VERMELHO
                    pa_text = ""

                row_cells[data_str] = {"pa": {"fill": pa_fill, "text": pa_text}}

                for key, refeicao in (("al", "Almoço"), ("ja", "Jantar")):
                    ativo_refeicao = self._user_tem_refeicao_na_data_ctx(user, data_str, refeicao, ctx)
                    ferias_refeicao = ativo_refeicao and self._user_em_ferias_na_refeicao_ctx(user, data_str, refeicao, ctx)
                    if ferias_refeicao:
                        fill = COR_FERIAS
                        text = "F"
                    elif not ativo_refeicao:
                        fill = COR_INATIVO
                        text = ""
                    else:
                        marcado = self._valor_efetivo_ctx(user["id"], data_str, refeicao, ctx)
                        if marcado:
                            fill = COR_VERMELHO
                            text = ""
                        else:
                            fill = base
                            text = ""
                            totais_dfac[data_str][key] += 1
                    row_cells[data_str][key] = {"fill": fill, "text": text}

            w_total, c_total, r_total = self.calcular_resumo_user(user)
            rows.append({
                "identificacao": self.identificacao(user),
                "cells": row_cells,
                "welfare_total": w_total,
                "cohesion_total": c_total,
                "reimbursement": r_total,
            })

        return dias, rows, totais_dfac

    def imprimir_semana(self, inicio_semana_str, numero_semana):
        try:
            inicio_semana = datetime.strptime(inicio_semana_str, "%Y-%m-%d").date()
        except ValueError:
            messagebox.showerror(t("error"), t("date_format"), parent=self.janela)
            self.janela.lift()
            self.janela.focus_force()
            return

        dias_semana, rows_semana, totais_dfac_semana = self._dados_para_pdf_semana_completa(inicio_semana)

        nome = f"W{numero_semana}-{inicio_semana.year}_Welfare_Individual.pdf"
        caminho = filedialog.asksaveasfilename(
            parent=self.janela,
            title=t("save_as"),
            initialfile=nome,
            defaultextension=".pdf",
            filetypes=[(t("pdf_files"), "*.pdf"), ("PDF", "*.pdf")]
        )
        if not caminho:
            self.janela.lift()
            self.janela.focus_force()
            return

        periodo = f"{self.prefixo_semana()}{numero_semana} - {inicio_semana.year}"
        try:
            gerar_pdf_welfare_individual(
                caminho_pdf=caminho,
                titulo="Contingente Português - Welfares/Marcações Individuais",
                periodo=periodo,
                dias=dias_semana,
                rows=rows_semana,
                totais_dfac=totais_dfac_semana,
                day_offs=set().union(*(self._ctx_para_data(datetime.strptime(d["data_str"], "%Y-%m-%d").date()).get("day_offs", set()) for d in dias_semana)),
                modo_paginas=1,
            )
        except Exception as exc:
            messagebox.showerror(t("error"), str(exc), parent=self.janela)
            self.janela.lift()
            self.janela.focus_force()
            return

        messagebox.showinfo(t("saved"), t("pdf_saved"), parent=self.janela)
        self.janela.lift()
        self.janela.focus_force()

    def _date_in_mes_export(self, valor):
        valor = (valor or "").strip()
        if not valor:
            return False
        try:
            data = datetime.strptime(valor[:10], "%Y-%m-%d").date()
        except ValueError:
            return False
        return data.year == self.ano_atual and data.month == self.mes_atual

    def _cor_identificacao_user(self, user, row_idx):
        if self._date_in_mes_export(user.get("data_partida")):
            return COR_PARTIDA
        if self._date_in_mes_export(user.get("data_chegada")):
            return COR_CHEGADA
        return "#f7f7f7" if row_idx % 2 == 0 else "white"

    def _row_hover_bg(self, row_idx, cor_original):
        if self.hover_row_idx == row_idx:
            return COR_HOVER
        return cor_original

    def on_canvas_motion(self, event):
        x = self.canvas.canvasx(event.x)
        y = self.canvas.canvasy(event.y)

        row_idx = int((y - self.header_h1 - self.header_h2) // self.row_h)
        novo_row = row_idx if 0 <= row_idx < len(self.utilizadores) else None

        unidades_por_dia = 1 if self.modo == "pequeno_almoco" else 2
        if x >= self.ident_w:
            dia_idx = int((x - self.ident_w) // (unidades_por_dia * self.cell_w)) + 1
            novo_dia = dia_idx if 1 <= dia_idx <= self.dias_mes() else None
        else:
            novo_dia = None

        if novo_row != self.hover_row_idx or novo_dia != self.hover_dia_idx:
            self.hover_row_idx = novo_row
            self.hover_dia_idx = novo_dia
            self._agendar_redesenho(delay=35)

    def on_canvas_leave(self, event):
        if self.hover_row_idx is not None or self.hover_dia_idx is not None:
            self.hover_row_idx = None
            self.hover_dia_idx = None
            self._agendar_redesenho(delay=35)

    def abrir_distribuicao_xfa(self):
        if self.app.trazer_janela_tipo("distribuicao_xfa"):
            return

        if not getattr(self, "hoto_selecionados", set()):
            messagebox.showwarning(
                "Validação",
                "Selecione pelo menos uma pessoa para efetuar a Distribuição XFA.",
                parent=self.janela
            )
            self.janela.lift()
            self.janela.focus_force()
            return

        XfaDistributionWindow(self)


    def _dados_service_note(self):
        """Prepara dados para a Service Note.

        Exclui militares com data de partida no mês da Service Note.
        Para cada militar incluído, recolhe as datas de Coesão: Welfares
        marcados em dias normais, ou seja, que não são fim de semana nem Day Off.
        Se no mesmo dia houver Almoço e Jantar marcados, a data aparece apenas uma vez.
        """
        pessoas = []

        for user in self.utilizadores:
            if self._date_in_mes_export(user.get("data_partida")):
                continue

            datas = []
            for dia in range(1, self.dias_mes() + 1):
                data_str = f"{self.ano_atual}-{self.mes_atual:02d}-{dia:02d}"
                if self.is_fim_semana_ou_day_off(data_str):
                    continue

                tem_coesao = False
                for refeicao in REFEICOES_WELFARE:
                    if self.user_tem_refeicao_na_data(user, data_str, refeicao) and not self.user_em_ferias_na_refeicao(user, data_str, refeicao) and self.valor_efetivo(user["id"], data_str, refeicao):
                        tem_coesao = True
                        break

                if tem_coesao:
                    datas.append(data_str)

            pessoas.append({
                "user": user,
                "datas": tuple(datas),
            })

        conjuntos = {}
        for item in pessoas:
            if not item["datas"]:
                continue
            conjuntos[item["datas"]] = conjuntos.get(item["datas"], 0) + 1

        if conjuntos:
            datas_comuns = sorted(
                conjuntos.items(),
                key=lambda kv: (-kv[1], -len(kv[0]), kv[0])
            )[0][0]
        else:
            datas_comuns = tuple()

        dates_cohesion = "; ".join(
            formatar_data_militar(datetime.strptime(data_str, "%Y-%m-%d").date())
            for data_str in datas_comuns
        )

        linhas_individuais = []
        for item in pessoas:
            datas = item["datas"]
            if not datas or datas == datas_comuns:
                continue

            user = item["user"]
            posto = (user.get("posto") or "").strip()
            sobrenome = (user.get("sobrenome") or "").strip().upper()
            datas_txt = "; ".join(
                formatar_data_militar(datetime.strptime(data_str, "%Y-%m-%d").date())
                for data_str in datas
            )
            linhas_individuais.append(f"{posto} {sobrenome} ({datas_txt});".strip())

        individual_cohesion = "\n".join(linhas_individuais)
        return dates_cohesion, individual_cohesion


    def _identificacao_posto_nome_sobrenome(self, user):
        if not user:
            return ""
        posto = (user.get("posto") or "").strip()
        nome = (user.get("nome") or "").strip().upper()
        sobrenome = (user.get("sobrenome") or "").strip().upper()
        return f"{posto} {nome} {sobrenome}".strip()

    def _formatar_valor_espacos(self, valor):
        try:
            return f"{int(valor):,}".replace(",", " ")
        except Exception:
            return "0"

    def _totais_request_para_export(self):
        linhas = self._dados_reembolso_para_export(hoto=False)
        total_reimb = sum(int(l.get("reimbursement") or 0) for l in linhas)
        valor = self.valor_welfare_numero()
        total_meals = int(total_reimb / valor) if valor else 0
        return total_reimb, total_meals

    def exportar_request(self):
        if self.alteracoes_pendentes:
            confirmar = messagebox.askyesno(
                t("pending_changes_title"),
                t("pending_changes_question"),
                parent=self.janela
            )
            if confirmar:
                self.confirmar_alteracoes_pendentes()
            else:
                self.janela.lift()
                self.janela.focus_force()
                return

        hoje = date.today()
        nome = f"_{self.mes_atual:02d}_{str(self.ano_atual)[-2:]}_Request Welfare meals.docx"

        messagebox.showwarning(t("request"), t("request_alert"), parent=self.janela)
        self.janela.lift()
        self.janela.focus_force()

        destino = filedialog.asksaveasfilename(
            parent=self.janela,
            title=t("save_as"),
            initialfile=nome,
            defaultextension=".docx",
            filetypes=[("Word", "*.docx")],
        )
        if not destino:
            self.janela.lift()
            self.janela.focus_force()
            return

        responsavel = get_responsavel_welfare_mais_antigo_ativo()
        senior = get_snr_unico_para_assinatura()
        total_reimb, total_meals = self._totais_request_para_export()

        try:
            gerar_request_welfare_meals(
                docs_dir=DOCS_DIR,
                destino=destino,
                ano=self.ano_atual,
                mes=self.mes_atual,
                responsavel_welfare=self._identificacao_posto_nome_sobrenome(responsavel),
                telefone_servico=(responsavel.get("telemovel_servico") if responsavel else "") or "",
                total_reimb=self._formatar_valor_espacos(total_reimb),
                total_meals=total_meals,
                senior_prt=self._identificacao_posto_nome_sobrenome(senior),
            )
        except FileNotFoundError:
            messagebox.showerror(t("error"), t("request_template_missing"), parent=self.janela)
            self.janela.lift()
            self.janela.focus_force()
            return
        except Exception as exc:
            messagebox.showerror(t("error"), str(exc), parent=self.janela)
            self.janela.lift()
            self.janela.focus_force()
            return

        messagebox.showinfo(t("saved"), t("request_saved") + f"\n{destino}", parent=self.janela)
        self.janela.lift()
        self.janela.focus_force()

    def _user_por_id(self, user_id):
        for user in self.utilizadores:
            if int(user.get("id")) == int(user_id):
                return user
        return None

    def _data_partida_para_comparar(self, user):
        return (user.get("data_partida") or "").strip()

    def _data_partida_hoto_formatada(self, user):
        raw = self._data_partida_para_comparar(user)
        if not raw:
            return ""
        data_txt = raw[:10]
        try:
            data_obj = datetime.strptime(data_txt, "%Y-%m-%d").date()
            return formatar_data_militar(data_obj)
        except Exception:
            return data_txt

    def _data_partida_hoto_excel(self, user):
        raw = self._data_partida_para_comparar(user)
        if not raw:
            return ""
        try:
            data_obj = datetime.strptime(raw[:10], "%Y-%m-%d").date()
            return data_obj.strftime("%d.%m.%Y")
        except Exception:
            return raw[:10]

    def _mostrar_erro_datas_hoto(self, selecionados):
        dlg = tk.Toplevel(self.janela)
        aplicar_icone(dlg)
        dlg.title(t("hoto_dates_error_title"))
        dlg.geometry("620x360")
        dlg.configure(bg="white")
        dlg.transient(self.janela)
        dlg.grab_set()

        tk.Label(
            dlg,
            text=t("hoto_dates_error"),
            bg="white",
            fg="#111111",
            font=("Arial", 11, "bold"),
            wraplength=560,
            justify="center"
        ).pack(padx=20, pady=(18, 12))

        cols = ("ident", "partida")
        tabela = ttk.Treeview(dlg, columns=cols, show="headings", height=8)
        tabela.heading("ident", text=t("identification"))
        tabela.heading("partida", text=t("departure_datetime"))
        tabela.column("ident", width=300, anchor="center")
        tabela.column("partida", width=220, anchor="center")
        tabela.pack(fill="both", expand=True, padx=20, pady=(0, 12))

        for user in selecionados:
            tabela.insert("", "end", values=(self.identificacao_curta(user), self._data_partida_para_comparar(user)))

        tk.Button(
            dlg,
            text="OK",
            bg=COR_PRINCIPAL,
            fg="white",
            font=("Arial", 10, "bold"),
            relief="flat",
            width=12,
            command=dlg.destroy
        ).pack(pady=(0, 14))

        dlg.wait_window()
        self.janela.lift()
        self.janela.focus_force()

    def identificacao_curta(self, user):
        posto = (user.get("posto") or "").strip()
        sobrenome = (user.get("sobrenome") or "").strip().upper()
        return f"{posto} {sobrenome}".strip()

    def exportar_request_hoto(self):
        if not self.hoto_selecionados:
            messagebox.showwarning(t("validation"), t("select_hoto_people"), parent=self.janela)
            self.janela.lift()
            self.janela.focus_force()
            return

        selecionados = [
            user
            for user in self.utilizadores
            if int(user.get("id")) in self.hoto_selecionados
        ]
        partidas = {self._data_partida_para_comparar(user) for user in selecionados}
        if len(partidas) != 1:
            self._mostrar_erro_datas_hoto(selecionados)
            return

        if self.alteracoes_pendentes:
            confirmar = messagebox.askyesno(
                t("pending_changes_title"),
                t("pending_changes_question"),
                parent=self.janela
            )
            if confirmar:
                self.confirmar_alteracoes_pendentes()
            else:
                self.janela.lift()
                self.janela.focus_force()
                return

        hoje = date.today()
        nome = f"_{self.mes_atual:02d}_{str(self.ano_atual)[-2:]}_Request Welfare meals HOTO.docx"

        messagebox.showwarning(t("request_hoto"), t("request_alert"), parent=self.janela)
        self.janela.lift()
        self.janela.focus_force()

        destino = filedialog.asksaveasfilename(
            parent=self.janela,
            title=t("save_as"),
            initialfile=nome,
            defaultextension=".docx",
            filetypes=[("Word", "*.docx")],
        )
        if not destino:
            self.janela.lift()
            self.janela.focus_force()
            return

        responsavel = get_responsavel_welfare_mais_antigo_ativo()
        senior = get_snr_unico_para_assinatura()
        total_reimb = 0
        total_meals = 0
        for user in selecionados:
            welfare, cohesion, reimbursement = self.calcular_resumo_user(user)
            total_reimb += int(reimbursement or 0)
            valor = self.valor_welfare_numero()
            total_meals += int((reimbursement or 0) / valor) if valor else 0
        pessoas_hoto = "; ".join(self.identificacao_curta(user) for user in selecionados) + ";"
        data_partida_hoto = self._data_partida_hoto_formatada(selecionados[0]) if selecionados else ""

        try:
            gerar_request_welfare_meals_hoto(
                docs_dir=DOCS_DIR,
                destino=destino,
                ano=self.ano_atual,
                mes=self.mes_atual,
                responsavel_welfare=self._identificacao_posto_nome_sobrenome(responsavel),
                telefone_servico=(responsavel.get("telemovel_servico") if responsavel else "") or "",
                total_reimb=self._formatar_valor_espacos(total_reimb),
                total_meals=total_meals,
                senior_prt=self._identificacao_posto_nome_sobrenome(senior),
                pessoas_hoto=pessoas_hoto,
                data_inicio_override=data_partida_hoto,
            )
        except FileNotFoundError:
            messagebox.showerror(t("error"), t("request_hoto_template_missing"), parent=self.janela)
            self.janela.lift()
            self.janela.focus_force()
            return
        except Exception as exc:
            messagebox.showerror(t("error"), str(exc), parent=self.janela)
            self.janela.lift()
            self.janela.focus_force()
            return

        messagebox.showinfo(t("saved"), t("request_saved") + f"\n{destino}", parent=self.janela)
        self.janela.lift()
        self.janela.focus_force()

    def exportar_service_note(self):
        if self.alteracoes_pendentes:
            confirmar = messagebox.askyesno(
                t("pending_changes_title"),
                t("pending_changes_question"),
                parent=self.janela
            )
            if confirmar:
                self.confirmar_alteracoes_pendentes()
            else:
                self.janela.lift()
                self.janela.focus_force()
                return

        hoje = date.today()
        nome = f"{hoje.year}{hoje.month:02d}{hoje.day:02d}_UNC_EDP_PT_SNR_SN_Welfare_Activities_Meals_Reimbursement.docx"

        messagebox.showwarning(t("service_note"), t("service_note_alert"), parent=self.janela)
        self.janela.lift()
        self.janela.focus_force()

        destino = filedialog.asksaveasfilename(
            parent=self.janela,
            title=t("save_as"),
            initialfile=nome,
            defaultextension=".docx",
            filetypes=[("Word", "*.docx")],
        )
        if not destino:
            self.janela.lift()
            self.janela.focus_force()
            return

        dates_cohesion, individual_cohesion = self._dados_service_note()

        try:
            gerar_service_note(
                docs_dir=DOCS_DIR,
                destino=destino,
                ano=self.ano_atual,
                mes=self.mes_atual,
                dates_cohesion=dates_cohesion,
                individual_cohesion=individual_cohesion,
                chief_of_staff_name=get_nome_cos(),
            )
        except FileNotFoundError:
            messagebox.showerror(t("error"), t("service_note_template_missing"), parent=self.janela)
            self.janela.lift()
            self.janela.focus_force()
            return
        except Exception as exc:
            messagebox.showerror(t("error"), str(exc), parent=self.janela)
            self.janela.lift()
            self.janela.focus_force()
            return

        messagebox.showinfo(t("saved"), t("service_note_saved") + f"\n{destino}", parent=self.janela)
        self.janela.lift()
        self.janela.focus_force()

    def _dados_reembolso_para_export(self, hoto=False, utilizadores_override=None):
        linhas = []
        utilizadores_base = utilizadores_override if utilizadores_override is not None else self.utilizadores

        for user in utilizadores_base:
            if not user:
                continue

            partida_no_mes = self._date_in_mes_export(user.get("data_partida"))

            # Exportação normal: exclui quem tem partida no mês.
            # Exportação HOTO: usa exatamente a seleção validada na tabela.
            if not hoto and partida_no_mes:
                continue

            welfare, cohesion, reimbursement = self.calcular_resumo_user(user)
            linhas.append({
                "posto": (user.get("posto") or "").strip(),
                "sobrenome": (user.get("sobrenome") or "").strip().upper(),
                "nome": (user.get("nome") or "").strip().upper(),
                "welfare": welfare,
                "cohesion": cohesion,
                "reimbursement": reimbursement,
                "antiguidade": (user.get("antiguidade") or "").strip(),
                "data_partida": (user.get("data_partida") or "").strip(),
                "snr": int(user.get("snr") or 0),
            })
        return linhas

    def exportar_reembolso(self, hoto=False):
        utilizadores_override = None
        data_fim_override = None

        if hoto:
            if not self.hoto_selecionados:
                messagebox.showwarning(t("validation"), t("select_hoto_people"), parent=self.janela)
                self.janela.lift()
                self.janela.focus_force()
                return

            selecionados = [
                user
                for user in self.utilizadores
                if int(user.get("id")) in self.hoto_selecionados
            ]
            partidas = {self._data_partida_para_comparar(user) for user in selecionados}

            if len(partidas) != 1:
                self._mostrar_erro_datas_hoto(selecionados)
                return

            utilizadores_override = selecionados
            data_fim_override = self._data_partida_hoto_excel(selecionados[0]) if selecionados else None

        linhas = self._dados_reembolso_para_export(hoto=hoto, utilizadores_override=utilizadores_override)
        if not linhas:
            messagebox.showwarning(t("validation"), t("no_reimbursement_records"), parent=self.janela)
            self.janela.lift()
            self.janela.focus_force()
            return

        meses_en = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        sufixo = f"{meses_en[self.mes_atual - 1]}{self.ano_atual}"
        prefixo = "Meals_reimbursment_HOTO" if hoto else "Meals_reimbursment"
        nome = f"{prefixo}_{sufixo}.xlsx"

        destino = filedialog.asksaveasfilename(
            parent=self.janela,
            title=t("save_as"),
            initialfile=nome,
            defaultextension=".xlsx",
            filetypes=[("Excel", "*.xlsx")],
        )
        if not destino:
            self.janela.lift()
            self.janela.focus_force()
            return

        try:
            gerar_reembolso_mensal(
                docs_dir=DOCS_DIR,
                destino=destino,
                ano=self.ano_atual,
                mes=self.mes_atual,
                linhas=linhas,
                senior_assinatura=get_snr_unico_para_assinatura(),
                data_fim_override=data_fim_override,
            )
        except Exception as exc:
            messagebox.showerror(t("error"), str(exc), parent=self.janela)
            self.janela.lift()
            self.janela.focus_force()
            return

        messagebox.showinfo(t("saved"), destino, parent=self.janela)
        self.janela.lift()
        self.janela.focus_force()

    def on_canvas_click(self, event):
        if self._select_hoto_all_click_tag():
            self.alternar_selecao_hoto_todos()
            return

        user_id_select = self._select_hoto_click_tag()
        if user_id_select is not None:
            if user_id_select in self.hoto_selecionados:
                self.hoto_selecionados.remove(user_id_select)
            else:
                self.hoto_selecionados.add(user_id_select)
            self.desenhar_grelha()
            return

        inicio_semana_str, numero_semana = self._semana_click_tag()
        if inicio_semana_str:
            if self.pode_exportar_semanas():
                self.mostrar_menu_semana(event, inicio_semana_str, numero_semana)
            return

        if is_mes_trancado(self.ano_atual, self.mes_atual):
            messagebox.showwarning(t("month_locked"), t("month_locked_warning"), parent=self.janela)
            self.janela.lift()
            self.janela.focus_force()
            return
        if not self.pode_editar():
            return
        if self.modo == "pequeno_almoco":
            self.on_canvas_click_pequeno_almoco(event)
        else:
            self.on_canvas_click_welfare(event)

    def on_canvas_click_welfare(self, event):
        x = self.canvas.canvasx(event.x)
        y = self.canvas.canvasy(event.y)
        if x < self.ident_w or y < self.header_h1 + self.header_h2:
            return
        dias_w = self.dias_mes() * 2 * self.cell_w
        if x >= self.ident_w + dias_w:
            return
        dia_idx = int((x - self.ident_w) // (2 * self.cell_w)) + 1
        sub_x = (x - self.ident_w) % (2 * self.cell_w)
        refeicao = "Almoço" if sub_x < self.cell_w else "Jantar"
        row_idx = int((y - self.header_h1 - self.header_h2) // self.row_h)
        if row_idx < 0 or row_idx >= len(self.utilizadores):
            return
        if dia_idx < 1 or dia_idx > self.dias_mes():
            return
        user = self.utilizadores[row_idx]
        data_str = f"{self.ano_atual}-{self.mes_atual:02d}-{dia_idx:02d}"
        if not self.user_tem_refeicao_na_data(user, data_str, refeicao) or self.user_em_ferias_na_refeicao(user, data_str, refeicao):
            return
        chave = (user["id"], data_str, refeicao)
        atual = self.valor_efetivo(user["id"], data_str, refeicao)
        novo = not atual
        original = self.valor_efetivo_base(user["id"], data_str, refeicao)
        if novo == original:
            self.alteracoes_pendentes.pop(chave, None)
        else:
            self.alteracoes_pendentes[chave] = 1 if novo else 0
        self._limpar_caches_calculo()
        self._limpar_caches_calculo()
        self.atualizar_estado_botao_atualizar()
        self.desenhar_grelha()

    def on_canvas_click_pequeno_almoco(self, event):
        x = self.canvas.canvasx(event.x)
        y = self.canvas.canvasy(event.y)
        if x < self.ident_w or y < self.header_h1 + self.header_h2:
            return
        dias_w = self.dias_mes() * self.cell_w
        if x >= self.ident_w + dias_w:
            return
        dia_idx = int((x - self.ident_w) // self.cell_w) + 1
        row_idx = int((y - self.header_h1 - self.header_h2) // self.row_h)
        if row_idx < 0 or row_idx >= len(self.utilizadores):
            return
        user = self.utilizadores[row_idx]
        data_str = f"{self.ano_atual}-{self.mes_atual:02d}-{dia_idx:02d}"
        if not self.user_tem_pequeno_almoco_na_data(user, data_str):
            return
        chave = (user["id"], data_str, REFEICAO_PEQUENO_ALMOCO)
        atual = self.valor_pequeno_almoco(user, data_str)
        novo = not atual
        original = self.valor_pequeno_almoco_base(user, data_str)
        if novo == original:
            self.alteracoes_pendentes.pop(chave, None)
        else:
            self.alteracoes_pendentes[chave] = 1 if novo else 0
        self.atualizar_estado_botao_atualizar()
        self.desenhar_grelha()


class XfaDistributionWindow:
    DENOMINACOES = [10000, 5000, 2000, 1000, 500]

    def __init__(self, individual_window):
        self.individual = individual_window
        self.app = individual_window.app
        self.janela = tk.Toplevel(self.app.root)
        aplicar_icone(self.janela)
        self.app.registar_janela(self.janela, "distribuicao_xfa")
        self.janela.title("Distribuição XFA")
        self.janela.geometry("1400x780")
        self.janela.minsize(1100, 650)
        self.janela.configure(bg="white")
        try:
            self.janela.state("zoomed")
        except tk.TclError:
            self.janela.attributes("-zoomed", True)

        self.imagens_notas = {}
        self.entries = {}
        self.resultados = []
        self._linhas_marcadas = set()
        self.manual_mode = False
        self.manual_entries = []
        self.manual_panel = None
        self.tipo_valor_distribuicao = tk.StringVar(value="reembolso")
        self.criar_layout()

    def criar_layout(self):
        topo = tk.Frame(self.janela, bg=COR_PRINCIPAL, height=58)
        topo.pack(fill="x")
        topo.pack_propagate(False)
        tk.Label(topo, text="Distribuição XFA", bg=COR_PRINCIPAL, fg="white", font=("Arial", 17, "bold")).pack(side="left", padx=20)

        corpo = tk.Frame(self.janela, bg="white")
        corpo.pack(fill="both", expand=True, padx=12, pady=12)
        corpo.grid_columnconfigure(0, weight=1, uniform="main")
        corpo.grid_columnconfigure(1, weight=3, uniform="main")
        corpo.grid_rowconfigure(0, weight=1)

        painel = tk.Frame(corpo, bg="#f7fbfb", highlightthickness=1, highlightbackground=COR_LINHA, padx=18, pady=18)
        painel.grid(row=0, column=0, sticky="nsew", padx=(0, 10))

        tk.Label(painel, text="Notas disponíveis", bg="#f7fbfb", fg=COR_PRINCIPAL, font=("Arial", 14, "bold")).pack(anchor="w", pady=(0, 16))

        for denom in self.DENOMINACOES:
            linha = tk.Frame(painel, bg="#f7fbfb")
            linha.pack(fill="x", pady=8)
            img_label = self._criar_label_nota(linha, denom)
            img_label.pack(side="left", padx=(0, 12))
            tk.Label(linha, text=f"{denom:,}".replace(",", "."), bg="#f7fbfb", fg="#111111", font=("Arial", 10, "bold"), width=8, anchor="w").pack(side="left")
            ent = tk.Entry(linha, width=10, justify="center", font=("Arial", 11))
            ent.insert(0, "0")
            ent.pack(side="left", padx=(8, 0), ipady=4)
            ent.bind("<KeyRelease>", self._atualizar_total_notas)
            ent.bind("<FocusOut>", self._atualizar_total_notas)
            self.entries[denom] = ent

        self.lbl_total_notas = tk.Label(
            painel,
            text="",
            bg="#f7fbfb",
            fg="#111111",
            font=("Arial", 11, "bold"),
            anchor="w",
            justify="left",
        )
        self.lbl_total_notas.pack(anchor="w", fill="x", pady=(12, 2))
        self._atualizar_total_notas()

        escolha_valor = tk.LabelFrame(
            painel,
            text="Valor a distribuir",
            bg="#f7fbfb",
            fg=COR_PRINCIPAL,
            font=("Arial", 9, "bold"),
            padx=8,
            pady=6,
        )
        escolha_valor.pack(anchor="w", fill="x", pady=(12, 4))

        tk.Radiobutton(
            escolha_valor,
            text="Reembolso",
            variable=self.tipo_valor_distribuicao,
            value="reembolso",
            bg="#f7fbfb",
            activebackground="#f7fbfb",
            font=("Arial", 9, "bold"),
            command=self._on_tipo_valor_distribuicao_change,
        ).pack(anchor="w")

        tk.Radiobutton(
            escolha_valor,
            text="Reembolso Final",
            variable=self.tipo_valor_distribuicao,
            value="final",
            bg="#f7fbfb",
            activebackground="#f7fbfb",
            font=("Arial", 9, "bold"),
            command=self._on_tipo_valor_distribuicao_change,
        ).pack(anchor="w")

        self.lbl_total_reembolso = tk.Label(
            painel,
            text="",
            bg="#f7fbfb",
            fg=COR_PRINCIPAL,
            font=("Arial", 12, "bold"),
            anchor="w",
            justify="left",
        )
        self.lbl_total_reembolso.pack(anchor="w", fill="x", pady=(16, 4))
        self._atualizar_total_reembolso()

        botoes_calc = tk.Frame(painel, bg="#f7fbfb")
        botoes_calc.pack(anchor="w", pady=(8, 8))

        tk.Button(
            botoes_calc,
            text="Calcular",
            bg=COR_PRINCIPAL,
            fg="white",
            activebackground="#1ab394",
            activeforeground="white",
            font=("Arial", 11, "bold"),
            relief="flat",
            padx=20,
            pady=7,
            command=self.calcular,
        ).pack(side="left")

        tk.Button(
            botoes_calc,
            text="Manual",
            bg="#f7fbfb",
            fg=COR_PRINCIPAL,
            activebackground="#edf7f7",
            activeforeground=COR_PRINCIPAL,
            font=("Arial", 11, "bold"),
            relief="solid",
            bd=1,
            highlightthickness=1,
            highlightbackground=COR_PRINCIPAL,
            padx=20,
            pady=6,
            command=self.toggle_manual,
        ).pack(side="left", padx=(10, 0))

        self.manual_container = tk.Frame(painel, bg="#f7fbfb")
        self.manual_container.pack(fill="both", expand=False, pady=(2, 4))

        self.lbl_info = tk.Label(painel, text="Indica o número de notas disponíveis. A distribuição é feita apenas para as pessoas selecionadas no Welfare Individual.", bg="#f7fbfb", fg="#555555", font=("Arial", 9), wraplength=300, justify="left")
        self.lbl_info.pack(anchor="w", pady=(6, 0))

        tabela_frame = tk.Frame(corpo, bg="white")
        tabela_frame.grid(row=0, column=1, sticky="nsew")
        tabela_frame.grid_rowconfigure(0, weight=1)
        tabela_frame.grid_columnconfigure(0, weight=1)

        colunas = ("identificacao", "reembolso", "10000", "5000", "2000", "1000", "500")
        self.tabela = ttk.Treeview(tabela_frame, columns=colunas, show="headings")
        headers = {
            "identificacao": "Posto e Sobrenome",
            "reembolso": "Valor",
            "10000": "10000",
            "5000": "5000",
            "2000": "2000",
            "1000": "1000",
            "500": "500",
        }
        widths = {"identificacao": 260, "reembolso": 100, "10000": 70, "5000": 70, "2000": 70, "1000": 70, "500": 70}
        for col in colunas:
            self.tabela.heading(col, text=headers[col])
            self.tabela.column(col, width=widths[col], anchor="center" if col != "identificacao" else "w")
        self.tabela.tag_configure("feito", background="#d7f7d7")
        self.tabela.grid(row=0, column=0, sticky="nsew")
        sy = ttk.Scrollbar(tabela_frame, orient="vertical", command=self.tabela.yview)
        sx = ttk.Scrollbar(tabela_frame, orient="horizontal", command=self.tabela.xview)
        self.tabela.configure(yscrollcommand=sy.set, xscrollcommand=sx.set)
        sy.grid(row=0, column=1, sticky="ns")
        sx.grid(row=1, column=0, sticky="ew")
        self.tabela.bind("<ButtonRelease-1>", self.toggle_linha)
        self._atualizar_cabecalho_valor()

    def _criar_label_nota(self, parent, denom):
        caminho = DOCS_DIR + f"/{denom}.png"
        largura_padrao = 150
        altura_padrao = 70
        try:
            img = Image.open(caminho).convert("RGBA")
            ratio = largura_padrao / max(img.width, 1)
            nova_altura = max(1, int(img.height * ratio))
            img = img.resize((largura_padrao, nova_altura), Image.LANCZOS)

            canvas_img = Image.new("RGBA", (largura_padrao, altura_padrao), (255, 255, 255, 0))
            y = max(0, (altura_padrao - nova_altura) // 2)
            canvas_img.alpha_composite(img, (0, y))

            photo = ImageTk.PhotoImage(canvas_img)
            self.imagens_notas[denom] = photo
            return tk.Label(parent, image=photo, bg="#f7fbfb", width=largura_padrao, height=altura_padrao)
        except Exception:
            return tk.Label(parent, text=f"{denom}", bg="#f7fbfb", fg=COR_PRINCIPAL, font=("Arial", 14, "bold"), width=18, height=4)

    def toggle_linha(self, event=None):
        item = self.tabela.focus()
        if not item:
            return
        if item in self._linhas_marcadas:
            self._linhas_marcadas.remove(item)
            self.tabela.item(item, tags=())
        else:
            self._linhas_marcadas.add(item)
            self.tabela.item(item, tags=("feito",))

    def _total_notas_atual(self):
        total = 0
        for denom, ent in self.entries.items():
            raw = (ent.get() or "0").strip().replace(".", "").replace(" ", "")
            try:
                qtd = int(raw or 0)
                if qtd < 0:
                    qtd = 0
            except ValueError:
                qtd = 0
            total += int(denom) * qtd
        return total

    def _atualizar_total_notas(self, event=None):
        if not hasattr(self, "lbl_total_notas"):
            return
        total = self._total_notas_atual()
        self.lbl_total_notas.config(
            text=f"Total em notas: {self.individual.formatar_valor(total)} XAF"
        )

    def _total_reembolso_atual(self):
        linhas = self._dados_pessoas() if self.manual_mode else self._dados_pessoas_base()
        if linhas is None:
            return 0
        return sum(int(linha.get("reimbursement") or 0) for linha in linhas)

    def _atualizar_total_reembolso(self, event=None):
        if not hasattr(self, "lbl_total_reembolso"):
            return
        total = self._total_reembolso_atual()
        self.lbl_total_reembolso.config(
            text=f"{self._label_total_reembolso()}: {self.individual.formatar_valor(total)} XAF"
        )

    def _label_total_reembolso(self):
        return "Total Reembolso Final" if self.tipo_valor_distribuicao.get() == "final" else "Total Reembolso"

    def _atualizar_cabecalho_valor(self):
        if hasattr(self, "tabela"):
            titulo = "Reembolso Final" if self.tipo_valor_distribuicao.get() == "final" else "Reembolso"
            self.tabela.heading("reembolso", text=titulo)

    def _on_tipo_valor_distribuicao_change(self):
        self._atualizar_cabecalho_valor()
        self._atualizar_manual_if_active()
        self._atualizar_total_reembolso()

    def toggle_manual(self):
        self.manual_mode = not self.manual_mode
        if self.manual_mode:
            self._criar_manual_entries()
        else:
            self._limpar_manual_entries()
        self._atualizar_total_reembolso()

    def _atualizar_manual_if_active(self):
        if self.manual_mode:
            self._criar_manual_entries()
        self._atualizar_total_reembolso()

    def _limpar_manual_entries(self):
        self.manual_entries = []
        for child in self.manual_container.winfo_children():
            child.destroy()

    def _criar_manual_entries(self):
        self._limpar_manual_entries()

        linhas = self._dados_pessoas_base()
        if not linhas:
            tk.Label(
                self.manual_container,
                text="Selecione pelo menos uma pessoa para efetuar a Distribuição XFA.",
                bg="#f7fbfb",
                fg="#555555",
                font=("Arial", 9),
            ).pack(anchor="w", pady=(4, 0))
            return

        tk.Label(
            self.manual_container,
            text="Valores manuais",
            bg="#f7fbfb",
            fg=COR_PRINCIPAL,
            font=("Arial", 10, "bold"),
        ).pack(anchor="w", pady=(6, 4))

        wrapper = tk.Frame(self.manual_container, bg="#f7fbfb")
        wrapper.pack(fill="x", expand=False)

        canvas = tk.Canvas(wrapper, bg="#f7fbfb", highlightthickness=0, height=210)
        scrollbar = ttk.Scrollbar(wrapper, orient="vertical", command=canvas.yview)
        inner = tk.Frame(canvas, bg="#f7fbfb")
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="x", expand=True)
        scrollbar.pack(side="right", fill="y")

        self.manual_entries = []
        for linha in linhas:
            row = tk.Frame(inner, bg="#f7fbfb")
            row.pack(fill="x", pady=2)
            tk.Label(
                row,
                text=self._formatar_identificacao(linha),
                bg="#f7fbfb",
                fg="#111111",
                font=("Arial", 8),
                width=22,
                anchor="w",
            ).pack(side="left")
            ent = tk.Entry(row, width=12, justify="right", font=("Arial", 9))
            ent.insert(0, str(int(linha.get("reimbursement") or 0)))
            ent.pack(side="left", padx=(6, 0), ipady=2)
            ent.bind("<KeyRelease>", self._atualizar_total_reembolso)
            self.manual_entries.append((linha, ent))

    def _dados_pessoas_base(self):
        selecionados = getattr(self.individual, "hoto_selecionados", set()) or set()
        if not selecionados:
            return []

        linhas = []
        for user in self.individual.utilizadores:
            if user.get("id") not in selecionados:
                continue
            welfare, cohesion, reimbursement = self.individual.calcular_resumo_user(user)
            caixa = self.individual.calcular_caixa_user(user)
            reembolso_final = max(0, int(reimbursement or 0) - int(caixa or 0))
            valor_distribuir = reembolso_final if self.tipo_valor_distribuicao.get() == "final" else reimbursement
            linhas.append({
                "posto": (user.get("posto") or "").strip(),
                "sobrenome": (user.get("sobrenome") or "").strip().upper(),
                "nome": (user.get("nome") or "").strip().upper(),
                "welfare": welfare,
                "cohesion": cohesion,
                "reimbursement": valor_distribuir,
                "reimbursement_original": reimbursement,
                "caixa": caixa,
                "reembolso_final": reembolso_final,
                "antiguidade": (user.get("antiguidade") or "").strip(),
                "snr": int(user.get("snr") or 0),
            })

        linhas = [dict(l) for l in linhas if int(l.get("reimbursement") or 0) > 0]
        return linhas

    def _ler_stock(self):
        stock = {}
        for denom, ent in self.entries.items():
            raw = ent.get().strip() or "0"
            try:
                val = int(raw)
                if val < 0:
                    raise ValueError
            except ValueError:
                messagebox.showwarning("Validação", f"Quantidade inválida para a nota {denom}.", parent=self.janela)
                self.janela.lift(); self.janela.focus_force()
                return None
            stock[denom] = val
        return stock

    def _dados_pessoas(self):
        if self.manual_mode:
            linhas = []
            for linha_original, ent in self.manual_entries:
                raw = ent.get().strip().replace(".", "").replace(" ", "") or "0"
                try:
                    valor = int(raw)
                    if valor < 0:
                        raise ValueError
                except ValueError:
                    messagebox.showwarning("Validação", f"Valor inválido para {self._formatar_identificacao(linha_original)}.", parent=self.janela)
                    self.janela.lift(); self.janela.focus_force()
                    return None
                if valor <= 0:
                    continue
                linha = dict(linha_original)
                linha["reimbursement"] = valor
                linhas.append(linha)
            return linhas

        return self._dados_pessoas_base()

    def _formatar_identificacao(self, linha):
        posto = (linha.get("posto") or "").strip()
        sobrenome = (linha.get("sobrenome") or "").strip().upper()
        return f"{posto} {sobrenome}".strip()

    def _combo_dp_para_valor(self, valor, stock, preferencia="baixas"):
        """Procura uma combinação exata para um valor com o stock disponível.

        A primeira prioridade é sempre conseguir fechar o valor. A preferência
        pelas notas mais baixas é usada apenas para escolher entre combinações
        possíveis.
        """
        denoms = self.DENOMINACOES
        if valor <= 0:
            return {d: 0 for d in denoms}
        if valor % 500 != 0:
            return None

        alvo = valor // 500
        unidades = {d: d // 500 for d in denoms}

        opcoes_por_denom = []
        for d in denoms:
            max_qtd = min(int(stock.get(d, 0) or 0), alvo // unidades[d])
            opcoes_por_denom.append((d, max_qtd))

        dp = {0: ((0, 0), {d: 0 for d in denoms})}

        for d, max_qtd in opcoes_por_denom:
            u = unidades[d]
            novo = {}
            for soma, (score_atual, combo_atual) in dp.items():
                for qtd in range(max_qtd + 1):
                    nsoma = soma + qtd * u
                    if nsoma > alvo:
                        break

                    combo = dict(combo_atual)
                    combo[d] = qtd

                    if preferencia == "baixas":
                        peso = {500: 1, 1000: 2, 2000: 4, 5000: 10, 10000: 20}.get(d, d // 500)
                    elif preferencia == "altas":
                        peso = {10000: 1, 5000: 2, 2000: 5, 1000: 10, 500: 20}.get(d, d // 500)
                    else:
                        peso = 1

                    nscore = (score_atual[0] + qtd * peso, score_atual[1] + qtd)
                    atual = novo.get(nsoma)
                    if atual is None or nscore < atual[0]:
                        novo[nsoma] = (nscore, combo)

            dp = novo
            if not dp:
                return None

        if alvo not in dp:
            return None
        return dp[alvo][1]

    def _combo_dp_proporcional(self, valor, stock, target, preferir_baixas=True):
        """Escolhe uma combinação exata aproximando a quota proporcional.

        Exemplo da lógica: se uma pessoa recebe cerca de 50% do valor de outra,
        tenta receber também cerca de 50% das notas de cada tipo, sempre que isso
        seja possível e sem deixar de fechar o valor.
        """
        denoms = self.DENOMINACOES
        if valor <= 0:
            return {d: 0 for d in denoms}
        if valor % 500 != 0:
            return None

        alvo = valor // 500
        unidades = {d: d // 500 for d in denoms}
        ranks_baixas = {500: 0, 1000: 1, 2000: 2, 5000: 3, 10000: 4}

        dp = {0: ((0.0, 0.0, 0), {d: 0 for d in denoms})}

        for d in denoms:
            max_qtd = min(int(stock.get(d, 0) or 0), alvo // unidades[d])
            u = unidades[d]
            novo = {}

            for soma, (score_atual, combo_atual) in dp.items():
                for qtd in range(max_qtd + 1):
                    nsoma = soma + qtd * u
                    if nsoma > alvo:
                        break

                    combo = dict(combo_atual)
                    combo[d] = qtd

                    esperado = float(target.get(d, 0) or 0)
                    # Penalização proporcional: quanto mais distante da quota,
                    # pior. Quando a quota é zero, qualquer uso fica penalizado.
                    if esperado > 0:
                        desvio = ((qtd - esperado) / max(1.0, esperado)) ** 2
                    else:
                        desvio = float(qtd * qtd)

                    # Preferência suave por notas baixas. É secundária: só decide
                    # entre combinações com equilíbrio semelhante.
                    if preferir_baixas:
                        pref = qtd * ranks_baixas.get(d, 0) * 0.0001
                    else:
                        pref = -qtd * ranks_baixas.get(d, 0) * 0.0001

                    nscore = (
                        score_atual[0] + desvio,
                        score_atual[1] + pref,
                        score_atual[2] + qtd,
                    )
                    atual = novo.get(nsoma)
                    if atual is None or nscore < atual[0]:
                        novo[nsoma] = (nscore, combo)

            dp = novo
            if not dp:
                return None

        if alvo not in dp:
            return None
        return dp[alvo][1]

    def _avaliar_distribuicao(self, resultados, stock_inicial, stock_final, falhas):
        """Pontua uma distribuição: completar primeiro, equilíbrio depois."""
        total_falhas = len(falhas)
        total_amount = sum(int(item.get("amount") or 0) for item in resultados)
        denoms = self.DENOMINACOES

        # Equilíbrio por percentagem: cada pessoa deve receber uma proporção de
        # notas parecida com a sua proporção no valor total a pagar.
        equilibrio = 0.0
        for d in denoms:
            total_usado_d = sum(int(item.get("combo", {}).get(d, 0) or 0) for item in resultados)
            if total_usado_d <= 0 or total_amount <= 0:
                continue
            for item in resultados:
                amount = int(item.get("amount") or 0)
                esperado = total_usado_d * (amount / total_amount) if total_amount else 0
                atual = int(item.get("combo", {}).get(d, 0) or 0)
                if esperado > 0:
                    equilibrio += ((atual - esperado) / max(1.0, esperado)) ** 2
                elif atual:
                    equilibrio += atual * atual

        # Penaliza valores por fechar.
        restante = sum(int(item.get("remaining") or 0) for item in resultados)

        # Preferência suave: entre soluções igualmente boas, usar mais notas
        # baixas e deixar mais notas altas disponíveis.
        notas_altas_sobra = stock_final.get(10000, 0) + stock_final.get(5000, 0)
        notas_baixas_sobra = stock_final.get(500, 0) + stock_final.get(1000, 0)
        preferencia_sobra = notas_baixas_sobra - notas_altas_sobra

        return (
            total_falhas,
            restante,
            equilibrio,
            preferencia_sobra,
        )

    def _calcular_distribuicao_com_estrategia(self, linhas, stock, ordem="maior", preferir_baixas=True):
        denoms = self.DENOMINACOES
        if ordem == "menor":
            linhas_ordenadas = sorted(enumerate(linhas), key=lambda x: (int(x[1].get("reimbursement") or 0), x[0]))
        elif ordem == "original":
            linhas_ordenadas = list(enumerate(linhas))
        else:
            linhas_ordenadas = sorted(enumerate(linhas), key=lambda x: (-int(x[1].get("reimbursement") or 0), x[0]))

        resultados_tmp = []
        stock_atual = dict(stock)
        total_restante_global = sum(int(l.get("reimbursement") or 0) for _idx, l in linhas_ordenadas)

        for idx_original, linha in linhas_ordenadas:
            amount = int(linha.get("reimbursement") or 0)
            if amount <= 0:
                combo = {d: 0 for d in denoms}
                remaining = 0
            else:
                target = {}
                if total_restante_global > 0:
                    proporcao = amount / total_restante_global
                    for d in denoms:
                        target[d] = int(stock_atual.get(d, 0) or 0) * proporcao
                else:
                    target = {d: 0 for d in denoms}

                combo = self._combo_dp_proporcional(amount, stock_atual, target, preferir_baixas=preferir_baixas)
                if combo is None:
                    # Fallback: fechar o valor continua a ser mais importante
                    # do que respeitar a proporção ideal.
                    combo = self._combo_dp_para_valor(amount, stock_atual, preferencia="baixas" if preferir_baixas else "altas")

                if combo is None:
                    combo = {d: 0 for d in denoms}
                    remaining = amount
                else:
                    remaining = 0
                    for d in denoms:
                        stock_atual[d] = int(stock_atual.get(d, 0) or 0) - int(combo.get(d, 0) or 0)

            resultados_tmp.append({
                "idx_original": idx_original,
                "linha": linha,
                "amount": amount,
                "remaining": remaining,
                "combo": combo,
            })
            total_restante_global -= amount

        falhas = [self._formatar_identificacao(item["linha"]) for item in resultados_tmp if item["remaining"] != 0]
        resultados_tmp.sort(key=lambda r: r["idx_original"])
        saida = [(item["linha"], item["combo"]) for item in resultados_tmp]
        return saida, stock_atual, falhas, resultados_tmp

    def _calcular_distribuicao_equilibrada(self, linhas, stock):
        """Distribui notas por percentagem, sem falhar o valor quando possível.

        A distribuição procura que a composição das notas acompanhe o peso de
        cada reembolso. Exemplo: se uma pessoa recebe cerca do dobro de outra,
        tenta receber cerca do dobro das notas de 10.000, 5.000, 2.000, etc.
        A preferência por notas baixas existe, mas é secundária: primeiro fecha
        o valor, depois equilibra percentagens, depois prefere usar notas baixas.
        """
        estrategias = [
            ("maior", True),
            ("original", True),
            ("menor", True),
            ("maior", False),
            ("original", False),
        ]

        melhor = None
        melhor_score = None

        for ordem, preferir_baixas in estrategias:
            saida, stock_final, falhas, resultados_tmp = self._calcular_distribuicao_com_estrategia(
                linhas,
                stock,
                ordem=ordem,
                preferir_baixas=preferir_baixas,
            )
            score = self._avaliar_distribuicao(resultados_tmp, stock, stock_final, falhas)
            if melhor is None or score < melhor_score:
                melhor = (saida, stock_final, falhas)
                melhor_score = score

        return melhor

    def calcular(self):
        stock = self._ler_stock()
        if stock is None:
            return
        linhas = self._dados_pessoas()
        if linhas is None:
            return
        if not linhas:
            messagebox.showwarning(
                "Validação",
                "Selecione pelo menos uma pessoa para efetuar a Distribuição XFA.",
                parent=self.janela
            )
            self.janela.lift()
            self.janela.focus_force()
            return
        total_reembolsos = sum(int(l.get("reimbursement") or 0) for l in linhas)
        self._atualizar_total_reembolso()
        total_stock = sum(d * q for d, q in stock.items())
        if total_stock < total_reembolsos:
            messagebox.showwarning("Notas insuficientes", f"Valor disponível insuficiente. Disponível: {total_stock:,} | Necessário: {total_reembolsos:,}".replace(",", "."), parent=self.janela)
            self.janela.lift(); self.janela.focus_force()
            return

        for item in self.tabela.get_children():
            self.tabela.delete(item)
        self._linhas_marcadas.clear()

        resultados, stock_atual, falhas = self._calcular_distribuicao_equilibrada(linhas, stock)

        for linha, combo in resultados:
            valores = [
                self._formatar_identificacao(linha),
                self.individual.formatar_valor(linha.get("reimbursement") or 0),
                combo.get(10000, 0),
                combo.get(5000, 0),
                combo.get(2000, 0),
                combo.get(1000, 0),
                combo.get(500, 0),
            ]
            self.tabela.insert("", "end", values=valores)

        sobra_txt = " | ".join(f"{d}: {stock_atual.get(d,0)}" for d in self.DENOMINACOES)
        self.lbl_info.config(text=f"Total necessário: {self.individual.formatar_valor(total_reembolsos)} XAF\nSobra: {sobra_txt}")
        if falhas:
            messagebox.showwarning("Distribuição incompleta", "Não foi possível acertar exatamente para:\n" + "\n".join(falhas), parent=self.janela)
            self.janela.lift(); self.janela.focus_force()
