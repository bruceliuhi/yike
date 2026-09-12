# 平台登录状态同步 Implementation Plan

> 执行：当前主任务串行实现，独立Agent集中审核本批。遵守用户减少重复审核/构包要求，不逐文件重复审核。

**Goal:** 原生登录结束后弹窗及时显示真实安全状态，绝不自动登记/核验平台连接。

**Architecture:** 现有严格IPC新增STATUS；控制器只读flow，renderer服务校验归属，页面有界串行轮询。CHECK继续仅由人工触发。

**Tech Stack:** TypeScript、Zod、React、Vitest。

## Chunk 1：单一功能批

- [x] 在 `desktop/tests/platformConnectionController.test.ts` 新增STATUS等待/失败/完成、白名单/未知消息、错flow/平台/会话/设备和过期测试，确认无store读写、transport或stop调用。
- [x] 在 `desktop/tests/ui/platform-connection-adapter.test.ts` 新增STATUS命令及晚结果/错flow/伪CONNECTED拒绝；在 `desktop/tests/ui/platform-connection-page.test.tsx` 新增失败立即显示、LOGIN_READY不CHECK、串行超时、取消/切账号/CHECK后迟到保护。
- [x] 执行 `node node_modules/vitest/vitest.mjs run tests/platformConnectionController.test.ts tests/ui/platform-connection-adapter.test.ts tests/ui/platform-connection-page.test.tsx --maxWorkers=2`，保存新增回归RED。
- [x] 修改 `desktop/src/shared/platformConnection.ts` 增加严格STATUS、LOGIN_READY及安全错误枚举；`desktop/src/main/platformConnectionController.ts` 将失败布尔改安全错误，仅STATUS分支只读返回，不进入check。
- [x] 修改 `desktop/src/renderer/services/platformConnection.ts` 增加 `connectionLoginStatus(platform)`，只调用当前flow STATUS，拒绝错flow及其它成功响应；`contracts.ts` 可选同名服务方法，`client.ts` 接实际实现。
- [x] 修改 `desktop/src/renderer/pages/Connections.tsx` 增加串行有界观察和待检查提示；复用generation/abort守卫。失败禁用CHECK，退出/重开/CHECK取消观察，无需页面改版。
- [x] 重跑上述测试及连接合同、主进程路由、客户端/UI既有回归与 `tsc --noEmit`。独立审核仅本批差量，修复实际问题。
- [x] 将限定证据写本计划，纳入同批main提交。当前2a85dbc安装版不追认此修复。
- [ ] 与同批真实平台问题收敛后一次候选构包和实际失败页面复验，不为纯记录或其它内部模块重新构包。

## Evidence

基线 `cf07260`。首轮新增回归 **23 failed / 33 passed**，原始 `.runtime/login-status-red.json`；实现后 **56 passed**，`.runtime/login-status-green-initial.json`，随后修正一个新增测试Promise泛型类型错误。前两轮误用了系统Node24.11.1，不作为正式引擎兼容验证；最终切换仓库范围内的Node24.19.0。

扩展9文件首轮 **102 passed / 3 failed / 0 skipped**，`.runtime/login-status-green.json`。失败均来自旧 `connections.test.tsx` spread真实service后仅替换OPEN/CHECK，继承新增真实STATUS而不存在真实flow。只补夹具WAITING_LOGIN，不改生产逻辑；单文件 **6 passed / 0 failed**，`.runtime/login-status-fixture-green.json`，TypeScript exit0。去重范围为105项均已有最终通过证据，不将102+6相加为108；保留首次失败JSON。首轮组合shell的最终退出码来自tsc，实际Vitest失败以JSON为准，补测显式检查测试退出码后再做类型检查。

独立 `login_status_review` 设计/整批代码及夹具差量 GO，无阻断；shared blob `7bc904a424f4d05280f950520ed15c58ddf7bf12`、controller `def77e0a703f81d59d6841fb405861ce2ed4f6d2`、renderer服务 `f48b831bbed126a1baaeb815540d2727ad6d6d15`、页面 `bfad3b494f116942e29aff446c6c44a10e6f8a07`。核对只读无登记/停止副作用、白名单、身份与晚结果隔离，复用同字节检查。

本批未构包/覆盖安装/部署，当前2a85dbc仍保留原失败。小红书PLATFORM_RESPONSE_CHANGED的实际根因、设备重启重复核验、真实平台认证及端到端用户闭环仍待处理，不标完整Goal或发布完成。
