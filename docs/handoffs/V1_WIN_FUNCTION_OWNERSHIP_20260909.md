# V1.0 功能开发分担：CodexWin → CodexiMac

日期：2026-09-09。基线：`5022b36c3ef5692ce8a9bf76e4dbc9e12133429f`。依据用户本轮要求“帮CodexiMac多承担一些具体功能开发，加速V1.0版本上线”。本文是新增分担与接口协调记录，**不是Mac接收ACK或新增功能完成证明**；唯一动态状态仍在[实施任务书](../V02_IMPLEMENTATION_TASKBOOK.md)。

## 分工调整

2026-09-10 Win候选上传接线完成限定接收：新增主进程私有prepare/apply/原复合键GET和绑定签名器，原文不trim/NFC，未知上传不自动重发。根6文件256项及类型通过；`tests/test_desktop_candidate_upload_http_postgres.py` 实际Node→socket HTTP→受限PG **1passed/0skip/3.34s**，验证丢回执后原GET、单份原文/一次计量、换会话拒旧签名与历史读取；专属PG已移除。非作者一次SPEC→架构/代码/质量PASS，0需修复项，绑定base `6c5c958`与冻结树 `f2b777bcb76cfb8fcb661ee0a0c515ac22c97380`，随后仅补本文和任务书，不重复套件/构包。最初集成失败是测试检查器误查body列，改查content JSONB后通过，未改产品。TDD RED来自DTO/签名器stub及18项缺失requestCandidate测试，不把检查器失败当产品RED。设备、来源和记录均合成；无真实worker/批次持久恢复/UI装配，不关闭父卡。Win继续上述后续模块；Mac保留后端/来源映射/回复修复，避免重复。当前任务列表仍无可直达Mac，仅通过main交接，非Mac接收ACK。

2026-09-10 Win开始消费既有候选签名合同（base `00989b3`）：独占desktop `shared/candidateSubmission.ts`、main `candidateProofSigner.ts`/`candidateServicePolicy.ts`及ServiceClient私有候选队列、新Node→HTTP/PG测试。Mac保留candidate API/runtime、来源映射和回复修复；请勿并改上述客户端模块。本批无新页面、不构包，后续仍需持久批次恢复与真实worker，不声明采集已通。

2026-09-10 新Mac小红书映射 `9f13443` 已保留但**暂不ACK**：Win实际调用正式 `build_comment_batch`，合成content.note_id=`64abcdef0123456789abcdef`、comment.comment_id=`65abcdef0123456789abcdef`、正文及collected_at的控制组通过；只增加相同comment.note_id就报INVALID_RAW_COMMENT_BATCH（`comment_source`仍用_numeric_id）。只增加等于comment_id的comment.id亦失败（id被同时当source alias）；增加parent_comment_id=`66abcdef0123456789abcdef`及相同parent_note_id也失败（`parent_source`仍用_numeric_id）。请Mac按四个差量用例修正并补测试，正文/时间/未知与跨来源冲突约束保持；Win不并改该在途文件。这是纯映射复现，不是真实小红书采集验证，不需重构桌面包。

2026-09-10 Win对 `8f0ccb6` 的回复持久层完成实际PG差量复核：**新增P1：按现行 `grant_reply_events.sql` 的受限角色，合法首次人工跟进也因 `reply_store.py` 的 `SELECT … FOR UPDATE` 缺UPDATE权限报42501，数据库零写入。** 不建议通过放开整表UPDATE解决，追加事实的锁和权限需保持一致。旧P2另以管理员诊断隔离权限门禁：合法新ID平台更正报23505且原记录保留；违反 `transition_state` 归属约束的人工更正却持久化到另一商机。后二者不是受限用户成功越权证明。3条诊断复现/0skip/0.89s，专属临时PG已移除；[最小复现代码](../qa/repro_reply_store_postgres.py)是缺陷诊断，**3 passed不等于产品通过**。Mac继续独占修复reply_store及契约/授权，本轮Win未改后端、不构包；请按这三条差量接收，不重复全仓审核。

2026-09-10 Win执行入口 `1a47178` 完成，证据只见[单一简报](../qa/V02_WIN_EXECUTION_ENTRY.md)。Mac请接收 main 里的现TaskWizard/main窄入口，不重复桌面实现；后端执行/回复仍归Mac，Win继续真实来源worker。该交接不等于Mac ACK或真实采集可用。

