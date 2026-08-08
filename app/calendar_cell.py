import tkinter as tk

from app.i18n import t
from app.db import is_mes_trancado

from app.config import (
    COR_AZUL_REFEICAO,
    COR_EMENTA,
    COR_LINHA,
    COR_LINHA_INTERNA,
    COR_OBS,
    COR_PRINCIPAL,
    COR_VERMELHO,
    TIPOS_WELFARE,
)


class DiaCalendario(tk.Frame):
    def __init__(self, parent, app, dia, data_str, welfares_dia, bg, is_day_off=False):
        super().__init__(
            parent,
            bg=bg,
            bd=0,
            highlightthickness=1,
            highlightbackground=COR_LINHA
        )

        self.app = app
        self.dia = dia
        self.data_str = data_str
        self.welfares_dia = welfares_dia
        self.bg = bg
        self.is_day_off = is_day_off
        self.edit_areas = []

        self.canvas = tk.Canvas(
            self,
            bg=bg,
            bd=0,
            highlightthickness=0,
            cursor="hand2"
        )
        self.canvas.pack(fill="both", expand=True)

        self.canvas.bind("<Configure>", self.desenhar)
        self.canvas.bind("<Button-1>", self._tratar_clique)

    def _tratar_clique(self, event):
        """
        Clique no ícone editar ou no texto ALMOÇO/JANTAR: edita essa refeição.
        Clique no resto da célula: adiciona a refeição em falta.
        Se já tiver Almoço e Jantar, não abre nada no resto da célula.
        """
        for x1, y1, x2, y2, refeicao in self.edit_areas:
            if x1 <= event.x <= x2 and y1 <= event.y <= y2:
                self.app.abrir_janela_dia(self.data_str, refeicao, modo="editar")
                return "break"

        if is_mes_trancado(self.app.ano_atual, self.app.mes_atual):
            return "break"

        refeicoes_existentes = {w["refeicao"] for w in self.welfares_dia}

        if not self.app.pode_adicionar_editar_welfare_mensal():
            return "break"

        if "Almoço" in refeicoes_existentes and "Jantar" in refeicoes_existentes:
            return "break"

        if "Almoço" not in refeicoes_existentes:
            self.app.abrir_janela_dia(self.data_str, "Almoço", modo="adicionar")
        elif "Jantar" not in refeicoes_existentes:
            self.app.abrir_janela_dia(self.data_str, "Jantar", modo="adicionar")

        return "break"

    def desenhar(self, event=None):
        self.canvas.delete("all")
        self.edit_areas = []

        w = max(self.canvas.winfo_width(), 1)
        h = max(self.canvas.winfo_height(), 1)

        self.canvas.create_rectangle(
            1,
            1,
            w - 2,
            h - 2,
            outline=COR_PRINCIPAL,
            width=1 if self.welfares_dia else 0
        )

        self.canvas.create_text(
            10,
            8,
            text=str(self.dia),
            anchor="nw",
            fill="#000000",
            font=("Arial", 10, "bold" if (self.welfares_dia or self.is_day_off) else "normal")
        )

        almoco = next((x for x in self.welfares_dia if x["refeicao"] == "Almoço"), None)
        jantar = next((x for x in self.welfares_dia if x["refeicao"] == "Jantar"), None)

        if almoco and jantar:
            bloco1_y = int(h * 0.26)
            bloco1_altura = int(h * 0.30)
            separador_y = int(h * 0.58)
            bloco2_y = separador_y + 8
            bloco2_altura = h - bloco2_y - 8

            self._desenhar_bloco(almoco, 10, bloco1_y, w - 20, bloco1_altura, compacto=True)

            self.canvas.create_line(
                10,
                separador_y,
                w - 10,
                separador_y,
                fill=COR_LINHA_INTERNA,
                width=1
            )

            self._desenhar_bloco(jantar, 10, bloco2_y, w - 20, bloco2_altura, compacto=True)

        elif almoco:
            self._desenhar_bloco(almoco, 10, int(h * 0.30), w - 20, int(h * 0.63), compacto=False)

        elif jantar:
            self._desenhar_bloco(jantar, 10, int(h * 0.30), w - 20, int(h * 0.63), compacto=False)

    def _desenhar_bloco(self, welfare, x, y, largura, altura, compacto=False):
        refeicao = welfare["refeicao"]

        titulo_font = ("Arial", 10 if compacto else 12, "bold")
        obs_font = ("Arial", 7 if compacto else 8, "bold")
        ementa_font = ("Arial", 7 if compacto else 9, "normal")

        pode_ver_editar = self.app.pode_ver_botao_editar_welfare_mensal()
        icone_editar = self.app.imagens_cache.get("editar.png") if pode_ver_editar else None

        edit_x1 = x
        edit_y1 = y - 3
        edit_x2 = x + (118 if compacto else 150)
        edit_y2 = y + (25 if compacto else 30)
        self.edit_areas.append((edit_x1, edit_y1, edit_x2, edit_y2, refeicao))

        if icone_editar:
            self.canvas.create_image(
                x + 12,
                y + 11,
                image=icone_editar,
                anchor="center"
            )
            texto_x = x + 30
        elif pode_ver_editar:
            self.canvas.create_text(
                x,
                y - 1,
                text="✎",
                anchor="nw",
                fill=COR_AZUL_REFEICAO,
                font=("Arial", 16, "bold")
            )
            texto_x = x + 28
        else:
            texto_x = x

        self.canvas.create_text(
            texto_x,
            y - 1,
            text=(t("lunch") if refeicao == "Almoço" else t("dinner")).upper(),
            anchor="nw",
            fill=COR_AZUL_REFEICAO,
            font=titulo_font
        )

        self._desenhar_icones_refeicao(
            welfare=welfare,
            x_direita=x + largura,
            y=y,
            compacto=compacto
        )

        obs = (welfare.get("observacao") or "").strip()
        ementa = self._texto_ementa(welfare)

        y_texto = y + (20 if compacto else 28)
        largura_texto = max(largura - 8, 80)

        if obs:
            self.canvas.create_text(
                x,
                y_texto,
                text=obs,
                anchor="nw",
                fill=COR_OBS,
                font=obs_font,
                width=largura_texto
            )
            y_texto += 13 if compacto else 24

        if ementa:
            self.canvas.create_text(
                x,
                y_texto,
                text=ementa,
                anchor="nw",
                fill=COR_EMENTA,
                font=ementa_font,
                width=largura_texto
            )

    def _texto_ementa(self, welfare):
        prato = (welfare.get("prato") or "").strip()
        sobremesa = (welfare.get("sobremesa") or "").strip()

        if prato and sobremesa:
            return f"{prato}/{sobremesa}"

        if prato:
            return prato

        if sobremesa:
            return sobremesa

        return ""

    def _desenhar_icones_refeicao(self, welfare, x_direita, y, compacto):
        ficheiros = TIPOS_WELFARE.get(welfare["tipo"], [])

        tamanho_gap = 25 if compacto else 29
        x = x_direita - 18

        for ficheiro in reversed(ficheiros):
            img = self.app.imagens_cache.get(ficheiro)

            if img:
                self.canvas.create_image(
                    x,
                    y + 12,
                    image=img,
                    anchor="center"
                )
            else:
                self.canvas.create_text(
                    x,
                    y + 1,
                    text="★" if "star" in ficheiro else "●",
                    anchor="n",
                    fill=COR_VERMELHO,
                    font=("Arial", 15, "bold")
                )

            x -= tamanho_gap
