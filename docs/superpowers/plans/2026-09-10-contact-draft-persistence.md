# 07B 人工草稿实际保存

沿用已批准的 `UI_OUTREACH_CONTRACT.md`、`UI_SHORT_COACH_CONTRACT.md` 及客户端 `domain/shortCoach.ts`，不新增产品范围。本片 Mac 实现后端，Win 保留客户端接入。基线 `98c5577`；迁移 121 本片使用。

## 接口及完成条件

- `POST /api/ui/contact-drafts` 接收现有 `DraftSaveInput`；摘要严格等于客户端 `snapshotDigest`，服务器认证租户/owner，不接受调用方授权事实。
- 同一事务锁定当前来源、已确认画像及商机；固定证据版本必须匹配。草稿分别按 owner/商机/comment或dm 保存；版本必须前进、savedContent 必须等于上次保存正文（首次等于导入草稿），拒绝旧窗口覆盖。
- `POST /api/ui/contact-drafts/operation` 按完整 `DraftSaveBinding` 查询原回执；超时、404不是未保存。原UUID重放先读原快照，不因后来来源/画像变化重写历史。
- `GET /api/ui/opportunities/{id}/contact-drafts/{channel}` 恢复本人的最新草稿。保存正文不代表已发送；不写确认、不更新商机联系状态、不开放outreach能力。
- 追加式 `pilot_contact_drafts` 同时保存版本与原请求回执；强制owner/tenant RLS、只授予SELECT/INSERT。普通runtime实际装配，无新执行器/模型依赖。

## 本批执行

1. 先写实际HTTP/受限PostgreSQL测试，取得保存接口404 RED；另核对客户端摘要兼容。
2. 实现 `pilot/contact_drafts.py`（校验/事务），`pilot/contact_draft_api.py`（有界请求/错误），迁移121/授权及runtime/router装配；不改Win文件。
3. 只跑新增HTTP/PG测试和已有runtime定向检查；验证评论私信独立、重放、跨owner/tenant、过时来源/画像/草稿拒绝、原回执恢复。一次独立整批审核后推main；文档记实际结果和未验范围，不重复构包。

后续07B仍需确认快照、发送幂等队列和真实对账；本片不关闭07B或完整Goal，也不宣称客户端或平台验收。
