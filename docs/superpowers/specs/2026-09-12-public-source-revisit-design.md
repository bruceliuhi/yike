# 已发现公开来源有界复查

## 目标与取舍

完整V0.2持续监控包括来源变化，当前公开采样只覆盖index，旧帖滑出后无法观察作者更新。本批接V2EX项目外包及作者回复源的已发现旧帖复查，保持新发现预算。用户已授权既定范围内自行细化，不等待逐项设计批准。

选择：复用服务端原文/批次/监控事实生成固定复查对象，并经原CLAIM、签名batch保存读取结果。只增加搜索词仍漏旧帖；本地历史队列不能跨设备恢复；全站历史重扫成本与授权范围不合适。不新增任意URL抓取或独立调度。

## 固定协议

- 显式只读协商`execution.support {samplingVersion:2}`映射`?sampling_version=2`，支持既有public monitor的policy才返回`public_sampling:'committed-round-revisit-v2'`。v1/plain回包保持不变。旧服务精确422/invalid_request时允许一次`samplingVersion:1`读取；其它错误/会话改变不降级，执行操作不重试。
- CLAIM可选`public_sampling_version:2`（严格整数，仅CLAIM，与native互斥）；v1保持原签名和回执。新`public_sampling:{schema_version:'public-sampling-round-v2',plan_id,source_id,round,revisit:null|{topic_id,query}}`。topic_id为无前导零的正ASCII十进制字符串，数值不超过9007199254740991；query是该确认快照的关键词。
- 仅source_id=`v2ex-outsourcing-authors-v1`且round为奇数选择最多1个旧帖；偶数、新计划或无合格历史时revisit=null。其它公开源v2仍只轮换当前index，不扩来源范围。
- 非空revisit时driver completed返回`{records,publicRevisit}`，worker签名batch新增`public_revisit:{schema_version:'public-source-revisit-v1',claim_request_id,topic_id,outcome:'READ'|'UNAVAILABLE'}`。回执exact echo、fingerprint和加密journal包含该字段。无复查时缺省省略，不写null或undefined。
- 服务端batch必须匹配同平台当前CLAIM冻结的复查对象及完整执行context；有复查必须提交该结果，无复查禁止结果。READ恰有一条对应PAGE记录、同query及collector且有合法作者context；UNAVAILABLE无该topic记录。不能提交任意新链接、冒用旧CLAIM或原生平台结果。

## 调度与读取

服务端从同tenant/owner/plan/profile/strategy/source的已提交批次中找PAGE来源，严格确认V2EX规范URL、数字topic ID和原query仍在确认关键词内。以已提交`public_revisit`结果的最新received_at做最久未复查优先（从未复查最先），首次入库时间和topic ID确定性打破平手。只计同计划已提交结果，不从本地缓存/CLAIM发出/客户端时间推断成功。CLAIM原请求重放不改选择，提交失败不推进，空records但UNAVAILABLE可以推进；不写“已删除/需求关闭”。沿已有签名入库、事务、fence、未知恢复，无新表。

driver总量仍为`min(3,maxRecords)`；有revisit时预留1槽给旧帖，其余新帖在过滤前取样，不返还未命中预算。index与revisit相同topic去重，在抽样前剔除以保留不同来源；总请求最多5（index＋最多2新帖回复＋1旧帖正文＋1旧帖回复），20秒、总1MiB、60秒本机冷却、无跳转/凭据、取消规则保持。

旧帖通过固定`https://www.v2ex.com/api/topics/show.json?id=<数字>`读取，必须200 JSON数组，最多1条，且ID、node=outsourcing、正文与原文URL校验符合原规范。200空数组或明确deleted/空正文记录为UNAVAILABLE；非200（包括403/404/429）、畸形响应、网络/验证码/取消均失败，不提交成功复查。成功正文不再要求仍含原关键词/不含排除词，因为“已找到”等变化也须入库；query保留冻结来源的原关键词，而非新匹配事实。作者回复只保留同作者，有界读取，附言仍未读，不称完整历史或全评论。

内容与复查回执同原batch事务留存，原作者变化时间线/简报消费新版原文；不修改人工作出的联系或关闭状态，不执行外发。

## 验证与边界

定向RED→GREEN覆盖协议v1兼容/v2严格性、隔离与公平轮换、空结果、失败不推进、重放、签名/回执/恢复、真实driver读取旧帖及作者关闭更新、重复去重/预算/网络失败。复用实际受限PG＋认证HTTPS fixture，保存脱敏合成request/receipt给正式TS解析器；独立整批审核后合main，不重复全套/构包。

本批不代表真实平台/Windows/部署或客户价值通过；其它原生平台游标、完整评论深读、多源研究及跨行业闭环仍属完整Goal。
