import tempfile
import subprocess
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import main


class ApplicationUpdaterTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.local = self.root / "local" / "SIGCP.exe"
        self.shared = self.root / "shared"
        self.local.parent.mkdir()
        self.shared.mkdir()
        self.local.write_bytes(b"versao-local")
        self.db_patch = patch.object(
            main.config, "DB_PATH", str(self.root / "settings.sqlite3")
        )
        self.db_patch.start()

    def tearDown(self):
        self.db_patch.stop()
        self.temp_dir.cleanup()

    def _patch_runtime(self, answer=True):
        return (
            patch.object(main.sys, "frozen", True, create=True),
            patch.object(main.sys, "executable", str(self.local)),
            patch.object(main.config, "_ler_config_local", return_value={"update_folder": str(self.shared)}),
            patch.object(main.config.messagebox, "askyesno", return_value=answer),
            patch.object(main, "_agendar_substituicao_executavel"),
        )

    def test_same_executable_starts_without_prompt(self):
        (self.shared / "SIGCP.exe").write_bytes(b"versao-local")
        patches = self._patch_runtime()
        with patches[0], patches[1], patches[2], patches[3] as prompt, patches[4] as schedule:
            self.assertFalse(main.verificar_atualizacao())
        prompt.assert_not_called()
        schedule.assert_not_called()

    def test_different_executable_is_scheduled_when_accepted(self):
        published = self.shared / "SIGCP.exe"
        published.write_bytes(b"versao-2.1")
        patches = self._patch_runtime(answer=True)
        with patches[0], patches[1], patches[2], patches[3] as prompt, patches[4] as schedule:
            self.assertTrue(main.verificar_atualizacao())
        prompt.assert_called_once()
        schedule.assert_called_once_with(published, self.local)

    def test_different_executable_closes_when_update_is_declined_twice(self):
        (self.shared / "SIGCP.exe").write_bytes(b"versao-2.1")
        patches = self._patch_runtime(answer=False)
        with (
            patches[0], patches[1], patches[2], patches[3],
            patch.object(
                main, "_confirmar_atualizacao_obrigatoria", return_value=False
            ) as mandatory_prompt,
            patches[4] as schedule,
        ):
            self.assertTrue(main.verificar_atualizacao())
        mandatory_prompt.assert_called_once_with()
        schedule.assert_not_called()

    def test_different_executable_updates_after_initial_refusal(self):
        published = self.shared / "SIGCP.exe"
        published.write_bytes(b"versao-2.3.1")
        patches = self._patch_runtime(answer=False)
        with (
            patches[0], patches[1], patches[2], patches[3],
            patch.object(
                main, "_confirmar_atualizacao_obrigatoria", return_value=True
            ) as mandatory_prompt,
            patches[4] as schedule,
        ):
            self.assertTrue(main.verificar_atualizacao())
        mandatory_prompt.assert_called_once_with()
        schedule.assert_called_once_with(published, self.local)

    def test_update_reports_completion_without_relaunching_application(self):
        published = self.shared / "SIGCP.exe"
        published.write_bytes(b"versao-2.3")

        with (
            patch.object(
                main.config,
                "CONFIG_PATH",
                str(self.root / "settings" / "sigcp_config.json"),
            ),
            patch.object(main.subprocess, "Popen") as popen,
        ):
            main._agendar_substituicao_executavel(published, self.local)

        command = popen.call_args.args[0][-1]
        self.assertIn("A atualização foi concluída", command)
        self.assertIn("System.Windows.Forms.MessageBox", command)
        self.assertNotIn("Start-Process", command)
        self.assertNotIn("UseNewEnvironment", command)
        self.assertIn("Get-FileHash", command)

        parser = (
            "$source=[Console]::In.ReadToEnd(); $tokens=$null; $errors=$null; "
            "[System.Management.Automation.Language.Parser]::ParseInput("
            "$source,[ref]$tokens,[ref]$errors) | Out-Null; "
            "if($errors.Count){ $errors | ForEach-Object { $_.Message }; exit 1 }"
        )
        parsed = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", parser],
            input=command,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(0, parsed.returncode, parsed.stdout + parsed.stderr)

    def test_legacy_use_new_environment_only_reports_completion(self):
        with (
            patch.object(main.sys, "frozen", True, create=True),
            patch.dict(
                main.os.environ,
                {"USERNAME": "SYSTEM", "windir": r"C:\Windows"},
                clear=True,
            ),
            patch.object(main, "_utilizador_real_windows", return_value="fonse"),
            patch.object(main.config.messagebox, "showinfo") as message,
            patch.object(main, "_porta_servidor") as server_port,
        ):
            main.main()

        message.assert_called_once()
        self.assertIn("concluída", message.call_args.args[1])
        server_port.assert_not_called()

    def test_real_system_account_is_not_treated_as_legacy_relaunch(self):
        with (
            patch.dict(
                main.os.environ,
                {"USERNAME": "SYSTEM", "windir": r"C:\Windows"},
                clear=True,
            ),
            patch.object(main, "_utilizador_real_windows", return_value="SYSTEM"),
        ):
            self.assertFalse(main._ambiente_de_reabertura_legada())
