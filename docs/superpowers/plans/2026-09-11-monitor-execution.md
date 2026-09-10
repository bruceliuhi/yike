# 监控到期轮次接原执行链

基线 `75fe6c5`，完整 V0.2 的连续发现接续。已有计划/日历不重复开发。

## Global Constraints

- 不重写 START/CLAIM/RENEW/候选上传/FINISH 协议。真实执行仍须设备签名、当前本人账号、已确认当前画像/策略、租约和额度校验。
- 每个计划时间槽最多一个持久原 START request_id。响应丢失、重启、并发请求不生成替代 START；未决轮次先核对原执行记录。
- 服务端时钟，在线心跳间隔上限90秒；首次上线或超过90秒空窗不补跑。日历完全遵守已提交 policyVersion=1。
- 计划 ACTIVE 不等于采集成功。READY 是已预留待设备签名，RUNNING 是已有服务端任务，不是平台完成；后台不可据此宣传真实线索/Windows/上线成功。
- 不自动对外评论或私信。无真实平台、Windows、生产与客户证据时保留未完成。
- 用户要求省Token：改动路径TDD，一次独立批次审核；只补失败差异，不全量测试/构包。

## Task 1: 持久轮次与执行围栏

文件归属：`pilot/monitor_runtime.py`、`pilot/monitor_runtime_contract.py`、`migrations/127_v02_monitor_runtime.sql`、`deploy/grant_monitor_runtime.sql`、`pilot/db.py`、`pilot/execution_runtime.py`、`tests/test_monitor_runtime_postgres.py`。

服务 `MonitorRuntime(database, execution_runtime)`，`pulse(claims, body)`；严格 `MonitorPulseRequest` 字段 schema_version=`monitor-runtime-v1`、plan_id/device_id/monitor_session_id（canonical UUID）、credential_version（strict int 1..2147483647）、targets（现有 ExecutionTarget，1..5，平台不重复）。monitor_session_id 是客户端本次进程随机ID，不是 Cookie。请求不接受时间、用户、next_due 或 human_confirmed（同计划创建的明确确认已保存）。

新增 owner/tenant RLS 的在线绑定与轮次表。绑定包含 plan revision、设备、credential_version、原有序targets、monitor_session_id、last_seen。轮次固定 plan_id/revision/scheduled_at、有效期（预留后90秒）、设备及原 START JSON、request_id；唯一 plan+scheduled_at。一计划最多一个未决轮次。原请求及绑定不可改；状态/执行task关联有列级最小权限。授权脚本检查继承及 SET ROLE 可达特权/不可变字段，复用126/114模式。

Pulse 原则：
1. 当前有效会话，复用 runtime._key、_connection、_strategy 核对原计划确认快照及三个支持的平台；禁用部署模式则501。计划必须 ACTIVE。
2. 与 MonitorPlanStore 相同 owner advisory lock；设备/连接/画像/策略锁在计划行锁前，owner gate 使计划编辑和pulse串行。START 不反向获取此owner锁；START已有设备/画像锁与pulse同序。
3. 同 revision 设备/credential/targets 不一致返回409 `monitor_binding_conflict`，不自动换号。显式暂停/恢复产生新revision后才能重新绑定。旧未决任务先返回 RECOVERY_REQUIRED，不启动下一轮。
4. 首次上线、monitor_session_id变化或last_seen距今>90秒重新锚定在线；已错过 next_due 时计算严格未来值，返回 SKIPPED_OFFLINE。next_due 未到返回 WAITING。不得把离线说成无新线索。
5. 仅稳定同进程在线、next_due 位于上次last_seen之后且不晚于当前server time时预留轮次。否则错过窗口跳至严格未来（SKIPPED_MISSED）。预留时更新计划 next_due 为严格未来；不改变用户revision。
6. 同进程仍有效的原预留返回完全相同 START；不更换request_id。预留到期且未启动标EXPIRED，不能迟发START。新进程遇旧未决预留返回 RECOVERY_REQUIRED，过期后才允许下一未来槽。
7. 已启动轮次从原 task 的真实状态/deadline判断。未终结返回 RUNNING/RECOVERY_REQUIRED，不新建；SUCCEEDED/CANCELED 或超过deadline才能关闭该轮次，不把截止时间等同已采集成功。繁忙期间错过的日程也不补跑。

