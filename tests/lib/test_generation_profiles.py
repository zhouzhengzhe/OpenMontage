from __future__ import annotations

import json
import os
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path

import pytest
import yaml

from lib.generation_profiles import (
    GenerationProfileError,
    build_generation_profile_report,
    load_generation_profiles,
    validate_generation_profile_registry,
)


ROOT = Path(__file__).resolve().parents[2]


def test_shipped_profiles_load_with_daily_default() -> None:
    config = load_generation_profiles()
    assert config["version"] == 1
    assert config["default_profile"] == "daily"
    assert set(config["profiles"]) == {"daily", "quality"}
    for profile in config["profiles"].values():
        assert set(profile["capabilities"]) == {
            "video_generation",
            "image_generation",
            "tts",
            "music_generation",
        }


def _write_config(tmp_path: Path, config: dict) -> Path:
    path = tmp_path / "profiles.yaml"
    path.write_text(yaml.safe_dump(config, allow_unicode=True), encoding="utf-8")
    return path


def _shipped_config() -> dict:
    return yaml.safe_load(
        (ROOT / "generation_profiles.yaml").read_text(encoding="utf-8")
    )


def test_loader_rejects_non_daily_default(tmp_path: Path) -> None:
    config = deepcopy(_shipped_config())
    config["default_profile"] = "quality"

    with pytest.raises(GenerationProfileError, match="schema validation failed"):
        load_generation_profiles(_write_config(tmp_path, config))


def test_schema_rejects_sensitive_candidate_field(tmp_path: Path) -> None:
    config = deepcopy(_shipped_config())
    candidate = config["profiles"]["daily"]["capabilities"]["tts"]["candidates"][0]
    candidate["api_key"] = "not-a-real-key"
    with pytest.raises(GenerationProfileError, match="schema validation failed"):
        load_generation_profiles(_write_config(tmp_path, config))


def test_loader_rejects_secret_shaped_value(tmp_path: Path) -> None:
    config = deepcopy(_shipped_config())
    config["profiles"]["daily"]["capabilities"]["tts"]["candidates"][0]["reason"] = (
        "sk-example-value-that-must-never-be-stored"
    )
    with pytest.raises(GenerationProfileError, match="secret-like value"):
        load_generation_profiles(_write_config(tmp_path, config))


@pytest.mark.parametrize(
    "sensitive_key",
    [
        "token",
        "credential",
        "private_key",
        "client-secret",
        "access_key",
        "header",
        "cookie",
        "authToken",
    ],
)
def test_loader_rejects_sensitive_keys_nested_in_params(
    tmp_path: Path,
    sensitive_key: str,
) -> None:
    config = deepcopy(_shipped_config())
    params = config["profiles"]["daily"]["capabilities"]["tts"]["candidates"][0][
        "params"
    ]
    params["transport"] = {sensitive_key: "redacted-fixture"}

    with pytest.raises(GenerationProfileError) as error:
        load_generation_profiles(_write_config(tmp_path, config))

    assert "sensitive field at" in str(error.value)
    assert "redacted-fixture" not in str(error.value)


@pytest.mark.parametrize(
    "secret_value",
    [
        "OPENAI_API_KEY",
        "SOME_PROVIDER_TOKEN",
        "SOME_PROVIDER_SECRET",
        "SOME_PROVIDER_CREDENTIALS",
        r"C:\\service\\.env",
        "./credentials/service-account.json",
        "../private-key.pem",
        "./keys/signing.key",
        "Authorization: Bearer opaque-payload",
        "Cookie: session=opaque-payload",
        "sk-example-value",
        "sk_example_value",
        "sk-ant-example-value",
        "gsk_example_value",
        "xai-example-value",
        "ghp_example_value",
        "AKIAIOSFODNN7EXAMPLE",
        "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.signature123",
        "-----BEGIN PRIVATE KEY-----\nopaque\n-----END PRIVATE KEY-----",
    ],
)
def test_loader_rejects_sensitive_values_without_echoing_them(
    tmp_path: Path,
    secret_value: str,
) -> None:
    config = deepcopy(_shipped_config())
    config["profiles"]["daily"]["capabilities"]["tts"]["candidates"][0][
        "reason"
    ] = secret_value

    with pytest.raises(GenerationProfileError) as error:
        load_generation_profiles(_write_config(tmp_path, config))

    assert "secret-like value at" in str(error.value)
    assert secret_value not in str(error.value)


