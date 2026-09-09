# 05E固定原文证据客户端 Implementation Plan

> **For agentic workers:** Use subagent-driven-development, TDD and independent spec/code/architecture/quality review. 用户要求原文证据首发必须有；沿用已批准R4，不重新设计页面。直接main，根代理唯一Git写入者。

**Goal:** 客户打开现有商机详情，可以看见纳入时固定的真实原文、本人/原帖/父评论归属、逐字引用和不同事件时间；旧数据与读取失败明确区分。此片不把历史证据当作当前可访问或联系批准。

**Architecture:** 复用Mac115和既有认证opportunities.get；一个严格领域解析器被普通详情及R4可选研究结果共同使用，现EvidencePanel增加固定快照分区，保留已有useResource身份/generation隔离与联系侧栏。无新IPC、后端、迁移或整页重建。

**Tech Stack:** TypeScript/Zod、现有React19页面/CSS、Vitest/Testing Library、真实HTTP/受限PostgreSQL和隔离浏览器走查。

基线`a9d18db`，后端来源`26502ee`/`9c71e3b`；[新DTO合同](../../contracts/V02_OPPORTUNITY_SOURCE_EVIDENCE.md)及`pilot/opportunity_evidence.py`为字段权威。Win先收口设备vault/签名的已开工小片，再优先本片；05F签名字节入口/正常运行装配由Mac接续，不能等待接口时继续扩高级密码功能。

独立计划复审：`strategy_client_contract_impl` **Approved**。已修正R4路径不读普通详情会漏掉CAPTURED正文、opportunity缺signal无法兑现取消范围两点，并明确六位微秒与desktop IPC不支持物理取消；这是可实施计划通过，不是本片功能已完成。

## Task 1: 同一严格DTO接入现有读取

Files: 新增`desktop/src/renderer/domain/opportunitySourceEvidence.ts`、`desktop/tests/opportunitySourceEvidence.test.ts`；窄改`domain/models.ts`、`services/contracts.ts`、`services/client.ts`、`domain/opportunityResearch.ts`及相关`tests/ui/client.test.ts`、R4领域测试。主改和审核均不得触碰Mac115/shared store/runtime。

1. 先写RED。严格两形态：`UNAVAILABLE/NOT_CAPTURED`和`CAPTURED/snapshot_sha256/snapshot`，全部对象按合同字段allowlist；raw缺少、null、未知格式及损坏均拒绝。列表没有正文是“未加载”，不创建NOT_CAPTURED；详情必须真实返回该字段。合法原文字节与空白不trim、不拼接；nullable未知作者/发布时间/父评论正文原样保留。
2. 导出`parseOpportunitySourceEvidence(raw, {opportunityId,profileVersionId})`和`OpportunitySourceEvidence`类型。逐项核对schema、商机/画像绑定、五平台/kind、COMMENT角色约束、64位小写摘要、有限正整数版本、带时区可解释时间、引用四维/四字段及quote在对应字段精确存在。所有异常固定为无原文正文的安全错误。总输入上限复用现主进程2MiB，不人为压缩合法长正文；禁止私有画像、完整模型response或完整观察历史混入。
3. `Opportunity.sourceEvidence`单独可选，不覆写旧`sourceObservedAt/sourceEvidenceVersion`或`libraryFacts`。普通list缺字段保持undefined；普通detail明确要求字段，缺失提示接口不兼容/可重试，不伪称没有证据。mapOpportunity与R4的passthrough机会对象若携带sourceEvidence，都必须调用同一绑定解析器；详情以外R4集合不带该字段时保持旧协议可用。**非sample详情如果优先读取的R4 record缺sourceEvidence，必须在同一useResource generation/abort范围内继续读取现有service.opportunity(id)，核对id/profileVersionId一致后补入其固定证据**；普通详情缺字段/失败继续ResourceStatus错误，不降级为“未加载”，确保启用R4不会遮住已存在的CAPTURED正文。
4. snapshot_sha256是服务端已验证摘要，客户端校验格式并保留；本片不新造同步SHA算法或宣称浏览器重新完成加密认证。数据通过现有认证HTTPS/主进程固定请求读取，服务器仍全量验摘要；跨来源缓存/签名离线导出不在本片。
5. 边界测试含错误商机/画像、缺字段、嵌套extra、引用来源错配/空白变化、COMMENT本人标题与原帖混淆、未知时间/null、合法Unicode长文、javascript/data链接不可打开；CAPTURED与当前BLOCKED/EXPIRED并存。时间解析覆盖Python/PG isoformat的六位微秒与时区，不能直接复用仅接受1–3位小数的旧validator。只读详情不请求模型/采集/发送，不暴露已省略的私有画像引文。
6. 现`YikeService.opportunity`窄加可选`signal?: AbortSignal`，client普通详情透传现request的signal；调用前和结果采用前检查取消，防止R4请求结束后已切账号仍启动fallback。Web fetch实际abort，desktop既有IPC没有物理取消协议，本片只做调用前/结果采用的取消与generation隔离，不宣称主进程GET已被撤销、不新增IPC取消框架。页面loader接useResource给出的signal并交给内部boundedRequest/fallback。补切账号时signal.aborted、提前取消不发fallback、IPC迟到不采用的反例。
7. 跑新增解析器与修改的client/R4定向测试、tsc，非作者审核后进入Task2。不改旧假数据使其伪装成真实证据；升级测试fixture须明确TEST来源。

