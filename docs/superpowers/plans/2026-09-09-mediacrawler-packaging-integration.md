# MediaCrawler 打包集成 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将已获授权的固定版本 MediaCrawler 变成意客 AI 可复现的仓内采集依赖，并保持现有证据链与人工在环边界。

**Architecture:** MediaCrawler 作为 vendor runtime，collector supervisor 负责锁定版本、应用补丁和启动隔离进程；意客 adapter 负责 JSONL 标准化、去重和 SQLite 事实写入。账号 Profile 和原始恢复文件继续放在仓外私有目录。

**Tech Stack:** Python 3.11/uv、MediaCrawler、Playwright、SQLite、FastAPI、pytest、Bash。

## Global Constraints

- 仅适用当前授权 B 站＋抖音 Discovery MVP。
- 不自动发送、不绕过验证码、限流或平台风控。
- Cookie、Token、Profile、二维码和授权原件不进 Git、SQLite、日志或导出。
- fixture 不得计入真实采集、联系、回复或商业结果。
- MediaCrawler 源码固定 commit；补丁、依赖和许可证必须可追溯。

## Task 1: Vendor runtime manifest and packaging helper

Files: `vendor/mediacrawler.lock`, `vendor/patches/mediacrawler/*`, `scripts/fetch_mediacrawler.sh`, new `scripts/package_mediacrawler.sh`, tests for lock/packaging.

- [ ] 先写失败测试：固定 commit、许可证文件、补丁摘要和目标目录校验失败时 fail closed。
- [ ] 实现仓内 vendor 打包/校验脚本，保留上游 LICENSE/NOTICE，禁止覆盖已有 runtime。
- [ ] 运行针对性测试和 shellcheck-equivalent syntax checks。
- [ ] 提交独立 commit。

## Task 2: Collector runtime resolution

Files: `app/config.py`, `app/collector.py`, `docs/RUNBOOK.md`, `.env.example`。

- [ ] 先写失败测试：默认解析仓内 vendor runtime；显式仓外路径仍可用于回滚；校验不通过时返回稳定错误码。
- [ ] 实现最小路径解析和锁摘要绑定，不改变现有 collection state machine。
- [ ] 运行 collector、CLI、secret scan 和 compile 测试。
- [ ] 提交独立 commit。

## Task 3: Documentation and authority synchronization

Files: `AUTHORITY.md`, `docs/RUNBOOK.md`, parent authority handoff if needed.

- [ ] 写明用户授权是本轮前提、授权原件不入仓、vendor commit 和回滚方式。
- [ ] 明确代码完成不等于真实平台采集和业务成功。
- [ ] 更新任务台账与锁摘要引用，检查无旧路径矛盾。
- [ ] 提交独立 commit。

## Final verification

- [ ] 运行 `uv run --frozen pytest -q tests/test_collector.py tests/test_cli.py tests/test_bootstrap.py`。
- [ ] 运行 `uv run --frozen python -m compileall -q app tests`、`node --check static/app.js`、`git diff --check`。
- [ ] 运行 secret scan 和 vendor lock 校验。
- [ ] 独立 reviewer 检查实现 commit，修复 Critical/Important findings 后再报告。