def test_loader_rejects_nested_authorization_header_without_echoing_value(
    tmp_path: Path,
) -> None:
    config = deepcopy(_shipped_config())
    params = config["profiles"]["daily"]["capabilities"]["tts"]["candidates"][0][
        "params"
    ]
    params["transport"] = {
        "headers": {"Authorization": "Bearer nested-secret-fixture"}
    }

    with pytest.raises(GenerationProfileError) as error:
        load_generation_profiles(_write_config(tmp_path, config))

    message = str(error.value)
    assert "sensitive field at" in message
    assert "nested-secret-fixture" not in message


def test_loader_accepts_safe_nested_candidate_metadata(tmp_path: Path) -> None:
    config = deepcopy(_shipped_config())
    params = config["profiles"]["daily"]["capabilities"]["tts"]["candidates"][0][
        "params"
    ]
    params["render_options"] = {
        "voice_style": "warm",
        "output_format": "mp3",
        "cache_policy": "local-only",
    }

    loaded = load_generation_profiles(_write_config(tmp_path, config))

    assert loaded["default_profile"] == "daily"


def test_loader_wraps_invalid_main_schema_without_leaking_contents(
    tmp_path: Path,
) -> None:
    sentinel = "schema-secret-sentinel-4f2b"
    schema_path = tmp_path / "invalid.schema.json"
    schema_path.write_text(
        json.dumps({"type": 7, "description": sentinel}),
        encoding="utf-8",
    )

    with pytest.raises(GenerationProfileError) as error:
        load_generation_profiles(schema_path=schema_path)

    message = str(error.value)
    assert "profile schema is invalid" in message
    assert sentinel not in message


def test_loader_wraps_non_object_main_schema(tmp_path: Path) -> None:
    schema_path = tmp_path / "array.schema.json"
    schema_path.write_text("[]", encoding="utf-8")

    with pytest.raises(GenerationProfileError, match="profile schema is invalid"):
        load_generation_profiles(schema_path=schema_path)


@dataclass
class FakeStatus:
    value: str


class FakeTool:
    def __init__(self, name: str, provider: str, capability: str, properties: dict) -> None:
        self.name = name
        self.provider = provider
        self.capability = capability
        self.input_schema = {"type": "object", "properties": properties}
        self.status_calls = 0

    def get_status(self) -> FakeStatus:
        self.status_calls += 1
        return FakeStatus("available")


class FakeRegistry:
    def __init__(self, tools: list[FakeTool]) -> None:
        self.tools = {tool.name: tool for tool in tools}
        self.discovered = False

    def ensure_discovered(self) -> None:
        self.discovered = True

    def get(self, name: str) -> FakeTool | None:
        return self.tools.get(name)


class FailingDiscoveryRegistry(FakeRegistry):
    def ensure_discovered(self) -> None:
        raise RuntimeError("registry-secret-sentinel-81ce")


def _minimal_config() -> dict:
    capability = {
        "candidates": [
            {
                "tool": "fake_video",
                "provider": "fake",
                "params": {"mode": "std"},
                "reason": "contract fixture",
            }
        ]
    }
    return {
        "version": 1,
        "default_profile": "daily",
        "profiles": {
            name: {
                "intent": name,
                "capabilities": {
                    "video_generation": deepcopy(capability),
                    "image_generation": {"candidates": []},
                    "tts": {"candidates": []},
                    "music_generation": {"candidates": []},
                },
            }
            for name in ("daily", "quality")
        },
    }


def test_registry_validation_accepts_matching_tool_contract() -> None:
    config = _minimal_config()
    registry = FakeRegistry(
        [FakeTool("fake_video", "fake", "video_generation", {"mode": {"enum": ["std", "pro"]}})]
    )
    assert validate_generation_profile_registry(config, registry) == []
    assert registry.discovered is True


def test_registry_validation_reports_discovery_failure_without_exception_text() -> None:
    errors = validate_generation_profile_registry(
        _minimal_config(), FailingDiscoveryRegistry([])
    )

    assert errors == ["registry discovery failed (RuntimeError)"]
    assert "registry-secret-sentinel-81ce" not in repr(errors)


@pytest.mark.parametrize(
    ("input_schema", "category"),
    [
        ([], "input_schema is not an object"),
        ({"type": "object", "properties": []}, "input_schema.properties is not an object"),
    ],
)
def test_registry_validation_reports_malformed_tool_input_schema(
    input_schema: object,
    category: str,
) -> None:
    config = _minimal_config()
    config["profiles"]["quality"]["capabilities"]["video_generation"]["candidates"] = []
    tool = FakeTool("fake_video", "fake", "video_generation", {})
    tool.input_schema = input_schema

    errors = validate_generation_profile_registry(config, FakeRegistry([tool]))

    assert errors == [
        "profiles.daily.video_generation.candidates[0]: " + category
    ]


