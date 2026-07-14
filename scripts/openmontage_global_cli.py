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
    return Path(
        os.environ.get("OPENMONTAGE_HOME", str(DEFAULT_HOME))
    ).expanduser().resolve()


def _probe(executable: str, *args: str) -> dict[str, object]:
    resolved = shutil.which(executable)
    if not resolved:
        return {"ok": False, "detail": f"{executable} not found"}
    completed = subprocess.run(
        [resolved, *args],
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )
    output = (completed.stdout or completed.stderr).splitlines()
    return {
        "ok": completed.returncode == 0,
        "detail": output[0] if output else f"exit {completed.returncode}",
    }


def _check_hyperframes(home: Path) -> dict[str, object]:
    package = home / "node_modules" / "hyperframes" / "package.json"
    required = "0.7.57"
    if not package.is_file():
        return {"ok": False, "detail": f"required version {required}; package not found"}
    try:
        installed = json.loads(package.read_text(encoding="utf-8")).get("version")
    except (OSError, json.JSONDecodeError):
        return {"ok": False, "detail": f"required version {required}; package unreadable"}
    return {
        "ok": installed == required,
        "detail": f"required version {required}; installed {installed or 'unknown'}",
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
            "detail": str(
                home / "remotion-composer" / "node_modules" / "remotion"
            ),
        },
        "hyperframes": _check_hyperframes(home),
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
    raw_args = list(sys.argv[1:] if argv is None else argv)
    home = resolve_home()
    if raw_args[:1] == ["demo"]:
        if not (home / "AGENT_GUIDE.md").is_file():
            print(f"OpenMontage home is invalid: {home}", file=sys.stderr)
            return 2
        return _run(
            home,
            [sys.executable, str(home / "render_demo.py"), *raw_args[1:]],
        )
    args = build_parser().parse_args(raw_args)
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
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
