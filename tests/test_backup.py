import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import main


class BackupTest(unittest.TestCase):
    def test_creates_consistent_snapshot_and_keeps_latest_twenty(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            database = root / "database.sqlite3"
            connection = sqlite3.connect(database)
            try:
                connection.execute("CREATE TABLE exemplo (valor TEXT)")
                connection.execute("INSERT INTO exemplo VALUES ('conteúdo preservado')")
                connection.commit()
            finally:
                connection.close()

            backup_dir = root / "db_backup"
            backup_dir.mkdir()
            inicio = datetime(2025, 1, 1, 0, 0, 0)
            for offset in range(20):
                antigo = backup_dir / (inicio + timedelta(seconds=offset)).strftime(
                    "%d%m%Y_%H%M%S"
                )
                antigo.mkdir()
                (antigo / "database.sqlite3").touch()

            with patch.object(main.config, "DB_PATH", str(database)):
                created = main.criar_backup_base_dados(max_backups=20)

            backups = sorted(path for path in backup_dir.iterdir() if path.is_dir())
            self.assertEqual(20, len(backups))
            self.assertTrue(created.is_file())
            self.assertFalse((backup_dir / "01012025_000000").exists())

            snapshot = sqlite3.connect(created)
            try:
                value = snapshot.execute("SELECT valor FROM exemplo").fetchone()[0]
            finally:
                snapshot.close()
            self.assertEqual("conteúdo preservado", value)

    def test_network_destination_is_a_normal_file_copy(self):
        """O servidor não precisa de suportar uma ligação SQLite no destino."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            database = root / "database.sqlite3"
            connection = sqlite3.connect(database)
            try:
                connection.execute("CREATE TABLE exemplo (valor TEXT)")
                connection.execute("INSERT INTO exemplo VALUES ('rede')")
                connection.commit()
            finally:
                connection.close()

            backup_dir = root / "db_backup"
            backup_dir.mkdir()
            real_connect = main.sqlite3.connect

            def rejeitar_sqlite_no_servidor(caminho, *args, **kwargs):
                if str(caminho).startswith(str(backup_dir)):
                    raise sqlite3.OperationalError(
                        "o servidor não permite abrir SQLite no destino"
                    )
                return real_connect(caminho, *args, **kwargs)

            with (
                patch.object(main.config, "DB_PATH", str(database)),
                patch.object(
                    main.sqlite3,
                    "connect",
                    side_effect=rejeitar_sqlite_no_servidor,
                ),
            ):
                created = main.criar_backup_base_dados()

            self.assertTrue(created.is_file())
            snapshot = sqlite3.connect(created)
            try:
                value = snapshot.execute("SELECT valor FROM exemplo").fetchone()[0]
            finally:
                snapshot.close()
            self.assertEqual("rede", value)

    def test_cleanup_permission_error_does_not_invalidate_new_backup(self):
        """Uma cópia nova continua válida se um backup antigo não puder ser apagado."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            database = root / "database.sqlite3"
            connection = sqlite3.connect(database)
            try:
                connection.execute("CREATE TABLE exemplo (valor TEXT)")
                connection.execute("INSERT INTO exemplo VALUES ('preservado')")
                connection.commit()
            finally:
                connection.close()

            backup_dir = root / "db_backup"
            backup_dir.mkdir()
            inicio = datetime(2025, 1, 1, 0, 0, 0)
            for offset in range(20):
                antigo = backup_dir / (inicio + timedelta(seconds=offset)).strftime(
                    "%d%m%Y_%H%M%S"
                )
                antigo.mkdir()
                (antigo / "database.sqlite3").touch()

            real_rmtree = main.shutil.rmtree

            def recusar_backups_antigos(caminho, *args, **kwargs):
                caminho = Path(caminho)
                if caminho.parent == backup_dir:
                    raise PermissionError("eliminação recusada pelo servidor")
                return real_rmtree(caminho, *args, **kwargs)

            with (
                patch.object(main.config, "DB_PATH", str(database)),
                patch.object(
                    main.shutil,
                    "rmtree",
                    side_effect=recusar_backups_antigos,
                ),
            ):
                created = main.criar_backup_base_dados(max_backups=20)

            self.assertTrue(created.is_file())
            self.assertEqual(21, len(list(backup_dir.iterdir())))


if __name__ == "__main__":
    unittest.main()