def test_registry_validation_reports_invalid_property_schema_without_traceback() -> None:
    config = _minimal_config()
    config["profiles"]["quality"]["capabilities"]["video_generation"]["candidates"] = []
    tool = FakeTool(
        "fake_video",
        "fake",
        "video_generation",
        {"mode": {"type": 7, "description": "property-secret-sentinel-7d09"}},
    )

    errors = validate_generation_profile_registry(config, FakeRegistry([tool]))

    assert errors == [
        "profiles.daily.video_generation.candidates[0]: "
        "param 'mode' has invalid registry schema"
    ]
    assert "property-secret-sentinel-7d09" not in repr(errors)


@pytest.mark.parametrize(
    ("value", "allowed"),
    [
        (True, [1]),
        (1, [True]),
    ],
)
def test_registry_validation_enum_distinguishes_booleans_from_numbers(
    value: object,
    allowed: list[object],
) -> None:
    config = _minimal_config()
    config["profiles"]["quality"]["capabilities"]["video_generation"]["candidates"] = []
    candidate = config["profiles"]["daily"]["capabilities"]["video_generation"]["candidates"][0]
    candidate["params"] = {"mode": value}
    registry = FakeRegistry(
        [FakeTool("fake_video", "fake", "video_generation", {"mode": {"enum": allowed}})]
    )

    errors = validate_generation_profile_registry(config, registry)

    assert errors == [
        "profiles.daily.video_generation.candidates[0]: param 'mode' "
        "is outside enum"
    ]


@pytest.mark.parametrize(
    ("value", "allowed"),
    [
        (1, [1]),
        (True, [True]),
    ],
)
def test_registry_validation_enum_accepts_same_json_type(
    value: object,
    allowed: list[object],
) -> None:
    config = _minimal_config()
    config["profiles"]["quality"]["capabilities"]["video_generation"]["candidates"] = []
    candidate = config["profiles"]["daily"]["capabilities"]["video_generation"]["candidates"][0]
    candidate["params"] = {"mode": value}
    registry = FakeRegistry(
        [FakeTool("fake_video", "fake", "video_generation", {"mode": {"enum": allowed}})]
    )

    assert validate_generation_profile_registry(config, registry) == []


def test_registry_validation_reports_all_candidate_mismatches() -> None:
    config = _minimal_config()
    config["profiles"]["quality"]["capabilities"]["video_generation"]["candidates"] = []
    candidates = config["profiles"]["daily"]["capabilities"]["video_generation"]["candidates"]
    candidate = candidates[0]
    candidate["provider"] = "wrong-provider"
    candidate["params"] = {"mode": "invalid", "api_family": "missing"}
    candidates.append(
        {
            "tool": "missing_video",
            "provider": "missing",
            "params": {"mode": "std"},
            "reason": "unregistered contract fixture",
        }
    )
    registry = FakeRegistry(
        [FakeTool("fake_video", "fake", "image_generation", {"mode": {"enum": ["std", "pro"]}})]
    )
    errors = validate_generation_profile_registry(config, registry)
    assert len(errors) == 5
    assert errors == [
        "profiles.daily.video_generation.candidates[0]: provider 'wrong-provider' "
        "does not match 'fake'",
        "profiles.daily.video_generation.candidates[0]: capability 'video_generation' "
        "does not match 'image_generation'",
        "profiles.daily.video_generation.candidates[0]: param 'mode' is outside enum",
        "profiles.daily.video_generation.candidates[0]: param 'api_family' is not accepted "
        "by fake_video",
        "profiles.daily.video_generation.candidates[1]: tool 'missing_video' is not registered",
    ]


@pytest.mark.parametrize(
    ("property_schema", "value", "validator"),
    [
        ({"type": "integer"}, "not-an-integer", "type"),
        ({"type": "integer", "minimum": 2}, 1, "minimum"),
        ({"type": "integer", "maximum": 2}, 3, "maximum"),
    ],
)
def test_registry_validation_rejects_type_and_range_schema_violations(
    property_schema: dict,
    value: object,
    validator: str,
) -> None:
    config = _minimal_config()
    config["profiles"]["quality"]["capabilities"]["video_generation"]["candidates"] = []
    candidate = config["profiles"]["daily"]["capabilities"]["video_generation"]["candidates"][0]
    candidate["params"] = {"duration": value}
    registry = FakeRegistry(
        [FakeTool("fake_video", "fake", "video_generation", {"duration": property_schema})]
    )

    errors = validate_generation_profile_registry(config, registry)

    assert errors == [
        "profiles.daily.video_generation.candidates[0]: "
        f"param 'duration' violates registry schema ({validator})"
    ]


