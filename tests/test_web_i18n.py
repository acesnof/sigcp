import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import db
from app.web_app import create_web_app
from app.web_i18n import ENGLISH, translate, translate_messages


class WebTranslationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.database = patch.object(db, "DB_PATH", str(Path(self.directory.name) / "test.sqlite3"))
        self.database.start()
        self.addCleanup(self.database.stop)
        db.init_db()
        self.client = create_web_app().test_client()

    def test_login_and_shell_use_saved_language_before_authentication(self):
        for language, heading, label in (("en", "Welcome", "Leave Management"), ("pt", "Bem-vindo", "Gestão de Férias")):
            with self.subTest(language=language):
                db.set_lingua(language)
                response = self.client.get("/")
                self.assertEqual(response.status_code, 200)
                html = response.get_data(as_text=True)
                self.assertIn(f'<html lang="{language}">', html)
                self.assertIn(f'>{heading}<', html)
                self.assertIn(f'>{label}<', html)
                self.assertIn('id="i18n-catalog" type="application/json"', html)
                self.assertIn("script-src 'self'", response.headers["Content-Security-Policy"])
                boot = self.client.get("/api/bootstrap").get_json()
                self.assertFalse(boot["authenticated"])
                self.assertEqual(boot["language"], language)

    def test_api_errors_follow_language_and_keep_error_codes(self):
        for language, expected in (("en", "Enter the user and password."), ("pt", "Indica o utilizador e a password.")):
            db.set_lingua(language)
            response = self.client.post("/api/login", json={})
            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.get_json()["error"], expected)
            self.assertEqual(response.get_json()["code"], "erro")

    def test_dynamic_validation_preserves_values(self):
        db.set_lingua("en")
        self.assertEqual(
            translate("A ausência tem 31 dias; o limite configurado é 30."),
            "The absence lasts 31 days; the configured limit is 30.",
        )
        self.assertEqual(translate("João submeteu um período para decisão."), "João submitted a period for a decision.")

    def test_message_translation_does_not_change_business_or_user_data(self):
        db.set_lingua("en")
        payload = {"message": "Welfare guardado com sucesso.", "data": {
            "refeicao": "Almoço", "estado": "Pendente", "nome": "João",
            "observacao": "Welfare guardado com sucesso.", "message": "texto pessoal",
        }, "errors": ["A chegada não pode ser anterior à partida."]}
        localized = translate_messages(payload)
        self.assertEqual(localized["message"], "Welfare saved successfully.")
        self.assertEqual(localized["data"], payload["data"])
        self.assertEqual(localized["errors"], ["Arrival cannot precede departure."])
        self.assertEqual(payload["message"], "Welfare guardado com sucesso.")

    def test_english_welfare_save_keeps_portuguese_codes_and_free_text(self):
        with self.client.session_transaction() as session:
            session["superadmin"] = True
            session["csrf_token"] = "test-token"
        headers = {"X-CSRF-Token": "test-token"}
        saved = self.client.put("/api/settings", json={"lingua": "en"}, headers=headers)
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(saved.get_json()["message"], "Settings saved successfully.")
        boot = self.client.get("/api/bootstrap").get_json()
        self.assertEqual(boot["language"], "en")
        self.assertEqual(boot["config"]["meses"]["9"], "September")
        response = self.client.post("/api/welfares", json={
            "data": "2026-09-09", "refeicao": "Almoço", "tipo": "Welfare Livre",
            "prato": "Bacalhau à Brás", "observacao": "Guardar",
        }, headers=headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["message"], "Welfare saved successfully.")
        welfare = self.client.get("/api/calendar?ano=2026&mes=9").get_json()["welfares"]["2026-09-09"][0]
        self.assertEqual(welfare["refeicao"], "Almoço")
        self.assertEqual(welfare["tipo"], "Welfare Livre")
        self.assertEqual(welfare["prato"], "Bacalhau à Brás")
        self.assertEqual(welfare["observacao"], "Guardar")
        exported = self.client.get("/api/export/database.json")
        self.assertEqual(exported.status_code, 200)
        self.assertIn("attachment", exported.headers["Content-Disposition"])
        exported.close()

    def test_catalog_has_matching_placeholders_and_no_duplicates(self):
        path = Path(__file__).parents[1] / "app/translations/en.json"
        pairs = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=list)
        self.assertEqual(len(pairs), len(dict(pairs)))
        for source, target in ENGLISH.items():
            with self.subTest(source=source):
                self.assertEqual(sorted(re.findall(r"\{\d+\}", source)), sorted(re.findall(r"\{\d+\}", target)))
                self.assertTrue(target.strip())

    def test_all_explicit_web_translation_keys_exist(self):
        root = Path(__file__).parents[1]
        source = (root / "app/static/app.js").read_text(encoding="utf-8")
        keys = {json.loads(value) for value in re.findall(r'\bt\(("(?:[^"\\]|\\.)*")', source)}
        self.assertFalse(keys - ENGLISH.keys(), f"Missing translations: {keys - ENGLISH.keys()}")

    def test_startup_messages_read_saved_language_without_creating_a_database(self):
        import main
        db.set_lingua("en")
        with patch.object(main.config, "DB_PATH", db.DB_PATH):
            self.assertEqual(main._traduzir_mensagem("Atualização do SIGCP"), "SIGCP update")
        missing = Path(self.directory.name) / "missing.sqlite3"
        with patch.object(main.config, "DB_PATH", str(missing)):
            self.assertEqual(main._traduzir_mensagem("Atualização do SIGCP"), "Atualização do SIGCP")
        self.assertFalse(missing.exists())


if __name__ == "__main__":
    unittest.main()
