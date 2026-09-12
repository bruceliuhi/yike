# 公开研究：确定不可读与执行未知分离

2026-09-13。范围内技术设计，依据用户2026-09-11自行细化与开发授权；**尚未实现**。本设计承接[实际探针](../../qa/DYNAMIC_RESEARCH_REAL_PROBE_20260913.md)，不宣称已确定电鸭本次失败原因。

## 要解决的客户问题

普通公开页面明确不存在或格式不支持时，研究应记录缺口、在原预算内选择另一个来源；不能整批崩掉，也不能把不可读页面当成功原文。真实未知、限流、权限拒绝、取消和失去授权仍停止，禁止重放未知动作或绕过受阻路径。

## 方案取舍

1. 继续全部停止：保持现状，但不能恢复本地Skill的换源行为，不选。
2. 所有确定结果存SUCCEEDED、结果内部区分不可读：数据库改动少，但当前成功READ直接驱动候选和计数，需重定义成功计数/客户端协议，容易误称成功原文，不选。
3. **保留FAILED状态，只为严格已知READ失败保留结果信封和摘要**：新增迁移调整两个存储约束，序列准入只豁免已核实的限定失败；现有failed计数和v4客户端合同保持含义。选择此方案，不创建另一套账本或泛化重试框架。

## 分类与不可突破的边界

读器新增足够明确的原因，而不是直接放行现有PublicReadError：

- `not_found`：已收到HTTP404或410。不得自动跟重定向或读其它身份接口。
- `unsupported_media_type`：HTTP200后明确MIME非text/html/text/plain；不把编码、解析器异常合并进来。
- `too_large`：现有确定响应/提取上限拒绝；保留上限，不截断冒充完整原文。

仅这三类可继续选择**不同**已准入来源。失败缓存不再次出网。结果信封使用严格 `{status:"FAILED",code:<上述三类>,replayed:false}`；URL绑定原payload，观测时间由持久动作时间表达，不新增模型编造日期。

401/403/429、任何验证或登录需要、重定向、TLS/DNS/网络未知、通用`unavailable`、超时、非法URL、坏/不完整协议、无效正文证据、宿主期限及取消都不属于上述豁免。权限/限流应有可识别的脱敏错误码；本批只保证不继续或重试，不新做登录引导。不能从消息字符串猜测分类。404本身不证明项目关闭，只是当前路径不可读。

## 接线与数据合同

- `open_web_reader_worker.py`在已知HTTP状态/MIME分支产生准确原因；父读器与MCP错误码显式接纳，旧通用错误语义不变。空页面或解析异常仍保守失败。
- `research_effect_contract.py`新增严格已知READ失败验证；不能把任意`status:FAILED`、未知code、额外字段、业务文本或MODEL/SEARCH失败当可继续结果。
- `PublicReadSession`在perform内部形成明确失败信封；无效证据仍走未知失败路径。预算、缓存、截止、allowed URL和敏感字段门禁保持。
- `DurableResearchDispatcher`根据严格结果选择SUCCEEDED或FAILED持久终态；回执需验证状态、输入/输出摘要、permit、action、context与完整结果。结果或ACK不明确则关闭，不重新出网。已保存、严格匹配的已知失败可在当前有效授权下读取回执，但不重新请求原URL。
- `ResearchEffectJournal.finish`仅允许READ的这三类FAILED结果同时携带result和output_sha256，且与资源事件同事务更新；老FAILED/UNKNOWN的空结果继续兼容。失败原因不可后补改写已终态记录。
- 新迁移（实施时确认下一个编号）修改journal与resource的对应CHECK；保留RLS、不可变trigger、事件绑定。资源FAILED+摘要仅用于SOURCE_READ的内部已绑定结果；普通resource.finish仍拒绝任意失败摘要。由于finish先更新resource、后更新journal，新分支使用事务末deferred配对约束，验证对应journal最终为FAILED且permit/动作/摘要匹配，不能在resource即时trigger要求尚未更新的journal已终态。旧数据不回填为新已知失败，旧版本遇新FAILED保守停止。
- 串行begin不能再简单要求所有前序SUCCEEDED：只允许前序成功或逐条严格验证的已知READ失败，且资源事件、摘要、状态和permit完全匹配。禁止仅凭kind=READ/status=FAILED豁免。同run已经确定失败的规范URL不能在新序号下再次准入出网；缓存/相同序号的严格回执重放可返回旧结果，未明确恢复的进程仍不自动重启。
- 动态supervisor的出站、判断、完成和status使用同一个确定失败判定；未配对、损坏、其他资源失败或UNKNOWN仍阻断。status显示全部failed计数，但停止判定使用排除已验证软失败后的hard_failed，避免实际完成又显示STOPPED。取消/租约/策略/凭据检查优先，不因结果可分类而继续失效任务。
- `_successful_reads`、候选publish只接SUCCEEDED+READ原文。已知失败计入reads.failed与usage.sourceReads.failed，不计accepted/analyzed/unpublishedOriginals，不生成商机卡或供应商关闭判断。
- 完成可以包含已明确记录的不可读来源，客户端继续显示failed计数与覆盖缺口；不能用“全部来源成功”宣传。没有成功原文的批次仍保留worker的`no_verified_reads`停止语义，为0原文、0候选，不说市场无需求。未知用量仍UNCERTAIN；不自动退款或修改搜贝价格。

## 最小验收

1. 不联网的实际worker/MCP/dispatcher边界：一条已知404结果后可读第二条允许URL，同URL缓存无第二次请求；权限/限流/未知/坏证据全部停止，不延续搜索。
2. 受限PG纵切：SEARCH→已知READ失败→成功READ→候选/判断；准确计数1失败/1成功/1候选，资源关闭非UNKNOWN，读失败页绝不入候选；重放与取消仍安全。
3. 真值反例：FAILED空结果、伪造/额外字段、MODEL失败、资源不配对、摘要篡改、ACK丢失、旧授权和过期均不能继续。
4. 旧固定来源不变；v4状态被现有客户端严格schema接受，正常成功/空结果及未知停止仍通过受影响测试。仅定向回归与一次整批独立审核，不重复构包未改的客户端。
5. 实际研究另行验证，保留此前失败，不用夹具完成宣称供给恢复。若真实新批次只有广告/无买方，直接改变研究策略与可用深读入口，不靠更多接口测试刷进度。

本批不改个人Skill，不改授权平台范围，不部署、不外联。搜索行为质量、授权评论与跨行业用户试用仍是后续业务验收，不随本设计完成。

独立只读架构分析基于`aed17ff`支持方案3，明确提醒错误码全链传递、失败后status不能误判硬停止、资源先更新时的deferred配对，以及同run失败URL禁止新序号重试。分析不等于代码审核或功能完成；按当前范围内自主细化授权进入后续实现，不新增逐项等待用户确认的门槛。
