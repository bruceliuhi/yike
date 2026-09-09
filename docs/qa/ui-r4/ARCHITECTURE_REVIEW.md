# R4 独立架构与合并复核

日期：2026-09-09。审核者：`design_handoff_architecture`（A）。

**绑定提交：`190683c87af536b8e1af47e6a002abf0464d376b`。结论：所列独立审核范围 PASS，发现的问题已完成修复与交叉确认，当前范围无剩余 P0/P1/P2；没有发现本次合并阻断。** 这是有限源码/契约审核，不是完整产品、真实服务、客户端发行或部署验收通过。

## 独立范围与排除

- B 的 P10/P11：研究分类列表、精确授权集合详情、同来源证据时间线、相似研究预览/本机草稿交接及隔离 TEST 适配；`domain/opportunityResearch.ts`、对应服务与 `pages/opportunities` 新模块、接线和合同。
- C 的覆盖补查：`coveragePlan/coverageProvenance` 域与服务、预览抽屉、上限调整及原请求核对、Tasks 接线和隔离 TEST 适配。
- root 的共享改动：`useResource` 有界读取、账户范围及本机任务/模板分区、研究配置/来源持久化、搜贝 quote 与启动预留绑定、任务配置 hash、`useTaskScope`、`PendingTaskStarts` 及中央服务接入边界。
- 明确排除 A 自作的 P02 机会简报、P09 搜索覆盖功能及其服务/视觉夹具，不用自己编写的测试给这些模块独立背书。P09 后续由 B 修改的密度呈现只读检查了字段/入口保持，视觉结果另验。
- A 在共享审核中修复的模板删除身份问题不自审：由 C 独立读审并运行 `task-templates.test.tsx` 12 项通过，见下方交叉记录。远端新增后端功能只核对合并保留，不作整卡功能审查。

## 已核对的关键合同

**P10/P11。** 新研究服务必须具备可信 Session 的账户空间 ID/正安全整数版本，不能以 userId 代替账户或从回包补出空间。无此范围时保留原商机 facade，新时间线/相似建议不发请求。列表的研究类别、人工复核、原处理状态和采购阶段保持独立；非待分类项有同来源版本且存在于原文的摘录。详情按当前授权集合精确取 ID，不把观察/排除项开放为已认可客户触达。

时间线只允许同一 URL 的递增版本链；当前证据版本须为链尾，变化前后引用必须落在真实对应版本。访问失败不生成关闭事实，人工联系与渠道回执分开。三个快照 parser 均校验生成早于到期、拒绝过期和超过 5 分钟时钟容差的未来生成时间。

相似研究在创建草稿前再次读取授权机会、画像、认可记录和原请求建议。账户/来源/画像变更、认可撤销、手工编辑或迟到响应不创建草稿。公开样例不调用客户相似服务，不入客户集合、不启动或发送。本机交接保留已有编辑内容，不能将其提示为已执行研究。

**覆盖补查与搜贝调整。** 预览绑定原账户、任务、run/window/unit/snapshot、画像/配置/去重/预算版本和有效期。上限调整核对新旧上限与差额，未知估算不填零；令牌只在内存。真实调整前可靠落盘最小账户/任务/请求/确认 hash 账本；存储失败不调写接口。

PENDING/UNKNOWN、超时或错绑回执保留原请求保护，关闭抽屉/清理普通草稿不能清锁。核对限定原账户与原请求，终态必须回显去令牌的完整确认快照并匹配 hash。APPLIED 还须核对预算版本、新上限及 `notResumed=true`；REJECTED 使旧预览和勾选失效，旧确认 hash 不能直接重发。调整上限没有自动恢复调用。

终态补查生成新 ID 的可编辑草稿，原运行/窗口/方向/去重/空间及版本/范围保存在 `research.coverageProvenance`，进入后续配置 hash；不复用原预览作为新启动授权，不覆盖当前草稿和原列表。中央持久 schema 接受该字段，估算前拒绝其他账户空间来源。

**共享生命周期。** `useResource` 保留原渲染时身份隔离，增加 31 秒外层截止、重载/卸载取消和迟到响应丢弃；域内已有 30 秒错误说明优先生效。草稿、草稿列表和模板按 user+空间 ID/版本分区；旧无空间服务保留旧键。新模板副本具有默认研究设置，不绕过 R4 搜贝确认；模板来源启动 UNKNOWN 仍阻止派生。

新研究启动要求 v1 执行适配、当前配置 hash 的有效 quote，并随原请求保存去令牌预留摘要；ACCEPTED/REJECTED 不能遗漏该摘要，拒绝还须确认无剩余预留。等待期间换账户/空间或配置后，不用旧结果更新当前任务。PendingTaskStarts 只能在原空间核对有预留摘要的请求，不把未知结果当作未创建。

## 发现与关闭

