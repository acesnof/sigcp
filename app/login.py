import tkinter as tk
from tkinter import messagebox

from app.config import COR_PRINCIPAL
from app.db import autenticar_utilizador
from app.utils import aplicar_icone


class LoginDialog(tk.Toplevel):
    def __init__(self, root):
        super().__init__(root)

        self.root = root
        self.user = None

        self.title("Login - SIGCP")
        aplicar_icone(self)
        self.geometry("380x250")
        self._centrar_no_monitor(380, 250)
        self.resizable(False, False)
        self.configure(bg="white")
        self.grab_set()

        self.protocol("WM_DELETE_WINDOW", self.cancelar)

        tk.Label(
            self,
            text="SIGCP",
            bg="white",
            fg=COR_PRINCIPAL,
            font=("Arial", 18, "bold")
        ).pack(pady=(20, 10))

        frame = tk.Frame(self, bg="white", padx=30)
        frame.pack(fill="x")

        tk.Label(frame, text="NIM:", bg="white", font=("Arial", 10, "bold")).pack(anchor="w")
        self.entry_nim = tk.Entry(frame, width=35)
        self.entry_nim.pack(pady=(2, 10), ipady=4)

        tk.Label(frame, text="Password:", bg="white", font=("Arial", 10, "bold")).pack(anchor="w")
        self.entry_password = tk.Entry(frame, width=35, show="*")
        self.entry_password.pack(pady=(2, 15), ipady=4)

        tk.Button(
            self,
            text="Entrar",
            bg=COR_PRINCIPAL,
            fg="white",
            relief="flat",
            font=("Arial", 10, "bold"),
            width=18,
            command=self.login
        ).pack()

        self.entry_password.bind("<Return>", lambda e: self.login())
        self.entry_nim.focus_set()

    def _centrar_no_monitor(self, largura, altura):
        self.update_idletasks()
        x = int((self.winfo_screenwidth() - largura) / 2)
        y = int((self.winfo_screenheight() - altura) / 2)
        self.geometry(f"{largura}x{altura}+{x}+{y}")

    def login(self):
        nim = self.entry_nim.get().strip()
        password = self.entry_password.get()

        user = autenticar_utilizador(nim, password)

        if not user:
            messagebox.showerror("Erro", "Credenciais inválidas.")
            return

        self.user = user
        self.destroy()

    def cancelar(self):
        self.user = None
        self.destroy()
        self.root.destroy()
