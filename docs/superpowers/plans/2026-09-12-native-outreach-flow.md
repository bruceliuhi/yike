# 原生确认闭环装配

Base a1216ff。继续已批准V0.2及现有确认页，不改视觉布局，不进行外部发送/生产部署。整批一次独立审核，变化路径定向测试；现有签名、outbox、消费许可和Job监督复用。

## Global Constraints

- main拥有会话、设备、服务Origin、profile路径、冻结context及连接映射。renderer只提供操作意图，不能签任意payload、换路径或提供AVAILABLE。
- PREPARE只读服务端最新已保存草稿、context和当前连接；核对其与屏幕draft完全一致，原文/账号/收件人/全文返回给用户确认。此步不声称平台已核验。
- 用户明确CONFIRM后才做实际channel.check→签名122确认队列→已有123 dispatch session/consumer→一次execute→原outbox→RESULT。不得将CLAIM或UNKNOWN当已发送；不自动重试。
- profile来自当前身份的RESOLVED连接记录及其原VERIFY服务器receipt，连接ID/版本/公开账号必须与当前CONNECTED row、冻结context相符；不能猜测profileUUID或只比昵称。
- PREPARED响应返回原requestId/claimId/tenantId/contextSha256；renderer须先持久记录这些恢复元数据，再可CONFIRM。正文不进入恢复日志。关闭/换会话取消活动driver；清理未知则该controller保持阻断，不重建绕过。
- 本批可注册可信sender验证的专用IPC，但不打开服务端默认关闭的平台外发许可，不实际发送。Windows/平台实机与部署UAT仍未完成。

## Task 1 — shared command / private controller（独立实现）

新增shared/nativeOutreach.ts：频道`desktop:native-outreach`；严格command：
- PREPARE `{action,requestId:uuid,draft}`，draft严格复用ContactDraft的业务字段（opportunityId/channel/content/savedContent/version/accountId/recipient；可忽略UI-only confirmedFingerprint不发送）。
- CONFIRM `{action,flowId:uuid,humanConfirmed:true}`。
- CANCEL `{action,flowId:uuid}`。
- RECONCILE / RESUME_RESULT `{action,binding:{tenantId,requestId,claimId,contextSha256}}`，仅查询/补原outbox结果，绝不再CLAIM。
- CANCEL_QUEUED `{action,binding}`：用户明确取消原QUEUED请求；只调用原queue取消，不生成新UUID，不把UNKNOWN取消失败当未投递。

Result：PREPARED `{state,flowId,binding,context:OutreachContext}`（context只业务公开信息/正文，无profile路径）；FAILED `{state,error:固定安全码}`；CANCELLED `{state}`；其余包装`{state:'RESULT',binding,result:现有dispatchSession结果}`。不得把原RESULT包装为发送成功；共享类型可type-only引入既有context，不在renderer引入Node实现。

新增main/nativeOutreachController.ts和所需小型confirmation协议/签名器，扩既有private requestOutreach allowlist：latest draft GET、context POST、confirmation prepare/apply/cancel，加现有dispatch操作；public servicePolicy不开放这些写入。签名必须复用既有dispatch signer的canonical/Ed25519方法（可提取公共纯函数，禁止任意sign IPC），对照实际`pilot.outreach_queue.Confirmation`：request.context是`{binding,deviceId,connectionId,connectionVersion}`，不是完整OutreachContext；prepared还有requestSha256，须校验。

构造controller options `{serviceOrigin,identity,store,vault,journal,outbox,driver(context,profileId)}`。driver返回现有NativeOutreachChannel+stop/cleanupConfirmed。暴露execute(raw)及stop()；单活动flow、会话/时间/内容变化拒绝；所有异常固定码。scope当前校验遵循现有controller；profile映射读store+VERIFY原receipt。最新draft receipt与context字段严格核对（可复用现domain短草稿解析，但不能让renderer不可信输入决定身份）。

PREPARE的flow120秒超时，CONFIRM消费内存flow一次且人类bool必须true；先check保存实际observation用于122，冻结原轻context和requestId签名提交；确认API响应必须原ID/QUEUED，不明确则不CLAIM。dispatch使用原claimId。为consumer再次check复用同driver的只读缓存仅在5秒有效期内；过期先明确stop已核验未执行driver，再新建同profile driver供consumer检查。不得扩检查有效期。主进程重启恢复只用RECONCILE/RESUME_RESULT。

Task1专属：shared/nativeOutreach.ts、main/nativeOutreachController.ts、main/outreachConfirmation*.ts、main/outreachDispatchSigner.ts必要纯方法导出、main/serviceClient.ts必要private路由扩展、对应tests。勿修改main.ts/preload/UI/现driver或Python。report同目录native-outreach-controller-report.md。少量完整controller链测试、签名实际Python向量，类型检查；不全量测试。

## Task 2 — existing UI / preload（根代理装配）

在现有SendConfirmation里桌面XHS分支使用原生flow；显示main返回的全文/原账号/对象与来源，用户勾选并确认。其他平台保留原流程而不虚构能力。现ContactEditor允许已连接XHS账号进入“准备发送”，只代表可核验，不给它伪造send capability。最小API桥加到contracts/preload/main可信sender；普通HTTP页面不暴露原生发送。使用现有对话框/提示/操作ledger保存原binding，未知只能核对/补结果，关闭不隐藏未决状态。

## Task 3 — driver lifecycle / integration（根代理）

实际CHECK结果可在相同context/未执行/未停止/5秒内重复读取给consumer，不伪造新checkedAt。增加只读核验后stop的正常终止：Job监督确认取消且尚未EXECUTE时，可返回UNKNOWN+cleanupConfirmed=true作为清理结果，不是发送事实；TS允许这种只读关闭的终态。仍保持单次execute/原context/清理异常拒绝。

主进程装配原身份、OS加密journal/outbox、profileStore、固定driver配置及controller；关闭时stop，publicIPC严格验证sender。验收以新增完整流定向、已有页面分支及一次类型检查为准；可见入口冻结后才构包，不因文档重复构建。

## 本批验证（持续更新，非发布结论）

Task3两个定向RED分别复现：重复读同一核验失败、只读stop被当不明清理；修复后driver 7 passed，Python bridge24 passed（合成页面+本机socket，非Windows实机）。preload固定API用例随新增专用channel先失败，更新精确名单/调用断言后1 passed；最终driver/preload合计8 passed。controller独立实现见[native-outreach-controller-report](native-outreach-controller-report.md)，46定向通过包含实际Python签名字节向量。首次集成类型检查发现controller的never箭头函数未完成空值收窄和UI草稿索引类型问题；修复后再做一次集成类型检查，不重复无变化测试。UI与整批独立审核待接收，未跑全量suite或构包。
