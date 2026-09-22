# 内部公开原文工具

这是研究 Worker 的工具，不是客户服务地址，也不是全网搜索已经接通的声明。客户只登录意客；模型密钥与工具配置由服务端持有。

## 当前入口

安装可选工具依赖（不强升现有 Web 依赖）：

```sh
uv sync --frozen --extra research
uv run --frozen --extra research python -m pilot.research_tools --max-reads 5 --max-seconds 60
```

第二条命令启动标准 MCP stdio 服务，供父级研究 Harness 通过 stdin/stdout 使用，终端等待输入是正常状态。不会监听 HTTP 端口，不读取平台 Cookie、Codex 登录态、业务数据库或模型密钥。宿主应使用独立环境启动，不把主服务凭据传给工具进程。

默认只有 `read_public_page({"url":"https://example.com/"})`：返回实际提取的标题/原文、读取时间、文本SHA256、读取范围 `PUBLIC_PAGE_TEXT` 与 `UNREVIEWED` 标识。读取不是事实核验或需求判断；明确网页声明按下文保留，不断言已核验买方身份或需求日期。宿主明确启用下述搜索模式后增加搜索工具；两种模式均没有登录、写库、审批或发送能力。

### 网页标注证据增量（2026-09-22，未发布）

可选 `page_metadata` 使用 `schema_version=public-page-metadata-v1`，严格包含 `publication` 与 `author`（至少一项非null）。只读取当前HTML head的 `meta property/name=article:published_time/datepublished/author`；不猜正文中的任意日期、不把修改时间、HTTP Date或采集时间当发布时间，不解析脚本/评论/附件。多项冲突、非法、未来或过多声明不补猜。缺失时仍兼容旧六字段或附links结果。

- `publication`：`raw`、`declaration`、`value`、`precision`。DATE为真实日历日期；LOCAL_SECOND为未注明时区的秒级本地时间；SECOND仅接受明确Z/±HH:mm时区并规范为UTC。保留原值，不替DATE补午夜，不给LOCAL_SECOND猜时区。UTC+14只用于拒绝不可能的未来本地时间，不是赋予时区。
- `author`：`raw`、`declaration=author`、`value`，为网页声明的公开名称，不当作平台用户ID/需求发言人。
- READ正文与正文SHA不变，完整工具结果摘要覆盖声明；候选 `dynamic-public-read-v2` 将声明纳入原文内容版本和不可变留存。仅SECOND投影 `published_at`，`author_public_id`仍未知。网页的人工归属/时间补证、重新判断与纳入门禁对v1/v2同样适用。
- 候选原文、固定机会证据显示声明原值、日期精度与身份限制。新字段不静默剥离来迁就旧客户端；发布需要同批服务/客户端，旧记录与摘要不变。

这是特定声明格式的证据补全，不意味着所有站点的作者/时间已提取、资格截止已核验或真实商机已通过。

2026-09-13 导航增量：成功原文可携带 `links`（最多50个规范化、去重的匿名HTTPS锚点URL）。它们只供同任务继续读取，不是已读原文或采购证据。旧六字段结果仍兼容；字段不能由模型自行补写。动态客户任务搜索单类上限为min(10,sources-1)、读取单类上限为sources-1，保证搜索不能用光共同额度、至少留一次READ尝试；两者不是独立预算，总量始终受同一持久来源许可限制，不锁死纠偏搜索可用的余额。

`max-reads`（1–100）与 `max-seconds`（1–1800）由宿主指定，工具参数不能修改。尝试前计数，同URL成功/失败本进程内缓存重放；多个请求串行处理。进程重启后的持久去重和任务预算仍必须接现有账本，不能依靠此缓存结算搜贝。

## 读取边界

- 仅匿名 HTTPS/default443，支持正常公开域名，不要求加入网站目录。
- 拒绝私网DNS和常见凭据查询参数；固定已验证IP连接并保留原域名TLS验证；无代理、Cookie、跳转或自动重试。
- 每页最多20秒（包括DNS），1MiB响应正文、60,000字符提取文本；超限/超时明确失败，不截取后声称完整。
- UTF8/ASCII HTML或纯文本。HTML脚本、样式及可识别隐藏节点不计正文；不是浏览器渲染，不能保证CSS可见性、登录后内容或动态评论完整性。
- `observed_at`只是本次读取时间，不刷新需求原始时间。
- 读取子进程使用隔离Python和空环境；超时或中断回收子进程。仅固定错误码进入协议，不输出底层异常正文。

专用连接器保留：登录、评论展开和增量监测优先复用已有平台连接器及有效缓存；通用研究用于扩展未知来源。专用路径减少重复浏览和模型操作的潜力需以实际用量验证，不预先承诺节省比例。

## 验证与接续

