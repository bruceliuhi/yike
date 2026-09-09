# P07 真实候选判断/复核接入审计

- 日期：2026-09-10（Asia/Shanghai）
- 主工作区：`/Users/bruce/Developer/work/yike-ai-product-design`
- 源码提交：`a31069fead15f395e7b4ec93c9c91e441beea798`（已合入远端 `ab6407d`）
- 只读范围：新后端合同、实际服务和当前 P07 类型/界面/恢复代码；未改源码、未调用模型、未提交真实复核。
- 未提交的四个 raw 读取文件仅读为原文辅助提案，不视为既有产品功能或本次主列表方案。

## 结论

不能只把现有 `service.candidates` / `reviewCandidate` 换成 fetch。最小完整接入是 **已评估候选读模型 + 显式分析及原请求恢复 + 独立人工来源核验 + 绑定核验 ID 的人工决策 + 历史快照只读核对**。主列表应使用 GET `/api/ui/candidates`；raw 详情只做固定来源版本与观察历史辅助，不给 raw UNVERIFIED 记录补造 assessment、批准状态或复核回执。

有一个必须先补的服务响应缺口：INCLUDE 已要求 `sourceVerificationId`，但成功 `receipt.review` 还没有回传该字段。客户端无法既把核验 ID 纳入新确认 hash，又用当前服务回执核对原请求。应先补服务原确认快照，不能客户端猜补或省略 hash 字段。

## 实际已有接口及最小传输适配

后端入口：`pilot/candidate_review_api.py:67–111`，服务注入：`pilot/ui_api.py:335–336` / `pilot/web.py:50,292`。普通启动可以没有 `candidate_review` 实例，返回 501；端点存在不代表模型、策略 resolver 和真实平台读取已启用。

| 固定 operation 建议 | 真实 HTTP | 适配要求 |
| --- | --- | --- |
| `candidates.list` | GET `/api/ui/candidates` | query/platform/status/page/pageSize/ids/reviewRequestId 严格允许列表；空 query 必须省略，不能发送 `query=""`；中文来源映射正式平台枚举。 |
| `candidateReviews.create` | POST `/api/ui/candidate-reviews` | ASSESS 与 INCLUDE/EXCLUDE 用判别联合；保留原 requestId/retryOf/sourceVerificationId；不传 tenant/reviewer/time。 |
| `candidateSourceVerifications.create` | POST `/api/ui/candidate-source-verifications` | 独立人工动作及严格绑定，不由打开链接或模型完成代替。 |
| `candidateReviewRequests.get` | GET `/api/ui/candidate-review-requests/{requestId}` | 只查询原请求；不隐式 POST，不重试模型；适用于分析、核验和决策三类动作。 |

在 `desktop/src/shared/contracts.ts:37–44` 和 `src/main/servicePolicy.ts:7–56` 增加上述固定枚举与严格运行时 payload schema，main 生成路径/查询字符串。renderer 不接受任意 URL、header、actor 或路径。POST 对齐后端 64 KiB UTF-8 上限、UUID 绑定字段和 opaque request ID；中文/emoji 的字符数与字节数不要混为一谈。复用现有受信主 frame、HTTPS/Origin、内存会话、拒绝重定向和非 JSON 策略。

`services/client.ts:26–51` 保留服务端小写错误 code；当前 P07 `uncertainReview` (`Opportunities.tsx:854–862`) 只识别大写 `CAPABILITY_UNAVAILABLE`，直接接 HTTP 501 会留下不可恢复的不存在请求。适配器可以把合同明确的 501 `capability_unavailable` 映射为“未执行”，但不能把所有 409/422/5xx 统称 `REVIEW_REJECTED`。特别是 ASSESS 409 可能发生于模型调用后重新核对快照，不能宣称未调用或未消耗。

## 必须扩展的 DTO 与当前不兼容

