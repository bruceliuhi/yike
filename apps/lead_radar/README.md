# Lead Radar

意客 AI 的第一版商机雷达内核。它把搜索目标、三路搜索计划、来源能力、公开证据、机会状态、人工反馈和用量记录放进一个可审计的本地工作台。

## 运行

```bash
python3 apps/lead_radar/server.py --port 8780
```

然后打开 <http://127.0.0.1:8780>。

默认数据库是 `apps/lead_radar/lead_radar.sqlite3`。生产环境要换成正式数据库，并加入用户、权限、密钥托管、队列、连接器和迁移管理。

## API

- `GET /api/health`
- `GET /api/v1/sources/capabilities`
- `GET /api/v1/workspaces/ws_意客AI/dashboard`
- `GET /api/v1/workspaces/ws_意客AI/audit?limit=100`
- `GET /api/v1/workspaces/ws_意客AI/source-proofs`
- `POST /api/v1/workspaces/ws_意客AI/profiles`
- `POST /api/v1/workspaces/ws_意客AI/source-proofs`
- `POST /api/v1/workspaces/ws_意客AI/source-proofs/revoke`
- `POST /api/v1/workspaces/ws_意客AI/tasks`
- `POST /api/v1/business/create_search_task`：创建任务和可检查搜索计划；使用 `Idempotency-Key` 可安全重试
- `GET /api/v1/business/get_search_status/{task_id}`：读取任务、运行实例和来源门禁状态
- `GET /api/v1/business/fetch_search_results/{task_id}?limit=20&offset=0&status=REVIEW`：按任务分页读取候选和证据
- `GET /api/v1/business/enrich_entity/{entity_id}`：读取本地实体解析和关联证据；当前不执行第三方外部增强
- `POST /api/v1/workspaces/ws_意客AI/schedules`：保存周期任务、预算上限、结果阈值和失败策略；不会因为创建任务就自动搜索
- `GET /api/v1/workspaces/ws_意客AI/schedules` / `GET /api/v1/schedules/{schedule_id}`：读取调度及最近运行记录
- `POST /api/v1/schedules/{schedule_id}/trigger`：由受控 scheduler 触发一次到期运行；来源未通过门禁时会持久化阻塞原因
- `POST /api/v1/schedules/{schedule_id}/pause` / `resume`：暂停或恢复周期任务
- `GET /api/v1/workspaces/ws_意客AI/feed?event_type=HIRING&status=NEW`：读取证据绑定的 Feed 时间线
- `GET /api/v1/feed-events/{event_id}`：读取单条 Feed 事件
- `POST /api/v1/feed-events/{event_id}/review`：记录人工复核或忽略
- `GET /api/v1/tasks/{task_id}/plan`
- `POST /api/v1/tasks/{task_id}/start`
- `POST /api/v1/tasks/{task_id}/execute`
- `GET /api/v1/tasks/{task_id}/runs/{run_id}/events`
- `POST /api/v1/tasks/{task_id}/runs/{run_id}/pause|resume|cancel|retry`
- `POST /api/v1/tasks/{task_id}/capture-url`
- `POST /api/v1/tasks/{task_id}/capture-urls`
- `POST /api/v1/tasks/{task_id}/index-results`
- `POST /api/v1/opportunities/{opportunity_id}/reopen`
- `POST /api/v1/tasks/{task_id}/opportunities`
- `POST /api/v1/opportunities/{opportunity_id}/feedback`
- `GET /api/v1/opportunities/{opportunity_id}/action-drafts`
- `POST /api/v1/opportunities/{opportunity_id}/action-drafts`
- `POST /api/v1/action-drafts/{draft_id}/approve|cancel`
- `GET /api/v1/workspaces/{workspace_id}/calibration-batches`
- `POST /api/v1/workspaces/{workspace_id}/calibration-batches`
- `GET /api/v1/calibration-batches/{batch_id}`
- `POST /api/v1/calibration-batches/{batch_id}/items/{item_id}/review`
- `GET /api/v1/evaluation-contract?language=zh-CN|en-US`
- `POST /api/v1/evaluation-contract/validate`
- `GET /api/v1/icp-profiles?language=zh-CN|en-US`
- `GET /api/v1/workspaces/ws_意客AI/entities`
- `POST /api/v1/entities/{entity_id}/merge`
- `POST /api/v1/entities/{entity_id}/split`

