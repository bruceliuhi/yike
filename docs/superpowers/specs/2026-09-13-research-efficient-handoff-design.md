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
4. **真实进度**：修正unpublishedOriginals。无candidate batch仍为未发布；有效BACKGROUND回执是已完成筛选，不计未发布。被容量/无效原文阻止入库的ASSESS零项回执仍计未发布，不能把所有零项都清零。复用batch.receipt中的 `skipped_background_count`，无新字段/表/客户端协议。

## 不变边界

- 不放宽原文哈希/引用/完整性校验，不增加模糊修复、默认全选或静默重试。
- 不更改登录、租户/owner隔离、SSRF/redirect、凭据、UNKNOWN、取消、确认外联、资源计量与付款门禁。
- 个人Skill及仓库原Skill包不改；不删普通assessment、不虚构作者或原文日期。
- 不新增来源连接器、不改生产、不构包，不声称新线索或商业证明。

## 验收

定向RED→GREEN：contextual命令schema及桥接原样传递、无context旧命令；规则有效性/新指纹/单份画像/语义反例；两个ASSESS在研究用完分配后仍能判断；BACKGROUND完成后未发布0、真正未发布与budget-skipped不被吞掉；取消/UNKNOWN保持原证据。

一批独立代码审核；同快照fresh模型一次验证真实schema/合法final/输入量。若需要业务候选，则使用有明确业务需求的另一个固定公开快照作不同样本并披露来源，不把BACKGROUND成功当候选判断通过。实网验证仅在上述通过后新建有界任务，保留旧失败，不重放旧UNKNOWN。只对修改影响的检查追加；不重复全量测试或安装包。
