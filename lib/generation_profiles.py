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
_FORMAT_CHECKER = jsonschema.FormatChecker()


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


def _iter_candidates(config: dict[str, Any]):
    for profile_name, profile in config["profiles"].items():
        for capability, capability_config in profile["capabilities"].items():
            for index, candidate in enumerate(capability_config["candidates"]):
                yield profile_name, capability, index, candidate


def validate_generation_profile_registry(
    config: dict[str, Any],
    tool_registry: Any,
) -> list[str]:
    tool_registry.ensure_discovered()
    errors: list[str] = []
    for profile_name, capability, index, candidate in _iter_candidates(config):
        location = f"profiles.{profile_name}.{capability}.candidates[{index}]"
        tool = tool_registry.get(candidate["tool"])
        if tool is None:
            errors.append(f"{location}: tool {candidate['tool']!r} is not registered")
            continue
        if tool.provider != candidate["provider"]:
            errors.append(
                f"{location}: provider {candidate['provider']!r} does not match {tool.provider!r}"
            )
        if tool.capability != capability:
            errors.append(
                f"{location}: capability {capability!r} does not match {tool.capability!r}"
            )
        properties = tool.input_schema.get("properties", {})
        for key, value in candidate["params"].items():
            if key not in properties:
                errors.append(f"{location}: param {key!r} is not accepted by {tool.name}")
                continue
            property_schema = properties[key]
            allowed = property_schema.get("enum")
            if allowed is not None and value not in allowed:
                errors.append(
                    f"{location}: param {key!r} value {value!r} is outside enum {allowed!r}"
                )
                continue
            try:
                jsonschema.validate(
                    instance=value,
                    schema=property_schema,
                    format_checker=_FORMAT_CHECKER,
                )
            except jsonschema.ValidationError as exc:
                errors.append(
                    f"{location}: param {key!r} value {value!r} "
                    f"violates schema: {exc.message}"
                )
    return errors


def build_generation_profile_report(
    config: dict[str, Any],
    tool_registry: Any,
    include_status: bool = True,
) -> dict[str, Any]:
    errors = validate_generation_profile_registry(config, tool_registry)
    profiles: dict[str, Any] = {}
    for profile_name, profile in config["profiles"].items():
        capabilities: dict[str, list[dict[str, Any]]] = {}
        for capability, capability_config in profile["capabilities"].items():
            candidates: list[dict[str, Any]] = []
            for candidate in capability_config["candidates"]:
                item = dict(candidate)
                tool = tool_registry.get(candidate["tool"])
                if include_status and tool is not None:
                    item["status"] = tool.get_status().value
                elif include_status:
                    item["status"] = "unregistered"
                else:
                    item["status"] = "not_checked"
                candidates.append(item)
            capabilities[capability] = candidates
        profiles[profile_name] = {
            "intent": profile["intent"],
            "capabilities": capabilities,
        }
    return {
        "ok": not errors,
        "version": config["version"],
        "default_profile": config["default_profile"],
        "errors": errors,
        "profiles": profiles,
    }
