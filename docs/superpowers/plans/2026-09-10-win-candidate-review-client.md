# 05G 真实候选判断与人工复核客户端 Implementation Plan

> **For agentic workers:** REQUIRED: Use `subagent-driven-development`; TDD and independent spec then code/architecture/quality review. 用户已授权沿现有 R3/R4 接真实服务，直接 main；root 唯一 Git 写入者，独立文件分工，不改 Mac 在途共享后端。

**Goal:** 让已有 P07 完成真实候选读取、查看原文与判断、人工来源核验、确认纳入/排除及原请求恢复，并在入库后进入已接通的 P11 固定原文；不是另建一个只读演示。

**Architecture:** 现有认证 HTTP/固定 IPC → 严格共享 DTO → 现有 P07 页面；新增小型独立来源核验面板及新版 opaque 操作记录，复用旧样例、确认弹窗与账户隔离。原始候选未核实，AI 分析和人工纳入均不授权发送。旧账本只读核对，不迁移/删除/自动重发。

**Tech Stack:** TypeScript/Zod、现有 React 页面/operationLedger、Vitest、真实 Node→共享 FastAPI→受限 PostgreSQL、Windows Edge 隔离界面。

基线 `c88b64b`。产品授权与风格见 `AUTHORITY.md`；服务规范为 `docs/contracts/V02_CANDIDATE_REVIEW.md`、`V02_RAW_CANDIDATE_INBOX.md` 和正常装配合同，UI 恢复沿 `docs/UI_CANDIDATE_REVIEW_CONTRACT.md`。不是新一轮视觉设计，不改变旧采集/策略/发送模块。

## 当前依赖和范围

- 普通 CLI 已构造真实 candidate review/strategy reader；正常 POST ASSESS 仍需配置模型，不能靠新前端打开未配置能力。
- 服务端 `receipt.review` 当前未返回 `sourceVerificationId`；完整新版确认必须包含此字段。给 Mac 请求最小同原请求返回补充，不在 Win 私自伪造回执。接口补齐前不启用无法完整核对的新 INCLUDE，读取/协议/核验和实际测试可继续。
- 设备登记缺少幂等请求与 owner/current credential 的精确找回，这只影响设备 HTTP 登记恢复，不阻止当前已授权 GET 候选或复核接口接线。交接另列，Mac 现有执行签名载荷继续原所有权。
- 当前 P07 source projection 不含 COMMENT kind/父上下文；必须补读已存在 `/raw-candidates/{candidate_id}` 明确来源角色，不从 title/buyer 猜身份或把父帖标题当评论本人需求。保留 nullable 时间、观察与版本，快照不混代。

## Chunk 1: 严格协议和产品传输

### Task 1: 独立共享候选复核合同

**Files:** Create `desktop/src/shared/candidateReviewApi.ts`, `desktop/tests/candidateReviewApi.test.ts`, `desktop/tests/fixtures/candidateReviewApi.ts`。

