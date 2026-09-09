# 修复候选架构差量复核

- 日期：2026-09-10。
- 冻结目录：`/tmp/yike-ui-review-20260910`。
- 完整候选：`e70c3a1d048f0f3d6b13bf74805eb60ad4a587cf`。
- 直接父提交：`99993552f1559681c8f671a57096ec23d4e9095b`。
- 整体审查基线：`a77e5828de9ecb0f3c9b60dfcebf56c96685d9bc`。

**架构结论：PASS，可以合入此前授权的前端候选范围。** 原 `9999355` 中唯一的 P1 已在此子提交关闭；继承此前未变化范围的审查结论后，完整 `e70c3a1` 未发现剩余 P0/P1 架构阻断。这是候选集成结论，不代表完整 UI Goal、Windows 实机、真实平台服务或生产上线已完成。

## 差异与修复验证

实际差量仅 3 文件、41 行新增：旧连接解析器 2 行、现有断开 UI 测试 26 行、主线程修复日志 13 行。原工作树正在开发的原始候选接入不在此提交内。退出保护/导航、P09 画像谱系、P20 日程、Windows 构建和实例核验脚本均未变更。

`desktop/src/renderer/domain/connectionDisconnect.ts:60–62` 在 `z.object.parse()` 之前拒绝任何带 `registration` 字段的对象。因而设备/连接版本标记不会再被剥离后进入旧预检或核对流程：

- CONNECTED 与 DISCONNECTED 登记回包都在旧预检入口失败，不写入新未决记录，也不调用平台级 disconnect。
- 已存在 ACKNOWLEDGED 的旧请求不能依据登记回包核销；异常发生在 `inspect()` 回写连接之前，原记录保留，也不提示成功。
- 真正未带登记字段的旧响应仍走原有校验；未改写服务契约、操作账本或平台执行能力。

三个新增测试调用真实 `ConnectionsPage`、断开 hook 和持久账本路径，仅使用隔离 TEST adapter；不是只断言新增的错误字符串或私有函数结果。

## 本次独立执行

在冻结目录、Node 24.19.0 下执行：

```sh
vitest run tests/ui/connection-disconnect.test.tsx tests/ui/connection-registry-client.test.ts tests/ui/connection-registry.test.tsx
```

实际 **3 文件、36 passed、0 skipped**，工具输出 `1c93b3`。首次尝试因审核目录的依赖软链接临时缺失，vitest/zod 无法加载，未进入测试；主线程恢复依赖后上述命令正常执行。未修改源码或测试，未安装/升级依赖。

另直接导入候选源码验证 4 类带字段输入：正常登记对象、`registration: undefined`、`registration: null`、继承的 registration 字段，均被拒绝；不含该字段的旧连接保持可解析。工具输出 `786d02`：

```json
{"rejected":[true,true,true,true],"legacyPreserved":true}
```

父提交的独立 7 套 98 passed / 4 Windows 条件 skipped 与 279/279 桌面输入哈希一致记录，仍只表示父候选的当时验证。未把两轮测试数量相加，也未将旧包摘要继承为修复后重新构建的摘要。

`git diff --check` 差量仅提示 `docs/qa/ui-connection-registry/review-fix.log:13` 的日志 EOF 空行；这是保存原始命令输出产生的空白，不是源码或架构阻断，不报告为全差异检查 clean。

## 继承范围与限制

完整原审核保留于 `/tmp/yike-ui-architecture-9999355.md`，其 **NEEDS_FIX** 结论不回写。此文只关闭该 SHA 的 registration 问题，并给出修复后候选的集成结论。

- P20 初版有本审阅者参与实现，仍不由此文作为唯一独立代码批准；按主线程分工由 Peirce 代码复核、Hubble 质量复核覆盖。本报告独立重点仍为主线程的退出保护/导航/连接、Peirce 的 P09 和 Windows 脚本。
- 此次未运行 Windows/PowerShell、未重新构建或打开 Mac 包、未执行真实受限 PostgreSQL + HTTPS 登录/连接贯通，也未执行真实平台采集或外发。
- 修复后产物须由整合流程重新绑定最终源码并提供对应构建证据。历史 Mac/Windows 成功、TEST 界面和自动测试不能替代当前候选的实机人工验收。
- 全页面状态可见验收、字体/像素对齐、系统保存窗口、Windows 缩放/安装/卸载等仍按各自证据推进；此候选可合入不等于这些剩余项完成。

本次只读审核候选；唯一新增文件为此 `/tmp` 报告。现有 `desktop/node_modules` 依赖软链接由主线程统一管理，不属于源码差量。
