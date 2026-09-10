# 05G 真实候选判断与人工复核客户端 Implementation Plan

> **For agentic workers:** REQUIRED: Use `subagent-driven-development`; TDD and independent spec then code/architecture/quality review. 用户已授权沿现有 R3/R4 接真实服务，直接 main；root 唯一 Git 写入者，独立文件分工，不改 Mac 在途共享后端。

**Goal:** 让已有 P07 完成真实候选读取、查看原文与判断、人工来源核验、确认纳入/排除及原请求恢复，并在入库后进入已接通的 P11 固定原文；不是另建一个只读演示。

**Architecture:** 现有认证 HTTP/固定 IPC → 严格共享 DTO → 现有 P07 页面；新增小型独立来源核验面板及新版 opaque 操作记录，复用旧样例、确认弹窗与账户隔离。原始候选未核实，AI 分析和人工纳入均不授权发送。旧账本只读核对，不迁移/删除/自动重发。

**Tech Stack:** TypeScript/Zod、现有 React 页面/operationLedger、Vitest、真实 Node→共享 FastAPI→受限 PostgreSQL、Windows Edge 隔离界面。

基线 `c88b64b`。产品授权与风格见 `AUTHORITY.md`；服务规范为 `docs/contracts/V02_CANDIDATE_REVIEW.md`、`V02_RAW_CANDIDATE_INBOX.md` 和正常装配合同，UI 恢复沿 `docs/UI_CANDIDATE_REVIEW_CONTRACT.md`。不是新一轮视觉设计，不改变旧采集/策略/发送模块。

## 当前依赖和范围

- 普通 CLI 已构造真实 candidate review/strategy reader；正常 POST ASSESS 仍需配置模型，不能靠新前端打开未配置能力。
- 原基线服务端 `receipt.review` 未返回 `sourceVerificationId`；Mac已按main交接以`9d9e965`补齐，新EXCLUDE省略/null返回null、原始payload指纹仍区分省略/null，旧回执不补写。Win现已快进到`2d799bc`并独立核对该单行修复；实际客户端HTTP接收仍需验证，不在Win伪造服务回执。
- 设备登记的幂等请求及owner/current credential精确找回已由Mac交付服务与三接口合同（`a6f68dd`，当前`2d799bc`）。不再作为无接口阻断，Win候选片后按合同接设备HTTP并独立验证；Mac执行签名载荷继续原所有权。
- 当前 P07 source projection 不含 COMMENT kind/父上下文；必须补读已存在 `/raw-candidates/{candidate_id}` 明确来源角色，不从 title/buyer 猜身份或把父帖标题当评论本人需求。保留 nullable 时间、观察与版本，快照不混代。

## Chunk 1: 严格协议和产品传输

### Task 1: 独立共享候选复核合同（已完成限定工程片）

**Files:** Create `desktop/src/shared/candidateReviewApi.ts`, `desktop/tests/candidateReviewApi.test.ts`, `desktop/tests/fixtures/candidateReviewApi.ts`。

