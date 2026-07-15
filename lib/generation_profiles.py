from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import jsonschema
import yaml


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PROFILE_PATH = ROOT / "generation_profiles.yaml"
DEFAULT_SCHEMA_PATH = ROOT / "schemas" / "config" / "generation_profiles.schema.json"
_SENSITIVE_KEY = re.compile(r"(?:api[_-]?key|access[_-]?token|secret|authorization)", re.I)
_SECRET_VALUE = re.compile(
    r"(?:sk-[A-Za-z0-9_-]{12,}|AIza[0-9A-Za-z_-]{20,}|Bearer\s+[A-Za-z0-9._-]{12,})",
    re.I,
)


class GenerationProfileError(ValueError):
    """Raised when generation profile configuration violates its contract."""


def _secret_findings(value: Any, path: str = "$") -> list[str]:
    findings: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            child = f"{path}.{key}"
            if _SENSITIVE_KEY.search(str(key)):
                findings.append(f"sensitive field at {child}")
            findings.extend(_secret_findings(item, child))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            findings.extend(_secret_findings(item, f"{path}[{index}]"))
    elif isinstance(value, str) and _SECRET_VALUE.search(value):
        findings.append(f"secret-like value at {path}")
    return findings


def load_generation_profiles(
    config_path: Path | None = None,
    schema_path: Path | None = None,
) -> dict[str, Any]:
    config_file = Path(config_path or DEFAULT_PROFILE_PATH)
    schema_file = Path(schema_path or DEFAULT_SCHEMA_PATH)
    try:
        config = yaml.safe_load(config_file.read_text(encoding="utf-8"))
        schema = json.loads(schema_file.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError, json.JSONDecodeError) as exc:
        raise GenerationProfileError(f"profile configuration could not be read: {exc}") from exc
    try:
        jsonschema.validate(instance=config, schema=schema)
    except jsonschema.ValidationError as exc:
        raise GenerationProfileError(
            f"profile schema validation failed: {exc.message}"
        ) from exc
    findings = _secret_findings(config)
    if findings:
        raise GenerationProfileError("; ".join(findings))
    return config
