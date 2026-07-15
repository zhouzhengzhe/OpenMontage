# OpenMontage 全局生成档位设计

## 目标

为全局 OpenMontage 增加两个可审计的云端生成档位：

- `daily`：默认档，优先控制费用、延迟和日常迭代效率。
- `quality`：精品档，优先最终质量，允许选择更昂贵的模型和参数。

用户不需要修改 `.env`、复制 API 密钥或重新启动项目。档位由每次生产请求的语义或显式指令决定，并在所有项目目录和新的 Codex 会话中保持一致。

## 成功标准

- `$openmontage` 在任意项目和新会话中均能读取同一份中央档位策略。
- 未指定档位的生产请求默认使用 `daily`。
- “高质量、精品、最终成片、质量优先”等明确质量意图触发 `quality`。
- `日常模式`、`高质量模式`、`profile=daily` 和 `profile=quality` 可以显式覆盖自动判断。
- API 密钥继续只从中央 `.env` 加载，档位文件、日志、测试输出和 Git 中不出现密钥值。
- 每次付费生成前仍披露工具、Provider、模型或变体、原因、样片或批量状态以及预计费用。
- 档位不绕过 Provider 可用性检查、预算阈值、流水线阶段或人工审批。
- 已批准的 Provider 或模型不可因档位或故障被静默替换。

## 非目标

- 不创建两份 `.env`，也不在档位之间复制或启停密钥。
- 不把 Provider 选择、创意判断或流水线编排写进 Python。
- 不把某个模型的当前可用性视为永久事实；工具注册表仍是运行时真相源。
- 不允许 `quality` 档自动获得无限预算、跳过样片或跳过人工确认。
- 不改变 `$openmontage` 的按需触发边界；普通开发任务不会加载 OpenMontage。

## 选定方案

采用“中央声明式档位 + Agent 指令路由 + 注册表运行时校验”。

中央仓库提供一份不含密钥的档位文件和一份路由 Skill。全局 `$openmontage` Skill 在被用户明确触发后，读取这两份中央文件。Agent 根据用户意图解析档位，运行 Provider 预检，然后把已批准的偏好传给现有 selector，或按流水线要求直接调用已批准的 Provider 工具。

Python 只承担档位文件的加载、结构校验和无密钥诊断，不承担“应该选择哪个档位或 Provider”的决策。

## 组件设计

### 中央档位文件

新增根目录文件：

```text
generation_profiles.yaml
```

该文件是非敏感配置，可进入 Git。建议结构：

```yaml
version: 1
default_profile: daily

profiles:
  daily:
    intent: balanced_cost_latency
    capabilities:
      video_generation:
        candidates: []
      image_generation:
        candidates: []
      tts:
        candidates: []
      music_generation:
        candidates: []

  quality:
    intent: maximize_output_quality
    capabilities:
      video_generation:
        candidates: []
      image_generation:
        candidates: []
      tts:
        candidates: []
      music_generation:
        candidates: []
```

每个候选项只允许包含非敏感字段：

- `tool`：注册表工具名。
- `provider`：注册表 Provider 名，用于 selector 的 `preferred_provider`。
- `params`：目标工具公开 `input_schema` 中允许的模型、质量或分辨率参数。
- `reason`：面向 Agent 和用户的简短选择依据。

禁止出现 `api_key`、`token`、`secret`、凭据环境变量名、密钥文件路径或内联请求头。

### 路由 Skill

新增：

```text
skills/meta/generation-profile-routing.md
```

该 Skill 定义档位解析、注册表校验、Provider 披露、预算保护和切换规则。它是决策说明，不执行付费调用。

全局入口 `scripts/windows/openmontage/SKILL.md` 在完成 `AGENT_GUIDE.md` 和 `PROJECT_CONTEXT.md` 的读取后，再读取中央档位文件与路由 Skill。安装程序继续只复制轻量全局 Skill；档位策略始终从 `OPENMONTAGE_HOME` 指向的中央仓库读取，因此其他项目和新会话不会持有策略副本。

### 校验与诊断

增加只读诊断命令：

```text
openmontage profiles
openmontage profiles validate
```

- `profiles` 仅显示默认档、候选工具、模型参数和当前注册表可用状态。
- `profiles validate` 检查 YAML 结构、工具名、Provider 名以及 `params` 是否属于目标工具的 `input_schema`。
- 两个命令都不得打印 `.env` 内容、密钥值或请求认证头。
- 工具或模型契约发生变化时校验应失败并指出具体候选项，不得静默改写档位文件。