业务 API 返回 `api_version`，响应头返回 `X-Request-ID`。这组接口只操作当前本地工作区台账；它不会把 Cookie、密码、第三方 Token 当作参数，也不会因为创建任务就自动搜索、发送私信、发邮件或写入外部 CRM。外部来源仍须通过来源证明、权限、重开、发布时间、限流和保存边界门禁。`enrich_entity` 当前是本地证据解析投影，不能被解释成企业工商、联系方式或第三方画像增强。

GET /api/v1/task-templates?language=zh-CN 或 en-US 返回首批可复用任务模板。创建任务时可以传 template_id 而不传 objective，服务端会把模板目标、条件和模板 ID 编译进同一份 IntentProfile/TaskPlan；模板只降低首次使用门槛，不会改变来源权限和人工复核门禁。

GET /api/v1/integrations?language=zh-CN 或 en-US 返回连接器市场目录，包含授权方式、允许字段、阻断字段和接入前证据要求。目录是声明式能力清单，当前连接器仍明确为 REQUIRES_AUTH 或 REQUIRES_PROOF；它不会把配置项、环境变量或 UI 点击伪装成已接通。

GET /api/v1/product-catalog?language=zh-CN 或 en-US 返回独立于 CRM 的产品模块目录。每个模块声明买方结果、输入输出、当前状态和是否需要外部权利/回写证据，可用于产品包装、报价和生产验收。

GET /api/v1/icp-profiles?language=zh-CN 或 en-US 返回当前首个 ICP `ai_solution_buyer_v1`：AI 解决方案采购方。画像定义正向信号、排除条件、必须保留的证据、评分优先级和试点验收线；创建业务任务时可以传 `icp_id`，未知画像会被拒绝。画像本身是产品假设和验收合同，仍需真实客户访谈与付费试点验证，不能冒充市场事实。

POST /api/v1/tasks/{task_id}/capture-feed 接受用户明确提交的公开 RSS/Atom URL，限制公网地址、XML 类型、大小和条目数量。每条 Feed 条目进入 REVIEW，保留原文链接、发布时间、Feed 内容指纹和可重复计量记录；它不执行社交平台搜索，也不接受 Cookie 或 Token。

GET /api/v1/business/research_brief/{task_id} 和 MCP 的 get_research_brief 会把任务候选、证据缺口、实体关联、状态分布和人工下一步整理成研究简报。它只读本地 task replay，响应明确标记 external_lookup_performed=false、external_actions_sent=false；需要工商、联系方式或第三方画像时，必须另行接入有权利证明的连接器。

GET /api/v1/workspaces/ws_意客AI/readiness 和 MCP 的 get_production_readiness 会返回逐项生产门禁。当前没有真实授权来源、可搜索来源权利、官方回写或回款证据时，status 必须为 BLOCKED，claim_allowed=false；这份报告用于决定下一步验收，不把本地功能测试当成生产就绪。

调度接口负责持久化周期、搜贝预算、最低新增结果数、失败策略和人工审核策略；独立的 worker.py 负责按 `next_run_at` 扫描到期任务、并发幂等触发、执行已通过门禁的授权搜索，并把来源阻塞、证据写入、用量和结算状态落到同一审计链路。worker 可由 supervisor 执行 `.venv/bin/python -m apps.lead_radar.worker --db apps/lead_radar/lead_radar.sqlite3 --once`，或去掉 `--once` 持续运行；没有真实来源 proof 时只记录 BLOCKED_SOURCE。

可选的 Codex/MCP 入口使用本地 stdio：

```bash
.venv/bin/python -m apps.lead_radar.mcp_server --db apps/lead_radar/lead_radar.sqlite3
```

