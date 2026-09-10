# 持续监控客户端闭环

基线：`3c23b004d65c7ecf68e00f8d5a51acce3055a5b3`。属于已批准完整 V0.2，复用现有监控计划、127 轮次和签名执行，不重建调度数据库。

## Global Constraints

- 仅当前认证用户、当前设备与已确认策略/账号可执行；换用户、换凭据、退出、暂停、停止不明确时停止本机来源。登录态不进业务日志。
- 服务端决定到期时间和唯一原 START；客户端不改策略快照/摘要，不伪造 once，不对未知领取重开来源，不补跑离线历史。
- 多计划共享单个采集槽；多平台轮次按原目标顺序串行，复用签名租约/上传/FINISH。繁忙只维持心跳并明确跳过到期，不批量预占。
- UI 区分计划保存、本机接管、轮次运行、实际采集结果；没有真实平台证据不得宣称采集成功。重启后原计划可查看，须用户确认本机账号后恢复接管，未知旧轮次不重开。
- 外部发送不在本批。只做改动路径测试及一批独立审核，不重复构包/全量测试。完整 Goal、真实 Windows/平台/部署/UAT 不因本批结束而完成。

## Task 1: 原生监控接管与既有执行器（独立实现 Agent）

负责 `desktop/src/shared/monitorCollection.ts`、main 监控控制器、foregroundCollectionController/collectionWorker/pythonCollectionDriver 最小接线、executionServicePolicy、main/preload/contracts 的 native IPC 与对应测试。不要修改 renderer；root 接页面及 Python。

新主进程私有 execution 操作：`monitor.support` GET `/api/ui/monitor-runtime/support`，响应 `{schema_version:'monitor-runtime-support-v1',mode:null|'three-platform-monitor-v1'}`；`monitor.pulse` POST `/api/ui/monitor-runtime/pulse`，严格沿用 MonitorPulseRequest，增加 `can_start:boolean`。false 时未占用的到期轮次返回 `SKIPPED_BUSY`，pending 原轮次仍可原样返回。公共 requestApi 不接受这些操作。

计划操作也通过私有 execution transport 固定路由：`monitor.list` GET `/api/ui/monitor-plans`；`monitor.create` POST `/api/ui/monitor-plans`；`monitor.state` POST `/api/ui/monitor-plans/state`；`monitor.receipt` GET `/api/ui/monitor-plan-operations/{request_id}`。严格复制现有 Python contract，所有响应验证。

原生 IPC 建议 command：LIST；CREATE（requestId/profileVersionId/strategyVersionId/targets/humanConfirmed:true）；ATTACH（planId/expectedRevision/targets/humanConfirmed:true）；SET_STATE（requestId/planId/expectedRevision/state/targets 可选/humanConfirmed:true）；RECEIPT（完整原 CREATE 或 SET_STATE 命令用于绑定验证）。公开结果不含签名/凭据/私有 session，不含原 pulse START。导出共享 schema/type，尽早通知 root 接口。

接管限当前进程和认证 scope，保存计划不等于接管。CREATE 先核对当前策略/账号与命令，保存确认回执后自动接管；ATTACH/恢复必须核对服务器 revision 和当前目标/账号。未知 CREATE/SET_STATE 不自动重试；查询原回执及最新列表解决，不另造 UUID。服务端同策略唯一约束/CAS 保持兜底，重载 UI 可从计划列表确认接管，不要求原 UI 内存存在。

main 控制器启动一个有界、不重入的定时轮询（约20秒，测试可注入/手动 tick），只对已明确接管的当前用户计划运行；每轮检查计划最新 state/revision，失效立即取消本机对应 worker。停止计划先停止本机采集，再提交状态；不能把本机停止写成服务器已暂停。退出清空本进程接管，不复用旧用户状态。LIST 返回计划及本机状态/轮次 taskId/最近错误、下次服务器时间，供页面显示。main 生命周期 attach/shutdown 接通，服务不可用不刷错误日志。

共享 foreground 的 busy/stopUnconfirmed 槽，添加 main-only 执行已预留 monitor START 的方法（不暴露 raw START IPC）。原 foreground.start 仍只允许 once。核验 monitor support、原策略摘要、全部原 target 与账号。提交原 START 并严格验证原 receipt，已有任何 CLAIM/RENEW/FINISH journal 则不重开来源；新轮次每个平台按原回执用独立当前 scope 串行执行。任何未知租约/上传/完成、会话变化、取消/来源停不下来均停止后续平台。下一平台仍核对原身份/目标，不借新 session 接续旧任务。worker/driver 允许已确认 monitor policyVersion1 原快照的一次迭代，服务端预留和签名租约仍是权限。

定向测试：原一次模式不扩权；显式接管后到期 pulse→原 START→原 worker；忙时 false、不重复打开；多平台原顺序；暂停/用户变化停止；未知轮次/重启不重开；固定路由拒绝 renderer pulse。仅相关文件用例和必要 typecheck。报告放 git worktree 私有 sdd 目录（绝对路径），不可在产品目录创建 sdd 文件。

## Task 2: 服务端可用性及忙闲心跳（root）

增加认证的 monitor support 只读接口，仅显式 three-platform-monitor-v1 为可用。can_start 默认 true 保持已交付 pulse 合同；false 时正常刷新在线时间，到期只推进未来并返回 SKIPPED_BUSY，不预占轮次、不改变已有原请求。定向验证 support、严格 bool 及真实 PG 忙→空闲不追补。

## Task 3: 既有任务页面接线及整批审核（root）

复用已确认策略和 TaskWizard 的最后人工确认，通过新原生 CREATE 保存并接管 monitor；不把监控伪装一次任务。原 once 流程保留。监控路由接真实计划列表、详情、暂停/恢复/本机接管及原请求核对，复用原 UI 组件不另做视觉设计。未知请求持久保留原 UUID，按钮不得隐式重新创建。显示离线/未接管/繁忙跳过与实际轮次状态，不显示假采集数。相关 UI 合同测试、typecheck、一批非作者审核，修复仅复核差量，随后快进 main。
