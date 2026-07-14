# OpenMontage 全局按需安装设计

## 目标

在 Windows 11 上将 OpenMontage 安装为一个中央、隔离、可维护的运行环境，并让任意项目目录及新的 Codex 会话都能按需调用。普通开发会话不得自动加载 OpenMontage 的大量代理指令，API 密钥不得写入 Windows 用户级环境变量。

## 成功标准

- 在任意工作目录执行 `openmontage doctor` 都能检查中央运行环境。
- `openmontage preflight` 能报告实际可用能力，但不显示任何密钥值。
- `openmontage backlot` 能打开中央 `projects` 项目库。
- 新 Codex 会话能通过 `$openmontage` 或明确的自然语言请求按需触发全局 Skill。
- 未触发 Skill 的普通会话不读取 OpenMontage 的流水线和制作指令。
- Python 合约测试、Node 依赖审计和零密钥渲染验证通过。

## 非目标

- 不把全部 OpenMontage Skill 或 Markdown 指令复制到全局 Codex 技能目录。
- 不把 OpenMontage 依赖安装到系统 Python 或其他项目的 Python 环境。
- 不在 Windows 用户级环境变量中保存 Provider API 密钥。
- 不安装本地 GPU 视频生成依赖；当前 Intel Arc 显存约 2 GB，不满足项目所列本地视频模型要求。
- 不让启动器绕过 OpenMontage 的人工审批、费用确认或流水线检查点。

## 选定方案

采用“中央隔离安装 + 全局 Codex Skill + 全局命令入口”。

中央仓库继续位于：

```text
D:\SoftDocument\CodexProject\OpenMontage
```

Python 依赖安装到仓库内的 `.venv`，Remotion 依赖安装到 `remotion-composer\node_modules`。全局只安装一个轻量级 Codex 路由 Skill 和一个启动命令，不复制 OpenMontage 的完整知识库。

## 组件设计

### 中央运行环境

- `OPENMONTAGE_HOME` 指向中央仓库。
- Python 使用中央 `.venv\Scripts\python.exe`。
- Remotion 使用中央 `remotion-composer\node_modules`。
- 项目状态、资产和视频统一保存在中央 `projects` 目录。
- 外部项目素材通过绝对路径传入；仅在流水线需要时复制到中央项目工作区。

### 全局命令入口

在当前用户的命令目录中提供 `openmontage.cmd`，并将该命令目录加入用户级 `PATH`。启动器负责：

1. 验证 `OPENMONTAGE_HOME`、中央仓库和 `.venv` 是否存在。
2. 切换到中央仓库，确保仓库内相对路径、Skill、YAML 和渲染资产可被正确解析。
3. 将子命令映射到中央 Python 环境。
4. 返回原始退出码并输出不包含密钥的诊断信息。

首批子命令：

- `openmontage doctor`：检查 Python、Node、npm、FFmpeg、Remotion、HyperFrames 和项目路径。
- `openmontage preflight`：调用 Provider 菜单摘要，显示可用与不可用能力。
- `openmontage backlot [project-id]`：打开中央项目库或指定项目。
- `openmontage test-contracts`：运行无需 API 密钥的合约测试。
- `openmontage demo`：运行零密钥演示渲染。

未知子命令必须返回非零退出码和简短帮助，不得把输入拼接到任意 Shell 命令。

### 全局 Codex Skill

全局 Skill 位于：

```text
C:\Users\Aristotle\.codex\skills\openmontage\SKILL.md
```

该 Skill 只承担路由职责：

- 仅在 `$openmontage` 或用户明确要求使用 OpenMontage 时触发。
- 定位 `OPENMONTAGE_HOME`。
- 要求代理先读取中央 `AGENT_GUIDE.md` 和 `PROJECT_CONTEXT.md`。
- 要求所有 OpenMontage Python 命令使用中央 `.venv`，所有制作产物使用中央 `projects`。
- 保留 Provider、预算、渲染运行时和人工审批规则。
- 禁止把 OpenMontage 全量指令预加载到普通任务。

## 密钥与环境配置

API 密钥只保存在：

