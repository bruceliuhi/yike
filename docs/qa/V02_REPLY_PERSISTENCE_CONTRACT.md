# V02 回复事件持久层候选验收

日期：2026-09-10

## Mac 接收 Win 回复修复（2026-09-10）

基线 `6846b30`，接收代码 `4c683ac`；仅接收 Win `96bb371` 的 `pilot/reply_store.py`、`tests/test_reply_store_postgres.py`，两文件字节完全一致，不接收同分支运行包 WIP。

- RED：新建专属测试库后，原 main 的首次人工跟进用例以 `InsufficientPrivilege` 失败（1 failed / 31 deselected）；追加式表的 `SELECT FOR UPDATE` 需要未授予的更新权限。
- 修复：保留最小权限，以事务级有序锁保护事件与平台去重键；追加更正使用递增 revision、校验原归属及状态；只允许符合契约的已读变化，历史原请求重放不覆盖当前事实。
- GREEN：`pytest -q tests/test_reply_store_postgres.py tests/test_reply_store.py tests/test_reply_contract.py tests/test_outreach_store.py --tb=short`，**55 passed / 0 skipped，6.30s**；其中32项实际受限PostgreSQL，平台/发送来源输入为合成。`git diff --check`通过；未重复全量、桌面构包或平台实测。
- 独立非作者 `full_scope_review` 对 `6846b30..4c683ac` 代码/架构/质量审核 PASS，Critical/Important/Minor均0；质量采用上述本轮执行证据，审核方不重复运行。Mac限定接收此持久层修复。
- 仅验证持久层接收，不代表真实平台回复采集、客户端闭环或V02-08整卡完成。以下无PostgreSQL验证的说明是原候选历史，不覆盖本次实际数据库证据。

## 原候选历史

本候选新增 `migrations/118_v02_reply_events.sql`、`pilot/reply_store.py`、`deploy/grant_reply_events.sql` 并注册至 `pilot/db.py`。专项测试：

`uv run --frozen pytest -q tests/test_reply_contract.py tests/test_reply_store.py tests/test_outreach_contract.py tests/test_outreach_store.py` → **32 passed**；compileall 与 diff check 通过。

表按租户/用户隔离，平台回复必须先找到同一所有者的触达确认快照，再以来源、原发送请求、平台和公开回复 ID 建立去重范围；已读变化使用同一事件 ID的新 revision，人工跟进不携带平台字段，更新/删除由不可变触发器拒绝。服务层保留原始 payload 摘要并在回读时校验。

本轮没有 PostgreSQL 实例，未证明真实迁移、RLS、并发 replay/conflict、回滚、会话撤销、角色授权或真实平台回流。正式服务还必须在同一事务重验商机/来源/画像/发送请求归属及纠正目标，不能把此候选当作回复已回流、已读已同步或产品上线。
