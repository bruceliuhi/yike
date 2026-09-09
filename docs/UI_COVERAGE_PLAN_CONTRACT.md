# P09 覆盖补查与搜贝上限调整交接合同

适用 R4 搜索覆盖后的操作入口。前端抽屉、确认、原请求恢复及隔离测试已实现；生产 `YikeService.coveragePlans?` adapter 尚未接通。缺服务明确显示未接通，原任务仍可查看。本合同不代表真实追加用量、扣费、补查或自动恢复已可用。

## 实现入口

- 入口来源：[搜索覆盖合同](UI_SEARCH_COVERAGE_CONTRACT.md) 的 `CoveragePlanRequest`；[Tasks](../desktop/src/renderer/pages/Tasks.tsx) 默认接入操作抽屉。
- 唯一运行时合同：[coveragePlan.ts](../desktop/src/renderer/domain/coveragePlan.ts)；原运行溯源：[coverageProvenance.ts](../desktop/src/renderer/domain/coverageProvenance.ts)。
- 可选接口：[CoveragePlanService](../desktop/src/renderer/services/coveragePlan.ts)：`preview(input,signal?)`、`adjust({binding,preview})`、`reconcile(binding)`。
- 交互：[CoveragePlanDrawer](../desktop/src/renderer/pages/tasks/CoveragePlanDrawer.tsx)、[useCoverageAdjustment](../desktop/src/renderer/pages/tasks/useCoverageAdjustment.ts)、[CoverageAdjustmentRecovery](../desktop/src/renderer/pages/tasks/CoverageAdjustmentRecovery.tsx)。

## 只读预览与两条分支

`preview` 输入为 `{requestId, plan, newMaxSoubei?}`。原 `plan` 绑定用户/客户空间版本、任务/运行、覆盖快照、方向、窗口、画像/配置版本、去重版本、预算版本和有效期。返回须精确对应原请求/范围，并带新的预览 ID、范围说明及有效期。预览不会创建任务、预留或扣减搜贝。服务必须重新核对真实恢复状态；不能从暂停字样或空列表推断可恢复。

| 已核实状态 | 允许操作 | 必须保留的边界 |
| --- | --- | --- |
| `TERMINAL` → `NEW_DRAFT` | 用户确认后，根据服务返回的完整条件创建新的本机会话草稿。 | 新 UUID、修订从 1 开始；保留原当前输入与既有草稿列表。原任务不重启，草稿仍需编辑、重新估算并在最终页确认。 |
| `RESUMABLE_CONFIRMED` → `ADJUST_LIMIT` | 读取新上限估算，核对并明确确认后，仅调整搜贝上限。 | 展示原上限、新上限、差额、旧预算版本、规则和有效期；**不自动恢复任务**。 |
| 恢复状态未知、原覆盖过期或身份失配 | 不形成可执行预览。 | 提示重新读取或核对原记录，不提供猜测状态或假成功。 |

新草稿将完整原 `plan` 与 `scopeSummary` 写入 `research.coverageProvenance`，保留 `runId/windowId/unitId/snapshotId/deduplicationVersion` 等溯源。该结构进入本机草稿 schema、后续配置摘要与确认页，供真实执行端复核和去重；它不是复用旧报价或重启原运行的授权。后续搜贝估算仍检查来源用户和客户空间，并遵守 [研究用量合同](UI_RESEARCH_USAGE_CONTRACT.md)。

## 上限调整确认与原请求核对

调整报价必须绑定原任务/运行、客户空间版本、旧预算版本、旧/新上限、精确差额、计量规则和期限；未知预计新增消耗显示“尚未确定”，不能默认零。报价有效期不得超出原预览；改变新上限会废弃预览和勾选。报价 token 只存内存。

明确确认后生成 `CoverageAdjustmentBinding`：`{accountScopeId, scopeVersion, taskId, requestId, confirmationHash}`。摘要涵盖精确预览及报价快照，排除授权 token。服务必须在旧预算版本上原子、幂等地调整同一范围上限，并以原请求 ID 支持查询；不得顺带调用 resume/start 或重新研究。

派发前同步写入用户隔离的 `coverage-adjustments` 账本：键 `[accountScopeId,scopeVersion,taskId,requestId,confirmationHash]`，值 `PENDING`。存储失败不派发；同任务同空间有原锁时禁止新增调整。清草稿、离页、登出后仍保留原请求，任务详情独立显示核对入口；跨空间不能查询，迟到结果不能解锁或修改新空间界面。

| 回执 | 接受条件与行为 |
| --- | --- |
| `APPLIED` | 回显去 token 的原确认快照，重新计算摘要匹配；旧预算版本、新上限一致，新预算版本增加，并明确 `notResumed:true`。才核销原锁并提示“上限已调整，任务尚未恢复”。 |
| `REJECTED` | 同样回显并验证原确认快照，明确 `confirmedNotApplied:true`。核销原锁，废弃旧预览/勾选；旧确认摘要不能直接换新请求再发，须重新读取预览。 |
| `PENDING` / `UNKNOWN`、超时、网络失败、失配或缺字段 | 保留原锁；只能 `reconcile` 查询原请求，不能另造请求绕过。普通错误不证明原调整未执行。 |

预览、调整和核对等待上限均为 30 秒。停止等待不等于撤销服务端操作。已提交的未知调整不会因取消抽屉而消失；核对不依赖已过期的内存 token，而依赖原请求和去 token 确认快照。

## 验证与真实接入要求

主回归：[r4-coverage-plan.test.tsx](../desktop/tests/ui/r4-coverage-plan.test.tsx)，覆盖默认任务入口、条件预览、草稿保留/溯源、新旧上限、配置改变、已拒绝预览失效、UNKNOWN 重进核对、错回执、跨空间和存储失败。既有页面回归：[tasks.test.tsx](../desktop/tests/ui/tasks.test.tsx)、[r4-search-coverage.test.tsx](../desktop/tests/ui/r4-search-coverage.test.tsx)。

[TEST adapter](../desktop/tests/visual/r4-coverage-plan.ts) 须在覆盖 TEST adapter 后配置；默认演练“UNKNOWN → 核对原请求 → 内存 APPLIED 且未恢复”，可用 `terminal:true` 演练本地补查草稿。对应 [adapter 测试](../desktop/tests/ui/r4-coverage-plan-visual.test.ts)。TEST 数据与回执不能证明真实预算服务可用。

真实后端仍须交付已认证空间授权、原覆盖/恢复状态复核、计量规则与预算版本并发控制、幂等事务、原请求查询和“不恢复”证据。不得用旧 `taskAction`、客户端估算或任意路径 IPC 冒充此服务。真实采集与服务端部署验收仍按既有门禁执行。
