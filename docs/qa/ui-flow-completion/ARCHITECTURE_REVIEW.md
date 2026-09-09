# UI 流程补齐：独立架构审核

审核人：独立 Agent A。日期：2026-09-09。

当前结论：**本次独立审核范围通过，未发现尚未处理的 P0/P1。** 审核绑定业务源码候选 `237a5b2a6be4f68682fcae4312f338e2338a3646`，基线为 `30da93e5ba39c9bc11227640b06094c7afe980b2`，工作分支 `codex/ui-flow-completion`。随后用户新增的平台品牌资源及页面接入不在这次业务源码绑定范围内，须另作独立增量复核。

## 独立范围

- B 编写的 P14/P15：Followups、domain/followup、services/followup、pages/followups、相关测试和 [跟进契约](../../UI_FOLLOWUP_CONTRACT.md)。检查人工 facade 兼容、结构化条件服务、纠正/撤销、回复关联、未知结果与工作台精确定位。
- C 编写的 P05/P08/P09/P19 增量：domain/taskOperations、services/taskOperations、pages/tasks、TaskWizard 新启动/恢复路径、Tasks 新动作/筛选/分页、相关测试和 [任务操作契约](../../UI_TASK_OPERATIONS_CONTRACT.md)。对 TaskWizard 的审核仅针对 C 本轮增量，不将既有 A 生命周期代码算为独立自审。
- 主 Agent 的 operationLedger 扩展：新增 followup-operations/task-operations，以及 unknown-task-starts 的配置摘要格式。兼看既有 management-operations 格式未被放宽或破坏。

**排除自作实现：** A 的本轮 Profile/P03/P04、domain/materials、services/materials、pages/profile 及资料测试不在本报告批准范围，由 B 交叉审核；历史由 A 编写的 Python facade、登录/连接/建议等待生命周期也不重新自审。主 Agent 的全局视觉、工作台、联系草稿搜索以及完整打包验收由其他检查分别覆盖，本报告不代替它们。P19 新摘要的事实状态与模板启动保护另在下文增量审核中覆盖；像素和实际分辨率视觉验收仍由主任务负责。

## 审核结论依据

P14/P15 保留真实人工登记接口；联系时间/下一步等在旧接口模式下明确随备注保存，不冒充结构化提醒。可选 followup 服务才启用成员、通道回复、修订链和原请求核对。保存前重新读取商机和画像版本；纠正保留原记录、撤销要求原因和确定回执；已读操作绑定原回复与版本。写前保存原请求标识，未知结果保留锁，关闭/换用户后的可信终态只结算原用户记录，不在新页面提示成功。旧 facade 没有原 requestId 查询能力的限制已写明，没有用内容相似性猜测成功。

任务启动保存原 draftId/revision/requestId/配置 hash/模式；直接返回还对照确认的名称、平台和画像。重新进入只查询原请求，明确未创建才能释放并增加 revision；旧锁缺原配置 hash 不自动迁移解锁。暂停/恢复/重试/取消在确认后检查服务端和当前界面的原任务指纹，持久记录成功后才派发；接收请求不是操作完成，APPLIED 还必须返回匹配 taskId 的目标状态。超时、错配、未知、存储失败、身份或页面变化均有独立保护。分页和日期只处理当前实际快照，不显示假全局总数或推算未返回的调度状态。

共享 ledger 的六项跟进键、四项任务动作键与各自 domain 编解码契约一致；新启动值绑定对应草稿键和正整数版本、64 位小写十六进制摘要与模式。错误类型/超长组合/损坏存储阻止派发，原管理操作枚举保持不变。A 的资料记录使用独立前缀，不与这些 scope 互相解析。上述本机记录均不是服务端事务或跨设备互斥保证，接口契约明确要求服务端身份、原子状态与持久幂等。

## 本次发现与修复闭环

| 发现 | 影响 | 复核状态 |
|---|---|---|
| 真实客户人工时间线仅按商机筛选，可能混入同商机 sample:true 记录且不标样例 | 样例可能被误认作客户历史事实 | B 已在关联人工时间线排除 sample 和保留样例 ID，新增真假混合回归；已独立复核 |
| 跟进日期筛选直接截 UTC 字符串 | 中国凌晨联系记录被归到前一天，与显示日期不一致 | B 已按客户端本机日历日期筛选，新增当地 00:30 序列化回归；已在 Asia/Shanghai 独立运行 |

当前没有需要阻止前端候选提交的未解决发现。后续源码变更须重新核对增量，不能沿用本报告不加审查。

## 实际执行证据

工作目录 `desktop`，使用已配置的 Node 24；以下是本审核人实际运行结果，工具 chunk 是本轮会话检索标识，不是仓库中的原始日志文件：

| 命令 | 结果 | 工具输出 |
|---|---|---|
| `TZ=Asia/Shanghai npx vitest run tests/ui/followup-completion.test.tsx tests/ui/followup-ledger.test.tsx tests/ui/followup-routing.test.tsx tests/ui/followups.test.tsx` | 4 文件，35 passed | `3ad281` |
| `npx vitest run tests/taskOperations.test.ts tests/ui/task-recovery.test.tsx tests/ui/task-actions.test.tsx tests/ui/tasks.test.tsx tests/ui/task-wizard.test.tsx tests/ui/task-start-contract.test.tsx` | 6 文件，82 passed | `258050` |
| `npm run typecheck` | 通过 | `720e4b` |
| `git diff --check` | 通过 | `c8dcef` |

