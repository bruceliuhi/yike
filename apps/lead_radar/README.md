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
- `POST /api/v1/tasks/{task_id}/capture-url`
- `POST /api/v1/tasks/{task_id}/opportunities`
- `POST /api/v1/opportunities/{opportunity_id}/feedback`

任务创建时会生成三条可检查的搜索路径：快速搜索、条件核验、扩展搜索，并给出来源状态和 credits 估算。机会录入必须有 `title`、`source_url` 和 `snippet`。系统保留来源 URL、原文片段和核验时间；当前外部平台连接器仍显示为 `REQUIRES_PROOF` 或 `REQUIRES_AUTH`，不会用假数据冒充自动搜索。

`capture-url` 只访问用户明确提交的公网 URL，拒绝内网地址、非标准端口、带凭据 URL、非 HTML 页面和超过 1 MB 的响应。系统只保存正文摘要和内容指纹，结果默认为 `REVIEW`，不会因为页面抓取成功就判断为采购意向。

## 当前生产门禁

要把来源状态改为 `READY`，必须先验证：访问权限、平台条款与 robots、访问频率、原始发布时间、证据 URL 可重开、保存和回写边界、失败重试幂等，以及删除/退订处理。所有自动联系动作仍要经过人工确认。
