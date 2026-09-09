# V02 触达确认持久层候选验收

日期：2026-09-10
提交范围：`pilot/outreach_store.py`、`migrations/117_v02_outreach_contract.sql`、`deploy/grant_outreach_contract.sql`、`pilot/db.py`、`tests/test_outreach_store.py`

## 结果

- 纯函数/快照专项：`uv run --frozen pytest -q tests/test_outreach_contract.py tests/test_outreach_store.py` → **11 passed**（之后追加幂等冲突与内容摘要测试后，当前专项合计 **11 passed**）。
- `uv run python -m compileall -q pilot/outreach_contract.py pilot/outreach_store.py pilot/db.py`：通过。
- `git diff --check`：通过。
- 独立只读复核：**PASS WITH MAJOR FOLLOW-UP**，确认可作为持久层骨架提交，但不构成 PostgreSQL 或生产验收。

## 已冻结的行为

确认快照在 PostgreSQL 中按 `(tenant_id, owner_user_id, request_id)` 唯一；事务内 advisory lock 使同一请求可重放或在绑定变化时返回冲突。RLS 仅允许当前租户/用户读取和插入；不可变触发器拒绝更新/删除。快照保存结构化确认事实和摘要，不保存草稿明文、Cookie、Token 或浏览器凭据。应用角色授权脚本只授予 SELECT/INSERT。

## 尚未证明的边界

本轮没有可用的 PostgreSQL 实例，因此未验证迁移执行、受限角色权限、跨租户/跨用户读取、并发重放、事务回滚、会话撤销或服务重启恢复。`OutreachConfirmationStore` 也不会自行查询来源/商机/连接是否真实存在、是否属于当前用户或是否已撤回；正式路由必须在同一事务中重新读取并锁定这些服务端事实，不能把调用方传入的模型当授权依据。`snapshot_sha256` 的正确生成目前由服务层保证，后续 DB/服务测试需覆盖伪摘要与审计。

因此 V02-06/07 仍为 `IN_PROGRESS`：没有真实平台适配器、发送路由、回执对账、回复回流、Windows 接入或客户 UAT，不得把本候选写成已发送、已上线或已产生商业结果。
