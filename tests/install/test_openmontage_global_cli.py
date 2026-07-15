from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
CLI = REPO_ROOT / "scripts" / "openmontage_global_cli.py"


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
