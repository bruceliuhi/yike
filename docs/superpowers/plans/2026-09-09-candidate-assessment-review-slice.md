# V02-04C 原始候选 → 判断 → 人工复核

2026-09-09；IN_PROGRESS；base `f3770a415effa89b459c51e432cc78e9da050bc0`。
既有 V1.0 技术实施，不新增SKU、发送授权或上线声明。复用隔离 `dual-agent-taskboard` / `codex/mac-device-authorization`。
**113预留Mac本片；108/110仍归Win，111/112不可改写。** Win拥有04A/B、05B/C；Mac消费确认策略resolver，不造假画像/策略。05G客户端另行接收，不抢改已有页面。

## Global Constraints

- 原始候选不自动成为已审核商机；模型不设置来源 OPEN、复核人、复核时间或 APPROVED。
- 来源原文、发布时间、作者、URL 由服务端已存版本提供；模型引用必须逐字匹配。匿名、未知日期保留未知；父帖不能冒充评论作者自己的采购证据。
- 业务匹配、购买意向、紧迫性、可行动性分开；等级不是成交概率或发送授权。记录反证与未知，评论/私信独立短句，不编案例或联系方式。
- 新私有记录使用 tenant + owner 复合约束及 FORCE RLS；身份、复核时间来自服务端当前会话，不能由请求体提供 reviewer 或 reviewedAt。
- 请求幂等和原请求查询持久化：相同请求重放原回执，异载荷409；查询不创建请求、不重跑模型。UNKNOWN不自动重试或宣称未计费。
- 锁顺序：会话 → 请求幂等锁 → 画像父行/版本 → 同事务策略resolver → raw candidate → 判断/核验/复核 → 旧商机。事务内不等待模型、浏览器或网络。
- 保存结果及纳入前重查候选revision/source version、CONFIRMED画像、策略和会话；歧义版本不能作为依据。同内容新observation不强制使判断失效。
- 显式人工来源核验记录HUMAN_REOPENED，属于用户声明，不是机器读取证明；不能把已有humanConfirmed偷换成打开检查。纳入需本版本有效核验与最近60天已知原始发布时间。
- INCLUDE在一个connection事务内调用原同事务导入并保存人工证据、映射和回执，失败全回滚。仅批准的最小字段分享到租户商机库，不分享私有原始观察历史。
- 旧商机来源保持UNVERIFIED，不因本片人工声明升级。ALREADY_IMPORTED保留旧机会判断词，本次私有review保留新词，不伪称覆盖旧机会。
- 不启用默认关闭的采集/模型/发送能力；不写密钥、令牌、provider原始异常或私有画像到日志。真实来源/模型、Win ACK、客户UAT和部署未验收就明确保留。

## 设计

运行入口复用版本化研究Skill的SKILL.md和资格证据参考文件，并追加跨行业画像优先及严格JSON合同。规则版本/内容摘要、model/provider随分析保存；打包包含同样规则文件，缺失明确不可用，不读取客户指定路径。不使用旧“唯一Offer意客AI”的评分提示。

模型输入仅服务端画像description（<=8000字符）、当前来源content（总UTF8<=128KiB）。引用字段仅 `title/body/parent.title/parent.body/profile.description`，不得归一化引用。输出不包含作者、日期、URL或核验状态。四维 `businessMatch/intent/urgency/actionability` 各含 `level=HIGH|MEDIUM|LOW|UNKNOWN`、reason、citations（field/quote）。非UNKNOWN至少一处引用；intent/urgency不能只引用画像或父帖。

其他输出：`purchaseType=PROJECT|DIAGNOSIS|PRODUCT|SUPPLY_OR_JOB|UNKNOWN`；`grade=S|A|B+|null`；`decision=SEND_READY|REVIEW|OBSERVE|EXCLUDE`；五项evidence（matchReason/actionSignal/value/risk/unknowns）；summary；draftComment/draftDm。草稿通常25–60字、各最多120字符且不相同；无任何发送授权。OBSERVE/EXCLUDE不凑等级。

