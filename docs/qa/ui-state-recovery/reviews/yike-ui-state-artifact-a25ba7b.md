# a25 中间 Mac 包独立字节核对

候选：`a25ba7b331e7712c4fba53b173cbbc704ec3e734`。仓库：`/Users/bruce/Developer/work/yike-ai-product-design`。

**中间产物完整性限定 PASS；不能作为最终交付包。** 新发现的 P14/P15 跨客户空间 P1 正在另外修复，该包不含后续修改；没有该候选的实际可见原生 UAT 记录。本报告只读核对源清单、文件、ASAR/ZIP 和已有日志，没有构包、启动 UI、重跑全套测试或自批 P18 实现。

## 实际独立核对

1. `native/mac-package.json` 的 candidateCommit、状态与中间包限制明确。`source-final-before.json`、`source-final-after.json` 各 296 个输入，逐项比较前后哈希及 `git show a25…:<path>` 字节均一致；重新计算排序路径/NUL/文件 SHA 清单摘要为 `5f618e546cad164185fef0b56533981efc958cc851a0547e7c1e6b96a7fe6588`。
2. manifest 列出的 5 个产物（含源图标）及 11 个证据文件重新读取字节数与 SHA-256，均相符；前后源 snapshot 文件本身的哈希也一致。
3. ZIP 实际 582 项，`ZipFile.testzip()` 未发现 CRC 错误；其唯一 `Contents/Resources/app.asar` 解出字节与独立 ASAR 完全一致。
4. 使用 `@electron/asar.extractFile` 实际读取并重算 37 个 renderer 文件以及 main、preload、Vite manifest 三项哈希，均与已保存证据一致；47 个 archive 路径中没有 visual 恢复夹具或四个 raw 草稿路径。生产模块图与重新生成输出的比较采用 Peirce 已保存、哈希核对通过的图证据：4761 模块、129 个受跟踪输入、38 个生成输出，0 项不符；本审核者没有重新构建该图。

| 产物 | 字节数 | SHA-256 |
| --- | ---: | --- |
| ASAR | 1774811 | `dbb50b11feb25e35b4d5055af106022fd64a7d71a6ff3c9e7d7f9c1556eea582` |
| ZIP | 122474078 | `f557ec55424b875df6b56f5e5de664a17b71dc2f24375c1947d6446651771806` |

路径由 `docs/qa/ui-state-recovery/native/mac-package.json` 保存；后续重建可能覆盖工作区 `desktop/out`，本报告绑定上述字节，不自动适用于路径下的新文件。候选仍为应用版本 0.2.0、darwin arm64；没有因 QA 记录更新产品版本。

## 运行证据边界

- 最终测试日志确为 **92 文件、1007 passed / 21 skipped**，不是最后点号修正前的 1005/21。typecheck、make、package-check、packaged-smoke、native-service-smoke、production-exclusion 日志均按 manifest 留存并通过哈希核对。
- packaged smoke 覆盖实际包 main/preload/renderer、固定 IPC、隔离临时文件写入/取消及退出保护；这是自动化运行，不能说成用户实际操作原生文件选择器。native-service-smoke 的网络端是本地夹具服务器，不是生产服务。
- P04/P12 的 CUA 证据来自独立 TEST 静态站点，P18 来自更早的 TEST freeze，均不能替代本生产包的可见原生 UAT。
- codesign 检查记录为 ad-hoc/linker-signed，没有 TeamIdentifier、Developer ID 或 notarization；本次未重新签名或验 Apple 分发。
- 四个未跟踪 raw 草稿和 TEST 行为不计入产品功能。Windows 安装/缩放/卸载及真实后台授权不在本次结论内。

因此可保留此包作为 a25 自动门禁和完整性中间证据；P14/P15 修复合入后必须生成新候选、新包并绑定新的验收记录，不能因本次字节一致而关闭整体 Goal。