统一响应：schema_version、plan_id、plan_revision、state（WAITING/READY/RUNNING/RECOVERY_REQUIRED/SKIPPED_OFFLINE/SKIPPED_MISSED）、server_time、next_due_at、occurrence（null或固定 id/scheduled_at/expires_at/start_request/task_id）。只读/等待不创建平台任务。固定安全错误以 `ExecutionRuntimeError` 返回，底层数据库异常外层转换503 `monitor_runtime_unavailable`。

ExecutionRuntime 增加可选 `monitor_runtime` 接线，不改变现有签名JSON：
- START成功建task前后同事务，以 `request_id` 查询并锁定原预留，对原 START JSON逐字段规范化比对、到期时间、当前计划状态/revision/绑定及snapshot检查，关联真实task/run；伪造未预留的monitor START拒绝。无monitor_runtime时monitor策略不能START。
- `_versions` 对 monitor task 追加当前plan/revision及原轮次关联检查；暂停/恢复旧revision后 CLAIM/RENEW/候选入库/FINISH 不再续授权。该check不改计划，但须在设备/连接/画像/策略锁之后取得计划的非阻塞共享行锁并保留到事务结束，和暂停建立提交顺序；锁忙拒绝，不形成plan→profile反向等待环。START同样保护计划，保留原runtime重复围栏/事务验证。CANCEL可结束已暂停旧任务。普通once完全不改变语义/签名字节。
- 不能仅因 capability_check 接受 monitor 就绕过预留；现有runtime先校验设备签名。

TDD：专用受限Postgres与真实 Ed25519 + 正式已确认策略/计划。验证首次上线跳过、稳定到期唯一原请求/并发恢复、START→CLAIM关联、无预留/改目标/过期拒绝、暂停后拒续授权、重启/轮次未决/设备换绑、owner隔离和最小权限。只测必要路径，不全量回归。可让测试把服务端存储的last_seen/next_due改成合成时刻，不以fixture证明真实平台采集。

## Task 2: 普通入口与部署能力

CodexiMac负责 `pilot/monitor_runtime_api.py`、普通web/ui/runtime装配、`foreground_collection.py` 显式 `three-platform-monitor-v1` 模式（兼容once，monitor仅policy1且相同受限搜索能力）、对应HTTP/policy小范围测试与文档。现有 foreground support 不冒充新原生客户端已适配；新模式的后端能力与客户端实际可用状态分别呈现。

本批不虚构“客户端已经自动运行”。后续接主进程心跳/原签名/采集worker、暂停/恢复界面与真实平台验收，继续完整Goal。

## 实施与验证

最终源码 `a68b945ac2c85c61f21d3097199afe6ff6094683`，非作者独立批次审核及修复差异复核 GO。`374eb11` 接普通认证 pulse 接口和显式部署模式；`f528789` 实现127持久轮次和原执行围栏；`fa41d71` 补正式确认策略/计划、B站合成当前连接、真实Ed25519与受限PG流程，并移除误放入产品树的过程报告。

定向证据：原搜索能力与新模式19 PASS；新HTTP/普通runtime接线4 PASS。Task1首次35 PASS只证明参数、迁移ACL与原签名/请求契约，**不证明周期运行**；补充3个受限PG组合场景 PASS（11项未重跑）：离线跳过/并发唯一预留/原请求重开/换进程恢复、签名START→CLAIM及暂停拒RENEW、未预留/过期拒START。正式部署仍需真实平台和客户端验收。本批不全量测试或构包。

首次独立审核 `fa41d71` NO-GO，专用受限PG与真实设备签名窄复现：P1暂停提交和续租提交缺乏并发顺序；P2繁忙期间错过时段会补跑；P2恢复新revision仍返回旧预留READY。`a68b945` 全部修复：原“只读计划”细化为不改计划+非阻塞共享行锁，不能用无锁检查替代暂停围栏；忙碌保持在线并跳过到期槽；旧revision只恢复核对。对应RED 3 FAIL → 受影响真实PG GREEN 7 PASS/11未重跑（含原3场景，不能直接相加）。独立复审仅看差异，未重跑测试，无新增P1/P2。专用合成PG容器随本批清理，共享库未动；过程报告保留在私有git工作树元数据，不进入产品树。

下一接入点：原生main按已保存计划每30秒调用 `/api/ui/monitor-runtime/pulse`；保持每进程 monitor_session_id，READY 仅提交返回的原 START 给已有设备签名/执行会话；不可自己生成替代UUID或重写策略成once。RUNNING/RECOVERY_REQUIRED 先核对原任务，不重复采集；SKIPPED_* 不是“没有新线索”。当前客户端收集器仍只接受once，下一批须连接其monitor入口与暂停/恢复，不能仅改显示文案宣布可用。
