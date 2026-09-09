# UI 交互增量独立代码复核

状态：**PASS，绑定最终源码候选 `a9f3078b98ffe443ee5b7d95b7bc5ff55530a2e5`**。

审核工作树为 `codex/ui-interactions`，父基线为 `15ddb7039e385c9adbda04bfd553bf8d222e6308`。本结论针对父基线至上述源码候选的交互增量，不能据此把新功能归入父基线，也不代表安装包或生产服务已经验收。冻结后核对 HEAD 与运行源码工作树无差异；仅有文档与 QA 材料继续收口。`8011a30635d9c66ff2e22fe45e9e5adef6bb087d` 为过程候选；最终候选在此基础上增加已复核的队列导航/用途修复及 P18 间距，不能用过程包替代最终包。

## 范围与独立性

- A 的 P01/P06/P17/P20：`Login.tsx`、`Connections.tsx`、`TaskWizard.tsx`、`app/context.tsx`、`app/boundedRequest.ts` 及相应新增回归。
- B 的 P12/P13：`Outreach.tsx`、`OutreachQueue.tsx`、`domain/outreach.ts`、`services/outreach.ts`、可选服务契约、发送 ledger 四段键兼容及队列/核对测试。
- 主代理的 P18：`Settings.tsx`、`domain/management.ts`、`services/management.ts`、`pages/settings/ManagementActions.tsx`、`useManagementScope.ts`、抽取后的 `useManagedOperation.ts`、management ledger scope 及相关回归。
- 同步核对 [触达契约](../../UI_OUTREACH_CONTRACT.md) 中的服务未接通、服务端幂等及真实渠道验收边界。

审核者未编写以上本轮实现。部分已有 UI 测试由本审核者在先前轮次编写，因此它们只是回归证据，不能单独作为独立实现审核。本审核者本轮编写的原生 `saveExport`、下载 helper、P10 导出改动及其测试不在此独立结论内；由另一审核者的 [原生导出复核](NATIVE_EXPORT_REVIEW.md) 覆盖。

## 结论

当前范围未发现待修 P0/P1，可进入统一候选构建与验收。本轮发现的下列具体问题已修复并复查：

1. **P01 登录和首屏等待有明确结束条件。** 登录交换、会话确认及首屏 session bootstrap 均有 30 秒等待上限。超时后的旧会话响应必须同时经过 AbortSignal 和请求代次检查才能更新全局身份，不能把较新登录覆盖为 guest，亦不能让旧身份触发工作台跳转。短信换号会丢弃旧请求、清除旧验证码和倒计时；登录期间阻止重复提交。超时文案保留“结果尚未确认”，没有宣称服务端撤销了动作。
2. **P06/P20 保留人工搜索条件。** AI 建议按任务、画像及版本、请求代次关联，45 秒超时或取消后保留当前输入；保存、换步骤、换画像及离页后旧结果不能自动改写草稿。生成期间有人工作业时需要显式合并预览，画像来源标记保留到确认摘要。P17 打开平台原生授权窗口和检查连接有 30 秒等待上限；关闭或切换平台后的旧成功响应不能变成当前平台已连接。
3. **P18 操作必须绑定当前客户空间和预览。** 预览绑定操作种类、空间、revision、设备、目标版本和备份摘要；执行重新检查人工确认、有效期和完整 scope identity。文件摘要计算结束后、真正上传 `prepare` 前再次检查作用域，避免关闭窗口或换空间后上传旧文件。导出响应返回后、调用原生保存前及回执提示前均检查作用域。文件读取期间禁止再次选文件；文件版本、空间、大小及常见带前后缀的凭据字段均校验。备份敏感字段过滤只是额外防护，正式服务仍需业务字段白名单。
4. **管理写入的未知结果保留原请求。** 本机 ledger 在 `execute` 前持久化；持久化失败不发请求。30 秒超时、网络错误或不匹配回执不会清锁；仅同 requestId、kind、spaceId 的确定回执可以结算。已发请求离页后只能结算原用户的记录，不能在新作用域显示旧成功。将该逻辑抽为 `useManagedOperation.ts` 后，以上边界保留。
5. **P12 队列不提供发送授权。** 服务缺失与成功的空队列区分；快照校验队列、总数、记录唯一性、商机/用途/版本及时间。用户、服务或队列变化时通过 `useResource` 身份门禁立即隐藏旧记录；公开样例只读。队列详情导航按 opportunityId 和用途重新读取商机，不把队列记录 ID、文字或选择动作当成客户草稿保存/发送确认。首次生成可用，失败可重试，新建议先预览，人工文字只有显式替换才改变。
6. **P13 仅以原请求的确定证据收敛发送。** 对象、账号、机会、全文版本和人工确认在发前再次核验；新请求 ID 在发送前持久保存。二次核验等待期间可能新增发送记录，因此持久化 updater 会重新读取并拒绝最新同机会/用途 PENDING、旧锁或同版本 SENT，不能仅依赖开始核验时的闭包。绑定回执逐项校验 requestId、opportunityId、channel、version；FAILED 还需 `confirmed:true` 和 `confirmedNotDelivered:true`。UNKNOWN、PENDING、404、网络错误、不匹配或缺字段继续锁定。旧接口单独返回 FAILED 不再显示确定未送达；旧 pending 没有请求编号时不得猜编号或自动解锁。查询只调用 reconcile，归档到原版本，不自动重发。
7. **最终导航缺口已闭环。** 另一审核者发现队列“查看联系准备”只更新路由而未切回草稿箱；初次修复后，本审核又指出真实异步 `hashchange` 下同商机可能保持旧用途。最终由父组件切回草稿箱，并将规范化路由用途纳入编辑器 key；本机草稿存储键仍按用户和商机保留。新增真实 `AppProvider` 回归从同商机评论人工编辑，经队列进入私信，再切回评论确认人工文字仍在，没有使用同步路由 mock 掩盖时序。最终 P18 增量仅为容器 class 与间距，未改变管理操作逻辑。