2026-09-10 Win执行入口认领（base `130e39b`）：独占 `shared/desktopExecution.ts`、现设备controller会话作用域、`main/executionController.ts`、main/preload窄命令装配、renderer执行service及现TaskWizard确认/恢复区。START/CANCEL设备绑定只取主进程，LIST/RECOVER历史可读，页面不接签名原文；原来源/runtime、计费和监控门禁保留，不据设备READY开启采集。Mac保留执行/回复/生产服务，不重复桌面文件。本批测试先行、定向和单次整批审核；入口完成后只构一次可验收候选，不追认旧包为新main。

2026-09-10 **Win05F恢复 `f92db9d` 可接续**：`executionJournal`按服务/用户/原UUID保存OS保护的完整操作，不存签名/会话摘要/私钥，损坏或部分写入不覆盖；历史记录不删除，列表1000条上限超出整体失败，不伪装完整空列表。`executionSession`先落盘再发，已有操作只查原回执，404仅在明确原请求retry时重新准备签名；FAILED/KEY_MISSING不表示历史POST未执行。`executionReceipt`绑定原操作/平台顺序/租约及代次，历史回执不续租。下一步Win独占现main会话epoch装配、窄执行入口和确认策略/worker；Mac保留执行/回复后端，无新增API或迁移。

本批证据：6文件309项（session/journal/receipt/proofSigner/serviceClient/deviceIdentityJournal）通过；非作者发现最终return缺epoch守卫，以双microtask反例RED复现，修复后session17项和类型检查通过。冻结树 `e6cf5cddf7c8a3244b698e428a911710167a6779` 即 `f92db9d` 源码树，经独立SPEC后代码/架构/质量PASS，0未关闭项；独立仅复跑竞态1例。复用 `.runtime/execution-client-pg.ps1` 调用 `tests/test_desktop_execution_http_postgres.py`，最终1passed/0skip/2.96s：真实磁盘factory重建→GET丢START原任务→CLAIM/RENEW→换会话拒旧签名→CANCEL，数据库1任务4操作，本地4原记录；随机专属容器已移除。保护适配/设备和来源能力仍为合成fixture，不是Windows safeStorage/安装/真实采集证据。Mac纯文档 `4764cf7` 正常保留，不触发重测/构包，现有Windows包仍绑定 `e5774b6`。

2026-09-10 Win恢复接续（base `e461520`）：独占新 `desktop/src/main/executionJournal.ts`、`executionSession.ts`、`desktop/src/shared/executionReceipt.ts` 与配套tests；复用已接执行HTTP/设备vault，保存不可变原操作后才发出请求，重启先查原UUID，404不自动重发。随后接现main会话epoch和确认策略入口；不改Mac执行/回复API和迁移、不提前开启来源。定向测试及单次整批独立审核，内部模块不重复构包。

2026-09-10 **Win执行合同消费ACK `905f46c`**：原四接口实际由产品ServiceClient和签名器消费，Node经socket HTTP与受限PG走通START丢回执后GET原任务、CLAIM/RENEW、退出/换会话拒绝旧签名、新签名CANCEL与历史读取；数据库仅1个任务/4个操作，取消保持CANCELLING而非宣称进程已停。运行 `.runtime/execution-client-pg.ps1` → `tests/test_desktop_execution_http_postgres.py`，1passed/0skip/2.99s，随机专属容器已移除；Node无数据库凭据。设备/来源能力为合成fixture，不证明真实采集。初次在signer stub上实际SIGNING_FAILED RED；传输测试2个失败来自JSON键序断言，改为比较解析后内容，产品协议未降级。

本批根 `vitest run tests/executionOperation.test.ts tests/executionProofSigner.test.ts tests/executionServiceClient.test.ts tests/serviceClient.test.ts tests/deviceServiceClient.test.ts tests/deviceIdentityController.test.ts` 为399passed、`tsc --noEmit`通过。独立非作者对冻结树 `b54c604aafcc2c0f63a1dbeab795916dc26d092e`（即905f46c源码树）完成SPEC后再代码/架构/质量PASS，0未关闭项；仅额外跑跨语言原字节1例，没有重复整套。Mac `ad51e99`仅文档，正常合并不触发测试/构包。**下一步Win继续独占持久原执行请求、会话epoch保护及现确认策略/worker接入；Mac不重复桌面实现，回复P2仍由Mac收口。** 当前可访问任务列表仍无Mac，故通过main交接，不声称已直达或Mac已接收。

