---
name: openmontage
description: Use only when the user explicitly invokes $openmontage or clearly asks to use OpenMontage for a video-production task; do not auto-trigger for ordinary development work.
---

# OpenMontage 全局路由

仅在用户输入 `$openmontage` 或明确要求“使用 OpenMontage”时启用；不得自动触发普通开发任务。

1. 从用户环境变量 `OPENMONTAGE_HOME` 定位中央仓库；缺失时使用 `D:\SoftDocument\CodexProject\OpenMontage`。
2. 在采取任何 OpenMontage 行动前，完整读取中央 `AGENT_GUIDE.md` 与 `PROJECT_CONTEXT.md`。
3. 在每个生成 Provider 提案前，先读取中央 `skills/meta/generation-profile-routing.md`，再运行 `openmontage profiles validate`；不得在校验前直接读取原始 `generation_profiles.yaml`。校验成功后只消费安全加载产生的 `openmontage profiles` JSON 报告，解析并披露 `daily` 或 `quality`。
4. 使用全局 `openmontage` 命令做 `doctor`、`preflight` 与 `profiles validate`；Python 命令只允许使用中央 `.venv`。
5. 所有检查点、资产和成片写入 `OPENMONTAGE_PROJECTS_DIR` 指向的中央 `projects`。
6. API 密钥只从中央 `.env` 加载；不得打印；不得复制到用户环境变量；不得写入其他项目。
7. 所有视频制作继续遵守流水线、Provider 披露、费用确认、渲染运行时选择与人工审批规则；档位候选不得静默回退。
8. 外部项目素材使用绝对路径传入；不得修改来源项目，除非用户明确要求。
