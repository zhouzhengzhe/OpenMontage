from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest
import yaml

from lib.generation_profiles import GenerationProfileError, load_generation_profiles


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