它暴露 `create_search_task`、`get_search_status`、`fetch_search_results` 和 `enrich_entity` 四个基础工具，并继续提供调度、Feed、任务回放和校准评测只读工具。MCP 依赖属于可选的 `research` 组；普通 HTTP 工作台不依赖它。MCP 工具没有发送、登录、Cookie、密码或第三方 Token 参数，也不监听 HTTP 端口。

MCP 还暴露 `create_monitor_schedule`、`get_monitor_schedule` 和 `trigger_monitor_schedule`。调度器目前以 `trigger` 作为清晰的 worker 边界：创建和到期判定已持久化，后台进程需要显式调用该入口；来源未通过生产门禁时会记录 `BLOCKED_SOURCE`，不会把排队当成搜索完成。

MCP 还提供 `get_feed`、`get_feed_event` 和 `review_feed_event`。Feed 事件只从机会证据、重复内容变化或原文重开变化产生，支持 `PURCHASE_DEMAND`、`HIRING`、`TENDER`、`WEBSITE_CHANGE` 和 `COMPETITOR_CHANGE`；每条事件保留来源 URL、摘要、内容指纹和人工复核状态。

任务创建时会生成三条可检查的搜索路径：快速搜索、条件核验、扩展搜索，并给出来源状态和搜贝估算。`cost_estimate.unit` 固定为 `SOUBEI`，`display_unit` 为 `搜贝`，`rule_version` 为 `source-result-v1`；旧版 `estimated_credits` / `credits_used` 字段暂保留作为兼容字段，不代表人民币价格或外部平台收费。机会录入必须有 `title`、`source_url` 和 `snippet`。系统保留来源 URL、原文片段和核验时间；当前外部平台连接器仍显示为 `REQUIRES_PROOF` 或 `REQUIRES_AUTH`，不会用假数据冒充自动搜索。

每条机会会按 `qualification-v1` 生成可解释评分，拆分为场景词、采购动作、企业信号、时间窗、证据完整度和排除词惩罚，并把命中词、复核优先级和下一步写入 `decision.qualification`。评分只用于排序人工复核，`permission_granted` 永远为 false；来源权利、原文重开和人工确认仍由独立门禁决定。

机会列表和详情支持 `language=zh-CN|en-US`，在不修改原始证据、状态或评分的前提下附加 `presentation` 展示层，提供状态、来源类型、判断码和资格优先级的本地化标签；不支持的语言会返回明确错误。

人工录入即使提交了 `evidence_level=VERIFIED` 和 `source_permission=allowed`，也必须额外提供 `manual_override: {status: "SEND_READY", actor, reason, confirmed: true}`；系统会把覆写写入证据元数据和审计事件。没有该覆写的记录不会进入联系队列。受控 URL、授权搜索和索引导入继续默认 `REVIEW`，必须经过原文重开和人工反馈。

机会反馈支持 `CONTACTED`（已联系）、`DEFERRED`（暂缓）、`HANDOFF`（转人工）、`DUPLICATE`（重复）和 `UNSUBSCRIBED`（退订/禁触达）。进入这些状态会取消尚未发送的动作草稿；`DO_NOT_CONTACT` 是锁定状态，除重复记录退订外，普通反馈不能重新放行。

机会还会进入保守的实体解析层：导入记录明确提供 `entity_name` / `company_name` 时建立企业或组织实体；没有实体名称时，只在来源 URL 主机足够稳定时按官网主机建立关联。小红书、抖音、微博等社交平台主机不会被当成企业官网，标题和作者昵称也不会单独创建企业实体。同名实体如果对应不同官网主机会保持分离，避免把不同公司的公开信号错误合并。每张机会卡返回 `entities`，包含实体、主机、置信度、解析原因和关联证据。

机会列表、机会详情和业务搜索结果支持 `language=zh-CN|en-US`。`presentation` 只翻译状态、来源类型、决策代码和评分优先级；原始标题、原文片段、来源 URL、发布时间和证据 metadata 原样保留，避免翻译层覆盖可审计证据。当前工作台默认中文，多语言导出与完整界面切换仍是独立待办。