前两个测试结果没有相互重叠的文件。本报告没有运行完整全仓业务测试、生产数据库操作、平台采集/外发、浏览器或客户端打包。本轮测试为隔离契约/合成数据，不能证明实际 followup/taskOperations 服务、平台授权、生产 CP-06、Mac 包或 Windows 实机安装已完成。

## 最终绑定

2026-09-09 读取仓库 HEAD，核对主任务冻结的业务源码候选为 `237a5b2a6be4f68682fcae4312f338e2338a3646`。本报告上述工作树检查及后续 P19/模板修复均绑定到该提交的对应范围，保留测试实际执行时的工具记录，不声称全部测试在提交后重跑。后续平台品牌组件、资产和接入由其他审核人独立检查；本报告不能单独充当发布批准或生产就绪结论。

## P19 摘要与 P05/P08 模板增量审核

本节追加检查主 Agent 的 TaskConfirmationSummary/confirmation.css/TaskWizard 呈现替换，以及 C 的 TaskDraftRow/localTemplates/useTaskTemplates、Tasks 接线、模板来源字段 schema 和分页样式，最终绑定 `237a5b2a6be4f68682fcae4312f338e2338a3646` 的业务增量；不把追加测试与上一节重叠套件相加。

P19 两栏摘要保留任务名、画像与版本、设备、关键词/排除词、来源、模式、日程、时区，以及所选平台的执行账号和连接状态。修改配置在启动等待中禁用；blockers 仅收起呈现，原启动校验和人工勾选仍执行。步骤条只标当前序号，不把曾经经过的平台连接步骤画成已经连接。分页增量只调整专属 label/select 横排与外层折行，不改变页码或统计语义。

模板保存为用户隔离的本机会话资料，字段白名单排除旧任务 ID、版本、运行状态与计数。从模板创建新任务时分配新 ID/revision，仍经过正常核验。来源 ID 链最多 50 个去重非空 ID，跨代继承；保存/使用都通过 ledger updater 读取最新持久锁。最终启动同时检查当前草稿和祖先，且在实际派发前再次检查，不能用预检期间新出现的祖先未决记录绕过。祖先原请求使用独立恢复面板，没有套用当前草稿成功回调，因此核对祖先成功不会声称派生任务已创建。模板不代表跨设备执行幂等，契约已明确这点。

独立实际运行 `npx vitest run tests/ui/task-templates.test.tsx tests/ui/task-wizard.test.tsx tests/ui/task-recovery.test.tsx`：**3 文件、48 passed**，工具输出 `3b7953`。覆盖模板命名/新身份/运行字段剥离、祖先链、未知或存储失败时拒绝、用户与清草稿隔离、P08 只读展开、P19 初始祖先阻断及预检后才落锁的竞态。

增量复核提出两项 P2，现已闭环：P19 当前连接账号与所选执行账号不匹配时，不应对所选行显示绿色已连接；删除草稿确认在祖先锁变化后应与列表按钮使用同一组来源检查。两项均未发现能派发实际启动的绕过。C 已修复第二项：删除弹窗的 disabled 与提交 handler 均检查自身和祖先，新增打开弹窗后祖先落锁回归；独立重复上述三个套件 **49 passed**（`194ac8`）。主 Agent 已修复 P19：只有匹配的已连接社交账号或具备采集能力的公开网站才显示绿色；账号错配/未选显示待核对/待选择，且三元条件分组经源码复查正确（`3f0730`）。该源码候选的上述增量范围无剩余 P0/P1/P2。

## 平台品牌接入的独立增量复核

2026-09-09，绑定品牌源码 `1c1567325bca971a723c87983efb0c289c57e03a`，相对业务源码 `237a5b2a6be4f68682fcae4312f338e2338a3646`。本节仅独立审核 C 编写的 Tasks、TaskWizard、pages/tasks 中的 TaskPlatforms、TaskConfirmationSummary、TaskDraftRow、TaskEvents、useTaskTemplates 及 tasks.css，以及模板展开断言的对应调整。已核对这些文件的工作树与绑定 SHA 无差异；没有重复执行全量测试。

**结论：此接入范围通过，未发现 P0/P1/P2 阻断。** 新增 span 均位于可接收短语内容的 label、button、p、dd 或 td 内，表格的 tr/td/th 结构保持完整；没有把图片放进原生 option。平台复选框继续由包围 label 提供中文名称；监控状态按钮的显式可访问名称、aria-pressed 和原执行账号 select 名称不变。共享组件使用时仅图标被隐藏，平台文字保留，未形成重复可访问名称。多平台摘要保持各平台名称与未知原名，空平台仍有文字回退。模板增加的平台行只读取已保存条件，不改变模板身份、锁或启动规则。

所有被替换位置只改变平台标识的呈现；连接/账号匹配与色调条件、平台运行状态、计数、任务动作、选择回调和执行事件筛选逻辑未变。既有重复的“连接账号”等行内动作没有因本次图标引入新的命名歧义；平台行语境继续保留。模板展开测试由连接字符串改为逐个平台名称断言，仍覆盖五个平台，没有删除原条件或状态断言。

本节**不审核 A 自作的 Platform 共享组件、CSS 和品牌资产**，这些由主 Agent/C 交叉复核；也不代替 Connections、商机/触达/跟进页面的其他作者审核、全页面可见验收、离线打包或后续合并增量审核。
