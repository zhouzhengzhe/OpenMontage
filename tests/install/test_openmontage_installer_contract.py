from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
INSTALLER = REPO_ROOT / "scripts" / "windows" / "install-openmontage-global.ps1"
SKILL = REPO_ROOT / "scripts" / "windows" / "openmontage" / "SKILL.md"
SKILL_UI = REPO_ROOT / "scripts" / "windows" / "openmontage" / "agents" / "openai.yaml"


class InstallerContractTests(unittest.TestCase):
    def test_powershell_script_parses(self) -> None:
        command = (
            "$errors=$null; "
            f"[System.Management.Automation.Language.Parser]::ParseFile('{INSTALLER}',"
            "[ref]$null,[ref]$errors) > $null; "
            "if($errors.Count){$errors | Out-String | Write-Error; exit 1}"
        )
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", command],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_installer_does_not_shadow_read_only_powershell_home(self) -> None:
        text = INSTALLER.read_text(encoding="utf-8")
        self.assertNotIn("[string]$Home", text)
        self.assertIn('[Alias("Home")]', text)

    def test_installer_never_sets_provider_secrets_globally(self) -> None:
        text = INSTALLER.read_text(encoding="utf-8")
        forbidden = [
            "OPENAI_API_KEY",
            "FAL_KEY",
            "GOOGLE_API_KEY",
            "ELEVENLABS_API_KEY",
        ]
        for name in forbidden:
            self.assertNotIn(f'SetEnvironmentVariable("{name}"', text)

    def test_installer_preserves_env_and_pins_hyperframes(self) -> None:
        text = INSTALLER.read_text(encoding="utf-8")
        self.assertIn("if (-not (Test-Path -LiteralPath $EnvFile))", text)
        self.assertIn("hyperframes@0.7.57", text)
        self.assertIn("npx.cmd hyperframes browser ensure", text)
        self.assertIn("npx.cmd hyperframes telemetry disable", text)
        self.assertIn("for ($Attempt = 1; $Attempt -le 3; $Attempt++)", text)
        self.assertIn("Google\\Chrome\\Application\\chrome.exe", text)
        self.assertIn("Add-Content -LiteralPath $EnvFile", text)

    def test_installer_replaces_env_acl_with_three_trusted_principals(self) -> None:
        text = INSTALLER.read_text(encoding="utf-8")
        self.assertIn("icacls.exe $EnvFile /reset", text)
        self.assertIn("icacls.exe $EnvFile /inheritance:r", text)
        self.assertIn("icacls.exe $EnvFile /grant:r", text)
        self.assertIn("S-1-5-32-544", text)
        self.assertIn("S-1-5-18", text)
        self.assertNotIn("Set-Acl", text)

    def test_skill_is_explicitly_triggered(self) -> None:
        text = SKILL.read_text(encoding="utf-8")
        self.assertIn("$openmontage", text)
        self.assertIn("明确要求", text)
        self.assertIn("不得自动触发", text)

    def test_skill_routes_to_central_generation_profiles(self) -> None:
        text = SKILL.read_text(encoding="utf-8")
        self.assertIn("generation_profiles.yaml", text)
        self.assertIn("skills/meta/generation-profile-routing.md", text)
        self.assertNotIn("API 密钥值", text)

    def test_skill_ui_disables_implicit_invocation(self) -> None:
        text = SKILL_UI.read_text(encoding="utf-8")
        self.assertIn("allow_implicit_invocation: false", text)
        self.assertIn("$openmontage", text)


if __name__ == "__main__":
    unittest.main()
