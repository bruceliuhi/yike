# V02-04C 候选判断与人工复核接口

2026-09-09，IN_PROGRESS，尚待服务实现、独立审核与Win实际接收。
本文件不代表真实采集、真实模型效果、客户端接通、已发送或上线。原始上传/读取仍用[02B协议](V02_RAW_CANDIDATE_INBOX.md)。

## 与客户端的关系

沿用[现有P07类型](../../desktop/src/renderer/domain/candidates.ts)与[原请求恢复约定](../UI_CANDIDATE_REVIEW_CONTRACT.md)。`profileId`实际是业务画像**版本ID**（`business_profile_versions.profile_version_id`），`profileVersion`是该版本整数，不是父画像ID。

当前服务为显式构建注入 `build_app(..., candidate_review=service)`，普通启动不自动注入模型或策略；缺服务返回501 `capability_unavailable`。客户端不得因为端点存在就启用未验收能力。模型provider、资料处理授权、真实确认策略resolver及平台读取仍为实际启用条件。

| HTTP | 用途 | 关键边界 |
|---|---|---|
| GET `/api/ui/candidates` | 当前候选列表与原复核核对 | 不调用模型、不新建复核 |
| POST `/api/ui/candidate-reviews` | ASSESS或人工INCLUDE/EXCLUDE | ASSESS永不自动入库或批准 |
| POST `/api/ui/candidate-source-verifications` | 单独的人工打开核验 | 不是平台机器验证 |
| GET `/api/ui/candidate-review-requests/{request_id}` | 查询原请求 | 不重试模型、不凭超时认定未执行 |

以上入口均使用当前认证会话和既有HTTPS约束，不从正文接受tenant/owner/reviewer/time。POST实际JSON正文最多64KiB；拒绝重复JSON键、非有限数、坏UTF8、未知字段；不把校验失败的敏感值写到错误或日志。查询拒绝重复参数、未知筛选项。

列表参数：`query`（最多200字符）、`platform`（02A正式平台标识）、`status`（PENDING_REVIEW/IMPORTED/EXCLUDED/DUPLICATE）、`page`（从1开始）、`pageSize`（1–100）。`ids`为1–100个不重复UUID，以逗号分隔。原复核恢复使用唯一 `ids`、`reviewRequestId`、`page=1&pageSize=1`；不要把当前新版本候选与旧成功回执拼成同一次操作。

## 写入绑定

三类写入均包含 `candidateId / candidateRevision / sourceVersionId / profileId / profileVersion / requestId`。同requestId异载荷409；所有原确认字段都在服务端请求指纹内。

- ASSESS：另传 `action:"ASSESS"`；只有查询过原失败/未知尝试后，才以新requestId及显式`retryOf`发起新尝试。在途或成功缓存复用仍保留新requestId的查询关系。
- 人工来源核验：另传 `humanConfirmed:true / status / openingMethod / locator / excerpt / contactMethod`。状态OPEN/BLOCKED/EXPIRED/UNVERIFIED；打开方式DIRECT/IN_PLATFORM；联系路径COMMENT/DM/PUBLIC_CONTACT/NONE。服务端登记HUMAN_REOPENED和实际认证用户/时间，不能由模型自报。
- INCLUDE/EXCLUDE：另传`action / assessmentId / evidence / reason / humanConfirmed:true`。evidence必须含人工确认的`matchReason/actionSignal/value/risk/unknowns`五项。INCLUDE另指明`sourceVerificationId`；EXCLUDE必须有原因，不要求来源OPEN。

OPEN只是“此用户声明已打开”，不证明买方身份、需求今天仍开放或能收到私信。纳入需同绑定最新的有效OPEN核验，后来的BLOCKED/EXPIRED等使旧OPEN失效；核验24小时内，原需求本人发布时间已知且在60天内，至少一条检查过的联系路径。人工检查不会刷新原始发布时间。

## 判断结果与用户看到的依据

四维分别记录 `businessMatch / intent / urgency / actionability`，各有level、理由与逐字原文引用；模型结果还保留购买形态、研究优先级、联系建议、最强反证/未知和分别撰写的短评论/私信。S/A/B+不是成交概率，SEND_READY不是发送批准。

分析绑定候选revision、原文版本、画像/策略版本、规则内容摘要和模型版本。COMMENT的raw.title来自父视频/主帖，服务端把它放到模型parent.title，不能拿来证明评论者自己的采购动作。原始作者、日期和URL留在服务端，不由模型填写。

原文变化、歧义、画像撤销或策略变更时，历史分析仍可追溯，但不作为当前有效判断；同内容的后续观察不强制重复付费分析。原复核成功快照与当前版本不同的恢复查询必须明确标历史快照，不能因此重新开放操作。

## 恢复、预算与入库

PROCESSING/SUCCEEDED/FAILED/UNKNOWN分别表示处理、已保存、明确失败和结果不确定。服务端90秒提交期限及模型自身总I/O时限是两道不同边界；超期晚到结果不能复活原请求。UNKNOWN不自动退款为“未调用”，也不自动重试。

相同owner的精确输入/规则/model成功结果可复用，其他owner不能读取其私有缓存；在途请求不重复外调。每快照最多3次实际调用，默认每客户服务端Asia/Shanghai自然日20次预约上限，可由可信配置调整；这是运行限制，不是定价或真实扣费声明。tenant级计数仅存日期和次数，不暴露其他owner私有请求内容。

人工INCLUDE是明确的最小数据分享边界：私有原始候选经认证复核后，批准的摘要、证据和草稿进入现有tenant共享商机库；不把全部原始观察历史共享。原子事务保存商机、复核及回执；重放不重复入库。

同来源/画像已入库时返回ALREADY_IMPORTED，旧共享机会保留当时判断，本次修改词另存私有review；不能写成已覆盖原机会。新机会来源默认UNVERIFIED，人工打开核验不等于触达执行前的平台验证。现有机会后续人工设置的状态不因重复纳入被重置。

## 接收前必须补齐

真实受限PostgreSQL整链及并发/撤销/超时证据、独立精确commit审核、Win对新核验步骤/扩展字段/原请求恢复的实际ACK、真实策略和至少一个真实来源样本。最终字段与回执示例在服务冻结后补入；不得按本文IN_PROGRESS状态对外销售已可用能力。
