# 07B 人工草稿实际保存

沿用已批准的 `UI_OUTREACH_CONTRACT.md`、`UI_SHORT_COACH_CONTRACT.md` 及客户端 `domain/shortCoach.ts`，不新增产品范围。本片 Mac 实现后端，Win 保留客户端接入。基线 `98c5577`；迁移 121 本片使用。

## 接口及完成条件

- `POST /api/ui/contact-drafts` 接收现有 `DraftSaveInput`及保存前驱 `previousRequestId`；摘要严格等于客户端 `snapshotDigest`，服务器认证租户/owner，不接受调用方授权事实。
- 同一事务锁定当前来源、已确认画像及商机；固定证据版本必须匹配。草稿分别按 owner/商机/comment或dm 保存；顶层previousRequestId必须等于开始编辑所基于的原保存请求（首次null），并核对版本前进及savedContent等于上次正文。仅正文比较不能阻断A→B→A，独立审核后补此CAS；不改原摘要/回执格式。
- `POST /api/ui/contact-drafts/operation` 按完整 `DraftSaveBinding` 查询原回执；超时、404不是未保存。原UUID重放先读原快照，不因后来来源/画像变化重写历史。
- `GET /api/ui/opportunities/{id}/contact-drafts/{channel}` 恢复本人的最新草稿。保存正文不代表已发送；不写确认、不更新商机联系状态、不开放outreach能力。
- 追加式 `pilot_contact_drafts` 同时保存版本与原请求回执；强制owner/tenant RLS、只授予SELECT/INSERT。普通runtime实际装配，无新执行器/模型依赖。

## 本批执行

1. 先写实际HTTP/受限PostgreSQL测试，取得保存接口404 RED；另核对客户端摘要兼容。
2. 实现 `pilot/contact_drafts.py`（校验/事务），`pilot/contact_draft_api.py`（有界请求/错误），迁移121/授权及runtime/router装配；不改Win文件。
3. 只跑新增HTTP/PG测试和已有runtime定向检查；验证评论私信独立、重放、跨owner/tenant、过时来源/画像/草稿拒绝、原回执恢复。一次独立整批审核后推main；文档记实际结果和未验范围，不重复构包。

后续07B仍需确认快照、发送幂等队列和真实对账；本片不关闭07B或完整Goal，也不宣称客户端或平台验收。

## 本批证据

代码 `fca33d3`。实际新接口先取得404 RED；fixture初建失败为固定证据绑定漏更新、旧迁移将来源默认设为UNVERIFIED，已修正合成输入，不放宽产品门禁。实际HTTP/受限PG的11项及已有runtime15项合计 **26 passed / 0 skipped / 3.71s**；随后将并发测试改为同owner三个独立session，定向 **1 passed / 1.18s**，未重复其余套件。实际Node JSON.stringify/crypto与Python摘要在中文、emoji、换行及scope样本上一致。每轮仅新建随机名隔离测试DB并在结束删除，未修改生产或保留测试客户；synthetic来源注入不是平台采集验证。

独立整批审核发现正文A→B→A时旧窗口覆盖P2，root实际复现200（应409）；`2d77f58`增加保存前驱CAS并保持原回执查询。修改后的 **12项实际HTTP/受限PG全部通过 / 0 skipped / 4.29s**；未改runtime装配，复用原15项。非作者对该精确提交差量复审 **GO，原P2关闭，无新增阻断项**。本批只交付后端草稿实际保存/恢复，无客户端构包、平台发送或客户UAT。
