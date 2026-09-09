# R3 P10–P20 剩余状态审计

审计日期：2026-09-09，工作时区 Asia/Shanghai。绑定源码 **`9e27723b4513d184438da44628017c237e895fe0`**。审计时工作树干净；随后在同一源码的 `codex/r4-design` 分支仅补录本报告，未修复产品代码。

范围：按 [R3 PAGE_STATE_MATRIX](../../../design/v02-suite-r3/PAGE_STATE_MATRIX.md) 核查 P10–P20，重点为 P12 生成/人工修改/保存、P14/P15 回复与跟进失败恢复、P18 管理/备份恢复、P20 跨日和夏令时。方法为源码、现有契约和真实定向测试核查；本轮未操作浏览器、真实平台、管理后台或安装包，不是完整状态矩阵验收，也不是 R4 实现验收。

## 结论

本范围未发现新的 P0/P1。发现 **2 个 P2 代码缺陷**、**2 个既存契约/后台接入缺口**，另有一组可见验收证据待补。代码缺陷目前未修复；已有测试通过不能替代这两项新增反例的回归。

### 1. P2：P12 保存等待与迟到成功提示没有完整生命周期保护

- 位置：[Outreach.tsx](../../../desktop/src/renderer/pages/Outreach.tsx)，绑定版本第 372–385 行；[hooks.ts](../../../desktop/src/renderer/app/hooks.ts)，第 323–332 行。
- 状态路径：真实客户草稿编辑后点击“保存草稿” → `saveContact()` 长时间不返回，`useAction` 持续 busy；或者保存发出后离页/切换用户，旧请求随后成功。
- 当前代码直接等待 `saveContact(submitted)`，没有与生成、发送相同的等待上限；旧成功回调没有当前作用域检查，仍会调用全局 `notify("草稿已保存到客户空间。")`。
- `useLocalDraft` 第 273–279 行已有卸载、键和清理代次保护，本审计未发现旧草稿写入新身份。问题是保存无限等待及旧操作提示，不将其扩大为已确认的跨用户数据写入。
- 最小后续：补有界等待与身份/商机/用途生命周期检查；保留人工输入。超时应解释为保存结果待确认，不能假称确定失败或自动重发。新增挂起、离页/换身份后迟到成功、保存期间继续编辑的回归。正式草稿服务接入时同时明确保存版本与未知结果核对契约；当前生产 `saveContact` 仍返回不可用。

### 2. P2：P15 纠正记录的下次跟进日期可能向前偏移一天

- 位置：[FollowupEditor.tsx](../../../desktop/src/renderer/pages/followups/FollowupEditor.tsx)，第 73 行以 `nextFollowupAt.slice(0, 10)` 回填日期，第 126–127 行又将该日期按本机 09:00 转成 ISO 时间。
- 状态路径：在 UTC+10 等时区登记本地 9 月 15 日 09:00 的下一次计划 → 打开该记录的“纠正” → 日期框显示 9 月 14 日 → 即使只修改备注，重新保存也会把计划提前 24 小时。
- 原因：回填取的是 UTC 文本日期，保存使用的却是本机日历日期；[跟进契约](../../UI_FOLLOWUP_CONTRACT.md) 第 25 行规定当前 date 控件按本机该日 09:00 转换，两端语义不一致。
- 最小后续：回填与保存统一使用同一本机日历日期语义，避免未编辑计划时间时发生变化；补 UTC+10/UTC+12、UTC 负偏移与 DST 日期的往返回归。

本轮实际执行的最小复现（不写文件、不访问服务）：

```sh
env TZ=Australia/Sydney /Users/bruce/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node -e 'const original=new Date("2026-09-15T09:00:00").toISOString(); const correctionDate=original.slice(0,10); const resaved=new Date(correctionDate+"T09:00:00").toISOString(); console.log(JSON.stringify({original,correctionDate,resaved,shiftHours:(Date.parse(resaved)-Date.parse(original))/3600000}));'
```

实际输出：

```json
{"original":"2026-09-14T23:00:00.000Z","correctionDate":"2026-09-14","resaved":"2026-09-13T23:00:00.000Z","shiftHours":-24}
```

此输出复现的是现有转换表达式，不声称已在真实客户后台保存错误记录。

### 3. 契约未完成：P20 跨日、相同起止、DST 与离线恢复语义尚未定义

