# 持续监控：持久化日程基础

基线：`ee3743a`。沿用已批准的 V0.2 监控设计与 `schedule.ts` policyVersion=1，不改变采集或外联授权。

本批范围：已确认的 monitor 策略注册为持久计划；按服务端时间计算严格未来的日程；暂停、恢复、版本冲突和原请求回执；普通 Web API 接线。暂不创建采集轮次、不发 START、不声明采集能力支持 monitor。下一批将接原请求唯一轮次和原生执行器，只有届时才能显示正在监控。

## 验收

- 只接受当前且已确认的画像/策略、monitor 模式、明确 policyVersion=1、再次显式确认；不接受客户端传入日程或 next_due_at。
- daily 按当地时间；DST 缺失时刻跳过，重复时刻仅取首次。interval 当日窗口起点锚定、按实际小时、允许跨夜、左闭右开；无效 DST 边界跳过窗口。
- next_due_at 只是下一次计划时间，过期不补跑；恢复从服务端当前时间重新计算。
- 计划只允许 ACTIVE/PAUSED（期望状态，不是执行证明）；响应固定 execution_status=NOT_CONNECTED。原策略、画像或平台授权不会被自动替换。
- owner/tenant 隔离、会话有效性、幂等回执、CAS revision；同一策略每人至多一个计划，总量有界。
- 暂停无需策略仍有效；恢复/创建必须实时 resolve。保存过的历史回执不证明当前策略仍有效。
- 仅运行日历/新存储/API 相关测试及一次独立批次审核，不全量构包。

## 分工

CodexiMac：日历、普通 API/runtime 接线、集成和证据。
独立实现 agent：MonitorPlanStore、迁移126、最小权限与专用 Postgres 测试。
非作者 reviewer：审核冻结提交及修复差异。

## 结果

源码 `71ab809`（包含 `eabdf5f` 日历与接口、`d773f3e` 存储）。非作者独立修复差异审核 GO，绑定完整 SHA `71ab80954c530d64fc1141ef95551c9e5b3ebcea`；尚无客户端持续采集、真实平台、Windows、部署或商业验收证据。

普通 Web runtime 装配 `MonitorPlanStore`，复用同一个 `ResearchStrategyStore.resolve`。认证接口均在 `/api/ui`，不接受查询参数或客户端身份字段：

- `POST /monitor-plans`：`schema_version=monitor-plans-v1`、`request_id`、`profile_version_id`、`strategy_version_id`、`human_confirmed=true`。返回原请求回执，plan_id 等于创建 request_id。
- `POST /monitor-plans/state`：同 schema、全新 request_id、plan_id、expected_revision、state（ACTIVE/PAUSED）、human_confirmed=true。原请求重试返回原回执，旧 revision 拒绝。
- `GET /monitor-plans`：本人最多20个持久计划；同策略版本不能重复建计划。
- `GET /monitor-plan-operations/{request_id}`：本人历史回执；不意味着原策略现在仍有效。

日程来自已确认策略，`next_due_at` 来自数据库当前时间。ACTIVE 仅表示用户期望启用，所有输出仍有 `execution_status=NOT_CONNECTED`；不会把下一次计划时间当作已调度或已采集。过期的保存时间是未执行的历史计划；本批没有后台进程自动推进它。后续客户端不得仅据 ACTIVE 派发，必须接原轮次请求、防重、实时连接/能力校验、离线跳过及原执行租约。当前上限20个（含暂停），计划归档/替换尚未接入。

定向证据（合成业务数据，非真实商机）：日历14 PASS；HTTP与普通runtime首次18 PASS/1失败（测试误将既有 HTTPS 400 预期为403，修正后误用错误 envelope，再改为既有 detail 后对应1 PASS）；独立受限PostgreSQL存储16 PASS，使用专属临时库，未修改共享库。没有全量测试或重复构包。

首次独立审核 `d773f3e` 为 NO-GO：授权脚本未拒绝继承角色的计划全表 UPDATE，可修改原确认绑定。`71ab809` 复用已有策略授权的可达角色检查，覆盖 NOINHERIT/SET ROLE、不可变列、历史回执与特权成员；另将策略存储不可用保持503，不误报策略冲突。仅对应权限、服务不可用与受影响正常保存/恢复6 PASS（14项未重跑）；不与前16项简单相加。编译及 diff 检查通过。

最终审核仅检查修复差异，独立专用PG探针确认 NOINHERIT 但可 SET ROLE 的全表UPDATE路径被拒绝，探针事务回滚，无新增P1/P2。专用合成测试库随本批清理，共享库未动。没有重新构包；旧Windows包不包含本批源码。完整Goal继续，下一片接周期实际执行，而非重复本批存储协议。
