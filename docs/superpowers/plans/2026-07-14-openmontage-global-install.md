# OpenMontage Global On-Demand Installation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 Windows 11 上建立中央隔离的 OpenMontage 运行环境，并通过全局命令和按需 Codex Skill 从任意项目安全调用。

**Architecture:** OpenMontage 代码、Python 虚拟环境、Node 依赖、密钥和项目产物都保留在中央仓库。一个受测试的 Python CLI 提供稳定子命令，批处理入口只负责定位中央环境；PowerShell 安装器负责幂等安装、非敏感用户变量、PATH、ACL 和全局 Skill 部署。

**Tech Stack:** Python 3.14、`unittest`/pytest、PowerShell 5.1、Windows batch、Node.js/npm、FFmpeg、Codex Skill Markdown。

## Global Constraints

- 中央仓库固定为 `D:\SoftDocument\CodexProject\OpenMontage`。
- API 密钥只允许保存在中央 `.env`，不得写入 Windows 用户级环境变量。
- 全局 Skill 只能按 `$openmontage` 或明确自然语言请求触发。
- Python 依赖只能进入中央 `.venv`；Remotion 依赖只能进入中央 `remotion-composer\node_modules`。
- HyperFrames 固定为 `0.7.57`，不得使用无版本约束的最新版。
- 全局命令固定为 `C:\Users\Aristotle\.local\bin\openmontage.cmd`。
- 全局 Skill 固定为 `C:\Users\Aristotle\.codex\skills\openmontage\SKILL.md`。
- 所有项目产物固定写入中央 `projects`。
- 不安装 `requirements-gpu.txt`。
- 安装和卸载不得删除或覆盖已有 `.env` 与 `projects`。

---

### Task 1: 受测试的中央 CLI 与批处理入口

**Files:**
- Create: `scripts/openmontage_global_cli.py`
- Create: `scripts/windows/openmontage.cmd`
- Create: `tests/install/test_openmontage_global_cli.py`

**Interfaces:**
- Consumes: `OPENMONTAGE_HOME`、中央 `.venv`、`tools.tool_registry`、`backlot`、`render_demo.py`。
- Produces: `main(argv: list[str] | None = None) -> int`；子命令 `doctor`、`preflight`、`backlot`、`test-contracts`、`demo`。

- [ ] **Step 1: 写失败测试**

```python
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
    def run_cli(self, *args: str, home: Path | None = None) -> subprocess.CompletedProcess[str]:
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
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `python -m unittest tests.install.test_openmontage_global_cli -v`

Expected: FAIL，因为 `scripts/openmontage_global_cli.py` 尚不存在。

- [ ] **Step 3: 实现中央 CLI**

```python
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Sequence


DEFAULT_HOME = Path(r"D:\SoftDocument\CodexProject\OpenMontage")


def resolve_home() -> Path:
    return Path(os.environ.get("OPENMONTAGE_HOME", str(DEFAULT_HOME))).expanduser().resolve()


def _probe(executable: str, *args: str) -> dict[str, object]:
    resolved = shutil.which(executable)
    if not resolved:
        return {"ok": False, "detail": f"{executable} not found"}
    completed = subprocess.run(
        [resolved, *args], text=True, capture_output=True, check=False, timeout=30
    )
    output = (completed.stdout or completed.stderr).splitlines()
    return {
        "ok": completed.returncode == 0,
        "detail": output[0] if output else f"exit {completed.returncode}",
    }


def doctor(home: Path) -> int:
    checks: dict[str, dict[str, object]] = {
        "home": {"ok": (home / "AGENT_GUIDE.md").is_file(), "detail": str(home)},
        "venv": {
            "ok": (home / ".venv" / "Scripts" / "python.exe").is_file(),
            "detail": str(home / ".venv" / "Scripts" / "python.exe"),
        },
        "node": _probe("node", "--version"),
        "npm": _probe("npm.cmd", "--version"),
        "npx": _probe("npx.cmd", "--version"),
        "ffmpeg": _probe("ffmpeg", "-version"),
        "remotion": {
            "ok": (home / "remotion-composer" / "node_modules" / "remotion").is_dir(),
            "detail": str(home / "remotion-composer" / "node_modules" / "remotion"),
        },
        "hyperframes": {
            "ok": (home / "node_modules" / "hyperframes" / "package.json").is_file(),
            "detail": "required version 0.7.57",
        },
        "projects": {
            "ok": (home / "projects").is_dir(),
            "detail": str(home / "projects"),
        },
    }
    print(json.dumps({"home": str(home), "checks": checks}, ensure_ascii=False, indent=2))
    return 0 if all(bool(item["ok"]) for item in checks.values()) else 1


