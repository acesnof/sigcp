"""Regra comum de ordenação das pessoas na aplicação."""

from datetime import date, datetime, time

from app.config import POSTOS


# OF-6 deixou de estar disponível para novos perfis, mas continua reconhecido
# para ordenar corretamente bases de dados antigas.
POSTO_ORDER = {posto: indice for indice, posto in enumerate(["OF-6", *POSTOS])}


def person_still_in_mission(person, reference=None):
    """Indica se a pessoa ainda não ultrapassou o fim da missão."""
    departure_text = str(person.get("data_partida") or "").strip().replace("T", " ")
    if not departure_text:
        return True

    try:
        if len(departure_text) >= 16:
            departure = datetime.strptime(departure_text[:16], "%Y-%m-%d %H:%M")
        else:
            departure = datetime.combine(
                date.fromisoformat(departure_text[:10]), time.max
            )
    except ValueError:
        # Dados antigos inválidos não devem esconder nem despromover a pessoa.
        return True

    current = reference or datetime.now()
    if isinstance(current, date) and not isinstance(current, datetime):
        current = datetime.combine(current, time.min)
    return departure >= current


def person_order_key(person, *, departed_last=False, reference=None):
    """Ordena sempre por posto, antiguidade e, por fim, nome.

    ``departed_last`` mantém-se apenas por compatibilidade com chamadas antigas;
    o estado da missão não altera a precedência das pessoas numa lista.
    """
    rank = POSTO_ORDER.get(str(person.get("posto") or "").strip().upper(), 99)

    antiquity = str(person.get("antiguidade") or "").strip()[:10]
    try:
        date.fromisoformat(antiquity)
    except ValueError:
        antiquity = ""

    surname = str(person.get("sobrenome") or "").strip().casefold()
    name = str(person.get("nome") or "").strip().casefold()
    nim = str(person.get("nim") or "").strip().casefold()
    identifier = str(person.get("id") or "")
    return (
        rank,
        0 if antiquity else 1,
        antiquity,
        surname,
        name,
        nim,
        identifier,
    )