- 位置：[task.ts](../../../desktop/src/renderer/domain/task.ts)，第 130–158 行；[models.ts](../../../desktop/src/renderer/domain/models.ts)，`Schedule` 第 24–31 行；[TaskConfirmationSummary.tsx](../../../desktop/src/renderer/pages/tasks/TaskConfirmationSummary.tsx)，第 111–120 行。
- [状态矩阵](../../../design/v02-suite-r3/PAGE_STATE_MATRIX.md) 第 28、46 行要求覆盖跨日、夏令时和写入配置的离线恢复策略。现有校验覆盖有效时区、每日时刻重复、1–168 小时间隔及窗口时刻格式。
- 22:00→02:00 的次日含义、09:00→09:00 表示空窗口还是全天、DST 不存在或重复的时刻、离线错过计划后是否补跑，当前配置和确认摘要没有明确语义。现有 [页面契约](../../UI_R3_PAGE_CONTRACTS.md) 第 160 行也将实际调度留给后端契约定义验证。
- 最小后续：冻结这些有限规则，纳入配置/最终确认和边界测试，再接调度器。该项属于已批准 R3 的执行交接缺口，不是已观察到的生产错误调度；当前任务服务尚不可用，不能用配置成功替代运行验证。

### 4. 后台接入缺口：P14/P15 旧人工登记接口无法核对未知保存

- 位置：[useFollowupOperation.ts](../../../desktop/src/renderer/pages/followups/useFollowupOperation.ts)，第 61–76、101–108 行；[client.ts](../../../desktop/src/renderer/services/client.ts)，第 242–251 行。
- 状态路径：现有真实 `addFollowup` facade 发出登记 → 网络失败/超时而结果未知 → 原请求保护保留 → 离页、清草稿、重登后再核对，旧接口仍没有原 requestId 查询能力，不能继续重复保存。
- 这是已在 [跟进契约](../../UI_FOLLOWUP_CONTRACT.md) 记录的保守限制。本机不确定时保持锁是正确保护，不能以清锁、按内容相似猜成功等方式解除。
- 最小后续：后台补持久幂等、原请求查询和明确终态，接现有可选 `FollowupService`；前端按原请求恢复。真实回复回流、事件去重、已读同步、结构化成员/计划与提醒也不能因隔离测试通过而标为已接通。

### 5. 可见证据待补：P12、P14/P15、P18 的异常组合已有测试，未逐个可见走查

- 位置：[本批设计验收](design-qa.md)，第 43–52 行；[P18 管理契约](../../UI_MANAGEMENT_CONTRACT.md)，第 71–75 行。
- 已有回归覆盖 P12 生成期间人工编辑、候选预览后显式替换；P14/P15 保存失败保留输入、未匹配回复、已读关联、未知保存；P18 超时留锁、错配回执、持久存储失败、保存取消、异空间、恢复 hash 和关闭/换空间迟到保护。
- 下一步优先补这些状态的隔离 TEST 浏览器演练和原始截图/操作记录，不重写已有保护。真实 ManagementService、设备绑定、恢复、更新/回退及通道回复仍分别需要后台接入与真实环境验收。
- 本项不表示已有可见状态失败，也不把尚未逐个演练的全部异常都列为代码缺陷。

## 本轮实际测试

工作目录：`/Users/bruce/Developer/work/yike-ai-product-design/desktop`。

```sh
env PATH=/Users/bruce/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH npm exec -- vitest run tests/ui/outreach.test.tsx tests/ui/outreach-queues.test.tsx tests/ui/followup-completion.test.tsx tests/ui/followups.test.tsx tests/ui/management.test.tsx tests/ui/management-scope.test.tsx tests/ui/task-domain.test.ts
```

实际结果（2026-09-09 20:12，Asia/Shanghai，Vitest 4.1.11）：

```text
Test Files  7 passed (7)
Tests       66 passed (66)
Duration    2.51s
```

以上 66 项是上述七个现有套件的实际合并结果，不与历史全量、其他定向结果相加。本轮没有新增测试，没有运行完整前后端测试、真实调度或客户恢复操作。P12 保存挂起/迟到与 P15 日期往返这两项新发现仍待修复及新增回归。

R4 的范围确认与增量图生成独立进行，不覆盖本报告记录的 R3 剩余项，也不意味着 R4 视觉、接口或功能已经实现验收。
