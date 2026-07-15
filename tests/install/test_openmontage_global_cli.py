from __future__ import annotations

import json
import importlib.util
import io
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
CLI = REPO_ROOT / "scripts" / "openmontage_global_cli.py"


def load_cli_module():
    spec = importlib.util.spec_from_file_location("openmontage_global_cli_test", CLI)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class OpenMontageGlobalCliTests(unittest.TestCase):
    def run_cli(
        self, *args: str, home: Path | None = None
    ) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        if home is not None:
            env["OPENMONTAGE_HOME"] = str(home)
        return subprocess.run(
            [sys.executable, str(CLI), *args],
            cwd=REPO_ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_help_is_available_without_runtime(self) -> None:
        result = self.run_cli("--help")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("doctor", result.stdout)
        self.assertIn("preflight", result.stdout)

    def test_help_lists_profiles(self) -> None:
        result = self.run_cli("--help")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("profiles", result.stdout)

    def test_unknown_command_is_rejected(self) -> None:
        result = self.run_cli("unknown-command")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("invalid choice", result.stderr)

    def test_doctor_reports_missing_home_without_secrets(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "missing"
            result = self.run_cli("doctor", home=missing)
        self.assertEqual(result.returncode, 1)
        report = json.loads(result.stdout)
        self.assertFalse(report["checks"]["home"]["ok"])
        self.assertNotIn("API_KEY", result.stdout)
        self.assertNotIn("TOKEN", result.stdout)

    def test_doctor_rejects_unpinned_hyperframes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            package = home / "node_modules" / "hyperframes" / "package.json"
            package.parent.mkdir(parents=True)
            package.write_text('{"version": "9.9.9"}', encoding="utf-8")
            result = self.run_cli("doctor", home=home)
        report = json.loads(result.stdout)
        self.assertFalse(report["checks"]["hyperframes"]["ok"])
        self.assertIn("0.7.57", report["checks"]["hyperframes"]["detail"])

    def test_profiles_validate_checks_shipped_contract_without_secrets(self) -> None:
        result = self.run_cli("profiles", "validate", home=REPO_ROOT)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertTrue(report["ok"])
        self.assertEqual(report["default_profile"], "daily")
        self.assertEqual(report["errors"], [])
        for marker in ("OPENAI_API_KEY", "FAL_KEY", "GOOGLE_API_KEY", "Bearer "):
            self.assertNotIn(marker, result.stdout)

    def test_profiles_show_is_safe_end_to_end(self) -> None:
        sentinel_name = "OPENMONTAGE_PROFILE_TEST_SENTINEL"
        sentinel_value = "subprocess-environment-secret-sentinel-2f56"
        previous = os.environ.get(sentinel_name)
        os.environ[sentinel_name] = sentinel_value
        try:
            result = self.run_cli("profiles", home=REPO_ROOT)
        finally:
            if previous is None:
                os.environ.pop(sentinel_name, None)
            else:
                os.environ[sentinel_name] = previous

        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertTrue(report["ok"])
        self.assertIn("daily", report["profiles"])
        self.assertIn("quality", report["profiles"])
        serialized = result.stdout
        self.assertIn('"status"', serialized)
        for marker in (
            sentinel_name,
            sentinel_value,
            "OPENAI_API_KEY",
            "Bearer ",
            "sk-",
            "AKIA",
            "-----BEGIN PRIVATE KEY-----",
        ):
            self.assertNotIn(marker, serialized)

    def test_profiles_invalid_temporary_home_returns_safe_json(self) -> None:
        sentinel = "yaml-secret-sentinel-6a19"
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            (home / "AGENT_GUIDE.md").touch()
            (home / "generation_profiles.yaml").write_text(
                f"version: 1\ndefault_profile: [{sentinel}\n",
                encoding="utf-8",
            )

            result = self.run_cli("profiles", "validate", home=home)

        self.assertEqual(result.returncode, 1, result.stderr)
        report = json.loads(result.stdout)
        self.assertFalse(report["ok"])
        self.assertTrue(report["errors"])
        self.assertNotIn(sentinel, result.stdout)
        self.assertNotIn("Traceback", result.stdout + result.stderr)

    def test_profiles_temporary_home_rejects_nested_key_without_echoing_value(self) -> None:
        sentinel = "temporary-home-secret-sentinel-b4da"
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            (home / "AGENT_GUIDE.md").touch()
            config = yaml.safe_load(
                (REPO_ROOT / "generation_profiles.yaml").read_text(encoding="utf-8")
            )
            params = config["profiles"]["daily"]["capabilities"]["tts"]["candidates"][0][
                "params"
            ]
            params["transport"] = {"fal_key": sentinel}
            (home / "generation_profiles.yaml").write_text(
                yaml.safe_dump(config, allow_unicode=True),
                encoding="utf-8",
            )

            result = self.run_cli("profiles", home=home)

        self.assertEqual(result.returncode, 1, result.stderr)
        report = json.loads(result.stdout)
        self.assertFalse(report["ok"])
        self.assertTrue(report["errors"])
        self.assertNotIn(sentinel, result.stdout)
        self.assertNotIn("Traceback", result.stdout + result.stderr)

    def test_main_converts_unexpected_diagnostic_exception_to_safe_json(self) -> None:
        cli = load_cli_module()
        output = io.StringIO()
        with (
            mock.patch.object(cli, "resolve_home", return_value=REPO_ROOT),
            mock.patch.object(
                cli,
                "profiles",
                side_effect=RuntimeError("generic-secret-sentinel-083e"),
            ),
            redirect_stdout(output),
        ):
            exit_code = cli.main(["profiles"])

        report = json.loads(output.getvalue())
        self.assertEqual(exit_code, 1)
        self.assertFalse(report["ok"])
        self.assertEqual(report["errors"], ["diagnostic failed (RuntimeError)"])
        self.assertNotIn("generic-secret-sentinel-083e", output.getvalue())

    def test_demo_forwards_option_arguments(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            (home / "AGENT_GUIDE.md").touch()
            (home / "render_demo.py").write_text(
                "import json, sys; print(json.dumps(sys.argv[1:]))",
                encoding="utf-8",
            )
            result = self.run_cli("demo", "--list", home=home)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), ["--list"])


if __name__ == "__main__":
    unittest.main()
