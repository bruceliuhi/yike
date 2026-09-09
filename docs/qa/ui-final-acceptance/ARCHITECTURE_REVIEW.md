# UI 最终候选独立架构审核

日期：2026-09-09。审核者：独立架构 Agent。

**结论：PASS。** 本报告绑定源码提交 `58c8a7d3a8743f5f2eb9590e93ba8c2c66751fd9`，增量基线为 `d2a68648570d6e89ea04a1babf7e96765d1b30b1`。在下列独立审核范围内未发现新增 P0/P1 或阻止本轮前端候选交付的问题。绑定时相关源码及测试相对该提交无工作树差异。

## 独立范围与结论

- **P07 候选复核及恢复：**审核 `candidateReviewOperation.ts`、`useCandidateReviewLedger.ts`、`PendingCandidateReviews.tsx`、`Opportunities.tsx` 的决策提交/查询接线，以及共享 ledger 的 `candidate-reviews` 增量。入库/排除在派发前持久记录候选 ID、动作、原请求 ID 和人工确认快照摘要；存储失败不派发。清除普通草稿、离页及同身份重入不丢失未知保护。查询须返回唯一、同候选、非样例且原确认摘要匹配的回执，成功另核对存储状态、商机 ID 和人工复核记录；超时、一般 HTTP 错误、缺回执或错版本均不自动解锁。原候选不在当前列表时仍有核对入口，批量遇未知即停止后续派发。规则与[候选恢复契约](../../UI_CANDIDATE_REVIEW_CONTRACT.md)一致。
- **P10 结构化阶段与截止：**审核字段适配、来源/证据版本绑定、筛选排序、展示与 CSV 输出。缺失或失配事实不会推断为真实采购阶段或截止时间；导出排除公开样例，并沿用 CSV 公式防护。最终修复保留非零秒及毫秒，例如 `18:00:59.500` 不再截断为分钟；时区保持明确。参见[商机库契约](../../UI_OPPORTUNITY_LIBRARY_CONTRACT.md)。
- **TEST 恢复入口及生产隔离：**审核 `tests/visual/recovery.ts`、`RecoveryControls.tsx`、`routing.ts`、`main.tsx` 和对应测试。四类场景只操作本实例 TEST 内存，按允许的页面和身份启用；发送仅返回 UNKNOWN 或确定未送达的 FAILED，启动仅返回 UNKNOWN 或确定未启动的 REJECTED，不生成 SENT/ACCEPTED。终态核对严格绑定原请求，公开样例使用产品已有只读路由。生产排除脚本按整个 `tests/visual` 模块图及包路径覆盖新增文件，未发现生产源码反向引用测试入口。
- **P19 旧错误清除：**`TaskWizard` 的 `onSettled` 只在原启动回执通过校验并确定结束后清除旧“启动结果尚未确认”提示；确定未启动后保留草稿、取消确认勾选，不自动再次启动。

**排除自审：**本审核者编写的 P16 断开连接生命周期、相关模块/测试及共享 ledger 的 `connection-disconnects` 分支，不纳入本报告的独立通过结论，由主 Agent/其他审核者负责。未重审历史全部前端，也未操作浏览器或 Windows 主机。

## 验证证据

本审核者实际执行以下定向测试，均在 `desktop` 目录：

```sh
npx vitest run tests/ui/candidate-review-operation.test.ts tests/ui/candidates.test.tsx tests/ui/operation-ledger.test.tsx tests/ui/opportunity-library.test.ts
```

结果：**4 个文件、65 项通过**，工具输出 chunk `c699a0`。涵盖持久未知保护、错回执、身份隔离、存储失败/损坏、派发前并发落锁、离页、实际超时及时间精度。

```sh
npx vitest run tests/visual/recovery.test.ts tests/visual/recovery-pages.test.tsx tests/visual/routing.test.tsx tests/visual/isolation.test.ts
```

结果：**4 个文件、16 项通过**，工具输出 chunk `8b52ac`。包含真实 AppProvider 路由、迟到建议保护、原请求核对、公开样例不可写，以及 P19 清除旧错误后仍留在确认页且必须重新勾选。

在 `58c8a7d` 预合并阶段已阅读主 Agent 生成的全套测试结果（58 个文件、570 passed、1 skipped）、类型检查、包内冒烟和生产排除结果；当时排除结果为 `manifestHarnessReferences: 0`、`existingAsarChecked: true`、`failures: []`。此处数字保留该阶段历史，不冒充后续合并后的重建结果。当前[全套测试日志](final-tests.log)、[类型检查日志](typecheck.log)、[包内冒烟日志](packaged-smoke.log)和[生产排除日志](production-exclusion.log)由主 Agent 更新，最终提交与构建绑定以其本轮集成记录为准。这些不是本审核者重复执行的检查；跳过项不计作 Windows 通过。

## 实际边界