def _run(home: Path, args: Sequence[str]) -> int:
    completed = subprocess.run(list(args), cwd=home, check=False)
    return completed.returncode


def preflight(home: Path) -> int:
    sys.path.insert(0, str(home))
    from tools.tool_registry import registry

    registry.discover()
    print(json.dumps(registry.provider_menu_summary(), ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="openmontage")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("doctor")
    subparsers.add_parser("preflight")
    backlot = subparsers.add_parser("backlot")
    backlot.add_argument("project_id", nargs="?")
    subparsers.add_parser("test-contracts")
    demo = subparsers.add_parser("demo")
    demo.add_argument("args", nargs=argparse.REMAINDER)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    home = resolve_home()
    if args.command == "doctor":
        return doctor(home)
    if not (home / "AGENT_GUIDE.md").is_file():
        print(f"OpenMontage home is invalid: {home}", file=sys.stderr)
        return 2
    if args.command == "preflight":
        return preflight(home)
    if args.command == "backlot":
        command = [sys.executable, "-m", "backlot", "open"]
        if args.project_id:
            command.append(args.project_id)
        return _run(home, command)
    if args.command == "test-contracts":
        return _run(home, [sys.executable, "-m", "pytest", "tests/contracts", "-v"])
    if args.command == "demo":
        return _run(home, [sys.executable, str(home / "render_demo.py"), *args.args])
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: 实现批处理入口**

```bat
@echo off
setlocal EnableExtensions DisableDelayedExpansion
set "OM_HOME=%OPENMONTAGE_HOME%"
if not defined OM_HOME set "OM_HOME=D:\SoftDocument\CodexProject\OpenMontage"
set "OM_PY=%OM_HOME%\.venv\Scripts\python.exe"
if not exist "%OM_PY%" (
  >&2 echo OpenMontage runtime missing: "%OM_PY%"
  >&2 echo Run scripts\windows\install-openmontage-global.ps1 from the central repository.
  exit /b 2
)
pushd "%OM_HOME%" >nul || exit /b 2
"%OM_PY%" "%OM_HOME%\scripts\openmontage_global_cli.py" %*
set "OM_RC=%ERRORLEVEL%"
popd >nul
exit /b %OM_RC%
```

- [ ] **Step 5: 运行单元测试并确认通过**

Run: `python -m unittest tests.install.test_openmontage_global_cli -v`

Expected: 3 tests，全部 PASS。

- [ ] **Step 6: 提交 Task 1**

```powershell
git add scripts/openmontage_global_cli.py scripts/windows/openmontage.cmd tests/install/test_openmontage_global_cli.py
git commit -m "feat: add global OpenMontage command router"
```

### Task 2: 全局 Codex Skill 与幂等 Windows 安装器

**Files:**
- Create: `scripts/windows/openmontage/SKILL.md`
- Create: `scripts/windows/openmontage/agents/openai.yaml`
- Create: `scripts/windows/install-openmontage-global.ps1`
- Create: `tests/install/test_openmontage_installer_contract.py`

**Interfaces:**
- Consumes: Task 1 的 `scripts/windows/openmontage.cmd`、中央仓库、当前 Windows 用户目录。
- Produces: `Install-OpenMontageGlobal` 行为；全局 Skill；用户变量 `OPENMONTAGE_HOME` 与 `OPENMONTAGE_PROJECTS_DIR`。

- [ ] **Step 1: 使用 `skill-creator` 初始化全局 Skill 源目录**

Run:

```powershell
Get-Content C:\Users\Aristotle\.codex\skills\.system\skill-creator\references\openai_yaml.md -Raw
python C:\Users\Aristotle\.codex\skills\.system\skill-creator\scripts\init_skill.py openmontage --path scripts\windows --interface display_name="OpenMontage" --interface short_description="按需调用中央 OpenMontage 视频制作环境" --interface default_prompt="Use `$openmontage to run an OpenMontage video-production workflow."
```

Expected: 创建 `scripts\windows\openmontage\SKILL.md` 与 `scripts\windows\openmontage\agents\openai.yaml`；生成文件暂含模板内容，后续步骤会完整替换。

- [ ] **Step 2: 写失败的安装器契约测试**

```python
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

    def test_installer_never_sets_provider_secrets_globally(self) -> None:
        text = INSTALLER.read_text(encoding="utf-8")
        forbidden = ["OPENAI_API_KEY", "FAL_KEY", "GOOGLE_API_KEY", "ELEVENLABS_API_KEY"]
        for name in forbidden:
            self.assertNotIn(f'SetEnvironmentVariable("{name}"', text)

    def test_skill_is_explicitly_triggered(self) -> None:
        text = SKILL.read_text(encoding="utf-8")
        self.assertIn("$openmontage", text)
        self.assertIn("明确要求", text)
        self.assertIn("不得自动触发", text)
        self.assertTrue(SKILL_UI.is_file())


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: 运行契约测试并确认失败**

Run: `python -m unittest tests.install.test_openmontage_installer_contract -v`

Expected: FAIL，因为安装器和 Skill 尚不存在。

- [ ] **Step 4: 替换为按需全局 Skill 内容并保留生成的 UI 元数据**

```markdown
---
name: openmontage
description: Use only when the user explicitly invokes $openmontage or clearly asks to use OpenMontage for a video-production task; do not auto-trigger for ordinary development work.
---

# OpenMontage 全局路由

仅在用户输入 `$openmontage` 或明确要求“使用 OpenMontage”时启用；不得自动触发普通开发任务。

1. 从用户环境变量 `OPENMONTAGE_HOME` 定位中央仓库；缺失时使用 `D:\SoftDocument\CodexProject\OpenMontage`。
2. 在采取任何 OpenMontage 行动前，完整读取中央 `AGENT_GUIDE.md` 与 `PROJECT_CONTEXT.md`。
3. 使用全局 `openmontage` 命令做 `doctor` 与 `preflight`；Python 命令只允许使用中央 `.venv`。
4. 所有检查点、资产和成片写入 `OPENMONTAGE_PROJECTS_DIR` 指向的中央 `projects`。
5. API 密钥只从中央 `.env` 加载；不得打印、复制到用户环境变量或写入其他项目。
6. 所有视频制作继续遵守流水线、Provider 披露、费用确认、渲染运行时选择与人工审批规则。
7. 外部项目素材使用绝对路径传入；不得修改来源项目，除非用户明确要求。
```

- [ ] **Step 5: 创建幂等安装器**

```powershell
[CmdletBinding()]
param(
    [string]$Home = "D:\SoftDocument\CodexProject\OpenMontage",
    [switch]$SkipDependencies
)

$ErrorActionPreference = "Stop"
$Home = (Resolve-Path -LiteralPath $Home).Path
$VenvPython = Join-Path $Home ".venv\Scripts\python.exe"
$RemotionDir = Join-Path $Home "remotion-composer"
$EnvFile = Join-Path $Home ".env"
$ProjectsDir = Join-Path $Home "projects"
$BinDir = Join-Path $env:USERPROFILE ".local\bin"
$GlobalLauncher = Join-Path $BinDir "openmontage.cmd"
$GlobalSkillDir = Join-Path $env:USERPROFILE ".codex\skills\openmontage"

if (-not (Test-Path (Join-Path $Home "AGENT_GUIDE.md"))) {
    throw "Invalid OpenMontage home: $Home"
}

if (-not $SkipDependencies) {
    if (-not (Test-Path $VenvPython)) {
        & python -m venv (Join-Path $Home ".venv")
        if ($LASTEXITCODE -ne 0) { throw "Failed to create Python virtual environment" }
    }
    & $VenvPython -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) { throw "Failed to upgrade pip" }
    & $VenvPython -m pip install -r (Join-Path $Home "requirements.txt") piper-tts pytest pytest-asyncio httpx2
    if ($LASTEXITCODE -ne 0) { throw "Failed to install Python dependencies" }
    Push-Location $RemotionDir
    try {
        & npm.cmd ci
        if ($LASTEXITCODE -ne 0) { throw "Failed to install Remotion dependencies" }
    } finally {
        Pop-Location
    }
    Push-Location $Home
    try {
        & npm.cmd install --no-save --no-package-lock hyperframes@0.7.57
        if ($LASTEXITCODE -ne 0) { throw "Failed to install HyperFrames 0.7.57" }
    } finally {
        Pop-Location
    }
}

New-Item -ItemType Directory -Force -Path $ProjectsDir, $BinDir, $GlobalSkillDir | Out-Null
if (-not (Test-Path $EnvFile)) {
    Copy-Item -LiteralPath (Join-Path $Home ".env.example") -Destination $EnvFile
}

Copy-Item -LiteralPath (Join-Path $Home "scripts\windows\openmontage.cmd") -Destination $GlobalLauncher -Force
Copy-Item -LiteralPath (Join-Path $Home "scripts\windows\openmontage\SKILL.md") -Destination (Join-Path $GlobalSkillDir "SKILL.md") -Force
New-Item -ItemType Directory -Force -Path (Join-Path $GlobalSkillDir "agents") | Out-Null
Copy-Item -LiteralPath (Join-Path $Home "scripts\windows\openmontage\agents\openai.yaml") -Destination (Join-Path $GlobalSkillDir "agents\openai.yaml") -Force

[Environment]::SetEnvironmentVariable("OPENMONTAGE_HOME", $Home, "User")
[Environment]::SetEnvironmentVariable("OPENMONTAGE_PROJECTS_DIR", $ProjectsDir, "User")
$UserPath = [Environment]::GetEnvironmentVariable("Path", "User")
$Parts = @($UserPath -split ";" | Where-Object { $_ })
if (-not ($Parts | Where-Object { $_.TrimEnd("\\") -ieq $BinDir.TrimEnd("\\") })) {
    [Environment]::SetEnvironmentVariable("Path", (($Parts + $BinDir) -join ";"), "User")
}
$env:OPENMONTAGE_HOME = $Home
$env:OPENMONTAGE_PROJECTS_DIR = $ProjectsDir
$env:Path = "$BinDir;$env:Path"

$Identity = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
& icacls.exe $EnvFile /inheritance:r /grant:r "${Identity}:(F)" "*S-1-5-32-544:(F)" "*S-1-5-18:(F)" | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Failed to restrict .env ACL" }

Write-Output "OpenMontage global installation complete."
Write-Output "Home: $Home"
Write-Output "Launcher: $GlobalLauncher"
Write-Output "Skill: $GlobalSkillDir"
Write-Output "Restart Codex to discover the new skill."
```

- [ ] **Step 6: 校验 Skill 和安装器契约并确认通过**

Run:

```powershell
python C:\Users\Aristotle\.codex\skills\.system\skill-creator\scripts\quick_validate.py scripts\windows\openmontage
python -m unittest tests.install.test_openmontage_installer_contract -v
```

Expected: Skill validation success；3 tests 全部 PASS。

- [ ] **Step 7: 提交 Task 2**

```powershell
git add scripts/windows/openmontage/SKILL.md scripts/windows/openmontage/agents/openai.yaml scripts/windows/install-openmontage-global.ps1 tests/install/test_openmontage_installer_contract.py
git commit -m "feat: add secure global OpenMontage installer"
```

### Task 3: 执行中央依赖与全局入口安装

**Files:**
- Create outside repo: `C:\Users\Aristotle\.local\bin\openmontage.cmd`
- Create outside repo: `C:\Users\Aristotle\.codex\skills\openmontage\SKILL.md`
- Create if absent: `.env`
- Create if absent: `.venv\`
- Create if absent: `projects\`
- Create: `node_modules\hyperframes\`
- Create: `remotion-composer\node_modules\`

**Interfaces:**
- Consumes: Task 1 和 Task 2 的已提交安装资产。
- Produces: 可从任意目录调用的全局环境。

- [ ] **Step 1: 记录安装前状态且不输出密钥值**

Run:

```powershell
git status --short --branch
[PSCustomObject]@{
  OpenMontageHome = [Environment]::GetEnvironmentVariable("OPENMONTAGE_HOME", "User")
  ProjectsDir = [Environment]::GetEnvironmentVariable("OPENMONTAGE_PROJECTS_DIR", "User")
  EnvExists = Test-Path .env
  VenvExists = Test-Path .venv
}
```

Expected: 只显示路径与存在状态，不显示任何 Provider 密钥。

- [ ] **Step 2: 执行安装器**

Run:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\windows\install-openmontage-global.ps1
```

Expected: 退出码 0，显示中央 Home、全局 Launcher 和 Skill 路径。

- [ ] **Step 3: 验证固定版本和用户变量**

Run:

```powershell
& .\.venv\Scripts\python.exe --version
& node --version
& npm.cmd --version
& ffmpeg -version | Select-Object -First 1
Get-Content node_modules\hyperframes\package.json -Raw | ConvertFrom-Json | Select-Object name,version
[PSCustomObject]@{
  OpenMontageHome = [Environment]::GetEnvironmentVariable("OPENMONTAGE_HOME", "User")
  ProjectsDir = [Environment]::GetEnvironmentVariable("OPENMONTAGE_PROJECTS_DIR", "User")
}
```

Expected: Python 3.14、Node 22 以上、HyperFrames `0.7.57`，用户变量只有非敏感路径。

- [ ] **Step 4: 验证 `.env` Git 状态和 ACL**

Run:

```powershell
git check-ignore -v .env
icacls.exe .env
```

Expected: `.env` 被 `.gitignore` 忽略；ACL 只包含当前用户、Administrators 和 SYSTEM。

### Task 4: 跨目录、安全和运行时验收

**Files:**
- Verify: `C:\Users\Aristotle\.local\bin\openmontage.cmd`
- Verify: `C:\Users\Aristotle\.codex\skills\openmontage\SKILL.md`
- Verify: `.venv\`、`remotion-composer\node_modules\`、`node_modules\hyperframes\`

**Interfaces:**
- Consumes: 完整全局安装。
- Produces: 可审计的验收证据与剩余限制清单。

- [ ] **Step 1: 从仓库外目录运行全局诊断**

Run:

```powershell
Push-Location $env:TEMP
try { & C:\Users\Aristotle\.local\bin\openmontage.cmd doctor } finally { Pop-Location }
```

Expected: JSON 中所有 `checks.*.ok` 为 `true`，退出码 0。

- [ ] **Step 2: 运行 Provider 预检并扫描密钥泄漏**

Run:

```powershell
$Output = & C:\Users\Aristotle\.local\bin\openmontage.cmd preflight | Out-String
$Output
$SecretValues = Get-Content .env | Where-Object { $_ -match '^[A-Z0-9_]+=.+' } | ForEach-Object { ($_ -split '=',2)[1].Trim() } | Where-Object { $_ }
foreach($Secret in $SecretValues) { if($Output.Contains($Secret)) { throw "Secret value leaked by preflight" } }
```

Expected: 显示能力摘要；密钥值扫描为空。

- [ ] **Step 3: 运行 Python 测试**

Run:

```powershell
& .\.venv\Scripts\python.exe -m unittest tests.install.test_openmontage_global_cli tests.install.test_openmontage_installer_contract -v
& .\.venv\Scripts\python.exe -m pytest tests/contracts -v
```

Expected: 安装测试与合约测试全部通过。

- [ ] **Step 4: 运行 Node 安全审计**

Run:

```powershell
Push-Location remotion-composer
try { & npm.cmd audit --package-lock-only --omit=dev } finally { Pop-Location }
```

Expected: 0 vulnerabilities。

- [ ] **Step 5: 运行零密钥演示并验证输出**

Run:

```powershell
& C:\Users\Aristotle\.local\bin\openmontage.cmd demo
```

Expected: 演示渲染退出码 0；使用 FFprobe 验证生成的 MP4 可读取且时长大于 0。

- [ ] **Step 6: 验证全局 Skill 内容与按需触发约束**

Run:

```powershell
Get-Content C:\Users\Aristotle\.codex\skills\openmontage\SKILL.md -Raw
```

Expected: 包含 `$openmontage`、中央路径、密钥限制和“不得自动触发”。提示用户重启 Codex 后在新会话验证发现状态。

- [ ] **Step 7: 最终工作树与提交核验**

Run:

```powershell
git status --short --branch
git log -5 --oneline
```

Expected: 只有预期提交，且没有未提交的源码或配置改动；`.env`、`.venv`、`node_modules` 和 `projects` 不被 Git 跟踪。
