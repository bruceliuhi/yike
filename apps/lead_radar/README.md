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
- `GET /api/v1/workspaces/ws_意客AI/entities`
- `POST /api/v1/entities/{entity_id}/merge`
- `POST /api/v1/entities/{entity_id}/split`

任务创建时会生成三条可检查的搜索路径：快速搜索、条件核验、扩展搜索，并给出来源状态和搜贝估算。`cost_estimate.unit` 固定为 `SOUBEI`，`display_unit` 为 `搜贝`，`rule_version` 为 `source-result-v1`；旧版 `estimated_credits` / `credits_used` 字段暂保留作为兼容字段，不代表人民币价格或外部平台收费。机会录入必须有 `title`、`source_url` 和 `snippet`。系统保留来源 URL、原文片段和核验时间；当前外部平台连接器仍显示为 `REQUIRES_PROOF` 或 `REQUIRES_AUTH`，不会用假数据冒充自动搜索。

人工录入即使提交了 `evidence_level=VERIFIED` 和 `source_permission=allowed`，也必须额外提供 `manual_override: {status: "SEND_READY", actor, reason, confirmed: true}`；系统会把覆写写入证据元数据和审计事件。没有该覆写的记录不会进入联系队列。受控 URL、授权搜索和索引导入继续默认 `REVIEW`，必须经过原文重开和人工反馈。

机会还会进入保守的实体解析层：导入记录明确提供 `entity_name` / `company_name` 时建立企业或组织实体；没有实体名称时，只在来源 URL 主机足够稳定时按官网主机建立关联。小红书、抖音、微博等社交平台主机不会被当成企业官网，标题和作者昵称也不会单独创建企业实体。同名实体如果对应不同官网主机会保持分离，避免把不同公司的公开信号错误合并。每张机会卡返回 `entities`，包含实体、主机、置信度、解析原因和关联证据。

三类社交公开来源已注册为同一来源策略：`xiaohongshu_public`、`douyin_public`、`bilibili_public`。用户侧发现可以不登录，第一层只接受用户明确提交的公开 URL，并在证据元数据中记录 `platform`、`source_family`、`capture_layer`、`end_user_login_required` 和 `server_authorization_required`。这些字段只描述来源边界，不授予抓取权限；三平台的自动搜索仍保持 `REQUIRES_PROOF`，需要平台条款、频率、发布时间、原文重开、保存边界和重试幂等证明后才能接入。

校准批次用于把一批候选交给人工复核，并记录模型/规则预测与人工金标准的差异。创建批次时可以传 `opportunity_ids`，也可以让服务按 `REVIEW → OBSERVE → SEND_READY → EXCLUDE` 的顺序选择最多 `target_count` 条当前工作区机会；目标数量必须为 1–500，机会只能来自当前工作区且不能重复。复核标签为 `VALID`、`INVALID`、`DUPLICATE`、`OBSERVE`、`NEEDS_EVIDENCE`，默认会写入既有反馈事件并同步机会状态；传 `apply_feedback:false` 只保存校准记录，不改变机会状态。批次返回覆盖率、人工复核数、准确率、误报/漏报数，以及对用户提交公开网页的重开率。重复复核会保留新的审计/反馈事实，不能当作幂等发送。

校准指标只反映当前批次中已录入的机会和人工标签，不代表平台召回率、商机成交率或跨行业效果。样本必须来自真实授权运行或明确的用户提交来源；fixture、静态页面和预置 URL 不能作为生产校准证据。正式发布仍需按 CP-06 记录真实来源 capability、生产数据库/恢复、HTTPS 和客户验收。

机会详情会同时展示证据快照、系统判断、来源权限、人工反馈和审计时间线；详情页只帮助人工复核，不会把查看动作变成联系或发送许可。

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

要把来源状态改为 `READY`，必须先验证：访问权限、平台条款与 robots、访问频率、原始发布时间、证据 URL 可重开、保存和回写边界、失败重试幂等，以及删除/退订处理。所有自动联系动作仍要经过人工确认。