- [ ] 先写可导入 stub 和 RED：合法完整列表/五种回执保留全部字段；未知/缺字段、坏类型、错误 UUID/opaque request、过大/残缺 Unicode、身份/版本失配拒绝。不将不可识别响应映射成空列表或成功。
- [ ] 导出 `candidateQuerySchema`、`candidateReviewRequestSchema`、`sourceVerificationRequestSchema` 及相应输入类型；`parseCandidatePage(raw, query)`、`parseCandidateReviewResult(raw, expected)` 返回严格类型，固定错误，不把 Zod 原值/cause 返回客户。
- [ ] Query 为现端点的 query/platform/status/page/pageSize/ids/reviewRequestId；去除 UI 空白查询后严格校验，query至多200个Unicode码点、正式平台枚举、小写规范UUID、page为1..999999999、pageSize为1..100、ids为1..100个唯一UUID。原请求列表必须恰好一个id且page=pageSize=1；opaque ID为`[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}`。创建 URL 用 URLSearchParams，ids按逗号连接传入，不接受客户端路径/查询字符串。
- [ ] 所有写入包含候选/来源/画像版本及原 requestId。ASSESS 允许显式 nullable retryOf；INCLUDE/EXCLUDE 保存五项依据与 humanConfirmed=true，INCLUDE 必须有 sourceVerificationId，EXCLUDE 有非空理由。VERIFY_SOURCE 保留 status/openingMethod/locator/excerpt/contactMethod，不接收 checkedAt/checkedBy/tenant。发送前完整 JSON UTF-8 上限 64KiB。
- [ ] 完整 assessment 包括四维(level/reason/citations)、purchaseType/grade/decision/effectiveDecision、summary/draftComment/draftDm、evidence、绑定/策略/规则/模型/assessedAt，sendingAuthorized 固定 false；不把 SEND_READY 解释成发送批准。引用字段五种仅原样校验保存，不转成伪来源。候选保留 profileId/profileVersion/strategyVersionId/historical/currentBindingValid/assessmentStale/sourceVerification；nullable url 和空发布时间不补造。成功 decision 的 candidate 与 receipt 严格一致；历史 response 可读但不解锁当前写入。
- [ ] `pending`/`failure`/`assessment`/`decision`/`sourceVerification` 分别解析：pending/failure只返回requestId/candidateId，不能伪造完整版本绑定；assessment/decision/sourceVerification按其实际携带字段与原请求核对完整绑定。UNKNOWN pending可有`code:"assessment_unknown"`，FAILED有`code:"assessment_failed"`；缓存别名的invocationRequestId可出现在assessment/pending/failure，保留它但不是第二次调用。复核回执核验 ID 缺失作为旧版本读取，而新 INCLUDE 的确认匹配不放宽。按Python Unicode codepoint长度与UTF-8实际字节校验，不因emoji的UTF-16长度不同而截断或误拒合法正文。
- [ ] 跑 `node node_modules/vitest/vitest.mjs run tests/candidateReviewApi.test.ts --maxWorkers=4` RED→GREEN、tsc；独立规格再质量复核后进入 Task2。

### Task 2: 现有主进程/renderer 固定服务接线

**Files:** Modify `desktop/src/shared/contracts.ts`, `desktop/src/main/servicePolicy.ts`, `desktop/src/renderer/services/contracts.ts`, `desktop/src/renderer/services/client.ts`, `desktop/src/renderer/domain/candidates.ts`; create `desktop/src/renderer/services/candidateReview.ts`, `desktop/tests/candidateReviewService.test.ts`; extend `desktop/tests/serviceClient.test.ts`, `desktop/tests/ui/client.test.ts`。

- [ ] 先写 RED：固定 `candidates.list/review/verifySource/request` 对应四个已存在 HTTP 入口；写操作仅已验证 payload，无通用 URL/任意方法，无来源核验冒充评估。所有动作复用同 session 队列与 HTTPS/Origin/no-store/响应字节限制。
- [ ] 独立 `createCandidateReviewService(request)` 做严格边界解析、预期身份核对及错误映射；在现 service 接 candidates/reviewCandidate，并加 source verification 与原请求读取。浏览器透传 AbortSignal，IPC 调用前/采用响应前检查取消；不声称物理取消服务器操作。
- [ ] P07当前中文平台筛选值显式映射为服务枚举`XIAOHONGSHU/DOUYIN/BILIBILI/ZHIHU/PUBLIC_WEB`，并提供反向显示映射；共享DTO不因此接受任意字符串。
- [ ] 保留旧 Candidate 类型兼容公开样例/旧 R3 夹具，实际服务 DTO 必须严格；新增服务元数据明确标识，不能让缺新字段旧夹具经真实接口变为已核验。
- [ ] 定向现策略/原文/连接/发送回归及类型检查；服务接线不自动调用模型或核验/入库。独立审核后进入恢复与 UI。

## Chunk 2: 来源证据与可靠操作接线

### Task 3: 原始证据读取与新版操作恢复

**Files:** Create `desktop/src/shared/rawCandidateEvidence.ts`, `desktop/src/renderer/domain/candidateRequestOperation.ts`, `desktop/src/renderer/pages/opportunities/useCandidateRequests.ts` 及各专属 tests；extend `desktop/src/renderer/app/operationLedger.ts`/`hooks.ts`（仅新的 opaque scope）、service policy/adapter。

