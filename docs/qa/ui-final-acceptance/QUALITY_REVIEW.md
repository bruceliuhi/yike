# 最终候选交付证据独立复核

日期：2026-09-09。审核者：Agent B。

**限定范围 PASS：本轮前端与 Mac 审阅候选的证据一致，未发现阻止该范围交付的 P0/P1。** 绑定整合提交 `b89df6c5349709ac692e4ce398e145797163ca5a`，UI 原候选为 `58c8a7d3a8743f5f2eb9590e93ba8c2c66751fd9`。本报告审核日志、源码输入与本地产物之间的一致性，不是正式发行或生产上线批准。

## 独立核验

1. 读取 [mac-package.json](mac-package.json)，将全部 **107 项构建输入**分别与当前文件及 `git show b89df6c:<path>` 的字节摘要比较，**0 处不符**；清单覆盖提交内 `desktop/src`、`desktop/assets`、`desktop/build` 全部文件及列出的包/构建配置。特别包含合并后的 `asciiStagingSquirrel.ts`、Forge 配置与 package lock，未沿用合并前构包结论。
2. 独立计算当前 ZIP/ASAR 摘要与 ZIP 字节数，均与清单一致；完整 ZIP CRC 检查无坏成员。ZIP 中唯一的 `Contents/Resources/app.asar` 与磁盘 ASAR 摘要相同。
3. 按 [package-check.json](package-check.json) 从 ASAR 实际读取 **32 项 renderer 资源**，全部摘要匹配；主入口为 `.vite/build/main.cjs`，preload 非空，应用版本为 `0.2.0`。该结构记录与清单嵌入的 `packageCheck` 一致；包路径中未发现 `tests/visual`、`.env`、`id_rsa` 或 `id_ed25519`。
4. 以 Git 独立确认整合提交的 `desktop/src/renderer`、`desktop/tests/visual` 相对 UI 原候选无差异。14 页 Chrome 配对检查及 P09/P15 本批底部补验见 [VISUAL_REVIEW](VISUAL_REVIEW.md)：底部均可见，P15 截图覆盖缺口已关闭，仍为滚动分屏，非一屏全展示。

上述字节/结构核验由 B 实际执行（工具输出 `92eb99`、`b95742`）。本报告没有重复全套测试或重新构包，没有启动真实业务或操作 Windows。哈希一致性不等于可复现构建、签名认证或供应链风险已经消除。

| 产物 | 独立核对的 SHA-256 |
|---|---|
| Mac ZIP，122,429,229 字节 | `472cbfb121b8ed73f595df0f66d82bdd839c31a9846616a7a61c816b00bf4886` |
| ASAR，含 ZIP 内同一 ASAR | `da270fd9f1e22bbf9d9ee7f06eca3a432e85d1b30c841657d0afd9c9d473b9bf` |
| mac-package.json | `75605e79aa467fd9e15f2271893ac32c75ba9aea8aacccadfc5246e81a5393fa` |

## 测试与构包记录

以下为根代理执行、B 阅读核对的原始日志，不能改写为 B 重跑，也不能把重叠集合相加。

| 证据 | 结果与适用范围 |
|---|---|
| [最终整合测试](integrated-node24-tests.log) | **61 文件、626 passed、21 skipped**。清单记录 Node 24.19.0 / npm 11.17.0；跳过项不计为 Windows 验收通过。 |
| [首次整合测试](integrated-tests.log) | 保留 **625 passed、21 skipped、1 failed**。失败在真实运行时版本校验，使用的旧 Node 24.13 不满足新要求；更新执行环境后的最终日志单独保存，没有删除失败证据或修改断言取绿。 |
| [合并前测试](final-tests.log) | 58 文件、570 passed、1 skipped，属于 UI 原候选记录，不能代替最终整合结果。 |
| [类型检查](typecheck.log) | `tsc --noEmit` 无诊断；根代理记录成功退出。 |
| [Mac 构建](mac-build.log) | npm 11.17.0，darwin/arm64 ZIP maker 完成；清单记录 Node 24.19.0、退出 0。旧运行时构建记录另存，不混用。 |
| [生产排除](production-exclusion.log) | 4718 个生产图模块、harness manifest 引用 0、已检查现存 ASAR、`failures: []`。这是隔离构建检查，不代表真实后台接通。 |
| [包内冒烟](packaged-smoke.log) | PASS：实际 ASAR main/preload/renderer、sandbox、自定义协议、固定 IPC、服务未配置拒绝、临时文件导出与取消、未保存退出取消及随后正常退出。 |

包内冒烟采用独立进程，保存及退出对话框由脚本替代以验证实际 IPC/文件写入和生命周期断言；没有把这次结果描述为用户对新包进行过可见安装、输入和重启验收。清单也明确未中断用户仍在运行的旧客户端，早前可见客户端证据只是历史记录。

## 作者边界与剩余交付边界

- B 自作的恢复 harness、既有 hooks/ledger、触达/跟进模块不在本报告的独立代码批准范围。harness 与本轮候选恢复由 [架构审核](ARCHITECTURE_REVIEW.md) 覆盖；连接断开等由 [代码审核](CODE_REVIEW.md) 覆盖。两份报告的 SHA 和自审排除仍按原文理解，不能扩大为整个仓库已复审。
- 本轮没有当前源代码的 Windows 安装、可见运行、重启、卸载及系统缩放证据；Mac 跳过项、单测、构包或 Chrome 截图均不能补足它们。Windows 专项进展以其 [独立记录](../WIN_CROSS_REVIEW_20260909.md) 为准。
- 代码签名、公证、更新发布、全部 P01–P20 交互状态的可见验收未完成。已记录的 [构建供应链发行门禁](../BUILD_DEPENDENCY_AUDIT_20260909.md) 也不因本轮构包成功而关闭；本报告未重新核对上游或批准风险豁免。
- TEST 状态、回执与截图只用于隔离验收。真实多平台采集/监控/触达、客户数据写入、服务端原请求幂等/权限校验及目标环境部署必须另验，不能使用本报告宣称可生产交付。

本轮可交付的是绑定上述提交与摘要的 Mac 审阅候选及证据包；上述限制须随交付保留。