| 当前位置 | 后端真实字段/规则 | 最小修改 |
| --- | --- | --- |
| `domain/candidates.ts:13–25,48–74` 只有旧精简 assessment、候选无绑定有效性标记 | `_candidate` (`pilot/candidate_review.py:311–325`) 有 `profileId/profileVersion/strategyVersionId/historical/currentBindingValid/assessmentStale/sourceVerification` | 严格解码并保留这些字段。未评估仍显示未评估；缺标记不能默认当前有效。人工决策不得使用历史/无效绑定或过期评估；ASSESS 则要允许当前有效绑定下的未评估/过期评估重新判断，不能因为 assessmentStale 永久禁用修复入口。来源核验独立校验五元绑定。 |
| 同上 `CandidateAssessment` 只保留五项证据 | 模型 schema (`pilot/candidate_assessment_model.py:73–103`) 有四维 `{level,reason,citations:[{field,quote}]}`、purchaseType/grade/decision/evidence/summary/draftComment/draftDm；`candidate_review.py:213–216` 加 provider/model/rule_version/rule_sha256/strategyVersionId/effectiveDecision/sendingAuthorized | 展示真实四维和引用、反证/未知、独立两类短句及版本标签。S/A/B+不是概率，SEND_READY不是批准；`sendingAuthorized` 必须 false，不能提升为发送权限。 |
| `candidateEditor` (`Opportunities.tsx:815–829`) 未评估记录只从 assessment 推断画像；UI `:1750–1773` 可选所有已确认画像 | 当前候选已绑定原任务画像**版本 ID**；`_capture:97–98` 要求请求 binding 全等 | 优先使用候选顶层 profileId/profileVersion，匹配同版本行。不能选另一业务或新版本直接改绑旧候选。需要换画像时另走新研究任务/草稿，旧版本保留。 |
| `assess:1055–1108` 只接受 kind=assessment，20 秒超时后丢原 requestId，允许再次生成 UUID | 真实结果还含 pending PROCESSING/UNKNOWN、failure FAILED，以及 alias `invocationRequestId`；请求可有 retryOf (`candidate_review.py:160–185,209–219`) | 分离分析状态和人工决策状态，发前持久原分析 requestId/绑定。超时、关闭、重启先 GET 原请求；FAILED 或 UNKNOWN 明确查询后才可由用户确认新尝试并传 retryOf。alias 时 retryOf 指实际 invocationRequestId，不误传缓存别名。成功缓存可复用，不假称新调用或退款。 |
| `openSource:1392–1397` 只调用 openExternal；`:1702–1714` 明确打开不解除限制 | `verify_source:230–249` 独立人工核验，字段见下 | 保留安全打开原文，新增人工核验表单/回执状态；不能把 openExternal 成功直接记 OPEN。 |
| `prepare:1127–1142`、`reviewSnapshot`、`candidateReviewHash` 缺核验 ID | INCLUDE 必须为同绑定最新且 24 小时内 OPEN，并有联系路径；发布时间未知或超 60 天也拒绝 (`candidate_review.py:269–279`) | INCLUDE snapshot 加 sourceVerificationId；确认弹窗显示核验人/时间/打开方式/联系路径及未知项。EXCLUDE 保持非空原因，不要求 OPEN。发布时间空字符串显示“未知”，禁止改成采集时间/今天。 |
| `reconcileOperation:1305–1333` 只读列表并 applyDecision 回写主列表 | 列表 reviewRequestId 路径只返回保存的成功人工决策，始终 historical=true；`:396–402` 可 currentBindingValid=false | 新动作恢复以专用 GET 原请求为主。原成功只能核销同一原操作；历史回执单独显示“原确认快照”，刷新当前列表，不把历史 candidate 覆盖当前版本、不据历史成功重新启用操作。 |

查询细节：`Opportunities.tsx:923–929` 默认传 `query: query.trim()`，空串会被后端拒绝；`:1429–1431` 使用中文平台值，服务需要 `XIAOHONGSHU/DOUYIN/BILIBILI/ZHIHU/PUBLIC_WEB`。恢复列表请求必须单个 ids 且 page=1/pageSize=1；普通单 ID 当前读取与历史核对不能共用不明确的成功语义。

## 人工来源核验的完整最小状态

请求共有 `candidateId/candidateRevision/sourceVersionId/profileId/profileVersion/requestId`；额外为：

```text
humanConfirmed: true
status: OPEN | BLOCKED | EXPIRED | UNVERIFIED
openingMethod: DIRECT | IN_PLATFORM
locator: 原文/平台定位说明
excerpt: 人工实际核对的原文摘录
contactMethod: COMMENT | DM | PUBLIC_CONTACT | NONE
```

响应 `kind:"sourceVerification"` 有 `id/requestId/candidateId/status/method:"HUMAN_REOPENED"/checkedBy/checkedAt/openingMethod/locator/excerpt/contactMethod/binding` (`candidate_review.py:241–244`)。这里 status 是来源状态，不能按请求 FAILED/SUCCEEDED 解释。

UI 应有编辑、提交中、已保存核验、确定拒绝、结果未知/核对原核验几个状态。人名/核验时间只读服务回执；来源变化、画像变化、最新核验被 BLOCKED/EXPIRED 覆盖或超时后，旧 OPEN 不再授予入库条件。客户端日期只能辅助提示，最终由服务端检查。收到原核验成功应刷新当前候选以获取最新有效性，不能把旧回执覆盖成新的 OPEN。

COMMENT 的候选 title 可能来自父帖；`_capture:116–118` 明确把它移到模型 `parent.title`。应区分“父帖背景”和评论者正文，不能把父帖采购需求称为该评论者意向。四维引用保留字段归属；需要展开完整原文/观察时，raw 详情按精确 sourceVersionId 匹配 current_version 或 observations 里的 version_id。历史版本不在截断的 100 次观察中就提示不可见，不能回退到最新原文冒充引用来源，也不自行声称已完成逐字校验。

## 恢复 hash / 账本迁移：不能清旧锁

现有 `candidate-reviews` ledger (`app/operationLedger.ts:70–71`、`pages/opportunities/useCandidateReviewLedger.ts`) 只记录 INCLUDE/EXCLUDE 的 `[candidateId,action,requestId,reviewHash]`，值 PENDING，按 user 隔离；旧 hash (`domain/candidateReviewOperation.ts:38–80`) 不含核验 ID。