模型请求分准备/外部调用/提交三个阶段。成功的同revision/source/profile/strategy/rule/model分析可复用；同版本正在运行返回原请求，不并发增加费用。PROCESSING/SUCCEEDED/FAILED/UNKNOWN持久化，提交期限90秒；到期可标UNKNOWN、拒绝晚到结果。FAILED/UNKNOWN须显式新requestId+retryOf才能重试，同快照最多3次调用，每客户自然日默认最多20次（可信配置可调），不是收费承诺。相同请求回执查询永不自动重跑。

人工来源核验是独立操作：版本binding、requestId、humanConfirmed=true、status OPEN/BLOCKED/EXPIRED/UNVERIFIED、openingMethod DIRECT/IN_PLATFORM、locator、原文中的excerpt、contactMethod COMMENT/DM/PUBLIC_CONTACT/NONE。开放核验24小时有效；服务端记录人和时间。仍不认证买方身份或今天仍开放，日期未知不得补造。

复核沿用P07 ASSESS/INCLUDE/EXCLUDE binding、五项人工evidence、requestId和原review快照；新增sourceVerificationId明确纳入证据。EXCLUDE要原因，不要求OPEN；INCLUDE要匹配assessment和有效sourceVerification。113四张私有业务表：requests、不可变assessments、source verifications、reviews；112仍为唯一raw仓库。另用一张仅含tenant/服务端日期/已预约次数的额度计数表，避免为跨owner计数放宽私有请求RLS或引入读取私有正文的SECURITY DEFINER函数；这是同一预算约束的最小实现细化，不是新产品功能。

旧商机导入source_external_id使用带命名空间的canonical source identity，保留platform/kind/post/comment/site边界，不按昵称或仅父帖ID合并。同来源不同owner可各私有审核，租户共享商机按source/profile只一张。当前判断由projection绑定动态计算；原文变化后历史记录不删，但不作为当前判断。

独立预检细化：新建机会默认UNVERIFIED，ALREADY_IMPORTED不重置旧机会后来人工设置的来源状态；来源核验必须是同绑定最新一条，后续BLOCKED等使旧OPEN不可消费。日额度按tenant与服务端Asia/Shanghai预约日期串行计数，UNKNOWN/坏结果不退回为“未调用”。缓存/在途命中仍保存新requestId到原运行的持久关联；retryOf只能同owner、精确快照的最后失败/未知尝试，并发重试仅一次。原运行期限后不能被晚到结果复活。只读查询可计算已超期UNKNOWN，不能偷偷启动/重跑工作。模型适配器还须在配置的总时限真正取消网络I/O，不能仅依赖httpx分阶段超时或拒绝晚到入库；独立审核已用慢速返回实测确认该差别。

P07的profileId沿用现有客户端含义：`business_profile_versions.profile_version_id`，不是画像父ID（`services/client.ts`）。模型content是最小视图 `{title,body,parent:{title,body}|null}`。COMMENT的raw.title实际来自父视频/主帖（mapper第182行），因此必须投影为title=null、parent.title=raw.title，parent.body保留原父评论正文；POST/PAGE才保留本人的title。其他作者/日期/URL/采集元数据留服务端，不发模型。ASSESS复用有权限的已完成采集证据，不要求旧采集任务继续持有活lease；但当前画像与策略仍须真实确认。

## Task 1: 版本化 Skill 模型和输出校验

文件：新 `pilot/candidate_assessment_model.py`、必要的固定私有模型worker、`tests/test_candidate_assessment_model.py`；必要的 `pyproject.toml` wheel规则文件包含配置。不要改Win search_suggestion_model或旧scorer。独立审核实测原生DNS不受async取消控制后，默认真实provider路径采用最小受控子进程，使DNS/启动/网络都能在时限后终止回收；不是另造DNS或通用任务框架。密钥/画像仅走有界stdin，不入参数/环境/文件/日志，worker核对规则摘要，父进程重验结果；内部网络替身路径不是默认生产路径。

