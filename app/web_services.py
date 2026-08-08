"""Serviços de negócio usados pelo interface web.

Este módulo reutiliza as regras já consolidadas no ecrã de Welfare Individual
sem criar janelas Tkinter. Assim, a versão web e a versão histórica de desktop
continuam a calcular refeições, férias, Caixa e reembolsos da mesma forma.
"""

from datetime import date, datetime

from app.db import get_lingua
from app.individual import (
    REFEICAO_PEQUENO_ALMOCO,
    REFEICOES_WELFARE,
    WelfareIndividualWindow,
    XfaDistributionWindow,
)


class WebUserContext:
    def __init__(self, current_user):
        self.current_user = current_user
        self.idioma = "EN" if get_lingua() == "en" else "PT"

    def acessos(self):
        acessos = self.current_user.get("acessos") or []
        if not acessos and self.current_user.get("tipo_acesso"):
            acessos = [
                acesso.strip()
                for acesso in str(self.current_user["tipo_acesso"]).split(",")
                if acesso.strip()
            ]
        return set(acessos)

    def is_admin(self):
        return "Administrador" in self.acessos()


class IndividualService(WelfareIndividualWindow):
    """Versão sem interface gráfica do motor de Welfare Individual."""

    def __init__(self, ano, mes, current_user, modo="welfare"):
        self.app = WebUserContext(current_user)
        self.ano_atual = int(ano)
        self.mes_atual = int(mes)
        self.modo = modo if modo in ("welfare", "pequeno_almoco") else "welfare"

        self.utilizadores = []
        self.mensais = {}
        self.individuais = {}
        self.day_offs = set()
        self.ferias = {}
        self.alteracoes_pendentes = {}
        self.hoto_selecionados = set()
        self._ctx_meses_export = {}

        self._valor_welfare_cache = 0
        self._valor_caixa_cache = 0
        self._horario_dfac_cache = {}
        self._inicio_semana_cache = ""
        self._mensais_set = set()
        self._day_infos = []
        self._ferias_intervalos = {}
        self._resumo_cache = {}
        self._dfac_cache = None

        self.carregar_dados()

    def _estado_welfare(self, user, data_str, refeicao):
        ativo = self.user_tem_refeicao_na_data(user, data_str, refeicao)
        ferias = ativo and self.user_em_ferias_na_refeicao(user, data_str, refeicao)
        marcado = ativo and not ferias and self.valor_efetivo(
            user["id"], data_str, refeicao
        )

        if not ativo:
            estado = "inativo"
        elif ferias:
            estado = "ferias"
        elif marcado:
            estado = "welfare"
        else:
            estado = "dfac"

        return {
            "estado": estado,
            "ativo": ativo,
            "ferias": ferias,
            "marcado": marcado,
        }

    def _estado_pequeno_almoco(self, user, data_str):
        ferias = self.user_em_ferias_na_refeicao(
            user, data_str, REFEICAO_PEQUENO_ALMOCO
        )
        ativo = self.user_tem_pequeno_almoco_na_data(user, data_str)
        marcado = ativo and self.valor_pequeno_almoco(user, data_str)

        if ferias and self.user_ativo_na_data(user, data_str):
            estado = "ferias"
        elif not ativo:
            estado = "inativo"
        elif marcado:
            estado = "dfac"
        else:
            estado = "nao_dfac"

        return {
            "estado": estado,
            "ativo": ativo,
            "ferias": ferias,
            "marcado": marcado,
        }

    def para_payload(self):
        dias = [
            {
                "dia": info["dia"],
                "data": info["data_str"],
                "dia_semana": info["weekday"],
                "fim_semana": info["fim_semana"],
                "day_off": info["day_off"],
                "especial": info["especial"],
            }
            for info in self._day_infos
        ]

        totais_dfac = {
            info["data_str"]: {
                "pequeno_almoco": 0,
                "almoco": 0,
                "jantar": 0,
            }
            for info in self._day_infos
        }
        linhas = []
        total_welfare = 0
        total_cohesion = 0
        total_reimbursement = 0
        total_caixa = 0
        total_reembolso_final = 0

        for user in self.utilizadores:
            celulas = {}
            for info in self._day_infos:
                data_str = info["data_str"]
                if self.modo == "pequeno_almoco":
                    pequeno_almoco = self._estado_pequeno_almoco(user, data_str)
                    celulas[data_str] = {
                        "pequeno_almoco": pequeno_almoco,
                    }
                    if pequeno_almoco["marcado"]:
                        totais_dfac[data_str]["pequeno_almoco"] += 1
                else:
                    almoco = self._estado_welfare(user, data_str, "Almoço")
                    jantar = self._estado_welfare(user, data_str, "Jantar")
                    celulas[data_str] = {
                        "almoco": almoco,
                        "jantar": jantar,
                    }
                    if almoco["estado"] == "dfac":
                        totais_dfac[data_str]["almoco"] += 1
                    if jantar["estado"] == "dfac":
                        totais_dfac[data_str]["jantar"] += 1

            welfare, cohesion, reimbursement = self.calcular_resumo_user(user)
            caixa = self.calcular_caixa_user(user)
            reembolso_final = max(0, int(reimbursement or 0) - int(caixa or 0))

            total_welfare += welfare
            total_cohesion += cohesion
            total_reimbursement += reimbursement
            total_caixa += caixa
            total_reembolso_final += reembolso_final

            linhas.append(
                {
                    "id": user["id"],
                    "nim": user.get("nim") or "",
                    "posto": user.get("posto") or "",
                    "nome": user.get("nome") or "",
                    "sobrenome": user.get("sobrenome") or "",
                    "identificacao": self.identificacao(user),
                    "antiguidade": user.get("antiguidade") or "",
                    "data_chegada": user.get("data_chegada") or "",
                    "data_partida": user.get("data_partida") or "",
                    "snr": bool(int(user.get("snr") or 0)),
                    "responsavel_welfare": bool(
                        int(user.get("responsavel_welfare") or 0)
                    ),
                    "celulas": celulas,
                    "resumo": {
                        "welfare": welfare,
                        "cohesion": cohesion,
                        "reimbursement": reimbursement,
                        "caixa": caixa,
                        "reembolso_final": reembolso_final,
                    },
                }
            )

        semanas = []
        for dias_mes, numero, inicio, datas in self.semanas_visiveis_mes():
            semanas.append(
                {
                    "numero": numero,
                    "inicio": inicio.isoformat(),
                    "dias_mes": dias_mes,
                    "datas": [data_ref.isoformat() for data_ref in datas],
                }
            )

        return {
            "ano": self.ano_atual,
            "mes": self.mes_atual,
            "modo": self.modo,
            "dias": dias,
            "linhas": linhas,
            "totais_dfac": totais_dfac,
            "totais": {
                "welfare": total_welfare,
                "cohesion": total_cohesion,
                "reimbursement": total_reimbursement,
                "caixa": total_caixa,
                "reembolso_final": total_reembolso_final,
            },
            "semanas": semanas,
            "valor_welfare": self.valor_welfare_numero(),
            "valor_caixa": self.valor_caixa_numero(),
            "mes_trancado": self._mes_esta_trancado(),
            "pode_editar": self.pode_editar(),
            "pode_trancar_mes": self.app.is_admin()
            or self.is_responsavel_welfare(),
            "pode_exportar_semanas": self.pode_exportar_semanas(),
            "responsavel_welfare": self.is_responsavel_welfare(),
        }

    def _mes_esta_trancado(self):
        from app.db import is_mes_trancado

        return is_mes_trancado(self.ano_atual, self.mes_atual)

    def utilizadores_por_ids(self, ids):
        ids_normalizados = {int(user_id) for user_id in ids}
        return [
            user
            for user in self.utilizadores
            if int(user.get("id")) in ids_normalizados
        ]

    def validar_selecao_hoto(self, ids):
        selecionados = self.utilizadores_por_ids(ids)
        if not selecionados:
            raise ValueError("Seleciona pelo menos uma pessoa.")

        partidas = {
            self._data_partida_para_comparar(user) for user in selecionados
        }
        if len(partidas) != 1:
            detalhes = ", ".join(
                f"{self.identificacao_curta(user)}: "
                f"{self._data_partida_para_comparar(user) or '-'}"
                for user in selecionados
            )
            raise ValueError(
                "As pessoas selecionadas têm datas/horas de partida diferentes. "
                + detalhes
            )
        return selecionados