- [x] 可导入stub的有效RED→合法完整列表/五种回执；未知/缺字段、坏类型、坏UUID/request、过大/残缺Unicode及身份/版本失配拒绝，不降级空列表或成功。
- [x] 导出查询/复核/来源核验schema及输入、严格输出类型；两个parse函数返回固定错误、不回显原值/cause。
- [x] 查询合同为query至多200个Unicode码点、正式平台、小写规范UUID、page1..999999999、pageSize1..100、1..100唯一ids；原请求恰好1id/page1/size1、opaque ID正则与后端一致。URLSearchParams和UI空白归一化由Task2适配执行，纯schema不改原值。
- [x] 写入完整候选/来源/画像绑定与原requestId；ASSESS保留retryOf省略/null；INCLUDE有核验ID，EXCLUDE有理由；人工核验不接actor/time/tenant；JSON UTF-8最多64KiB。
- [x] 完整分析维度/逐字引用/独立短句/规则模型、false发送授权和全部候选版本字段保留；nullable URL/未知时间不补造，历史仍核对原绑定而不授权当前写入。
- [x] 五类结果按实际字段解析；pending/failure无完整绑定不伪造，UNKNOWN代码及调用别名保留；旧缺核验ID回执可读但不匹配新INCLUDE。Python Unicode码点、空白比较和原始文本逐字保留。
- [x] 43项纯合同及4文件80项相关检查、类型检查通过；独立SPEC与代码/架构/质量PASS，三项反例修复记录见[QA](../../qa/V02-05G_CANDIDATE_CLIENT_WIN_REVIEW.md#task1-协议实现与反例)。仅本工程片完成，继续Task2～5真实接线。

### Task 2: 现有主进程/renderer 固定服务接线

**Files:** Modify `desktop/src/shared/contracts.ts`, `desktop/src/main/servicePolicy.ts`, `desktop/src/renderer/services/contracts.ts`, `desktop/src/renderer/services/client.ts`, `desktop/src/renderer/domain/candidates.ts`; create `desktop/src/renderer/services/candidateReview.ts`, `desktop/tests/candidateReviewService.test.ts`; extend `desktop/tests/serviceClient.test.ts`, `desktop/tests/ui/client.test.ts`。

- [x] 先写 RED：固定 `candidates.list/review/verifySource/request` 对应四个已存在 HTTP 入口；写操作仅已验证 payload，无通用 URL/任意方法，无来源核验冒充评估。所有动作复用同 session 队列与 HTTPS/Origin/no-store/响应字节限制。
- [x] 独立 `createCandidateReviewService(request)` 做严格边界解析、预期身份核对及错误映射，提供候选读/复核/来源核验/原请求读取。此片产品组合只接只读candidates，旧reviewCandidate保持明确不可用：当前P07换画像会直接调用它且没有ASSESS原请求持久化，不能提前启用真实模型。Task3/4恢复路径及显式按钮完成后再接产品写入口，无新通用权限框架/配置开关。浏览器透传 AbortSignal，IPC 调用前/采用响应前检查取消；不声称物理取消服务器操作。
- [x] P07当前中文平台筛选值显式映射为服务枚举`XIAOHONGSHU/DOUYIN/BILIBILI/ZHIHU/PUBLIC_WEB`，并提供反向显示映射；共享DTO不因此接受任意字符串。
- [x] 保留旧 Candidate 类型兼容公开样例/旧 R3 夹具，实际服务 DTO 必须严格；新增服务元数据明确标识，不能让缺新字段旧夹具经真实接口变为已核验。
- [x] 定向现策略/原文/连接/发送回归及类型检查；服务接线不自动调用模型或核验/入库。独立审核后进入恢复与 UI。
- [x] 组合回归证明此片真实service的旧判断入口仍不发候选POST；页面选择画像亦不能借只读接线触发模型。最终启用另验持久化先于POST。

Task2独立SPEC/代码/架构/质量通过，198相关及115策略/原文/确认发送检查分别通过，类型与生产TEST排除通过；[QA](../../qa/V02-05G_CANDIDATE_CLIENT_WIN_REVIEW.md#task2-固定传输与实际候选读取)保留原失败。此完成状态只覆盖固定传输和产品读取，不覆盖后续写入、PG与完整P07。

## Chunk 2: 来源证据与可靠操作接线

### Task 3: 原始证据读取与新版操作恢复

**Files:** Create `desktop/src/shared/rawCandidateEvidence.ts`, `desktop/src/renderer/domain/candidateRequestOperation.ts`, `desktop/src/renderer/pages/opportunities/useCandidateRequests.ts` 及各专属 tests；extend `desktop/src/renderer/app/operationLedger.ts`（仅新的 opaque scope）、service policy/adapter。实际核查后无需改`hooks.ts`，其清草稿流程本来就不删除新localStorage操作scope。

- [x] RED→GREEN：现 raw-candidate GET 的严格当前候选/版本/观察解析，bind candidateId/profile/strategy/version；COMMENT 当前本人正文/作者与原帖标题/父评论分开。不同版本拒绝混合；界面刷新提示及展示由Task4接。raw的profile_version_id就是复核profileId，无法从raw单独证明numeric profileVersion，不伪造该字段。
- [x] 新 scope 保留 ASSESS/VERIFY_SOURCE/INCLUDE/EXCLUDE 原 requestId、action、candidateId、绑定/确认摘要及必要 opaque 核验/重试 ID，不写原文/人工依据/凭据。先持久化再 POST；失败不派发，其他账户隔离，清草稿/退出不清记录。旧 candidate-reviews scope 完全保留并只读检查旧未决。实现/测试仅基础hook，实际页面写服务仍等Task4安装。
- [x] 结果未知、错回执、401/404/5xx保留；GET 原请求只读取，不自动调用模型或换 UUID。已查询的 FAILED/UNKNOWN 分析仅在用户显式确认后新 requestId+retryOf；PROCESSING不能发新请求；未知人工核验/决策先核对原请求，不能盲重试。按实际producer，requestId一直是用户原请求，invocationRequestId指实际模型调用；额外保存opaque invocationId，重试指它而不是错误的别名。慢hash期间同候选记录任何变化均使该次确认失效。
- [x] 新 INCLUDE 确认摘要覆盖 sourceVerificationId；旧缺字段回执不假装匹配新确认。Mac最小字段补齐后已在Task5通过实际产品客户端→HTTP→PG验证原核验ID，非客户端推断。

### Task 4: 复用 P07 的完整人工流程

**Files:** Modify `desktop/src/renderer/pages/Opportunities.tsx`（候选部分），create `desktop/src/renderer/pages/opportunities/CandidateSourceVerification.tsx`, `CandidateOriginalEvidence.tsx`, `CandidateAssessmentDetails.tsx` 及专属 UI tests；CSS只局部增量，现公开样例/批量确认/旧账本不删除。

- [x] 先写用户可见 RED：普通候选可读、未核验不能入库；四维理由和逐字出处/反证/未知可看，原文时间与采集/接收时间分别展示；没有模型结果不造等级/草稿。
- [x] 当前绑定画像自动选中但不自动 ASSESS；改变选择不悄悄产生调用，显式“按画像判断”后才发起。原文或画像/策略变化使旧分析/核验与确认失效；历史快照只读，返回当前版本才能继续。
- [x] 人工来源面板独立展示“已打开/受阻/过期/未核实”、直接或平台内打开、定位描述、原文逐字摘录、可检查联系路径，用户勾选确认后保存。仅点击回源不算核验成功，OPEN不等于平台验证或发送授权；缺时间/过期/无联系路径不得 INCLUDE。
- [x] 显示源核验人/时间/ID对应当前版本；INCLUDE/EXCLUDE确认时固定所有字段（含核验ID），更改即重确。原请求核对可从筛选外找回，晚到响应/账户空间切换不回填旧数据；确认成功给出现 P11 入口，旧来源快照继续独立。实际HTTP入库→P11固定原文整链仍由Task5验收。
- [x] 页面/旧发送防重相关回归；Windows 两视口真实浏览器（TEST隔离），检查原文、明确失败、确认/取消/恢复，不执行外部采集/模型/真实联系。

Task4源码`90c1feb`，保留Mac`81adccb`正常合入`5614d71`。最终扩大回归93文件1423项通过、类型/生产TEST排除通过，独立复审PASS；仅客户端工程与隔离浏览器验收，见[QA](../../qa/V02-05G_CANDIDATE_CLIENT_WIN_REVIEW.md#task4-p07-原文证据与完整人工流程)。

## Chunk 3: 实际服务闭环与交接

### Task 5: 真实 Node → HTTP → PostgreSQL 接收

**Files:** Create `tests/test_desktop_candidate_review_http_postgres.py`, `desktop/tests/integration/candidate-review-live.test.ts`；QA `docs/qa/V02-05G_CANDIDATE_CLIENT_WIN_REVIEW.md`，更新唯一任务书及 Win/Mac 交接。

- [x] 复用已验一次性 PG/112/113/115/真实策略 fixture，只有模型输出/平台原始输入合成；实际产品 client list→ASSESS→verify→INCLUDE→原请求→opportunity固定证据，跨用户/退出拒绝、重复不多商机、丢回执恢复、来源/画像版本变化拒绝。测试不改变生产 grants/store/API。
- [x] 子 Node 不含数据库 URL/管理员连接，测试 token 仅私有 env、不在 argv/log；实际执行后精确移除本轮临时容器。仅05G限定客户端工程接收，不称父任务或客户能力完成。
- [x] 最终相关批次/类型/构建/生产TEST排除/凭据扫描及非作者整片复核；源码`c0bd9f0`正常保留主干为`152abaa`，来件净文档变化、产品/测试字节不变；合入后实际PG3案例再次通过（8.92s），不强推、不计别人的测试为本轮结果。相关613项、类型/构建及独立SPEC/质量均有绑定记录。
- [x] 更新当前实现/尚缺真实来源和模型/确认收发/Windows发行/UAT边界；整体 Goal 继续，三个首发亮点与原产品范围不缩减。

Task5基于`ca1f28a`，3实际HTTP/PG案例通过，独立时间来源P2已关闭；[QA](../../qa/V02-05G_CANDIDATE_CLIENT_WIN_REVIEW.md#task5-windows-实际客户端-http-与-postgresql-接收)保留首次断言失败、实际权限错误码及所有验证边界。
