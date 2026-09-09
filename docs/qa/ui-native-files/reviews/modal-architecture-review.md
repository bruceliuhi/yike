# 共享模态可访问层级：限定架构复核

> 最新原生证据修正：9d1825b 仅同步 aria 属性仍需一次 Tab 后顶层才进入 AX，原缺陷未因此关闭。下方原 9d 的架构/9 项测试结论保留历史；初始焦点追加见末节，须等待新包实际复验。

**结论：PASS。** 对精确候选 `9d1825b5d1ca8befd35127e536e5009997873597` 相对父提交 `e65e3fe36692cd4b0100434b90751556e46bb0ec` 的两个文件进行非作者复核，未发现本次增量的 P0/P1/P2 阻断。该结论允许继续新包原生验证，不等于 macOS 辅助功能、全部弹窗状态或完整 Goal 已验收。

日期：2026-09-10。审核范围：`desktop/src/renderer/components/ui.tsx`、`desktop/tests/ui/modal.test.tsx`，并只读核对共享 CSS、资料编辑的 sibling 确认和全局导航确认调用方式。未修改产品，未提交，未重跑全量或构包。

## 共享层行为

- `ui.tsx:210–223` 复用原 `topDialog()` 的实际 DOM 顺序，只有已注册且处于文档中的最后一个弹窗为 `aria-modal=true`。没有另建可能与键盘/焦点冲突的栈；原 Escape、Tab、focusin 和关闭按钮仍使用同一 top 判定。
- 同次父子挂载时，子 effect 即使先注册，后续父 effect 再同步仍按 DOM 后序选中子弹窗。不是按 effect 的执行次序把父弹窗误置为 top。
- `ui.tsx:312–317` 在注册和删除后重新同步。移除上层时，仍挂载的下层恢复模态；整树卸载时，不再向已删除的 map 项授予模态。原滚动锁、监听器单次安装/移除和焦点回归逻辑未改。
- StrictMode 的 setup/cleanup/setup 可重入：map 键为原 DOM 节点，删除/重新加入后全量同步；不会因为 replay 留下两个模态声明或叠加新的监听器。
- `ui.tsx:336–342` 已移除 JSX 中固定的 `aria-modal=true`。该属性由共享管理函数单独维护，React 常规重渲染无同名 prop 可覆盖它；标题、内容、busy 状态或最新 onClose 更新不会把底层重新标成 true。角色和标题关联仍由 React 管理，双方职责没有重叠。
- 未对底层节点设置 `aria-hidden` 或 `inert`，避免顶层确认实际为下层 DOM 子节点时，被祖先隐藏/禁用一起屏蔽。`aria-modal=false` 不改变普通 DOM 可见性或业务操作状态；键盘焦点仍受原 top 逻辑约束。

本次沿用已有 DOM 顺序与统一 z-index 的当前调用约定，不宣称新建了支持任意 portal、外部 DOM 重排或不同 z-index 的通用弹窗系统。仓库当前审阅的相关调用没有引入这类新用法。属性同步继续位于既有 effect 生命周期；本次不是 SSR/hydration 或首帧辅助功能时序的全面改造。

## 独立验证及归属

运行前确认工作树中的上述源码/测试与候选精确相同：

```sh
git diff --exit-code 9d1825b -- src/renderer/components/ui.tsx tests/ui/modal.test.tsx
PATH=/Users/bruce/.nvm/versions/node/v24.19.0/bin:$PATH node node_modules/vitest/vitest.mjs run tests/ui/modal.test.tsx --reporter=dot
```

工作目录为 `desktop/`。独立结果：**1 文件、9 passed**，退出码 0，工具输出 chunk `acd323`，执行时间 2026-09-10 07:11:30。覆盖新增 sibling 单一模态与关闭恢复，以及原父子同次挂载、StrictMode、逐层 Escape、Tab 焦点循环、整树卸载、隐藏/禁用元素、输入法和最新关闭回调。

新增回归直接断言上下层 aria-modal 与唯一 true；其余既有测试主要断言键盘、焦点和滚动行为，不能扩大为全部 aria 生命周期逐项测试。共享增量的其余判定来自上述源码审阅。

主线程报告的 **985 UI tests 与 typecheck** 属于主线程执行，本审核未重复，也不与独立 9 项相加。

## 原生边界

JSDOM 的属性/焦点通过不能证明 macOS Chromium 的实际 AX 树已重新暴露顶层确认。新包必须继续实际打开底层资料编辑和上层放弃确认，验证顶层标题、取消、确认可被原生辅助功能定位和操作，取消后下层可继续编辑、确认后正确关闭；其构建绑定及实际结果由主线程另记。

本次不涉及服务、权限、平台连接、后台、Windows 或生产交付。没有根据源码修复或测试绿宣称全产品完成。


## 初始焦点追加：基于 9d 的工作树增量

复核时 HEAD 仍为 `9d1825b5d1ca8befd35127e536e5009997873597`，追加仅修改前述源码与测试两文件，尚未取得新提交 SHA。此节绑定实际读取的 SHA-256：

- `desktop/src/renderer/components/ui.tsx`：`a38512e7c783e8c25284bd205fbc38d2bd19bc20fd786812b4a80f8cccea9329`。
- `desktop/tests/ui/modal.test.tsx`：`51109a9bb479a37fe63b8f5b362bc7cebf1176304eb1628777aaac140789527a`。

**限定代码/架构结论：PASS，无本追加新增 P0/P1/P2 阻断；原生缺陷仍待新包验证，不能据此关闭。**

初始聚焦从顶层 dialog 容器改为 `dialogFocusable(activeDialog.node)[0] ?? activeDialog.node`，在完成单一模态同步之后执行 `.focus()`。当前共享 Modal 的第一个可聚焦节点是固定头部关闭按钮；它没有 onFocus 业务处理，只有显式点击时调用关闭。因此挂载聚焦不会自动确认、关闭、提交或取消，亦未模拟 Enter/Space/Click。正式确认按钮仍位于 footer，保持用户主动操作。

可聚焦列表复用原键盘陷阱过滤，跳过禁用、隐藏、inert、不可见或无布局矩形元素；没有候选时仍聚焦带 `tabIndex=-1` 的原容器，保留无可聚焦控件的回退。当前模板通常总有关闭按钮，fallback 属于防御逻辑；本次未新增一个专门模拟全部控件不可见的测试，也不声称原生隐藏时序已测全。

父子同次挂载仍使用共享 topDialog 选择结果，重复 effect 只会重新聚焦同一顶层关闭按钮；StrictMode 重挂载不会触发按钮 action。原关闭后的 previous/initialFocus 回归、滚动锁及焦点约束未改。测试中将初始焦点预期由容器改为关闭按钮，与新行为一致，没有删除 Escape、Tab、输入法或清理保护断言。

独立重跑同一 modal 套件：**1 文件、9 passed**，2026-09-10 07:14:16，退出码 0，工具输出 chunk `51adef`。这是该追加字节的验证，不与原 9 项相加。主线程正在跑的 UI 回归及新包原生结果在本节写入时尚未取得，未作为通过证据引用。

主线程已明确记录原 9d 包仍需手动 Tab 才暴露 AX。新包需验证无需额外 Tab 即可定位顶层取消/确认、取消回底层以及确认退出的真实路径；本报告不使用中间 9d 原生行为冒充修复通过。