这是前端状态、适配契约和本轮 Mac 候选证据的有限审核，不表示真实平台采集、候选入库、发送或生产部署已接通。默认候选服务仍明确不可用；租户授权、服务端幂等、原请求权威回执、来源/画像版本校验及 PostgreSQL 原子写入仍需真实后台验收。客户端 ledger 不能替代跨设备服务端幂等。TEST 终态和截图不构成真实业务执行证据；Windows 安装、运行与外部环境验收须使用对应实际结果另行确认。

## 主线并发增量集成复核

**集成结论：PASS，未发现新增 P0/P1 或合并阻断。** 绑定正常合并提交 `b89df6c5349709ac692e4ce398e145797163ca5a`，其两个父提交为本轮 UI 候选 `58c8a7d3a8743f5f2eb9590e93ba8c2c66751fd9` 与远端 `3c16faca1fb243652f70d08327a30ddc771fc1ef`。已用提交父链及祖先检查核实双方历史完整保留。`desktop/src/renderer` 和 `desktop/tests/visual` 相对已审 UI 候选无差异，前述独立审核结论可继承；P16 自审排除继续有效。

本次只读检查远端带入的 Windows ASCII staging、单一 Node/npm 运行时、ASAR 路径规范化及候选来源 IDNA 修正：

- staging 将原 MakerSquirrel 的制作目录限定到本次私有目录，再校验产物路径后回填原输出；保留资源编辑与原包检查，失败回填有备份/恢复记录，不递归删除最终输出目录。代码对非 ASCII 系统临时目录明确拒绝，不虚称兼容。
- Windows runner 以选定 Node 直接执行已探测 npm CLI，并仅在子进程环境副本前置该 Node；运行记录只保留版本、哈希及来源模式，不序列化内部环境或路径。最低 Node 范围与清单一致为 `>=24.15.0 <25`。
- ASAR 修复只在调用提取库时规范化平台分隔符；原始 manifest 路径仍先经过资产白名单验证，主入口、preload、非空资产与禁止文件检查未被绕过。
- 候选来源使用 UTS46 非 transitional IDNA，区分 `faß.example` 与 `fass.example`，规范等价 IPv6；规范化后仍检查私网/非法主机。原 URL 摘要保留，不将来源等价错误地当作相同内容版本。新增 `idna` 直接依赖与锁文件一致。

本审核者在合并工作树实际执行：

```sh
uv run --frozen pytest tests/test_candidate_contract.py -q
```

结果：**148 passed**，工具输出 chunk `ae5941`。这是来源纯契约验证，不是数据库入库、真实网络抓取或平台连接验收。Windows增量为源码与测试读取审核；本次没有在 Mac 上冒称运行 Windows 安装器。

Forge 配置和 package 清单已改变，`58c8a7d` 的旧 Mac 包不能作为此合并提交的精确产物。主 Agent 正在另行执行合并后全套前端检查及 Mac 重建；其完成证据须独立绑定。远端 Windows 历史构建失败、未运行阶段和人工 `UNTESTED` 保持其原环境与提交范围，不因正常合并或 Mac 测试通过而自动关闭。

### 合并后的最终环境与构建结果补记

上述“正在重建”为集成审核当时状态；主 Agent 随后完成环境纠正和新包验证，本审核者已读取对应日志及[Mac 构建记录](mac-package.json)。结果仍绑定 `b89df6c5349709ac692e4ce398e145797163ca5a`，不改变前述独立 Python **148 passed** 的范围或执行归属。

首次合并测试使用 Node **24.13.1**，低于新增清单要求 `>=24.15.0 <25`，运行时门禁测试确实失败：[首次集成测试日志](integrated-tests.log)记录 **625 passed、21 skipped、1 failed**。该失败保留，不能记为全通过；主 Agent 将运行时升级至 Node **24.19.0**，未降低版本门禁或删除失败测试。

纠正后主 Agent 的[最终集成测试日志](integrated-node24-tests.log)记录 **61 个文件、626 passed、21 skipped**。跳过项为当前 macOS arm64 不适用的 Windows/真实 x64 专属检查，不计为 Windows 通过。类型检查、新 Mac `make:mac`、[ASAR 结构与哈希检查](package-check.json)、[包内冒烟](packaged-smoke.log)及[生产排除检查](production-exclusion.log)已完成。`mac-package.json` 记录 Node 24.19.0/npm 11.17.0、107 个构建输入与源提交一致、构建退出码 0，以及当前 ASAR/ZIP 哈希。

此处为已读取的主 Agent 执行证据，不是本审核者重复运行。包内冒烟使用真实 ASAR 的 main/preload/renderer 和隔离进程，仅替换保存对话框；本批未把旧客户端的可见操作证据当作新包可见验收。Windows 安装、重启、卸载及系统缩放、签名/公证、真实平台后台和全页面全部交互状态继续按构建记录的未验证范围保留。
