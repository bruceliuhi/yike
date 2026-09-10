# 06A/07A 联系对象实际核验

基线`fa9b0ae`，沿用已批准触达对象/人工确认合同。发现当前确认模型仅校验传入对象，尚缺从实际保存草稿和公开原文解析收件对象的入口；先补这一必需前置，再接原计划07B发送队列，不将本片当发送完成。

## 交付

`POST /api/ui/outreach/context` 接收 `binding`（已保存DraftSaveBinding）、`deviceId`、`connectionId`、`connectionVersion`。普通runtime的ContactDraftStore提供事务内核验：本人最新保存稿、同租户OPEN机会和来源、已确认画像、固定原文版本、本人ACTIVE设备及CONNECTED同平台同版本连接。客户端不传作者或URL作为授权依据。

从原始证据解析目标：主帖评论指向帖子，评论回复必须指向该条评论而不是父评论/博主；私信指向原需求作者。不能确认作者/对象或公共网站PAGE不推断自动渠道。账号与保存稿不符、旧草稿/旧来源/旧连接拒绝。

返回来源、目标、实际账号、保存稿和规范摘要，仅为下一步渠道检查材料；明确 `authorization=NOT_GRANTED`、渠道 `UNVERIFIED`，不签发确认token、不入发送队列、无网络或平台写入。CONNECTED只表明已登记的账号状态，不等于可以发评论/私信。

## 实现与验收

1. `tests/test_outreach_context_http_postgres.py`复用草稿的实际HTTP/受限PG夹具，先取得404 RED。
2. `pilot/contact_drafts.py`抽出共用事实读取/owner锁并实现context；`pilot/contact_draft_api.py`注册有界认证入口，不另建数据表/执行框架，不改Win客户端。
3. 定向验证评论作者/主帖作者、本人连接、版本/历史、撤销、无敏感vault输出及无确认副作用；复用草稿定向回归，一次独立整批审核后提交main。Win消费与真实渠道检查后续分别验收，不改父Goal范围。

## 本批验证

`e2ae2b7`先取得新接口404 RED。实际HTTP/受限PG的11项context＋12项草稿通过；两项新增POST/PAGE样本沿用了评论引用导致fixture失败，按既有证据测试修正后这两项单独通过（1.31s），未放宽产品校验。共用锁按既有执行器的设备/连接→画像次序，避免锁序反转。

独立审核发现草稿accountId被误当连接UUID。核对客户端真实映射后用公开账号ID复现409（应200）；`53501e9`改为锁定连接后比对account_public_id，并加入UUID误作公开账号的拒绝反例。最终 **14项实际HTTP/受限PG通过 / 0 skipped / 4.90s**；未改保存逻辑，复用原12项草稿回归。每轮独立测试DB结束删除；平台来源/连接为明确合成输入，不是实际账号或发送验证。非作者对`53501e9`差量复审 **GO，原P2关闭，无新增阻断项**；未构包、未改客户端。
