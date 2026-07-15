# Global Generation Profiles Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为全局 OpenMontage 增加默认日常档和按需高质量档，使任意项目与新 Codex 会话无需改动 `.env` 即可安全选择生成工具和模型。

**Architecture:** 使用根目录 `generation_profiles.yaml` 声明少量有意图的 Provider 候选，使用 JSON Schema 和 `lib/generation_profiles.py` 做纯加载、敏感字段扫描与注册表契约校验。自然语言档位解析继续由 Agent 按 `skills/meta/generation-profile-routing.md` 执行；Python 只为全局 CLI 提供只读的 `profiles`/`profiles validate` 诊断，不承担生成路由或静默回退。

**Tech Stack:** Python 3.14、PyYAML、jsonschema、pytest/unittest、PowerShell、OpenMontage Tool Registry、Markdown Skills、YAML/JSON Schema。

## Global Constraints

- 默认档固定为 `daily`；每个新生产运行重新解析，不持久化上一次的 `quality` 状态。
- 显式档位 > 显式 Provider/模型 > 当前运行已批准决定 > 明确质量意图 > 默认 `daily`。
- API 密钥只保存在 `D:\SoftDocument\CodexProject\OpenMontage\.env`；不得复制、显示或写入 Git、用户级 Provider 环境变量、档位文件或其他项目。
- 所有工具、Provider 与参数必须在执行前由当前注册表和目标工具 `input_schema` 校验。
- 候选顺序只形成待批准短名单，不授予静默回退权限。
- `quality` 不修改 `budget.total_usd` 或 `budget.single_action_approval_usd=0.50`，不绕过付费披露、样片、流水线和人工检查点。
- Provider/模型中途变化必须先获批准，并以相同 `category` 与 `subject` 追加 `decision_log` 修订条目。
- Agent 决定档位和 Provider；Python 只负责配置加载、结构校验、注册表契约校验和无密钥诊断。
- 全局 `$openmontage` 仍只按显式调用或明确使用 OpenMontage 的请求触发，普通开发任务不得自动加载。

---

### Task 1: 声明式档位、JSON Schema 与安全加载器

**Files:**
- Create: `generation_profiles.yaml`
- Create: `schemas/config/generation_profiles.schema.json`
- Create: `lib/generation_profiles.py`
- Create: `tests/lib/test_generation_profiles.py`

**Interfaces:**
- Consumes: 仓库根目录、PyYAML、jsonschema。
- Produces: `GenerationProfileError`；`load_generation_profiles(config_path: Path | None = None, schema_path: Path | None = None) -> dict[str, Any]`；后续任务直接使用已完成结构校验和敏感信息扫描的字典。

- [ ] **Step 1: 写入档位加载与安全扫描的失败测试**

创建 `tests/lib/test_generation_profiles.py`：

```python
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
```

- [ ] **Step 2: 运行测试并确认因模块或文件尚不存在而失败**

Run:

```powershell
& .\.venv\Scripts\python.exe -m pytest tests/lib/test_generation_profiles.py -v
```

Expected: FAIL，首个错误为 `ModuleNotFoundError: No module named 'lib.generation_profiles'`。

- [ ] **Step 3: 创建完整 JSON Schema**

创建 `schemas/config/generation_profiles.schema.json`：

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "generation_profiles.schema.json",
  "title": "OpenMontage Generation Profiles",
  "type": "object",
  "additionalProperties": false,
  "required": ["version", "default_profile", "profiles"],
  "properties": {
    "version": {"const": 1},
    "default_profile": {"enum": ["daily", "quality"]},
    "profiles": {
      "type": "object",
      "additionalProperties": false,
      "required": ["daily", "quality"],
      "properties": {
        "daily": {"$ref": "#/$defs/profile"},
        "quality": {"$ref": "#/$defs/profile"}
      }
    }
  },
  "$defs": {
    "profile": {
      "type": "object",
      "additionalProperties": false,
      "required": ["intent", "capabilities"],
      "properties": {
        "intent": {"type": "string", "minLength": 1},
        "capabilities": {
          "type": "object",
          "additionalProperties": false,
          "required": ["video_generation", "image_generation", "tts", "music_generation"],
          "properties": {
            "video_generation": {"$ref": "#/$defs/capability"},
            "image_generation": {"$ref": "#/$defs/capability"},
            "tts": {"$ref": "#/$defs/capability"},
            "music_generation": {"$ref": "#/$defs/capability"}
          }
        }
      }
    },
    "capability": {
      "type": "object",
      "additionalProperties": false,
      "required": ["candidates"],
      "properties": {
        "candidates": {
          "type": "array",
          "minItems": 1,
          "items": {"$ref": "#/$defs/candidate"}
        }
      }
    },
    "candidate": {
      "type": "object",
      "additionalProperties": false,
      "required": ["tool", "provider", "params", "reason"],
      "properties": {
        "tool": {"type": "string", "minLength": 1},
        "provider": {"type": "string", "minLength": 1},
        "params": {"type": "object"},
        "reason": {"type": "string", "minLength": 1}
      }
    }
  }
}
```

- [ ] **Step 4: 创建两个档位的实际候选配置**

创建 `generation_profiles.yaml`：

```yaml
version: 1
default_profile: daily

