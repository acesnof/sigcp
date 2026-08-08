import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import main
from app import config


class StartupDatabaseTest(unittest.TestCase):
    def test_sigcp_reads_the_previous_prt_welfare_configuration(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            database = root / "database.sqlite3"
            sqlite3.connect(database).close()
            current_config = root / "SIGCP" / "sigcp_config.json"
            legacy_config = root / "PRT Welfare" / "prt_welfare_config.json"
            legacy_config.parent.mkdir(parents=True)
            legacy_config.write_text(
                json.dumps({"database_path": str(database)}), encoding="utf-8"
            )

            with (
                patch.object(config, "CONFIG_PATH", str(current_config)),
                patch.object(config, "LEGACY_CONFIG_PATH", str(legacy_config)),
                patch.object(config, "ADDITIONAL_CONFIG_PATHS", ()),
            ):
                loaded = config._ler_config_local()

            self.assertEqual(str(database), loaded["database_path"])

    def test_sigcp_database_environment_variable_is_supported(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            database = Path(temp_dir) / "database.sqlite3"
            sqlite3.connect(database).close()
            with (
                patch.dict(
                    os.environ,
                    {
                        "SIGCP_DB_PATH": str(database),
                        "PRT_WELFARE_DB_PATH": "",
                    },
                ),
                patch.object(main.config, "set_db_path") as set_path,
            ):
                self.assertTrue(main.configurar_base_dados())

            set_path.assert_called_once_with(str(database))

    def test_sqlite_validation_rejects_non_database_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            database = root / "database.sqlite3"
            invalid = root / "invalid.sqlite3"

            connection = sqlite3.connect(database)
            try:
                connection.execute("CREATE TABLE exemplo (id INTEGER PRIMARY KEY)")
                connection.commit()
            finally:
                connection.close()
            invalid.write_text("não é uma base de dados", encoding="utf-8")

            self.assertEqual((True, ""), config.validar_base_dados(database))
            valid, error = config.validar_base_dados(invalid)
            self.assertFalse(valid)
            self.assertIn("SQLite", error)

    def test_sqlite_readonly_uri_supports_windows_unc_paths(self):
        uri = config._sqlite_readonly_uri(
            r"\\CISBAN-FILER\SIGCP\base com espaço\database.sqlite3"
        )

        self.assertEqual(
            "file:////CISBAN-FILER/SIGCP/base%20com%20espa%C3%A7o/"
            "database.sqlite3?mode=ro",
            uri,
        )

    def test_saved_database_is_used_without_opening_selector(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            database = Path(temp_dir) / "database.sqlite3"
            sqlite3.connect(database).close()

            with (
                patch.dict(os.environ, {"PRT_WELFARE_DB_PATH": ""}),
                patch.object(
                    main.config,
                    "_ler_config_local",
                    return_value={"database_path": str(database)},
                ),
                patch.object(main.config, "set_db_path") as set_path,
                patch.object(
                    main.config, "garantir_base_dados_configurada"
                ) as selector,
            ):
                self.assertTrue(main.configurar_base_dados())

            set_path.assert_called_once_with(str(database))
            selector.assert_not_called()

    def test_missing_database_opens_selector_and_persists_choice(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            database = root / "database.sqlite3"
            config_path = root / "settings" / "prt_welfare_config.json"
            sqlite3.connect(database).close()

            with (
                patch.object(config, "CONFIG_PATH", str(config_path)),
                patch.object(config, "LEGACY_CONFIG_PATH", str(config_path)),
                patch.object(config, "DB_PATH", str(root / "unused.sqlite3")),
                patch.object(config.messagebox, "showinfo"),
                patch.object(config.messagebox, "showerror") as show_error,
                patch.object(
                    config.filedialog,
                    "askopenfilename",
                    return_value=str(database),
                ),
            ):
                self.assertTrue(config.garantir_base_dados_configurada())
                self.assertEqual(str(database.resolve()), config.DB_PATH)

            show_error.assert_not_called()
            stored = json.loads(config_path.read_text(encoding="utf-8"))
            self.assertEqual(str(database.resolve()), stored["database_path"])

    def test_startup_missing_saved_database_asks_for_a_new_path(self):
        missing = str(Path(tempfile.gettempdir()) / "missing-sigcp.sqlite3")
        with (
            patch.dict(os.environ, {"SIGCP_DB_PATH": "", "PRT_WELFARE_DB_PATH": ""}),
            patch.object(main.config, "_ler_config_local", return_value={"database_path": missing}),
            patch.object(main.config, "validar_base_dados", return_value=(False, "não existe")),
            patch.object(main.config, "garantir_base_dados_configurada", return_value=True) as selector,
        ):
            self.assertTrue(main.configurar_base_dados())

        selector.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