## 档位解析规则

解析优先级从高到低如下：

1. 用户显式指定 `日常模式`、`高质量模式`、`profile=daily` 或 `profile=quality`。
2. 用户显式指定具体 Provider、工具、模型或变体；该选择覆盖档位候选，但仍需通过注册表和预算检查。
3. 当前生产运行中已经由用户批准并写入 `decision_log` 的 Provider/模型决定；同一运行内保持粘性。
4. 明确的高质量意图触发 `quality`，例如“高质量、精品、最终成片、质量优先、最高质量”。
5. 其余情况使用 `daily`。

自动触发只分析用户对本次产物的制作意图。引用文本、素材标题或主题中偶然出现“高质量”不构成触发。否定表达如“不要高质量模式”“无需精品生成”“高质量不重要”抑制自动触发并回到 `daily`，但不覆盖用户同一句中的显式 `profile=quality`。

每个新生产运行重新从 `daily` 开始解析，不把上一次运行的 `quality` 状态保存为全局默认。

## 初始候选策略

下列候选名已经在当前工具注册表中发现。实际执行时仍必须按注册表状态过滤，并核对目标工具的实时 `input_schema`。

### `daily`

| 能力 | 首选 | 后备候选 | 初始参数意图 |
|---|---|---|---|
| 视频 | `gemini_omni_video` | `kling_official_video`、`grok_video` | Gemini 使用工具默认模型；Kling 使用 `kling-v3`、`std`、`720p`；Grok 使用 `720p` |
| 图片 | `google_imagen` | `dashscope_image`、`grok_image` | Imagen 使用 `imagen-4.0-fast-generate-001`；后备模型在调用前披露 |
| 配音 | `dashscope_tts` | `google_tts` | `qwen3-tts-flash` |
| 音乐 | `google_music` | `music_gen` | `lyria-3-pro-preview`，时长匹配成片 |

### `quality`

| 能力 | 首选 | 后备候选 | 初始参数意图 |
|---|---|---|---|
| 视频 | `seedance_video` | `kling_official_video`、`veo_video` | Seedance 2.0 `standard`、`720p`；Kling `kling-v3`、`pro`；Veo 3.1；1080p 或更高分辨率需结合费用单独确认 |
| 图片 | `openai_image` | `dashscope_image`、`google_imagen` | `gpt-image-2` + `high`；Qwen `qwen-image-2.0-pro`；Imagen `imagen-4.0-ultra-generate-001` |
| 配音 | `elevenlabs_tts` | `dashscope_tts` | `eleven_multilingual_v2`；后备使用 Qwen 指令或 Flash 路径 |
| 音乐 | `music_gen` | `google_music` | ElevenLabs Music；后备 `lyria-3-pro-preview` |

候选顺序不是静默回退授权。它只是在首选不可用时形成待批准的短名单。若首选在预检、认证、额度、模型访问或执行阶段失败，Agent 必须说明失败类型、列出实际可用后备并等待用户批准。

## 执行流程

```text
用户在任意项目触发 $openmontage
  -> 全局 Skill 定位中央仓库
  -> 读取 AGENT_GUIDE、PROJECT_CONTEXT 和档位路由 Skill
  -> 解析 daily / quality
  -> 运行 Provider 菜单预检
  -> 过滤不可用候选并验证模型参数
  -> 在提案中披露档位、工具、Provider、模型、费用和后备短名单
  -> 用户批准 Provider/模型与生产计划
  -> 写入 decision_log
  -> 按流水线阶段执行并遵守各人工检查点
```

档位解析发生在 Provider 提案之前，不构成对任何付费调用的预先批准。

## Selector 集成边界

- `video_selector`、`image_selector` 和 `tts_selector` 继续由注册表自动发现 Provider。
- 档位路由把已确认的候选转换成 selector 已支持的 `preferred_provider`、`allowed_providers` 和 Provider 参数。
- `video_selector` 现有的评分差距保护继续生效；若首选明显不适合任务，应在提案阶段解释评分差异并由用户决定，而不是强制生成。
- 音乐目前没有统一 selector，由 Agent 根据注册表和已批准档位直接选择 `google_music` 或 `music_gen`。
- 档位配置不得维护完整工具清单，只维护少量有意图的优先候选；所有可用工具和替代方案仍由注册表发现。

