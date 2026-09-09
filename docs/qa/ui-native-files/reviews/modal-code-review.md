# 共享弹窗模态声明：独立代码复核

日期：2026-09-10。基线 `e65e3fe36692cd4b0100434b90751556e46bb0ec`，审查时 HEAD `9d1825b5d1ca8befd35127e536e5009997873597`；审核根代理未提交的两文件差异，不审批其他工作区改动。本 Agent 未编写实现或回归测试。

**限定代码 PASS：未发现新增 P0/P1 或需先修复的代码阻断。** 此结论不替代 macOS 原生辅助功能树复验。

## 复核判断

- `ui.tsx:217–224,313,317` 仅在现有弹窗栈注册/注销后同步 `aria-modal`：最上层 true，其他 false。顶层继续复用按 DOM 顺序查询的 `topDialog()`，不按 effect 登记顺序推断，父子同次挂载时子层仍为顶层。
- 未给底层添加 `aria-hidden` 或 `inert`，因此内嵌确认框不会因为祖先被隐藏而一起失去可访问性。关闭上层后立即重新声明底层模态。
- StrictMode 的 setup/cleanup/setup 仍使用原 Map 生命周期，同步函数只更新属性，不增减事件监听。焦点陷阱、Escape 只关闭一层、关闭回调、焦点恢复与滚动锁逻辑均未改动；JSX 不再固定写 `aria-modal=true`，后续普通渲染不会把底层重写成 true。
- 保持原组件“DOM 顺序代表层级”的既有约定；本修复不改变层级 DOM、视觉、业务确认或资料保存/撤销动作。

## 独立验证

使用 Node 24 执行 `node node_modules/vitest/vitest.mjs run tests/ui/modal.test.tsx`：**1 文件 / 9 passed，exit 0**，日志 `/tmp/yike-modal-code-review-tests.log`。涵盖新增 sibling 的唯一模态声明及恢复，并验证嵌套、同次挂载、StrictMode、整树卸载、Tab/Shift+Tab、隐藏/禁用控件、输入法与最新关闭回调。jsdom 属性和焦点断言不能证明 Chromium/macOS AX 实际选择了正确确认框；原生验证由主线程执行并单独记录。

## 审核输入 SHA-256

- `desktop/src/renderer/components/ui.tsx`：`e0d0cf7022339ef5c7e4c86bc6d84d52c48e1bcf9248ea5c8cd2a0690b4eaa9e`
- `desktop/tests/ui/modal.test.tsx`：`cee20acda59d0066c324a44710ffeea3231185ad8b92a4310687413c1f63674e`

本 Agent 没有改产品/测试文件、运行 GUI、构包或提交 Git。

## 追加：9d1825b 后初始焦点窄修

基线 `9d1825b5d1ca8befd35127e536e5009997873597`。主线程报告该版本原生 AX 在按一次 Tab 后才更新，因此上文仅保留代码结论，**不把 9d1825b 记为原生问题已解决**。

本次独立只读复核 `ui.tsx:314–316`：注册及模态同步后，将初始焦点交给当前顶层首个可聚焦元素，无元素则退回容器。复用既有过滤函数，排除禁用、隐藏、inert、负 tabindex 与不可布局控件；当前 Modal 结构中正常首项为关闭按钮，聚焦不会执行关闭/确认。父子同次挂载仍通过 topDialog 选择子层，后续父层注册不会把焦点移到底层。卸载恢复、键盘陷阱、Escape、回调与业务动作未改。

**追加限定代码 PASS，未发现新增 P0/P1 或阻断。** 独立同套 1 文件 / 9 passed / exit 0，日志 `/tmp/yike-modal-initial-focus-review-tests.log`；调整后的断言明确检查嵌套首焦点为关闭按钮，原逐层返回触发按钮、StrictMode 与键盘循环断言保留。此结果与上一轮重叠，不相加。原生 AX 是否无需 Tab 即正确暴露确认框，等待主线程第二包复验。

本次输入 SHA-256：

- `desktop/src/renderer/components/ui.tsx`：`a38512e7c783e8c25284bd205fbc38d2bd19bc20fd786812b4a80f8cccea9329`
- `desktop/tests/ui/modal.test.tsx`：`51109a9bb479a37fe63b8f5b362bc7cebf1176304eb1628777aaac140789527a`
