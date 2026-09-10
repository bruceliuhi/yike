# 07B 单次领取与发送结果台账 Implementation Plan

> For agentic workers: use executing-plans；已有隔离工作树，按当前授权内联推进，独立审核，不重复构包。

**Goal:** 在普通runtime接上人工确认队列到原设备的一次性派发许可，以及原请求结果/UNKNOWN恢复；不以服务许可代替实际平台发送。

**Architecture:** 延用owner事务锁及Ed25519会话签名。123新增不可变领取/结果事件，新确认队列状态扩为QUEUED、UNKNOWN、SENT、FAILED、CANCELLED；领取即UNKNOWN，不造可自动续租的DISPATCHING。业务服务不保管平台登录态。

**Tech Stack:** 现有Python/FastAPI/PostgreSQL；不增依赖。

## Global Constraints

- 原V0.2完整Goal不缩小；本批不外发，不改Win文件，不启用全局outreach能力。
- 服务端默认不给派发许可，仅显式配置`YIKE_PILOT_OUTREACH_PLATFORMS`中的首发平台能CLAIM；配置不证明平台适配已验收。
- CLAIM同cursor重验原最新context、原设备/密钥版本、120秒内渠道检查及确认时间。只在首次提交成功的响应返回`dispatchAllowed:true`、原context和最迟30秒/原渠道120秒以内的`dispatchBefore`。重放/GET/结果响应永远false，丢首回执不自动再领取。
- 本机动作前仍需实际渠道复核及**持久消费**`(requestId,claimId)`，过期/重复响应/IPC/重启不得再次动作；Win接入未完成时不能声称端到端防重。
- UNKNOWN/SENT仍防新UUID；只有明确非投递FAILED或派发前CANCELLED后才允许重新人工确认。队列状态UNKNOWN不允许取消或重新排队。
- 结果签名绑定原requestId、claimId、context摘要、同设备及独立resultId；只查原领取快照，不重验后来修改的草稿/来源/连接。设备换钥可用当前新凭据报告原设备结果，撤销设备不获写权。
- SENT仅设备提交明确平台接收回执，FAILED仅设备提交明确本次未投递回执；UNKNOWN无确认字段。证据为有类型的观察时间、公开结果ID及摘要，不保存原始敏感响应；签名设备声明不冒称服务器独立平台核验。
- 原resultId同内容重放返回历史，异内容409；UNKNOWN可到SENT/FAILED，终态不可反转。旧117回复origin和旧renderer DTO仍须后续显式接入，不能伪造转换。

## Task 1 — 普通HTTP派发闭环

**Files:** `pilot/outreach_dispatch.py`（输入/事务）、`pilot/outreach_queue_api.py`（路由）、`pilot/outreach_queue.py`（状态回执/防重/取消）、`pilot/runtime.py`（平台配置）、`pilot/db.py`、`migrations/123_v02_outreach_dispatch.sql`、`deploy/grant_outreach_dispatch.sql`；测试`tests/test_outreach_dispatch_http_postgres.py`。

**Interfaces:** `/api/ui/outreach/dispatch/signing-payload`准备`{request}`；`/dispatch`接受`{request,signature}`。request的action为CLAIM或RESULT，公共requestId/deviceId/credentialVersion/contextSha256；CLAIM含claimId，RESULT增加resultId及严格outcome。GET沿用原queue入口，返回原状态及dispatchAllowed:false。

- [x] 写实际HTTP RED：签名准备404，先跑`.../python /tmp/yike-draft-pg-check.py tests/test_outreach_dispatch_http_postgres.py::test_claim_once_unknown_recovery_and_signed_platform_receipt`。
- [x] 实现新输入/事务/API/123授权，首次领取和取消共用owner锁，结果仅操作原领取，SQL强制不可变事件。
- [x] 跑本批HTTP/受限PG及受改queue测试一次，覆盖签名/原设备、重启重放、并发唯一许可、旧事实/过期、取消后拒领、UNKNOWN不重派、结果冲突及默认配置拒绝；只对实际失败补差量。
- [x] 一个具体commit独立审核，补合同/唯一任务书/部署说明；正常推main并核对远端，不构包、不合成平台成功。

## 本批验证

`04a4017`经非作者`draft_batch_review`对`1e70f36..04a4017`独立规格/代码/架构审核GO，无阻断，未重复测试/构包。

- 实际HTTP先取得新接口404 RED（1 failed）。实现后9项dispatch及11项受改queue合跑：16 passed/4 failed，12.77s。失败均为旧queue夹具未执行123新增读取授权，真实表现为原查询/取消500；补齐部署同款授权后仅这4项重跑4 passed，3.55s。部署说明同步要求两份grant，未放宽权限。
- 追加同owner跨新队列复用claimId，实际500 RED（1 failed）；补事务内冲突检查返回409后，该项及并发唯一许可差量2 passed，2.47s。其余通过且未改路径复用原证据，不冒称最终全量重跑。
- 所有测试使用临时真实PG/受限role/实际HTTP和设备签名，完成仅删除本次临时数据库，无生产操作。平台观察/结果为合成输入，不能作为真实投递、客户效果或商业证明。

本机消费许可、真实渠道、Win客户端消费ACK、117回复origin接入仍未完成。Mac接续06B/07B/08整链，完整Goal保持active，不以本片GO关闭任何真实平台门槛。
