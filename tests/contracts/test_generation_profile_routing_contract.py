from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ROUTING = ROOT / "skills" / "meta" / "generation-profile-routing.md"
GUIDE = ROOT / "AGENT_GUIDE.md"
CONTEXT = ROOT / "PROJECT_CONTEXT.md"
GLOBAL_SKILL = ROOT / "scripts" / "windows" / "openmontage" / "SKILL.md"


def test_routing_skill_defines_precedence_and_negation() -> None:
    text = ROUTING.read_text(encoding="utf-8")
    for phrase in (
        "profile=daily",
        "profile=quality",
        "日常模式",
        "高质量模式",
        "不要高质量模式",
        "当前运行已批准",
    ):
        assert phrase in text


def test_routing_skill_forbids_silent_fallback_and_preserves_budget_gate() -> None:
    text = ROUTING.read_text(encoding="utf-8")
    assert "不得静默回退" in text
    assert "single_action_approval_usd" in text
    assert "decision_log" in text
    assert "category" in text and "subject" in text


def test_agent_guide_requires_profile_resolution_before_provider_proposal() -> None:
    text = GUIDE.read_text(encoding="utf-8")
    assert "Generation Profiles (Mandatory)" in text
    assert "skills/meta/generation-profile-routing.md" in text
    assert "generation_profiles.yaml" in text


def test_global_skill_reads_central_profile_policy() -> None:
    text = GLOBAL_SKILL.read_text(encoding="utf-8")
    assert "generation_profiles.yaml" in text
    assert "skills/meta/generation-profile-routing.md" in text
    assert "不得自动触发" in text


def test_project_context_lists_profile_sources_of_truth() -> None:
    text = CONTEXT.read_text(encoding="utf-8")
    assert "generation_profiles.yaml" in text
    assert "lib/generation_profiles.py" in text
