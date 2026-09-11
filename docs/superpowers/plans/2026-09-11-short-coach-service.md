# 短句教练真实服务接入

> **For agentic workers:** Use subagent-driven-development。用户要求省token：定向测试，整批一次独立审核；不重跑全量或桌面打包。

**Goal:** 已核验商机可经用户确认交给已配置模型生成短句，保留原文引用、原请求和人工采用边界。
**Architecture:** 复用R4 P12、现有服务端模型配置/认证/PostgreSQL。预览披露当前公开原文和人工草稿、配置模型；用户明确确认后才调用一次模型。服务端重读固定原文，验证输入而不信任客户端事实；模型工作不跨SQL事务。
**Stack:** 现有Python/FastAPI/PostgreSQL、Node24/React/Zod。

## Global Constraints

- 已批准 `UI_SHORT_COACH_CONTRACT.md` 和R4界面范围，不增加自动发送、计价、搜贝余额或虚构团队能力。
- 只处理本人可访问的真实商机、已确认画像和OPEN来源；样例拒绝。入参sourceText必须逐字匹配已保存原文，版本、URL、观察时刻全部绑定。
- 只提交当前原文与人工草稿、channel/purpose给模型，不提交客户ID、URL、账号/对象、资料库或凭据。用户点击确认前展示实际模型provider/name与两段文本；手改草稿/切用途/来源/模型配置后旧确认失效。
- 整个生成结果绑定原请求与全文SHA；引用UTF-16[start,end)精确切片。一个问号问题、正文≤120 Unicode字符；PROMISE始终NEEDS_REVIEW，不把引用当业务承诺证明。
- 同原请求只派发一次模型；重复请求返回旧结果或明确处理中/失败，不自动重跑。SQL事务外执行、20秒进程截止/清理、不重试/重定向。未知用量不补零。
- 认证/owner与来源在调用前及结果返回前重验；撤销/来源变化不暴露结果或自动采用。结果有效期5分钟。
- 保留既有未接通/取消/人工修改/比较后采用/保存行为；客户端取消仅停止等待，不宣称退费或服务端撤销。

## Task 1: 后端、模型与受限PG联验（backend agent）

Own files: `pilot/short_coach.py`, `pilot/short_coach_model.py`, `pilot/short_coach_api.py`, `migrations/130_v02_short_coach.sql`, `deploy/grant_short_coach.sql`, `tests/test_short_coach*.py`。Root串行注册迁移、web/ui_api/runtime，不改你的文件。

接口：`ShortCoachService(database, model=None)`；`.preview(claims, raw)` / `.generate(claims, raw)`；`ShortCoachModel(config)` 复用已验证 `OpenAICompatibleCandidateAssessmentModel`（只复用配置，不复用评估prompt）。`register_short_coach_api(router,service,identity,require_session_https)`。

请求 `CoachInput` 为现有 `binding,content,sourceText`；binding保持前端domain/shortCoach.ts字段/命名/顺序，使用UUID、accountScope.version=1、draftVersion正整数、draftHash正文UTF8 SHA256。preview POST `/short-coach/preview` 不调用模型，响应 `{inputHash,modelProvider,modelName,policyVersion:'short-coach-public-draft-v1'}`。inputHash=SHA256(JSON.stringify([binding.accountScope.id,binding.accountScope.version,binding.requestId,binding.opportunityId,binding.profileVersionId,binding.sourceEvidenceVersion,binding.sourceUrl,binding.sourceObservedAt,binding.channel,binding.draftVersion,binding.draftHash,binding.purpose,content,sourceText]))，不改变原文或JSON空白。模型provider=`config.provider`、name=`config.model`，真实配置无效/无模型返回固定501。

generate POST `/short-coach/generate` 请求同CoachInput加 `disclosure:{accepted:true,...preview}`。必须复核其hash与当前模型匹配；模型只接 `{sourceText,content,channel,purpose}` 并返回 `{content,question,quote}`；service验证后合成现有CoachSuggestion完整shape。源证据使用已保存CAPTURED的body/version/public_url和observation.observed_at（比较时允许等价毫秒ISO），复用ContactDraftStore当前事实验证但不保存草稿。sourceText≤8000字符，content≤8000可空，拒绝NUL/非法Unicode。