接口：
- `AssessmentModelError(code,status)`固定白名单安全错误，无原始异常context。
- `AssessmentContent`、`validate_assessment(value, *, description, content)`严格拒绝额外字段、类型混淆、坏/空引用、parent-only本人意向、相同/过长草稿。
- `load_assessment_rules()` → `(rule_version,rule_sha256,system_prompt)`，确定性读取打包Skill两文件和固定输出指令。
- `CandidateAssessmentModel` Protocol：provider/model/rule_version/rule_sha256；`assess(*, description:str, content:dict) -> tuple[AssessmentContent,dict|None]`。
- `OpenAICompatibleCandidateAssessmentModel` 显式base_url/api_key/model，敏感repr隐藏；默认30秒、最大60；HTTPS或本机HTTP；单次请求禁重试/重定向，响应256KiB、max_tokens4096。工具调用/截断/拒答/坏JSON/重复键/非有限数不变成功，usage只接受一致非负整数。

TDD先完整输出及逐字证据，再缺维度/造引用/伪造author/time/APPROVED/父帖冒充/长短草稿。仅provider传输边界替身，检查实际请求解析；本地真实HTTP成功与失败，不访问付费模型。验证wheel规则内容一致。报告RED/GREEN/精确commit及边界；只提交所属文件。

## Task 2: PostgreSQL 判断、核验与复核服务

文件：新 `migrations/113_v02_candidate_review.sql`、配套最小权限授权、`pilot/candidate_review.py`、必要局部合同模块、`pilot/db.py`注册、`tests/test_candidate_review_postgres.py`。

`CandidateReviewStore(database, *, model=None, strategy_resolver=None, max_daily_calls=20)`：
- `review(claims,payload)` 分派P07 camelCase ASSESS/INCLUDE/EXCLUDE；额外字段拒绝。默认没配置不能模型调用。
- `verify_source(claims,payload)` 独立人工来源核验及不可变回执。
- `list_candidates(claims, *, query=None,platform=None,status=None,ids=None,review_request_id=None,page=1,page_size=20)` 返回P07页及扩展四维/版本/核验，计数和分页同SQL快照；只显示当前有效assessment。
- `get_request(claims,request_id)`只读原状态，同租户其他owner/跨租户拒绝。

TDD真实最小受限PG：签名raw→ASSESS→核验→INCLUDE→旧机会可读；重复异载荷、两会话并发同版本只一次模型/商机；伪造字段拒绝；网络期间原文/画像/策略/会话变化拒绝提交；歧义/未知日期/过期/坏引用/无核验不纳入；导入失败全回滚；同作者不同评论分开，同来源不同owner不重复机会；服务重启原回执；quota、UNKNOWN显式重试和超时晚结果；新表RLS/FK及重复/升级迁移。用已有fixture及独立最小NOLOGIN角色，不用admin跑服务。PG串行独占，根代理不同时跑PG。

## Task 3: 认证 HTTP、交接与独立终审

2026-09-10 Task2独立反例后的最小读一致性修正：列表用外层READ COMMITTED会话护栏和内层REPEATABLE READ数据视图，原文/画像/请求/逐项策略共用快照及数据库时间。resolver仅使用传入cursor，可行锁，不另开连接或重复会话锁；序列化冲突安全409，不自动重跑。保留前后当前撤销/真实到期检查。两个局部连接和owner全量投影是小规模试用已知成本，后续按实际量优化，不为本片新增通用分页框架。

根代理新增 `pilot/candidate_review_api.py`、ui_api/web最小注入注册、纯HTTP及真实HTTP→PG测试、`docs/contracts/V02_CANDIDATE_REVIEW.md`、QA和唯一任务台账。

- GET `/api/ui/candidates`（P07查询、原reviewRequestId核对）；POST `/api/ui/candidate-reviews`；POST `/api/ui/candidate-source-verifications`；GET `/api/ui/candidate-review-requests/{request_id}`。
- 实际JSON正文<=64KiB；拒绝重复键/重复query/未知字段；HTTPS、当前身份、安全错误、无服务501；默认能力关闭。DB/模型不阻塞async事件循环。
- 真实HTTP→受限PG贯通链路；仅provider边界替身，明确不是商业样本。
- 每任务独立spec/code审，整片独立架构/代码/质量终审；定向测试和相关集成，不反复跑未改桌面全量。
- 精确候选通过后正常fetch/merge/push feature及main，保留Win新增与原checkout用户改动。未接真实策略/平台/模型/Win消费/客户试用，不整卡DONE、不结束Goal。
