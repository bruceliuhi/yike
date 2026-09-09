# V02 回复事件持久层候选验收

日期：2026-09-10

本候选新增 `migrations/118_v02_reply_events.sql`、`pilot/reply_store.py`、`deploy/grant_reply_events.sql` 并注册至 `pilot/db.py`。专项测试：

`uv run --frozen pytest -q tests/test_reply_contract.py tests/test_reply_store.py tests/test_outreach_contract.py tests/test_outreach_store.py` → **32 passed**；compileall 与 diff check 通过。

表按租户/用户隔离，平台回复以来源、原发送请求、平台和公开回复 ID 建立去重范围；已读变化使用同一事件 ID的新 revision，人工跟进不携带平台字段，更新/删除由不可变触发器拒绝。服务层保留原始 payload 摘要并在回读时校验。

本轮没有 PostgreSQL 实例，未证明真实迁移、RLS、并发 replay/conflict、回滚、会话撤销、角色授权或真实平台回流。正式服务还必须在同一事务重验商机/来源/画像/发送请求归属及纠正目标，不能把此候选当作回复已回流、已读已同步或产品上线。
