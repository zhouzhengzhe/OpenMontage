from __future__ import annotations

import importlib.util
import re
from pathlib import Path
from types import ModuleType


ROOT = Path(__file__).resolve().parents[2]
ROUTING = ROOT / "skills" / "meta" / "generation-profile-routing.md"
GUIDE = ROOT / "AGENT_GUIDE.md"
CONTEXT = ROOT / "PROJECT_CONTEXT.md"
GLOBAL_SKILL = ROOT / "scripts" / "windows" / "openmontage" / "SKILL.md"
GLOBAL_CLI = ROOT / "scripts" / "openmontage_global_cli.py"


def _section(text: str, heading: str) -> str:
    start = text.index(heading) + len(heading)
    end = text.find("\n## ", start)
    return text[start:] if end == -1 else text[start:end]


def _routing_case_table(section: str) -> dict[str, tuple[str, str]]:
    rows: dict[str, tuple[str, str]] = {}
    for line in section.splitlines():
        if not line.startswith("| `"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) != 3:
            continue
        request = cells[0].strip("`")
        rows[request] = (cells[1].strip("`"), cells[2])
    return rows


def _load_global_cli() -> ModuleType:
    spec = importlib.util.spec_from_file_location("openmontage_global_cli", GLOBAL_CLI)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_routing_skill_defines_exact_five_level_precedence() -> None:
    text = ROUTING.read_text(encoding="utf-8")
    precedence = _section(text, "## 解析优先级")
    items = re.findall(r"(?m)^(\d+)\. (.+)$", precedence)

    assert [number for number, _ in items] == ["1", "2", "3", "4", "5"]
    assert "profile=daily" in items[0][1] and "profile=quality" in items[0][1]
    assert "Provider" in items[1][1] and "覆盖档位候选" in items[1][1]
    assert "当前运行已批准" in items[2][1] and "decision_log" in items[2][1]
    assert "质量意图" in items[3][1] and "quality" in items[3][1]
    assert "其余请求" in items[4][1] and "daily" in items[4][1]


def test_routing_skill_defines_negation_override_and_conflict_semantics() -> None:
    text = ROUTING.read_text(encoding="utf-8")
    precedence = _section(text, "## 解析优先级")

    assert "否定表达只抑制第 4 级质量意图自动触发" in precedence
    assert "显式 `profile=quality` 按第 1 级优先并覆盖否定表达" in precedence


def test_routing_skill_normalizes_all_explicit_profile_aliases() -> None:
    text = ROUTING.read_text(encoding="utf-8")
    assert "### 显式档位归一化与冲突" in text
    routing = _section(text, "### 显式档位归一化与冲突")
    mappings = re.findall(
        r"(?m)^- `([^`]+)`、`([^`]+)` -> `([^`]+)`$",
        routing,
    )

    assert mappings == [
        ("日常模式", "profile=daily", "daily"),
        ("高质量模式", "profile=quality", "quality"),
    ]


def test_routing_skill_conflict_matrix_covers_alias_combinations() -> None:
    text = ROUTING.read_text(encoding="utf-8")
    assert "### 显式档位归一化与冲突" in text
    routing = _section(text, "### 显式档位归一化与冲突")
    rows = _routing_case_table(routing)

    conflicting = (
        "日常模式 高质量模式",
        "日常模式 profile=quality",
        "profile=daily 高质量模式",
    )
    for request in conflicting:
        normalized, result = rows[request]
        assert normalized == "{daily, quality}"
        assert "停止提案与执行" in result
        assert "要求用户选择" in result
        assert "不得生成" in result

    normalized, result = rows["日常模式 profile=daily"]
    assert normalized == "{daily}"
    assert "不冲突" in result and "daily" in result


def test_routing_skill_resets_profile_for_every_new_run() -> None:
    text = ROUTING.read_text(encoding="utf-8")
    precedence = _section(text, "## 解析优先级")

    assert "每个新生产运行开始时，先把档位状态重置为“未解析”" in precedence
    assert "不得继承上一次运行的档位解析结果" in precedence


def test_routing_skill_forbids_silent_fallback_and_preserves_budget_gate() -> None:
    text = ROUTING.read_text(encoding="utf-8")
    assert "不得静默回退" in text
    assert "single_action_approval_usd" in text
    assert "decision_log" in text
    assert "category" in text and "subject" in text


def test_routing_skill_validates_candidate_params_then_full_request() -> None:
    text = ROUTING.read_text(encoding="utf-8")
    proposal = _section(text, "## Provider 提案流程")

    candidate_validation = "档位候选的 `params` 先按目标工具 `input_schema` 做属性级校验"
    request_validation = "最终完整生成请求在执行前再按目标工具完整 `input_schema` 校验"
    assert candidate_validation in proposal
    assert request_validation in proposal
    assert proposal.index(candidate_validation) < proposal.index(request_validation)


def test_agent_guide_requires_profile_resolution_before_provider_proposal() -> None:
    text = GUIDE.read_text(encoding="utf-8")
    section = _section(text, "## Generation Profiles (Mandatory)")
    assert "Before proposing any generation provider" in section
    assert "skills/meta/generation-profile-routing.md" in section
    assert "generation_profiles.yaml" in section
    assert "Paid-provider disclosure remains governed separately" in section


def test_global_skill_reads_central_profile_policy() -> None:
    text = GLOBAL_SKILL.read_text(encoding="utf-8")
    assert "generation_profiles.yaml" in text
    assert "skills/meta/generation-profile-routing.md" in text
    assert "不得自动触发" in text


def test_global_cli_really_parses_profiles_validate() -> None:
    cli = _load_global_cli()
    args = cli.build_parser().parse_args(["profiles", "validate"])

    assert args.command == "profiles"
    assert args.action == "validate"


def test_project_context_lists_profile_sources_of_truth() -> None:
    text = CONTEXT.read_text(encoding="utf-8")
    assert "generation_profiles.yaml" in text
    assert "lib/generation_profiles.py" in text