### 最新实际验证（2026-09-13）

`09d8cdb` 新真实批次已经区分研究与普通判断：独立单原文任务1搜索/1读取/3研究模型成功，mission COMPLETED并入库1，后续assessment UNKNOWN；该原文超期，人工/独立审查EXCLUDE，不计好线索。前一买方批5搜索后模型UNKNOWN，未进入READ。两次合成判断诊断一拒绝一通过，输入/路径不同，不证明timeout或修复。[最新证据与后续定位](qa/DYNAMIC_RESEARCH_REAL_PROBE_20260913.md#买方入口与单原文诊断同日绑定-09d8cdb)。下一优先普通判断阶段的固定故障类别/耗时/非敏感校验定位与真实完成，不能再把研究完成写成整个任务成功；不重放旧UNKNOWN或本页。

确定不可读换源最终代码 `e32df5a` 已获独立整批及一次差量 Spec/Quality PASS：[唯一计划与验证记录](superpowers/plans/2026-09-13-known-read-outcomes.md#evidence)。HTTP404/410、明确不支持的媒体类型和超限会持久记录为 FAILED，再允许同预算内不同来源；权限、限流、未知结果及缺失/畸形MIME仍停止，失败不计入成功原文。受限PG的失败→成功原文→候选→v4客户端路径已过本地夹具验证，**不是实际提供商或持续商机效果证据**。后续真实批次仍须改善买方入口与阅读优先，并记录准确失败原因；不重放旧UNKNOWN任务。

客户动态接线后，真实 Codex/豆包/搜索运行暴露并修复了传输元数据准入和 READ 结果包两个接口错误（`c2169de`、`5c311bb`）。实际记录为 4 次模型成功、9 次搜索成功、首个 READ UNKNOWN、0 候选；第二项修复仅有协议与受限 PG 定向验证，未追认真实研究全链成功。[唯一探针、本地 Skill 小样及后续缺口](qa/DYNAMIC_RESEARCH_REAL_PROBE_20260913.md)。本地样本 0 可交接、2 待核，非严格 A/B；下一步为实际原文入账/判断、阅读优先策略和授权评论深度，而非继续堆固定网站。下方旧阶段“未接客户/未运行”描述保留对应历史边界，不代表最新源码状态。

### 内部 Codex 执行入口

`pilot.codex_research_worker.run_public_read_mission` 使用明确指定的 Codex 可执行文件和安装本包的 Python；适用 POSIX 服务端，不是 Windows 客户端执行器。宿主在内存中传入模型密钥、模型名、公开阅读任务和资源上限。当前适配仅固定火山方舟 Responses 地址，不支持调用方指定任意模型服务地址；Qwen 尚未实测或启用。

```python
from pilot.codex_research_worker import run_public_read_mission

result = run_public_read_mission(
    "用提供的工具读取 https://example.com/，仅依据原文说明标题。",
    codex_binary=approved_codex_path,
    python_binary=research_python_path,
    api_key=secret_from_host,  # 宿主凭据存储提供；不得写入任务文本或日志
    model=approved_model,
    max_reads=1, max_requests=2, max_seconds=60,
    cancelled=host_cancelled,
)
```

内部临时桥接器只监听带随机令牌的本机端口，将 Codex 的命名空间工具协议转换为供应商兼容形式。真实供应商密钥只留在桥接器内存，不进入 Codex 参数、工作目录或工具环境。执行器使用临时工作区、独立 Codex 状态目录、禁用用户配置和无关工具；这不替代正式部署时逐租户容器和网络隔离。

返回 `COMPLETED/FAILED/CANCELLED`、固定错误码、实际 MCP `reads`、`read_failures`、独立模型 `summary`、Token 用量和供应商请求回执。模型自述不生成原文证据；没有成功工具读取则不能完成。失败/取消可保留此前已读取事实，但仍是失败/取消，缺失用量保持未知。不得直接把模型摘要发布为已复核商机。

此入口尚未绑定客户 API、持久任务许可、搜贝账本或数据库证据事务，不能由客户直接调用，也不等于全网搜索已经接通。任务限制是本次执行保护，不是跨任务配额或计费依据。当前实现及真实调用证据见[执行器批次记录](superpowers/plans/2026-09-12-domestic-harness.md#evidence)。

```sh
uv run --frozen --extra dev --extra research pytest -q tests/test_open_web_reader.py tests/test_research_tools.py
```

协议测试使用官方SDK真实会话和stdio子进程；网络替身仅用于可重复的故障/边界测试，不算真实需求。未安装research依赖时协议测试显式跳过。

后台优先接Codex开源Harness与国产模型API，但工具协议不依赖模型品牌。旧读取工具证据集中在[读取批次](superpowers/plans/2026-09-12-open-web-research.md#evidence)。后续仍须完成 Skill 多轮业务研究、现有签名任务/许可/证据事务、客户进度和真实效果验证；不得用本工具取代这些交付。

### 自主搜索后读取

新增内部 `run_public_research_mission`，参数沿用只读入口并增加宿主内存中的 `search_api_key`、`max_searches`（默认3）。默认最多5次读取、8次模型请求、120秒。模型只能调用 `search_public_web` 和 `read_public_page`，搜索使用固定 Serper 服务；搜索进程通过私有 stdin 接收供应商密钥，MCP 只持有临时本机端口与随机令牌。

```python
from pilot.codex_research_worker import run_public_research_mission

result = run_public_research_mission(
    confirmed_public_mission,
    codex_binary=approved_codex_path,
    python_binary=research_python_path,
    api_key=model_secret_from_host,
    model=approved_model,
    search_api_key=search_secret_from_host,
    max_searches=2, max_reads=2, max_requests=6, max_seconds=90,
    cancelled=host_cancelled,
)
```

结果新增 `searches` / `search_failures`，索引摘要、索引日期提示和原文证据分开。搜索模式只允许读取本轮实际命中URL，以及本轮成功原文返回的已验证公开链接；同查询缓存不会算新发现。搜索空结果与搜索失败分开；无实际原文不得完成，返回 `no_verified_searches` 或 `no_verified_reads` 等固定错误码。读取边界仍如上，不额外支持HTTP跳转、JS或登录。

COMPLETED 仅表示执行器正常结束并取得搜索和原文，不表示近期、匹配、已复核或可联系。任务时效、行业判断、持久许可、客户隔离与证据入库仍需通过产品链路接入。一次真实成功及前次失败集中在[搜索批次证据](superpowers/plans/2026-09-12-public-search-research.md#evidence)，不得把这些旧帖作为新线索推给客户。

## 与原本地 Skill 对照（2026-09-13）

用户明确要求参考效果较好的本地研究方法。本轮完整读取本地 `ai-project-lead-research` 及三份引用、`yike-opportunity-research` 及交接引用；与仓库规则实际 diff，不根据名称推断加载。

仓库 `skills/ai-project-lead-research-v1` 已保存主要本地规则：入口仅增加版本/输入输出约定；搜索覆盖与评估两份引用逐字相同；资格引用仅增加事实/推断分开说明。**不是规则丢失，而是执行链此前没有完整使用。** `candidate_assessment_model.py` 加载入口与资格规则供候选判断；对照基线 `ba0ae76` 的 `codex_research_worker.py` 仅生成工具/预算指令。下表保留当时差距，新增接线状态见后文。

| 原方法 | 新通用执行器当前差距 | 接续要求 |
| --- | --- | --- |
| 买方业务问题→交付物→寻源动作，使用原文新词 | 有买方/社区偏好，未加载覆盖规则 | 版本化加载研究规则；行业词由确认画像驱动，不限定AI术语 |
| 主帖、需求评论、失败替换、在手渠道项目四条路径 | 当前只搜索索引及读匿名页面 | 通用工具与专用连接器分工；未展开评论就不报告已覆盖 |
| 广告多/旧帖多/同作者集中时换假设或入口 | 有界调用但无持久覆盖/损耗记录 | 确切查询、实际独立来源、失败与下一假设进入运行记录；预算不允许时停止并保留下一方向 |
| 作者原始日期/本人更新、关闭反证和最小联系路径 | 实际原文与摘要分开，但缺业务资格流程 | 沿已确认策略执行时效/采购形态/排除检查；索引时间不是需求时间 |
| 历史排除、同项目多来源合并、研究等级与操作状态分开 | 新入口无客户历史与持久去重上下文 | 复用现有客户账本，未知不报净新增；有业务行动但缺操作证据留待复核 |
| 一个原帖细节＋一个容易回答的问题 | 本批没有新草稿流程 | 复用既有短草稿/确认机制，不由通用搜索直接发送 |

移植原则：不直接让服务端读取个人 Skill 目录，不把本地30–60分钟建议覆盖宿主实际预算，不将自用AI画像、旧政府/招标排除项写成全行业硬规则，也不把研究状态 SEND_READY 当用户发送批准。全行业通用判断参考本地 `yike-opportunity-research`；正式采购窗口规则只在对应策略允许且有原始文件时采用。

### 本批接入状态

内部 `run_public_research_mission(..., research_context=host_snapshot)` 已加载上述四份规则及宿主传入的业务画像、时效、排除条件、部分历史；上下文走 stdin，不进入参数或环境变量。具体必填字段和上限见[上下文合同](superpowers/specs/2026-09-13-research-skill-context-design.md#上下文与执行)。调用方省略参数时保持旧工具入口；显式传空或非法值则失败，不悄悄退回无画像搜索。

结果附宿主生成的 `research_binding`（规则版本/摘要、上下文摘要、画像/策略版本），用于追溯实际使用了什么，**不证明已获客户确认或发送批准**。缺规则失败；生产仍须从受认证客户任务加载和核实画像、许可与历史，而非接受任意客户对象。本批尚未接入该产品链路。

真实有界执行在 `f783b3b` 完成：3 次搜索、2 篇原文、4 次模型请求，63.67 秒，**0 条合格机会**。一篇偏企业 DIY 咨询，另一篇是技术负责人招募；不以技术链成功充当销售效果。预算很小、入口偏 V2EX，不能据此证明全网没有需求，也不能证明已恢复本地研究效果。[唯一实施与失败证据](superpowers/plans/2026-09-13-research-skill-context.md#evidence)。

下一步把宿主快照接到现有客户画像/任务/许可/证据事务，同步前端真实进度；研究质量以同一证据快照、同一预算比较旧帖、广告、匿名无预算、需求评论、已关闭/已联系的判断，再比较实际有效产出。**此类模型行为对照尚未完成**，现有离线测试只验证加载/合同/安全边界。前后异时真实查询不称因果A/B；工具链成功与销售认可分别统计。原本地 Skill 保持不变。

### 宿主调用控制（2026-09-13，内部接入层）

内部研究入口现在可显式传 `effect_dispatcher(kind, payload, deadline, perform)`，分别控制 `MODEL`、`SEARCH`、`READ`。这是可信宿主代码，不是客户 JSON 配置，也不是数据库许可。省略参数保留内部旧入口；显式 `None` 或不可调用值在启动前失败。

受控模式的 MCP 原文工具只拿临时 loopback 地址与令牌，经宿主验证“该 URL 确由本任务搜索或成功原文链接发现”，再由本任务专属读取器读取。不同任务关闭互不取消。已处理的查询、原文及失败尝试不重复外部调用；宿主可拒绝、缩短期限或返回已存结果，不能重复启动同一动作、延长期限或返回后再启动动作。配置缺失、非法、拒绝不回退到直连。

已用本地真实 HTTP/stdio 协议和 fixture Codex 进程验证控制链，外部模型/搜索/网页使用测试替身；**不是公网研究、客户 UAT、持久计费或上线证明**。[本批唯一证据](superpowers/plans/2026-09-13-research-effect-gateway.md#evidence)。完成客户同库许可、执行及证据链前不开放新的客户动态研究能力。

## 客户上下文接续（2026-09-13）

新增内部 `CustomerResearchContextStore.load(claims, task_id=..., run_id=...)`，从已确认画像/策略和签名启动任务解析 v2 上下文，保留合法 8000 字多行描述、完整行业策略与固定任务时间。不接受客户端自报 seller/history；重复读取检查当前授权、资料撤销及不可变版本绑定。

同库历史只覆盖本客户、同业务实体候选，区分已知、排除、已联系和关闭；最多30条且明确 PARTIAL，不能据此声称全历史去重或净新增。模型上下文只带有界摘录，不复制私有资料原文。v1 规则字节与调用方式保持兼容。[实现和测试边界](superpowers/plans/2026-09-13-customer-research-context.md#evidence)。

这仍是内部接线基础：下一步接逐动作持久许可/账本、客户执行链和证据入库，而非让普通客户直接调用内部 worker。原 Skill 与产品的同证据预算业务效果对照仍未完成，未宣称恢复本地效果或持续供给。

## 持久调用控制接续（2026-09-13）

`ResearchEffectJournal(resources)`复用已确认任务的资源服务与同一PG，`DurableResearchDispatcher`绑定claims、task/run、实际coordinator generation/owner和context-v2 binding后，可作为内部worker的`effect_dispatcher`。调用方必须先通过正常任务流程取得这些身份与租约，不能从客户JSON直接构造授权；当前没有新的客户调用入口。

每次MODEL消耗MODEL_CALL，SEARCH/READ分别消耗SOURCE_READ；先提交许可与输入，再调用，再原子保存结果。重放只使用原始已验证成功结果；未知/在途不重发、不退款，不跳过未成功序号。取消/失租约后可保存先前已准入事实，但不能继续新动作。模型SSE/usage和原文text/hash保留在隔离账本，敏感字段、携带凭据的URL与文本拒绝保存。[版本、定向验证和独立审核](superpowers/plans/2026-09-13-durable-research-effects.md#evidence)。

下一步必须接客户动态任务supervisor、通用候选提交、判断及现有页面：普通客户仍只登录意客，不需要Codex账号或模型key。旧固定来源不自动升级，公开读取不假装读过登录评论；分类失败后的换源行为与实际效果仍需在完整客户链路验收。
