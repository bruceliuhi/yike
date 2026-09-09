# 冻结候选差量复核

- 日期：2026-09-10（Asia/Shanghai）
- 完整候选：`e70c3a1d048f0f3d6b13bf74805eb60ad4a587cf`
- 直接父提交：`99993552f1559681c8f671a57096ec23d4e9095b`
- 完整审核基线：`a77e5828de9ecb0f3c9b60dfcebf56c96685d9bc`
- 冻结目录：`/tmp/yike-ui-review-20260910`
- 继承原报告：[9999355 独立代码审核](yike-ui-code-9999355.md)。原报告未覆盖或改写。

## 结论

**该完整候选在本次独立代码审核范围内可合入。未发现新增 P0/P1；原登记连接降级 P2 已关闭。**

本次仅核对父提交到候选的三文件差量：`connectionDisconnect.ts` 两行入口保护、`connection-disconnect.test.tsx` 三项回归、修复日志。其余产品源码与此前已审父提交相同，继承原报告中退出保护、日程、导航、固定连接读取及 Windows 证据脚本的限定结论。没有读取主工作区后续 raw 候选开发。

该结论不等同于平台登录/断开/采集/调度已真实接通，也不等同于 Windows 实机、安装/卸载、签名或新包可见验收。P09 为本审核者此前作者部分，不作为该部分唯一批准；仍依赖另两名独立审核。

## 修复核对

- `desktop/src/renderer/domain/connectionDisconnect.ts:60–61` 在 Zod 解析之前检查原始对象是否存在 `registration` 字段并拒绝。字段不会再被 Zod 剥离后变成旧平台/账号对象。
- CONNECTED 和 DISCONNECTED 登记响应均不能通过旧预检；新回归确认不调用 `disconnect`，不生成新操作锁。
- 原 ACKNOWLEDGED 请求在收到带登记信息的 DISCONNECTED 响应时仍保留原锁，未发成功通知。错误发生在 `onConnection` 合并及核销之前，避免退化为旧操作行。
- 额外只读域函数验证：`registration: undefined`、`null`、不完整对象以及继承该字段的对象都被拒绝（四种均 REJECTED）。此反例仅调用本地函数，无外部请求。

## 本次独立验证

Node `v24.19.0`；仅临时链接依赖，未修改产品源码。

```text
npm exec -- vitest run
  tests/ui/connection-disconnect.test.tsx
  tests/ui/connection-registry-client.test.ts
  tests/ui/connection-registry.test.tsx
```

- **3 files / 36 passed，0 skipped**（00:59:07，输出 `3c074c`）。
- `npm run typecheck`：通过（`aa87e9`）。
- 差量产品源码及测试 `git diff --check`：通过（`3f4527`）。
- 四类含登记字段对象的独立拒绝检查：通过（`3eb7da`）。
- 首次启动验证时冻结目录未带依赖链接，命令因缺 `tsc`/npm 本地解析失败，未计入通过；恢复授权的原依赖链接后完成以上验证。未安装新依赖。

父候选 11 套 131 passed / 4 Windows 条件 skipped 是前次范围证据，与此次 36 项存在重叠，不累加为新的测试总数。本次未重跑全套、Mac 构建或 Windows 脚本实机路径；原报告的证据边界保留。
