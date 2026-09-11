# 同来源后续变化与首页提醒实施计划

> **For agentic workers:** Use superpowers:subagent-driven-development. 复用已批准 R4 P11 时间线/P02简报，不新建页面；本批一次整批独立审核，定向测试，修复仅差量。

**Goal:** 已纳入商机的后续真实留存正文变化可回查，并进入当日首页提醒；不再停留在纳入时旧版本。
**Architecture:** 以纳入证据的精确 observation 锚定本人 source_id，复用112留存表进行只读投影；V2分开内容版本与观察序列，共同供时间线与简报使用。
**Tech Stack:** PostgreSQL/Python、Zod/React，无迁移/新模型/外发。

## Global Constraints

- 完整V0.2继续，当前基线 `15a41b3b3c00fab189d19cec68d5f4cdc3021c87`。不把本批代码/合成数据验证宣称真实平台、Windows、部署或UAT。
- 不改变纳入商机的原文、人工判断、OPEN/CLOSED状态或发送资格；来源变化不自动成为采购、预算、截止或关闭事实。读取不采集、不写入、不发送、不收费。
- 始终按认证tenant+owner和冻结证据 `observation.id` 定位唯一source；核对version、观察/收到时间与原证据。允许同一owner该来源跨任务的观察，禁止跨owner/PAGE/同名实体拼接。来源URL与冻结URL必须一致，不能模糊匹配。
- 完整读取最多200条观察、100个真实内容版本，超过明确报错，不截断后声称无变化。版本目录仍真实version_id，A→B→A不能发明第三个内容版本。
- 观察按observedAt升序，receivedAt/id仅作稳定同刻排序；同observedAt出现不同正文视为歧义，不产定向变化，也不能让歧义组任意成员作为下一条比较基点。更早观察晚上传保留历史，不当作纳入后新变化。
- 只从无歧义观察组之间产生 `CONTENT`，body逐字不同时才有变化；标题、作者、parent、发布时间等单独变化不生成正文提醒。变化的下一观察必须严格晚于锚点observedAt，前观察不早于锚点；重复同正文无变化。歧义后首次清晰观察只重新建立基点。
- `occurredAt:null`（真实编辑时间未知），`detectedAt`为变化两端receivedAt最大值，另保留观察时间。不以收到时间改写原帖/评论发布时间。
- 变化ID绑定前后真实observation，snapshotId包含锚点、观察身份/两种时间、版本和变化，原锚点不必是最末。引用逐字来自对应body，≤8000 UTF16单位、非空，用首个差异附近片段并保留可回查全文。
- V1原严格规则保持。V2 wire沿用binding/window/versions/contacts/gaps，新增 `anchorObservationId`、`observations:[{id,versionId,observedAt,receivedAt}]`；schemaVersion=2。V2 changes沿用id/kind/label/from/to/occurredAt，新增 `fromObservationId`、`toObservationId`、`detectedAt`。from/to仍原ResearchQuote结构，仅field source.body或缺字段。
- V2版本目录ordinal按首次观察，previousVersionId连接目录上一个内容版本（不是页面变更顺序）；唯一ID/同URL/真实body。观察引用已列版本；anchor指向binding.evidenceVersion；变化前后观察必须时间严格递增、对应version/quote，且不越过歧义组，不按版本ordinal判断方向。空白/重复/未知锚点/伪造引用/未来记录拒绝。
- 首页每机会最多一条（今天收到的最新变化），复用同一投影，日界以业务时区detectedAt；ID/basis.recordId绑定变化端点，basis.version为toObservationId，basis.excerpt是当前变化后原文，basis.kind保持VERIFIED_CHANGE仅表示留存对比事实，reason说明观察时间/编辑时间未知及待复核需求。coverage仍PARTIAL，未读/未覆盖不补零。点击进入该机会changes标签。

## Task 1: 服务端同源观察投影（backend agent）