四类社交公开来源已注册为同一来源策略：`xiaohongshu_public`、`douyin_public`、`bilibili_public`、`zhihu_public`。用户侧发现可以不登录，第一层只接受用户明确提交的公开 URL，并在证据元数据中记录 `platform`、`source_family`、`capture_layer`、`end_user_login_required` 和 `server_authorization_required`。这些字段只描述来源边界，不授予抓取权限；四平台的自动搜索仍保持 `REQUIRES_PROOF`，需要平台条款、频率、发布时间、原文重开、保存边界和重试幂等证明后才能接入。

校准批次用于把一批候选交给人工复核，并记录模型/规则预测与人工金标准的差异。创建批次时可以传 `opportunity_ids`，也可以让服务按 `REVIEW → OBSERVE → SEND_READY → EXCLUDE` 的顺序选择最多 `target_count` 条当前工作区机会；目标数量必须为 1–500，机会只能来自当前工作区且不能重复。复核标签为 `VALID`、`INVALID`、`DUPLICATE`、`OBSERVE`、`NEEDS_EVIDENCE`，默认会写入既有反馈事件并同步机会状态；传 `apply_feedback:false` 只保存校准记录，不改变机会状态。批次返回覆盖率、人工复核数、准确率、误报/漏报数，以及对用户提交公开网页的重开率。重复复核会保留新的审计/反馈事实，不能当作幂等发送。

校准指标只反映当前批次中已录入的机会和人工标签，不代表平台召回率、商机成交率或跨行业效果。样本必须来自真实授权运行或明确的用户提交来源；fixture、静态页面和预置 URL 不能作为生产校准证据。正式发布仍需按 CP-06 记录真实来源 capability、生产数据库/恢复、HTTPS 和客户验收。

评测接口 GET /api/v1/calibration-batches/{batch_id}/evaluation 会输出相关性、证据完整度、原文重开率、实体关联与重复风险、搜贝成本和任务/人工复核延迟。报告同时列出 source_kind、已批准来源权利、样本量、不可计算指标和 quality_gate；没有 30 条人工样本、已批准授权来源或完成任务时间时会明确 BLOCKED。cost 只表示搜贝账本，不是人民币报价；报告默认 not_a_public_benchmark=true。MCP 通过 get_calibration_evaluation 提供同一只读结果。

评测集导入前应先读取 GET /api/v1/evaluation-contract。`lead-radar-evaluation-v1` 规定数据集版本、权利证明引用、来源 URL、发布时间、原文片段、系统预测、人工金标准、复核理由、原文重开和内容指纹；同时明确禁止把 Cookie、Token、联系人字段或私信内容放进评测集。契约状态为 `CONTRACT_READY`，`benchmark_claim_allowed=false`，只有真实授权样本达到 30 条、全部复核、重开合格、准确率至少 80%、误报率不超过 20%、权利证明完整且外部动作数为 0 后，才允许把评测报告作为公开基准候选。MCP 通过 `get_evaluation_contract` 提供同一只读契约。

POST /api/v1/evaluation-contract/validate 接收 `{dataset, samples}` manifest，只做无副作用校验：返回 schema 是否有效、行业/来源分布、标签准确率、误报/漏报、重开率、权利证明引用覆盖率和阻塞原因，不写入数据库、不访问来源、不发送外部动作。MCP 的 `validate_evaluation_manifest` 提供同一校验器；校验通过仍不等于已经发布公开 benchmark。

机会池支持 GET /api/v1/workspaces/ws_意客AI/opportunities/export.csv，可按 status 过滤，返回带 UTF-8 BOM 的证据 CSV。导出字段固定包含来源 URL、原文片段、来源类型、证据等级、来源权限、实体关联、重开次数、系统判断和状态，不会凭空增加联系人字段；严格 API 部署下该路由也需要 business_api API Key。

机会详情会同时展示证据快照、系统判断、来源权限、人工反馈和审计时间线；详情页只帮助人工复核，不会把查看动作变成联系或发送许可。

