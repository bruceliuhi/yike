# V0.2 双 AI 主线协作 Implementation Plan

> **执行定位：V0.2 协作建议，进度与编号服从 [实施任务书](../../V02_IMPLEMENTATION_TASKBOOK.md)，不构成第二套任务授权或状态台账。** 本文保留并行主线 `6f449e6` 的范围修正；实际服务端和 R3 前端从 `pilot/`、`desktop/` 继续，不能把旧 `app/` 路线作为新产品入口。前端可按既有契约独立推进，Windows 实机按用户手动执行方案验收。

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 `xinghetech/yike-ai2026/main` 上完成可安装、可试用、可验收的多平台获客产品，而不是仅完成本地演示。

**Architecture:** Mac Codex 负责身份、服务端事实库、调度、Skill、触达状态、集成和发布；Win Codex 负责适配器契约、前端/API client、Electron/sidecar 和 Windows 证据。两者只通过版本化 API/数据契约协作，所有外部发送仍需人工确认。

**Tech Stack:** 服务端 Python/FastAPI/PostgreSQL、受控平台执行器、版本化 Skill、既有 R3 前端、Electron、Windows 安装与回退测试。

## Global Constraints

- `yike-ai2026/main` 是唯一产品主线；每个任务从最新 `origin/main` 建 `codex/<主题>` 分支。
- V0.2 必须覆盖账号、客户空间、多平台采集、持续监控、Skill、复核、真实触达、回复跟进、Windows 交付和部署门禁。
- PostgreSQL 是正式客户库；SQLite 只可用于明确标记的本地实验。
- 未经人工确认不发送，不绕过验证码/限流/风控，不把凭据或私密会话写入仓库、数据库、日志或导出。
- mock、fixture、静态页面和 HTTP 200 不能证明真实平台、触达、回复、UAT 或商业成功。

---

### Task 1: `SYNC-01` 权威与主线对齐

**Files:** `AUTHORITY.md`、`docs/`、任务板。

- [ ] Fetch 最新 `origin/main`，记录 base SHA。
- [ ] 对照 `AUTHORITY.md`、`V02_COMMERCIAL_RELEASE_PLAN.md`、`V02_IMPLEMENTATION_TASKBOOK.md` 和旧 Discovery 文档，写出选择性迁移清单。
- [ ] 运行 `git diff --check` 和 secret scan；由 Win Codex 复核。
- [ ] 提交后才允许启动 V02-01/V02-02-WIN。

### Task 2: Mac 后端主链（`V02-01`～`V02-04`）

**Files:** `pilot/`、`migrations/`、`tests/`；旧 `app/` 仅作为经评估的复用来源，不建立第二套客户事实库。

- [ ] 先写身份串租户、整包事务、执行代次、坏模型输出、跨 run 绑定和未确认发送的失败测试。
- [ ] 实现最小闭环：认证/设备/连接 -> 候选 API -> 调度 -> Skill 评分 -> 人工复核。
- [ ] 每个子任务独立 commit，交 Win Codex 复核；修复后复审。
- [ ] 通过 pytest、compileall、数据库迁移和 secret scan 后再联调依赖这些新 API 的 UI/触达路径；已授权前端可以按现有契约独立推进。

### Task 3: Win 适配与客户端（`V02-02-WIN`、`V02-05`、`V02-09`）

**Files:** `desktop/`、`pilot/` 的版本化接口及 `tests/`；旧 `app/adapters/` 仅作适配器复用来源，R3 页面继续在 `desktop/src/renderer/` 实现。

- [ ] 只依赖 Mac 发布的接口契约，不直连数据库或管理员 CLI。
- [ ] 先完成适配器/解析器契约测试，再接入 R3 页面和 API client。
- [ ] 在真实 Windows 新机验证安装、登录、sidecar 取消/恢复、休眠/唤醒、更新/回退和凭据隔离。
- [ ] Mac Codex 对每个 PR 做独立复核并检查证据边界。

### Task 4: 触达、回复与跟进（`V02-06`～`V02-08`）

**Files:** `pilot/`、`desktop/src/renderer/`、`tests/` 及 `desktop/tests/`。

- [ ] 先验证首发通道可联系性和主体映射，再实现草稿版本、确认快照、幂等队列和未知结果对账。
- [ ] 真实发送前必须人工确认；回复事件与人工登记分开记录。
- [ ] Win Codex 复核 Mac 的触达状态机，Mac 复核 Win 的跟进工作台。

### Task 5: M3 集成、部署与客户 UAT（`V02-10`）

**Files:** `deploy/`、`scripts/`、`docs/`、`tests/`。

- [ ] 验证私网 PostgreSQL、非超级用户、RLS/ACL、HTTPS、备份恢复、回滚和部署 SHA。
- [ ] 逐平台保存真实运行与来源证据；真实账号/扫码/通道缺失只标 `BLOCKED_INPUT`。
- [ ] 锁定发布提交，Win Codex 做最终质量复核；Mac 才能合并 `main`。
- [ ] 至少 3 家客户完成 7–14 天试用并记录实付、使用、有效回复和续费意向；技术完成不等于商业成功。