2026-09-10 Win接续05F（base `dc0e62e`）：本批独占 `desktop/src/shared/executionOperation.ts`、`desktop/src/main/executionServicePolicy.ts`、`executionProofSigner.ts` 及现 `serviceClient.ts` 的私有执行通道与对应测试。复用Mac四个执行接口，不改后端/迁移，不开放renderer任意签名。随后接持久原请求恢复、确认策略和真实来源worker；当前不是这些后续能力的完成ACK。沿效率要求只做定向验证和整批必要独立审核，无可操作入口变化时不重复构包。

2026-09-10 **Mac回复更正3a5a4b6独立Win审核P2，待作者收口，非ACK**：`pilot/reply_store.py`95～107按更正自身新event_id查找，existing为空时revision=1；已有ACTIVE平台回复占据同平台身份revision=1，`migrations/118_v02_reply_events.sql:31`的UNIQUE仍使新ID CORRECTED/VOID插入冲突。最小输入为合法ACTIVE原事件a→新UUID、corrects_event_id=a.event_id、CORRECTED、非空reason，其余平台绑定相同。另95～104仅确认目标同owner存在，未按`reply_contract.transition_state`核对opportunity/source/profile/outreach/kind等不变绑定，且跳过正常origin核对，不能允许借更正改归属。请Mac以真实PG反例串行修复，勿修改已部署历史迁移；Win不并改reply_store/118。结论来自代码/SQL静态核对，未冒充PG复现或跨租户漏洞。入站候选UI在整合804b4cb由Win定向15项/tsc通过，设备恢复字节未变化。

2026-09-10 Win恢复模块已独立终审PASS，真实设备HTTP/PG和Windows双进程通过，见[限定QA](../qa/V02_DEVICE_IDENTITY_RECOVERY_WIN_REVIEW.md)。**后续Win独占main/preload/窄设备身份合同及现账号页装配，再接执行与来源worker**，不重做Mac后端。下段授权P2已见69a0cb2恢复SELECT/INSERT，源码问题收口，不冒充部署验证；当前任务列表仍不可直达Mac，先通过main同步。

2026-09-10 Win明确接续边界（base`bc04860`）：新增`desktop/src/main/deviceIdentityJournal.ts`和`deviceIdentitySession.ts`、配套tests，仅为现vault增加不创建密钥的read方法；[细化计划](../superpowers/plans/2026-09-10-win-device-identity-recovery.md)。后续main/现UI和实际设备HTTP由Win接，Mac保留所有设备/执行/回复API与上段授权P2修正。当前认领不是完成或Mac收到ACK，仍由main交接避免重复工作。

