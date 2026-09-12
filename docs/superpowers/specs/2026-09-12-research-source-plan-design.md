# 有界公开来源计划

基线 `0fe86ac70344bd4f10f56f4d651e48dd0a33c8d5`。V02 范围内自主技术细化；不部署、不新增平台承诺/收费规则。本批不是完整跨平台研究完成。

## 决策

当前单源研究已贯通，不能继续用多菜单代替多源执行。自动扩入未确认来源会偏离用户授权，一次跨账号平台全接又涉及不同执行器。本批采用**显式选择多个现有公开入口→同一冻结计划→逐源读取→统一判断**，保留单源兼容路径，作为完整多源编排的一步。

## 输入和权威

已确认策略 `configuration.research.sourcePlan` 可选，严格对象 `{version:1,sources:[sourceId,...]}`，仅现有 latest/qna/outsourcing 三枚 ID，2–3 个且唯一、有序。缺省字段不改变任何旧序列化摘要；显式 null、未知版本/字段/来源拒绝。`publicSource` 必须等于第一项，来源上限 `research.limits.sources >= sources.length`，`max_records >= sources.length`。只接 PUBLIC_WEB、匿名、search、once；不混入其他平台/links/monitor。

来源顺序由用户确认。每源独立固定 action：UUIDv5(runId, `research-source-plan-v1:` + taskId + `:` + sourceId)。旧无 sourcePlan 的 action 算法和全部协议/摘要不变。来源成员、预算和配置均从同 owner/tenant 的冻结任务快照派生；读取和提交均校验来源与其固定 action，不能用其他合法目录源或客户端摘要扩权。

## 执行和公平性

先按顺序读取全部计划源，再处理现有当前原文判断队列。每 advance 最多一个新 SOURCE_READ 或 MODEL_CALL；已有回执仅恢复。任何源 pending/FAILED/UNKNOWN 均阻止越过它读取下一源；取消、资料/策略失效和额度沿用原门禁。不用重启、换请求ID、换源掩盖失败。

每源记录配额由总 max_records 均分，余数按确认顺序分给前部：`divmod(max_records,len(sources))`。配额不足直接拒绝计划，空源不转移配额；避免第一个大索引吃完所有预算。仍总计最多100条，每源最多100输入、1MiB/20秒读取边界不变。来源回执、原文和预算计数继续同事务。相同平台来源复用原候选，不当作多个买方；先读后分析，由现有 current-version/observation 检查跳过已过时重复项，不重新造候选/判断缓存。逐源入库数是观察条目，不保证商机。

## 能力与结果协议

- 旧无参数 v1 capability、`source_catalog_version=1` v2 capability及单源任务 v1/v2 status原样保留。
- 精确 `GET /research-execution/capability?source_plan_version=1` 返回 `{contractVersion:3,sourceScope:V2EX_INDEX_PLAN,sourceLabel:V2EX多板块 · 有界来源计划,sourceIds:[v2ex-latest-v1,v2ex-qna-v1,v2ex-outsourcing-authors-v1],maxPlannedSources:3,maxFreshEffectsPerAdvance:1,settlementState:PENDING}`。
- 新客户端可按精确422/invalid_request从 plan查询退到catalog查询，再退到旧无参，至多三次只读；其他失败/取消/无效响应不降级，不自动重发 START。
- 计划任务 status 为 contractVersion3、上述scope/label，附 `sourceProgress:[{sourceId,phase,acceptedOriginals,recordLimit}]` 按计划顺序。phase 为 NOT_STARTED/PENDING/SUCCEEDED/FAILED/UNKNOWN；仅SUCCEEDED的acceptedOriginals为整数，其余null。没有计划的 status 不新增字段。
- 全部源已提交SUCCEEDED后，总 acceptedOriginals 才为所有源入库数之和，否则null，防止第一源读完即宣称完成。其余用量/原文分析计数、取消恢复语义继承。每源 acceptedOriginals 不超过其 recordLimit；计划len2–3、id唯一、总 recordLimit<=100；COMPLETED 必须所有源成功且分析/跳过数收齐。sourceProgress真实来自保存的事件/receipt，不由网页计时器推断。

## 用户路径

在现有公开来源选择处追加“同时研究其他已支持板块”复选，第一来源仍使用原选择。追加顺序固定目录顺序，主源在首部。旧服务只保留旧单源，已有不支持计划保留但阻止启动，不自动删除或换源。保存草稿、准备/确认、报价和签名START全部绑定sourcePlan。启动前重新核对每个来源的服务能力和公开绑定。确认摘要展示每源记录配额；进度展示逐源状态，不把同平台三个板块称为三平台。评论/作者回复未读仍明确显示。用户修改选择使原确认/报价失效。

## 验证

TDD：旧字节保留、新字段严格校验、缺预算/重复/错误anchor/跨平台拒绝；受限PG两/三源真实确认→报价→START→逐源原文→模型→完成/恢复，首源读完不提前完成、空源不跳过剩余、跨源 action/摘要拒绝、共享预算、公平配额、重复身份、失败不推进、取消/租约沿用。客户端实际向导和正式transport/DTO回放覆盖计划选择/修改/能力失效/旧服务降级/逐源进度。一个整批独立审核，不重复无关全套测试、构包或真实平台读取。