新增owner隔离的原请求表存requestHash、state和结果/固定错误，不存provider密钥或输入正文。reserve短事务同时持久原请求；该tenant一天最多50次新调用、每次只一调用（安全上限，不是售价/搜贝），序列化quota检查，原请求重放不占新次数；HTTP路径不能传额度。PROCESSING崩溃后原请求永不自动重发；短时busy/固定错误可明确返回。成功结果仅已授权原owner且事实仍当前时读取；原请求冲突不能覆盖。model超时/失败不输出privateexception/context；同日失败也计调用。过期原成功响应不能当新建议。

- [ ] RED：缺失service/model，未授权/错证据/未确认不调model；重复同request只一次；失败不重试；跨owner/撤销/模型配置变化拒绝；UTF16emoji引用正确，含两个问题/虚构quote拒绝。
- [ ] 实现上述有限模块，model参考material_model私有pipe+kill/reap，不改现有material服务。
- [ ] 受限RoleDatabasePG通过真实confirmedstrategy→signedingest→人工核验纳入fixture，注入明确合成model验证preview/generate/replay/factschange/owner。不用管理员或关闭触发器制造成功；清理仅测试合成记录。
- [ ] targeted model tests用受控httpx transport/子进程测试，不联系外部模型。报告原命令/RED/GREEN、边界；追加commit不amend/push。

## Task 2: 普通客户端及确认入口（Root）

- [ ] 新 `shared/shortCoach.ts` 严格wire schema及唯一inputHash；`services/shortCoach.ts`可选preview接口及既有generate，`services/shortCoachClient.ts`普通adapter、固定IPC和client挂载。
- [ ] `useShortCoach`/`ShortCoachPanel`复用现有生成确认弹窗：读取预览→展示model/当前原文及草稿→明确确认才generate，精确同份input（包括requestId）/disclosure。无preview的旧测试adapter兼容现有行为；生产必有preview且必需accepted。预览失败不调用生成。
- [ ] Root注册普通router/runtime与130/grant部署说明；无模型仍501，不构造假建议。
- [ ] 定向adapter/UI反例：预览不调用生成、取消不生成、同输入才可确认、迟到/换账号拒绝、精确binding/UTF16回执校验。
- [ ] Node普通client→HTTP→受限PG→合成model→CoachSuggestion验证，一次renderer构建/类型；无实际平台或外部模型调用。

## Task 3: 收尾

- [ ] 整批独立review＋修复差量；唯一证据更新本计划/合同/任务书，正常推送main、核对SHA、清理本轮临时资源。完整Goal不以此片完成。

## 实施与验证

2026-09-11 实现已落地：后端 `5b150cc` / `d42348a` / `c56def5`，普通客户端与runtime `1610eac`，审核修复 `2519ac8`。上方条目是原计划，不作为额外重跑清单；本节为实际接收记录。

- 已接完整输入预览和显式模型确认，普通IPC/HTTP生成、原请求去重、UTF-16原文引用、人工比较采用。迁移130及最小授权见部署说明。无模型返回不可用，不构造假建议；PROCESSING不自动重发，进程退出不会永久封锁租户的新请求。
- 界面/adapter先RED后 `37 passed`（仅两文件）；类型检查通过。后台专项 `9 passed`，包含受限PG原纳入链、跨owner限额、毫秒时间和受控模型字段；不是实际模型质量验收。
- 普通Node客户端→真实HTTP/runtime→受限PG→合成模型：`tests/test_short_coach_client_postgres.py` 两项通过，内层Node一项实际运行未跳过，确认同请求重放仅一次模型调用。初跑暴露响应微秒时间不兼容，改为毫秒后通过。模型、来源均合成，不代表真实平台或业务线索。
- 一次renderer构建通过（483ms），没有重打Windows/Electron包或跑全量。独立整批审核发现一个P1：reserve事务提交异常漏进程锁；`2519ac8`以外层资源清理覆盖提交及生成，专项故障注入 `1 passed, 2 deselected`，不因提交结果未知调用模型。
- 独立审核对 `2519ac8` 差量复核GO，无未关闭Critical/Important/Minor。尚未实际外发模型、自动发送、部署或完成Windows/客户UAT；完整V0.2 Goal继续ACTIVE。此批不证明内容质量、回复率或商业可售。
