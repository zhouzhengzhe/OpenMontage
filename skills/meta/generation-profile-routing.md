# Generation Profile Routing

在每个 OpenMontage 生产请求的 Provider 提案之前，先读取本 Skill，再运行 `openmontage profiles validate`。不得在校验前直接读取原始 `generation_profiles.yaml`。只有校验成功后，才消费安全加载产生的 `openmontage profiles` JSON 报告，并按本 Skill 解析 `daily` 或 `quality`。档位只产生候选短名单，不构成付费调用授权。

## 解析优先级

1. 显式档位：`日常模式`、`高质量模式`、`profile=daily`、`profile=quality`。
2. 用户显式 Provider、工具、模型或变体：覆盖档位候选，但仍需注册表、费用和审批检查。
3. 当前运行已批准并写入 `decision_log` 的 Provider/模型：同一运行保持粘性。
4. 明确质量意图：“高质量、精品、最终成片、质量优先、最高质量”触发 `quality`。
5. 其余请求使用 `daily`。

只分析用户对本次产物的制作意图。引用、标题或素材正文中偶然出现质量词不触发。`不要高质量模式`、`无需精品生成`、`高质量不重要` 等否定表达只抑制第 4 级质量意图自动触发，并使用 `daily`；同一句中的显式 `profile=quality` 按第 1 级优先并覆盖否定表达。

### 显式档位归一化与冲突

应用其他优先级之前，先收集同一请求中的所有显式档位别名，并按以下映射归一化：

- `日常模式`、`profile=daily` -> `daily`
- `高质量模式`、`profile=quality` -> `quality`

将归一化结果去重为集合。只要集合同时包含 `daily` 与 `quality`，无论原文使用中文、ASCII 或混合别名，档位指令都互相冲突：停止提案与执行，要求用户选择一个档位，在用户消除冲突前不得生成。多个别名归一化为同一值时不构成冲突。

| 请求中的显式档位 | 归一化结果 | 路由结果 |
|---|---|---|
| `日常模式 高质量模式` | `{daily, quality}` | 冲突：停止提案与执行，要求用户选择，冲突消除前不得生成 |
| `日常模式 profile=quality` | `{daily, quality}` | 冲突：停止提案与执行，要求用户选择，冲突消除前不得生成 |
| `profile=daily 高质量模式` | `{daily, quality}` | 冲突：停止提案与执行，要求用户选择，冲突消除前不得生成 |
| `profile=daily profile=quality` | `{daily, quality}` | 冲突：停止提案与执行，要求用户选择，冲突消除前不得生成 |
| `日常模式 profile=daily` | `{daily}` | 不冲突：继续使用 `daily` |

每个新生产运行开始时，先把档位状态重置为“未解析”，再按上述五级顺序重新解析。不得继承上一次运行的档位解析结果，也不得把上一次 `quality` 保存为全局默认。

## Provider 提案流程

1. 运行 `provider_menu_summary()`，报告实际能力。
2. 运行 `openmontage profiles validate` 或等价只读校验；失败时停止，不消费原始配置。
3. 校验成功后读取安全加载产生的 `openmontage profiles` JSON 报告，不直接消费原始 YAML。
4. 从已解析档位读取对应能力候选；档位候选的 `params` 先按目标工具 `input_schema` 做属性级校验（包括属性类型、`enum`、边界和未知属性），只保留注册表存在且候选参数契约匹配的项。
5. 披露已解析档位和候选；付费 Provider 另按既有付费披露规则说明精确工具、Provider、模型或变体、原因、样片或批量状态与预计费用。
6. 等待 Provider/模型和生产计划批准，再写入 `decision_log`，并构造包含提示词、输入资产、输出路径及所有运行参数的最终请求。
7. 最终完整生成请求在执行前再按目标工具完整 `input_schema` 校验；任何必填字段、属性或组合约束失败都停止执行并报告错误，不得调用生成工具。

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
- `$openmontage profile=daily profile=quality：制作品牌片` -> 停止并要求用户选择，不得生成