**Files:** 新 `pilot/source_content_changes.py`；`pilot/opportunity_research.py::timeline`、`pilot/opportunity_brief.py::query`；必要最小SELECT授权脚本；新 `tests/test_source_content_changes.py`/PG测试。

- [x] 定向用例：锚点非末、A→B→A、正文重复/仅元数据、早时晚传、同刻异文、上限。PAGE空ID及跨owner隔离由精确查询和独立代码审核核对，本批未新增这两项独立HTTP反例，不冒充实跑。
- [x] 共用有界helper读取/校验/投影，时间线输出V2；旧原文/判断不改，无法确定的方向列gaps。brief复用helper，仅本人当前画像纳入机会，当日真实变化去重一条；跨owner缺口不扩大读取。
- [x] 使用真实受限PG入库/纳入和普通HTTP证明更新后时间线与简报可见、A返回原version仍留存变化，复用既有授权边界基线；客户端适配验证单独执行，不宣称真实客户端到平台端到端。
- [x] Python固定运行时 `/tmp/yike-main-merge.PZkSlU/.venv/bin/python`；独立自有临时PG，不触碰60486/shared；仅目标测试，不重跑全套或构包。提交自身文件、报告命令/失败/通过/边界到sdd/source-changes-backend-report.md。

## Task 2: 原页面V2消费（root）

**Files:** `desktop/src/renderer/domain/opportunityResearch.ts`、`pages/opportunities/EvidenceTimeline.tsx`、`pages/workbench/OpportunityBrief.tsx`及定向domain/UI/service tests。

- [x] 新失败用例：V2锚点非末、A→B→A、错观察/版本/引用/时间拒绝；旧V1规则不变；原页面纳入锚点/后续观察/收到时间/未知编辑时间显示。
- [x] 用独立严格V2 schema与V1 union；校验观察序列、锚点及实际相邻无歧义比较，不放宽V1规则。已有service固定路由复用，无写接口。
- [x] 复用列表/原文/差异组件；V2按观察序列展示实际版本，可反复显示同版本并标纳入依据，不显示不存在的新版本；变化显示系统收到证据时间和后观察时间、实际编辑未知。
- [x] 首页VERIFIED_CHANGE文案改为留存原文对比，保留人工核验需求区分及原changes导航；定向domain/UI/adapter检查与TypeScript，不构包。

## Task 3: 独立审核与主线

- [x] 整批非作者审查上述基线到最终源码，复用测试，发现问题同波修复/差量复审。
- [x] 唯一证据集中本文件，更新合同/任务书/整合状态；主线推送及自有资源清理结果以任务最终回执为准。完整Goal仍须真实平台、Windows、生产与跨行业效果证据。

## 实施与验证

基线 `15a41b3`；计划 `a41aebf`、后端 `2d1d2a7`、客户端 `bf48f33`、精度修复 `b488aa9`。无新增迁移、模型披露、外发或授权扩大。

- 客户端新V2用例最初4失败/1通过；首页导航先失败后修复，测试空数组类型错误修复。最终一次受影响5文件93项通过（5.74s），TypeScript exit0。
- 后端受限角色普通HTTP/PG及纯投影共7项通过（8.44s）；测试搭建时fixture链、路由前缀、已有跟进授权脚本缺失和basis.version断言错误均先修正。源数据为合成数据，非真实平台。
- 一次整批独立审核 `bf48f33` NO-GO：微秒输入按微秒生成方向却输出毫秒，导致客户端拒绝。`b488aa9`统一到wire毫秒精度做方向/分组，原始DB锚点和未来检查保留精度。同毫秒异文仅报歧义并重建基点。新增反例先失败（3条变化），修复后5项纯投影通过（0.36s）；没有重跑PG/全套/构包。
- 独立差量复审 `b488aa9fcca796cd46ed0c6af65a8dab84ba5489` GO，时间精度P2关闭、无新增阻断；复用既有证据，无重复测试。实际平台变化、Windows、生产与跨行业UAT均未因此完成。详细执行/审核报告留存私有sdd/source-changes-{root,backend}-report.md与source-changes-final-review.md。
