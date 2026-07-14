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


if __name__ == "__main__":
    unittest.main()
