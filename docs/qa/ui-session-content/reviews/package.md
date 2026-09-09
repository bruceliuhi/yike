# b8b8236 包与源码输入：独立限定复核

2026-09-10。候选 **`b8b82367b34af24da218dba3796a8945d667aaa6`**。

**限定 PASS：本次实际源码输入、ASAR、ZIP、资源清单及 TEST 排除证据一致，未发现本包归档范围的 P0/P1/P2 阻断。** 本报告不是产品代码自审或原生退出链代签，不确认 Windows、真实服务或完整 Goal。

## 独立实际核验

- [输入清单](../final-build-inputs.json) 含 **355 项**，与 `git ls-tree -r --name-only b8b8236 -- desktop` 的 tracked 文件集合完全相同。对每项以 `git show <SHA>:<path>` 读取提交字节，并读取隔离构建源码 `/tmp/yike-session-content-release-b8b8236` 与当前工作区文件计算 SHA-256；三处均与清单相同，**0 不匹配**，没有只相信清单的布尔声明。
- [最终包清单](../final-mac-package.json) 指向的 `.app` 和 ZIP 均实际存在。直接计算交付 ASAR、ZIP 全量 SHA-256，ZIP CRC 检查无错误；ZIP 恰含一份 ASAR，其字节哈希与交付 `.app`、隔离原 ASAR 及 [结构记录](../final-package-structure.json) 相同。
- 直接解析实际 ASAR header 与文件内容，独立核对 **37 项 renderer 资源哈希**，全部符合结构清单。整个 archive 为 41 项，包含独立 Vite manifest、main、preload 与 package.json，资源计数没有把 manifest 冒算或漏绑。
- 实际 archive 路径与文本未见 `tests/visual`、`visual-harness`、rawCandidate 模块或 `YIKE_VISUAL_TEST_ONLY_18794`、`TEST-visual-review`、`TEST-monitor-paused` 标记；包内 Vite manifest 无 harness 引用。四个 untracked raw 草稿未进入输入集合或包，本审核未移动或删除它们。

| 产物 | SHA-256 |
|---|---|
| ASAR；同时匹配 ZIP 内及隔离原 ASAR | `f2cd0342c969ee19005041558fd91eccb4f79bb00735d4d8c51b09023daa5778` |
| ZIP | `fb9fa4ee102f14fe9b5889749386142634d71044a75ed19860dc0f4be5939823` |

实际交付目录为 `desktop/out/session-content-b8b8236/`，应用 `意客AI.app`，ZIP 为 `意客AI-darwin-arm64-0.2.0.zip`。没有借用上轮 f20b404 包或原生记录。

## 日志归属与验收边界

[生产排除日志](../logs/final-production-exclusion.log) 记录 4781 graph modules、0 harness manifest references、已检查 ASAR、failures 为空；与实际包检查相符。[packaged smoke](../logs/final-packaged-smoke.log) 有明确 PASS，但其隔离对话框替身与临时文件操作不能代替用户可见的真实 CmdQ、继续编辑、跨页、再次退出或重启链。

当前 [最终 UI 日志](../logs/final-ui-after-review.log) 实际为 **82 文件、1015 项通过**。此数为主线程既有执行，本审核仅读取，未重新运行或与 36 项限定审核、旧回归累加；空 typecheck 日志不单独产生新的退出码证据。原 RED 与测试设置更正由 README 保留，没有当作本候选新故障。

主线程正在实际原生验收本机资料保存后的会话内容退出保护；后续 AX、截图与进程绑定应明确属于本候选。本报告不提前签收该流程，也不将 Mac 替代 Windows、真实客户服务或所有页面状态。

本次仅新增此报告，没有测试重跑、构包、GUI、产品修改或 Git commit。


## 已补原生证据的独立审阅附录

同日读取最终 README、01–07 AX、运行/退出/重新打开的三份 JSON，并实际用图片工具查看原生确认截图。**原生记录一致性限定 PASS，无新增归档阻断。** 本节补齐上文包审核时尚在执行的原生部分，不改变包身份或先前字节核验结果。

- 01 显示登录前保存的 `TEST-退出保护资料`，状态“本机草稿/尚未同步”；02 与实际截图一致，真实原生确认含“放弃更改并关闭”“继续编辑”及关闭清除会话草稿提示，两按钮均完整可读。
- 03 取消退出后原行仍在，04 重新编辑显示原名称及完整 29 字正文。05 实际 AX 路由为工作台，06 再次显示同一原生退出确认；记录支持本条保护跨离开资料页仍生效，没有把跨页误记为退出或云同步。
- `native-running.json` 的候选为 b8b8236，PID 2875 的完整可执行路径位于已独立核包的 `session-content-b8b8236/意客AI.app`。`native-exited.json` 针对同一 PID，psExit=1 且输出为空，与其退出摘要一致；`native-reopened.json` 是同候选、同 app 路径的新 PID 4743。07 重开后 P04 显示“暂无资料”。主线程记录的明确放弃动作与这些前后状态一致，没有将资料清除写成意外丢失或跨重启永久保存。
- 本审核的 PID 核对针对主线程留存的原始记录，没有另行操作或关闭进程；动作顺序由主线程 CUA 执行记录承担，单独静态 AX 或 JSON 不被冒充第二次实操。
- README 与本报告当前原有引用共 **22 个本地链接，0 缺失**；候选、进程路径、退出 PID 及重开 PID 相互一致。README 将广泛 UI 状态覆盖与本次仅 P04 原生退出链清楚区分，保持 82 文件/1015 项回归与独立定向数不相加。

可以归档这条 b8b8236 的“保存资料→退出取消→原文保留→跨页再次确认→明确放弃退出→同包重开为空”的有限 Mac 原生证据。没有重复测试、包校验或 GUI 操作，没有新增签收其他页面实操、Windows、真实客户服务、永久保存或完整 Goal。
