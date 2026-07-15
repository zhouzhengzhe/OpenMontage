# Generation Profiles 最终审查修复报告

日期：2026-07-15
工作树：`D:\SoftDocument\CodexProject\OpenMontage\.worktrees\generation-profiles`

## 结论

最终审查列出的默认不变量、敏感信息扫描、安全读取顺序、稳定诊断 JSON 与 CLI 端到端问题均已修复。Python 仍只负责配置加载、校验和诊断，没有加入 NLP 路由或 Agent 决策逻辑。

## 修复明细

### 1. 默认不变量

- `schemas/config/generation_profiles.schema.json` 将 `default_profile` 从 `daily/quality` 枚举收紧为 `const: daily`。
- 发布配置继续使用 `default_profile: daily`。
- 新增复制发布配置并改为 `quality` 的负测，确认加载器以安全的 `schema validation failed` 拒绝。

### 2. 敏感扫描与安全读取顺序

- 递归扫描覆盖嵌套 `params`，拒绝 token、credential、private-key、client-secret、access-key、header、cookie、authorization 等敏感键，包括常见驼峰形式。
- 值扫描覆盖凭据环境变量名、`.env`/credentials/service-account/private-key/PEM/key 路径、Authorization/Cookie 载荷、`sk-`、`sk_`、`sk-ant`、`gsk_`、`xai-`、`ghp_`、`AKIA`、JWT 与 PEM private key。
- 敏感扫描错误只报告安全位置和类别，不回显原值。
- 安全嵌套候选继续通过，未发现新增扫描规则对发布配置或安全测试候选产生误报。
- `AGENT_GUIDE.md`、中央路由 Skill 与全局 Skill 现在统一要求：先读路由 Skill，运行 `openmontage profiles validate`；成功后只消费安全加载产生的 `openmontage profiles` JSON 报告；不得在校验前直接读取原始 YAML。
- 新增三处读取顺序合约测试，固定 validate 必须先于 profiles 报告。

### 3. 稳定诊断 JSON

- 主 Schema 在实例校验前执行 `check_schema`；`SchemaError` 被包装为 `GenerationProfileError`，不透传 Schema 内容。
- 配置/YAML/Schema 读取和解析失败使用固定安全类别，不透传底层异常文本。
- Schema 实例错误只报告 JSON 位置和 validator 类别，不回显失败值。
- 注册表 discovery 异常转换为稳定类型诊断。
- `tool.input_schema` 非对象、`properties` 非对象、属性 Schema 无效时返回候选 location 下的稳定错误，不产生 traceback，也不把 SchemaError 吞成成功。
- 参数 enum/Schema 错误不再回显候选值或注册表 Schema 值。
- CLI 顶层将未预期诊断异常转换为 `{"ok": false, "errors": [...]}` 与退出码 1；通用异常只报告异常类型。

### 4. CLI 端到端

- CLI 的 Python 导入固定来自脚本所在中央仓库 `CODE_ROOT`；`OPENMONTAGE_HOME` 仅决定配置 home。
- 新增真实 subprocess `profiles` 展示测试：验证 daily、quality、status，且不输出环境 sentinel 或常见敏感标记。
- 新增临时 home 非法 YAML 测试：退出码 1、stdout 为安全 JSON、无 traceback、无敏感原值。
- 新增 CLI 顶层通用异常安全 JSON 测试。
- launcher 的默认 home、命令分发和实际启动方式保持不变。

## TDD 证据

### RED

首次仅添加最终审查回归测试后：

- `pytest tests/lib/test_generation_profiles.py tests/contracts/test_generation_profile_routing_contract.py -q`
  - 31 failed，34 passed。
  - 预期失败覆盖：非 daily 默认仍被接受、敏感键/值漏检、主 SchemaError 未包装、registry discovery/工具 Schema traceback、三处读取顺序缺失。
- `python -m unittest tests.install.test_openmontage_global_cli -v`
  - 1 error，8 passed。
  - 临时 home 非法配置未产生可解析的安全 JSON。
- 增补驼峰敏感键边界后：目标用例 1 failed，1 passed；`authToken` 未被旧规则拒绝。

### GREEN

- 档位单测与路由合约：68 passed。
- CLI 与安装器 unittest：19 passed。
- 全量 `PYTHONUTF8=1` 的 `tests/lib tests/contracts`：637 passed，7 skipped，1 warning。
- PowerShell parser：通过。
- `git diff --check`：通过。

## 回归命令

```powershell
$env:PYTHONUTF8='1'
& .\.venv\Scripts\python.exe -m pytest tests/lib/test_generation_profiles.py tests/contracts/test_generation_profile_routing_contract.py -q
& .\.venv\Scripts\python.exe -m unittest tests.install.test_openmontage_global_cli tests.install.test_openmontage_installer_contract -v
& .\.venv\Scripts\python.exe -m pytest tests/lib tests/contracts -q

$Errors = $null
[System.Management.Automation.Language.Parser]::ParseFile(
  (Resolve-Path scripts\windows\install-openmontage-global.ps1),
  [ref]$null,
  [ref]$Errors
) | Out-Null
if ($Errors.Count) { throw ($Errors | Out-String) }

git diff --check
```

## 安全与范围确认

- 未读取、修改或打印真实 `.env`。
- 未调用任何生成 API。
- 未运行安装器本体。
- 安装器真实失败路径按要求留待合并后的隔离验证。
- 全量测试曾改写已跟踪 `diagram.png`；已确认测试前无该变更，并恢复到原提交对象哈希，未纳入修复提交。

## 关注点

- 全量测试唯一 warning 来自 `google.genai.types` 对 Python 3.17 将移除内部类型的第三方 `DeprecationWarning`，与本次改动无关。
- 真实安装器失败路径尚未执行，需在合并后按隔离验证计划完成。
