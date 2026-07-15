from __future__ import annotations

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


def test_schema_rejects_sensitive_candidate_field(tmp_path: Path) -> None:
    config = yaml.safe_load((ROOT / "generation_profiles.yaml").read_text(encoding="utf-8"))
    config = deepcopy(config)
    candidate = config["profiles"]["daily"]["capabilities"]["tts"]["candidates"][0]
    candidate["api_key"] = "not-a-real-key"
    path = tmp_path / "profiles.yaml"
    path.write_text(yaml.safe_dump(config, allow_unicode=True), encoding="utf-8")
    with pytest.raises(GenerationProfileError, match="schema validation failed"):
        load_generation_profiles(path)


def test_loader_rejects_secret_shaped_value(tmp_path: Path) -> None:
    config = yaml.safe_load((ROOT / "generation_profiles.yaml").read_text(encoding="utf-8"))
    config = deepcopy(config)
    config["profiles"]["daily"]["capabilities"]["tts"]["candidates"][0]["reason"] = (
        "sk-example-value-that-must-never-be-stored"
    )
    path = tmp_path / "profiles.yaml"
    path.write_text(yaml.safe_dump(config, allow_unicode=True), encoding="utf-8")
    with pytest.raises(GenerationProfileError, match="secret-like value"):
        load_generation_profiles(path)


@dataclass
class FakeStatus:
    value: str


class FakeTool:
    def __init__(self, name: str, provider: str, capability: str, properties: dict) -> None:
        self.name = name
        self.provider = provider
        self.capability = capability
        self.input_schema = {"type": "object", "properties": properties}

    def get_status(self) -> FakeStatus:
        return FakeStatus("available")


class FakeRegistry:
    def __init__(self, tools: list[FakeTool]) -> None:
        self.tools = {tool.name: tool for tool in tools}
        self.discovered = False

    def ensure_discovered(self) -> None:
        self.discovered = True

    def get(self, name: str) -> FakeTool | None:
        return self.tools.get(name)


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


def test_registry_validation_reports_all_candidate_mismatches() -> None:
    config = _minimal_config()
    candidate = config["profiles"]["daily"]["capabilities"]["video_generation"]["candidates"][0]
    candidate["provider"] = "wrong-provider"
    candidate["params"] = {"mode": "invalid", "api_family": "missing"}
    registry = FakeRegistry(
        [FakeTool("fake_video", "fake", "image_generation", {"mode": {"enum": ["std", "pro"]}})]
    )
    errors = validate_generation_profile_registry(config, registry)
    assert any("provider" in error for error in errors)
    assert any("capability" in error for error in errors)
    assert any("not accepted" in error for error in errors)
    assert any("outside enum" in error for error in errors)


def test_report_contains_status_but_no_environment_values() -> None:
    config = _minimal_config()
    registry = FakeRegistry(
        [FakeTool("fake_video", "fake", "video_generation", {"mode": {"enum": ["std", "pro"]}})]
    )
    report = build_generation_profile_report(config, registry)
    candidate = report["profiles"]["daily"]["capabilities"]["video_generation"][0]
    assert report["ok"] is True
    assert candidate["status"] == "available"
    assert "environment" not in repr(report).lower()


def test_shipped_profiles_match_current_registry_contracts() -> None:
    from tools.tool_registry import registry

    errors = validate_generation_profile_registry(load_generation_profiles(), registry)
    assert errors == []