## Task 2: 在现P11/R4原文区呈现并验证

Files: 窄改`pages/opportunities/OpportunityEvidence.tsx`，需要时拆新增`FixedSourceEvidence.tsx`；仅必要时改`pages/Opportunities.tsx`和`base.css`。测试`tests/ui/opportunities.test.tsx`、`tests/ui/r4-opportunity-research-ui.test.tsx`及新的固定原文组件测试；复用ContactEditor的compact模式检查。QA与唯一任务书由根代理维护。

1. RED覆盖原文、AI逐字引用、现人工判断三个区段；本人正文完整可展开，COMMENT分别显示本人评论/原帖标题/父评论与相应作者，不能把父帖采购意图归给评论者。引用保留空白并标注对应字段/判断维度，没公开引用显示“无可展示的公开引用”，不补造。
2. 展示来源发布、采集端观察、服务器收到、纳入留存时间，未知显示未知；版本/摘要与当时模型规则放既有可展开明细。注明这是纳入时历史留存，不证明当前在采购或已允许联系；现来源失效仍保留有权查看的历史快照。115只固定一次纳入，不伪造R4完整时间线或变化数量。
3. 只有明确NOT_CAPTURED才显示“未留存固定原文证据”；缺少字段/网络/权限/损坏继续走ResourceStatus错误及重试，不回退到当前网页或AI摘要补证。旧public_excerpt可作为明确旧摘录保留，不能冒充新固定快照。
4. 原文按钮统一准确命名“查看来源原文”，使用固定source.public_url；父评论链接若有才提供，不把打开父帖宣称已定位评论。保留现openExternal校验、禁止dangerouslySetInnerHTML。无自动打开、联系、入库、模型或采集调用；compact模式保留同样事实边界。
5. 保留现按用户/空间/商机key重挂载及useResource渲染期隔离/generation/abort；补切账号、切商机、迟到响应和错误重试实测，特别覆盖R4优先结果无nested DTO→普通详情有CAPTURED的真实读取分支及两次请求间切账号/错画像/失败。不改原分类或相似研究绑定来假装等价。正文pre-wrap、长词/hash换行，桌面1440×1000与960×600下原文可滚动/展开，无横向挤破联系侧栏。
6. 根代理实际Node客户端→现共享build_app→受限PG读取Mac固定证据，通过普通详情映射，不用fake store替代真实接口；样本来源可为明确合成评论，真实公开采集验收单列。相关UI/领域/服务测试、typecheck、renderer build及生产TEST排除、浏览器走查各按实际证据记录。绑定独立整片审核，正常fetch/整合/push，不将本片称完整05G、真实收发或上线完成。
