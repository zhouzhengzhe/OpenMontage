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
_SENSITIVE_KEY = re.compile(
    r"(?:api[_-]?key|access[_-]?(?:key|token)|client[_-]?secret|"
    r"private[_-]?key|credentials?|headers?|cookies?|authorization|"
    r"(?:^|[_-])(?:token|secret)(?:$|[_-])|token$|[_-]key$)",
    re.I,
)
_SECRET_VALUE = re.compile(
    r"(?:"
    r"(?-i:(?<![A-Z0-9])(?:[A-Z][A-Z0-9]*_)+(?:KEY|TOKEN|SECRET|CREDENTIALS)(?![A-Z0-9]))"
    r"|(?<![A-Za-z0-9_.-])\.env(?:\.[A-Za-z0-9_-]+)?"
    r"(?=$|[\\/\s,;:)\]}!?'\".])"
    r"|(?<![A-Za-z0-9_.-])(?:credentials?(?:\.[^\\/\s,;:)\]}!?'\"]+)?|"
    r"service[-_]account(?:\.[^\\/\s,;:)\]}!?'\"]+)?|"
    r"private[-_]key(?:\.[^\\/\s,;:)\]}!?'\"]+)?|"
    r"[^\\/\s,;:)\]}!?'\"]+\.(?:pem|key))"
    r"(?=$|[\\/]+|[\s,;:)\]}!?'\".])"
    r"|\b(?:authorization|proxy-authorization|x-api-key|cookie|set-cookie)\s*[:=]"
    r"|(?<![A-Za-z0-9])(?:sk-(?:ant-)?|sk_|gsk_|xai-|gh[pousr]_)[A-Za-z0-9][A-Za-z0-9_-]{3,}"
    r"|\bAKIA[A-Z0-9]{12,}\b"
    r"|\b[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"
    r"|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"
    r"|AIza[0-9A-Za-z_-]{20,}"
    r"|\bBearer\s+[A-Za-z0-9._-]{8,}"
    r")",
    re.I | re.MULTILINE,
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
        config_text = config_file.read_text(encoding="utf-8")
    except OSError as exc:
        raise GenerationProfileError("profile configuration could not be read") from exc
    try:
        config = yaml.safe_load(config_text)
    except yaml.YAMLError as exc:
        raise GenerationProfileError("profile configuration parse failed") from exc
    try:
        schema_text = schema_file.read_text(encoding="utf-8")
    except OSError as exc:
        raise GenerationProfileError("profile schema could not be read") from exc
    try:
        schema = json.loads(schema_text)
    except json.JSONDecodeError as exc:
        raise GenerationProfileError("profile schema JSON parse failed") from exc

    validator_class = jsonschema.validators.validator_for(schema)
    try:
        validator_class.check_schema(schema)
    except jsonschema.SchemaError as exc:
        raise GenerationProfileError("profile schema is invalid") from exc
    try:
        validator_class(schema, format_checker=_FORMAT_CHECKER).validate(config)
    except jsonschema.ValidationError as exc:
        location = "$"
        for segment in exc.absolute_path:
            if isinstance(segment, int):
                location += f"[{segment}]"
            elif _SENSITIVE_KEY.search(str(segment)):
                location += ".<sensitive-field>"
            else:
                location += f".{segment}"
        raise GenerationProfileError(
            f"profile schema validation failed at {location} ({exc.validator})"
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
    try:
        tool_registry.ensure_discovered()
    except Exception as exc:
        return [f"registry discovery failed ({type(exc).__name__})"]
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
        input_schema = getattr(tool, "input_schema", None)
        if not isinstance(input_schema, dict):
            errors.append(f"{location}: input_schema is not an object")
            continue
        properties = input_schema.get("properties", {})
        if not isinstance(properties, dict):
            errors.append(f"{location}: input_schema.properties is not an object")
            continue
        for key, value in candidate["params"].items():
            if key not in properties:
                errors.append(f"{location}: param {key!r} is not accepted by {tool.name}")
                continue
            property_schema = properties[key]
            try:
                property_validator = jsonschema.validators.validator_for(property_schema)
                property_validator.check_schema(property_schema)
            except (jsonschema.SchemaError, TypeError, AttributeError):
                errors.append(
                    f"{location}: param {key!r} has invalid registry schema"
                )
                continue
            allowed = property_schema.get("enum")
            if allowed is not None:
                try:
                    property_validator({"enum": allowed}).validate(value)
                except jsonschema.ValidationError:
                    errors.append(
                        f"{location}: param {key!r} is outside enum"
                    )
                    continue
            try:
                property_validator(
                    property_schema, format_checker=_FORMAT_CHECKER
                ).validate(value)
            except jsonschema.ValidationError as exc:
                errors.append(
                    f"{location}: param {key!r} violates registry schema "
                    f"({exc.validator})"
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
