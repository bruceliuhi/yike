# UI interactions 独立质量复核

最终源码候选 SHA：**`a9f3078b98ffe443ee5b7d95b7bc5ff55530a2e5`**。已对上一受审提交 `8011a30635d9c66ff2e22fe45e9e5adef6bb087d` 的实际增量完成核对。结论为 **PASS（限定于本报告所列前端代码与契约范围）**，没有新的 P0/P1 阻断，不表示生产管理服务或安装包验收完成。

## 审核范围与独立性

审核人：Agent B（design_handoff_inventory）。本次只读交叉审核其他 Agent 编写的 P18 管理实现：

- [管理类型](../../../desktop/src/renderer/domain/management.ts)、[服务契约](../../../desktop/src/renderer/services/management.ts)。
- [ManagementActions](../../../desktop/src/renderer/pages/settings/ManagementActions.tsx)、[useManagedOperation](../../../desktop/src/renderer/pages/settings/useManagedOperation.ts)、[useManagementScope](../../../desktop/src/renderer/pages/settings/useManagementScope.ts)，及 Settings 的调用边界。
- 两份 P18 管理与作用域测试；导出/保存契约作为依赖边界读取，没有把它等同于完整桌面保存层独立审计。

排除本人编写的 P12/P13、触达类型/服务、触达测试、隔离视觉 harness 接入，以及本人先前编写的共享 hooks/ledger 基础模块。没有用自作模块测试通过来代替独立复核；本轮新增管理 ledger scope 的调用方式在 P18 路径中检查，基础存储实现由其他审核者负责。

## 检查结果

有限范围内未发现新的 P0/P1 阻断，P18 前端契约和异步边界通过该候选提交的质量复核：

1. 预览绑定空间、revision、设备、操作、目标版本和备份 hash；过期、换输入/服务实例/作用域后的旧确认不能执行。
2. hash 与导出响应返回后重查当前作用域；窗口关闭、空间变化或同一空间的 revision 变化后，不继续上传旧备份或发起旧文件保存。文件读取有独立代次和读取中禁用状态。
3. 执行前持久化原 requestId；存储失败不派发，HTTP/网络错误和 30 秒等待超时保持未知。只有绑定原 requestId、类型和空间的确定终态才清除记录，查询不会自动重新执行。
4. 备份拒绝异空间、未知版本和明显凭据字段；保存成功与取消、失败、浏览器发起下载的回执分开表达。
5. 默认生产管理适配保持 unavailable；TEST 视觉工厂不执行恢复、更新、导出或设备更改。

## 实际测试证据

2026-09-09，审核者在 `desktop` 目录使用 Node.js 24 实际运行：

```sh
npx vitest run tests/ui/management.test.tsx tests/ui/management-scope.test.tsx
```

在 `8011a30635d9c66ff2e22fe45e9e5adef6bb087d` 上的独立运行结果：**2 个测试文件、14 项通过**。工具输出 chunk：`584201`；测试运行耗时约 1.50 秒。最终候选的这两份测试和 P18 业务逻辑均未改变，下述增量核对后沿用此证据。本审核者没有把该命令重跑结果冒称为最终 SHA 的新运行；此结果替代预审阶段的 13 项计数，不将两轮运行相加。

管理测试覆盖授权与影响确认、错空间回执保持锁、确定失败收敛、30 秒超时后保留原请求锁、过期/错配预览、持久化失败不派发、保存取消、异空间备份、恢复 hash、更新失败/回退状态、敏感字段扫描。作用域测试覆盖导出期间空间变化、同空间 revision 变化、digest 等待期间关闭窗口后不上传，以及文件读取期间禁选、完成后恢复。用户身份、服务实例等额外作用域边界同时做了源码检查，不把每种组合都声称为独立测试覆盖。

根 Agent 报告最终源码候选的桌面全套结果为 **37 个测试文件、362 项通过**；本审核者未重复运行全套。上述 14 项属于其覆盖范围，不与 362 相加，也不与先前各轮的局部测试数量累加。

## 最终候选增量适用说明

审核时实际 HEAD 为 `a9f3078b98ffe443ee5b7d95b7bc5ff55530a2e5`。对 `8011a306… → a9f3078b…` 的提交差异核对结果：

- P18 的 `ManagementActions.tsx` 仅将更新、客户数据两个区域的外层 Fragment 替换为带类名的 div；`base.css` 增加 grid 间距、按钮对齐和分隔线样式。输入 hash、预览确认、作用域校验、持久防重、执行/核对、导出保存和备份解析流程均未改变。
- P18 类型、服务契约、`useManagedOperation`、`useManagementScope`、Settings 调用及两份管理测试与前一受审提交一致。因此原有限范围 P18 结论适用于最终源码候选；此次没有将 CSS 调整声称为新的业务能力或完整视觉验收。
- 其余增量为 P12 队列回草稿及异步 hashchange 用途切换修复、相关测试，属于本人产物，明确排除在本独立质量结论之外，由其他 Agent 交叉复核。

## 保留的接入条件

- 服务端必须把 `FAILED / CANCELLED` 定义为确定终态，不能映射超时、查无记录或仅收到取消申请。还须执行权限复验、持久幂等、真实执行/补偿及回执保存。
- 同 userId 跨空间后，原未决请求会因空间不匹配继续保守阻塞；不能靠清草稿解除。当前未宣称支持完整多空间操作管理。
- 敏感字段扫描不是业务字段白名单。服务端负责明确可导出/可恢复字段、数据归属和完整性，不能导出凭据或恢复服务端环境。
- 本次没有验证真实生产管理服务、真实安装/回退、真实客户备份恢复或 Windows 实机；没有重跑业务全套、浏览器截图或安装包验收。根 Agent 的 Mac 重打包工作不属于此处已完成的独立质量证据。

上述条件已写入 [P18 管理契约](../../UI_MANAGEMENT_CONTRACT.md)。最终结论仅绑定 `a9f3078b98ffe443ee5b7d95b7bc5ff55530a2e5` 的受审范围；后续若修改这些源码、契约或测试，需对实际增量重新复核。
