# 冻结候选独立代码审核

- 日期：2026-09-10（Asia/Shanghai）
- 候选：`99993552f1559681c8f671a57096ec23d4e9095b`
- 基线：`a77e5828de9ecb0f3c9b60dfcebf56c96685d9bc`
- 审核目录：`/tmp/yike-ui-review-20260910`
- 方法：只读核对上述 Git 增量及必要调用上下文；独立运行针对性测试和类型检查。未改变产品源码、未运行真实平台写入、未使用本审核之外的新工作树改动。

## 结论

在该候选已接通的真实读取路径中，未发现新增 P0/P1 阻断。退出保护、日程版本门禁、监控导航归属、固定连接 GET 和多设备登记显示可继续按其声明范围交付。此结论不批准真实采集、旧平台写入适配、监控调度或 Windows 实机验收。

发现一项具体 P2：旧连接核对解析会丢掉 `registration`，需在入口拒绝后再合入未来写入适配。主线程已接受修复；本报告仍绑定原候选，不将尚未审核的新修复计为通过。

P09 `TaskProfileStatus` / `taskProfile` /实体映射是本审核者此前编写的部分，本次仅读作上下文，不作为该部分唯一批准者；另由独立架构与质量审核覆盖。

## P2：旧核对入口仍能把设备登记记录降为旧连接

- 位置：`desktop/src/renderer/domain/connectionDisconnect.ts:42–63`（旧解析器）；新增保护位于 `:65–67`。
- `checkedDisconnectConnection` 的 Zod 对象未声明或拒绝 `registration`，默认剥离该字段。新增 `disconnectTarget` 只能拒绝尚携带该字段的对象。
- 最小隔离反例：给 `checkedDisconnectConnection` 一个 `platform=xhs,status=CONNECTED,accountId=TEST-original,capabilities=[]` 且含 `registration={connectionId,deviceId,version,connectedAt,disconnectedAt}` 的对象，再交给 `disconnectTarget`。实际输出为 `checkedRegistered=false`，旧目标被接受为 `{platform:'xhs',accountId:'TEST-original'}`。验证仅调用域函数，无平台请求。
- 影响：未来旧 `checkConnection` 返回登记对象时，旧断开预检/结果核对可能失去设备与连接版本；读取合并也可能把其视为旧记录。应在 `checkedDisconnectConnection` 原始输入处拒绝任何登记对象，不能先剥字段再判断。
- 当前限制：`desktop/src/renderer/services/client.ts:271–273` 的 connect/checkConnection/disconnect 仍返回 unavailable；真实 GET 登记表不提供旧断开按钮，任务 `startBlockers` 也拒绝 registration。因此这不是当前候选已经可触发的真实平台写入路径，不上调为 P1。
- 建议回归：在 `connection-registry-client.test.ts` 覆盖带 registration 的 CONNECTED 和 DISCONNECTED 检查响应都拒绝；在旧断开套件覆盖预检不 dispatch、核对不核销原 pending/acknowledged 锁。

## 核对要点

1. **退出保护**：`sessionDraftExit` 在 beforeunload 当场读取 `hasSessionTaskDrafts`；包含已离页的本机会话草稿/库/模板和内存编辑。未加入内部 route guard，未将这些内容改称持久存储。清除后的 tombstone 防止存储删除失败复活旧内容；原生默认继续编辑，只有明确放弃才允许退出。没有变更 IPC、Origin 或管理员边界。
2. **日程**：v1 策略保留进 schema、指纹、最终摘要和启动绑定；旧无版本草稿不自动迁移。v1 在初始状态、异步预检后和落启动锁前检查执行器声明；缺声明仍可编辑/保存但不派发。跨日、DST、离线规则是配置合同和展示，未新增调度器、未产生虚构 nextRunAt。
3. **导航**：监控任务的新建、连接、确认三步由同一 mode 查询决定标题和左侧归属，单次任务仍归线索采集；没有扩大路由允许范围。
4. **连接读取**：新增 IPC 仅固定 GET `/api/ui/connections`，不接受调用者路径/身份/headers。解码校验明确平台枚举、ID、状态、时间、整数版本及重复 connectionId；错误不冒充空账号列表。服务端额外凭证字段不进入客户端对象，CONNECTED 登记仍无推导能力。表格保留同账号不同设备，刷新隐藏旧详情，user/space/version 改变后旧读响应被抑制。
5. **Windows 证据**：构建前后核对完整 SHA、Git 状态、跟踪文件真实字节及受检输入目录中的额外/链接文件；失败不能只凭各 stage 为绿变成功。报告分列自动测试 passed/skipped/todo，原始 reporter 删除，人工 24 项继续 UNTESTED。安装身份核对只读取指定可见 PID、启动时间和 EXE/ASAR 哈希，固定错误码，不停止用户进程；它只证明包身份，不证明安装/缩放/业务成功。

## 本次独立验证

Node `v24.19.0`；候选临时使用已存在的 `desktop/node_modules` 符号链接解析依赖，该链接不属于产品变更。

```text
npm exec -- vitest run
  tests/ui/connection-registry-client.test.ts
  tests/ui/connection-registry.test.tsx
  tests/ui/connections.test.tsx
  tests/ui/connection-disconnect.test.tsx
  tests/ui/session-draft-exit.test.tsx
  tests/ui/hooks.test.tsx
  tests/ui/navigation.test.tsx
  tests/ui/schedule-policy.test.ts
  tests/ui/schedule-policy-ui.test.tsx
  tests/windowsBuildEvidence.test.mjs
  tests/windowsSourceBinding.test.mjs
```

- 11 files：**131 passed / 4 skipped**（共 135；00:51:01，输出 `113a39`）。
- 四个 skipped 为 Windows bootstrap、低版本 Windows Node、非支持 Windows 架构及 Windows npm discovery 条件；不是通过。
- `npm run typecheck`：通过（输出 `5d628d`）。
- 全量 `git diff --check base..candidate` 未通过：命中已提交构建/测试 `.log` 的尾随空格和末尾空行；未发现产品源码空白错误。原始日志未在只读审核中修改，此项不作为运行阻断。
- 上述登记降级反例：实际域函数输出确认（`f7795a`）。先前尝试 esbuild 不可用，未作为通过；最终使用 Node stripTypeScriptTypes 仅加载原域函数。

未重复运行全部客户端测试、Mac 构建或浏览器/原生可见验收；未将主线程日志当成本审核者独立执行。PowerShell 在 Windows 上的解析、错误路径及新安装实例核验仍须 Windows 真实执行；本机 JS 临时仓库/哈希/失败报告测试不能替代它们。
