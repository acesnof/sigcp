import calendar
import tkinter as tk
from tkinter import ttk
from datetime import date

from app.utils import aplicar_icone
from app.i18n import months, weekdays_datepicker, t


class DatePicker(tk.Toplevel):
    def __init__(self, parent, target_entry, initial_date=None):
        super().__init__(parent)

        self.target_entry = target_entry

        if initial_date:
            try:
                ano, mes, dia = [int(x) for x in initial_date.split("-")]
                self.current = date(ano, mes, dia)
            except Exception:
                self.current = date.today()
        else:
            self.current = date.today()

        self.ano = self.current.year
        self.mes = self.current.month

        self.title(t("date").replace(":", ""))
        aplicar_icone(self)
        self.geometry("360x305")
        self.resizable(False, False)
        self.configure(bg="white")
        self.transient(parent)
        self.grab_set()

        self.header = tk.Frame(self, bg="white")
        self.header.pack(fill="x", pady=8)

        tk.Button(self.header, text="<", width=4, command=self.mes_anterior).pack(side="left", padx=8)

        self.lbl_mes = tk.Label(self.header, bg="white", font=("Arial", 11, "bold"))
        self.lbl_mes.pack(side="left", expand=True)

        tk.Button(self.header, text=">", width=4, command=self.mes_seguinte).pack(side="right", padx=8)

        self.grid_frame = tk.Frame(self, bg="white")
        self.grid_frame.pack(fill="both", expand=True, padx=12, pady=5)

        self.desenhar()

    def desenhar(self):
        for widget in self.grid_frame.winfo_children():
            widget.destroy()

        meses = months()

        self.lbl_mes.config(text=f"{meses[self.mes]} {self.ano}")

        dias = weekdays_datepicker()

        for col, dia in enumerate(dias):
            tk.Label(
                self.grid_frame,
                text=dia,
                bg="#0b4b52",
                fg="white",
                font=("Arial", 8, "bold"),
                width=5
            ).grid(row=0, column=col, padx=1, pady=1, sticky="nsew")

        for col in range(7):
            self.grid_frame.grid_columnconfigure(col, weight=1, uniform="dias_datepicker")

        cal = calendar.Calendar(firstweekday=0)
        semanas = cal.monthdayscalendar(self.ano, self.mes)

        for r, semana in enumerate(semanas, start=1):
            for c, dia in enumerate(semana):
                if dia == 0:
                    tk.Label(self.grid_frame, text="", bg="white", width=5).grid(row=r, column=c, padx=1, pady=1, sticky="nsew")
                    continue

                btn = tk.Button(
                    self.grid_frame,
                    text=str(dia),
                    width=5,
                    relief="flat",
                    bg="#d8f1f4" if c in [5, 6] else "#f8f8f8",
                    command=lambda d=dia: self.selecionar(d)
                )
                btn.grid(row=r, column=c, padx=1, pady=1, sticky="nsew")

    def selecionar(self, dia):
        valor = f"{self.ano}-{self.mes:02d}-{dia:02d}"
        self.target_entry.delete(0, tk.END)
        self.target_entry.insert(0, valor)
        self.destroy()

    def mes_anterior(self):
        self.mes -= 1
        if self.mes == 0:
            self.mes = 12
            self.ano -= 1
        self.desenhar()

    def mes_seguinte(self):
        self.mes += 1
        if self.mes == 13:
            self.mes = 1
            self.ano += 1
        self.desenhar()


class DateEntry(tk.Frame):
    def __init__(self, parent, value=""):
        super().__init__(parent, bg="white")

        self.entry = tk.Entry(self, width=35)
        self.entry.insert(0, value or "")
        self.entry.pack(side="left", ipady=3)

        tk.Button(
            self,
            text="📅",
            width=3,
            relief="flat",
            bg="#0b4b52",
            fg="white",
            command=self.abrir
        ).pack(side="left", padx=(4, 0))

    def abrir(self):
        DatePicker(self, self.entry, self.entry.get().strip())

    def get(self):
        return self.entry.get().strip()

    def set(self, value):
        self.entry.delete(0, tk.END)
        self.entry.insert(0, value or "")

    def config_state(self, state):
        self.entry.config(state=state)
        for child in self.winfo_children():
            if isinstance(child, tk.Button):
                child.config(state=state)


class DateTimePicker(DatePicker):
    def __init__(self, parent, target_entry, initial_value=None):
        self.initial_time = "08:00"
        initial_date = None
        if initial_value:
            value = initial_value.strip()
            if " " in value:
                initial_date, hora = value.split(" ", 1)
                hora = hora.strip()[:5]
                if len(hora) == 5 and hora[2] == ":":
                    self.initial_time = hora
            else:
                initial_date = value
        super().__init__(parent, target_entry, initial_date)
        self.title(t("datetime"))
        self.geometry("360x360")

        time_frame = tk.Frame(self, bg="white")
        time_frame.pack(fill="x", padx=12, pady=(0, 10))

        tk.Label(time_frame, text=t("time"), bg="white", font=("Arial", 9, "bold")).pack(side="left", padx=(0, 8))

        horas = [f"{h:02d}" for h in range(24)]
        minutos = ["00", "15", "30", "45"]
        h0, m0 = self.initial_time.split(":")

        self.combo_hora = ttk.Combobox(time_frame, state="readonly", values=horas, width=4)
        self.combo_hora.set(h0 if h0 in horas else "08")
        self.combo_hora.pack(side="left")

        tk.Label(time_frame, text=":", bg="white", font=("Arial", 10, "bold")).pack(side="left", padx=2)

        self.combo_minuto = ttk.Combobox(time_frame, state="readonly", values=minutos, width=4)
        self.combo_minuto.set(m0 if m0 in minutos else "00")
        self.combo_minuto.pack(side="left")

    def selecionar(self, dia):
        valor = f"{self.ano}-{self.mes:02d}-{dia:02d} {self.combo_hora.get()}:{self.combo_minuto.get()}"
        self.target_entry.delete(0, tk.END)
        self.target_entry.insert(0, valor)
        self.destroy()


class DateTimeEntry(tk.Frame):
    def __init__(self, parent, value=""):
        super().__init__(parent, bg="white")

        self.entry = tk.Entry(self, width=35)
        self.entry.insert(0, value or "")
        self.entry.pack(side="left", ipady=3)

        tk.Button(
            self,
            text="📅",
            width=3,
            relief="flat",
            bg="#0b4b52",
            fg="white",
            command=self.abrir
        ).pack(side="left", padx=(4, 0))

    def abrir(self):
        DateTimePicker(self, self.entry, self.entry.get().strip())

    def get(self):
        return self.entry.get().strip()

    def set(self, value):
        self.entry.delete(0, tk.END)
        self.entry.insert(0, value or "")

    def config_state(self, state):
        self.entry.config(state=state)
        for child in self.winfo_children():
            if isinstance(child, tk.Button):
                child.config(state=state)