1. 新版确认采用显式版本化 hash/ledger 记录，覆盖原绑定、assessmentId、五项人工证据、reason、INCLUDE 的 sourceVerificationId；不得修改旧 hash 算法让已有记录无法解析。旧记录保留旧核对分支，缺原确认信息时只读核对/提示服务支持，不按当前字段补造再发送。
2. 新增分析和来源核验的持久操作记录，保存原 requestId、类型、绑定/hash、必要 alias/retry 关联；不持久原文、人工填写全文或凭证。分析、核验、决策之间的 pending 互斥需明确，不能关闭窗口或清草稿解除未知保护。
3. 新记录携带本地 user/accountScope.id/version 归属；同 user 切空间不得查询/应用另空间回执。旧 user-only 锁保持保守阻塞，不猜属于新空间。当前外层 CandidateWorkbench 在空间切换时重挂载 (`Opportunities.tsx:766–771`) 可保留；新请求 hook 仍需 service/identity/generation 的同步 guard，保护 hashing、late response 和人工输入。
4. 新评估到达前若五项证据已有人工修改，保留人工稿并明确确认替换。当前替换确认可复用，但不要让旧 candidate revision/来源版本/策略的回包覆盖新行；assessmentMatches 还需服务返回的 currentBindingValid/assessmentStale/strategyVersionId 约束。
5. 任何不识别响应、网络失败、404、一般 5xx、无权限都不是“未执行”。GET 原请求 404 保留记录。只有新合同能证明原动作未保存的终态才能解除对应锁。ASSESS 的 kind=failure 不得误解为人工 INCLUDE/EXCLUDE 的 FAILED 并清另一操作锁。

### 服务端最小前置补件

`pilot/candidate_review.py:293–295` 当前构造 `receipt.review` 只保留七组旧字段，省略 `request.sourceVerificationId`。`get_request:44–62` 返回已存 result，不会补回此值；`_decide:301` 虽把 verification_id 存在 review 表，客户端没有读这个内部字段的接口。

应让新 decision receipt 的原 review 明确包含 sourceVerificationId（EXCLUDE 可显式 null），并版本化确认快照。已有历史回执要么使用服务器已保存的原 payload 做权限受控的明确旧版投影，要么保留 legacy，不能从当前最新核验补值。服务端的原请求幂等 fingerprint 已覆盖提交 payload；不用另建一套复核业务。

本机只读域函数验证：给现有 `candidateReviewHash` 同样快照，仅把附加 sourceVerificationId 从 A 改 B，两次 hash 相同（`15279a`）。这是现有算法遗漏新字段的证据，不是对未来新算法的测试。

## 建议拆分与实施顺序

1. **合同先齐**：补上述回执原核验 ID；新增 `shared/candidateReviewApi.ts` 固定输入/查询规则，扩展 `domain/candidates.ts` 或拆 `candidateAssessment.ts` / `candidateSourceVerification.ts` 为明确类型和解码，保留 legacy。
2. **适配器**：新 `services/candidateReviews.ts` 统一 list/assess/verify/decide/getRequest 严格解码、平台映射和错误分类；client 仅装配，main 固定 operation 接线。raw 服务只暴露 detail 辅助，不替换候选服务。
3. **有界操作**：新 `pages/opportunities/useCandidateAssessment.ts`、`useCandidateSourceVerification.ts`，版本化扩展 `useCandidateReviewLedger` / domain operation helper。复用 boundedRequest、既有 operationLedger 的持久失败保护和身份代次模式。
4. **界面收口**：把当前大 `Opportunities.tsx` 中 CandidateWorkbench 提到 `pages/opportunities/CandidateWorkbench.tsx`；分别挂 `CandidateAssessmentPanel`、`CandidateSourceVerificationDialog`、`CandidateHistoryPanel`、既有确认弹窗。维持批准的布局和原平台 Logo，不另做 raw-only 产品页。

最小验收需覆盖：默认空 query/各平台分页；未注入501无假数据；真实形状四维/未知日期；ASSESS pending/failure/alias/retryOf、超时离页重启原请求；人工原文核验四状态、空联系路径/已过期/不同版本阻断；INCLUDE 核验 ID hash 差异与错回执；原成功历史快照不能覆盖当前新版；ALREADY_IMPORTED 只提示既有机会未覆盖；清草稿不解锁、存储失败不派发、跨空间迟到不应用、批量遇未知即停。

现有后端回归入口可作为契约 fixture 依据：`tests/test_candidate_review_api.py`（HTTP字段/认证）、`test_candidate_review_http_postgres.py:165–188`（真实HTTP失败/显式重试）、`:200–240`（核验/决策/历史快照）、`test_candidate_review_postgres.py:343–352,438–447`（历史与当前绑定）、`:140–172`（核验ID/时效/联系路径）。本次仅检查源码与测试内容，未重跑其 PostgreSQL/HTTP套件；不把文档记载的56项结果算为本审核者本次执行。

共享商机 P11 的完整固定来源版本/观察/结构化引用投影仍是后端合同明确未接的下一段；本次 P07 可以完整接入私人复核，但不能因此宣称 PH-F06/P11 端到端证据已完成。
