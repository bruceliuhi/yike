# SYNC-01 主线与权威对齐记录

日期：2026-09-09
仓库：`xinghetech/yike-ai2026`
基线：`15ddb7039e385c9adbda04bfd553bf8d222e6308`

## 结论

本实现仓后续产品代码统一以 `AUTHORITY.md`、`docs/V02_COMMERCIAL_RELEASE_PLAN.md` 和 `docs/V02_IMPLEMENTATION_TASKBOOK.md` 为执行入口，目标是 V0.2 完整获客版。主线只接受从最新 `origin/main` 创建的 `codex/<主题>` 分支，并由 Mac Codex 集成回 `main`。

父目录 `/Users/xingheimac/Developer/Work/意客AI` 仍保留旧 DISCOVERY MVP 文档用于溯源；本次不改写、不删除、不把旧双平台分支整支合并。旧实现只允许按 V0.2 契约选择性迁移并重新审核。

## 证据边界

- 当前 `main` 已包含 R3 桌面候选和客户试用基础，但不代表 V0.2 完整功能完成。
- V02-01～V02-10 仍以各自任务证据为准；真实平台、Windows、触达、部署和客户 UAT 不能由文档或测试替代。
- 生产客户库使用 PostgreSQL；SQLite 只能用于明确标记的本地实验。
- 外部消息必须人工确认，不绕过验证码、限流或平台风控。

## 选择性迁移规则

旧 `codex/authorized-dual-platform-mvp`、`codex/self-use-auto-public-reply-v1` 和其他历史分支不直接合并。迁移前必须逐提交检查目录、数据契约、密钥边界和测试；任何自动外联、旧 SQLite 客户库或与 V0.2 冲突的范围均排除。