## 本次独立验证

以下均在隔离 service fixture 中运行，没有真实短信、平台登录、消息投递或客户数据恢复。各命令包含重复回归，数量不能相加作为不同测试总数。

| 执行范围（从 `desktop/` 运行 `npm test -- …`） | 实际结果 |
| --- | --- |
| `tests/boundedRequest.test.ts tests/ui/connections.test.tsx tests/ui/task-wizard.test.tsx tests/ui/login.test.tsx tests/ui/management.test.tsx tests/ui/management-scope.test.tsx` | 6 文件，54 passed |
| 登录等待修复后：`tests/ui/login.test.tsx tests/boundedRequest.test.ts` | 2 文件，14 passed |
| 首屏 session 修复及触达初审：`tests/ui/session-bootstrap.test.tsx tests/ui/outreach-queues.test.tsx tests/ui/outreach-reconciliation.test.tsx tests/ui/send-confirmation.test.tsx` | 4 文件，73 passed |
| 触达两项修复后：`tests/ui/outreach-reconciliation.test.tsx` | 1 文件，24 passed |

核验环境使用已配置的 Node 24 运行时。测试涵盖实际 Promise 挂起/迟到、fake timer 超时、真实 localStorage 持久化、原请求字段不匹配，以及不广播 storage 事件时发前仍读取最新锁。没有用按钮永远禁用代替可用分支验证。

最终导航修复的测试内容及 6 文件增量已作只读复核；另一独立审核者亦给出 PASS。整合者报告最终同树全套为 **37 文件、362 passed**，类型和差异检查通过；此数字为整合者执行结果，不冒称本审核者重跑了全套。

## 保留限制与下一门禁

- 本结论绑定上述源码候选；后续新增产品代码需再作增量复核，单独的构建和 QA 文档更新不自动改变源码候选的边界。
- 默认客户服务仍未接入手机号登录、平台采集/监控、触达队列/生成/发送/回流及管理写入适配；可选类型和测试数据只证明前端能处理这些契约。
- 服务端必须独立执行租户鉴权、确认 token 绑定、请求幂等、敏感字段白名单及渠道真实回执验证。本机 ledger 不构成多设备分布式互斥或平台投递保证。
- 本文不对本轮新 ASAR、真实原生保存窗口体验、签名/公证、Windows 构建安装或 CP-06 生产环境作通过声明；这些分别由冻结后的构建、真实客户端及目标环境证据验收。