| 问题 | 最小修复与复核 |
|---|---|
| P2：P10/P11 允许缺可信账户范围，且快照时序不完整 | B 改为必填可信范围、旧 facade 兼容；三类快照增加时序验证。A 独立复跑 57 项通过。 |
| P2：终态补查新草稿丢失原运行/窗口/去重溯源；拒绝后仍可复用旧确认 | C 加独立 coverageProvenance，root 接中央持久/估算/确认展示；旧 hash/预览/勾选失效。A 独立复跑 43 项通过。 |
| P2：模板删除弹窗仅靠 effect 清理，切空间时旧对象可进入新身份渲染 | A 将待删对象与 identity 同时捕获，render/remove 双 guard；C 独立审核并复跑 12 项通过。回归在 passive cleanup 前检查，两个空间故意使用相同模板 ID。 |

## 已有执行证据

以下是冻结前协作工具实际执行记录，随后核对本次合并没有改动 renderer、UI 测试或 TEST 视觉源码；各集合有重叠，**不可相加**。执行目录为 `desktop`，Node 路径使用 `/Users/bruce/.nvm/versions/node/v24.19.0/bin`。这些 chunk 标识指向本次工具记录，不伪装为仓库内原始日志文件。

| 执行者 / 范围 | 命令范围 | 实际结果 / 记录 |
|---|---|---|
| A 独立 P10/P11 | `npm test -- --run tests/ui/r4-opportunity-research-domain.test.ts tests/ui/r4-opportunity-research-ui.test.tsx tests/ui/r4-opportunity-research-handoff.test.tsx tests/ui/r4-opportunity-research-visual.test.ts` | 4 文件 **57 passed**，21:25:33，`f83e1b` 会话最终输出 |
| A 独立覆盖补查 | `npm test -- --run tests/ui/r4-coverage-plan.test.tsx tests/ui/r4-coverage-plan-visual.test.ts tests/ui/tasks.test.tsx tests/ui/r4-search-coverage.test.tsx` | 4 文件 **43 passed**，21:34:12，`53f8b6` 会话最终输出；其中搜索覆盖是关联回归，不作 A 自作功能的独立评审 |
| A 独立 root 共享 | `npm test -- --run tests/ui/r4-research-usage.test.tsx tests/ui/hooks.test.tsx tests/ui/task-templates.test.tsx tests/ui/task-recovery.test.tsx tests/ui/task-wizard.test.tsx tests/ui/operation-ledger.test.tsx` | 6 文件 **96 passed**，21:43:20，`b1ed97` 会话最终输出；在模板删除窄修前 |
| A 模板修复后定向验证（非自审） | `task-templates / r4-research-usage / hooks` 三套及 `npm run typecheck` | 3 文件 **46 passed**，21:46:00，`3ea4ce`；typecheck/diff 检查通过 `e4a5bc` |
| C 独立模板删除增量 | `task-templates.test.tsx`、`useTaskTemplates/useTaskScope` 只读复核 | **12 passed**，C 交叉消息绑定 `97bbbf`，无剩余 P0/P1/P2；A 未替代 C 给自身修改出具结论 |

## 合并保留核对

合并提交 `190683c87af536b8e1af47e6a002abf0464d376b` 的两个实际父提交为：

- 本轮源码候选 `676970c43899ca8ae6a5dec3a071c795d6323c24`。
- 远端主线 `2ce6f8a8076765cdbb7122b08175cd2f01cf1abd`。

已核对两者祖先关系与 merge parent；相对本轮父提交，`desktop/src/renderer`、`desktop/tests/ui`、`desktop/tests/visual` 无差异。相对远端父提交，后端 `app/connectors/pilot/migrations/deploy/tests`、Windows runtime 测试、V1 版本映射、手机登录计划、Win 分工交接和双端任务板均无差异（只读命令记录 `ce3113`）。这不等于远端后端整卡已验收。

逐项检查 AUTHORITY 与实施任务书冲突结果：V1.0 商用分期、V1.1 保留设计未启动、原 V02 工程编号、任务书第 7 节“端到端＋三个亮点”和 Win/Mac 分工均保留。手机登录 `V02-01D-PHONE` 仍为 IN_PROGRESS，109 归认证、108 留 Win，生产 SMS capability 未验收保持关闭；没有把计划改为已实现。R4 原实现授权及“搜贝换算/售价未定”并存，05A 等原任务没有被清零或标为 DONE。

## 限制与未被本报告放行的事项

新 R4 服务仍为条件接入合同，TEST 内存数据、APPLIED 模拟回执和可操作前端不证明真实采集、模型、计量、预留扣减、发送或生产简报已通。此次仅保留远端连接/候选映射/进程改动，不把继承其源码等同于整卡重新审核。

本报告写入时未将 root 正在执行的最终全套、新 Mac 包、包内冒烟、生产夹具排除或可见验收记为通过；相应结果必须由完成后的绑定记录给出。历史 Windows 证据不自动覆盖本次 R4。远端明确保留的 CP-06 备份认证 P1、真实环境恢复、正式发布及跨行业验证仍独立处理；本范围 PASS 不解除这些门禁，也不是可以对外收费或上线的结论。
