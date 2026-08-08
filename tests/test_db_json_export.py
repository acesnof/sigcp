import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import db


class DatabaseJsonExportTest(unittest.TestCase):
    def test_exporta_todas_as_tabelas_e_registos(self):
        with tempfile.TemporaryDirectory() as pasta:
            caminho_db = Path(pasta) / "teste.sqlite3"
            caminho_json = Path(pasta) / "exportacao.json"

            conn = sqlite3.connect(caminho_db)
            conn.executescript("""
                CREATE TABLE pessoas (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nome TEXT NOT NULL,
                    observacao TEXT,
                    fotografia BLOB
                );
                CREATE TABLE tabela_vazia (
                    codigo TEXT PRIMARY KEY,
                    valor REAL
                );
            """)
            conn.execute(
                "INSERT INTO pessoas (nome, observacao, fotografia) VALUES (?, ?, ?)",
                ("João", None, b"\x00\xff"),
            )
            conn.commit()
            conn.close()

            with patch.object(db, "DB_PATH", str(caminho_db)):
                resumo = db.exportar_base_dados_json(caminho_json)

            dados = json.loads(caminho_json.read_text(encoding="utf-8"))

            self.assertEqual("prt_welfare_database_export", dados["formato"])
            self.assertEqual(1, dados["versao"])
            self.assertEqual(2, resumo["tabelas"])
            self.assertEqual(1, resumo["registos"])
            self.assertEqual(
                {"pessoas", "tabela_vazia"},
                set(dados["tabelas"]),
            )
            self.assertEqual("João", dados["tabelas"]["pessoas"]["registos"][0]["nome"])
            self.assertIsNone(dados["tabelas"]["pessoas"]["registos"][0]["observacao"])
            self.assertEqual(
                {"__tipo__": "bytes", "base64": "AP8="},
                dados["tabelas"]["pessoas"]["registos"][0]["fotografia"],
            )
            self.assertEqual([], dados["tabelas"]["tabela_vazia"]["registos"])
            self.assertEqual(
                ["codigo", "valor"],
                [
                    coluna["nome"]
                    for coluna in dados["tabelas"]["tabela_vazia"]["colunas"]
                ],
            )


if __name__ == "__main__":
    unittest.main()
