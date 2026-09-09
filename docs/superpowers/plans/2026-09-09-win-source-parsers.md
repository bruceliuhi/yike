# V02-02C 独立解析器切片 Implementation Plan

> **For agentic workers:** REQUIRED: Use `subagent-driven-development` if the current harness supports helper agents; otherwise use `executing-plans`. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将已有抖音/B站纯解析从旧 SQLite Repository 依赖中拆出，保持兼容性，交付可单独导入、测试和打包的解析包；本切片不声称真实采集或候选 API 已完成。

**Architecture:** 新建无 I/O 的 `connectors` 包，迁入已有字段类型、解析与校验函数。旧 `app` 入口只重导出同一对象，避免两套规则漂移。公共平台名称映射使用已有 R3 小写 ID；服务端 DTO/认证/上传仍等待 V02-02A ACK，不在解析层预设。

**Tech Stack:** Python 3.11/3.12、stdlib、pytest、既有 Hatch wheel 配置。

依据：用户已确认并要求持续执行的[任务板 V02-02C](../../DUAL_AGENT_TASKBOARD.md)。本次只做该卡可独立部分；实际状态仍记录在[唯一任务书](../../V02_IMPLEMENTATION_TASKBOOK.md)。不修改 Mac 在途 `pilot`、迁移或 renderer。

## Chunk 1：纯解析包与旧入口兼容

### Task 1：先证明导入隔离与兼容

**Files:** 新增 `tests/test_connector_parsers.py`；复用 `tests/fixtures/dy/comments.json`、`tests/fixtures/bili/comments.json`，这些是合成的已脱敏格式样例，不是真实平台采集证据。

- [ ] 在新测试中动态导入 `connectors` 并断言解析函数存在；缺包应产生明确的测试失败。
- [ ] 用子进程导入解析包，断言不加载 `app`、`pilot`、`sqlite3`、`psycopg`；测试不启动库/网络/采集进程。
- [ ] 对既有格式样例检查正文、ID、URL、时间、摘要与 `verifiable=False`；重复输入结果一致但本层不进行数据库去重。
- [ ] 断言旧导入与新导入是同一函数/类型/异常对象，保护既有 `isinstance` 和异常捕获。
- [ ] 运行 `./.runtime/venvs/win-dev/Scripts/python.exe -m pytest -q tests/test_connector_parsers.py`，记录预期缺实现的 RED。

### Task 2：迁入已验证的纯逻辑

**Files:** 新增 `connectors/__init__.py`、`models.py`、`normalizer.py`、`douyin.py`、`bilibili.py`；修改 `app/collectors/douyin.py`、`app/collectors/bilibili.py`、`app/normalizer.py`、`app/repository.py`、`pyproject.toml`。

- [ ] 将 `NormalizedSignal` 原样移到 `connectors/models.py`，旧 Repository 重导出它；不改变字段/默认值，不让解析结果成为已复核候选。
- [ ] 迁入两解析器与 normalizer 工具，仅改纯包导入；旧三个模块保留兼容重导出，不复制维护两套实现。
- [ ] wheel packages 增加 `connectors`，不修改正式依赖版本或 lockfile。
- [ ] 运行新测试和旧解析回归：`./.runtime/venvs/win-dev/Scripts/python.exe -m pytest -q tests/test_connector_parsers.py tests/test_d03_remediation.py -k "connector or adapters or normalize_time or bilibili"`；均须通过。

## Chunk 2：平台名称边界与打包检查

### Task 3：显式名称映射，未知输入关闭

**Files:** 新增 `connectors/platforms.py`；扩展 `tests/test_connector_parsers.py`。

- [ ] 先加反例：`canonical_platform_id("dy") == "douyin"`、`canonical_platform_id("bili") == "bilibili"`；R3的 `xhs/douyin/bilibili/zhihu/web` 原样映射；未知、非字符串、大小写/空白变体拒绝；记录 RED。
- [ ] 使用固定映射及严格字符串检查实现函数；该映射只归一名称，不代表五个平台均有适配器、已登录或可收发。解析结果保留旧内部 `dy/bili`，正式候选 DTO 映射留待02A接收。
- [ ] 增补坏ID/非规范URL/时间反例和不改变输入的验证；保留旧解析回归，不因这次拆分改变既有来源规则。
- [ ] 运行上述定向测试、`./.runtime/venvs/win-dev/Scripts/python.exe -m compileall -q connectors app`、`uv build --wheel --out-dir .runtime/parser-dist`；检查 wheel 含全部纯包文件。
- [ ] 全仓回归按当前环境实际运行和记录；已知旧日期漂移、Windows特有限制与本切片回归分开，不以定向通过冒充全仓通过。
- [ ] 绑定候选 SHA 做独立规格、架构/代码/质量审核，修复后复审；更新任务书与切片证据再正常提交 main。纯解析完成后02C仍需02A DTO接收，不能整卡提前 DONE。

## 本机基线与执行说明

基线 `022b0fbb4163f21628f70d6f3fe02b483afdcca3`，Windows x64，uv 管理的 CPython 3.11.14。既有解析回归 31 passed/42 deselected。默认 `uv run --frozen pytest` 缺少 dev extra；默认 editable `.pth` 中中文路径被 Python 3.11 site 模块按 GBK 读取而失败，UTF-8模式不能修正该读取路径。本次使用隔离的非 editable 环境，不修改机器全局设置：

```powershell
$env:UV_PROJECT_ENVIRONMENT='.runtime/venvs/win-dev'
uv sync --frozen --extra dev --no-editable
./.runtime/venvs/win-dev/Scripts/python.exe -m pytest -q tests/test_connector_parsers.py
```

`python -m pytest` 从仓库根目录运行以测试当前源码；新增包后另验 wheel。本轮小切片按当前用户工作流串行直接 main，独立子代理只在互不冲突的范围检查/验证，最终推送前重新 fetch 并核对范围。
