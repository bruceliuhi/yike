# 原研究 Skill 接入 Codex 执行链

## 目标与选择

按 V0.2 自主细化授权实施。原本地 Skill 已有用户认可，仓库版本基本相同；本批接线，不重写个人 Skill，也不新建第二套研究框架。通用执行器继续兼容无画像的内部公开搜索；增加显式 `research_context` 时才进入商机研究模式，加载固定仓库规则并回传规则/上下文指纹。不是通过字段自报“已确认”获得客户权限。

现有 `CandidateAssessmentModel` 只加载入口/资格规则，新执行器尚未加载搜索覆盖/复盘。完整复用已有 `skills/ai-project-lead-research-v1` 四文件；宿主加载到临时指令文件，不开放模型读取任意本地文件，不读取个人 Skill 目录。源码与 wheel 使用同一字节，资源缺失/空白/超限失败，不降级通用模式。

## 上下文与执行

`research_context` 为严格 JSON 对象，结构版本 `research-context-v1`。必填：profile_version_id、strategy_version_id（规范UUID）、seller_description（1–4000字符）、reference_time（带时区ISO）、timezone（有效IANA）、max_age_days（严格整数1–365）、query_seeds/intent_signals/exclusions（最多20条，每条1–160字符；intent_signals至少1）、history_scope（NONE/PARTIAL/COMPLETE）、history（最多30项）。每项含 project_key（1–128）、description（1–500）、state（KNOWN/CONTACTED/EXCLUDED/CLOSED），另含 source_urls（最多3个规范匿名HTTPS链接）；NONE必须空history。所有字段必填、禁止额外字段/控制字符/非UTF8文本；完整规范JSON≤32KiB，不截断。

这只是宿主传入的范围快照，不能替代服务端身份、原画像/策略解析、许可和历史查询。生产调用方须从现有租户上下文加载并核实，不能暴露成客户随意POST即可执行的API。本批不冒充已接客户任务，也不把用户端自报历史视为数据库已核验。

可选参数缺省保留旧9字段搜索返回及旧只读7字段；显式提供的非法/None上下文返回 FAILED/invalid_research_context，且零供应商/子进程动作，增加 `research_binding:null`。有效上下文增加 `research_binding:{rule_version,rule_sha256,context_sha256,profile_version_id,strategy_version_id}`。规则不可用返回 FAILED/research_rules_unavailable。绑定是宿主生成，不采纳模型自报；不是商机评级或触达许可。任务描述及上下文含实际供应商密钥时仍拒绝，不把密钥写临时文件/日志。

加载规则：固定四文件，每个≤64KiB、合计≤128KiB、严格UTF8且非空；规则版本 `opportunity-research-context-v1/ai-project-lead-research-1.0.0`。规则SHA用文件名与原始文本的确定性JSON计算，文件名排序，确保字节/内容变化可追踪；上下文SHA用严格规范JSON。兼容wheel `pilot/_research_rules` 与源码固定仓库路径，wheel目录存在但不完整时不得fallback。

查询组合由宿主按 `query-portfolio-v2` 规则生成，作为独立的 `HOST_QUERY_PORTFOLIO_JSON` 数据帧传入，不混入固定开发者指令；组合采用 action-major round-robin，有限预算下先覆盖每个已确认词根，再扩展行动信号、排除词和兜底动作。研究进程把 `HOST_RESEARCH_CONTEXT_JSON` 与下一个 marker 之间视为上下文 JSON，把后续查询列表视为搜索方向；查询本身不是来源证据，仍必须打开并核验原文。

宿主指令明确：客户服务/意向/排除条件决定业务范围；AI行业表、历史用户排除和30–60分钟为原方法示例，不覆盖本轮画像/预算。从业务问题→交付物→采购动作生成词，广告/旧帖损耗时换假设；历史去重缺口不能称净新增。reference_time与max_age_days用于作者时间窗口，搜索索引日期不是原文日期；缺正文/作者更新待补证。可评论、预算未知不直接误杀。公开工具读不到动态评论必须记缺口，专用连接器另负责，不越权开新工具或发送。

规则和上下文随独立临时执行目录销毁；不把业务文本传入argv/env。规则是固定开发者指令，上下文作为JSON任务数据经stdin与原任务一起提供；上下文内容不得改变工具/安全边界。已有4000字符任务描述限制不因上下文扩大失效；编译后载荷由独立32KiB上下文＋原描述上限约束。

## 验证与边界

1. RED/GREEN验证严格上下文、缺失规则、确定性绑定、secret拒绝在spawn之前；真实fixture子进程捕获临时指令与stdin证明实际加载而非仅文件存在，旧模式完全不变。
2. wheel只构一次验证四文件和源码一致，不重构桌面包/部署，不重跑无关全套。
3. 同一离线业务快照作有界行为对照，区分原文不足、旧/关闭项目、预算未知/仅评论、行业适配和历史重复；原方法未改不追求无意义的全套Skill压力测试。一次真实研究应以本轮时间、画像和历史缺口为准；无合格结果如实保留。工具成功与有效商机分开。
4. 独立整批审核一次，修复仅差量。下一步仍为现有任务许可/证据事务/客户端进度接线，未关闭完整Goal。