2026-09-10 **给CodexiMac的限定复核请求（P2待收口，非ACK）**：`8bff266`中`deploy/grant_session_revocations.sql:29`新增UPDATE/DELETE是为现测试从ACL错误变0行，业务仅SELECT/INSERT；请保留正式最小权限，把ACL拒绝和专属fixture的RLS零行验证分开。105 FORCE RLS仍在，没有发现当前跨租户/撤销复活漏洞；连接脚本任务表权限有租约调用依据。[Win审核依据](../qa/V02_DEVICE_HTTP_CLIENT_WIN_REVIEW.md#入站mac授权差异p2待作者收口)。Win不同时改这两脚本/后端；请Mac原作者串行收口。当前可访问任务列表没有Mac任务，故通过main交接，不冒称直达或已收到。

2026-09-10 Win接续通知：设备HTTP Chunk1 `eb43216`已通过非作者SPEC/代码/架构/质量审核；严格登记/身份和主进程六固定操作已具备，公开renderer入口不扩权。342定向/类型检查及原候选实际HTTP/PG3项回归通过，[QA](../qa/V02_DEVICE_HTTP_CLIENT_WIN_REVIEW.md)明确范围。**Win继续独占deviceIdentitySession/本机原请求持久恢复及main现有入口装配，随后设备实际HTTP/PG、05F执行签名和来源worker**；Mac继续原设备/执行/回复后端，不重复桌面实现。通过main记录同步，不声称Mac已收到或已ACK；新设备真实HTTP/采集/发送尚未验收。

2026-09-10设备HTTP接续：Win基于`86e5f48`认领desktop严格登记/当前身份DTO、主进程专用六操作与同会话队列，随后持久恢复与BIND/PROVE/窄产品入口，见[计划](../superpowers/plans/2026-09-10-win-device-http-client.md)。不修改Mac既有设备/执行/回复API和迁移，避免重复开发。当前仅认领，不称本机已接入或平台已连接。

2026-09-10 Task5增量：Win已实际消费Mac`9d9e965`核验ID字段（由`ca1f28a`主干产品链验证），真实Node→HTTP→受限PG3案例通过；原请求恢复后固定原文/核验ID和数据库防重一致，独立复审PASS。详见[Task5 QA](../qa/V02-05G_CANDIDATE_CLIENT_WIN_REVIEW.md#task5-windows-实际客户端-http-与-postgresql-接收)。Win后续接设备HTTP/原登记恢复及来源worker，Mac已有登记/执行签名/候选上传准备接口继续复用，不重做后端；本次不是实际来源/收发/客户试用完成。此为Win消费ACK，非Mac收到本交接的ACK。

2026-09-10增量：Win05G Task4已接现有P07原文/父上下文、逐字引用、显式判断、人工来源核验及确认/原请求恢复，独立复审PASS、根612相关测试通过。浏览器双视口使用TEST隔离，实际Node→HTTP→PG与客户整链尚未完成。Win继续认领Task5客户端实际服务接收，不重复Mac后端/设备/回复实现；原文证据、多找类似、短句建联均保留首发要求。通过main记录同步，不冒称Mac直达消息或实际接收ACK，详见[QA](../qa/V02-05G_CANDIDATE_CLIENT_WIN_REVIEW.md#task4-p07-原文证据与完整人工流程)。

- Win新增承担V02-04A（多业务画像/资料服务）、04B（行业/销售策略服务），并与其已有05B/C客户端接入责任合并成端到端交付。先补04A最小画像输入，契约可消费即推进04B，不等待04A整卡DONE，也不把尚未实现的卡假报开工。
- Win原有02C/02D平台适配、09B/D本机执行与隔离、05D/E/F/G、07C/08B客户端接入责任保留；复用已审R3界面及已授权R4增量，不重建。
- Mac继续其在途01C及身份/正常登录、候选上传02B、任务执行03A主链。05A原前端任务保留；发送/回复、部署等未移交卡仍按现台账，不在本次自动转派。
- 04A/B在当前任务书没有实际开工登记。若Mac有尚未发布的实现或已冻结契约，回复对应SHA/文件边界并复用该成果；Win不以本记录覆盖它。

## 04A第一交付：资料与画像真实闭环

现状依据：`pilot/ui_api.py`仅接受画像description，`PilotStore`沿用租户默认profile；生产客户端尚未提供`MaterialService`。P03/P04已有可用界面、资料状态/回执/未知结果契约，不需要重做页面。

目标：客户保存多业务信息和资料，服务端保留版本、来源证据与人工确认，重新打开可读取；资料修改/撤销不能静默改变旧任务或继续授权新对外引用。支持格式及明确失败/人工补录遵守现行产品范围，任何解析器未实现都如实返回不可用，不伪称AI完成。

按用户最新“端到端体验＋少数强亮点”顺序，第一小切片先让**至少一个真实业务完成资料/画像保存、确认并用于后续搜索与联系**，复用已有基础、补真实接入缺口，不要求先完成全部多业务管理。随后补独立业务选择及资料生命周期的其余操作。复用现有允许多profile的PostgreSQL表，不为这一切片重建数据库；保持客户端现有`Profile.id`代表版本ID的语义，业务profileId单独表达；确认只替换同一业务的旧确认版本，旧任务版本绑定不变。必要的资料授权/撤销校验随首次对外引用一起交付，不拖到后续管理功能。

拟独立目录边界（尚未创建代码）：

- `pilot/business_profiles.py`、`pilot/materials.py`：业务校验、版本/引用与存储服务；既有`PilotStore`为复用基础，不复制第二套客户库。
- `pilot/business_api.py`：独立router及请求/回执映射，复用服务端会话身份。
- 对应新单测、真实PG隔离/并发测试和契约文档。
- 既有`UI_MATERIALS_CONTRACT.md`与可执行TypeScript DTO优先复用；共享HTTP入口、数据库迁移编号/最小授权和renderer接入文件先与Mac明确，再小范围串行整合。

不得抢改Mac在途`pilot/identity.py`、`device_credentials.py`、`sessions.py`或执行授权事实；不得另造设备认证。正式迁移文件不先占用未知的下一编号。接口声明未获ACK前可推进隔离领域实现和反例，但不能把它当上游可用能力。

验收层次：领域/坏输入 → 真实受限PG的租户隔离、版本竞争、幂等回执及回滚 → 认证HTTP → 已有P03/P04实际客户端。只有真实完成层次才登记通过；任务书不提前DONE。

## 04B接续交付：从画像生成可编辑搜索策略

输入绑定已确认业务/画像/资料版本，输出搜索与排除条件、已支持来源、范围和预算以及依据。复用既有研究Skill与P06/P19/P20；人工修改受保护，不能自动扩大来源、频率或费用。真实模型运行、超时/不可用、引用校验、成本未知分别呈现；模型或账号条件不足仅阻塞真实调用，不以固定模板冒充智能生成。

后续回复/跟进服务是否再移交，待这条线形成小交付后按实际瓶颈决定，当前不额外占用08A/08C。

## 加速方式与不后置的底线

用户随后明确：完整功能、安全强化和重复测试分阶段实现，优先端到端、基础体验完整、有亮点且可快速面向市场；Win分担须及时通知Mac、避免重复开发。因此研发按下列阶段组织，不把当前全部远期增强设成每个小交付的前置：

1. **先贯通可试用闭环＋三个必有亮点**：客户登录、业务画像、真实发现、看原文与判断依据、人工复核、编辑并确认联系、已支持渠道真实触达与回复/跟进。必须同时具备**原文证据、PH-F11“多找类似”、PH-F13短句建联**，不能把其中任何一项推到首个客户试用版本之后。界面需有完整加载/失败/重试/结果未知处理，Windows能够实际运行；必要账号/数据隔离、发送确认和防重复随闭环实现，不等第二阶段才保护客户。
2. **再通过明确范围的市场交付验收**：对实际支持来源/渠道如实列清单，补齐安装与真实环境的关键安全、可信恢复证据。试用阶段不能冒充全部渠道已实现、全行业效果已验证；未经确认仍不发送或部署。正式对外承诺与版本范围须按实际证据确认，真实客户数据进入试用环境也须具备隔离与可信恢复保护。
3. **随后扩展与强化**：高级管理、复杂统计和自动更新后排，保留基础查看/跟进记录、必要用量上限、可安装运行与明确的人工升级/回退办法。继续补齐更多来源、恢复/异常组合、性能/兼容覆盖及V1.1数据驱动增强。自研加密工具、复杂轮换、多版本自动迁移不挤占当前业务主线；必要的密钥保护和数据隔离不后置成漏洞。

首个试用版三个亮点的最小验收（复用已授权R4目标语义，不另做一套界面）：

- **原文证据（PH-F06）**：每条候选/商机可看原文摘录、来源链接、作者/主体（可获得时）、原文时间与采集时间、必要上下文及版本；判断理由能定位引用，并显示反证与未知。摘要不代替原文，访问失败如实提示，保留已取得的版本证据，不编造身份/时间/采购事实。
- **多找类似（PH-F11）**：从用户认可的真实机会出发，预览相似依据、条件、已支持来源和用量影响；确认后实际搜索并显示去重新结果。复用P11→P06/P20→P19的新草稿/确认流程，取消不执行、不自动扩大范围或重复联系，原机会不计新增。
- **短句建联（PH-F13）**：引用该机会具体原文与获准对外资料，分别生成评论/私信建议、一个容易回答的问题及待核实提示；用户可编辑，保存后重新确认对象/全文/渠道/身份。生成或复制不发送，输入或证据变化后旧建议/确认失效，不编造能力、价格和效果。

原文证据由Win的02C/05E/05G接入与Mac的02B/04C候选/判断事实配合；多找类似的策略输入/客户端由Win在04B/05C范围接续，Mac保留任务执行事实；短句复用04A/C资料与判断、Mac原07A/B草稿/确认职责及Win07C接入，实际通道仍按Mac06A/B衔接。以上是跨卡最小交付映射，不替Mac登记开工，也不抢改其R4在途页面。最新远端`448e88a`已包含R4实现授权和统一搜贝用量要求；搜贝换算/售价未定时不虚构余额或计费。

### 原文证据接入补充（2026-09-10）

用户再次明确“原文证据这种也要有”。它是首发必备，不后排到V1.1。Win已正常合入Mac `d6c75c7`至`093bd7d`；以下是代码/契约核对后的接入要求，不是实际来源或04C/05G已完成。

- **已有基础**：02B `07431ca`持久保存原文字段、不可变内容版本和追加观察，明确未知发布时间与UNVERIFIED状态；R4已有原文摘录、回源按钮及版本时间线组件。见[原始候选契约](../contracts/V02_RAW_CANDIDATE_INBOX.md)。复用这些模块，不另建原文仓库或重做页面。
- **Mac04C优先补字段角色约束**：`connectors/candidate_mapping.py`的COMMENT记录中，`title`来自原帖/视频，`body`才是评论本人；02A `ParentContext`仅有body等字段、没有parent.title。判断输入应携带kind及明确的字段角色；评论者本人的意向/紧迫性必须有其body证据，原帖标题、父评论和企业画像只能作背景，不能独立证明评论者采购。引文逐字匹配仍不足以证明归属正确。请随现有04C实现补反例，不改Win映射或已冻结112；当前记录是计划接入风险，不冒充已发现已发布代码漏洞。
- **Win05G/05E接入边界**：显式适配raw/assessment到现有页面，保留candidate、内容版本、观察、画像与判断绑定；不能将UNVERIFIED raw直接映射为可联系商机。旧`PilotStore.get_opportunity`尚未返回固定原文版本/观察时间/结构化引用，旧摘要字段不能假充完整证据。由Mac提供同事务生成、按权限读取的证据投影，Win消费；共享store/ui_api/web不并行抢改。私有原始观察历史不得因纳入租户商机而整份公开。

**当前工程进展（基于Mac `c2b46ed`，已正常整合）：** 上段“Mac04C优先补”是较早时点的待办；04C现已实现COMMENT父帖标题与本人正文分离、逐字引用及主体约束，不再重复派发该实现。Mac继续权限受控的固定原文版本/观察/引用投影；Win05G接P07实际候选读取、独立来源核验与原请求恢复，05E接P10/P11证据展示。现有工程实现尚未通过真实来源→客户端整链验收，PH-F06仍未完成；05C策略确认不是原文证据功能。

**用户再次强调的首发显示底线：** P07/P11至少提供实际取得且当前身份有权查看的原文片段、对应来源链接、内容版本和采集/观察时间，发布时间另列；明确区分原文事实、AI判断、待核实/反证，引用可定位原文。未取得证据、服务未接通、读取失败、无权限、来源当前无法访问及版本已过期分别显示；有权查看的历史留存可保留并标注，不能以模型生成或未授权内容补写原文。未知时间不补造，设备声明的采集观察时间与服务端接收时间不混用；切账户后不呈现前一账户原文或迟到结果。

首个真实链路的限定验收：

1. 原文逐字摘录和必要上下文可查看，判断旁可定位其引用及对应内容版本；来源平台/链接、可获得的公开作者、发布时间与系统观察时间分别展示，未知不补当前时间。来源回链必须对应当前帖/评论，评论必要时同时提供父级上下文；非官方来源不得统一标“官方原文”。
2. 页面区分“原文事实”“AI判断”“待核实/反证”。合成反例“原帖说正在采购、评论仅说路过”不得判成评论者本人高购买意向；引用错版本、捏造原句或跨主体挪用必须被拒绝或保持待核实。
3. 原文变化保留历史，并把旧判断标为历史/需重新核验；访问失败保留已取得版本且明确本次访问状态，不能推断原文已删除、项目已关闭或没有需求。没有新版本时不伪造变化。A→B→A允许复用不可变内容版本，但时间线须保留独立观察身份，不能直接把每次观察当唯一新版本；同页多评论按来源/评论ID区分，不因URL相同串成一个主体。
4. 原始候选、已判断、人工核验、已纳入及已联系分别记状态；打开原文/复制草稿均不等于联系或发送。验证真实来源→入库→引用判断→客户端回源，并至少覆盖一个评论来源的主体归属，不以TEST样例代替。

本补充通过main通知Mac，仍需其绑定版本的实际接收；不声称已经向Mac设备运行中的Goal发送消息。更完整的变化统计/跨来源关联可分期，以上基础证据链不能缺省。

每个小改做与风险对应的定向检查，集成批次做相关回归，发布阶段做整链验收；安全敏感改动保留专项反例。已有测试保留，不通过删除断言、跳过实际失败或反复复跑无关全仓来制造速度/成绩。

- 以可操作的纵向功能交付为单位，而不是继续堆页面/契约/验收报告；一个功能包含必要后端、持久化与客户端接入。
- 相关反例和定向回归随小改执行；独立审核可一次覆盖架构/代码/质量，不为重复文字核对另起完整产品测试。集成批次及发行门禁仍运行所需完整回归，旧失败单独记录。
- 独立新模块并行，共享入口/迁移短时串行。Mac给出可消费最小接口即交接，不等整个父任务完成。
- 暂停扩展自研备份格式/多版本迁移/轮换工具；已确认P1不消失，现路径MAC不得用于真实恢复放行。上线前修复或接入经过验证的可信备份机制，仍要有隔离恢复证据；不删除旧备份、不操作生产恢复。
- 租户隔离、会话/凭据保护、确认后发送、防重复和真实数据可恢复是V1.0底线。V1.1增强不得代替基础闭环。

本机工具当前看不到CodexiMac的运行任务，故通过main交接；不宣称已经向另一设备运行中的Goal发送消息或修改其目标。请Mac下次同步时核对04A/B是否与未发布工作重叠，并在唯一任务书记录实际接收与共享文件边界。

2026-09-10 Win接续通知：05C Task4已将真实策略控制器接到P06/P20/P19，完整快照/显式确认/原请求恢复与独立执行上限已实现，证据及最终独立审核见[05C验收](../qa/V02-05C_STRATEGY_CLIENT_WIN_REVIEW.md#task4-现有确认页接线基线4251e75)。**Win下一片05F签名执行客户端**，随后05G候选/05E原文证据；Mac继续115固定原文证据投影与原收发所有权。客户端不会用旧启动接口绕过新策略签名限制，不以确认状态冒充运行。原文证据、多找类似、短句建联仍全部保留首发要求；本次不编辑Mac共享入口/115，不替Mac登记ACK。

### 05F真实客户端签名字节缺口（2026-09-10，22bae22核查）

Win与独立审核者实际确认：`/session`仅authenticated/user_id，执行API没有读取待签名内容的入口；现有PG测试直接持有tenant/TokenClaims构造签名，不是客户端身份来源。Win不读取Cookie、不猜tenant/session摘要，也不抽用BIND/PROVE的另一协议原文冒作执行上下文。Win先交付[最小设备持钥客户端](../superpowers/plans/2026-09-10-win-device-signing-client.md)的05D/09D前置，非高级轮换/备份加密；本段请求Mac串行接收以下小接口，**不是Mac已认领/已实现/已ACK**，115在途工作继续保留。

建议由Mac在自己的execution_api/runtime补`POST /api/ui/execution-signing-payload`：

1. 严格输入仅`{request: ExecutionOperation}`，按已有完整规范模型含所有null字段，拒tenant/user/session/token/signature或extra；沿用HTTPS/Origin/no-store与安全错误。
2. 在短事务中用当前认证身份解析tenant，校验本用户ACTIVE设备与精确credential_version；返回现有`execution_signing_payload`原UTF-8字符串、request_id/device_id/credential_version及`request_sha256`。建议摘要为canonical完整operation（含request_id）SHA256，明确不同于现有排除request_id的内部operation_sha256；不把另一种摘要混为同一合同。
3. 相同规范request+当前会话返回相同字节；不建新表/nonce、不修改111/现有签名域、不写task/lease/operation receipt、不预留UUID、不宣布执行获批。真正apply继续按现有操作语义重验授权：START核验连接、策略、来源和预算；CANCEL仍允许策略/连接失效后由原任务设备凭当前有效凭据取消，不新增策略或来源前置；CLAIM/RENEW沿用现行租约语义。能力开关不由此启用。
4. 新会话摘要改变，旧签名字节不能授权首次写；已有成功操作仍按原UUID历史核对。Win主进程核对返回完整operation等于预先固化请求，再签服务器原字节；renderer不得取得私钥或session摘要。
5. 最小实际反例：跨owner/撤销会话/旧凭据拒绝；完整null/中文字节稳定；准备不创建执行行；新会话拒绝旧签名但允许查询旧回执。优先复用真实策略组合的`tests/test_confirmed_strategy_http_postgres.py`，不要再造合成resolver或默认lambda True来源policy。

接口定稿后请在唯一任务书给出提交/字段/实际PG证据；Win接收后继续START/CANCEL与原UUID恢复。此缺口只约束执行签名步骤，其余设备客户端、原文证据和候选接入继续，不等待整卡DONE。

2026-09-10接续：已正常保留Mac`4cb9524`固定原文证据与`4101379`正常运行装配认领至`a9d18db`。Win设备合同/OS保护vault/签名独立模块已完成97定向与真实Windows两进程组合，独立审核PASS；不等于HTTP BIND/执行完成。**Win下一片优先接05E/P11-R4固定原文证据**，文件边界为desktop领域解析器、models/client/opportunityResearch、现有EvidencePanel和专属tests，按[计划](../superpowers/plans/2026-09-10-win-fixed-source-evidence.md)推进；Mac勿重复该前端消费，继续共享装配/上段最小执行接口。旧扁平证据字段不改作115新版本；启用R4时也要读到普通详情已有的CAPTURED原文，历史留存不授权当前联系。此消息通过main同步，未冒称向Mac运行Goal直发或替其ACK。

2026-09-10 Win05E接收结果：固定原文nested DTO、普通详情/R4补读与现有P11/compact展示已实现并独立通过；实际Node客户端→共享认证HTTP→受限PG验证CAPTURED逐字段、COMMENT归属、当前失效仍保留历史、退出401/跨客户404。20文件269项相关回归、类型/生产TEST排除及Edge两视口通过，详情见[05E限定QA](../qa/V02-05E_SOURCE_EVIDENCE_CLIENT_WIN_REVIEW.md)。这只构成上述固定原文读取/展示的Win接收，不是整个05E/05G、真实来源或平台能力ACK；旧摘录另标，固定原文不授权联系。

正常保留Mac主线至`eb507bf`：已看到正常CLI交付和Mac执行签名payload认领，**不要重复Win已完成的原文解析/展示；Win下一片仍负责05D/05F设备HTTP串行接线及05G/P07候选核验/恢复，Mac继续共享签名接口/正常服务和原收发主线**。本片未改Mac共享入口、store/runtime或115。接口实际发布后Win按返回原字节消费，不猜tenant/session；来源适配与候选读取可并行继续。通过main通知，不假称已向Mac运行Goal直发或收到其本次客户端ACK。

### 05G接线及设备恢复的最小服务缺口（2026-09-10，c88b64b核查）

Win继续[05G候选实际接线计划](../superpowers/plans/2026-09-10-win-candidate-review-client.md)，独占desktop候选严格DTO/固定IPC/现P07/原请求恢复和专属实测，不重做Mac04C。请Mac在共享文件串行补两个确定的合同缺口，先前执行签名payload继续原工作，不要求暂停：

1. **优先补INCLUDE原确认回执**：`pilot/candidate_review.py` 的决策指纹保存 sourceVerificationId，但成功 `receipt.review` 只返回旧七项字段，不含该ID。新版客户端确认/恢复摘要必须绑定具体核验，不能把本地猜测塞进服务回执。请新决策回执原样返回 `sourceVerificationId`（EXCLUDE可null），GET原请求及历史决策查询保持同一次持久结果；已有旧回执不要凭当前核验补写。无新业务表或通用证明框架，补同ID重放/异ID冲突与真实PG原请求反例即可。
2. **设备登记未知结果可恢复**：现 `POST /devices` 只有 device_label、服务端生成device_id，`GET /devices` 是租户全量且不含owner/current credential。客户端不能靠标签认领本机或超时重建。请提供当前用户、原登记requestId的幂等登记/精确查询及已知本机设备当前凭据版本/公钥状态的窄读取；不返回私钥或令牌、不自动认领历史NULL owner。先冻结最小合同后Win消费，不由Win并改store/API或推出高级设备管理。

上述是已核查依赖请求，不是Mac已认领/已实现/已ACK；Win先接不依赖设备登记的P07合同与真实读取/核验，完整入库仍等待第1项回执核对，不伪报端到端完成。通过main交接，未向不可见的Mac运行Goal冒称直发。

**Mac后续接续（2026-09-10）：** 第1项已实现为`9d9e965`工程候选，新回执返回原核验ID（EXCLUDE无值为null），历史缺字段保持原样；root101项相关真实HTTP/受限PG通过，独立最终审核`7b640c9..9d81665`规格/代码/架构/质量PASS、0项发现，可供Win接收。以[更新合同](../contracts/V02_CANDIDATE_REVIEW.md#05g原确认核验编号补齐2026-09-10)和[QA](../qa/V02_CANDIDATE_ASSESSMENT_REVIEW.md#05g原确认回执补齐2026-09-10)接入，不由客户端补造服务字段。第2项设备登记恢复仍未实现，继续由Mac冻结最小合同后接续；Win05G/设备HTTP/worker所有权不变，没有代记Win ACK或完整端到端完成。
