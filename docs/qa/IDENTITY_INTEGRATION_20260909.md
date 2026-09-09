# V02-01A/B 与测试基线组合验收

日期：2026-09-09。范围：账号登记/报告遥测、会话撤销、旧应用角色权限升级及测试时钟基线；不包含设备认证、正常客户登录、真实平台执行或生产部署。

## 最新主线集成

2026-09-09：代码在 **`5d3373d9b7fa6cb74f0a9f6241bbb282e4db2514`** 合入远端 main，`git ls-remote` 已核验。它正常整合 `222119e` 与主线 `f7e7165`；任务板和任务书冲突按最新 main 原文保留，`pilot/app/migrations/tests/desktop/deploy` 相对 `222119e` 零差异。

本机独立 reviewer `identity_integration_review` 对 `5d3373d` 复审 PASS（0 Critical / 0 Important / 0 Minor）。CodexiMac 在该 SHA 配齐两组专用 PG 管理员/应用环境变量，串行重跑 `uv run --frozen pytest -q --tb=short`：**705 passed in 48.30s，0 skipped**；compileall、JS 语法、秘密扫描与 diff 检查均通过。`desktop/` 同版本本轮重新执行 **362 passed / 37 files**，typecheck 和 build:renderer 退出 0。

代码验证/集成与接收 ACK 分开：AUTHORITY、仓库工作流及任务板第53/55/146行允许独立 Agent 审核后正常集成；实际 CodexWin 接收仍未发生，不能标为其接口依赖已就绪或 Windows 已验收。构建依赖17 high门禁与整个产品剩余工作仍保留。以下为先前候选阶段记录，保留失败与测试归属，不与最新结果相加。

## 版本与独立审核

- 代码分支：`codex/mac-identity-execution-contract`。
- 历史接收候选：[222119e0b41b86b65867a92e14d3ed00dede4e7d](https://gitee.com/xinghetech/yike-ai2026/commit/222119e0b41b86b65867a92e14d3ed00dede4e7d)。当时代码未集成 main；最新集成见上节，CodexWin 接收 ACK 仍未收到。
- 已正常合并 main `30da93e5ba39c9bc11227640b06094c7afe980b2` 的跨行业目标和 R3 成果，保留并行 UI 实现。后续 main `022b0fb` 仅变更任务卡/文档，本交接同步保留，不重写上述代码测试版本。
- 已合入 `codex/mac-baseline-test-clock` 的 `e577f4b`（测试修复候选 `475166a`）。组合审核基线 `2f0626c3f3e76e0c4bec8748c898237e2a97db9f`。
- 独立 reviewer：本机 `identity_integration_review`；修复实现者为另一 Agent `identity_grant_fix`，集成与最终串行回归为 CodexiMac。reviewer 不是实现者，也不是实际 CodexWin。
- `2f0626c`：REQUEST_CHANGES，发现 104 三张身份表遗漏显式应用权限；`222119e`：修复后独立复审 PASS，reviewer 定向复跑 22 passed。本 PASS 仅覆盖本记录范围，不批准产品发行。

## 失败复现与修复

受限制旧应用角色在迁移及原 105 权限脚本后调用 `GET /api/ui/devices` 返回 500。新增真实 PostgreSQL 升级测试先得到 `1 failed`，随后修复发布入口 `deploy/grant_session_revocations.sql`：

- devices / connections 仅 `SELECT, INSERT, UPDATE`。
- execution events / session revocations 仅 `SELECT, INSERT`。
- 授权前拒绝缺失、超级用户、BYPASSRLS、CREATEROLE 及四张表任一 owner；不授予 ALL TABLES、默认权限或 pilot_users UPDATE。
- 104/105 迁移字节未修改，不弱化租户 RLS、Origin、认证或运行时管理员隔离。
- 新反例覆盖关联任务的事件、跨租户拒绝、重复升级、撤销/断开和禁止的表权限；全部使用一次性合成身份。

修复实现者复跑身份/撤销/升级 PG 测试 `42 passed`，静态契约 `17 passed`。以上是不同定向集合，不与下面全量数相加。

## CodexiMac 最终验证

代码锁定 `222119e`。专用本机 PostgreSQL 16，测试管理员与非超级用户/NOBYPASSRLS 应用角色分离；所有租户、设备、用户和任务是合成测试对象。配置四个测试环境变量后执行，不在本文件保存凭据或完整连接串：

```sh
# 预先配置专用一次性测试库：
# YIKE_PILOT_ADMIN_DATABASE_URL / YIKE_PILOT_DATABASE_URL
# YIKE_IDENTITY_TEST_DATABASE_URL / YIKE_IDENTITY_TEST_APP_DATABASE_URL
uv run --frozen pytest -q
uv run --frozen python -m compileall -q app pilot tests
node --check static/app.js
bash scripts/secret_scan.sh
git diff --check
```

最终串行输出：`705 passed in 42.16s`，0 skipped；compileall、JS 语法检查、diff 检查均退出 0；`secret-scan: clean`。

首次全量尝试出现 `1 failed, 704 passed`：主代理与 reviewer 同时对同一一次性测试库执行 DDL/GRANT，引发 PostgreSQL `tuple concurrently updated`。双方运行结束并确认两个测试库无活动连接后，串行重跑得到上述 705 passed。未删除失败记录、未跳过测试、未改动业务代码来掩盖此问题。以后并行审核使用独立测试库，或串行执行权限升级测试。

桌面在合并后的相同 `desktop/` 代码上已复跑 `npm test`（362 passed）、`npm run typecheck` 和 `npm run build:renderer`（退出 0）。随后的 `222119e` 仅改变权限脚本、Python 测试与说明文档，不改变桌面代码；此处不是声称本次重打了 Mac/Windows 包。完整构建依赖的 17 high 仍见[单独发行风险记录](BUILD_DEPENDENCY_AUDIT_20260909.md)，不得以运行时 audit 0 放行。

## 接收及剩余边界

[Mac→Win 交接](../handoffs/V02-01_MAC_TO_WIN.md)提供锁定版本的复现步骤；接收状态仅在[实施任务书](../V02_IMPLEMENTATION_TASKBOOK.md#在途子卡与接收登记)登记。没有实际 CodexWin ACK，不把接口依赖标成已接收。

这些证据仅证明本机代码/真实数据库回归，不证明手机号登录、设备持钥授权、真实采集/发送/回复、Windows 实机、CP-06 生产部署或跨行业客户 UAT 已完成。Goal 继续 ACTIVE。
