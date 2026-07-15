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