机会详情的 `background` 字段只汇总本地实体解析和已入账机会信号，状态为 `LOCAL_EVIDENCE_ONLY`；它会返回实体名称、官网主机、关联机会数、已知来源主机和观察信号，并明确 `external_lookup_performed=false`、`contact_data_returned=false`。工商、联系方式和第三方组织资料仍需另行接入有权利证明的背景连接器。

总览页的“审计与用量”读取同一工作区的审计事件和用量账本，只读展示任务、证据、反馈和动作草稿的实际变化。每条来源尝试带有 `source_id`、`outcome`、`unit`、规则版本和元数据：新结果为 `SUCCESS`（当前 1 搜贝），重复为 `DUPLICATE`（0），无结果为 `NO_RESULT`（0），来源失败为 `FAILED`（0）。同一工作区内重复的幂等键只返回原记录，不会再次增加任务用量。`credits_used` 汇总来自用量账本，兼容旧字段并按搜贝计，不代表人民币价格、平台搜索已经成功或外部触达已经发送。

跟进草稿只能从 `SEND_READY` 机会生成，渠道为 `PUBLIC_REPLY`、`EMAIL`、`FEISHU_TASK` 或 `CRM_TASK`。生成时绑定当前证据 ID，默认状态为 `DRAFT`；审批必须显式提交 `confirm:true`，只记录人工批准事实，不调用平台发送器、不写入外部 CRM，也不会把审批当作已发送。重复请求可使用 `Idempotency-Key`，同一机会和渠道不会重复生成未取消草稿。

实体主档支持人工合并和按单条机会拆分。操作会把关联关系写入审计事件，并保留机会原始证据；“合并”只移动机会与实体的关系，“拆分”只改变选中机会的实体归属，不会删除来源内容。

校准批次把一组机会的系统判断冻结为 `predicted_label`，由复核人填写 `gold_label`、备注和时间，计算覆盖率、准确率、误报、漏报与公开页面重开率。默认目标数量为 30 条；校准反馈可以回写机会状态，但不会修改原始来源证据。校准指标是效果验收材料，不代表样本已经来自真实授权平台。

`capture-urls` 接受最多 50 个用户明确提交的 URL，逐条返回成功项和失败项；重复 URL 使用任务级幂等键，不会重复计费。它是受控导入入口，不等同于平台搜索连接器，也不会自动扩大抓取范围。

`source-proofs` 是工作区级的来源证明登记入口。它只保存 `proof_ref`、提供商、HTTPS endpoint、外部 proof artifact 的 SHA-256、检查时间和 proof gates，不保存原始 Cookie、Token 或 artifact 内容；相同 `proof_ref` 重复提交必须是同一份声明，修改会被拒绝。登记动作本身不等于平台授予权限，生产环境仍需要受限的运营权限和外部 artifact 审核。`source-proofs/revoke` 会把 proof 标记为 `REVOKED` 并立即阻断后续索引导入，保留撤销审计，不能通过重复登记自动恢复。

`index-results` 接受服务端搜索索引或合规数据供应商返回的标题、摘要和公开 URL。请求必须带 `provider`、`query`、带时区的 `retrieved_at` 和已登记的 `proof_ref`；系统会按提供商匹配 proof、去重、记录平台来源，并强制写入 `REGISTERED` proof 元数据及 `search_index_snippet` / `INDEXED_SNIPPET` 证据状态。索引摘要永远进入 `REVIEW`，必须重新打开原始 URL 并由人工确认，不能直接生成联系草稿。没有命中时可提交 `items:[]` 与 `result_status:NO_MATCHES`，系统记录一次已完成搜索和零候选用量，不把访问失败伪装成无结果，也不按完整结果收费。用户不需要登录小红书、抖音或 B 站，但服务端仍需拥有可审计的索引来源权利。