profiles:
  daily:
    intent: balanced_cost_latency
    capabilities:
      video_generation:
        candidates:
          - tool: gemini_omni_video
            provider: gemini_omni
            params: {}
            reason: 日常视频优先兼顾生成能力与迭代效率
          - tool: kling_official_video
            provider: kling_official
            params:
              model_name: kling-v3
              mode: std
              resolution: 720p
            reason: 首选不可用时提供稳定的标准质量路径
          - tool: grok_video
            provider: grok
            params:
              resolution: 720p
            reason: 提供短视频日常迭代候选
      image_generation:
        candidates:
          - tool: google_imagen
            provider: google_imagen
            params:
              model: imagen-4.0-fast-generate-001
            reason: 日常图片优先低延迟模型
          - tool: dashscope_image
            provider: dashscope
            params:
              model: z-image-turbo
            reason: 提供快速中文生态图片候选
          - tool: grok_image
            provider: grok
            params:
              model: grok-imagine-image
              resolution: 1k
            reason: 提供通用日常图片候选
      tts:
        candidates:
          - tool: dashscope_tts
            provider: dashscope
            params:
              model: qwen3-tts-flash
            reason: 日常中文配音优先低延迟路径
          - tool: google_tts
            provider: google_tts
            params: {}
            reason: 提供多语言日常配音候选
      music_generation:
        candidates:
          - tool: google_music
            provider: google
            params: {}
            reason: 日常背景音乐使用固定的 Lyria 生成路径
          - tool: music_gen
            provider: elevenlabs
            params: {}
            reason: 首选不可用时提供另一条音乐生成路径

  quality:
    intent: maximize_output_quality
    capabilities:
      video_generation:
        candidates:
          - tool: seedance_video
            provider: seedance
            params:
              model_variant: standard
              resolution: 720p
            reason: 精品视频优先电影感与运动一致性
          - tool: kling_official_video
            provider: kling_official
            params:
              model_name: kling-v3
              mode: pro
              resolution: 1080p
            reason: 提供高质量 Kling 专业模式候选
          - tool: veo_video
            provider: veo
            params:
              model_variant: veo3.1
              resolution: 1080p
            reason: 提供高质量原生音视频候选
      image_generation:
        candidates:
          - tool: openai_image
            provider: openai
            params:
              model: gpt-image-2
              quality: high
            reason: 精品图片优先细节、文字与编辑能力
          - tool: dashscope_image
            provider: dashscope
            params:
              model: qwen-image-2.0-pro
            reason: 提供高质量中文图像候选
          - tool: google_imagen
            provider: google_imagen
            params:
              model: imagen-4.0-ultra-generate-001
            reason: 提供高保真 Imagen 候选
      tts:
        candidates:
          - tool: elevenlabs_tts
            provider: elevenlabs
            params:
              model_id: eleven_multilingual_v2
            reason: 精品配音优先自然度与角色表现
          - tool: dashscope_tts
            provider: dashscope
            params:
              model: qwen3-tts-instruct-flash
            reason: 提供可指令控制的中文配音候选
      music_generation:
        candidates:
          - tool: music_gen
            provider: elevenlabs
            params: {}
            reason: 精品音乐优先完整结构与情绪控制
          - tool: google_music
            provider: google
            params: {}
            reason: 提供 Lyria 高质量音乐候选
