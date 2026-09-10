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

进行中；尚无客户端持续采集、真实平台、Windows、部署或商业验收证据。