`reopen` 只对受控公开 URL、授权搜索 API 和搜索索引候选执行。它访问候选的 HTTPS 原文 URL，追加当前页面快照、内容指纹、来源平台和原索引 `proof_ref`，并把判断更新为 `REOPENED_SOURCE_NEEDS_REVIEW`；重开成功不会自动变成 `SEND_READY`，仍需人工确认相关性、发布时间、来源使用权和触达资格。

任务运行实例现在会记录创建、来源阻塞、暂停、恢复、取消和重试事件。重复执行同一状态操作不会追加重复事件；重试会创建新的运行实例并保留上一实例 ID，方便回放失败原因。运行控制和日志已经具备，真正执行搜索仍必须等来源连接器通过权限、频率、发布时间和证据重开验收。

授权搜索 API 适配器使用以下环境变量：`LEAD_RADAR_SEARCH_ENDPOINT`、`LEAD_RADAR_SEARCH_TOKEN`、`LEAD_RADAR_SEARCH_PROVIDER` 和 `LEAD_RADAR_SEARCH_REOPEN_PROOF=true`。即使布尔开关为 true，仍必须绑定 proof artifact：`LEAD_RADAR_SEARCH_PROOF_REF`、`LEAD_RADAR_SEARCH_PROOF_SHA256`、`LEAD_RADAR_SEARCH_PROOF_CHECKED_AT`、`LEAD_RADAR_SEARCH_PROOF_ENDPOINT`、`LEAD_RADAR_SEARCH_PROOF_PROVIDER` 和 `LEAD_RADAR_SEARCH_PROOF_CHECKS`（JSON 中 `url_reopen`、`published_at`、`save_boundary`、`retry_idempotency` 均为 true）。接口必须返回 `{"items": [{"title", "source_url", "snippet", ...}]}`；系统会限制响应体大小、只接受 HTTPS URL、校验必填字段、按 URL+标题去重，并把 provider 结果先放入 `REVIEW`。当前代码提供适配器和执行门禁，未配置真实授权服务或完整 proof artifact 时不会宣称来源已接通。

`capture-url` 只访问用户明确提交的公网 URL，拒绝内网地址、非标准端口、带凭据 URL、非 HTML 页面和超过 1 MB 的响应。系统只保存正文摘要和内容指纹，结果默认为 `REVIEW`，不会因为页面抓取成功就判断为采购意向。

## 当前生产门禁

API Key 通过 POST /api/v1/workspaces/ws_意客AI/api-keys 创建，明文只在创建响应展示一次；数据库只保存哈希和前缀。对外提供业务 API 时设置 LEAD_RADAR_REQUIRE_API_KEY=1，并使用 X-API-Key 或 Authorization Bearer 请求头。

GET /api/v1/workspaces/ws_意客AI/usage 返回自然月用量、剩余额度、请求数和按操作汇总；POST /api/v1/workspaces/ws_意客AI/quota 设置自然月额度和硬门禁。创建搜索任务、实体增强和监测调度按动作记账，查询类请求免费但仍写入请求 ID 和审计事件；重复幂等请求不会重复扣动作费用。POST /api/v1/api-keys/{id}/revoke 可撤销 Key。

Key 管理和额度接口只适合绑定本机或接入已有管理员会话的控制面，不能在没有管理员认证时直接暴露到公网。

控制面鉴权使用独立的 `LEAD_RADAR_ADMIN_TOKEN`，请求头为 `X-Admin-Token`；它与客户 API Key 分离，不能用客户 Key 创建、列出、撤销 Key 或修改/读取额度。开启 `LEAD_RADAR_REQUIRE_API_KEY=1` 时必须配置该管理员令牌，即使服务只监听回环地址也会拒绝无令牌请求。未开启严格鉴权且仅监听回环地址的本地开发服务可以省略令牌，绑定非回环地址时则始终拒绝未配置管理员令牌的控制面请求。

要把来源状态改为 `READY`，必须先验证：访问权限、平台条款与 robots、访问频率、原始发布时间、证据 URL 可重开、保存和回写边界、失败重试幂等，以及删除/退订处理。所有自动联系动作仍要经过人工确认。
