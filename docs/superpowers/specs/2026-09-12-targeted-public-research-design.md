# 定向公开板块研究

基线 `8da6d87496481958ada3558efffae0f27b776677`。依据 AUTHORITY 中 V02 范围内自主细化授权实施；本批不是跨平台研究完成，也不变更收费或部署配置。

## 问题与选择

普通采集已有 V2EX 最新、问答和外包入口，研究执行却只读最新索引。直接增加平台菜单不能补足执行；一次实现所有平台研究又涉及不同授权执行面。本批选择先贯通现有三个公开入口的单源研究，复用签名启动、预算、原文入库、模型判断和恢复，不另造执行系统。

## 固定范围与协议

- 一次研究仅使用已确认策略 `publicSource` 选择的一个索引；不是三个独立平台、不是全站搜索、不是自动补查。来源不因无结果、失败、撤销或重启而替换。
- `v2ex-latest-v1` 保留当前 endpoint、输入摘要、规范化输出、action ID、collector 和 v1 状态字节。
- `v2ex-qna-v1` 固定读取 `https://www.v2ex.com/api/topics/show.json?node_name=qna`。
- `v2ex-outsourcing-authors-v1` 在研究链路只读取 `https://www.v2ex.com/api/topics/show.json?node_name=outsourcing` 的主题索引，明确显示“V2EX项目外包 · 单源索引研究（未读作者回复）”。普通采集的作者回复能力不冒充研究能力。
- 新节点状态 `contractVersion:2`，分别 `sourceScope:V2EX_QNA_INDEX / V2EX_OUTSOURCING_INDEX`，固定标签 `V2EX问与答 · 单源索引研究（未读评论）` / 上述外包标签；最新任务依然返回原 v1 DTO。除来源标识外其余字段与计数规则不变。
- 无参数 `GET /research-execution/capability` 保留原 v1；精确 `?source_catalog_version=1` 返回 `contractVersion:2,sourceScope:V2EX_SELECTED_INDEX,sourceLabel:V2EX定向板块 · 单源索引研究,sourceIds:[v2ex-latest-v1,v2ex-qna-v1,v2ex-outsourcing-authors-v1],maxFreshEffectsPerAdvance:1,settlementState:PENDING`。重复、未知、非法参数返回 422。客户端仅精确 422/invalid_request 可退回一次无参数只读查询；错误、取消、网络失败不自动重试，不重发执行。

## 权威与安全

来源从同租户/所有者任务的已绑定策略快照派生，既在读取前核实，也在原文提交事务中检查 source 输入摘要与快照一致。不能由客户端或 fetcher 自报 URL、collector、来源。节点 JSON 必须含匹配 node.name，防止串板块；topic ID、URL、时间、体积与重定向限制沿用当前读取器。20 秒总时限、1 MiB、最多 100 条、每 advance 一个新效果和预算上限不变。失败/UNKNOWN 不换源不补读；重启只恢复原 action 和来源。

客户端保留已有下拉框，不重做视觉。显示研究专属范围，与服务能力和已授权公开绑定求交集；所选不可用时保留选择并阻止启动。点击启动前重新检查所选来源能力，不能仅“有研究 capability”即放行。恢复记录不写死最新来源；结果页展示服务端严格解析的来源标签。

## 验收

先失败用例后实现；节点路由、串节点/URL拒绝、来源摘要互换拒绝、旧格式保留；真实受限 PostgreSQL 下确认策略→报价/START→节点索引→原文和来源→模型→完成/恢复。客户端验证能力协商、旧服务降级只读、来源不可用阻止、严格 DTO 及实际服务输出解析。独立审核绑定产品提交；不重复全量构包，Windows、真实平台、生产和商业验收继续未完成。
