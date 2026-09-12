# 作者需求更新：时间线与每日简报

> 使用 subagent-driven-development/TDD：后端Agent与root客户端互斥开发，整批一次非作者审核。既定V0.2内用户已授权自主细化，不再等待逐项设计确认。

**Goal:** 已纳入机会的后续作者本人回复，不再只显示笼统gap；客户能看到首次观察或修改的逐字证据，并在当日简报进入同一机会。保持冻结纳入依据不变。

**Architecture:** 从既有owner范围candidate versions/observations投影，不新建采集库或修改原纳入证据；timeline显式V3请求，新旧协议共存。正文changes保持V2语义，作者事件独立；只报告可证明的观察，不自动判断预算/关闭/新发布时间。

**Tech Stack:** Python/PostgreSQL/FastAPI；Electron既有固定IPC、React/Zod/Vitest。

## Global Constraints

- 基线`8941dfa50c80ab4575894f3235dab6fdac62b1e6`；独占worktree `/tmp/yike-v02-scope.Pwf9Fs`，分支`codex/author-change-timeline`。不部署/构包/实网/外发/真实模型，不改变已批准产品范围。
- 原请求`{binding}`仍返回完全原样V2。新请求精确`{binding,timelineSchemaVersion:3}`返回V3；其他版本/额外字段/布尔值拒绝。新客户端默认V3，只在transport抛出ServiceError且status=422、code=invalid_request时读一次旧请求；不对认证错误、响应解析错误、超时或取消重试。
- V3保留V2所有字段和正文changes，`schemaVersion:3`；versions每项额外且必须`authorPublicId:string|null`（原public author ID）、`sourceContext:SourceContext|null`（沿用v2ex-author-context-v1，按原字段严格校验、不从冻结author_updates数组猜replyId）。普通非作者来源两项可null。
- V3额外`authorChanges`数组，最多200项。每项精确`id,replyId,kind,label,fromObservationId,toObservationId,detectedAt,occurredAt,from,to`。kind仅`OBSERVED_NEW`/`MODIFIED`；occurredAt恒null；detectedAt=max(前后receivedAt)。quote精确`sourceUrl,evidenceVersion,quote`（逐字、非空、最多8000 UTF16单元）。OBSERVED_NEW的from=null；MODIFIED的from是前一观察中同replyId正文引用。to总为该replyId的后一正文引用。不得伪造“以前没有”的引文。
- 仅已验证非空同authorPublicId、且两次sourceContext存在时比较；不推断跨作者关系。按observedAt毫秒分组和先后观察处理，锚点以前不产生事件；同毫秒出现不同正文/作者/作者回复集合则gap且重建基线，不按到达先后猜方向。作者回复集合按replyId排序，不因排序/计数变化生成事件。
- 相邻可比较组：同ID且body变化→MODIFIED，前次未读到ID而本次读到→OBSERVED_NEW（标签“首次观察到作者回复”，不是刚发布）；相同body不产生事件，published_at/读取计数变化不冒充内容变化。前次存在而本次未读到仅gap，不能判删除。缺上下文/作者变化仅gap并重建基线；普通两次无上下文不制造作者gap。所有author时间仍不得晚于观察/早于原文发布。
- 保留来源/owner/租户/锚点/200观察/100版本限制、稳定事件ID、关键引用和完整事件集合验证；重复查询不重复计“新”事件。原CONTENT逻辑与旧V1/V2客户端验证不放宽，作者事件引用按对应replyId与版本查正文，不能用source.body检验。
- 每日简报内部显式启用作者投影，正文/作者事件合并选当日最近一项，VERIFIED_CHANGE表示库内证据变化而非商业需求确认；保持原简报DTO与当日时区/去重/来源归属。理由区别作者回复变化与正文变化，不说项目已关闭。
- UI复用现有EvidenceTimeline布局，不重设计页面。V3仍显示观察与纳入锚点；单独作者回复变化区，新增from显示“此前留存范围内未读到该回复”（非blockquote）；保留原文和检测时间、未知编辑时间；正文无变化不能遮掉作者事件。普通固定引用/触达权限不变。