def test_registry_validation_rejects_pattern_schema_violation() -> None:
    config = _minimal_config()
    config["profiles"]["quality"]["capabilities"]["video_generation"]["candidates"] = []
    candidate = config["profiles"]["daily"]["capabilities"]["video_generation"]["candidates"][0]
    candidate["params"] = {"aspect_ratio": "horizontal"}
    registry = FakeRegistry(
        [
            FakeTool(
                "fake_video",
                "fake",
                "video_generation",
                {"aspect_ratio": {"type": "string", "pattern": r"^\d+:\d+$"}},
            )
        ]
    )

    errors = validate_generation_profile_registry(config, registry)

    assert errors == [
        "profiles.daily.video_generation.candidates[0]: param 'aspect_ratio' "
        "violates registry schema (pattern)"
    ]


def test_registry_validation_rejects_format_schema_violation() -> None:
    config = _minimal_config()
    config["profiles"]["quality"]["capabilities"]["video_generation"]["candidates"] = []
    candidate = config["profiles"]["daily"]["capabilities"]["video_generation"]["candidates"][0]
    candidate["params"] = {"notification_email": "not-an-email"}
    registry = FakeRegistry(
        [
            FakeTool(
                "fake_video",
                "fake",
                "video_generation",
                {"notification_email": {"type": "string", "format": "email"}},
            )
        ]
    )

    errors = validate_generation_profile_registry(config, registry)

    assert errors == [
        "profiles.daily.video_generation.candidates[0]: param 'notification_email' "
        "violates registry schema (format)"
    ]


def test_registry_validation_does_not_echo_candidate_or_schema_values() -> None:
    sentinel = "registry-param-secret-sentinel-504d"
    config = _minimal_config()
    config["profiles"]["quality"]["capabilities"]["video_generation"]["candidates"] = []
    candidate = config["profiles"]["daily"]["capabilities"]["video_generation"][
        "candidates"
    ][0]
    candidate["params"] = {"mode": sentinel}
    registry = FakeRegistry(
        [
            FakeTool(
                "fake_video",
                "fake",
                "video_generation",
                {"mode": {"enum": ["schema-secret-sentinel-ea72"]}},
            )
        ]
    )

    errors = validate_generation_profile_registry(config, registry)

    assert errors == [
        "profiles.daily.video_generation.candidates[0]: param 'mode' is outside enum"
    ]
    assert sentinel not in repr(errors)
    assert "schema-secret-sentinel-ea72" not in repr(errors)


def test_report_contains_available_and_unregistered_statuses_without_environment_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sentinel = "task2-environment-secret-sentinel-9f4e50d7"
    monkeypatch.setenv("OPENMONTAGE_TEST_SECRET", sentinel)
    assert os.environ["OPENMONTAGE_TEST_SECRET"] == sentinel
    config = _minimal_config()
    config["profiles"]["daily"]["capabilities"]["video_generation"]["candidates"].append(
        {
            "tool": "missing_video",
            "provider": "missing",
            "params": {},
            "reason": "unregistered report fixture",
        }
    )
    assert sentinel not in repr(config)
    tool = FakeTool("fake_video", "fake", "video_generation", {"mode": {"enum": ["std", "pro"]}})
    registry = FakeRegistry([tool])
    report = build_generation_profile_report(config, registry)
    candidates = report["profiles"]["daily"]["capabilities"]["video_generation"]
    assert report["ok"] is False
    assert candidates[0]["status"] == "available"
    assert candidates[1]["status"] == "unregistered"
    assert tool.status_calls == 2
    serialized = json.dumps(report, sort_keys=True)
    assert sentinel not in serialized
    assert sentinel not in repr(report)


def test_report_marks_status_not_checked_without_calling_get_status() -> None:
    config = _minimal_config()
    tool = FakeTool("fake_video", "fake", "video_generation", {"mode": {"enum": ["std", "pro"]}})
    report = build_generation_profile_report(config, FakeRegistry([tool]), include_status=False)
    statuses = [
        profile["capabilities"]["video_generation"][0]["status"]
        for profile in report["profiles"].values()
    ]
    assert statuses == ["not_checked", "not_checked"]
    assert tool.status_calls == 0


def test_shipped_profiles_match_current_registry_contracts() -> None:
    from tools.tool_registry import registry

    errors = validate_generation_profile_registry(load_generation_profiles(), registry)
    assert errors == []
