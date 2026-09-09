# 双 AI 主线协作 Implementation Plan

> **范围：旧 DISCOVERY MVP 参考计划，非当前执行授权。** 2026-09-09 整合保留来源 `554c1ed`、`e7c94a9`。下文旧 SQLite/双平台限制与固定 SHA 不覆盖已授权的多平台、PostgreSQL、R3 页面及客户端目标；接续工作须转至 [V0.2 实施任务书](../../V02_IMPLEMENTATION_TASKBOOK.md)和[仓库工作流](../../REPOSITORY_WORKFLOW.md)。本计划中的步骤与技能调用是历史内容，不应自动启动。

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 `yike-ai2026/main` 上用 Mac Codex 主集成、Win Codex 独立模块和双向复核，完成当前 B 站＋抖音 DISCOVERY MVP。

**Architecture:** 保留当前权威的本地 MVP 边界。Mac 负责事实库、评分工作流、指标和合并；Win 通过稳定接口负责适配器、前端/API client 与 Windows 可移植性验证。所有外部平台操作仍由人工在环完成。

**Tech Stack:** Python 3.11、uv、FastAPI、SQLite、Jinja2、原生 JavaScript、固定版本 MediaCrawler、pytest、Node syntax check。

## Global Constraints

- 主仓固定为 `xinghetech/yike-ai2026`，主分支固定为 `main`；任务开始前必须以最新 `origin/main` 作为 base，初始基线为 `0e20ffb`。
- 当前范围固定为 B 站＋抖音 DISCOVERY MVP；不恢复冻结的云端、多租户、自动外联或其他平台。
- 不使用 mock/fixture 证明真实采集、联系、回复或商业成功。
- 所有外部发送必须人工批准；不绕过验证码、限流或平台风控。
- Secret、Cookie、Token、Profile、二维码不得进入 Git、SQLite、日志或导出。
- 每项任务必须有独立 commit、测试命令、证据路径和非实现者 reviewer PASS。

---

### Task 1: 建立双 AI 协作基线

**Files:**
- Modify: `docs/DUAL_AGENT_TASKBOARD.md`
- Modify: `AUTHORITY.md`（仅在发现主线指针不一致时）
- Test: `git status --short --branch`、`git diff --check`

**Interfaces:**
- Produces: 所有后续任务使用 `main@0e20ffb` 作为 base，并按任务板记录 owner、branch、reviewer 和证据。

- [ ] **Step 1: Fetch and record baseline**

```bash
git fetch origin
git rev-parse origin/main
```

Expected: `0e20ffb0c6ea5b1f3aa6293ee0495692eb8fd513`。

- [ ] **Step 2: Verify authority boundary**

```bash
rg -n "B站|抖音|DISCOVERY_MVP|自动发送|yike-ai2026" AUTHORITY.md docs
```

Expected: 当前范围和人工在环约束无矛盾。

- [ ] **Step 3: Commit taskboard**

```bash
git add docs/DUAL_AGENT_TASKBOARD.md docs/superpowers/plans/2026-09-09-dual-agent-mainline-development.md
git commit -m "docs: add dual-agent mainline taskboard"
```

### Task 2: Mac 实现评分、复核与业务事实链

**Files:**
- Modify: `app/`、`migrations/`
- Test: `tests/`

**Interfaces:**
- Consumes: 现有 `Signal`、`mvp_run_id` 和采集适配器输出。
- Produces: 严格评分、人工复核、草稿、人工联系、回复/访谈/报价的同 run 因果链。

- [ ] **Step 1:** 先写坏模型输出、跨 run 外键、重复主体和未批准发送的失败测试。
- [ ] **Step 2:** 运行定向 pytest，确认测试在实现前失败。
- [ ] **Step 3:** 实现最小闭环并保持只追加事实。
- [ ] **Step 4:** 运行定向测试和完整门禁。
- [ ] **Step 5:** 提交后交 Win Codex 复核，修复并保留复审记录。

### Task 3: Win 实现适配器与契约测试

**Files:**
- Modify: `app/adapters/`、`tests/adapters/`

**Interfaces:**
- Consumes: 公开的 collector output contract。
- Produces: B站/抖音标准化、URL/时间/作者处理和身份冲突失败关闭。

- [ ] **Step 1:** 写每个平台输入、缺失 ID、冲突正文和可重开 URL 的失败测试。
- [ ] **Step 2:** 运行定向测试确认 RED。
- [ ] **Step 3:** 实现适配器，不访问数据库管理接口。
- [ ] **Step 4:** 运行 adapter tests、compileall、secret scan。
- [ ] **Step 5:** 提交 PR，由 Mac Codex 复核并记录证据路径。

### Task 4: Mac/Win 并行完成 UI、指标与集成门禁

**Files:**
- Win: `static/`、`app/web/`、`tests/web/`
- Mac: `app/metrics/`、`app/exporter/`、`scripts/`、`docs/RUNBOOK.md`

**Interfaces:**
- Consumes: Task 2/3 的稳定 API、事实表和适配器接口。
- Produces: 五页空库主流程、三层指标、脱敏 CSV、最终门禁和真实输入阻塞记录。

- [ ] **Step 1:** 双方先 rebase/fetch `origin/main`，不得互相覆盖正在修改的目录。
- [ ] **Step 2:** 各自执行 RED/GREEN 和独立测试。
- [ ] **Step 3:** 互相 review；Mac 审 Win UI，Win 审 Mac metrics/integration。
- [ ] **Step 4:** 修复后复审，运行完整门禁。
- [ ] **Step 5:** Mac 仅在所有 PASS 后合并到 `main`。

### Task 5: 发布与持续同步

**Files:**
- Modify: `docs/DUAL_AGENT_TASKBOARD.md`、发布清单

- [ ] **Step 1:** 每次合并记录 merge commit、测试摘要、证据路径和回滚点。
- [ ] **Step 2:** Win 每次同步使用 `git fetch origin` 和新分支，不在 Mac 工作树改写历史。
- [ ] **Step 3:** 每周由双方交叉抽查一个已合并任务；发现证据越界立即回滚或标记阻塞。