### Task 1: 作者变化投影、协商与简报（backend Agent）

**Files:** `pilot/source_content_changes.py`（可新建`pilot/source_author_changes.py`隔离纯算法）、`pilot/opportunity_research.py`、`pilot/opportunity_research_api.py`、`pilot/opportunity_brief.py`；新增`tests/test_source_author_changes.py`及必要`tests/test_opportunity_research_api.py`/真实PG专用测试。不要改desktop、monitor、迁移、Task2/root文件或docs，不commit/push。

**Interfaces:** `project_source_content_changes(..., include_author_changes=False)`与`load_source_content_changes(..., include_author_changes=False)`默认原返回；true按Global Constraints增加版本字段/authorChanges并替换旧泛作者gap。`OpportunityResearchService.timeline(claims,binding,timeline_schema_version=2)`（实际类名以repo为准）仅2/3；HTTP旧请求调用旧两参数形态不破坏现有fake services，新请求传3；简报load传true。

- [ ] RED：有效空作者集合→新回复→同ID修改→重复；不完整范围首次读到仍OBSERVED_NEW，减少只gap；顺序/第三方计数变化无事件；空/错作者/同毫秒冲突/早于锚点不伪造变化；超限失败。
- [ ] 实现有界纯投影，复用现_source_content_changes时间规范/引用截断；新字段只在opt-in出现，legacy输出不变。稳定ID绑定锚点/前后观察/版本/replyId/kind，内容不放进日志。
- [ ] API定向RED/GREEN：旧请求V2、新请求V3、错误版本/字段拒绝、身份门禁仍生效。
- [ ] 真实隔离PG/HTTP覆盖已纳入同来源作者更新后，V3引用命中保留版本、旧V2仍原形状、当日brief仅一次且是对应author事件；另一owner不可见。模型/来源输入合成，数据库/HTTP用真实限制角色。可启动既有自有容器`yike-research-resources-task1-pg`并新建独立DB，不输出密码/URL；保持数据等root核对。
- [ ] 给root报告：文件、exact命令、RED/GREEN、已知未验及安全复用DB名；不扩测试整仓，不真实provider，不计“已获得客户需求”。

### Task 2: 严格客户端读取与可见时间线（root）

**Files:** `desktop/src/shared/opportunityResearchApi.ts`、`desktop/src/renderer/domain/opportunityResearch.ts`、新`desktop/src/renderer/domain/authorChanges.ts`（需要时）、`desktop/src/renderer/services/opportunityResearch.ts`、`desktop/src/renderer/pages/opportunities/EvidenceTimeline.tsx`、`desktop/src/renderer/pages/workbench/OpportunityBrief.tsx`；对应定向测试。

- [ ] RED：原V1/V2仍可读、V3可读并逐字展示新增/修改；重复/漏事件/错replyId/错引用/跨作者/未来时间拒绝。全量期望事件由留存版本重新计算，不能只检查服务器提供的几个事件。
- [ ] 添加严格V3 schema与作者验证，保持V2正文校验并重用引用检验。service只对明确旧版422降级一次，取消/超时/401/解析失败不降级。
- [ ] UI复用既有组件呈现作者前后引文、来源版本、观察/检测时间及新增未知前文，非作者普通时间线不加空壳；每日简报“留存原文对比”改“留存来源证据”。
- [ ] Node24/Vitest定向及tsc，跑新旧timeline/service/fixed IPC边界。与backend组合至少一份真实HTTP响应交给正式TS parser核验；若可行用现有测试UI harness验证，不拿合成数据当平台结果。

## 验收与交接

- [ ] 根整合/定向交叉验证，固定SHA独立审核；代码与文档正常合main，不重复构包/部署。
- [ ] 记录版本、实际通过范围、未验平台/Windows/客户闭环；跨轮来源游标继续留在完整Goal，不以作者事件子项完成关闭目标。
