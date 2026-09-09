# a31069f 产物一致性与验收证据复核

- 复核日期：2026-09-10。
- 候选：`a31069fead15f395e7b4ec93c9c91e441beea798`。
- 范围：独立核对源码清单、构建文件、ASAR、ZIP、日志及其证明边界；未修改产品代码，未重复全量测试、构包或操作原生界面。
- 结论：**产物字节与候选绑定通过；当前原生启动验收不通过，不能据此交付为已验收客户端。** 主线程报告该新 `.app` 直接启动出现“页面未能打开”，重试仍失败；隔离 smoke 的 PASS 不能覆盖此失败。尚未确定启动故障根因。

## 已独立核对

证据目录：[ui-reviewed-integration](/Users/bruce/Developer/work/yike-ai-product-design/docs/qa/ui-reviewed-integration)。

1. 当前 HEAD 与候选一致，`desktop` Git tree 为 `b620b42cbc70c16026258a2c36991d422ab10002`。`source-binding.json` 的 279 个输入与该提交全部受控 desktop 文件集合一致；逐个将当前文件字节、SHA-256、Git blob 与 `git show <候选>:<路径>` / `git rev-parse` 核对，全部一致。
2. 当前 39 个 `.vite` 构建文件与 ASAR 内对应文件逐字节一致；`package.json` 的 36 个 renderer 资源哈希与包内字节一致。包内包含本轮拒绝将带设备与版本信息的连接按旧平台操作核对的新提示文本。
3. 下列两个产物重新计算的大小和 SHA-256 均与清单一致；ZIP 内唯一 `Contents/Resources/app.asar` 的字节哈希也等于下表 ASAR。

| 产物 | 字节数 | SHA-256 |
| --- | ---: | --- |
| `desktop/out/意客AI-darwin-arm64/意客AI.app/Contents/Resources/app.asar` | 1,771,279 | `29d93a50535cdd2cebc01304c4166d4fee8f3fc09a2184d43db2d736f06d21d6` |
| `desktop/out/make/zip/darwin/arm64/意客AI-darwin-arm64-0.2.0.zip` | 122,472,995 | `3f9e802db169d8e1ad082639894279604aa2710acc3fabda504827ee6efda735` |

4. 检查 ASAR 文件目录未发现 tests 或四个未提交 raw 模块路径。生产图排除日志进一步记录 4,759 个模块、TEST harness 引用为 0、指定未提交模块引用为 0、failures 为空。未提交模块为 `domain/rawCandidates.ts`、`services/rawCandidates.ts`、`shared/rawCandidateRead.ts`、`tests/rawCandidateReads.test.ts`；不能将其计为此候选功能。文件名检查本身不作为完整的图引用证明。
5. `tracked-tests.log` 明确运行 84 个受控测试文件，结果 **927 passed、21 skipped**；命令未包含未提交 raw 测试文件。`typecheck.log` 无错误，`make-mac.log` 记录构包完成。这些为本轮已记录执行结果，本复核未重跑，不将 21 个跳过记为通过。

`source-binding.json` 已正确限定为构建后受控输入核对，**没有证明构建前工作树干净**。当前四个未提交 raw 文件仍存在，不能改述为 clean checkout 构建。该核对证明所列源码及当前产物一致，不等于可重现构建或真实业务接通。

## 原生启动阻断与 smoke 漏检

**P1 / 客户端交付阻断：实际新包可见启动失败。** “页面未能打开、重试仍失败”为主线程实际原生 AX 观察，本审核未独立操作界面。已只读检查 `/tmp/yike-native-reviewed-20260910.log`，其中为 Node deprecation 与 IMK mach port 消息，没有足以定位 React 页面故障的堆栈；不能据此归因于某项环境、构建资源或业务接口。

独立源码核对发现 smoke 存在可明确复现于断言逻辑的漏检边界：

- [run-packaged-smoke.mjs:37](/Users/bruce/Developer/work/yike-ai-product-design/desktop/scripts/run-packaged-smoke.mjs:37) 与第 48 行仅以 `body.includes('商机工作台')` 判断页面完成。固定侧栏包含该文字；[App.tsx:62](/Users/bruce/Developer/work/yike-ai-product-design/desktop/src/renderer/app/App.tsx:62) 错误页也含“返回商机工作台”。因此错误回退页或尚未完成的懒加载页面仍可能被记为应用已渲染。
- smoke 使用 `node_modules` Electron 启动临时 app/userData、加载打包 ASAR，覆盖 `window.show` 隐藏窗口，并去除服务端配置环境变量。它并未直接执行此 `.app` 的可见启动路径。
- 保存及退出确认使用替代 dialog，保存测试确实走 IPC 与临时文件写入，但不等于实际原生文件选择器验收。退出测试另行注入 `beforeunload`，不能代替用户真实草稿触发的退出提示验收。

因此应保留 `packaged-smoke.log` 原始 PASS 作为上述有限检查的执行事实，同时撤回/避免“新包原生启动已通过”或“application render 已充分验证”的推论。最小收口为定位并修复真实启动错误，将 smoke 增加错误回退页拒绝与实际目标页内容完成断言，然后对修复后的新候选、新包和直接原生启动重新绑定证据。此报告不预先批准尚未生成的新包。

## 验收限制

本报告不自批本人此前编写的 Windows 交付脚本，不替代其他审核者的源码审查；Windows 安装、启动、退出重启、卸载、100/125/150% 缩放及连续尺寸仍须真实 Windows 回传。真实平台账号、采集、监控、发送、后台接入和收费边界不在本次字节核对通过范围内。前端整体 Goal 不能据本报告标完成。
