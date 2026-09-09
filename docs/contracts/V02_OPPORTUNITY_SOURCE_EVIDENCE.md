# 商机详情：固定原文证据接入合同

2026-09-10，Mac115固定证据工程候选`26502ee`已实现，接口验收与实际接收以[唯一任务书](../V02_IMPLEMENTATION_TASKBOOK.md)为准。本文是Win05G/05E接入目标，不是客户端、实际平台或生产已完成。实施范围见[计划](../superpowers/plans/2026-09-10-opportunity-source-evidence.md)。

## 用户应看到什么

人工纳入商机时，固定保留该次使用的公开原文、版本、观察时间和逐字引用。共享商机详情回答：原文说了什么、判断引用哪里、何时观察/收到/纳入、哪些仍未知。它不是当前网页仍有效或对方仍在采购的证明。

- 同一客户空间内，其他用户可看**已纳入的最小公开证据**；原始候选、所有观察、私有复核请求和画像引文仍不共享。
- 纳入后再次采集、修改画像、撤销策略或重复纳入，不改写该商机原证据。当前来源状态与历史快照并列，不能用历史OPEN推导当前可发送。
- 旧导包商机、缺少新快照的历史商机明确“未留存固定原文证据”。不拿当前原文、旧导入时间或模型生成内容补写。

## 读取入口

既有认证 `GET /api/ui/opportunities/{opportunity_id}` 的 `opportunity` 新增 `source_evidence`。其余商机字段和`followups`不改名；列表暂不携带完整正文，客户端进入详情时读取。它不是新的私有历史查询权限。

```json
{"status":"UNAVAILABLE","reason":"NOT_CAPTURED"}
```

只有确实不存在快照时返回上述值。有快照时：

```text
source_evidence
  status = CAPTURED
  snapshot_sha256 = 服务端保存的完整快照摘要
  snapshot
    schema_version = opportunity-source-evidence-v1
    opportunity_id
    captured_at
    source
    observation
    assessment
    verification
```

CAPTURED仅表示保存了纳入时的证据，不是VERIFIED、当前可访问或发送批准。服务端校验摘要、schema与商机/画像绑定；损坏或读取失败应走错误状态，不能当NOT_CAPTURED。跨空间目标按现有详情404处理；会话失效401，响应沿用no-store。实际服务异常不得在客户端降级为“没有新机会”。

## 字段与时间

| 对象 | 字段 | 使用说明 |
|---|---|---|
| source | platform、kind、external_source_id、external_comment_id、public_url | 固定公开定位；kind为POST/COMMENT/PAGE，匿名和缺失外部ID保持null |
| source | version_id、content_sha256 | 原始候选内容版本及摘要，不是平台官方版本，也不是旧导入的标题/摘录版本 |
| source | title、container_title、body、author_public_id、published_at、parent | 本人文本、原帖上下文与父评论分开，规则见下节；发布时间未知不补造 |
| observation | id、observed_at、received_at | 该次纳入选中的观察；observed_at是受签名约束的采集端观察声明，received_at是服务端入库时间 |
| snapshot | captured_at | 服务端本次人工纳入时间，不是来源发布或采集时间 |
| assessment | id、assessed_at、profile_version_id、profile_version、strategy_version_id、provider、model、rule_version、rule_sha256 | 当时判断的绑定及版本标签；不是当前画像/策略仍有效 |
| assessment | citations、omitted_profile_citations | 只保留公开原文引用；画像引文省略数量，不能自动补成公开引用 |
| verification | method、status_at_capture、checked_at、opening_method、contact_method | 历史HUMAN_REOPENED/OPEN及人工声明；不展示自由输入locator/excerpt为官方证据 |

parent为null或`external_comment_id/body/author_public_id/published_at/public_url`五个公开字段。它是父评论，不是原帖作者。普通商机已有的`match_reason/action_signal/value_judgment/risk`继续表示人工确认后的判断，不混入原文区。

现INCLUDE确认绑定内容版本。**同内容的新观察不会增加候选revision，也不强制重新付费分析**；快照选取实际纳入时当前同版本观察。Win确认/显示文案须体现该语义，不声称用户批准的是早先预览中的某个固定采集时间；若未来需要批准观察ID，必须另改协议，不能前端自行补承诺。

## 评论角色与引用定位

| 原模型field | 新公开引用field | 指向的事实 |
|---|---|---|
| title | source.title | 主帖/页面本人的标题；COMMENT时必为null |
| body | source.body | 当前来源本人正文，COMMENT即评论正文 |
| parent.title | source.container_title | COMMENT所在原帖/视频标题，不能归给本评论者或父评论作者 |
| parent.body | source.parent.body | 父评论正文，作者/时间只取parent对应字段 |
| profile.description | 不公开 | 计入omitted_profile_citations，不进入共享原文 |

每条citations精确包含`dimension/field/quote`。dimension是businessMatch、intent、urgency、actionability之一；quote逐字出现在对应固定字段，不折叠空格、不拼接、不自行改字。某维只有私有画像依据时，公开引用可为空，UI提示没有可展示的公开引用，不补造。

共享快照不包含完整模型response、维度自由reason、私有画像description、搜索词/策略全文、request payload、设备/连接/会话或完整观察历史。新DTO不授权前端加载这些私有对象。

## Win05G/05E接收清单

1. 复用已有P07/P10/P11与R4，不新增一套商机页面。现`mapOpportunity`只有扁平`sourceObservedAt/sourceEvidenceVersion`，**尚未消费本nested DTO**，端点返回新字段不等于展示完成。
2. 加严格DTO适配，检查schema、商机ID/画像版本和字段类型；未知格式/损坏/失败显示可重试错误。切用户/空间后清除原文和迟到响应，不暂时显示前一用户的详情。
3. 详情展开看到原文、角色、引用与三个时间；原文事实/人工判断/模型引用分区。来源目前BLOCKED/EXPIRED与历史CAPTURED可以并存，不抹掉有权查看的留存。
4. 链接只打开对应公开来源；外部评论定位能力据实际平台验收，不把能打开父帖写成已定位原评论。未知作者/时间、原文缺失和当前无法回源分别说明。
5. P07来源人工核验和INCLUDE仍按[04C合同](V02_CANDIDATE_REVIEW.md)更新请求/回执/原键恢复；向用户明确纳入后的同空间最小分享。此处没有自动启用旧本机确认hash或发送能力。
6. 接收绑定实际后端SHA、真实接口往返和页面状态证据；Mac工程测试不代替Win客户端ACK、PH-F06或真实平台整链验收。

## 受信部署

115随既有迁移清单登记；受信管理员路径在准确的`yike.app_role`作用域执行`deploy/grant_opportunity_evidence.sql`。应用只获新表SELECT/INSERT，租户共享读、纳入人写；新增不可变/首次纳入约束。运行端不持有管理员连接。旧部署缺表/授权应完成受信升级，不能吞异常伪装为NOT_CAPTURED。默认平台、执行和发送能力仍不由本片开启。
