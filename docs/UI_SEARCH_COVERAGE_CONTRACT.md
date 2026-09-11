# R4 P09 搜索覆盖服务契约

2026-09-09。适用范围为已获实现授权的 R4 搜索覆盖前端，依据 [R4 交互合同](../design/v02-suite-r4/INTERACTION_CONTRACT.md)。本文记录条件适配接口和真实交互边界，不代表平台采集、监控、搜贝计量或生产服务已接通。

## 接入与身份

2026-09-11 接线边界：普通客户端及真实采集任务详情已接现有运行、上传观察与原文版本的只读服务，版本和审核见[唯一实施记录](superpowers/plans/2026-09-11-search-coverage-service.md#实施与验证)。当前方向是每个平台的已确认关键词集合，不宣称逐关键词/页码已经穷尽。窗口为任务授权创建/截止区间，不是实际在线时长；原内容计数仅含持久上传观察，重复项指同来源重复观察（含版本变化），来源示例最多20条，数字统计不截断。无可信逐词结束、筛选聚合或搜贝规则的项继续未知，不以 FINISH 推断 COMPLETE。

可选能力为 `YikeService.searchCoverage?: SearchCoverageService`，仅有 `query(request, signal?)` 读取方法。完整类型与校验分别位于 [服务接口](../desktop/src/renderer/services/searchCoverage.ts) 和 [数据合同](../desktop/src/renderer/domain/searchCoverage.ts)。生产适配缺失时，P09 明确提示尚未接通；原平台状态、执行记录和任务配置仍可查看。

请求携带 `contractVersion=1`、独立 `requestId`、`taskId`、`profileId/profileVersion` 和 `expectedScope`。后者必须来自可信 `Session.userId/accountScope.id/accountScope.version`；缺失或无效不能请求此新能力。客户端字段仅用于一致性校验，服务端必须从认证会话确定账户和授权，不能据请求任意切换租户。

响应必须原样绑定请求 ID、账户空间及版本、任务、画像及版本，另提供 `snapshotId/runId/configurationRevision`、`window(id,start,end,timezone)`、`deduplicationVersion`、生成与到期时间。画像历史版本仍是原运行的版本，不能把切换到最新画像伪装成对旧结果的重新计算。当前旧 `TaskRun` 没有独立运行窗口字段，新服务须给出真实窗口，不能从旧事件列表推导。

## 二维结果与证据

| 字段 | 含义与限制 |
|---|---|
| `coverage` | `NOT_STARTED / RUNNING / PARTIAL / COMPLETE`，独立表示检查完整度。整体完成要求所有方向完成；部分完成不能由空集合或全部完成方向组成。 |
| `screening` | `HAS_CANDIDATES / PENDING_REVIEW / ALL_EXCLUDED / NO_QUALIFIED / MIXED / UNKNOWN`，独立表示筛选结果，不能用访问失败推导无合格机会。 |
| `units` | 平台与搜索方向明细；含范围、完整度、筛选结果、停止原因、已知说明和 `unchecked` 未查范围。平台必须属于当前运行的配置。 |
| `counts` | 请求、原内容、重复项、独立来源、新候选、已确认机会、待复核数；未知一律 `null`，不能补零。 |
| `exclusions` | 区分去重与业务筛选，保存理由、规则版本、数量、是否重叠及原文证据。已知正数量必须有证据。 |
| `evidence` | 稳定来源 ID、来源版本、URL 和原文摘录；拒绝样例 ID、非 HTTP(S) 或带用户名密码的 URL。 |
| `countingBasis` | 本方向、本窗口的统计依据，不能把各平台方向直接相加声称独立客户数量。 |

`ALL_EXCLUDED / NO_QUALIFIED` 必须属于已完成方向且待复核数为已知零；全部排除还要求正独立来源数与实际筛选证据。未完成方向必须说明未查范围，完成方向不能仍列未查范围或登录失效、设备离线等未完成原因。违反合同显示数据错误，不退化成空结果。

服务返回的是已存在快照：`query` 不得借读取触发新采集、自动补查、额度预留、恢复任务或收费。公开样例不进入此客户运行统计。

## 搜贝与后续动作

`usage` 可以为 `null`；有值时包含 `unit=SOUBEI`、计量规则版本、预算版本、预计/最多/实际用量及结算状态。未知金额保持 `null`；`SETTLED` 不能缺少实际值，已知实际值不能超过已知上限。页面使用“搜贝”展示，内部请求数、原内容等仍按原始资源统计解释，不能冒充统一价格。

根据确切停止原因提供连接平台、查看设备等已有入口。只有 `LIMIT_REACHED` 且服务确认 `RESUMABLE_CONFIRMED`、存在预算绑定时才发起 `ADJUST_LIMIT` 意图；终态 `TERMINAL` 发起 `NEW_DRAFT` 意图；可恢复性未知不猜测。

`CoveragePlanRequest` 携带原账户、任务、运行、窗口、方向、快照、画像/配置/去重/预算版本及到期时间。它是下一流程的绑定信息，不能作为直接恢复或扣费授权。接线通过 `TasksPage.onCoveragePlan` 或默认补查抽屉完成，后续独立服务见 [coveragePlan 接口](../desktop/src/renderer/services/coveragePlan.ts) 和 [计量合同](UI_RESEARCH_USAGE_CONTRACT.md)。追加上限须独立确认、原请求保护及可核对回执；确认调整不代表任务已恢复。终态只能创建可编辑新草稿并保留原运行溯源，仍须走最终启动确认。

上限调整预览绑定原 `run/budgetRevision`，显示旧上限、新上限、差额、预计新增消耗（未知保持未知）、规则和有效期。改值后旧预览与勾选失效。调整请求发出前须可靠保存仅含账户/任务/请求/确认 hash 的账本；令牌仅留内存。`PENDING/UNKNOWN`、超时、错绑或缺回执均保留保护，关闭抽屉和清理普通草稿不能解除；只能核对原请求。终态回执须匹配不含令牌的完整确认快照：`APPLIED` 明确新预算版本、上限和 `notResumed=true`；`REJECTED` 明确未调整并使旧确认失效，重新读取预览后才能再决定。

终态新草稿保留 `coverageProvenance` 的原运行、窗口、方向、快照、去重版本、账户、画像及配置版本和范围说明；其到期时间是原预览的历史记录，不能复用为新启动授权。保存使用新草稿 ID，保留当前编辑内容与已有列表，进入后续配置/最终确认；不得把保存本机草稿提示为补查已运行。

## 页面生命周期与验收

- 每次读取有 30 秒边界；共享资源钩子也提供外层取消。刷新、更换身份/账户/画像或离页后，旧响应不能更新新页面。失败可重试，不显示成“未找到”。
- 校验生成时间不在未来且早于到期时间；旧快照可作为明确标识的历史结果展示。到期计时器会禁用后续动作，刷新后才能重新决定。
- 覆盖为默认标签，平台状态、执行记录和任务配置保留。方向可选择、证据与排除依据可展开，样例不会成为真实客户统计。
- `r4-search-coverage` 的 domain/UI 测试覆盖二维矛盾、未知数值、身份/窗口绑定、错误/超时/过期及导航；与补查调整测试分开计数。
- [隔离视觉适配](../desktop/tests/visual/r4-search-coverage.ts) 仅为 `TEST` 内存数据，可展示有数据、空、错误、等待状态；不发外部请求，不操作客户数据，不证明生产服务或平台已通。真实可见验收、包验证与候选 SHA 由当轮 QA 记录给出。
