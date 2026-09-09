# 07d4b85 限定合并质量复核

结论：**PASS（仅合并完整性）**。本次未发现合并造成的 P0/P1；这不是后端重新验收、最终安装包放行或整个前端 Goal 完成结论。

- 复核提交：`07d4b85b557774f96dd9e0d916a010ef8ce70147`。
- 第一父提交：`f18a922b778f437400de8165e67b162fea028724`；远端父提交：`a9d18db99255a7fe272e24a9260095462a1e3612`。已核实为保留双方历史的普通合并。
- 本次只读核对 Git 对象、范围差异、原始测试日志与未跟踪文件；未修改源码、运行全量测试或操作客户端。

## 已核对的保留范围

| 范围 | 独立核对结果 |
| --- | --- |
| 桌面产品与桌面测试 | `git diff f18a922 07d4b85 -- desktop` 为空；两者目录树均为 `42b26591fbfde6830cd0cd004ba18d97d45b10f0`。f18 的 P14/P15 修复未被远端旧桌面内容覆盖。 |
| 后端 | `pilot` 与远端父提交完全一致，树为 `e4143f519301324dff6a23927b60c5db0c79a549`。 |
| 迁移与 Python 测试 | 与远端父提交完全一致，树分别为 `3a1e928ae909c7b7ff1d736b7aa5ee9008b26dc3`、`2a9f0913d6f8707d8b4d363afff805348df4ea1f`。 |
| 远端文档与任务 | `deploy`、`docs/INTEGRATION_STATUS.md`、`docs/V02_IMPLEMENTATION_TASKBOOK.md`、`docs/contracts`、`docs/handoffs`、`docs/qa/V02_OPPORTUNITY_SOURCE_EVIDENCE.md`、`docs/superpowers/plans` 对远端父提交无差异。新增商机来源证据合同、迁移 115、运行组合与 Windows 设备签名规划均保留；规划和缺失接入没有被改写为已实现。 |
| 本地原始候选草稿 | 四个 `rawCandidates.ts` / `rawCandidateRead.ts` / `rawCandidateReads.test.ts` 路径仍为未跟踪文件，`git ls-tree` 确认不在该候选中。 |
| 差异格式 | `git diff f18a922 07d4b85 --check` 通过。 |

合并相对 f18 的 18 个改动仅来自上述远端后端和文档范围。既有独立 [f18 跟进代码复核](yike-ui-state-quality-f18a922.md) 继续绑定 f18；本报告只确认其产品字节在合并中保留。本人此前编写的 P18 TEST 适配不在本次独立代码批准范围，其非作者审核另见已有架构报告。

## 测试与交付边界

已读取 [release-tests.log](../final/release-tests.log) 和 [调用清单](../final/release-test-invocation.json)：该次真实结果为 **1 failed / 1120 passed / 22 skipped**，失败是 `followup-completion.test.tsx` 在异步摘要计算完成前断言 `mutate` 已调用。原始红色记录保留，不能写成全量通过。另一个较早的 `final/tests.log` 为不同运行，不能与此计数混用。

复核时工作区 HEAD 已到 `c59cf1b68d5446be6a4fbb2ea9d6e9815f1a349e`，它是后续测试等待时序修订，不属于本报告的 `07d4b85` 合并结论。其最终全量结果及新安装包的 source/ASAR/ZIP 绑定、实际原生可见验收须由后续证据单独确认。本报告未将中间 a25/495 的可见记录改绑为合并后客户端，也未宣称 Windows、真实后台或全部恢复状态已验收。
