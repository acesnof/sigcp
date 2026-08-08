import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import cash_service, db


class CashServiceTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database = Path(self.temp_dir.name) / "cash.sqlite3"
        self.db_patch = patch.object(db, "DB_PATH", str(self.database))
        self.db_patch.start()
        db.init_db()
        self.user = {
            "id": db.db_execute_return_id("""
                INSERT INTO utilizadores (
                    nim, posto, nome, sobrenome, data_chegada, antiguidade,
                    tipo_acesso, password_salt, password_hash, master
                ) VALUES ('cash-user', 'OR-5', 'Nome', 'Caixa', '2026-01-01',
                          '2020-01-01', 'Gestão Caixa', 'x', 'x', 0)
            """),
            "nim": "cash-user", "posto": "OR-5", "nome": "Nome", "sobrenome": "Caixa",
        }

    def tearDown(self):
        self.db_patch.stop()
        self.temp_dir.cleanup()

    def movement(self, kind, day, amount, description="Movimento"):
        return cash_service.save({
            "tipo": kind, "data": day, "valor": amount,
            "descritivo": description, "pessoa_gasto": "Militar Teste",
            "local": "Bangui", "observacoes": "Teste",
        }, self.user)

    def test_balance_includes_opening_entries_exits_and_running_balance(self):
        self.movement("entrada", "2026-07-31", 1000)
        self.movement("entrada", "2026-08-02", 500)
        self.movement("saida", "2026-08-03", 200)

        report = cash_service.balance("2026-08-01", "2026-08-31")

        self.assertEqual(1000, report["saldo_inicial"])
        self.assertEqual(500, report["total_entradas"])
        self.assertEqual(200, report["total_saidas"])
        self.assertEqual(1300, report["saldo_final"])
        self.assertEqual([1500, 1300], [row["saldo"] for row in report["movimentos"]])

    def test_entry_drops_expense_person_and_audit_fields_are_updated(self):
        movement_id = self.movement("saida", "2026-08-03", 200)
        cash_service.save({
            "tipo": "entrada", "data": "2026-08-04", "valor": "300,50",
            "descritivo": "Reposição", "pessoa_gasto": "Não guardar",
        }, self.user, movement_id)
        row = db.db_one("SELECT * FROM caixa_movimentos WHERE id=?", (movement_id,))
        self.assertEqual("", row["pessoa_gasto"])
        self.assertEqual(300.5, row["valor"])
        self.assertEqual("OR-5 Nome Caixa", row["criado_por_nome"])
        self.assertEqual("OR-5 Nome Caixa", row["atualizado_por_nome"])

    def test_pdf_is_generated(self):
        self.movement("entrada", "2026-08-02", 500)
        self.movement("saida", "2026-08-03", 200)
        output = Path(self.temp_dir.name) / "cash.pdf"
        cash_service.generate_pdf("2026-08-01", "2026-08-31", str(output))
        self.assertTrue(output.read_bytes().startswith(b"%PDF"))

    def test_pdf_supports_many_movements_across_pages(self):
        for index in range(80):
            self.movement(
                "entrada" if index % 2 == 0 else "saida",
                f"2026-08-{index % 28 + 1:02d}",
                100 + index,
                f"Movimento {index}",
            )
        output = Path(self.temp_dir.name) / "cash-long.pdf"
        cash_service.generate_pdf("2026-08-01", "2026-08-31", str(output))
        self.assertTrue(output.read_bytes().startswith(b"%PDF"))


if __name__ == "__main__":
    unittest.main()
