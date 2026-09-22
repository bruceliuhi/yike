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
- `POST /api/v1/workspaces/ws_意客AI/profiles`
- `POST /api/v1/workspaces/ws_意客AI/tasks`
- `GET /api/v1/tasks/{task_id}/plan`
- `POST /api/v1/tasks/{task_id}/start`
- `POST /api/v1/tasks/{task_id}/execute`
- `GET /api/v1/tasks/{task_id}/runs/{run_id}/events`
- `POST /api/v1/tasks/{task_id}/runs/{run_id}/pause|resume|cancel|retry`
- `POST /api/v1/tasks/{task_id}/capture-url`
- `POST /api/v1/tasks/{task_id}/capture-urls`
- `POST /api/v1/tasks/{task_id}/opportunities`
- `POST /api/v1/opportunities/{opportunity_id}/feedback`
- `GET /api/v1/workspaces/ws_意客AI/entities`
- `POST /api/v1/entities/{entity_id}/merge`
- `POST /api/v1/entities/{entity_id}/split`

任务创建时会生成三条可检查的搜索路径：快速搜索、条件核验、扩展搜索，并给出来源状态和 credits 估算。机会录入必须有 `title`、`source_url` 和 `snippet`。系统保留来源 URL、原文片段和核验时间；当前外部平台连接器仍显示为 `REQUIRES_PROOF` 或 `REQUIRES_AUTH`，不会用假数据冒充自动搜索。

机会还会进入保守的实体解析层：导入记录明确提供 `entity_name` / `company_name` 时建立企业或组织实体；没有实体名称时，只在来源 URL 主机足够稳定时按官网主机建立关联。小红书、抖音、微博等社交平台主机不会被当成企业官网，标题和作者昵称也不会单独创建企业实体。同名实体如果对应不同官网主机会保持分离，避免把不同公司的公开信号错误合并。每张机会卡返回 `entities`，包含实体、主机、置信度、解析原因和关联证据。

实体主档支持人工合并和按单条机会拆分。操作会把关联关系写入审计事件，并保留机会原始证据；“合并”只移动机会与实体的关系，“拆分”只改变选中机会的实体归属，不会删除来源内容。

`capture-urls` 接受最多 50 个用户明确提交的 URL，逐条返回成功项和失败项；重复 URL 使用任务级幂等键，不会重复计费。它是受控导入入口，不等同于平台搜索连接器，也不会自动扩大抓取范围。

任务运行实例现在会记录创建、来源阻塞、暂停、恢复、取消和重试事件。重复执行同一状态操作不会追加重复事件；重试会创建新的运行实例并保留上一实例 ID，方便回放失败原因。运行控制和日志已经具备，真正执行搜索仍必须等来源连接器通过权限、频率、发布时间和证据重开验收。

授权搜索 API 适配器使用以下环境变量：`LEAD_RADAR_SEARCH_ENDPOINT`、`LEAD_RADAR_SEARCH_TOKEN`、`LEAD_RADAR_SEARCH_PROVIDER` 和 `LEAD_RADAR_SEARCH_REOPEN_PROOF=true`。即使布尔开关为 true，仍必须绑定 proof artifact：`LEAD_RADAR_SEARCH_PROOF_REF`、`LEAD_RADAR_SEARCH_PROOF_SHA256`、`LEAD_RADAR_SEARCH_PROOF_CHECKED_AT`、`LEAD_RADAR_SEARCH_PROOF_ENDPOINT`、`LEAD_RADAR_SEARCH_PROOF_PROVIDER` 和 `LEAD_RADAR_SEARCH_PROOF_CHECKS`（JSON 中 `url_reopen`、`published_at`、`save_boundary`、`retry_idempotency` 均为 true）。接口必须返回 `{"items": [{"title", "source_url", "snippet", ...}]}`；系统会限制响应体大小、只接受 HTTPS URL、校验必填字段、按 URL+标题去重，并把 provider 结果先放入 `REVIEW`。当前代码提供适配器和执行门禁，未配置真实授权服务或完整 proof artifact 时不会宣称来源已接通。

`capture-url` 只访问用户明确提交的公网 URL，拒绝内网地址、非标准端口、带凭据 URL、非 HTML 页面和超过 1 MB 的响应。系统只保存正文摘要和内容指纹，结果默认为 `REVIEW`，不会因为页面抓取成功就判断为采购意向。

## 当前生产门禁

要把来源状态改为 `READY`，必须先验证：访问权限、平台条款与 robots、访问频率、原始发布时间、证据 URL 可重开、保存和回写边界、失败重试幂等，以及删除/退订处理。所有自动联系动作仍要经过人工确认。
