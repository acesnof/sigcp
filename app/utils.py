import os

from app.config import FAVICON_PATH


def aplicar_icone(janela):
    """Aplica docs/favico.ico à janela, se existir.

    Funciona em Windows com ficheiros .ico. Se o ficheiro não existir
    ou houver erro, não bloqueia a aplicação.
    """
    try:
        if os.path.exists(FAVICON_PATH):
            janela.iconbitmap(FAVICON_PATH)
    except Exception:
        pass