- [ ] RED→GREEN：现 raw-candidate GET 的严格当前候选/版本/观察解析，bind candidateId/profile/strategy/version；COMMENT 当前本人正文/作者与原帖标题/父评论分开。列表与详情版本变化提示刷新，不能混合展示或付费重判。
- [ ] 新 scope 保留 ASSESS/VERIFY_SOURCE/INCLUDE/EXCLUDE 原 requestId、action、candidateId、绑定/确认摘要及必要 opaque 核验/重试 ID，不写原文/人工依据/凭据。先持久化再 POST；失败不派发，其他账户隔离，清草稿/退出不清记录。旧 candidate-reviews scope 完全保留。
- [ ] 结果未知、错回执、401/404/5xx保留；GET 原请求只读取，不自动调用模型或换 UUID。已查询的 FAILED/UNKNOWN 分析仅在用户显式确认后新 requestId+retryOf；PROCESSING不能发新请求；未知人工核验/决策先核对原请求，不能盲重试。
- [ ] 新 INCLUDE 确认摘要覆盖 sourceVerificationId；旧缺字段回执不假装匹配新确认。Mac最小字段补齐后通过真实 HTTP 验证；若尚未交付保留该精确接收缺口，不以客户端推断替代。

### Task 4: 复用 P07 的完整人工流程

**Files:** Modify `desktop/src/renderer/pages/Opportunities.tsx`（候选部分），create `desktop/src/renderer/pages/opportunities/CandidateSourceVerification.tsx`, `CandidateOriginalEvidence.tsx`, `CandidateAssessmentDetails.tsx` 及专属 UI tests；CSS只局部增量，现公开样例/批量确认/旧账本不删除。

- [ ] 先写用户可见 RED：普通候选可读、未核验不能入库；四维理由和逐字出处/反证/未知可看，原文时间与采集/接收时间分别展示；没有模型结果不造等级/草稿。
- [ ] 当前绑定画像自动选中但不自动 ASSESS；改变选择不悄悄产生调用，显式“按画像判断”后才发起。原文或画像/策略变化使旧分析/核验与确认失效；历史快照只读，返回当前版本才能继续。
- [ ] 人工来源面板独立展示“已打开/受阻/过期/未核实”、直接或平台内打开、定位描述、原文逐字摘录、可检查联系路径，用户勾选确认后保存。仅点击回源不算核验成功，OPEN不等于平台验证或发送授权；缺时间/过期/无联系路径不得 INCLUDE。
- [ ] 显示源核验人/时间/ID对应当前版本；INCLUDE/EXCLUDE确认时固定所有字段（含核验ID），更改即重确。原请求核对可从筛选外找回，晚到响应/账户空间切换不回填旧数据；确认成功进入现 P11，旧来源快照继续独立。
- [ ] 页面/旧发送防重相关回归；Windows 两视口真实浏览器（TEST隔离），检查原文、明确失败、确认/取消/恢复，不执行外部采集/模型/真实联系。

## Chunk 3: 实际服务闭环与交接

### Task 5: 真实 Node → HTTP → PostgreSQL 接收

**Files:** Create `tests/test_desktop_candidate_review_http_postgres.py`, `desktop/tests/integration/candidate-review-live.test.ts`；QA `docs/qa/V02-05G_CANDIDATE_CLIENT_WIN_REVIEW.md`，更新唯一任务书及 Win/Mac 交接。

- [ ] 复用已验一次性 PG/112/113/115/真实策略 fixture，只有模型输出/平台原始输入合成；实际产品 client list→ASSESS→verify→INCLUDE→原请求→opportunity固定证据，跨用户/退出拒绝、重复不多商机、丢回执恢复、来源/画像版本变化拒绝。测试不改变生产 grants/store/API。
- [ ] 子 Node 不含数据库 URL/管理员连接，测试 token 仅私有 env、不在 argv/log；精确移除本轮临时容器。没有实际服务完整执行不宣称05G已接收。
- [ ] 最终相关批次/类型/构建/生产TEST排除/凭据扫描及非作者整片复核；正常整合main并按新来件影响检查，不强推、不计别人的测试为本轮结果。
- [ ] 更新当前实现/尚缺真实来源和模型/确认收发/Windows发行/UAT边界；整体 Goal 继续，三个首发亮点与原产品范围不缩减。