## 预算与审批

- `budget.single_action_approval_usd` 继续适用于两个档位。
- `quality` 不修改 `budget.total_usd`，也不自动提高单次费用阈值。
- 每次付费调用前必须给出当前档位、精确工具、Provider、模型/变体、预计费用、选择原因以及样片或批量状态。
- 首次进入批量生成前仍应先做低数量样片，除非流水线和用户已明确批准其他策略。
- 同一流水线中途从 `daily` 切到 `quality`，或反向切换，属于重大 Provider/模型决策变更：必须先请求批准，并使用相同的 `category` 与 `subject` 追加修订后的 `decision_log` 条目。

## 密钥安全

所有 Provider 密钥继续只保存在：

```text
D:\SoftDocument\CodexProject\OpenMontage\.env
```

档位不会直接选择、复制或展示密钥。工具只有在被用户批准并执行时，才由中央 OpenMontage 进程读取对应 Provider 的环境配置。

安全校验包括：

- `generation_profiles.yaml` 不含敏感字段和值。
- `.env` 继续被 Git 忽略并维持受限 ACL。
- 全局 Skill 和启动器不复制 `.env` 到其他项目或用户环境变量。
- `profiles`、`profiles validate`、测试和错误输出使用状态信息，不输出凭据。
- 即使日志中出现 Provider 请求失败，也必须清理认证头、查询参数和密钥形态字符串。

## 错误处理

- 档位文件缺失或无效：停止 Provider 选择，报告配置错误并建议运行 `openmontage profiles validate`。
- 档位中的工具已从注册表移除：校验失败，指出工具名，不自动改用同类别第一个工具。
- 模型参数不再被目标工具接受：校验失败并要求更新配置，不依赖陈旧模型名继续执行。
- 首选未配置或认证失败：报告能力状态和失败类别，列出已配置候选，等待用户批准。
- 生成失败：遵守 OpenMontage blocker 格式，不将后备顺序视为自动执行许可。
- 档位解析存在歧义：默认 `daily`，并在提案中说明解析结果；不会因为模糊的“效果好一点”自动进入高费用档。

## 测试策略

### 配置合约

- 两个档位均存在且默认档为 `daily`。
- 四类能力的候选结构符合 schema。
- 所有候选工具和 Provider 可在注册表中找到。
- 所有 `params` 键及枚举值符合目标工具的 `input_schema`。
- 配置不含敏感字段、凭据值或密钥文件引用。

### 路由合约

- 无触发词返回 `daily`。
- 明确质量词返回 `quality`。
- 否定质量词返回 `daily`。
- 显式档位覆盖自动触发。
- 用户显式 Provider/模型优先于档位候选。
- 同一运行已批准决定保持粘性，变更必须要求批准并追加决策日志。

路由合约以 Skill 文本和固定测试用例验证，不在 Python 中实现自然语言意图分类器。

### 全局安装合约

- 安装后的全局 Skill 明确读取中央档位路由文件。
- 从仓库外目录运行 `openmontage profiles validate` 成功。
- 在新的 Codex 会话中，普通 `$openmontage` 请求默认 `daily`，明确高质量请求解析为 `quality`。
- 重复运行安装程序不会覆盖 `.env`，也不会产生档位策略副本。

### 安全回归

- 对诊断输出、测试输出和全局安装产物运行密钥形态扫描，结果必须为空。
- 确认 `.env` 未被 Git 跟踪，ACL 未放宽。
- 档位切换前后用户级环境变量中不新增 Provider 密钥。

## 预期变更范围

实施阶段预计新增或修改：

- 新增 `generation_profiles.yaml`。
- 新增 `schemas/config/generation_profiles.schema.json`。
- 新增 `skills/meta/generation-profile-routing.md`。
- 修改 `scripts/windows/openmontage/SKILL.md`。
- 扩展 `scripts/openmontage_global_cli.py` 的只读档位诊断命令。
- 扩展安装与档位合约测试。
- 按需要更新 `AGENT_GUIDE.md` 或 `PROJECT_CONTEXT.md` 的路由说明。

不修改 Provider 工具的密钥加载方式，不增加第二份 `.env`，也不把档位判断写入 selector 或流水线 Python 代码。
