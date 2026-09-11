# 项目来源与作者更新

基线11a640b；在已批准V0.2内自行细化，不改变邀请候选或部署。依据上一批真实案例及本轮匿名API实测：topic详情返回replies但无附言；replies/show.json返回topic_id、member.id、原文及created，1232232作者结束声明可读。官方维护者历史说明支持该v1回复路径（https://www.v2ex.com/t/33784）；v2需令牌，本片不接令牌。

选择：不把回复拼进主帖冒充原文，不仅加关键词；新增显式固定来源 `v2ex-outsourcing-authors-v1`，在新模式 `four-platform-public-project-monitor-v1` 下开放。旧模式允许源保持不变；搜贝research仍仅latest。复用普通once/monitor/确认/上传/人工复核链。

## 唯一跨端合同

CandidateRecord新增可选（不可null）`source_context`，旧记录缺省不添加字段，不改变旧内容hash：

```json
{"schema_version":"v2ex-author-context-v1","replies_expected":2,"replies_read":2,"replies_complete":true,"supplements_read":false,"author_replies":[{"id":"18012619","body":"合成测试中的作者更新","published_at":"2026-08-24T12:00:00Z"}]}
```

只允许PUBLIC_WEB/PAGE且author_public_id、external_source_id非空，normalizer_version为`v2ex-author-page-v1`；context是采集器声明，不是人工已核验。replies_expected为0..2147483647整数或null；replies_read为0..100整数；complete仅当expected非null且等于read；supplements_read只能false。author_replies最多100项且不超过read，id为正十进制安全整数文本、唯一；body沿用非空Unicode/控制字符规则，单条最多20000字符、总和最多20000；published_at沿用UTC秒，不能晚于观察或早于主帖发布时间。不保存非作者正文。回复列表按API顺序，不假设顺序即时间。

内容版本保存context；作者回复/覆盖变化形成新版本，旧hash保持。候选原文详情显示作者更新和API回复读取计数，明确附言未读；缺context的旧公开来源显示仅主帖、后续更新未核。历史版本校验包含context及其时间。

模型最小content投影新增可选`author_updates`（字符串数组，按author_replies顺序）和可选`source_read_scope`（固定`AUTHOR_REPLIES_COUNT_MATCHED_SUPPLEMENTS_UNREAD`或`AUTHOR_REPLIES_PARTIAL_SUPPLEMENTS_UNREAD`），二者同时出现；不传作者ID、时间或URL。引用field扩为`author_updates.0`..`author_updates.99`；逐字引用校验保留，作者回复可作为intent/urgency本人的依据。读取范围不能作为采购引用；complete只表示本次API计数匹配，绝不称来源整体完整或已人工核实。模型不得推翻用户历史排除，既有独立复核/发送授权不变。

## 新来源执行

固定索引`https://www.v2ex.com/api/topics/show.json?node_name=outsourcing`，最多检查min(maxRecords,3)篇，不补足排除项。验证node.name；先做原主帖筛词，匹配项才从固定`https://www.v2ex.com/api/replies/show.json?topic_id=<已验证ID>`读取一次。不接受用户URL/重定向、鉴权或任意分页；最多4GET，共用20秒deadline、1MiB总响应上限、跨来源60秒冷却。取消/未知不重试；任何响应错配/结构错误均失败，不当无回复。

回复逐条核topic_id、id、created、member.id；member_id若存在须一致；仅member.id与topic.member.id相同才保留。缺作者标识拒绝新路径。API返回reply数与topic.replies不同时完整度false；不得通过附加时间戳绕缓存。附言接口未核，始终标未读。

来源选择、模板/快照/能力、旧服务拒绝新源、监控恢复和确认失效复用现有机制；UI说明最多3篇/4请求及附言未读。不增加生产配置、价格、SMS、账号或发送。

## 验收

定向RED/GREEN：旧请求字节不变；新上下文严格跨端解析/持久/模型引用；作者关闭与作品要求原文不改写；非作者不借意图；数量不符为partial；错topic/成员/时间/重复拒绝；旧能力不接受新源；改源重新确认。一次隔离PG联验含context保存/重开及版本变化；一次真实新driver读取（无模型外发）验证实际形状，不把记录数当商机。整批一次独立审核，修复仅差量。Windows/客户UAT仍待验，不构包或部署。