```

- [ ] **Step 5: 实现结构校验和敏感信息扫描**

创建 `lib/generation_profiles.py`：

```python
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
```

- [ ] **Step 6: 运行加载与安全测试**

Run:

```powershell
& .\.venv\Scripts\python.exe -m pytest tests/lib/test_generation_profiles.py -v
```

Expected: `3 passed`。

- [ ] **Step 7: 检查格式并提交**

Run:

```powershell
git diff --check
git add generation_profiles.yaml schemas/config/generation_profiles.schema.json lib/generation_profiles.py tests/lib/test_generation_profiles.py
git commit -m "feat: add validated generation profiles"
```

Expected: `git diff --check` 无输出，提交成功。

---

### Task 2: 注册表契约校验与无密钥状态报告

**Files:**
- Modify: `lib/generation_profiles.py`
- Modify: `tests/lib/test_generation_profiles.py`

**Interfaces:**
- Consumes: Task 1 的已校验档位字典；`ToolRegistry.ensure_discovered()`、`ToolRegistry.get(name)`；每个工具的 `name`、`provider`、`capability`、`input_schema` 和 `get_status()`。
- Produces: `validate_generation_profile_registry(config: dict[str, Any], tool_registry: Any) -> list[str]`；`build_generation_profile_report(config: dict[str, Any], tool_registry: Any, include_status: bool = True) -> dict[str, Any]`。

- [ ] **Step 1: 增加注册表契约的失败测试**

在 `tests/lib/test_generation_profiles.py` 追加：

```python
from dataclasses import dataclass

