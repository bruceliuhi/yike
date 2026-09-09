# e65e3fe Mac 包与源码证据独立复核

2026-09-10。候选：`e65e3fe36692cd4b0100434b90751556e46bb0ec`。

**限定 PASS：实际产物、源码输入、包结构及排除证据相互一致，本次范围未发现 P0/P1/P2 阻断。** 此结论仅用于本包证据归档，不代表原生文件操作、Windows、真实服务或完整 Goal 已通过。

## 独立执行的核对

1. 用 `git ls-tree -r --name-only <candidate> -- desktop` 比较输入集合，实际 tracked desktop 文件为 **347 项**，与 [输入清单](../final-build-inputs.json) 完全相同，无漏项或额外项。逐项通过 `git show <candidate>:<path>` 取得提交字节，再分别计算提交、`/tmp/yike-native-files-release-e65e3fe` 隔离源码及当前工作区文件 SHA-256，均与清单相同；没有仅相信 `matchesCommit: true`。
2. [包摘要](../final-mac-package.json) 的 app 和 ZIP 均实际存在。读取实际 `.app/Contents/Resources/app.asar` 与 ZIP 全量字节计算 SHA；Python `zipfile.testzip()` 无 CRC 错误，ZIP 中恰有一份 app.asar，解压字节哈希与独立 app 相同。
3. 隔离构包目录中的原 ASAR 与交付目录复制后的 ASAR 完全相同，和 [包结构记录](../final-package-structure.json) 的 archiveSha256 一致。
4. 直接解析实际 ASAR header/文件偏移，核对 **37 项 renderer 资源**的字节哈希，全部符合结构记录。ASAR renderer 下另有 `.vite/manifest.json`；这是包校验脚本明确从资源集合中单独读取的 Vite 清单，因此实际 renderer 文件 38 项与报告的资源 37 项不矛盾。全部 archive 共 41 项，包括 main、preload、renderer 及 package.json。
5. 实际 ASAR 路径和文本内容未见 `tests/visual`、`visual-harness`、rawCandidate 模块或隔离标记 `YIKE_VISUAL_TEST_ONLY_18794`、`TEST-visual-review`、`TEST-monitor-paused`。包内 Vite 清单无 TEST harness 引用。四个 untracked raw 草稿未出现在 347 项输入集合中，也未进入 archive；本次没有移动或删除它们。

| 对象 | SHA-256 |
|---|---|
| 实际 ASAR / ZIP 内 ASAR / 隔离原 ASAR | `acd8b059b41a73dc109c3d288edb00ad571cf6a4f5c1896036bd12c12212db87` |
| 实际 ZIP | `f67a8f69c58cd2661ee0e909e8904131ede2714933655e9ab98fb8337f331384` |

交付路径为 `desktop/out/native-files-e65e3fe/意客AI.app` 与同目录 `意客AI-darwin-arm64-0.2.0.zip`；源码仍为 0.2.0，没有用本次 QA 擅改版本。

## 已读日志与边界

- [Mac 构包日志](../logs/final-mac-build.log) 记录 darwin/arm64 distributable 构建完成；[生产排除日志](../logs/final-production-exclusion.log) 记录 4778 graph modules、0 manifest harness references、已检查 ASAR、failures 为空。独立实际包内容检查与该结果相符。
- [packaged smoke](../logs/final-packaged-smoke.log) 有明确 PASS。已读对应脚本：保存对话框与关闭确认在隔离 smoke 进程内被替换，临时文件写入是真实的，但**不构成实际原生选择器或用户确认过程验收**。主线程当前执行的原生导入/取消应以另存的 CUA/AX/截图及随后 README 为准，本报告不预先签收。
- 类型日志为空不单独证明退出码，本报告不由此新增类型检查或全量测试结论；未重新执行测试、构包、GUI 或 Windows 操作。构包日志中的 Node/打包警告未冒报为零警告。
- 当前已有 `native-process.txt` 指向本候选 app 路径；本审核只检查该记录和产物路径，没有接管或重复主线程原生操作。真实 backend、Mac 签名/公证、Windows 安装/缩放/卸载及全部页面状态均不在本次范围。

审核仅新增此报告，未修改产品源码、构建输入、包或其它 QA 记录，未进行 Git commit。
