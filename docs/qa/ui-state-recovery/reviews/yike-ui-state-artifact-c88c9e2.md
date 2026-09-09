# c88c9e2 最终产物与证据质量复核

结论：**限定 PASS，可合入本批源码和验收文档；没有发现本次范围的 P0/P1。** 新包具有可核验的源码、产物和冷启动证据，完整 05A / 前端 Goal 仍未完成。

复核绑定最终测试候选 **`c88c9e20934c536a600d67dfe2ba2f7a02dd6404`**。实际构包源码为 **`f18a922b778f437400de8165e67b162fea028724`**；后端合并 `07d4b85` 和测试等待修订 `c59cf1b`、`c88c9e2` 没有改变产品或打包输入。本人本次只读核对文件、Git 对象、ZIP/ASAR、日志与已有可见证据，没有重跑全量、构包或操作原生 GUI。

## 独立字节核对

- [构包摘要](../final/release-mac-package.json)中的两份输入记录、五项产物及更新后的 22 项证据文件，尺寸与 SHA-256 均与实际文件相符。
- 构建前后 **317** 项输入哈希完全相同，并逐项匹配 Git `f18a922`。排序输入清单 SHA-256：`8c3a0f22b2cdb298dd06adc3bfe6e555f99ad1ed2fdc520479998bed8caf9c14`。
- [最终等价清单](../final/release-desktop-equivalence-c88c9e2.json)的 **177** 项生产和打包输入逐项匹配 f18 与 c88。其间 desktop 只变动 `followup-completion.test.tsx` 和 `management-scope.test.tsx`；实际等待请求派发、会话 effect 与文件选择完成，原超时、锁保留和文件禁选断言仍保留。
- 实际 ASAR：**`79a52de9d645378e0903fd93c4f49ac4c9ce703592fc1b537875708b372c86fa`**，1,826,753 字节。
- 实际 ZIP：**`75d4f8b269e8ecef2b7211d267447189bea7f940e9d1fc3e0ee8b814b185de32`**，122,488,736 字节。独立 ZIP CRC 检查通过，582 个条目中唯一应用 ASAR 与上述哈希相同。
- 使用 `@electron/asar` 独立读取包内容：38 个实际 renderer 文件（含 index 和 manifest）与构建输出一致；main、preload 及 manifest 的摘要也匹配记录。47 个归档路径未出现测试、visual 或四个 raw 草稿路径。构建图的 4,771 模块 / 139 受控输入 / 38 输出结果引用已校验哈希的构包者记录，本人未重新构建依赖图。
- 图标与批准源图标字节一致。四个未提交 raw 辅助草稿既不在候选树内，也不在实际包内，不计为已交付功能。

## 测试及非作者审核

已独立读取完整 [最终日志](../final/release-verified-tests.log)、[调用记录](../final/release-verified-test-invocation.json)，并将 [317 项测试源码清单](../final/release-verified-test-source.json)逐项与 c88 Git 内容比较：无差异。最终结果为 **101 文件通过 / 1 文件跳过，1121 passed / 22 skipped**，包含实际坏 ASAR 反例，排除未提交 raw 测试。

此前 `final/tests.log` 的 495 ASAR 输出未完成失败、`release-tests.log` 的 f18 摘要计算计时失败和 `release-final-tests.log` 的 c59 文件读取等待失败均仍保留；它们未被改写成通过，各轮数量没有累加。类型检查、构包、严格 smoke、服务桥 smoke 与生产 TEST 排除结果和日志绑定一致。

P14/P15 产品代码沿用本人 [f18 限定非作者审核](yike-ui-state-quality-f18a922.md)及其他非作者审核。本人此前编写的 P18 TEST 适配、既有 hooks 等不因本次产物核对而得到自作者批准；其外部审核保留原报告范围。

## 可见证据和文档边界

实际查看了 [冷启动图片](../final/native-cold-start.png)，并读取 [任务页 AX](../final/native-task-status.txt)、[启动绑定](../final/native-launch-binding.json)及 [原生验收说明](../final/NATIVE_ACCEPTANCE.md)：进程 PID 15583 的二进制/ASAR 与本包一致，真实 `yike://app/index.html` 工作台可见；任务页五平台的复选框名称与文本同为“读取失败”。未配置真实服务，公开研究样例未计为客户商机。

随后 Mac 锁屏，输入未成功、退出取消及重启没有继续执行。文档没有将旧包完整退出链移用到新包，也没有宣称绕过锁屏。严格 smoke 的临时文件写入、取消和退出验证仍是自动化隔离验证，不替代本包人工原生文件选择器或完整生命周期验收。

对 `docs/V02_IMPLEMENTATION_TASKBOOK.md`、`docs/INTEGRATION_STATUS.md`、根 `design-qa.md` 的本轮差异，以及本批 README / NATIVE_ACCEPTANCE 全文进行核对：495 的 P14/P15 内存 TEST 截图明确保留 495 绑定；f18 的源码回归和新包冷启动分开；P14 UNKNOWN 可见链、无人工记录时的匹配回复入口 P2、剩余同状态视觉/交互均保留待办。上述入口及合并报告共 **205 个本地链接目标存在**。本报告不把静态哈希补记为未曾记录的构建前证据。

未完成：新包输入/退出/重启和真实原生选择器、Windows 安装/缩放/连续尺寸/卸载、Apple Developer ID 签名及公证、真实资料/跟进/收发/计量后台和全部页面状态。现有 ad-hoc linker 签名没有 TeamIdentifier 或 sealed resources。以上限制与最终摘要一致，不构成将整个 Goal 标为完成的依据。
