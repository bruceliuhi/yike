# 主线测试基线漂移：独立诊断

基线 `15ddb7039e385c9adbda04bfd553bf8d222e6308`，2026-09-09。本地独立 Agent `baseline_regression_audit` 只读诊断，不是 CodexWin 或生产验收。

## 复现

在 `da2a2f2` 工作树运行 `pytest -q tests/test_bootstrap.py tests/test_d04_remediation.py`：93 failed、51 passed。相关 `app/`、两个测试文件及共享 fixture、`001_discovery.sql`、`AUTHORITY.md` 与上述 main 基线无差异。

1. `test_bootstrap.py` 两项把当前权威固定为旧 Discovery SHA/状态，与现行 V0.2 权威冲突。历史草案自身 hash 校验应保留；当前权威应单独验证现行状态和入口。
2. D04 的 91 项失败：fixture 固定在 2026-08-12、Day14 在 8 月 26 日，而 SQL 触发器读取今天的真实时钟，合法前置事实已经超期。不能通过放松生产窗口修复。

## 诊断对照（不是普通回归通过）

- 独立 Agent 仅在临时测试进程内统一 SQLite `strftime(...,'now')`、Repository/Workflow/Web 默认时钟，保留原 SQL 和断言：D04 139 passed。
- 不替换 SQLite 真实时钟，另运行过期/取消矩阵：32 passed，含 `test_sql_rejects_backdated_d04_fact_when_server_is_past_day14`。
- 临时对照不是可提交修复，也不是普通全仓 green。后续在独立测试基线分支修测试时钟，保留原生过期反例并重新审核。

本诊断未发现身份候选引入这些失败；不表示身份代码已通过审核，也不解除全仓回归或发布门禁。
