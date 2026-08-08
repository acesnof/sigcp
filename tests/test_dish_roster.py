import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import db, dish_roster


class DishRosterTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database = Path(self.temp_dir.name) / "dish.sqlite3"
        self.db_patch = patch.object(db, "DB_PATH", str(self.database))
        self.db_patch.start()
        db.init_db()

    def tearDown(self):
        self.db_patch.stop()
        self.temp_dir.cleanup()

    def person(self, nim, arrival, rank="OR-1", departure=""):
        return db.db_execute_return_id(
            """INSERT INTO utilizadores (
                nim, posto, nome, sobrenome, data_chegada, data_partida,
                antiguidade, tipo_acesso, password_salt, password_hash, master
            ) VALUES (?, ?, 'Nome', ?, ?, ?, '2020-01-01', 'Leitura', 'x', 'x', 0)""",
            (nim, rank, nim, arrival, departure),
        )

    def test_generation_respects_seven_days_departure_vacations_and_priority(self):
        vacation = self.person("ferias", "2026-01-01", "OR-1")
        oldest = self.person("antigo", "2026-01-01", "OR-5")
        next_person = self.person("seguinte", "2026-01-02", "OR-1")
        too_new = self.person("recem_chegado", "2026-07-27", "OR-1")
        self.person("parte_sabado", "2026-01-01", "OF-6", "2026-08-01")
        db.db_execute(
            """INSERT INTO ferias (
                utilizador_id, data_hora_inicio, data_hora_fim, estado
            ) VALUES (?, '2026-08-01 00:00', '2026-08-02 23:59', 'Aprovado')""",
            (vacation,),
        )

        dish_roster.generate(2026, 8)
        first = dish_roster.get_row("2026-08-01")

        self.assertEqual(oldest, first["militar_1_id"])
        self.assertEqual(next_person, first["militar_2_id"])
        self.assertNotIn(too_new, (first["militar_1_id"], first["militar_2_id"]))
        payload = dish_roster.payload(2026, 8)
        self.assertEqual(18, len(payload["linhas"]))
        self.assertTrue(payload["linhas"][0]["observacoes"])

    def test_pdf_is_generated_in_a4_roster_format(self):
        self.person("militar1", "2026-01-01")
        self.person("militar2", "2026-01-01", "OR-2")
        dish_roster.generate(2026, 8)
        output = Path(self.temp_dir.name) / "escala.pdf"

        dish_roster.generate_pdf(2026, 8, str(output))

        self.assertTrue(output.exists())
        self.assertTrue(output.read_bytes().startswith(b"%PDF"))
        self.assertEqual(14, len([
            item for item in dish_roster.payload(2026, 8)["linhas"]
            if item["fim_semana"] <= "2026-10-31"
        ]))

    def test_dropdown_excludes_departed_and_manual_weekend_accepts_one_person(self):
        first = self.person("primeiro", "2026-01-01")
        future = self.person("entrada_futura", "2099-01-01")
        self.person("partiu", "2020-01-01", departure="2020-12-31")
        dish_roster.ensure_rows(2026, 8)

        people_ids = {
            item["id"] for item in dish_roster.payload(2026, 8)["pessoas"]
        }
        dish_roster.save_rows(2026, 8, [{
            "fim_semana": "2026-08-01",
            "militar_1_id": first,
            "militar_2_id": None,
        }])
        dish_roster.generate(2026, 8)
        row = dish_roster.get_row("2026-08-01")

        self.assertEqual({first, future}, people_ids)
        self.assertEqual(first, row["militar_1_id"])
        self.assertIsNone(row["militar_2_id"])

    def test_forecast_continues_after_last_validated_service(self):
        people = [
            self.person(f"rotacao{index}", "2026-01-01", rank=f"OR-{index}")
            for index in range(1, 5)
        ]
        dish_roster.ensure_rows(2026, 8)
        dish_roster.save_rows(2026, 8, [{
            "fim_semana": "2026-08-01",
            "militar_1_id": people[0],
            "militar_2_id": people[1],
        }])
        dish_roster.set_validation("2026-08-01", True)

        dish_roster.generate(2026, 8)
        following = dish_roster.get_row("2026-08-08")

        self.assertEqual(people[2], following["militar_1_id"])
        self.assertEqual(people[3], following["militar_2_id"])

    def test_forecast_repairs_empty_rows_previously_marked_as_manual(self):
        first = self.person("disponivel1", "2026-01-01")
        second = self.person("disponivel2", "2026-01-01", rank="OR-2")
        dish_roster.ensure_rows(2026, 8)
        db.db_execute(
            "UPDATE escala_loica SET manual=1 WHERE fim_semana='2026-08-01'"
        )

        dish_roster.generate(2026, 8)
        row = dish_roster.get_row("2026-08-01")

        self.assertEqual(first, row["militar_1_id"])
        self.assertEqual(second, row["militar_2_id"])
        self.assertEqual(0, row["manual"])

    def test_explicit_rebuild_discards_manual_rows_after_latest_validation(self):
        people = [
            self.person(f"rebuild{index}", "2026-01-01", rank=f"OR-{index}")
            for index in range(1, 5)
        ]
        dish_roster.ensure_rows(2026, 8)
        dish_roster.save_rows(2026, 8, [{
            "fim_semana": "2026-08-01",
            "militar_1_id": people[0],
            "militar_2_id": people[1],
        }])
        dish_roster.set_validation("2026-08-01", True)
        dish_roster.save_rows(2026, 8, [{
            "fim_semana": "2026-08-08",
            "militar_1_id": people[0],
            "militar_2_id": None,
        }])

        dish_roster.generate(2026, 8, rebuild_forecast=True)
        rebuilt = dish_roster.get_row("2026-08-08")

        self.assertEqual(people[2], rebuilt["militar_1_id"])
        self.assertEqual(people[3], rebuilt["militar_2_id"])
        self.assertEqual(0, rebuilt["manual"])

    def test_forecast_prioritizes_never_served_then_longest_resting(self):
        oldest_service = self.person("servico_antigo", "2026-01-01", "OR-1")
        recent_service = self.person("servico_recente", "2026-01-01", "OR-2")
        never_served = self.person("nunca_fez", "2026-01-01", "OR-3")
        dish_roster.ensure_rows(2026, 8)
        db.db_execute(
            """UPDATE escala_loica SET militar_1_id=?, validada=1
               WHERE fim_semana='2026-08-01'""",
            (oldest_service,),
        )
        db.db_execute(
            """UPDATE escala_loica SET militar_1_id=?, validada=1
               WHERE fim_semana='2026-08-08'""",
            (recent_service,),
        )

        dish_roster.generate(2026, 8)
        following = dish_roster.get_row("2026-08-15")

        self.assertEqual(never_served, following["militar_1_id"])
        self.assertEqual(oldest_service, following["militar_2_id"])


if __name__ == "__main__":
    unittest.main()