def calcular_distribuicao_xfa(
    individual,
    utilizador_ids,
    stock,
    tipo_valor="reembolso",
    valores_manuais=None,
):
    """Calcula a distribuição XFA usando o mesmo algoritmo do desktop."""
    selecionados = individual.utilizadores_por_ids(utilizador_ids)
    if not selecionados:
        raise ValueError(
            "Seleciona pelo menos uma pessoa para efetuar a Distribuição XFA."
        )

    stock_normalizado = {}
    for denominacao in XfaDistributionWindow.DENOMINACOES:
        try:
            quantidade = int(stock.get(str(denominacao), stock.get(denominacao, 0)))
        except (TypeError, ValueError):
            raise ValueError(f"Quantidade inválida para a nota {denominacao}.")
        if quantidade < 0:
            raise ValueError(f"Quantidade inválida para a nota {denominacao}.")
        stock_normalizado[denominacao] = quantidade

    manuais = valores_manuais or {}
    linhas = []
    for user in selecionados:
        welfare, cohesion, reimbursement = individual.calcular_resumo_user(user)
        caixa = individual.calcular_caixa_user(user)
        reembolso_final = max(0, int(reimbursement or 0) - int(caixa or 0))
        valor = (
            reembolso_final
            if tipo_valor == "final"
            else int(reimbursement or 0)
        )

        if manuais:
            valor_manual = manuais.get(str(user["id"]), manuais.get(user["id"], valor))
            try:
                valor = int(valor_manual)
            except (TypeError, ValueError):
                raise ValueError(
                    f"Valor inválido para {individual.identificacao_curta(user)}."
                )
            if valor < 0:
                raise ValueError(
                    f"Valor inválido para {individual.identificacao_curta(user)}."
                )

        if valor <= 0:
            continue

        linhas.append(
            {
                "id": user["id"],
                "posto": (user.get("posto") or "").strip(),
                "sobrenome": (user.get("sobrenome") or "").strip().upper(),
                "nome": (user.get("nome") or "").strip().upper(),
                "welfare": welfare,
                "cohesion": cohesion,
                "reimbursement": valor,
                "reimbursement_original": reimbursement,
                "caixa": caixa,
                "reembolso_final": reembolso_final,
                "antiguidade": (user.get("antiguidade") or "").strip(),
                "snr": int(user.get("snr") or 0),
            }
        )

    if not linhas:
        raise ValueError("Não existem valores positivos para distribuir.")

    total_necessario = sum(int(linha["reimbursement"]) for linha in linhas)
    total_disponivel = sum(
        denominacao * quantidade
        for denominacao, quantidade in stock_normalizado.items()
    )
    if total_disponivel < total_necessario:
        raise ValueError(
            "Valor disponível insuficiente. "
            f"Disponível: {total_disponivel:,} | Necessário: {total_necessario:,}"
        )

    calculador = XfaDistributionWindow.__new__(XfaDistributionWindow)
    resultados, sobra, falhas = calculador._calcular_distribuicao_equilibrada(
        linhas, stock_normalizado
    )

    return {
        "gerado_em": datetime.now().isoformat(timespec="seconds"),
        "total_necessario": total_necessario,
        "total_disponivel": total_disponivel,
        "sobra": {str(chave): valor for chave, valor in sobra.items()},
        "falhas": falhas,
        "resultados": [
            {
                "id": linha["id"],
                "identificacao": calculador._formatar_identificacao(linha),
                "valor": linha["reimbursement"],
                "notas": {str(chave): valor for chave, valor in combo.items()},
            }
            for linha, combo in resultados
        ],
    }