```text
D:\SoftDocument\CodexProject\OpenMontage\.env
```

安装程序只在 `.env` 不存在时从 `.env.example` 创建空白文件，绝不覆盖已有 `.env`。文件继续受 `.gitignore` 保护，并限制为当前用户、Administrators 和 SYSTEM 可访问。

用户级环境变量只允许保存非敏感值：

- `OPENMONTAGE_HOME=D:\SoftDocument\CodexProject\OpenMontage`
- `OPENMONTAGE_PROJECTS_DIR=D:\SoftDocument\CodexProject\OpenMontage\projects`
- 用户级 `PATH` 增加 OpenMontage 启动器所在目录。

诊断、日志、错误信息和测试输出不得打印 `.env` 内容或密钥值。缺少密钥时，对应 Provider 只标记为不可用。

## 依赖策略

- 使用当前 Python 3.14 创建隔离 `.venv`；核心依赖和 Piper 已完成解析检查。
- 安装 `requirements.txt` 与 `piper-tts`。
- Remotion 使用 `npm.cmd ci`，依据现有 `package-lock.json` 安装。
- HyperFrames 安装前查询具体版本并记录；只安装经过本次检查的固定版本，不使用无版本约束的持续最新版作为全局运行时。
- 不安装 `requirements-gpu.txt`。
- 初始运行版本固定在已审查提交 `f8d94632ea9bd0057da31904acca1cefecf005dd`。后续更新必须显式执行并重新验证。

## 调用和数据流

```text
用户在任意项目触发 $openmontage
  -> 全局 Skill 读取中央入口与代理合同
  -> 全局启动器调用中央 .venv
  -> 中央 .env 在 OpenMontage 进程内加载
  -> 流水线读取外部素材绝对路径
  -> 检查点、资产和成片写入中央 projects
  -> Backlot 展示中央项目历史
```

密钥只进入 OpenMontage 进程及被明确选择的 Provider 请求。不得因为缺少某个 Provider 而静默切换到其他付费 Provider。

## 错误处理

- 中央仓库、虚拟环境或必要运行时缺失时立即失败，并给出具体修复命令。
- Provider 密钥缺失时继续报告其余能力，不视为安装失败。
- 已批准的渲染运行时不可用时停止，不静默切换。
- 安装操作必须可重复执行，且不得删除已有 `.env`、`.venv`、`projects` 或用户素材。
- Node 或 Python 安装失败时保留完整退出码，不把部分安装报告为成功。
- PowerShell 执行策略可能拦截 `npm.ps1`，Windows 命令统一使用 `npm.cmd` 和 `npx.cmd`。

## 验证方案

### 安装验证

- 核对 Python、Node、npm、FFmpeg 和中央路径。
- 从仓库外目录运行 `openmontage doctor`。
- 运行 `openmontage preflight` 并确认输出中没有密钥。
- 运行 Python 合约测试。
- 运行 `npm.cmd audit --package-lock-only --omit=dev`。
- 运行零密钥演示并用 FFprobe 验证成片。

### 全局调用验证

- 在新的 Codex 会话中确认 `$openmontage` 可被发现。
- 在普通非视频任务中确认 Skill 不会自动触发。
- 从另一个项目传入一个测试素材绝对路径，确认产物仍进入中央 `projects`。

### 安全验证

- 检查用户级环境变量中不存在已知 Provider 密钥名称。
- 检查 `.env` 未被 Git 跟踪。
- 检查 `.env` ACL 只保留当前用户、Administrators 和 SYSTEM。
- 对启动器输出执行密钥值扫描，结果必须为空。

## 更新与卸载

更新时先获取上游变更并审查目标提交，再更新 Python、Node 和 HyperFrames 固定版本，最后重新执行完整验证。更新失败时保留旧环境，不覆盖 `.env` 和 `projects`。

卸载全局入口时只删除：

- 全局 `openmontage` Skill。
- 全局启动器。
- `OPENMONTAGE_HOME`、`OPENMONTAGE_PROJECTS_DIR` 和对应用户级 `PATH` 项。

中央仓库、`.env`、`.venv` 和 `projects` 默认保留，除非用户另行明确要求删除。
