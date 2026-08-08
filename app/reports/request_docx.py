import os
import calendar
from datetime import date

from app.reports.service_note_docx import substituir_placeholders_docx


MESES_EN_ABREV = {
    1: "JAN", 2: "FEB", 3: "MAR", 4: "APR", 5: "MAY", 6: "JUN",
    7: "JUL", 8: "AUG", 9: "SEP", 10: "OCT", 11: "NOV", 12: "DEC",
}


def _procurar_template(docs_dir, nome_base):
    candidatos = [
        os.path.join(docs_dir, f"{nome_base}.docx"),
        os.path.join(docs_dir, nome_base),
    ]
    for caminho in candidatos:
        if os.path.exists(caminho):
            return caminho
    return None


def formatar_data_ponto(data_obj):
    return f"{data_obj.day:02d}.{data_obj.month:02d}.{data_obj.year}"


def formatar_data_mil(data_obj):
    return f"{data_obj.day:02d}{MESES_EN_ABREV[data_obj.month]}{str(data_obj.year)[-2:]}"


def _replacements_base(ano, mes, responsavel_welfare, telefone_servico, total_reimb, total_meals, senior_prt):
    hoje = date.today()
    ultimo_dia = calendar.monthrange(ano, mes)[1]
    data_inicio = date(ano, mes, 1)
    data_fim = date(ano, mes, ultimo_dia)

    return {
        "DATA_HOJE": formatar_data_ponto(hoje),
        "DATA_INICIO": formatar_data_mil(data_inicio),
        "DATA_FIM": formatar_data_mil(data_fim),
        "NR/ANO": f"NR/{str(ano)[-2:]}",
        "RESPONSAVEL_WELFARE": responsavel_welfare or "",
        "TELEFONE_SERVICO": telefone_servico or "",
        "TOTAL_REIMB": total_reimb or "",
        "TOTAL_MEALS": str(total_meals or 0),
        "SENIOR_PRT": senior_prt or "",
    }


def gerar_request_welfare_meals(
    docs_dir,
    destino,
    ano,
    mes,
    responsavel_welfare,
    telefone_servico,
    total_reimb,
    total_meals,
    senior_prt,
):
    template = _procurar_template(docs_dir, "request_welfare_meals")
    if not template:
        raise FileNotFoundError("docs/request_welfare_meals.docx")

    replacements = _replacements_base(
        ano=ano,
        mes=mes,
        responsavel_welfare=responsavel_welfare,
        telefone_servico=telefone_servico,
        total_reimb=total_reimb,
        total_meals=total_meals,
        senior_prt=senior_prt,
    )

    substituir_placeholders_docx(template, destino, replacements)


def gerar_request_welfare_meals_hoto(
    docs_dir,
    destino,
    ano,
    mes,
    responsavel_welfare,
    telefone_servico,
    total_reimb,
    total_meals,
    senior_prt,
    pessoas_hoto,
    data_inicio_override=None,
):
    template = _procurar_template(docs_dir, "request_welfare_meals_hoto")
    if not template:
        raise FileNotFoundError("docs/request_welfare_meals_hoto.docx")

    replacements = _replacements_base(
        ano=ano,
        mes=mes,
        responsavel_welfare=responsavel_welfare,
        telefone_servico=telefone_servico,
        total_reimb=total_reimb,
        total_meals=total_meals,
        senior_prt=senior_prt,
    )
    replacements["PESSOAS_HOTO"] = pessoas_hoto or ""
    if data_inicio_override:
        replacements["DATA_INICIO"] = data_inicio_override

    substituir_placeholders_docx(template, destino, replacements)