from lib.generation_profiles import (
    build_generation_profile_report,
    validate_generation_profile_registry,
)


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
```

- [ ] **Step 2: 运行新增测试并确认接口尚不存在**

Run:

```powershell
& .\.venv\Scripts\python.exe -m pytest tests/lib/test_generation_profiles.py -v
```

Expected: FAIL，导入 `build_generation_profile_report` 或 `validate_generation_profile_registry` 失败。

- [ ] **Step 3: 实现工具、Provider、能力和参数契约校验**

在 `lib/generation_profiles.py` 追加：

```python
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
            allowed = properties[key].get("enum")
            if allowed is not None and value not in allowed:
                errors.append(
                    f"{location}: param {key!r} value {value!r} is outside enum {allowed!r}"
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
```

- [ ] **Step 4: 运行注册表与发布配置测试**

Run:

```powershell
& .\.venv\Scripts\python.exe -m pytest tests/lib/test_generation_profiles.py -v
```

Expected: `7 passed`，其中发布配置契约测试不得调用任何生成 API。

- [ ] **Step 5: 提交注册表契约**

Run:

```powershell
git diff --check
git add lib/generation_profiles.py tests/lib/test_generation_profiles.py
git commit -m "feat: validate profile registry contracts"
```

Expected: 提交成功。

---

### Task 3: Agent 路由 Skill 与全局入口合约

**Files:**
- Create: `skills/meta/generation-profile-routing.md`
- Create: `tests/contracts/test_generation_profile_routing_contract.py`
- Modify: `AGENT_GUIDE.md:429`
- Modify: `PROJECT_CONTEXT.md:21-31`
- Modify: `PROJECT_CONTEXT.md:59-81`
- Modify: `scripts/windows/openmontage/SKILL.md:8-17`
- Modify: `tests/install/test_openmontage_installer_contract.py`

**Interfaces:**
- Consumes: Task 1 的 `generation_profiles.yaml`；`AGENT_GUIDE.md` 的 Provider 披露、预算、审批和 `decision_log` 合约。
- Produces: 所有 Agent 使用的确定性优先级和禁止静默回退规则；全局 Skill 在任意项目和新会话中读取中央策略。

- [ ] **Step 1: 写入路由与全局 Skill 的失败合约测试**

创建 `tests/contracts/test_generation_profile_routing_contract.py`：

```python
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
```

在 `tests/install/test_openmontage_installer_contract.py` 的 `InstallerContractTests` 中追加：

```python
    def test_skill_routes_to_central_generation_profiles(self) -> None:
        text = SKILL.read_text(encoding="utf-8")
        self.assertIn("generation_profiles.yaml", text)
        self.assertIn("skills/meta/generation-profile-routing.md", text)
        self.assertNotIn("API 密钥值", text)
```

- [ ] **Step 2: 运行合约测试并确认路由文件缺失**

Run:

```powershell
& .\.venv\Scripts\python.exe -m pytest tests/contracts/test_generation_profile_routing_contract.py -v
& .\.venv\Scripts\python.exe -m unittest tests.install.test_openmontage_installer_contract -v
```

Expected: pytest FAIL 于 `FileNotFoundError`；unittest FAIL 于缺少中央档位引用。

- [ ] **Step 3: 创建完整的档位路由 Skill**

创建 `skills/meta/generation-profile-routing.md`：

```markdown
# Generation Profile Routing

在每个 OpenMontage 生产请求的 Provider 提案之前读取中央 `generation_profiles.yaml`，并按本 Skill 解析 `daily` 或 `quality`。档位只产生候选短名单，不构成付费调用授权。

## 解析优先级

1. 显式档位：`日常模式`、`高质量模式`、`profile=daily`、`profile=quality`。
2. 用户显式 Provider、工具、模型或变体：覆盖档位候选，但仍需注册表、费用和审批检查。
3. 当前运行已批准并写入 `decision_log` 的 Provider/模型：同一运行保持粘性。
4. 明确质量意图：“高质量、精品、最终成片、质量优先、最高质量”触发 `quality`。
5. 其余请求使用 `daily`。

只分析用户对本次产物的制作意图。引用、标题或素材正文中偶然出现质量词不触发。`不要高质量模式`、`无需精品生成`、`高质量不重要` 等否定表达抑制自动触发并使用 `daily`；同一句中的显式 `profile=quality` 仍优先。

每个新生产运行重新解析，禁止把上一次 `quality` 保存为全局默认。

## Provider 提案流程

1. 运行 `provider_menu_summary()`，报告实际能力。
2. 运行 `openmontage profiles validate` 或等价只读校验。
3. 从已解析档位读取对应能力候选，只保留注册表存在且契约匹配的项。
4. 在付费调用前披露：档位、精确工具、Provider、模型或变体、原因、样片或批量状态、预计费用。
5. 等待 Provider/模型和生产计划批准，再写入 `decision_log` 并执行流水线。

## 强制约束

- 候选顺序不是自动回退链；首选失败时不得静默回退。
- 报告失败属于认证、模型访问、额度、Provider 状态、工具缺陷或设计质量中的哪一类。
- 列出当前实际可用候选和推荐项，等待用户批准后才能替代。
- `quality` 不修改 `budget.total_usd` 或 `single_action_approval_usd`，不得跳过样片、流水线阶段或人工检查点。
- 中途切换档位、Provider 或模型是重大变更。先获批准，再用相同 `category` 与相同 `subject` 追加修订后的 `decision_log` 条目。
- API 密钥只从中央 `.env` 加载；不得显示、复制、写入档位文件或用户级 Provider 环境变量。

## 示例

- `$openmontage 做一个 30 秒产品视频` -> `daily`
- `$openmontage 高质量生成最终成片：做一个 30 秒产品视频` -> `quality`
- `$openmontage 日常模式：质量要稳定` -> `daily`
- `$openmontage profile=quality：制作品牌片` -> `quality`
- `$openmontage 不要高质量模式，先快速试稿` -> `daily`
```

- [ ] **Step 4: 把档位规则接入 Agent Guide、项目上下文和全局 Skill**

在 `AGENT_GUIDE.md` 的 `## Capability Discovery` 之前插入：

```markdown
## Generation Profiles (Mandatory)

Before proposing any paid generation provider, read `skills/meta/generation-profile-routing.md` and the central `generation_profiles.yaml`. Resolve `daily` or `quality`, validate candidates against the live registry, and disclose the resolved profile in the provider proposal.

The profile is a preference policy, not approval and not an automatic fallback chain. Provider/model substitutions still require the Decision Communication Contract, budget checks, and an append-only `decision_log` revision.
```

在 `PROJECT_CONTEXT.md` 的 `## Source of Truth` 列表中加入：

```markdown
- **Generation profile policy:** `generation_profiles.yaml` + `skills/meta/generation-profile-routing.md`
```

在 `PROJECT_CONTEXT.md` 的 Key Files 表加入：

```markdown
| `generation_profiles.yaml` | Non-secret daily/quality provider preferences |
| `lib/generation_profiles.py` | Profile schema, secret scan, and registry-contract diagnostics |
```

将 `scripts/windows/openmontage/SKILL.md` 的步骤更新为：

```markdown
1. 从用户环境变量 `OPENMONTAGE_HOME` 定位中央仓库；缺失时使用 `D:\SoftDocument\CodexProject\OpenMontage`。
2. 在采取任何 OpenMontage 行动前，完整读取中央 `AGENT_GUIDE.md` 与 `PROJECT_CONTEXT.md`。
3. 在每个生成 Provider 提案前，读取中央 `generation_profiles.yaml` 与 `skills/meta/generation-profile-routing.md`，解析并披露 `daily` 或 `quality`。
4. 使用全局 `openmontage` 命令做 `doctor`、`preflight` 与 `profiles validate`；Python 命令只允许使用中央 `.venv`。
5. 所有检查点、资产和成片写入 `OPENMONTAGE_PROJECTS_DIR` 指向的中央 `projects`。
6. API 密钥只从中央 `.env` 加载；不得打印、复制到用户环境变量或写入其他项目。
7. 所有视频制作继续遵守流水线、Provider 披露、费用确认、渲染运行时选择与人工审批规则；档位候选不得静默回退。
8. 外部项目素材使用绝对路径传入；不得修改来源项目，除非用户明确要求。
```

- [ ] **Step 5: 运行路由和安装入口合约测试**

Run:

```powershell
& .\.venv\Scripts\python.exe -m pytest tests/contracts/test_generation_profile_routing_contract.py -v
& .\.venv\Scripts\python.exe -m unittest tests.install.test_openmontage_installer_contract -v
```

Expected: 路由测试 `5 passed`；安装器 unittest 全部通过。

- [ ] **Step 6: 提交 Agent 路由合同**

Run:

```powershell
git diff --check
git add skills/meta/generation-profile-routing.md AGENT_GUIDE.md PROJECT_CONTEXT.md scripts/windows/openmontage/SKILL.md tests/contracts/test_generation_profile_routing_contract.py tests/install/test_openmontage_installer_contract.py
git commit -m "docs: add generation profile routing"
```

Expected: 提交成功。

---

### Task 4: 全局 CLI 的 `profiles` 与 `profiles validate`

**Files:**
- Modify: `scripts/openmontage_global_cli.py:75-129`
- Modify: `tests/install/test_openmontage_global_cli.py`

**Interfaces:**
- Consumes: Task 1/2 的 `load_generation_profiles()`、`validate_generation_profile_registry()`、`build_generation_profile_report()`；中央 Tool Registry。
- Produces: `openmontage profiles` 返回无密钥的档位和实时状态 JSON；`openmontage profiles validate` 只做结构与契约检查并以退出码表达成功或失败。

- [ ] **Step 1: 写入 CLI 解析、成功报告和密钥输出边界的失败测试**

在 `tests/install/test_openmontage_global_cli.py` 中更新 help 测试并追加：

```python
    def test_help_lists_profiles(self) -> None:
        result = self.run_cli("--help")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("profiles", result.stdout)

    def test_profiles_validate_checks_shipped_contract_without_secrets(self) -> None:
        result = self.run_cli("profiles", "validate", home=REPO_ROOT)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertTrue(report["ok"])
        self.assertEqual(report["default_profile"], "daily")
        self.assertEqual(report["errors"], [])
        for marker in ("OPENAI_API_KEY", "FAL_KEY", "GOOGLE_API_KEY", "Bearer "):
            self.assertNotIn(marker, result.stdout)
```

- [ ] **Step 2: 运行 CLI 测试并确认 `profiles` 尚不是合法子命令**

Run:

```powershell
& .\.venv\Scripts\python.exe -m unittest tests.install.test_openmontage_global_cli -v
```

Expected: 新测试 FAIL，stderr 包含 `invalid choice: 'profiles'`。

- [ ] **Step 3: 实现只读档位诊断函数**

在 `scripts/openmontage_global_cli.py` 的 `preflight()` 后加入：

```python
def profiles(home: Path, validate_only: bool = False) -> int:
    sys.path.insert(0, str(home))
    from lib.generation_profiles import (
        GenerationProfileError,
        build_generation_profile_report,
        load_generation_profiles,
        validate_generation_profile_registry,
    )
    from tools.tool_registry import registry

    try:
        config = load_generation_profiles(home / "generation_profiles.yaml")
        registry.ensure_discovered()
        if validate_only:
            errors = validate_generation_profile_registry(config, registry)
            report = {
                "ok": not errors,
                "version": config["version"],
                "default_profile": config["default_profile"],
                "errors": errors,
            }
        else:
            report = build_generation_profile_report(config, registry, include_status=True)
    except GenerationProfileError as exc:
        report = {"ok": False, "errors": [str(exc)]}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1
```

- [ ] **Step 4: 把命令加入 argparse 和 main 分派**

在 `build_parser()` 中加入：

```python
    profiles_parser = subparsers.add_parser("profiles")
    profiles_parser.add_argument("action", nargs="?", choices=["validate"], default="show")
```

在 `main()` 的 `preflight` 分支后加入：

```python
    if args.command == "profiles":
        return profiles(home, validate_only=args.action == "validate")
```

保持现有 home 合法性检查不变，因此无效 `OPENMONTAGE_HOME` 返回退出码 2，且不会回退到中央默认目录。

- [ ] **Step 5: 运行 CLI 与档位单元测试**

Run:

```powershell
& .\.venv\Scripts\python.exe -m unittest tests.install.test_openmontage_global_cli -v
& .\.venv\Scripts\python.exe -m pytest tests/lib/test_generation_profiles.py -v
```

Expected: 两组测试全部通过；`profiles validate` 输出 JSON 且 `ok=true`。

- [ ] **Step 6: 手工检查诊断输出结构但不打印 `.env`**

Run:

```powershell
& .\.venv\Scripts\python.exe scripts\openmontage_global_cli.py profiles validate
```

Expected: 退出码 0；输出只包含 `ok`、`version`、`default_profile` 和 `errors`，不包含任何密钥名和值。

- [ ] **Step 7: 提交 CLI 诊断能力**

Run:

```powershell
git diff --check
git add scripts/openmontage_global_cli.py tests/install/test_openmontage_global_cli.py
git commit -m "feat: add generation profile diagnostics"
```

Expected: 提交成功。

---

### Task 5: 安装器验证、全局更新与端到端安全回归

**Files:**
- Modify: `scripts/windows/install-openmontage-global.ps1:129-153`
- Modify: `tests/install/test_openmontage_installer_contract.py`
- Verify outside repository: `C:\Users\Aristotle\.codex\skills\openmontage\SKILL.md`
- Verify outside repository: `C:\Users\Aristotle\.local\bin\openmontage.cmd`
- Verify protected file without editing: `D:\SoftDocument\CodexProject\OpenMontage\.env`

**Interfaces:**
- Consumes: Task 4 的 `profiles validate` 子命令、现有中央 `.venv`、现有幂等 Windows 安装器。
- Produces: 安装过程在报告成功前验证档位契约；全局 Skill 更新后，任意目录与新会话都引用中央档位策略。

- [ ] **Step 1: 写入安装完成前必须验证档位的失败测试**

在 `tests/install/test_openmontage_installer_contract.py` 追加：

```python
    def test_installer_validates_profiles_before_success(self) -> None:
        text = INSTALLER.read_text(encoding="utf-8")
        validate_index = text.index('"profiles", "validate"')
        success_index = text.index('Write-Output "OpenMontage global installation complete."')
        self.assertLess(validate_index, success_index)
        self.assertIn("Failed to validate generation profiles", text)
```

- [ ] **Step 2: 运行安装器合约并确认失败**

Run:

```powershell
& .\.venv\Scripts\python.exe -m unittest tests.install.test_openmontage_installer_contract -v
```

Expected: 新测试 FAIL，原因是安装器尚无 `"profiles", "validate"`。

- [ ] **Step 3: 在安装成功输出前执行中央档位校验**

在 `scripts/windows/install-openmontage-global.ps1` 完成 `.env` ACL 设置后、成功输出前加入：

```powershell
$ProfilesCli = Join-Path $InstallRoot "scripts\openmontage_global_cli.py"
$ProfileArgs = @("profiles", "validate")
& $VenvPython $ProfilesCli @ProfileArgs
if ($LASTEXITCODE -ne 0) {
    throw "Failed to validate generation profiles"
}
```

此调用只输出档位结构与注册表契约结果，不输出 `.env` 或密钥值。

- [ ] **Step 4: 运行 PowerShell 语法、安装器合约和完整目标测试**

Run:

```powershell
$Errors = $null
[System.Management.Automation.Language.Parser]::ParseFile(
  (Resolve-Path scripts\windows\install-openmontage-global.ps1),
  [ref]$null,
  [ref]$Errors
) | Out-Null
if ($Errors.Count) { throw ($Errors | Out-String) }

& .\.venv\Scripts\python.exe -m pytest tests/lib/test_generation_profiles.py tests/contracts/test_generation_profile_routing_contract.py -v
& .\.venv\Scripts\python.exe -m unittest tests.install.test_openmontage_global_cli tests.install.test_openmontage_installer_contract -v
```

Expected: PowerShell 无解析错误；pytest 和 unittest 全部通过。

- [ ] **Step 5: 提交安装器守卫**

Run:

```powershell
git diff --check
git add scripts/windows/install-openmontage-global.ps1 tests/install/test_openmontage_installer_contract.py
git commit -m "fix: validate profiles during global install"
```

Expected: 提交成功。

- [ ] **Step 6: 幂等更新全局入口，不重装依赖或覆盖 `.env`**

Run:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\windows\install-openmontage-global.ps1 -SkipDependencies
```

Expected: 安装器先输出 `profiles validate` 的 `ok: true` 报告，再输出 `OpenMontage global installation complete.`；现有 `.env` 未被覆盖。

- [ ] **Step 7: 从仓库外目录验证全局命令和已安装 Skill**

Run:

```powershell
Push-Location $env:TEMP
try {
  & C:\Users\Aristotle\.local\bin\openmontage.cmd profiles validate
  if ($LASTEXITCODE -ne 0) { throw "global profiles validate failed" }
}
finally {
  Pop-Location
}

$InstalledSkill = Get-Content -Raw -Encoding utf8 C:\Users\Aristotle\.codex\skills\openmontage\SKILL.md
foreach ($Marker in @("generation_profiles.yaml", "skills/meta/generation-profile-routing.md", "不得静默回退")) {
  if (-not $InstalledSkill.Contains($Marker)) { throw "installed skill missing $Marker" }
}
```

Expected: 全局命令退出码 0；三个 Skill 标记均存在。

- [ ] **Step 8: 执行密钥与环境安全回归**

Run:

```powershell
git check-ignore .env
if ($LASTEXITCODE -ne 0) { throw ".env is not ignored" }

$TrackedEnv = git ls-files --error-unmatch .env 2>$null
if ($LASTEXITCODE -eq 0) { throw ".env is tracked" }

$ProviderGlobals = @(
  "OPENAI_API_KEY",
  "FAL_KEY",
  "GOOGLE_API_KEY",
  "ELEVENLABS_API_KEY"
) | Where-Object { [Environment]::GetEnvironmentVariable($_, "User") }
if ($ProviderGlobals.Count) { throw "provider keys found in user environment" }

icacls.exe .env
```

Expected: `.env` 被 Git 忽略且未跟踪；用户级环境变量中没有已知 Provider 密钥；ACL 仍只包含当前用户、Administrators 和 SYSTEM。

- [ ] **Step 9: 最终验证工作树与提交历史**

Run:

```powershell
git status --short
git log -5 --oneline
```

Expected: 工作树为空；最近提交依次覆盖档位配置、注册表契约、Agent 路由、CLI 诊断和安装器守卫。

---

## Completion Checklist

- [ ] `generation_profiles.yaml` 和 JSON Schema 通过结构与敏感信息扫描。
- [ ] 发布档位中的每个工具、Provider、能力、参数键和枚举值都与当前注册表一致。
- [ ] Agent Guide、中央路由 Skill 和全局 Skill 对解析优先级、否定词、预算和禁止静默回退表述一致。
- [ ] `openmontage profiles validate` 在仓库内外均返回成功且不输出密钥。
- [ ] 安装器幂等更新全局入口并在成功前验证档位。
- [ ] `.env` 未被修改、未被 Git 跟踪、未复制到其他项目，ACL 未放宽。
- [ ] 目标 pytest/unittest、PowerShell 解析检查和 `git diff --check` 全部通过。
