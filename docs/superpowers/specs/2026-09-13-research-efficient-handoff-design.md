# 研究交接与阶段效率

状态：APPROVED_FOR_IMPLEMENTATION，依据 2026-09-11 范围内自主细化授权。
基线：`79427c0`（已保留 Windows 验证记录）。属于完整 V02 的研究链路改进，不缩小产品 Goal。

## 证据与选择

旧真实运行成功读取两页，在最终筛选停止，原 final 未留存，具体错误未知。新固定两份公开快照＋真实模型运行通过，不能倒推旧失败已修复，也不是新采集。现有输入含四份人工 Skill 全文约23941字节；旧41.35秒运行的三次提供商调用合计32.90秒，缓存输入不能全算浪费或费用。

选择现有 Codex 原生结构化 final＋阶段规则投影＋预算预留。仅加重试/模型预算会放大不稳定交接成本；改成另一个执行器、合并普通判断或引入新的page_ref协议，会扩大当前变更且缺故障证据，本批不做。

## 设计

1. **结构化 final**：仅已编译研究上下文启用固定 `research-page-selection-v1` JSON schema，经 `codex exec --output-schema` 下发。`--json`继续接事件。schema限定精确root/page字段、类型和枚举；URL/hash/逐字quote/大小/每页完整性仍由现有持久证据parser严格校验。schema不含提供商不支持的字符串/数组长度约束；本地语义约束不变。没有上下文的旧任务不加schema。临时schema在原隔离任务目录内生成，不加载用户文件。桥接保留实际 `text.format`，不静默删除或降级。官方说明：[Codex非交互模式](https://learn.chatgpt.com/docs/non-interactive-mode)。国产提供商兼容性仍须有界实测，不能以文档或mock证明。
2. **研究执行投影**：新增 `pilot/research_stage_rules.py` 保存固定版本执行文本，替换模型输入中的四份全文，但继续加载和校验原规则包；其全部摘要进入新的rule指纹，原规则变化不能无感沿用旧绑定。保留客户画像优先、业务问题→交付物→行动、四发现路径、独立来源/作者扩展、原文和搜索摘要区分、时效/作者更新、购买对象/资金归属、预算匿名联系路径未知不误杀、按成果而非岗位标题判断、明确排除与反证、部分历史不可称净新增、授权与只读边界。去掉本阶段的写文件/维护队列/写联系草稿/商业验证动作；普通assessment与其规则包不改。对有context的mission只发送一次已验证画像（在context JSON中），不再正文重复description。规则版本追加 `/efficient-handoff-v1`，持久context JSON和绑定字段形状不改。旧运行绑定不兼容时继续拒绝，不重放。
3. **预算分配**：维持用户确认的总MODEL_CALL和来源上限、不增请求、不新增自动重试。设M=modelCalls、R=task.max_records、P=原max_reads，预留 `A=min(R,P,max(1,M//2))` 次普通判断，研究最多 `M-A` 次。这是有界分配而非“确保所有页面都能判断”的承诺；原SEARCH/READ上限不降低，模型不能把超出判断额度的潜在需求强标BACKGROUND。剩余额度仍以持久账本逐次校验，研究实际少用则普通判断可继续使用未花额度；更多候选保留已发布/待分析并按原STOPPED/resource_limit_exceeded结束，不伪造COMPLETED。不引入未确认的追加预算/继续任务。M=2时保持1+1；R=1只预留1。
4. **真实进度**：修正unpublishedOriginals。无candidate batch仍为未发布；有效BACKGROUND回执是已完成筛选，不计未发布。被容量/无效原文阻止入库的ASSESS零项回执仍计未发布，不能把所有零项都清零。复用batch.execution_context中的 `skipped_background_count`、`page_selection`及其他跳过计数；receipt只提供items，不新增其字段。无新表/客户端协议。

## 不变边界

- 不放宽原文哈希/引用/完整性校验，不增加模糊修复、默认全选或静默重试。
- 不更改登录、租户/owner隔离、SSRF/redirect、凭据、UNKNOWN、取消、确认外联、资源计量与付款门禁。
- 个人Skill及仓库原Skill包不改；不删普通assessment、不虚构作者或原文日期。
- 不新增来源连接器、不改生产、不构包，不声称新线索或商业证明。

## 验收

定向RED→GREEN：contextual命令schema及桥接原样传递、无context旧命令；规则有效性/新指纹/单份画像/语义反例；两个ASSESS在研究用完分配后仍能判断；BACKGROUND完成后未发布0、真正未发布与budget-skipped不被吞掉；取消/UNKNOWN保持原证据。

一批独立代码审核；同快照fresh模型一次验证真实schema/合法final/输入量。若需要业务候选，则使用有明确业务需求的另一个固定公开快照作不同样本并披露来源，不把BACKGROUND成功当候选判断通过。实网验证仅在上述通过后新建有界任务，保留旧失败，不重放旧UNKNOWN。只对修改影响的检查追加；不重复全量测试或安装包。

## 实测后的定点设计修订：引用选择而非抄写

`a23c0ce`独立Spec/Quality已通过，但新固定快照真实模型session2589终态失败：两页JSON形状、URL、SHA、规则绑定全正确，第二页123字符quote不是持久text中的连续逐字片段，原parser如实拒绝。三次实际出站均保留strict schema，故不能将问题归因于提供商未收到schema，也不放宽引用校验。具体是拼接、改写或空白差异未留存，不能猜测。旧“本批不引入page_ref”的选择保留历史；本修订仍不引入page_ref、不移除URL/SHA，仅把模型生成quote改为选择宿主片段。

- 新增内部 `research-citation-choice-v1` final：原root/page字段不变，仅 `quote` 换成 `quote_ref`（例如`q1`）；保留URL＋内容SHA完整版本身份、decision/reason。原持久 `research-page-selection-v1` 不变。
- 纯函数将成功READ的**原始text按Python字符每400字符连续切片**，不规整空白、不删除字符、不从标题/链接生成证据。序号q1起；拼接全部片段必须精确恢复原text。选择纯空白片段仍被原校验拒绝。所有片段可见，不截掉后部需求。
- 仅已编译contextual任务给内部MCP启用显式citation模式。模型可见TextContent以 `text_fragments:[{quote_ref,text}]` 替代text；同条structuredContent仍保持既有原始READ（包括完整text），不新增持久证据字段。展示明确是原文的宿主切片、不是作者身份或采购证明。legacy工具内容和命令保持不变。
- contextual worker严格解析新final（精确字段、版本、无重复JSON键、无额外页、每个成功唯一URL/SHA恰一次），从已经验证的READ事件按同一纯函数解析片段，重建旧v1 summary，再经原parser验证。不得从模型回传文本、标题、未知ref或其他页面恢复，不修复错误ref，不接受v1作为新模式降级。失败返回固定 `research_selection_invalid`，不回显模型原文。
- runtime仍依据**同tenant/owner/task/run持久成功READ**做原v1 parser及绑定、发布判断；worker重建不成为信任捷径。取消/失败任务不转成完成。规则版本/哈希追加citation版本，不能沿用旧确认。
- 不改Bridge、预算或普通assessment，不新增请求/重试。模型是否同时收到structuredContent影响输入量，必须实测，不预先声称此修订更省token。

验收只追加：片段可逆/中文与emoji/长文后部/空白、越界ref/跨页与错sha/重复缺页/非逐字v1仍拒绝；contextual MCP显示＋原structured一致，legacy不变；实际worker事件转换后能通过旧parser，错误final失败不降级；复用现有最终PG及191项证据，仅新接点定向测试。独立同审核者差量复核，然后同输入**新任务**一次真实模型核验；旧失败artifact不可覆盖。

## 首次试用必要补口：成功READ可回查

依据同日用户“按这个处理”的试用范围确认，只增加只读可见性，不把所有原文自动发布为候选。独立源码核查确认目前仅展示unpublishedOriginals数量，journal原文没有客户回查入口。

`GET /api/ui/research-execution/tasks/{task_id}/reads?run_id=<uuid>&after=0&limit=5`：run_id必填，after为0～1000整数、limit为1～5整数，拒绝重复/未知参数；服务未装配此能力返回明确501，不重试执行。响应固定 `{contractVersion:1,taskId,runId,items:[{sequence,url,title,text,observedAt,contentSha256}],nextAfter}`；nextAfter为最后返回序号或null，只有确有下一页时非null。最多5条，按sequence正序；每条均来自当前身份tenant/owner、指定task/run的READ/SUCCEEDED且已配对有效资源回执，不返回MODEL/SEARCH payload、内部context、凭据或未知/失败原文；返回前复用既有原文与output hash校验。无候选化、模型、网络、重试、计量、退款或状态变更。任务历史版本的只读证据不因为新画像确认而被篡改，跨owner/tenant/run绝不能查到。

在现有ResearchProgress的dynamic状态下增加折叠“已读原文”区，展开才调用（不加入轮询），可手动刷新/下一页；有界请求、任务/run切换或退出中断并清空旧结果，错误明确显示不能当空列表。展示标题、规范来源URL、观察时间和原文（长文展开），统一标注“研究原文，尚非已确认商机”；不猜发布状态或作者/发布时间。现有候选/分析入口保留，只读材料不获得联系/发送资格。仅渲染文本，不解释HTML或页面指令；外链复用现有安全打开机制。旧服务/fixture没有reads方法时不影响现有进度/候选路径，不新增整个能力版本协商。

此增量解决失败后的原文可见性，不声称已经实现逐页候选发布容错；当前quote_ref修订先降低已证实的抄写错误，未通过证据绑定的页仍不发布。完整V02其余项按最新试用里程碑后置，不在此扩入。
## 实际Codex工具通道修订（同批定点修复）

`2516f5d`新同快照探针证明仅TextContent投影片段不足：真实模型input没有引用编号。已核对本机Codex0.153.4源码`protocol/src/models.rs:2206-2216`：有structuredContent时优先使用，忽略content；JSONL事件处理`exec/src/event_processor_with_jsonl_output.rs:228`保留工具_meta。

因此本节覆盖前述“structuredContent原READ不变”的**工具展示**约定，不改变持久READ或最终v1合同。仅citation成功READ：structuredContent为精确片段投影；content固定短标记；`_meta.yike_original_read_v1`保留完整原READ，仅供宿主JSONL事件核验。worker仅此模式从_meta取原READ，验证原envelope/URL/hash，并从原文重算片段与structuredContent精确比较后纳入events.reads；任一缺失或偏差固定拒绝。模型final仍仅选编号，展开仅用已验证原文，runtime仍和同任务持久原文逐字/完整性核对。legacy、SEARCH、失败、Bridge和资源门禁不变。

为覆盖实际通道而非只测SDK对象，增加一次本机真实Codex CLI＋假provider的无外网往返观察：模型input有片段、无_meta原文；JSONL保留原meta并通过worker；同时核对最大合法原文/链接的事件大小。定向验证后一次差量审核，不再重审前述整批。
