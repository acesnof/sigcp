import json
import tempfile
import unittest
import json
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import Mock, patch

from app import audit_service, db
from app.config import MASTER_NIM, MASTER_PASSWORD
from app.security import hash_password
from app.web_app import create_web_app


class WebAppTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "web_test.sqlite3"
        self.db_patch = patch.object(db, "DB_PATH", str(self.db_path))
        self.db_patch.start()
        db.init_db()

        self.app = create_web_app()
        self.app.config.update(TESTING=True)
        self.client = self.app.test_client()

    def tearDown(self):
        self.db_patch.stop()
        self.temp_dir.cleanup()

    def login(self):
        response = self.client.post(
            "/api/login",
            json={"nim": MASTER_NIM, "password": MASTER_PASSWORD},
        )
        self.assertEqual(200, response.status_code)
        bootstrap = self.client.get("/api/bootstrap").get_json()
        self.assertTrue(bootstrap["authenticated"])
        return bootstrap["csrf_token"]

    def create_user(
        self,
        nim,
        *,
        snr=0,
        responsavel=0,
        partida="",
        acesso="Gestão Welfare Individual",
    ):
        salt, pwd_hash = hash_password("Teste123!")
        user_id = db.db_execute_return_id(
            """
            INSERT INTO utilizadores (
                nim, posto, nome, sobrenome, data_chegada, data_partida,
                antiguidade, snr, telemovel_servico, responsavel_welfare,
                tipo_acesso, password_salt, password_hash, master
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
            """,
            (
                nim,
                "OR-5",
                "Nome",
                nim,
                "2026-01-01 08:00",
                partida,
                "2020-01-01",
                snr,
                "600000000" if responsavel else "",
                responsavel,
                acesso,
                salt,
                pwd_hash,
            ),
        )
        db.set_utilizador_acessos(user_id, [acesso])
        return user_id

    def login_as(self, nim, password="Teste123!"):
        response = self.client.post(
            "/api/login",
            json={"nim": nim, "password": password},
        )
        self.assertEqual(200, response.status_code)
        return self.client.get("/api/bootstrap").get_json()["csrf_token"]

    def test_login_bootstrap_calendar_and_individual(self):
        landing = self.client.get("/")
        self.assertEqual(200, landing.status_code)
        html = landing.get_data(as_text=True)
        self.assertIn("<h1>SIGCP</h1>", html)
        self.assertIn("Sistema Integrado de Gestão do Contingente Português", html)
        self.assertEqual(2, html.count("data-vacation-notification-count"))

        anonymous = self.client.get("/api/bootstrap").get_json()
        self.assertFalse(anonymous["authenticated"])

        csrf = self.login()
        headers = {"X-CSRF-Token": csrf}

        calendar_response = self.client.get("/api/calendar?ano=2026&mes=7")
        self.assertEqual(200, calendar_response.status_code)
        self.assertEqual(0, calendar_response.get_json()["total"])

        save_response = self.client.post(
            "/api/welfares",
            json={
                "data": "2026-07-31",
                "refeicao": "Almoço",
                "tipo": "Welfare",
                "prato": "Bacalhau",
                "sobremesa": "Fruta",
                "observacao": "Teste",
            },
            headers=headers,
        )
        self.assertEqual(200, save_response.status_code)

        calendar_data = self.client.get(
            "/api/calendar?ano=2026&mes=7"
        ).get_json()
        self.assertEqual(1, calendar_data["total"])
        self.assertEqual(
            "Bacalhau",
            calendar_data["welfares"]["2026-07-31"][0]["prato"],
        )
        self.assertEqual(
            "Recanto",
            calendar_data["welfares"]["2026-07-31"][0]["local"],
        )

        save_in_restaurant = self.client.post(
            "/api/welfares",
            json={
                "data": "2026-07-31",
                "refeicao": "Almoço",
                "tipo": "Welfare",
                "local": "Restaurante",
                "prato": "Bacalhau",
                "sobremesa": "Fruta",
            },
            headers=headers,
        )
        self.assertEqual(200, save_in_restaurant.status_code)
        self.assertEqual(
            "Restaurante",
            self.client.get("/api/calendar?ano=2026&mes=7").get_json()["welfares"]["2026-07-31"][0]["local"],
        )

        individual = self.client.get(
            "/api/individual?ano=2026&mes=7&modo=welfare"
        )
        self.assertEqual(200, individual.status_code)
        self.assertIn("linhas", individual.get_json()["data"])

    def test_instance_marker_and_browser_lifecycle_are_available_before_login(self):
        marker = self.client.get("/api/instance")
        self.assertEqual(200, marker.status_code)
        self.assertEqual("SIGCP", marker.get_json()["application"])
        self.assertTrue(marker.get_json()["instance"])

        callback = Mock()
        self.app.config["BROWSER_LIFECYCLE_CALLBACK"] = callback
        heartbeat = self.client.post(
            "/api/lifecycle",
            json={"tab_id": "browser-tab-1", "event": "heartbeat"},
        )
        self.assertEqual(200, heartbeat.status_code)
        callback.assert_called_once_with("browser-tab-1", "heartbeat")

        invalid = self.client.post(
            "/api/lifecycle", json={"tab_id": "", "event": "close"}
        )
        self.assertEqual(400, invalid.status_code)

        self.login()
        callback.reset_mock()
        close = self.client.post(
            "/api/lifecycle",
            json={"tab_id": "browser-tab-1", "event": "close"},
        )
        self.assertEqual(200, close.status_code)
        callback.assert_called_once_with("browser-tab-1", "close")

    def test_admin_previews_and_selectively_imports_portugal_holidays(self):
        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return json.dumps([
                    {"date": "2027-01-01", "name": "Ano Novo", "nationalHoliday": True, "holidayTypes": ["Public"]},
                    {"date": "2027-04-25", "name": "Dia da Liberdade", "nationalHoliday": True, "holidayTypes": ["Public"]},
                    {"date": "2027-06-13", "name": "Feriado local", "nationalHoliday": False, "holidayTypes": ["Public"]},
                ]).encode("utf-8")

        csrf = self.login()
        headers = {"X-CSRF-Token": csrf}
        db.db_execute(
            "INSERT INTO feriados (data, descricao, ativo) VALUES (?, ?, 1)",
            ("2027-01-01", "Ano Novo existente"),
        )
        with patch("app.web_app.urllib.request.urlopen", return_value=FakeResponse()):
            preview = self.client.get(
                "/api/vacations/holidays/import-preview?ano=2027"
            )
        self.assertEqual(200, preview.status_code, preview.get_json())
        holidays = preview.get_json()["data"]["feriados"]
        self.assertEqual(2, len(holidays))
        self.assertTrue(holidays[0]["existente"])
        self.assertFalse(holidays[1]["existente"])

        imported = self.client.post(
            "/api/vacations/holidays/import",
            json={
                "ano": 2027,
                "feriados": [
                    {"data": "2027-04-25", "descricao": "Dia da Liberdade"}
                ],
            },
            headers=headers,
        )
        self.assertEqual(200, imported.status_code, imported.get_json())
        self.assertEqual(1, imported.get_json()["imported"])
        listed = self.client.get("/api/vacations/holidays?ano=2027").get_json()["holidays"]
        self.assertEqual(2, len(listed))

        self.create_user("holiday_denied", acesso="Pessoal/Gestão Férias")
        self.login_as("holiday_denied")
        denied = self.client.get(
            "/api/vacations/holidays/import-preview?ano=2027"
        )
        self.assertEqual(403, denied.status_code)

    def test_successful_login_triggers_backup_callback(self):
        backup = Mock(return_value="backup.sqlite3")
        self.app.config["BACKUP_CALLBACK"] = backup

        denied = self.client.post(
            "/api/login",
            json={"nim": MASTER_NIM, "password": "incorreta"},
        )
        self.assertEqual(401, denied.status_code)
        backup.assert_not_called()

        accepted = self.client.post(
            "/api/login",
            json={"nim": MASTER_NIM, "password": MASTER_PASSWORD},
        )
        self.assertEqual(200, accepted.status_code)
        self.assertTrue(accepted.get_json()["backup"]["ok"])
        backup.assert_called_once_with()

    def test_person_position_number_is_created_and_updated(self):
        csrf = self.login()
        headers = {"X-CSRF-Token": csrf}
        created = self.client.post(
            "/api/users",
            json={
                "nim": "posicao_teste",
                "posto": "OR-4",
                "antiguidade": "2021-03-04",
                "nome": "Nome",
                "sobrenome": "Posição",
                "area_funcional": "Operações",
                "posicao_numero": "OPS-017",
                "data_chegada": "2026-01-01T08:00",
                "data_partida": "2026-12-31T20:00",
                "telemovel_servico": "",
                "snr": False,
                "responsavel_welfare": False,
                "ferias_direito_override": 27.5,
                "missao_prorrogada": False,
                "notas_ferias": "Teste do novo campo",
                "password": "Teste123!",
                "confirmar_password": "Teste123!",
                "acessos": ["Leitura"],
            },
            headers=headers,
        )
        self.assertEqual(200, created.status_code, created.get_json())
        person = created.get_json()["user"]
        self.assertEqual("OPS-017", person["posicao_numero"])
        self.assertEqual(
            "OPS-017",
            db.db_one(
                "SELECT posicao_numero FROM utilizadores WHERE id=?", (person["id"],)
            )["posicao_numero"],
        )

        updated = self.client.put(
            f"/api/vacations/people/{person['id']}",
            json={
                "area_funcional": "Operações",
                "posicao_numero": "OPS-021",
                "data_chegada": "2026-01-01T08:00",
                "data_partida": "2026-12-31T20:00",
                "ferias_direito_override": 28,
                "missao_prorrogada": True,
                "notas_ferias": "Atualizado",
            },
            headers=headers,
        )
        self.assertEqual(200, updated.status_code, updated.get_json())
        self.assertEqual(
            "OPS-021",
            db.db_one(
                "SELECT posicao_numero FROM utilizadores WHERE id=?", (person["id"],)
            )["posicao_numero"],
        )

    def test_people_are_ordered_by_rank_and_antiquity_everywhere(self):
        future = (date.today() + timedelta(days=365)).isoformat()
        past_recent = (date.today() - timedelta(days=1)).isoformat()
        past_old = (date.today() - timedelta(days=90)).isoformat()
        people = {
            "active_of2": self.create_user("order_active_of2", partida=future),
            "active_or9": self.create_user("order_active_or9", partida=future),
            "active_or5_old": self.create_user("order_active_or5_old", partida=future),
            "active_or5_new": self.create_user("order_active_or5_new", partida=future),
            "departed_of6": self.create_user("order_departed_of6", partida=past_old),
            "departed_or8": self.create_user("order_departed_or8", partida=past_recent),
        }
        values = {
            "active_of2": ("OF-2", "2022-01-01"),
            "active_or9": ("OR-9", "2010-01-01"),
            "active_or5_old": ("OR-5", "2018-01-01"),
            "active_or5_new": ("OR-5", "2021-01-01"),
            "departed_of6": ("OF-6", "2025-01-01"),
            "departed_or8": ("OR-8", "2012-01-01"),
        }
        for label, person_id in people.items():
            posto, antiguidade = values[label]
            db.db_execute(
                "UPDATE utilizadores SET posto=?, antiguidade=? WHERE id=?",
                (posto, antiguidade, person_id),
            )

        self.login()
        response = self.client.get("/api/users?todos=1")

        self.assertEqual(200, response.status_code)
        relevant = set(people.values())
        ordered = [
            person["id"]
            for person in response.get_json()["users"]
            if person["id"] in relevant
        ]
        self.assertEqual(
            [
                people["departed_of6"],
                people["active_of2"],
                people["active_or9"],
                people["departed_or8"],
                people["active_or5_old"],
                people["active_or5_new"],
            ],
            ordered,
        )

    def test_dish_roster_is_visible_to_all_but_only_monthly_manager_can_generate(self):
        self.create_user("dish_reader", acesso="Leitura")
        self.create_user("dish_manager", acesso="Gestão Welfare Mensal")

        reader_csrf = self.login_as("dish_reader")
        visible = self.client.get("/api/dish-roster?ano=2026&mes=8")
        denied = self.client.post(
            "/api/dish-roster/generate",
            json={"ano": 2026, "mes": 8},
            headers={"X-CSRF-Token": reader_csrf},
        )
        self.assertEqual(200, visible.status_code, visible.get_json())
        self.assertEqual(403, denied.status_code, denied.get_json())

        manager_csrf = self.login_as("dish_manager")
        boot = self.client.get("/api/bootstrap").get_json()
        generated = self.client.post(
            "/api/dish-roster/generate",
            json={"ano": 2026, "mes": 8},
            headers={"X-CSRF-Token": manager_csrf},
        )
        self.assertTrue(boot["permissions"]["escala_loica_gerir"])
        self.assertEqual(200, generated.status_code, generated.get_json())

    def test_cash_management_is_restricted_but_consultation_is_public(self):
        self.create_user("cash_reader", acesso="Leitura")
        self.create_user("cash_manager", acesso="Gestão Caixa")

        reader_csrf = self.login_as("cash_reader")
        self.assertFalse(self.client.get("/api/bootstrap").get_json()["permissions"]["caixa"])
        self.assertEqual(403, self.client.get("/api/cash?inicio=2026-08-01&fim=2026-08-31").status_code)
        self.assertEqual(200, self.client.get("/api/cash/consultation?inicio=2026-08-01&fim=2026-08-31").status_code)
        denied = self.client.post("/api/cash", json={"tipo":"entrada", "data":"2026-08-01", "valor":100, "descritivo":"Teste"}, headers={"X-CSRF-Token":reader_csrf})
        self.assertEqual(403, denied.status_code)

        manager_csrf = self.login_as("cash_manager")
        self.assertTrue(self.client.get("/api/bootstrap").get_json()["permissions"]["caixa"])
        created = self.client.post("/api/cash", json={"tipo":"saida", "data":"2026-08-03", "valor":250, "descritivo":"Compra", "pessoa_gasto":"OR-5 Teste", "local":"Bangui"}, headers={"X-CSRF-Token":manager_csrf})
        self.assertEqual(200, created.status_code, created.get_json())
        report = self.client.get("/api/cash?inicio=2026-08-01&fim=2026-08-31").get_json()["data"]
        self.assertEqual(250, report["total_saidas"])
        self.assertEqual("OR-5 Teste", report["movimentos"][0]["pessoa_gasto"])

    def test_admin_can_register_both_dish_roster_signatures_outside_saturday(self):
        first = self.create_user("dish_signature_1", acesso="Leitura")
        second = self.create_user("dish_signature_2", acesso="Leitura")
        saturday = date.today() + timedelta(days=30)
        saturday += timedelta(days=(5 - saturday.weekday()) % 7)
        db.db_execute(
            """INSERT INTO escala_loica (
                   fim_semana, militar_1_id, militar_2_id
               ) VALUES (?, ?, ?)""",
            (saturday.isoformat(), first, second),
        )
        csrf = self.login()
        headers = {"X-CSRF-Token": csrf}

        roster = self.client.get(
            f"/api/dish-roster?ano={saturday.year}&mes={saturday.month}"
        ).get_json()["data"]
        row = next(
            item for item in roster["linhas"]
            if item["fim_semana"] == saturday.isoformat()
        )
        self.assertTrue(row["pode_assinar_1"])
        self.assertTrue(row["pode_assinar_2"])

        for slot in (1, 2):
            response = self.client.put(
                f"/api/dish-roster/{saturday.isoformat()}/signature/{slot}",
                json={"assinada": True},
                headers=headers,
            )
            self.assertEqual(200, response.status_code, response.get_json())
        saved = db.db_one(
            "SELECT * FROM escala_loica WHERE fim_semana=?",
            (saturday.isoformat(),),
        )
        self.assertEqual(1, saved["assinatura_1"])
        self.assertEqual(1, saved["assinatura_2"])

    def test_only_admin_can_assign_person_functions(self):
        manager_id = self.create_user(
            "gestor_pessoal", acesso="Pessoal/Gestão Férias"
        )
        target_id = self.create_user(
            "funcoes_protegidas", snr=1, responsavel=1,
            acesso="Pessoal/Gestão Férias",
        )
        csrf = self.login_as("gestor_pessoal")
        headers = {"X-CSRF-Token": csrf}

        updated = self.client.put(
            f"/api/users/{target_id}",
            json={
                "nim": "funcoes_protegidas",
                "posto": "OR-5",
                "antiguidade": "2020-01-01",
                "nome": "Nome",
                "sobrenome": "Protegidas",
                "area_funcional": "HQ",
                "posicao_numero": "HQ-01",
                "data_chegada": "2026-01-01T08:00",
                "data_partida": "2026-12-31T20:00",
                "telemovel_servico": "600000000",
                "snr": False,
                "responsavel_welfare": False,
                "ferias_direito_override": "",
                "missao_prorrogada": False,
                "notas_ferias": "",
                "password": "",
                "confirmar_password": "",
            },
            headers=headers,
        )
        self.assertEqual(200, updated.status_code, updated.get_json())
        protected = db.db_one(
            "SELECT snr, responsavel_welfare FROM utilizadores WHERE id=?",
            (target_id,),
        )
        self.assertEqual(1, protected["snr"])
        self.assertEqual(1, protected["responsavel_welfare"])

        created = self.client.post(
            "/api/users",
            json={
                "nim": "funcoes_nao_autorizadas",
                "posto": "OR-4",
                "nome": "Novo",
                "sobrenome": "Militar",
                "snr": True,
                "responsavel_welfare": True,
                "telemovel_servico": "600000001",
                "password": "Teste123!",
                "confirmar_password": "Teste123!",
            },
            headers=headers,
        )
        self.assertEqual(200, created.status_code, created.get_json())
        created_user = db.db_one(
            "SELECT snr, responsavel_welfare FROM utilizadores WHERE id=?",
            (created.get_json()["user"]["id"],),
        )
        self.assertEqual(0, created_user["snr"])
        self.assertEqual(0, created_user["responsavel_welfare"])

    def test_snr_can_name_one_date_bound_substitute_and_clear_it(self):
        snr_id = self.create_user(
            "snr_titular", snr=1, acesso="Gestão Welfare Individual"
        )
        substitute_id = self.create_user("snr_substituto", acesso="Leitura")
        other_id = self.create_user("snr_substituto_2", acesso="Leitura")
        start = (date.today() - timedelta(days=1)).isoformat()
        end = (date.today() + timedelta(days=2)).isoformat()

        csrf = self.login_as("snr_titular")
        headers = {"X-CSRF-Token": csrf}
        bootstrap = self.client.get("/api/bootstrap").get_json()
        self.assertTrue(bootstrap["permissions"]["snr_titular"])
        self.assertTrue(bootstrap["permissions"]["snr_substituicao"])
        self.assertTrue(bootstrap["permissions"]["pessoal"])
        self.assertFalse(bootstrap["permissions"]["pessoal_editar"])
        self.assertEqual(200, self.client.get("/api/users").status_code)

        named = self.client.put(
            f"/api/users/{substitute_id}/snr-substitution",
            json={
                "snr_substituto": True,
                "snr_substituto_inicio": start,
                "snr_substituto_fim": end,
            },
            headers=headers,
        )
        self.assertEqual(200, named.status_code, named.get_json())
        stored = db.db_one(
            "SELECT * FROM utilizadores WHERE id=?", (substitute_id,)
        )
        self.assertEqual(1, stored["snr_substituto"])
        self.assertEqual(start, stored["snr_substituto_inicio"])
        self.assertEqual(end, stored["snr_substituto_fim"])

        substitute_csrf = self.login_as("snr_substituto")
        substitute_bootstrap = self.client.get("/api/bootstrap").get_json()
        self.assertTrue(substitute_bootstrap["permissions"]["snr"])
        self.assertFalse(substitute_bootstrap["permissions"]["snr_titular"])
        self.assertTrue(substitute_bootstrap["permissions"]["ferias_decidir"])
        self.assertFalse(substitute_bootstrap["permissions"]["snr_substituicao"])
        denied = self.client.put(
            f"/api/users/{other_id}/snr-substitution",
            json={"snr_substituto": False},
            headers={"X-CSRF-Token": substitute_csrf},
        )
        self.assertEqual(403, denied.status_code)

        csrf = self.login_as("snr_titular")
        headers = {"X-CSRF-Token": csrf}
        overlap = self.client.put(
            f"/api/users/{other_id}/snr-substitution",
            json={
                "snr_substituto": True,
                "snr_substituto_inicio": date.today().isoformat(),
                "snr_substituto_fim": end,
            },
            headers=headers,
        )
        self.assertEqual(400, overlap.status_code)

        cleared = self.client.put(
            f"/api/users/{substitute_id}/snr-substitution",
            json={
                "snr_substituto": False,
                "snr_substituto_inicio": "",
                "snr_substituto_fim": "",
            },
            headers=headers,
        )
        self.assertEqual(200, cleared.status_code, cleared.get_json())
        cleared_row = db.db_one(
            "SELECT * FROM utilizadores WHERE id=?", (substitute_id,)
        )
        self.assertEqual(0, cleared_row["snr_substituto"])
        self.assertEqual("", cleared_row["snr_substituto_inicio"])
        self.assertEqual("", cleared_row["snr_substituto_fim"])

        admin_csrf = self.login()
        future_start = (date.today() + timedelta(days=10)).isoformat()
        future_end = (date.today() + timedelta(days=20)).isoformat()
        admin_update = self.client.put(
            f"/api/users/{substitute_id}",
            json={
                "nim": "snr_substituto",
                "posto": "OR-5",
                "antiguidade": "2020-01-01",
                "nome": "Nome",
                "sobrenome": "snr_substituto",
                "data_chegada": "2026-01-01T08:00",
                "data_partida": "",
                "telemovel_servico": "",
                "snr": False,
                "responsavel_welfare": False,
                "area_funcional": "Não definido",
                "posicao_numero": "",
                "ferias_direito_override": "",
                "missao_prorrogada": False,
                "notas_ferias": "",
                "password": "",
                "confirmar_password": "",
                "acessos": ["Leitura"],
                "snr_substituto": True,
                "snr_substituto_inicio": future_start,
                "snr_substituto_fim": future_end,
            },
            headers={"X-CSRF-Token": admin_csrf},
        )
        self.assertEqual(200, admin_update.status_code, admin_update.get_json())
        self.login_as("snr_substituto")
        self.assertFalse(
            self.client.get("/api/bootstrap").get_json()["permissions"]["snr"]
        )

    def test_only_monthly_management_admin_or_welfare_responsible_edit_calendar_meals(self):
        self.create_user("calendar_monthly", acesso="Gestão Welfare Mensal")
        self.create_user(
            "calendar_responsible", responsavel=1, acesso="Leitura"
        )
        self.create_user("calendar_menu_legacy", acesso="Gestão Ementa")
        self.create_user("calendar_reader", acesso="Leitura")

        payload = {
            "data": "2026-09-10",
            "refeicao": "Almoço",
            "tipo": "Welfare",
            "prato": "Teste",
            "sobremesa": "Fruta",
            "observacao": "",
        }
        for nim, expected in (
            ("calendar_monthly", 200),
            ("calendar_responsible", 200),
            ("calendar_menu_legacy", 403),
            ("calendar_reader", 403),
        ):
            csrf = self.login_as(nim)
            boot = self.client.get("/api/bootstrap").get_json()
            allowed = expected == 200
            self.assertEqual(allowed, boot["permissions"]["editar_welfare"])
            self.assertEqual(allowed, boot["permissions"]["editar_ementa"])
            candidate = dict(payload)
            candidate["data"] = (
                date(2026, 9, 10) + timedelta(days=len(nim))
            ).isoformat()
            response = self.client.post(
                "/api/welfares",
                json=candidate,
                headers={"X-CSRF-Token": csrf},
            )
            self.assertEqual(expected, response.status_code, response.get_json())

    def test_audit_is_redacted_filtered_paginated_and_admin_only(self):
        csrf = self.login()
        headers = {"X-CSRF-Token": csrf}
        secret = "SegredoAudit123!"
        created = self.client.post(
            "/api/users",
            json={
                "nim": "audit_target",
                "posto": "OR-4",
                "nome": "Alvo",
                "sobrenome": "Auditoria",
                "password": secret,
                "confirmar_password": secret,
                "acessos": ["Leitura"],
            },
            headers=headers,
        )
        self.assertEqual(200, created.status_code, created.get_json())

        filtered = self.client.get(
            "/api/audit?pesquisa=audit_target&metodo=POST"
        )
        self.assertEqual(200, filtered.status_code, filtered.get_json())
        entries = filtered.get_json()["data"]["registos"]
        self.assertTrue(entries)
        entry = next(item for item in entries if item["entidade"] == "api_create_user")
        encoded_details = json.dumps(entry["detalhes"], ensure_ascii=False)
        self.assertNotIn(secret, encoded_details)
        self.assertIn("[OCULTO]", encoded_details)

        actor = db.db_one(
            "SELECT * FROM utilizadores WHERE nim=?", (MASTER_NIM,)
        )
        for index in range(15):
            audit_service.record(
                user=actor,
                endpoint="teste_paginacao",
                method="PUT",
                route=f"/api/teste/{index}",
                payload={"sequencia": index},
            )
        first_page = self.client.get("/api/audit?limite=10").get_json()["data"]
        self.assertEqual(10, len(first_page["registos"]))
        self.assertTrue(first_page["tem_mais"])
        second_page = self.client.get(
            f"/api/audit?limite=10&cursor={first_page['proximo_cursor']}"
        ).get_json()["data"]
        self.assertTrue(second_page["registos"])
        self.assertLess(
            second_page["registos"][0]["id"], first_page["registos"][-1]["id"]
        )

        self.client.post("/api/logout", headers=headers)
        self.create_user("audit_denied", acesso="Pessoal/Gestão Férias")
        self.login_as("audit_denied")
        denied = self.client.get("/api/audit")
        self.assertEqual(403, denied.status_code)

    def test_backup_failure_reports_real_cause_without_blocking_login(self):
        backup = Mock(side_effect=PermissionError("servidor recusou a escrita"))
        self.app.config["BACKUP_CALLBACK"] = backup

        response = self.client.post(
            "/api/login",
            json={"nim": MASTER_NIM, "password": MASTER_PASSWORD},
        )

        self.assertEqual(200, response.status_code)
        payload = response.get_json()
        self.assertFalse(payload["backup"]["ok"])
        self.assertIn("servidor recusou a escrita", payload["backup"]["message"])
        self.assertTrue(self.client.get("/api/bootstrap").get_json()["authenticated"])

    def test_individual_month_lock_permissions_and_scope(self):
        self.create_user(
            "resp_lock",
            responsavel=1,
            acesso="Gestão Welfare Mensal",
        )
        self.create_user(
            "snr_lock",
            snr=1,
            acesso="Gestão Welfare Individual",
        )

        csrf = self.login_as("resp_lock")
        bootstrap = self.client.get("/api/bootstrap").get_json()
        self.assertTrue(bootstrap["permissions"]["individual"])
        self.assertTrue(bootstrap["permissions"]["trancar_mes"])

        locked = self.client.post(
            "/api/individual/month-lock",
            json={"ano": 2026, "mes": 8, "trancado": True},
            headers={"X-CSRF-Token": csrf},
        )
        self.assertEqual(200, locked.status_code)
        self.assertTrue(db.is_mes_trancado(2026, 8))

        individual = self.client.get(
            "/api/individual?ano=2026&mes=8&modo=welfare"
        ).get_json()["data"]
        self.assertTrue(individual["mes_trancado"])
        self.assertTrue(individual["pode_trancar_mes"])
        self.assertFalse(individual["pode_editar"])

        csrf = self.login_as("snr_lock")
        bootstrap = self.client.get("/api/bootstrap").get_json()
        self.assertFalse(bootstrap["permissions"]["trancar_mes"])
        self.assertFalse(
            self.client.get(
                "/api/individual?ano=2026&mes=8&modo=welfare"
            ).get_json()["data"]["pode_trancar_mes"]
        )
        denied = self.client.post(
            "/api/individual/month-lock",
            json={"ano": 2026, "mes": 8, "trancado": False},
            headers={"X-CSRF-Token": csrf},
        )
        self.assertEqual(403, denied.status_code)

        csrf = self.login()
        headers = {"X-CSRF-Token": csrf}
        markings = self.client.put(
            "/api/individual/markings",
            json={"ano": 2026, "mes": 8, "changes": []},
            headers=headers,
        )
        self.assertEqual(403, markings.status_code)

        # O fecho pertence exclusivamente ao Welfare Individual; o Calendário
        # mantém as permissões normais de edição.
        calendar_save = self.client.post(
            "/api/welfares",
            json={
                "data": "2026-08-04",
                "refeicao": "Almoço",
                "tipo": "Welfare",
                "prato": "Teste",
                "sobremesa": "Fruta",
                "observacao": "",
            },
            headers=headers,
        )
        self.assertEqual(200, calendar_save.status_code)
        calendar_data = self.client.get(
            "/api/calendar?ano=2026&mes=8"
        ).get_json()
        self.assertNotIn("trancado", calendar_data)
        self.assertNotIn("trancar", calendar_data["permissions"])

        unlocked = self.client.post(
            "/api/individual/month-lock",
            json={"ano": 2026, "mes": 8, "trancado": False},
            headers=headers,
        )
        self.assertEqual(200, unlocked.status_code)
        self.assertFalse(db.is_mes_trancado(2026, 8))

    def test_mutations_require_csrf_and_json_export_downloads(self):
        csrf = self.login()

        denied = self.client.put(
            "/api/settings",
            json={"valor_welfare": "1000"},
        )
        self.assertEqual(403, denied.status_code)

        saved = self.client.put(
            "/api/settings",
            json={"valor_welfare": "1000", "valor_caixa": "5000"},
            headers={"X-CSRF-Token": csrf},
        )
        self.assertEqual(200, saved.status_code)

        exported = self.client.get("/api/export/database.json")
        self.assertEqual(200, exported.status_code)
        self.assertEqual("application/json", exported.mimetype)
        self.assertIn(
            "sigcp_export_", exported.headers.get("Content-Disposition", "")
        )
        payload = json.loads(exported.data.decode("utf-8"))
        self.assertIn("utilizadores", payload["tabelas"])
        self.assertIn("app_settings", payload["tabelas"])

    def test_individual_documents_and_xfa(self):
        responsavel_id = self.create_user("resp", responsavel=1)
        hoto_1 = self.create_user("hoto1", partida="2099-12-31 10:00", snr=1)
        hoto_2 = self.create_user("hoto2", partida="2099-12-31 10:00")
        db.set_valor_welfare("2500")
        db.set_valor_caixa("15000")
        db.guardar_welfare(
            "2026-07-04",
            "Almoço",
            "Welfare",
            "Prato",
            "Fruta",
            "",
        )
        db.guardar_welfare(
            "2026-07-04",
            "Jantar",
            "Welfare",
            "Prato",
            "Fruta",
            "",
        )
        csrf = self.login_as("resp")
        headers = {"X-CSRF-Token": csrf}

        exports = [
            ({"tipo": "pdf_mes", "modo_paginas": 1}, "application/pdf"),
            (
                {"tipo": "excel_semana", "inicio_semana": "2026-06-29"},
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ),
            (
                {"tipo": "pdf_semana", "inicio_semana": "2026-06-29"},
                "application/pdf",
            ),
            (
                {"tipo": "excel_reembolso"},
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ),
            (
                {"tipo": "service_note"},
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ),
            (
                {"tipo": "request"},
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ),
            (
                {
                    "tipo": "excel_hoto",
                    "utilizador_ids": [hoto_1, hoto_2],
                },
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ),
            (
                {
                    "tipo": "request_hoto",
                    "utilizador_ids": [hoto_1, hoto_2],
                },
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ),
        ]
        for payload, mimetype in exports:
            payload.update({"ano": 2026, "mes": 7})
            with self.subTest(tipo=payload["tipo"]):
                response = self.client.post(
                    "/api/individual/export",
                    json=payload,
                    headers=headers,
                )
                self.assertEqual(200, response.status_code)
                self.assertEqual(mimetype, response.mimetype)
                self.assertGreater(len(response.data), 100)

        from io import BytesIO
        from openpyxl import load_workbook

        hoto_response = self.client.post(
            "/api/individual/export",
            json={
                "tipo": "excel_hoto",
                "utilizador_ids": [hoto_1, hoto_2],
                "ano": 2026,
                "mes": 7,
            },
            headers=headers,
        )
        hoto_book = load_workbook(BytesIO(hoto_response.data), read_only=True)
        self.assertEqual("01.07.2026", hoto_book["F1"]["B5"].value)
        self.assertEqual("31.12.2099", hoto_book["F1"]["C5"].value)
        hoto_book.close()

        xfa = self.client.post(
            "/api/xfa",
            json={
                "ano": 2026,
                "mes": 7,
                "utilizador_ids": [responsavel_id],
                "tipo_valor": "reembolso",
                "stock": {"10000": 0, "5000": 0, "2000": 0, "1000": 0, "500": 20},
            },
            headers=headers,
        )
        self.assertEqual(200, xfa.status_code)
        self.assertEqual(1, len(xfa.get_json()["data"]["resultados"]))


if __name__ == "__main__":
    unittest.main()
