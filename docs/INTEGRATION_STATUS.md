# 当前整合状态（供后续 AI 交接）

## 2026-09-11 资料画像进入任务策略

修复新版资料引用摘要与策略消费者不兼容导致的 `profile_unavailable`；资料画像、显式空引用和旧画像可进入策略确认，来源撤销后阻止新解析且保留历史回执。`ecb5d1a` 独立整批 GO，[限定证据](superpowers/plans/2026-09-11-material-profile-task-readiness.md#实施与验证)。部署策略授权脚本须在迁移132后执行；行业策略正式采用与完整V0.2仍未完成。

## 2026-09-11 行业搜索策略建议

原搜索建议弹窗已接角色/销售方式、内容类型、意向信号、反例及画像原文依据；当前模型适配器强制新结构，旧结果保持兼容，策略随画像/模型回执保存。`25246c2`独立差量GO，首次P2及限定证据见[唯一记录](superpowers/plans/2026-09-11-industry-search-strategy.md#实施与验证)。策略仍是待核对建议，采用只更新搜索词；后续任务/候选判断实际采用、真实质量及上线验收仍未完成。

## 2026-09-11 独立业务画像

原画像页已能新建具名业务、独立保存/确认并在任务/评估中选用；确认业务A不会撤销业务B，旧任务版本保持不变。`077f68a`独立整批GO，定向证据及限制见[唯一记录](superpowers/plans/2026-09-11-independent-business-profiles.md#实施与验证)。无迁移或构包，不代表Windows/真实平台/生产/UAT；完整V02继续。

## 2026-09-11 资料画像引用闭环

普通画像页面已接字段出处保存/继承与明确人工解除；资料变更后，旧来源、搜索建议和候选AI评估不能继续作为有效新依据。源码 `73be8fc` 独立差量GO，保留首次三个P1及限定证据的[唯一记录](superpowers/plans/2026-09-11-material-profile-references.md#实施与验证)。历史文字与人工核验保留；未实现资料直接用于联系草稿的完整引用链，未真实模型/平台/Windows/生产/UAT，不标完整V0.2完成。

## 当前 Windows 接续入口

CodexWin 按[固定候选交接](handoffs/WIN_V02_CURRENT_CANDIDATE.md)从 `23d1793` 生成新 payload 并只构包一次，再用同包验收安装/重开和授权业务流程。旧 payload/Setup 不能代表当前功能；尚无本次 Win ACK、新包或实机通过记录。本次仅整合可执行交接，不重复测试或改变完整 V0.2 范围。

## 2026-09-11 首页机会简报

已接普通P02的认证只读服务、画像版本/业务日核对、已核验需求及结构化到期跟进；[唯一记录](superpowers/plans/2026-09-11-opportunity-brief-service.md#实施与验证)说明限定版本、审核与数据联验。原帖变化、实际平台、Windows、生产/UAT仍待验；不将PARTIAL简报当全网搜索完成。

## 2026-09-11 结构化跟进接线

普通P14/P15已接负责人、实际联系时间、下次计划和下一步的真实持久化，支持原请求恢复、纠正/撤销及旧历史保留；应用内已读与原始平台证据分别呈现。限定版本/独立审核/HTTP数据库联验见[唯一记录](superpowers/plans/2026-09-11-structured-followup-service.md#实施与验证)。不发送通知或平台已读，不代表Windows/生产/UAT完成。

## 2026-09-11 短句教练服务接通

普通编辑器现有“模型/原文/草稿预览→明确确认→有出处的短句→人工比较采用”链路；原请求持久去重，不自动发送。后端模型适配器和受限PG/HTTP/Node联验见[唯一记录](superpowers/plans/2026-09-11-short-coach-service.md#实施与验证)。未调用外部模型、未部署或验收Windows，完整V0.2继续推进。

## 2026-09-11 普通客户端联系草稿

评论/私信现可持久保存与重开恢复，保留人工修改、原请求和版本前驱；实际HTTP/受限PG联验及`fbc13a3`独立GO见[唯一记录](superpowers/plans/2026-09-11-contact-draft-client.md#实施与验证)。未开启短句模型或自动外发，原请求不存在不能自动解除保护；真实平台/Windows/生产与客户验证仍待完成。

## 2026-09-11 真实任务搜索覆盖

普通采集任务详情现可查看原任务窗口、原画像版本、已上传原文/去重来源统计与未查范围，复用现有持久记录；源码/审核/限定验收见[唯一记录](superpowers/plans/2026-09-11-search-coverage-service.md#实施与验证)。筛选、搜贝和穷尽范围未知不会补零，完整研究执行及产品上线门禁继续未完成。

## 2026-09-11 R4机会研究服务

普通客户端已接机会分类、原文时间线与类似建议/本机草稿；版本、审核及定向验证集中于[唯一记录](superpowers/plans/2026-09-11-opportunity-research-service.md#实施与验证)。只读预览不采集、不调用模型、不扣费；可信研究计量与实际执行仍待接，不能宣传类似研究已运行或产品已上线。

## 2026-09-11 三平台真实HTTP与数据库恢复联验

新增单场景贯通原生身份/签名/账号→HTTP→受限PostgreSQL，第二平台提交后丢响应，恢复原任务且不重采。联验暴露的STATUS/平台切换身份获取竞争已修复；定向验证及独立审核状态见[唯一记录](superpowers/plans/2026-09-11-multiplatform-http-acceptance.md#实施与验证)。同时更正上一批“HTTP平台乱序”的审核误报。来源仍为合成数据，不替代真实平台、Windows、生产和客户UAT；继续完整V0.2。

## 2026-09-11 单次多平台任务与恢复

单次任务已复用监控串行执行机制，按确认顺序在三个已支持平台中执行并共享记录上限；详情页可确认核对原上传、继续有证据证明未执行的平台。原回执/当前代次围栏防止缺日志导致重采。首轮阻断、修复及非阻断测试边界见[唯一证据](superpowers/plans/2026-09-11-multiplatform-once.md#实施与验证)。代码审核GO不代表真实平台、Windows或生产可上线。

## 2026-09-11 搜索排除词接通实际采集

合法排除词不再阻断普通单次/受控监控任务，原生driver依据确认快照过滤，保留原文、预算和去重冲突保护。版本、一次构建及独立审核集中于[唯一证据](superpowers/plans/2026-09-11-collection-exclusions.md#实施与验证)。这是代码接线修复，无真实平台/Windows/生产/UAT证据，完整Goal继续。

## 2026-09-11 搜索建议明确未受理恢复

已补配额/授权变化等“确未受理”原请求的持久证据；只有服务端与受理写入同锁确认并保留拒绝事实时，客户端才显示明确结束入口，原回执读取仍为只读。版本与验证集中于[接续记录](superpowers/plans/2026-09-11-search-suggestion-rejection.md#实施与验证)。未知、超时和404不解锁，不自动生成新请求或外发。此项不替代真实模型、平台、Windows及生产/UAT验收。

## 2026-09-11 搜索建议客户入口

现有TaskWizard已接普通服务的披露确认、后台建议、依据预览、人工采用与持久原请求恢复；新路径不再自动调用旧suggest。版本、限定检查与独立审核集中于[客户端记录](superpowers/plans/2026-09-11-search-suggestion-client.md#实施与验证)。下一步是同版本授权环境的画像→模型建议→确认策略→真实发现/复核主流程；没有实际模型、Windows安装包/平台、生产/UAT证据，完整Goal继续。

## 2026-09-11 搜索建议服务接续

已复用110请求台账和有总截止的模型子进程，接入授权预览、持久原请求、后台生成和普通runtime；128保留外发授权快照，未配置模型仍可认证查原回执。版本、审核与定向证据集中于[本批记录](superpowers/plans/2026-09-11-search-suggestion-service.md#实施与验证)。下一步是既有条件编辑器中的显式生成/预览采用及持久原请求恢复；客户端尚不可用，不能因API可用就开启旧自动suggest或宣布完整V0.2完成。

## 2026-09-11 任务结果与复核接续

首页已建任务判断、任务详情到本次发现候选的导航已接真实服务；候选按历史观察归属任务，展示当前版本，不用观察次数冒充商机数。版本、审核与定向测试集中于[任务结果记录](superpowers/plans/2026-09-11-task-results.md#实施与验证)。后续优先接普通用户的 AI 搜索建议及其原请求恢复，不能因内部模型/store已存在就称入口可用；真实平台、Windows、生产及跨行业试用继续未完成。

## 2026-09-11 真实采集任务列表接续

`/collection` 与 `?task=<UUID>` 已接原 execution 库的当前用户任务、分页、详情与确认取消；不再从旧 TaskRun 列表猜测运行结果。当前版本、独立审核与定向证据统一见[任务列表记录](superpowers/plans/2026-09-11-task-feed.md#实施与验证)。后续接工作台等仍消费旧 `service.tasks` 的入口，不重复开发 feed 或新建任务模型；真实平台/Windows/生产/UAT仍是未完成门禁。

## 2026-09-11 持续监控客户端接续

源码 `937bab6` 已经独立审核及修复差量复审 GO。已接新建监控、确认本机账号、周期采集、暂停/恢复、原请求核对与停止失败警告；多平台串行、多计划共享槽，离线/繁忙不补跑。[唯一版本与验证](superpowers/plans/2026-09-11-monitor-client.md#实施与验证)保留首次 NO-GO 及修复。不重复开发已接协议；真实平台、Windows新包、生产、UAT及完整V0.2仍未完成。下方“待接客户端”为历史时点。

## 2026-09-11 周期轮次后端接原执行

`a68b945` 独立审核 GO：在线到期预留→原设备签名START→CLAIM/RENEW围栏已接普通runtime，三平台monitor须显式配置；不改原签名字节或单次路径。[唯一源码与证据](superpowers/plans/2026-09-11-monitor-execution.md#实施与验证)保留首次P1/P2、7项受影响PG复测及边界。下一片必须接原生main心跳/worker和现有monitor界面；目前客户端仍once，不是实际持续采集或上线。不要重复开发计划/日历/127轮次协议；完整Goal继续。

## 2026-09-11 监控日程持久化基础

已补计划保存、暂停/恢复、原请求回执与 policyVersion=1 时区日历；普通runtime复用当前确认策略，固定返回 NOT_CONNECTED。源码、定向验证及审核结论集中于[本批记录](superpowers/plans/2026-09-11-monitor-plans.md)。下一片接唯一到期轮次和客户端原执行链；当前无周期采集、真实平台或上线证明，不重复开发日历/计划协议，完整V0.2继续。

## 2026-09-11 三平台单次采集接线

`ad0ff04` 已将当前账号页面→单次搜索任务→原生账号绑定采集→原候选入库链路扩展到小红书/抖音/B站；须显式三平台部署模式，未配置不开放，旧XHS模式不扩权。独立源码审核 GO，[唯一实施与证据](superpowers/plans/2026-09-11-three-platform-collection.md#实施与验证2026-09-11)记录定向测试、旧依赖缓存失败及两个P2修复。没有真实平台采集/Windows新包/发布证据；下一片接周期监控和多平台调度，不重复开发账号选择与同浏览器采集护栏。完整V0.2与父卡继续。

## 2026-09-11 三平台账号连接源码

`23cae61` 接通小红书、抖音、B站的原生登录平台分派和各自本人账号识别，复用原账号页面、隔离 profile 与版本化连接回执；独立源合入审核 GO。[单一证据及后续](superpowers/plans/2026-09-12-three-platform-login.md#本批实施与证据实际核对日期2026-09-11北京时间)保留首次 NO-GO 和仅一项补测。没有 Windows/真实登录/采集/发送/构包/发布证据，采集能力没有扩大；下一片实现两视频平台采集账号绑定及前台入口，之后周期监控，完整 V0.2 继续。

## 2026-09-11 小红书实际页面适配

07B已有页面适配（作者主页精确点击重开原帖），本批继续接受监督CHECK/EXECUTE进程桥及TS NativeOutreachChannel，见[当前记录](superpowers/plans/2026-09-11-outreach-process-bridge.md)和[接入合同](contracts/V02_OUTREACH_CHANNELS.md#07b-小红书页面执行接续2026-09-11)。下一步是可信connection/profile解析→main私有派发session→Win确认/结果界面装配；不是再写一套协议。当前没有开放发送入口，未实际外发、未部署，Windows实机仍待验，父卡继续IN_PROGRESS。

## 2026-09-10 结果落盘与重启补交

07B补充加密结果outbox→重启仅补原RESULT；原设备当前密钥可重放同一结果，历史事实不改写。接口/边界见[合同](contracts/V02_OUTREACH_CHANNELS.md#07b-结果持久恢复2026-09-10)，版本/验证/审核集中于[本批记录](superpowers/plans/2026-09-10-outreach-result-recovery.md#本批验证)。Mac下一步接真实driver，Win按新增outbox依赖装配main/UI；尚无客户端ACK或实际发送，不将底层恢复能力当产品上线。

## 2026-09-10 私有客户端派发链

`3478556`接通既有身份scope/HTTP传输→签名CLAIM→本机consume→签名RESULT及只读恢复，公共IPC没有派发权限。[验证记录](superpowers/plans/2026-09-10-outreach-private-session.md#本批验证)集中维护原失败和定向证据；[Win接入合同](contracts/V02_OUTREACH_CHANNELS.md#07b-私有客户端调用链2026-09-10)说明调用及状态。持久结果outbox、真实driver、main/Win界面接入未完成，父卡/Goal仍IN_PROGRESS；不把测试中的SENT当实际消息。

## 2026-09-10 本机一次消费组件

`74b4d52`补充实际文件持久消费和主进程控制器，异常不重发、跨会话重建防重；[单一验证记录](superpowers/plans/2026-09-10-native-outreach-consumption.md#本批验证)集中维护。尚未接私有transport/main/IPC、真实渠道或Win界面，不是平台收发完成。下一步按[接入合同](contracts/V02_OUTREACH_CHANNELS.md#07b-本机许可消费组件2026-09-10)装配真实链路，不重复开发日志，不重复无变化全量测试/构包。

## 2026-09-10 签名回复关联新发送来源

`9df9d69`独立审核GO；普通runtime接设备签名回复→122/123原claim→商机，历史/人工/设备证明分开，原UNKNOWN发送不自动变成功。同回复后续轮询复用首次事实及canonical event_id；124不改旧payload摘要。[单一证据](superpowers/plans/2026-09-10-signed-reply-origin.md#本批验证)保留失败和补验。Win须消费返回ID及证据列表，尚无ACK；Mac继续本机消费/真实通道，不将测试回复计为真实客户成果。

## 2026-09-10 单次领取与结果台账

`04a4017`独立审核GO。普通runtime已接一次派发许可、签名结果、UNKNOWN不重派及原请求恢复，123/最小授权就绪；[单一证据记录](superpowers/plans/2026-09-10-outreach-dispatch-ledger.md#本批验证)保留原失败与定向补验。本机持久消费/真实通道、Win消费ACK及旧回复origin桥接未完成，不宣称端到端最多发送一次。Mac继续这条主链，不重测本批无变化字节。

## 2026-09-10 人工确认已能持久入队

`8461892`独立审核GO：普通runtime接设备签名确认、同事务最新context复核、未决防重、原UUID恢复和派发前取消，122最小授权已配套。[本批记录](superpowers/plans/2026-09-10-outreach-confirmation-queue.md#本批验证)集中保留定向测试和原失败，不重构包。仅QUEUED/CANCELLED，无实际发送，Win尚未消费ACK；Mac继续06B/07B领取、实际执行与UNKNOWN对账，完整V0.2继续推进。

## 2026-09-10 联系对象核验后端

`53501e9`独立审核GO；普通服务接本人最新保存稿→固定原文作者/帖子/评论→本人设备/连接身份，保留公开账号ID与连接UUID的区别。入口、14项实际HTTP/PG证据和原失败集中在[本批记录](superpowers/plans/2026-09-10-outreach-context.md#本批验证)。此处是后端对象解析，不是渠道权限检查或发送；Win客户端/真实渠道仍未验。Mac继续06B/07B真实确认执行主链路。

## 2026-09-10 人工草稿后端已接普通启动

`2d77f58` 已通过独立审核；现有Web提供本人评论/私信保存、原请求恢复及最新稿读取，迁移121和授权说明已接入。原失败、12项实际HTTP/受限PG及未改字节复用见[本批证据](superpowers/plans/2026-09-10-contact-draft-persistence.md#本批证据)。Win接入须同时维护编辑前驱requestId，详情见[07B合同](UI_SHORT_COACH_CONTRACT.md#07b-后端接入2026-09-10)；未触碰Win客户端或构包，不冒称已消费。Mac继续确认发送/回执链；保存不等于发送或完整产品可上线。

## 2026-09-10 Mac 接收 Win 已实测运行包来件

当前接收 `d9ebbb7`，生成器/库存生产字节保持 Win `e2b75ce`；Windows生成、搬迁和独立审核证据复用[Win单一记录](superpowers/plans/2026-09-10-win-portable-runtime.md#本批交付与验证2026-09-10-恢复后)，Mac未重构或重跑Windows。Mac同时进行的库存替代实现已保留在本地 `codex/v02-full-scope@431cd4a`，被该实机来件取代，不再合并或重复接续；原脏工作树未改动。

仅接入 `ebf03ec` 的宿主测试条件修正：Windows原测试仍执行，Mac拒绝路径/无输出用例实际通过；本机定向 **2 passed / 27 skipped**，跳过均不计为Windows成功。非作者 `portable_host_gate_review` 对 `d9ebbb7..ebf03ec` 规格/质量GO、无阻断，不触发重复产品验收。下一步Win保留客户Electron bootstrap/平台客户端，Mac接续06/07触达后端；当前普通运行时仍未装配触达确认服务，真实收发与完整Goal继续未完成。

## 2026-09-10 用户恢复：上一批 WIP 收口

用户明确要求完成未完成部分后提交 Gitee。本批已修复离线运行包两项失败、实际生成并搬迁复验同一 payload，回复持久层修复完成独立审核；源码版本、运行入口、定向证据及 PG 环境失败统一见[本批交付记录](superpowers/plans/2026-09-10-win-portable-runtime.md#本批交付与验证2026-09-10-恢复后)。接收并保留 `8f8da34` 的完整 V0.2 目标文档和回复修复；回复两文件字节一致，不重复修改。此记录为 Win 已恢复并完成本批的实际接收通知，Mac 本地未提交改动未触碰；客户 Electron bootstrap、真实平台收发和产品整体验收仍未完成，不把本批提交当产品上线。

## 2026-09-10 Mac 接收暂停前的回复持久层修复

`4c683ac`仅接收Win `96bb371`的回复存储及其PostgreSQL测试，未合入离线运行包。原代码权限失败已复现，修复后的定向验证和非作者独立审核通过，证据集中在[回复QA](qa/V02_REPLY_PERSISTENCE_CONTRACT.md#mac-接收-win-回复修复2026-09-10)。08仍IN_PROGRESS，未验证真实回复回流；接续客户启动、平台/发送及客户端闭环，不重跑本批无变化字节的验证。

## 2026-09-10 最新接续：同步 main 并恢复完整 V0.2

用户最新要求“同步最新代码，看下现在目标，我还是希望按照原来规划的V0.2目标全量推进”。已读取远端 `main@03f2705` 及暂停来件 `codex/win-collection-flow@96bb371`；本次在隔离 `codex/v02-full-scope` 分支统一权威、产品计划、版本映射与任务入口，当前为 `V02_FULL_SCOPE_ACTIVE`，以[产品计划第1.0节](V02_COMMERCIAL_RELEASE_PLAN.md#10-当前执行完整-v02-全量推进2026-09-10)为准。精简版只保留历史，阶段试用不关闭完整 Goal。

本轮只同步目标与接续边界，不将 Win 在途运行包/回复修复合入 main，也不改动 Mac 原 `codex/launch-resume` 脏工作树。接续顺序与职责见[任务书顶部](V02_IMPLEMENTATION_TASKBOOK.md#当前执行范围完整-v02-全量推进2026-09-10)；原失败、未审和真实来源/Windows/部署缺口仍有效。Mac 已恢复本任务工作，Win 是否运行与接收须独立确认。本次重新读取 Mac 当前任务 Goal，完整目标文字保持，状态已为 `active`；此前 `paused` 是本轮较早快照，不代表当前仍暂停。

本批纯文档验证：8份变更文档、17处新增/修改本地链接及锚点检查通过，`git diff --check`通过，变更文档凭据扫描无命中；不重跑产品全量测试或构包。全仓现有凭据扫描仍命中未改动的MediaCrawler补丁3处字段引用（已在`03f2705`存在，并非凭据值），不将全仓扫描记为通过。

独立非作者 `full_scope_review` 对 `03f2705..e50f3da` 范围/架构一致性审核 PASS，Critical/Important/Minor均0；独立复核17处链接锚点及差量格式通过。本行仅登记该结论，不扩大到Win WIP、真实平台或产品上线。

## 历史：2026-09-10 用户要求阶段暂停（后被上述决定恢复）

因额度停止开发、实验和构包。main 仅接收五个启动命令的 `-B` 兼容小差量；离线运行包与回复修复完整保存在现有 `codex/win-collection-flow`，未验部分不合入主干。已知失败、测试归属及恢复顺序见[暂停交接](handoffs/WIN_PAUSED_20260910.md)。等待用户明确恢复，不把 Goal 标为完成。

## 2026-09-10 Win 独立接管后的 XHS 采集接线

基线 `135212a` 的一次搜索已接入同浏览器账号核验、私有 worker、原文批次上传、签名 FINISH 和现有任务页状态/恢复；已有 CLAIM 不自动重采。入口、配置、定向证据与未验边界集中于[本批记录](superpowers/plans/2026-09-10-win-collection-flow.md#本批交付与验证)。Mac 停止不再等待 ACK；Win 下一步接客户 bootstrap、真实 XHS 与 Windows 验收。当前仅开发配置可用，未完成真实平台、客户安装包或首发，Goal 继续。

## 2026-09-10 Win 候选实际 HTTP/PG 接收

基线`ca1f28a`，现P07产品service→主进程固定ServiceClient→socket HTTP→受限PostgreSQL实际通过：原文/逐字引用、显式分析、人工来源核验、INCLUDE丢回执原请求恢复、防重、P11固定原文和三类时间、跨用户/退出拒绝、来源/画像版本失效。根3案例实际PG通过，20文件613相关回归、类型/生产TEST排除通过；独立规格及代码/架构/质量PASS。Mac原`sourceVerificationId`修复已取得Win实际消费ACK，详见[Task5 QA](qa/V02-05G_CANDIDATE_CLIENT_WIN_REVIEW.md#task5-windows-实际客户端-http-与-postgresql-接收)。平台/模型输入合成，不代表真实获客或上线；Win继续设备HTTP/来源worker，05G父卡及Goal保持IN_PROGRESS。

## 2026-09-10 Win P07 原文证据与人工闭环

Win在既有P07完成原文/父上下文/来源时间版本、四维判断逐字引用、显式判断、人工来源核验、固定核验ID的确认入库及筛选外原请求恢复。产品写入口已安装，不自动模型调用或发送。独立SPEC与代码/质量复审PASS，根20文件612项通过；Windows Edge双视口为TEST隔离界面验证，非真实服务/客户验收。详见[05G QA](qa/V02-05G_CANDIDATE_CLIENT_WIN_REVIEW.md#task4-p07-原文证据与完整人工流程)。Win继续Task5真实Node→HTTP→PG，不重复Mac后端/设备/回复工作；05G和Goal仍IN_PROGRESS。
2026-09-10 05A 退出保护增量 b8b8236：原生验证确认已保存本机资料在退出时被遗漏，现统一覆盖资料、画像改动、联系备注、评论/私信改动与保留的跟进稿，原任务保护保留。独立审核发现的跟进恢复初始值误报已关闭；82文件1015项UI、类型、构包/严格smoke通过。Mac实际走通仅资料草稿→CmdQ继续编辑→原文保留→切工作台再次提示→明确放弃退出→同包重启空资料；新包ASAR f2cd0342，详见[本轮验收](qa/ui-session-content/README.md)。不把退出提示当持久保存/真实同步，Windows及其余真实服务/页面状态继续分项待验。

2026-09-10 05A 原生资料交互：9d1825b/9b137fc 修复叠层确认的模态声明与初始焦点，最终集成 f20b404 保留 d6d9ff5 来件。1309 项 UI及候选定向、类型、Mac构包与严格smoke通过；新包 ASAR 04c0645e / ZIP f5b15bf9。原生实际完成文件导入、取消保留、保存本机稿、放弃编辑及原文恢复；最上层确认无需Tab即在AX可达，布局未变。中间候选未关闭缺陷的记录完整保留，见[本轮验收](qa/ui-native-files/README.md)。本机草稿不冒充客户同步或原生文件导出；后者、Windows和其余状态仍待验，05A继续IN_PROGRESS。

## 2026-09-10 Mac 增量复核（执行签名与回复持久层）

本轮在 `codex/mac-device-authorization` 工作树对已实现的执行签名准备接口、触达确认快照和回复/跟进事件持久层重新执行定向回归：

- `tests/test_execution_api.py`、`tests/test_execution_contract.py`、`tests/test_execution_signing_payload.py`、`tests/test_pilot_runtime.py`、`tests/test_outreach_contract.py`、`tests/test_outreach_store.py`、`tests/test_reply_contract.py`、`tests/test_reply_store.py`：**101 passed**。
- `tests/test_execution_signing_payload_http_postgres.py`：**11 skipped**，原因是本轮未提供该测试所需的专用 PostgreSQL/身份环境；跳过不计为真实 HTTP/数据库闭环证据。

本轮未改变产品边界，也未接入真实平台采集、发送或回复回流；V02-06/07/08、Windows 交付、生产部署和客户 UAT 仍保持 `IN_PROGRESS`。

同日全仓 `bash scripts/check.sh` 新鲜结果为 **2108 passed / 485 skipped**；该结果是代码回归门禁，不替代真实平台、生产或客户证据。

同日重新执行 `scripts/secret_scan.sh` 返回 `secret-scan: clean`；使用仓外 0600 临时运行环境、仓外口令文件、PostgreSQL URL、digest 固定镜像和禁用开发登录执行 `scripts/cp06_validate_env.sh`，返回 `cp06-preflight: pass`。默认空环境的预检仍按预期拒绝；两者均不代表已部署或完成备份恢复演练。

桌面端 `npm test` 新鲜回归结果：**118 个测试文件通过、3 个跳过；1701 passed / 26 skipped**。该结果覆盖当前 Win/Mac 共享客户端代码，但不替代 Windows 实机安装、真实平台连接或客户 UAT。

本轮发现并修复迁移注册缺口：`pilot/db.py` 原遗漏已有的 `110_v02_search_suggestions.sql`，导致全量新库未创建搜索建议表；新增 `v02-search-suggestions` 注册并以身份/搜索建议定向回归 **37 passed** 验证。该修复只补齐新库初始化顺序，不代表搜索建议真实模型服务已接通。

修复后的新库初始化复核：管理员迁移重新执行成功，全部 `deploy/grant_*.sql` 在受限应用角色下执行成功（`grants-all-pass`），并确认 `pilot_search_suggestion_requests`、`pilot_outreach_confirmations`、`pilot_reply_events` 三张表均存在。该环境为本地合成库，不代表生产部署或真实平台能力。

随后清理并重建测试专属 `win_search_suggestion` 数据库（不复用预置应用角色），由 `tests/test_search_suggestions_postgres.py` 自行创建受限角色并执行：**63 passed**。这是搜索建议真实 PostgreSQL 事务/RLS/幂等套件证据，不代表模型服务或平台采集已接通。

迁移注册修复后的全仓回归：`bash scripts/check.sh` **2109 passed / 485 skipped**；相比修复前新增 1 项迁移注册回归测试，其余跳过边界不变。

MediaCrawler 受控获取已验证固定 commit 和补丁链；打包门禁规则对无凭据的 `.env.example` 模板已放行、对真实 `.env*` 仍拒绝，专项 `tests/test_vendor_packaging.py` **14 passed**。后续 clean bundle 仍需非浅克隆输入（本轮浅克隆在本地对象传递阶段失败），未计为可发布采集包。

随后使用完整非浅克隆的固定 `439509782cc2991c8ef7648e178d5847b0545798` 生成 `/private/tmp/yike-mediacrawler-full.bundle`，打包 manifest 校验通过；再由该 bundle 安装独立运行目录，commit、补丁/依赖安装及 `git diff --check` 通过。该 bundle 尚未绑定真实平台账号或执行采集，不写成采集成功证据。

从 bundle 安装目录执行 `cd runtime && .venv/bin/python main.py --help` 成功加载 CLI，入口列出 `xhs/dy/bili/zhihu` 等平台；直接在其他 cwd 启动会因上游相对资源路径失败，已核对 `app/collector.py` 将受控子进程 `cwd` 固定为 runtime 目录。该项只证明运行时可启动，不证明账号登录或真实采集。

本轮修复 `fetch_mediacrawler.sh` 的浅克隆问题：bundle 需要完整历史传递固定 commit，脚本改为完整 clone；新增回归与 vendor packaging 合计 **15 passed**。仍不包含真实账号登录或平台采集证据。

修复后重新执行完整 clone → bundle → bundle 安装链：bundle manifest、依赖/Playwright 安装、固定 commit `4395097…` 和安装目录 `git diff --check` 全部通过。采集运行时已具备可交付的受控安装包，但尚未进行账号登录和真实平台采集。

2026-09-10 05A 可见验收补齐：`8af8eaf`收紧P04空态，本机资料与带入操作完整进入1280×720首屏；实际走通P06平台/设备往返、P09原标签与平台返回、P14无人工记录的匹配回复/已读/首次人工登记。新Mac包ASAR `98debe8e` / ZIP `f580c225` 已实际冷启动、取消关闭继续编辑、保存75搜贝会话草稿、明确退出并同目录重启；退出清除会话稿符合提示。定向33项/类型/构包/严格smoke通过，先前全量1340/23仍绑定d816，不追认重跑。证据及截图校准过程见[当前可见验收](qa/ui-visible-local-handoff/README.md)。05A仍IN_PROGRESS；原生选择器、剩余状态、真实后台及Windows分项接续。

2026-09-10 05A 本机资料与返回流程已收口：P04 `d66d487` 保留首画像保存前的本机资料，并支持人工带入/取消/重复复用目标；P06/P09/P16/P18 `315d590` 保留原任务、步骤、标签和平台。正常合入 `bbe2e20` 为 **fcae33e**，接收固定原文展示与执行签名准备，双方字节保留并独立兼容复核通过。旧超时测试计时起点修正为 **d816a9d**，产品未变；最终桌面 **1340 passed / 23 skipped**、类型、隔离 Mac 构包与严格 smoke 通过，原失败保留。包 ASAR `6ef0d95e` / ZIP `5ff63633` 绑定 fcae33e，详见[本批验收](qa/ui-local-handoff/README.md)。本片独立代码工作已完成；用户再次“继续”后 Mac 已恢复可操作，接续同状态视觉与原生生命周期，Windows/真实服务继续分项待验，05A 不标 DONE。

2026-09-10 Mac原确认回执补齐候选`9d9e965`（base `7b640c9`）：仅新决策返回原来源核验ID，旧持久回执不回填；不新增SQL/授权，不改Win客户端。root101项相关实际HTTP/受限PG与46项纯边界分别通过；完整`7b640c9..9d81665`独立规格/代码/架构/质量PASS、0项发现，[本次QA](qa/V02_CANDIDATE_ASSESSMENT_REVIEW.md#05g原确认回执补齐2026-09-10)保留RED、测试修正及各自验证归属。实际Win消费、来源/发送/上线未验。Mac下一处接设备登记未知恢复最小合同；首发仍按已批准端到端及三个亮点推进，高级管理/复杂统计/重复全量测试后排，基础隔离/确认防重/恢复不后排。

2026-09-10 设备登记恢复切片已完成并同步 `a6f68dd7`，文档状态记录提交 `c13df71`：新客户端可保存原 `request_id`，超时后恢复原设备回执，并读取当前 owner-scoped 公钥/版本/撤销状态；116 迁移启用强制 RLS，登记表只允许受限 SELECT/INSERT。严格输入、幂等冲突、同事务回滚、会话重验及旧接口兼容均有测试证据。该工程底座不等同于平台连接、真实采集、发送或 Windows/UAT 完成；下一步仍为真实来源/机会证据与确认收发主链路。

2026-09-10 最新候选`cfaf4fd`正常保留远端`c88b64b`固定原文展示及`a08751d`回复入口，与本轮执行签名准备兼容，独立复核**PASS，0项未关闭发现**。root实际176项客户端定向/类型检查及Node→HTTP→受限PG1项通过，不与此前80/69/15或Win372/1253相加；[本轮QA](qa/V02_EXECUTION_SIGNING_PAYLOAD.md)保留两次来件、原失败和精确验收范围。双方产品字节未覆盖。后续优先设备/真实来源/候选与确认收发闭环，原文亮点已接展示但不等于实际平台或客户验收，完整Goal继续。

2026-09-10 执行签名准备增量`eb507bf..9fc197c`独立最终规格/代码/架构/质量**PASS，0项未关闭发现**；原Minor测试干扰已修正，产品源码仍为`7d8f657`。详见[完整QA](qa/V02_EXECUTION_SIGNING_PAYLOAD.md)。后续仅登记审核与推送事实；Win继续主进程签名/来源/原文详情消费，Mac不代签ACK。下面“独立审核待收口”为原候选时点，整体产品门槛不关闭。

2026-09-10 CodexiMac执行签名字节候选`7d8f657`：普通认证客户端可取得设备/会话绑定原文，准备不执行也不新增事实。69项HTTP/规范及15项实际HTTP/受限PG分别通过，独立审核待收口；[字段合同](contracts/V02_EXECUTION_RUNTIME.md#05f待签名原文接续)和[QA](qa/V02_EXECUTION_SIGNING_PAYLOAD.md)已供Win接续05F。未改桌面/SQL，不替Win确认设备HTTP、候选上传或真实来源消费；默认START来源能力仍关闭，完整Goal继续。以下“下一步执行签名字节”保留为历史时点，后续优先实际来源/客户端和确认联系/回复。

2026-09-10 05A 最新增量 **4eb1bb8**：工作台待办按客户空间/版本隔离，模板保留人工搜贝及执行上限，P14 可直接选择商机查看回复且不依赖人工登记，P15 保存/取消保留目标。独立发现的迟到列表覆盖日期 P2 已修，最终限定代码/架构审核通过；桌面 **1253 passed / 22 skipped**、类型、Mac 构包及严格 smoke 通过。正常合入 `eb507bf` 为 `ffd7d80`，保留后台普通运行与签名接续认领。新包 ASAR `72b59770` / ZIP `c203b93e` 单独绑定；Mac 锁屏，新增选择器和当前包的可见验收未执行。见[本批记录](qa/ui-reply-entry/README.md)。旧“无人工记录回复入口 P2”源码缺口已关闭，其可见验收继续；05A/Goal、真实服务与 Windows 不标完成。

2026-09-10 05A 提交前正常合入 Win `ff623ed` 为 **16a9a3f**，保留其设备持钥/签名独立模块及下一片原文证据认领。新集成桌面全量 **104 文件通过 / 1 文件跳过，1206 passed / 22 skipped**；[本批验收](qa/ui-state-recovery/README.md)记录两轮不同候选，不累加。新增持钥模块尚未被产品入口导入，新包仍绑定 f18 的既有运行路径，不声称已经接通设备签名；下段 c88/1121 是先前通过的原候选。

2026-09-10 05A 状态恢复增量：资料操作按客户空间及版本隔离，评论/私信分别保护未保存内容，跟进登记支持取消、纠正与撤销后保留历史，未知结果按原请求恢复且防止确认成功后重复登记。最终产品源码为 **f18a922**，正常保留后端主线 `a9d18db` 为 `07d4b85`；测试等待修正后冻结 **c88c9e2**，产品字节不变。最终桌面 **101 文件通过 / 1 文件跳过，1121 passed / 22 skipped**，类型、Mac 构包、严格 smoke 和生产 TEST 排除通过。新包 ASAR `79a52de9` / ZIP `75d4f8b2` 已实际冷启动并核对任务平台状态；后续输入/退出/重启因 Mac 锁屏未完成，不借旧包证明。逐版本失败、修复及独立审核见[本批验收](qa/ui-state-recovery/README.md)。05A 与 Goal 继续：余下同状态视觉/交互、无人工跟进记录时的匹配回复入口 P2、真实服务与 Windows 实机分别验收；四个 raw 辅助草稿仍未纳入。

更新时间：2026-09-10。产品集成目标：`yike-ai2026/main`，不再使用 `codex/customer-pilot` 作为主干。小范围串行改动直接在 `main` 验证、审核和提交，较大或并行工作使用短期分支后合并清理；文档仓库分工见[仓库工作流](REPOSITORY_WORKFLOW.md)。

## 整合记录

2026-09-10 最终合并候选 **`a8f895a`** 已正常保留远端`27ed499`的基础体验恢复；独立代码/架构兼容性审核**PASS，0新增问题**。root12文件223项、类型检查及凭据扫描通过，双方源码未覆盖；[收口QA](qa/V02_NORMAL_RUNTIME_COMPOSITION.md)保留误报失败、修正、审核归属与范围。客户端实际来源、执行签名字节接续及真实收发仍是下一步，已知UI P2/完整Goal/生产门禁不因此关闭。

2026-09-10 正常运行增量终审收口：`a9d18db..d100cdf`独立复审**PASS，原容器缺规则P1已关闭，0项未解决发现**。普通启动、实际HTTP/受限PG和隔离镜像文件布局的证据分别记录于[QA](qa/V02_NORMAL_RUNTIME_COMPOSITION.md)，不合计为全仓/生产结果。正常保留Win设备签名来件`ff623ed`为`6b5e7e4`，双方源码完整保留，Mac97项定向与类型检查通过；来件独立兼容性复核另记。下一片Mac接执行签名字节入口、Win接固定原文详情及设备/真实来源，完整Goal保持ACTIVE。下段“独立审核待收口”为历史时点；真实来源、短信、收发及客户试用仍未验收。

2026-09-10 CodexiMac正常入口候选`bc6a5b6`＋真实HTTP验收`2e28526`，正常合入Win签名客户端交接`a9d18db`为`fad2d24`，无代码冲突。普通`yike-pilot-web`现装配策略/执行历史/原始候选/复核；配置真实兼容模型后可调用已有ASSESS，实际效果另验。262定向、9真实受限PG与本地provider的HTTP检查通过，独立审核待收口；证据类型/失败历史见[本片QA](qa/V02_NORMAL_RUNTIME_COMPOSITION.md)，部署见[契约](contracts/V02_NORMAL_RUNTIME_COMPOSITION.md)。源码之外尚缺真实来源policy/worker、正常短信、建议服务、客户端与收发/客户验收，默认能力保持关闭。下段CLI缺口是旧时点，不再据它重复实现本片；下一步Mac补Win已明确请求的执行签名字节入口，Win继续05F和实际来源，不把本片当产品上线。

2026-09-10 CodexiMac固定原文证据候选：`26502ee`与根HTTP断言`9c71e3b`，正常合入`4251e75`为`a128044`；双方源码完整保留。115仅在首次人工纳入原事务保存公开来源/当前同版本观察/逐字引用，详情按租户共享，私有画像和历史不共享，重复不替换。105相关、69HTTP/UI、合并后196合同/HTTP及75客户端定向/类型通过，结果不相加；见[本片QA](qa/V02_OPPORTUNITY_SOURCE_EVIDENCE.md)和[Win消费合同](contracts/V02_OPPORTUNITY_SOURCE_EVIDENCE.md)。完整自有增量`4251e75..2c216d0`独立代码/架构/质量终审PASS、0项发现；05G展示/真实平台/收发/Windows/客户验收未完成。正常CLI尚未装配新服务，下一步优先真实运行入口和客户端来源链，不能以测试组合代替普通用户启动。115归Mac、108/110归Win，既有迁移不改；下面记录保留原始时点。

2026-09-10 05A主干合并更新：正常保留远端aac3fe9（含3898c3e画像版本与确认账号修正）形成**4eca41301e599a431e06808d2b717926a094bbb5**，精确独立集成复核PASS。新快照88文件964passed/21skipped、typecheck、Mac构包与严格smoke通过；285受控输入/39构建文件及ZIP内ASAR完成绑定。新包ASAR d7f2d2c0/ZIP c5fdf73d的实际可见冷启动、任务表单与平台连接只读路由已核验，完整草稿退出链仍仅引用旧aec0证据。详见[最新整合验收](qa/ui-reviewed-integration/README.md)。旧944和3ecd29b保留历史；05A与完整Goal继续，未完成原生选择器、全部视觉/状态、真实服务及Windows验收。

2026-09-10 CodexMac前端05A：已审e70c3a1整合并推送a31069f；实际冷启动暴露本地依赖循环链接及旧smoke漏报，修复8ddafab通过独立代码/架构审查、944项测试和最终aec0包实际退出/重启验收。正常合入远端168872a为3ecd29b，只有既有任务书/Win认领文档新增，desktop树与8dd完全相同。质量与证据边界见[最新整合验收](qa/ui-reviewed-integration/README.md)，旧失败和过渡包单独保留。05A仍推进剩余状态，真实04C/05G接口按原分工接收，不将raw辅助草稿计作功能，不宣称Windows/签名/上线完成。

2026-09-10 当前冻结组合 **3898c3e**：Mac策略只读reader0c14b33独立审核PASS，共享router/114登记f4e9b71通过实际策略→签名执行/上传→分析/人工纳入→当前/历史列表。原纳入后列表归零故障根代理复测1项通过；88相关、369纯边界、12实际HTTP、48全新PG分开记录于[组合验收](qa/V02_CONFIRMED_STRATEGY_COMPOSITION.md)。完整自有增量a31069f..3898c3e独立规格/代码/架构/质量终审PASS，0项发现；Mac限定接收实际策略后端，不是Win客户端ACK。正常保留a31069f前端为cda69fb，新增画像事实/确认账号两项接入缺陷已修复为3898c3e并独立复审PASS，107定向/类型检查通过。114已共享注册而默认能力仍关闭，110/实际来源/客户端/收发/Windows/UAT尚未完成；下一步共享机会固定原文证据与Win来源/消费，不重做模型或全套界面。以下认领及未注册描述保留较早时点。

2026-09-10 CodexiMac认领04B/04C真实组合接入：基于aba7f4f，已复现实际策略resolver使纳入后的候选列表错误归为空结果（列表内外连接争用同一会话锁）。按[两项接入计划](superpowers/plans/2026-09-10-confirmed-strategy-composition.md)新增只读同快照reader，保留写入resolve实时授权，再串行注册114及共享router并验证真实PG/签名链。此处只是认领/故障证据，不是修复完成；Win继续05C及来源/客户端，避免并改共享接线和reader。既有迁移不改、生产能力不开，原文证据/多找类似/短句联系仍为阶段亮点。

2026-09-10 CodexiMac04C最终工程候选 **c2b46ed**：独立终审发现的“无联系路径仍纳入”和“等锁后过期身份回放”两项P2已用真实PG反例修正、精确复审PASS。最终相关56项通过/45.12s/0skip，独立探针及同边界定向6项通过/9.02s；[完整QA](qa/V02_CANDIDATE_ASSESSMENT_REVIEW.md)保留所有失败。正常保留Win真实策略36fef5b为4d04cd1，两边业务源码均未改；Mac新策略合同/HTTP233项通过/1.38s，非真实PG接收。下一步Mac串行注册114/router、用真实resolver贯通执行与04C，随后共享原文证据投影和Win05G；110/114默认能力尚未启用，不代表来源/客户端/收发/上线已完成。下面旧“整片终审待完成”只保留为较早时点。

2026-09-10 CodexiMac04C工程切片已接通签名raw→版本化Skill分析→单独人工来源核验→复核入旧商机→原请求恢复。模型c372c3f与PG fe2be00均独立复核PASS，列表混合策略快照P2经原反例RED→GREEN关闭；HTTP接口88fafa9与最终集成测试5b08386通过8个真实HTTP/PG相关用例，provider为本地合成响应，不是实际商机/模型效果。详见[接口](contracts/V02_CANDIDATE_REVIEW.md)、[验收](qa/V02_CANDIDATE_ASSESSMENT_REVIEW.md)。整片终审待完成；正常合入Win4dc2142为6950cba，保留110搜索组件及114真实策略认领，本片源码未变。110未自动注册、不宣称Win消费ACK；首发原文证据仍待共享商机固定版本/观察/引用投影及05G实接。下一步贯通真实策略、来源与客户端，随后确认联系/回复，不继续扩高级管理；完整Goal继续，默认真实能力未启用。

2026-09-10 CodexWin交付04B真实确认策略工程片：合同`0678383`、HTTP`808f44b`、持久层/114 `eadcd2c`，独立规格及代码/架构/质量全部PASS。根代理233合同/HTTP与230合同/真实PG通过（重叠集合不相加），实际消费Mac签名START→CLAIM→候选入库，撤销后拒绝旧租约新上传且CANCEL可用；来源policy/内容为明确测试边界，非真实平台或整卡Win ACK。见[限定验收](qa/V02-04B_CONFIRMED_STRATEGIES_WIN_REVIEW.md)和[Mac共享接线](contracts/V02_CONFIRMED_RESEARCH_STRATEGIES.md#mac同事务接收)。114尚未注册默认入口，111/112/113和共享文件未改；Mac继续04C/接收，Win继续05C及实际来源/原文证据、多找类似、短句建联闭环，默认能力与整体Goal仍未完成。

2026-09-10 CodexWin正常合入Mac执行/候选及R4 `d6c75c7`为`093bd7d`，保留双方代码/认领，未把Mac在途04C当已完成。合并树Win PG98/0skip、模型/进程/纯请求239/0skip、桌面77文件864/2既有架构skip及typecheck通过，各集合不相加，见[限定整合记录](qa/V02-04B_SEARCH_BACKEND_WIN_REVIEW.md#正常合入mac主线后的检查2026-09-10)。按用户再次强调原文证据，补充[首发真实接入验收](handoffs/V1_WIN_FUNCTION_OWNERSHIP_20260909.md#原文证据接入补充2026-09-10)：逐字引用必须保留版本和主体，COMMENT原帖标题不证明评论者本人采购；Mac04C/Win05G分别补判断与呈现，不重做R4或抢改113。默认未接通能力、真实来源/Windows发行/收发/UAT及Mac实际ACK仍未完成，Goal继续。

2026-09-09 CodexWin继续交付04B组件：持久请求/110/grant `32c70dd`（98相关通过，含63真实PG）、Windows模型调用进程 `a8707a8`（独立17通过），均已独立规格及代码/架构/质量审核，关闭竞争与成员角色超权反例已修正；根代理整合239通过。见[组件交接](handoffs/V02-04B_SEARCH_BACKEND_COMPONENTS_WIN_TO_MAC.md)与[限定验收](qa/V02-04B_SEARCH_BACKEND_WIN_REVIEW.md)。已保留Mac `639b17d`的111执行认领；Win110尚未注册共享入口，队列/router/外发授权/05C与确认策略仍继续，默认能力未启用，不表示客户可用或Mac已ACK。

2026-09-09 CodexiMac原始候选切片 **07431ca**：cf86c56实现签名入库/版本/观察/原复合键幂等及owner私有候选，9c49a50接四个认证上传/读取API，07431ca修复独立审核发现的并发计数/历史快照P2。最终规格/代码/架构/质量PASS；最终57专项及根代理5个真实HTTP/并发复现通过，先前316/211按原提交保留不累加。[原始候选接口](contracts/V02_RAW_CANDIDATE_INBOX.md)、[测试/失败与修正](qa/V02_CANDIDATE_INGESTION_REVIEW.md)可供Win消费。112是新迁移，未改111；无需重做桌面页面。raw状态始终UNVERIFIED，下一步Mac04C/真实策略与Win实际来源/05G接入；默认生产能力仍关闭，未取得Win ACK、真实来源、判断、收发或客户验收。下段“没有候选上传”是前次执行切片时点边界，不代表当前代码仍缺此API。

2026-09-09 CodexiMac执行服务切片：核心 **990ebca**、HTTP **25d393b**，与最新R4主线9291963正常合并为 **e5b4bcc**。新增真实持久任务/逐平台租约/取消/原请求查询以及供02B同事务消费的提交护栏，独立规格/代码/架构/质量限定PASS；核心60、受影响415定向通过且0跳过，集合不相加。[验收与失败历史](qa/V02_EXECUTION_RUNTIME_REVIEW.md)、[Win/02B接入契约](contracts/V02_EXECUTION_RUNTIME.md)可直接接续。后端与25d、桌面与R4主线字节相同，复用已有845/21桌面证据而非重复全套。没有真实确认策略resolver、worker或候选上传，生产task_execution保持关闭。下一步Mac02B→04C→收发闭环，Win04A/B→05B/C与实际来源；没有把整卡或市场验证标完成。

2026-09-09 R4 最新整合候选 **14aa73ea32a417a067b558b61f692a56fa8ba06b**：正常合入手机号登录/Win 搜索主线639b17d，保留两侧进度记录；R4视图与CBC一致。此精确候选桌面77文件845passed/21条件skip，typecheck、Mac重构包、ASAR冒烟和生产TEST排除全通过，见[R4整合证据](qa/ui-r4/README.md#最新主线合入与再验证)。旧CBC包及日志保留，不覆盖为新结果。仅通过前端及Mac隔离验收，服务、发行、Windows及完整Goal边界不变。

2026-09-09 R4 前端候选 **`cbc61703347c407413f8a732a6ca9a5637258eba`**：六组增量已按授权实现，包括 P02 机会简报、P06 研究任务配置（联动 P19/P20）、P09 搜索覆盖与补查、P10 需求分类、P11 同来源证据时间线与多找类似、P12 短句教练和联系准备；保留 R3 其余页面与既有服务路径。研究用量统一显示“预计 / 最多 / 实际搜贝”，未知不填零，未定义兑换比例、售价或余额。主体 `676970c` 正常合入远端 `2ce6f8a` 为 `190683c`，保留 V1 版本分期、第 7 节交付顺序和手机号登录登记；`cbc6170` 仅追加只读公开样例的短句文案对齐。具体实现、独立审核和原始日志见 [R4 验收记录](qa/ui-r4/README.md)，设计对照与视口证据见 [设计验收](../design-qa.md)。

本轮实际验证分开记录：`190683c` 桌面全量 **76 文件 / 829 passed / 21 平台或架构条件 skipped**；`cbc6170` 文案差量 **3 文件 / 56 passed**，不相加，也不将前一候选的全量记为后一候选重跑。最终 Mac `make:mac`、ASAR 包内冒烟及生产包排除 TEST 夹具检查通过。新界面已实现可选服务可用时的状态转换、绑定校验和失败 / 未知恢复；默认未接通的研究用量、覆盖 / 调整、研究集合 / 时间线 / 类似建议、短句教练和机会简报服务仍准确显示不可用。隔离 TEST 场景不证明真实平台、计量扣费或业务结果；本候选 Windows 实机、真实收费与平台整链仍未验收，完整 Goal 保持进行中，原 M3 / CP-06 和下述备份认证阻断保留。

2026-09-09 CodexWin搜索建议模型切片 `e26c7a3`：有原文依据的跨行业建议、严格返回验证与单次模型适配已完成，独立规格及代码/架构/质量PASS，根代理187专项通过/0跳过，见[限定验收](qa/V02-04B_SEARCH_MODEL_WIN_REVIEW.md)。Win继续110请求持久层及原回执恢复，不与Mac认证/执行/候选重复；共享入口仍由Mac串行接收。外发授权、调用总时限、真实模型效果和05C端到端尚未验收，默认能力未启用，04B及整体Goal不关闭。

2026-09-09 CodexWin后续限定接收：`2ce6f8a`中连接版本后端与Mac `a8a36fe`字节一致；独立Win PostgreSQL专项68通过/0跳过，真实Node24.19→HTTP→受限PG往返通过，新增消费反例独立审核PASS，见[Win接收](qa/V02-01C_CONNECTION_WIN_REVIEW.md)。此更新取代下方历史“Win CV ACK未完成”，只解锁该后端契约，不是平台连接、完整执行授权或desktop接入完成。Win已开工04B画像搜索建议模型，110登记给后续建议请求/配额，108/109与Mac共享入口边界保留；唯一状态和实际代码证据仍在任务书。

2026-09-09最新正常登录工程切片：`9556fab`手机号认证＋`f36ec97`HTTP/桌面服务接入，保留Win映射主线`2ce6f8a`正常合并为`99bb62d`，修正旧异步测试与登录错误提示至 **fe78c9e**。独立规格/代码/架构/质量通过；后端f36全量1092通过/0跳过，合并后受影响497定向通过，最终桌面646通过/21既有条件跳过、类型/构建通过。失败历史、两个非阻断P3及证据版本见[01D交接](handoffs/V02-01D_PHONE_LOGIN_MAC_TO_WIN.md)。生产短信入口仍关闭，缺供应商/真实收码/激活及Win ACK；不表示普通手机号登录已面向客户发布。Mac本轮另对Win原始COMMENT映射`78116d9`完成限定源码/定向验证ACK，不当作真实采集；唯一任务书已记录。下一步Mac推进01C/03A执行与02B候选入库，Win继续04A/B→05B/C；短信供应商接入条件单独跟进，不因它等待而停下其他链路。

后续同步：正常合并Win主线6780582至b720c98，仅新增手册分期、Win功能交接及台账调整，产品代码与已全量验证458dd81相同。CodexiMac已实际接收04A/B→05B/C由Win纵向交付的分工，不重复实现；共享入口串行集成及108迁移预留在唯一任务书登记。下段原“优先04A/B”由Win主实现、Mac接收，而不是Mac再另开一份。无真实接口ACK或上线状态升级。

2026-09-09 CodexiMac历史冻结集成候选 **458dd81863604c7962dc5bdc5dc2634f24bd1032**：连接版本107与历史操作回执a8a36fe、进程停止确认/Node冷启动夹具修复af0faf6已正常整合；保留主线448e88a的R4继续开发/搜贝修改授权、产品手册及Win限定ACK。独立最终代码/架构/质量PASS；本机串行后端1037通过/0跳过，桌面630通过/21既有条件跳过、typecheck与renderer build通过；d49的原两项失败及修复过程见[本轮验收](qa/V02-01C_CONNECTION_VERSIONS_REVIEW.md)，不回填为旧版通过。此处为锁定候选证据，实际远端同步以Git核对为准。

按用户最新要求，任务书第2节改为“正常建档/策略确认→客户端真实机会→确认联系/回复→阶段试用”的纵向交付；证据卡、固定多找类似和短句建联提前，高级管理/统计/自动更新后排。保留全行业配置、完整V1.0与M3/CP-06/14天目标、已授权R3/R4，不把阶段试用冒充正式商用。下一主线优先04A/B真实输入、01D正常登录与03A/02B最小执行接入，06A收发路径核验并行；不继续为高级基础设施延迟用户闭环。Win CV ACK、真实平台、Windows交付及生产/UAT仍未完成，以下备份认证P1不因分阶段而豁免。

2026-09-09发行阻断补充：Win复核独立确认既有备份脚本HMAC误用密钥文件路径字面值的P1，未修复；[手册](CUSTOMER_PILOT_RUNBOOK.md)已标注禁止以该侧车放行CP-06，合成复现见[Win复核第12节](qa/WIN_CROSS_REVIEW_20260909.md)。不影响下面版本绑定的UI/持钥切片接收结论，但产品发布审核不通过，需优先修复并重新演练。

2026-09-09后续：CodexWin正常保留Mac最新前端9e27723并合入 **4454a45**，独立增量/合入审核PASS；干净4454a45 Windows全链61文件647 passed/2架构skipped、9自动阶段通过，真实新ASAR及安装包摘要见[Win复核第10节](qa/WIN_CROSS_REVIEW_20260909.md)。同版本后端代码仍为已测65d，未重复报全量。原始Mac视觉/日志保留；该历史时点 R4 尚为未确认提案，当前授权与实现以上方 R4 记录为准。候选/断连真实后台、人工安装更新及17 high/未签名等发行门禁仍未完成，不把新UI或构包通过写成产品上线。

2026-09-09后续：CodexWin实际接收65d8676中的设备持钥后端子链，Windows PG定向123通过、真实Node/HTTP/受限PG往返通过，全仓908通过/54既有Windows失败；独立代码/集成审核后正常合入f925560，保留Mac代码与Win84c4b6f。Windows干净84c完整自动构建570通过/2架构跳过，9阶段通过，人工与供应链门禁仍未完成。契约两处文案勘误、受限ACK与原始报告摘要见[Win复核第8/9节](qa/WIN_CROSS_REVIEW_20260909.md)，父01C/09仍IN_PROGRESS。

以下Mac段落保留65d8676当时状态，其中“Win ACK未完成”已由上方后续实际限定接收取代；Mac与Win各自的全量结果分开解释。

2026-09-09 CodexiMac持钥后端子链已审并纳入main `65d867640ea216769adb5f947f5dea8fb7b31a35`：代码c3702c0实现设备owner、公钥绑定/一次性持钥检查/双钥轮换、持久回执、会话撤销事务锁与106最小权限升级。整分支7e4ab7c独立审核PASS；推送前发现并保留Win主线3c16fac，合并65d8676再获独立复核PASS。合并版Mac完整后端962通过/0跳过，桌面549通过/21平台或架构条件跳过、typecheck/renderer构建通过；原925仅为合并前快照，不相加。锁定安装17 high和Windows未验收项保留。01C实际Win ACK、连接版本/执行租约/提交授权、02B上传、真实平台与上线/UAT仍未完成；详见[01C验收](qa/V02-01C_DEVICE_KEYS_REVIEW.md)及[交接](handoffs/V02-01C_DEVICE_KEYS_MAC_TO_WIN.md)。Goal保持ACTIVE，继续01C并衔接03A任务运行持久化和02B结果入库。

2026-09-09后续CodexWin交叉接收：02A原e4d1695虽定向通过，独立复核发现IDNA不同网站误合并/等价IPv6漏去重。更正d14594f独立实现/规格/质量审核PASS，Win221项定向通过后限定ACK并集成95285dd；仅DTO/来源纯契约，不代表01C授权或02B上传。随后正常保留远端0a3ccf7的全部Mac前端与交接到37592ed，Win新UI定向423项/typecheck通过，完整Windows构建仍另验。详情见[Win记录](qa/WIN_CROSS_REVIEW_20260909.md)，任务书为唯一现态。

最新前端补齐：`237a5b2`、`1c15673` 完成资料、跟进、任务恢复/模板、工作台队列和平台Logo。`3228962` 已正常合并最新远端身份/会话主线 `9077383`，没有覆盖其他任务。随后58622ef同步Win主线fe85b46，最终前端50文件493项通过、1项Windows专属回归跳过，合并后UI/身份/会话/解析器定向140项通过；新Mac包构建与启动记录见 [本轮交付](qa/ui-flow-completion/REVIEW.md)。可选后台接入、品牌完整大图验收及Windows仍分别列为未完成，不把主线合并等同上线。

2026-09-09 候选契约与双方代码交叉整合：main 已包含 `e4d1695749f037bcafa13f77e703544b67b25c09`，保留Win的 `fe85b46`（解析器提取、Node预检、01A/B实际限定ACK和Windows失败记录），加入Mac的02A候选/来源契约。最终代码、架构、质量及集成独立审核通过；Mac同版本后端877通过/0跳过，桌面362通过/1项Windows限定测试跳过，typecheck/renderer build通过。首次缺少vitest及锁定安装时17 high等提示、历次失败与修复均记录在[02A验收](qa/V02-02A_REVIEW.md)。02A本身尚无Win ACK，上传/执行授权/真实平台未完成；[交接](handoffs/V02-02A_MAC_TO_WIN.md)明确旧解析器行为不能直接当正式上传体。以下各段保留各自时点，不将旧未接收状态覆盖实际新ACK。

2026-09-09 CodexWin交叉接收：身份/会话撤销组合 `222119e` 经独立Windows PostgreSQL定向136项通过；事件名称文档P2在 `f42ea909` 更正并新增防漂移测试，独立复审18项通过后，正常集成到main `bea5c7d`。同时纳入测试时钟修复，保留最新43卡/已有Mac工作。Windows全仓在原组合为647通过/58个既有失败、0跳过，集成定向161通过，不声明全仓或产品完成。Win纯解析切片 `e368b5a`、双Node预检修复 `e01e99a` 已纳入；中文路径Squirrel打包失败修复继续。证据见[Win记录](qa/WIN_CROSS_REVIEW_20260909.md)，当前认领/ACK以任务书为准。

CodexiMac并行集成快照（2026-09-09，以下验证属Mac环境）：远端 main 已包含 `5d3373d9b7fa6cb74f0a9f6241bbb282e4db2514`，即独立审核通过的01A登记/遥测、01B会话撤销、104/105最小权限升级和V02-10E测试时钟修复。保留最新跨行业目标、细化任务卡与R3前端；该版本本轮后端705项（含专用PG、无跳过）、桌面362项及typecheck/build通过，独立合入复审PASS。该记录时点Win接口接收尚未发生；后续Win ACK以上方记录为准。设备认证、正常登录、真实平台、Windows发行和生产/UAT未完成；[组合验收](qa/IDENTITY_INTEGRATION_20260909.md)区分代码集成与接收ACK。以下为更早的历史整合快照。

2026-09-09 任务卡细化：按用户要求，将双 AI 任务板拆成43张可交付小卡并取消重复状态表，实际认领/状态/候选与集成SHA/ACK统一在实施任务书记录。收尾同步远端 main `30da93e`，保留并行 R3 触达/管理/原生导出成果及 V02-07 的 IN_PROGRESS 状态，新增09F承接生产管理服务。只读核验身份分支 `8553491270a37f9d2f180a8eb525e7a862c73cb6`、基线修复分支 `e577f4bfc7549fc10180a08e72b38768701242f3` 后，V02-01从 NOT_STARTED 更新为 IN_PROGRESS，登记01A/01B及10E候选和未接收边界；本次没有合并这两条分支或复跑其功能测试。原Mac前端工作保留，不把新卡创建当作已分配任务。具体状态以[实施任务书](V02_IMPLEMENTATION_TASKBOOK.md)为准。

2026-09-09 范围更新：按用户“首发就要面向所有行业企业”和“修改文档和目标后提交到main”的要求，同步当前产品定位、共同 Goal、双 AI 执行目标、行业策略及跨行业验收口径。本次仅改文档，不改业务代码，不重置实施任务书状态，不将已有展台研究、R3 设计或历史测试升级为跨行业能力证明。目标及验收以 [AUTHORITY](../AUTHORITY.md) 和[产品计划](V02_COMMERCIAL_RELEASE_PLAN.md)为准；本次文档可由 CodexWin 直接提交 main，后续功能分支和独立审核规则不变。

下表记录已经纳入的工作及其验证范围。分支会持续前进，当前 HEAD、远端一致性与工作树状态应在接续工作时实际检查，不以本文件代替 git 状态。

| 提交 | 内容 | 状态边界 |
|---|---|---|
| `9c092be` | 纳入 `skills/ai-project-lead-research-v1/` 版本化研究 Skill | 规则、证据、分级、去重和评测契约已入库；尚未接入实际平台连接器、调度器或模型运行入口 |
| `3c854b8` | 纳入 `desktop/` 安全 Electron 壳候选 | 已通过本地单测、类型检查和 renderer 构建；只证明桌面壳候选，不证明 sidecar、Windows 安装、平台采集或真实触达 |
| `d9f74a5` | 更新 V02 任务台账，记录桌面壳提交 | V02-04、V02-09 为 `IN_PROGRESS`，不是 `DONE` |
| `a9f4207` | 搜索条件建议设计 R2：P06/P19/P20 与交互约定 | 画像自动建议、可编辑词、人工修改保护和最终配置确认已进入设计；整套仍待用户确认，真实建议服务尚未实现 |
| `4d43244`（来源分支） | 固定版本采集组件的源码 bundle 打包和仓外安装脚本 | 合并脚本与测试，继续保持 V0.2/PG/R3 当前约定；没有打包真实上游源码，也不代表桌面执行器或平台采集已接通 |
| `10ab8b6`、`615e340` | R3 前端、桌面候选及绑定独立审核 | 已合并并推送 `main`；20 页可访问、Mac 候选可运行，不代表所有可用服务交互与真实平台能力已经完成 |
| `afc7e8b`（选择性移植） | 研究包整包事务、同键公开 URL 冲突检查、商机查询源信息与跟进状态字段 | 保留当前 `provision_tenant`/RLS 与 UI facade；旧 Jinja 页面、演示启动器和范围文档不覆盖当前 R3 |
| `554c1ed`、`e7c94a9`、`6f449e6`（并行主线提交） | 保留双 AI 协作任务板及其 V0.2 范围修正 | 协作建议不重置实施任务书进度、R3 前端开发或用户手动 Windows 验收安排 |
| `8011a30`、`a9f3078` | P01/P06/P17/P20 请求生命周期、P12/P13 队列与草稿核对、P18 管理交互及原生文件导出 | 桌面 362 项测试通过；最终 Mac 包启动、退出及重启已检查。真实管理/队列/发送后端和完整 20 页视觉验收仍待完成；证据见 [交互增量验收](qa/ui-interactions/REVIEW.md) |
| `676970c`、`190683c`、`cbc6170` | R4 六组前端、搜贝配置与确认、覆盖补查、研究证据和联系准备；保留并行 V1 / 手机登录主线 | 全量与差量测试、Mac 包证据分开绑定；[R4 验收](qa/ui-r4/README.md)记录可选服务与 TEST 边界，未完成 Windows / 真实平台 / 收费 / 整体 Goal |

整体 20 页沿用 [R3 精修基准](../design/v02-suite-r3/README.md)，当前六组增量见 [R4 设计及授权](../design/v02-suite-r4/README.md)。R3 整套及 R4 增量均已获得实现授权，旧 R2 图册保留；上表旧提交的“待确认”描述是当时状态，不覆盖当前授权。既有实现见 [R3 UI 实施记录](UI_R3_IMPLEMENTATION.md)，本轮实现与限制见 [R4 验收](qa/ui-r4/README.md)及[设计验收](../design-qa.md)，不要用设计图或文档替代业务功能验收。

## 既有验证记录

以下命令结果来自上述 Skill/桌面壳提交的对应环境；R2 设计检查另见 [图册验证记录](../design/v02-suite/VALIDATION.md)。

R3 候选 `10ab8b6` 的更新验证为桌面 216 passed、UI API/试用页 62 passed、隔离 PostgreSQL 接口 22 项通过及真实 macOS 运行；绑定审核见 [R3 实施审核](qa/ui-r3/IMPLEMENTATION_REVIEW.md)。这些结果只适用于相应提交及环境，Windows 实机、生产部署和未接通后端仍待验收。下面 2 passed 是桌面壳的历史记录。

- `uv run --frozen pytest -q tests/test_research_skill_contract.py`：2 passed
- `npm test -- --run`（`desktop/`）：2 passed
- `npm run typecheck`（`desktop/`）：通过
- `npm run build:renderer`（`desktop/`）：通过
- `bash scripts/secret_scan.sh`：clean
- `git diff --check`：通过

上述历史版本的完整 Python 回归有日期窗口相关失败；V02-10E 后续修复已随 `5d3373d` 合入，Mac同版本完整705项通过见开头快照，Windows实际结果为647通过/58个既有兼容失败。不能将历史日期失败解释为新版本仍有同一问题，也不能把新版通过回填成旧版当时已经通过；平台与版本的证据分别保留。

## 未整合内容及原因

- `codex/customer-demo-v01` 中仍有效的导入事务与商机查询修复已精确移植；旧 Jinja 界面、源码演示启动器、旧四页权威及其发布记录保留在历史分支，不作为当前 R3 客户端交付。不整支合并，也不删除另一 worktree 的分支。

- `codex/self-use-auto-public-reply-v1` 的自动公开回复、资格闭环和旧数据库迁移没有整批合并；它属于不同权威路线。需要时只能按 V0.2 的“确认后发送”契约选择性迁移并重新审核。
- 父仓库的 `output/`、截图、PDF、SQLite 和浏览器运行记录没有批量复制；其中可能包含临时事实或敏感数据。可将脱敏规则、反例和 fixture 逐项提炼到 Skill 评测目录。
- 旧 `codex/authorized-dual-platform-mvp` 是当前基线的祖先，没有额外本地提交需要合并。

2026-09-10 触达协议契约切片：CodexiMac 新增 `pilot/outreach_contract.py`、专项测试与 [V02_OUTREACH_CHANNELS](contracts/V02_OUTREACH_CHANNELS.md)，提交 `74e8ff6d997e92f88e01a6003b75a152ee03fdf6`，幂等冲突与内容摘要反例追加于后续提交。独立只读复核为 PASS WITH MINOR；专项测试 **9 passed**，compileall 与 diff check 通过。该切片冻结来源版本、平台公开收件人、连接版本、内容摘要、确认有效窗口、request_id 幂等模型及 UNKNOWN/PENDING/FAILED/SENT 失败关闭语义。`IdempotencyRegistry` 仍为进程内契约模型，尚未接 PostgreSQL；没有真实平台连接器、服务端发送路由、回执对账、回复回流或客户/UAT证据，V02-06/07继续 `IN_PROGRESS`，不得把本提交写成真实发送或产品上线。

2026-09-10 持久确认快照候选：在 `c32ddb6` 基线上新增 `pilot/outreach_store.py`、117 迁移、受限角色授权脚本和纯函数专项。绑定事务已加入来源 URL/平台/健康度、商机来源与 OPEN 状态、连接平台/CONNECTED 状态/连接版本重验；但尚无 PostgreSQL 并发/RLS/回滚实测，数据库也未建立到业务表的外键，不能视作生产授权。没有真实平台发送、回执对账、回复回流、Windows 或客户 UAT 证据，V02-06/07继续 `IN_PROGRESS`。

2026-09-10 事实重验增量已集成 `1d1d39c5d3a4b567324918215ea5cfbd687342dd`：确认绑定事务现在锁定并重查来源平台/公开 URL/健康度、商机来源与 OPEN 状态、连接平台/CONNECTED 状态/连接版本；缺失、关闭、阻断或版本变化均拒绝持久化。专项测试 **12 passed**。这仍是服务端防伪边界，不包含 PostgreSQL 实测、真实发送或回复回流。

2026-09-10 回复/跟进契约切片：新增 `pilot/reply_contract.py` 与专项测试，平台回复和人工跟进严格分型，绑定租户/用户/商机/来源/画像版本/原发送请求；明确 `UNKNOWN` 不得标已读、纠正/撤销只能追加、平台公开回复 ID 去重冲突拒绝。专项 **12 passed**，compileall/diff check 通过；[契约](contracts/V02_REPLY_FOLLOWUP.md)。当前仅 contract-only，未接 PostgreSQL 事件表、真实平台回流、已读同步或提醒，V02-08继续 `IN_PROGRESS`。

2026-09-10 回复事件持久层候选：新增 118 迁移、`pilot/reply_store.py`、受限授权脚本并注册迁移，支持平台回复先核对原触达确认快照，再做去重、同事件已读 revision、人工跟进隔离和不可变 RLS 表。回复/触达合跑 **32 passed**。本轮未执行 PostgreSQL 实例、并发/RLS/回滚或真实平台回流，服务仍需重验业务事实与纠正目标；V02-08继续 `IN_PROGRESS`，不可写成回复已同步或上线。

2026-09-10 Mac/Win 正常合并同步：Mac 分支先完成 `5c0065d` 合并，随后正常吸收远端 Win 候选审核客户端提交 `c4fdf01`（当前合并提交以本地 HEAD 为准），新增候选审核证据保留与恢复契约、客户端测试和 QA 记录。合并后桌面完整回归 **1337 passed / 26 skipped（113 files，3 skipped）**，Python 触达/回复合同与持久层 **32 passed**，`git diff --check` 通过。该证据仅覆盖本地代码回归，不代表 Windows 实机安装、真实平台采集/发送、生产部署或客户 UAT。

2026-09-10 CP-06 环境复核：`scripts/check.sh` 全量 **2108 passed / 485 skipped**，`scripts/secret_scan.sh` clean，MediaCrawler 打包/采集专项 **69 passed**。`scripts/cp06_validate_env.sh` 在当前工作区明确拒绝非 PostgreSQL 数据库 URL（`cp06-preflight: database URL must use PostgreSQL`）；当前没有可用 PostgreSQL 实例证据，因此 RLS、并发、回滚和生产部署门禁仍未完成，不能将本地回归升级为生产就绪。

2026-09-10 PostgreSQL 隔离夹具加固：使用本机一次性 PostgreSQL 容器，以 `NOSUPERUSER/NOBYPASSRLS` 独立应用角色重跑导入原子性与租户隔离集合，**11 passed**。修正测试授权覆盖新增机会证据表，并禁止隔离测试因沿用管理员 URL 而静默绕过 RLS。该结果证明测试夹具真实执行了受限角色路径，不代表生产数据库、备份恢复或真实客户 UAT 已完成。

2026-09-10 CP-06 配置预检正向验证：使用仓外临时 runtime env、仓外 0600 备份口令、禁用开发登录、digest 固定镜像和 PostgreSQL URL，`scripts/cp06_validate_env.sh` 返回 `cp06-preflight: pass`。该结果只证明配置门禁规则可被满足，不代表镜像已发布、服务已部署、备份恢复已实测或真实平台/客户验收完成。

2026-09-10 PostgreSQL 跨套件探针：在一次性数据库上为多个专项统一注入同一管理员/受限角色，运行连接、策略、建议、执行、导入、触达/回复套件，结果 **237 passed / 44 failed / 202 errors**。失败主体为各套件专属授权/角色初始化缺失（如 `pilot_users` 权限）及共享库状态假设，不能归因于统一业务回归；该混合结果不计入通过。后续必须按测试套件独立数据库、角色和 grants 重新执行，保留受限 PostgreSQL 11 项通过作为当前可靠证据。

2026-09-10 策略套件独立 PostgreSQL 验证：按 `tests/test_research_strategies_postgres.py` 自有初始化流程使用全新 `win_research_strategy` 数据库，由套件创建 `strategy_app` 受限角色，**49 passed**。这消除了统一探针中的角色预创建冲突，证明确认策略、版本、撤销、RLS、HTTP 和真实 Node 往返在该独立环境通过；仍不代表生产部署、真实模型效果或客户 UAT。

2026-09-10 搜索建议套件独立 PostgreSQL 验证：按 `tests/test_search_suggestions_postgres.py` 自有初始化流程使用全新 `win_search_suggestion` 数据库，由套件创建 `suggestion_app` 受限角色，**63 passed**。覆盖画像版本绑定、额度、幂等、失败持久化、并发、RLS、最小授权和 Node/HTTP 路径；仍不代表真实模型服务或生产部署已接通。

2026-09-10 执行运行时独立 PostgreSQL 验证：使用一次性数据库并由套件创建动态 `NOSUPERUSER/NOBYPASSRLS` 执行角色，运行 `tests/test_execution_runtime_postgres.py` 与 `tests/test_execution_http_postgres.py`，**44 passed**。覆盖任务启动、逐平台租约、取消/停止确认、原始回执、服务重建、签名核验和 HTTP→受限 PG 往返；仍不代表真实来源 worker、平台执行或生产部署已接通。

2026-09-10 设备凭据授权增量：`grant_device_credentials.sql` 现明确授予受限角色读取 `pilot_users`、读写 `pilot_devices`、读取会话撤销表，以满足设备身份解析和历史校验的最小运行依赖。独立套件在一次性 PostgreSQL 上从原先无法初始化推进到 **24 passed / 4 failed**；剩余失败集中在撤销跨模块连接/会话授权和登出失效语义，尚未计为通过，需拆分依赖后继续验证。

2026-09-10 设备凭据授权收口：进一步补充受限角色更新 `pilot_platform_connections`、写入 `pilot_session_revocations` 的最小权限；独立 `tests/test_device_credentials_postgres.py` 在一次性 PostgreSQL 上 **28 passed**。设备挑战、签名、轮换、撤销、并发和 HTTP 安全路径通过；该结果不替代生产部署、真实平台连接或客户 UAT。

2026-09-10 设备登记恢复独立 PostgreSQL 验证：沿用受限身份角色和登记授权脚本，核心登记套件 **7 passed**，HTTP 登记恢复/严格输入/权限套件 **22 passed**。覆盖原 request_id 恢复、幂等冲突、撤销/过期、owner 隔离、HTTPS/Origin 和 no-store；不代表平台账号已连接或 Windows 实机验收完成。

2026-09-10 执行运行时复核：在全新一次性 PostgreSQL 数据库 `yike_mac_20260910_try` 上，由执行套件自行迁移并创建动态 `NOSUPERUSER/NOBYPASSRLS` 角色，`tests/test_execution_runtime_postgres.py` **42 passed**。此前复用旧库触发 `v02-identity-execution` checksum mismatch，已确认不能将旧库状态当作当前 schema 证据；本结果仅覆盖执行运行时套件，不代表其他 PG 套件或生产部署完成。

2026-09-10 搜索建议 PostgreSQL 复核：清理旧测试角色及其数据库对象后，使用固定 `win_search_suggestion` 数据库，由套件重新创建 `suggestion_app` 受限角色，`tests/test_search_suggestions_postgres.py` **63 passed**。覆盖迁移、RLS、配额、幂等、并发、失败持久化与 HTTP/Node 路径；该结果仅适用于一次性本机测试容器，不代表生产数据库或真实模型服务。

2026-09-10 研究策略 PostgreSQL 复核：清理旧 `strategy_app` 角色及其数据库对象，并安装锁定的 desktop Node 依赖后，使用固定 `win_research_strategy` 数据库按套件自有流程运行，`tests/test_research_strategies_postgres.py` **49 passed**。覆盖策略版本、确认/撤销、RLS、HTTP 和 Node 客户端往返；该结果仅适用于一次性本机测试容器，不代表生产部署或真实模型服务。

2026-09-10 设备凭据 PostgreSQL 复核：使用全新 `yike_mac_identity_20260910` 数据库、管理员与独立受限 `identity_app_mac` 角色运行 `tests/test_device_credentials_postgres.py`，**28 passed**。覆盖挑战、Ed25519 签名、轮换、撤销、并发与 HTTP 安全路径；不代表真实平台账号或 Windows 实机已接通。

2026-09-10 设备登记 PostgreSQL 复核：在同一受限身份数据库运行 `tests/test_device_registration_postgres.py` 与 `tests/test_device_registration_http_postgres.py`，**29 passed**。覆盖登记恢复、幂等、撤销/过期、owner 隔离、HTTPS/Origin 与 no-store；不代表真实平台账号或 Windows 实机已接通。

2026-09-10 触达/回复迁移授权探针：在全新 `yike_mac_outreach_20260910` PostgreSQL 数据库创建一次性受限应用角色，完成全量迁移并重复执行 `grant_outreach_contract.sql`、`grant_reply_events.sql`，输出 `migrations-and-grants-pass`。该探针只证明表结构与授权脚本可重复应用，不代表真实发送、回复回流或 RLS 业务套件已通过。

2026-09-10 研究导入原子性 PostgreSQL 复核：在全新 `yike_mac_import_20260910` 数据库使用独立管理员与受限 `import_app_mac` 角色运行 `tests/test_import_atomicity.py`，**5 passed**。覆盖受限导入、失败回滚和跨租户边界；不代表真实平台采集或生产部署完成。

2026-09-10 候选入库 PostgreSQL 复核：使用独立身份数据库的管理员/受限角色运行 `tests/test_candidate_ingestion_postgres.py`，**23 passed**。覆盖签名提交、原子回执、版本历史、租户隔离、预算/租约与失败关闭；不代表真实平台采集或生产部署完成。

2026-09-10 候选人工复核 PostgreSQL 复核：在受限身份数据库按候选入库套件创建授权后，运行 `tests/test_candidate_review_postgres.py` 与 `tests/test_candidate_review_http_postgres.py`，**58 passed**。覆盖模型评估边界、来源核验、人工复核、配额、RLS、HTTP 与回滚；模型为本地合成边界服务，不代表真实模型质量、平台采集或客户 UAT。

2026-09-10 机会证据 PostgreSQL 复核：在同一受限身份数据库运行 `tests/test_opportunity_evidence_postgres.py`，**8 passed**。覆盖证据快照、来源绑定、摘要哈希、晋级边界、RLS 与跨租户约束；数据为合成来源，不代表真实项目机会或商业转化。

2026-09-10 连接版本 PostgreSQL 复核：在独立身份数据库使用管理员/受限角色运行 `tests/test_connection_versions_postgres.py`，**40 passed**。覆盖连接版本递增、撤销/重连、租户隔离、RLS 与权限边界；不代表真实平台账号已连接。

2026-09-10 桌面机会 HTTP PostgreSQL 复核：同时注入研究策略、身份和 Pilot 受限数据库连接，运行 `tests/test_desktop_opportunity_http_postgres.py`，**1 passed**。覆盖桌面客户端读取机会、证据与跟进状态的 HTTP 往返；数据为合成输入，不代表真实平台线索或客户 UAT。

2026-09-10 执行签名回执 HTTP PostgreSQL 复核：在独立身份数据库运行 `tests/test_execution_signing_payload_http_postgres.py`，**11 passed**。覆盖签名载荷、请求完整性、回执关联、预算和受限 PostgreSQL HTTP 往返；不代表真实平台执行或发送。

2026-09-10 Pilot 运行时 HTTP 复核：同时注入身份与研究策略数据库，运行 `tests/test_pilot_runtime_http_postgres.py`，**2 passed**。覆盖普通 CLI 启动、实际 HTTP 路由、受限应用数据库选择与任务执行边界；来源/模型仍为合成输入，不代表真实平台采集或发送。

2026-09-10 已确认策略复核 PostgreSQL 验证：使用独立研究策略与身份数据库运行 `tests/test_confirmed_strategy_review_postgres.py`，**35 passed**。覆盖策略确认、复核绑定、撤销/重启、RLS、租户隔离及执行前约束；不代表真实平台采集或发送。

2026-09-10 Pilot 专用数据库权限与导入原子性复核：使用独立 `yike_mac_pilot_20260910` PostgreSQL 数据库及受限 `pilot_app` 角色运行 `tests/test_pilot_contracts.py` 与 `tests/test_import_atomicity.py`，**11 passed**。该结果补足此前将身份库角色误用于 Pilot 套件的环境问题，证明受限角色下的权限/原子性合同可执行；仍不代表真实平台采集、真实发送、生产部署或客户 UAT。

2026-09-10 回复历史追加修复：`3a5a4b6` 修正 `CORRECTED/VOID` 事件在同一租户/用户下被后续查询覆盖、误报 `event_conflict` 的问题；新增事件以自身 `event_id` 做幂等查询，并在目标不存在时返回 `event_target_unavailable`。回复合同与存储专项 **20 passed**，compile 检查通过。尚未完成 PostgreSQL 受限角色集成、真实平台回流、已读同步、提醒调度或客户 UAT。

2026-09-10 最新主线回归：在 `c0f0fcc`（含回复历史追加修复）上运行 `uv run --frozen pytest -q`，结果 **2110 passed / 488 skipped in 54.41s**。这是锁定代码的本地全量回归；跳过项仍主要依赖真实 PostgreSQL、平台账号、Windows 实机、生产环境或外部回复，不能升级为 M3 完成。

2026-09-10 回复事件 PostgreSQL 受限角色探针：在一次性 `yike_mac_pilot_20260910` 数据库核对 `pilot_reply_events` 已启用并强制 RLS，`pilot_app` 为 `NOSUPERUSER/NOBYPASSRLS`，具备最小 SELECT/INSERT 权限，当前事件表为空。该探针验证迁移与角色边界，不代表回复事件业务写入、并发、回流或生产部署已完成。

2026-09-10 固定 Mac 验收候选：在 `dc0e62e` 上执行桌面类型检查、生产 renderer 构建和 `npm run package:dev`，均通过；产物为 `desktop/out/意客AI-darwin-arm64/意客AI.app`，ASAR SHA-256 `b534830606316667fb485cc79d9d56d821662c4b5637e8b29ae6aec1f543cca9`。该包仅作为后续可见验收固定输入，不代表 Windows 实机、真实平台采集/发送/回流或客户 UAT 完成。

2026-09-10 CP-06 正向预检复核：使用仓外 0600 临时运行环境、PostgreSQL URL、禁用开发登录及 digest 固定镜像，`scripts/cp06_validate_env.sh` 返回 `cp06-preflight: pass`；临时文件已删除。该结果只证明配置门禁可满足，不代表镜像发布、服务部署、备份恢复或真实客户验收完成。

2026-09-10 Mac 可分发候选：在 `4764cf7` 上执行 `npm run make:mac` 成功，生成 `desktop/out/make/zip/darwin/arm64/意客AI-darwin-arm64-0.2.0.zip`，SHA-256 `eb7894f69e8f735b3b7b96ef4c582620e59f86e95b8ab5e1888004e02c47a912`。该包可用于 Mac 可见验收；未证明 Windows 安装、真实平台采集/触达、生产部署或客户 UAT。

## 后续 AI 必须遵守

1. 先读 `AUTHORITY.md`、本文件和 `docs/V02_IMPLEMENTATION_TASKBOOK.md`。
2. 将 Skill 规则层、平台连接器、任务调度、触达队列和 Windows 交付分开推进。
3. 不把 `SKILL.md` 存在、测试通过、设计完成或页面可打开写成平台已接通、真实采集、真实发送或商业成功。
4. 新代码使用独立提交和独立审核；未经用户确认不得发送外部消息，不得绕过验证码、限流或平台风控。
