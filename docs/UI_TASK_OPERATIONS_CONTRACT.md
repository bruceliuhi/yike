# 任务启动、原请求核对与任务操作契约

适用本轮 P05/P08/P09/P19 前端。这里定义可选执行服务的接入约束；不表示采集、监控或调度后端已接通。生产客户端目前没有 `taskOperations` 实现，任务列表仍依赖既有 `YikeService.tasks()`。不存在任意 URL、管理员凭据或平台外发入口。

## 模块和接入点

- `domain/taskOperations.ts`：启动/操作绑定、运行结果校验、SHA-256 和固定状态转换。
- `services/taskOperations.ts`：`YikeService.taskOperations?: TaskOperationsService` 的五个固定方法。
- `pages/tasks/PendingTaskStarts.tsx`：确认页和任务列表里的原启动请求核对。
- `pages/tasks/useTaskActions.tsx`：暂停、恢复、重试、取消的预检、确认、持久记录和核对。
- `pages/tasks/TaskEvents.tsx`、`TaskPagination.tsx`、`listState.ts`：仅按实际返回列表和事件筛选分页。
- `app/operationLedger.ts`：按登录用户隔离的本机请求记录。清空草稿和退出登录不删除未核对记录。

`TaskOperationsService` 方法：

| 方法 | 输入 | 输出 |
| --- | --- | --- |
| `start(draft, binding)` | 用户逐项确认的完整 TaskDraft 和 TaskStartBinding | TaskStartReceipt |
| `reconcileStart(original)` | 原 TaskStartLookup；严禁另造 requestId | 同一原请求的 TaskStartReceipt |
| `task(id)` | 当前任务 ID | 最新 TaskRun，用于操作前比对 |
| `action(binding)` | TaskActionBinding，固定 pause/resume/retry/cancel | TaskActionReceipt |
| `reconcileAction(original)` | 同一原 TaskActionBinding | 同一原操作 TaskActionReceipt |

缺少服务、请求挂起、网络失败、回执不完整、绑定不匹配或不确定状态均不会提示成功。所有执行/核对等待上限为 30 秒；超时只结束本轮界面等待，不声称撤销服务端执行。查询失败继续保留原记录。页面或身份变化后，旧结果不更新新页面；可信终态可清理原用户原请求记录。

## 启动绑定与恢复

TaskStartBinding = `{requestId,draftId,revision,configurationHash,mode}`：

- `requestId` 固定 `task:${draftId}:${revision}`，revision 为正安全整数。
- `configurationHash` 是 `SHA-256(UTF-8(taskFingerprint(draft)))` 的小写十六进制。序列化算法以 `domain/task.ts` 的 `taskFingerprint` 为单一来源；服务端须按相同字段顺序和规范复算，校验后固化完整输入快照，不能只回显客户端 hash。
- 本机 `unknown-task-starts` 以 draftId 为键，值是 `[requestId,revision,configurationHash,mode]` 的 JSON 字符串；不保存账号令牌、任务正文或采集内容。
- 持久记录写入成功后才能调用 start；已有该 draftId 未决记录时禁止新启动，即使修改搜索词或换 revision 也不绕过。
- ACCEPTED 必须带全量原绑定和有效 TaskRun；本次直接返回还须与确认的名称、模式、平台和画像版本一致。恢复时以服务端保存的不可变原 hash 为配置证据，不拿当前被编辑过的草稿冒充原始配置。
- REJECTED 仅在全量绑定一致且 `confirmedNotStarted:true` 时可清理记录；下一次尝试创建新 revision，仍须重新人工确认。PENDING/UNKNOWN 保留记录。
- 旧版 `task:draftId:revision` 字符串原样保留，可按原 requestId 查询。因为旧锁缺原配置摘要，本轮不会自动接受其终态或解锁；需要服务端独立原记录核验/迁移能力，不能从当前草稿推断原 hash。
- 没有新 adapter 时，兼容既有 `startTask` 契约及既有明确未执行错误；默认实现仍为 unavailable。旧路径若返回不确定结果，同样留下新格式记录，等待以后接入原请求查询。

## 暂停/恢复/重试/取消

TaskActionBinding = `{requestId,taskId,action,expectedHash}`。expectedHash 是 `taskActionFingerprint(run)` 的 SHA-256：任务 ID、模式、原状态、updatedAt（没有则 null）、画像 ID/版本和平台集合。服务端负责原子状态比较和幂等，不把前端检查当事务保证。

执行顺序：用户打开确认 → 读取最新 task → 比较当前画面、确认快照及服务端返回指纹 → 生成 requestId → 持久记录 → 调用 action。预检期间离开页面、身份变化、状态变化或存储失败均不执行。提交后的未知结果不另造 requestId 重试，只提供“核对原操作”。

`task-operations` 键是 `[taskId,action,expectedHash,requestId]` 的 JSON，值仅 PENDING。每次写入再次读取最新持久记录，发现同任务任一未决操作则阻止提交。ACCEPTED/请求已接收不等于操作完成；APPLIED 必须绑定原四项且返回匹配 taskId 的实际结果：暂停 PAUSED、恢复/重试 PENDING/RUNNING/RETRYING、取消 CANCELED。过渡状态或无确认失败继续保留记录。REJECTED 只有 `confirmedNotApplied:true` 才可释放，界面不提示完成。

服务端必须按当前会话确认租户/用户拥有任务，并把 `(tenant,user,requestId)` 的结果和状态转换原子记录。恢复/重试同时重新校验平台会话、能力、设备和调度。requestId 重复必须返回原结果，不执行第二次。本机 localStorage 不是多设备/多窗口分布式互斥锁，也不能阻止人为删除存储；跨端幂等由服务端负责。

## 列表、详情与真实状态

任务列表对 `tasks()` 返回的完整授权快照做状态、名称、平台与最近更新日期筛选；本机草稿以 savedAt，运行任务以 updatedAt。缺少日期的记录不混入指定日期范围。日期范围包含起止两天，按当前客户端本地时区解释；不推导没有返回的下一次运行时间。分页仅计当前已返回/本机可见记录，默认 10、可选 20/50。未来服务端改分页必须另加总数/游标契约，不能在截断数组上显示全局总数。

执行记录用同样的本地分页与真实 occurredAt/平台筛选。缺字段显示待获取或 `—`；未返回平台阶段、统计或事件时不构造状态、零值或样例记录。未决启动草稿禁止删除且标记“启动结果待确认”。

## 验证和未完成项

隔离测试覆盖确定成功、确定未执行、未知/超时/错误绑定、原请求重开核对、身份/路由/卸载迟到保护、并发本机记录、存储失败不派发、禁用按钮、任务和记录筛选分页、缺失时间以及新旧锁校验。测试 fixture 不接真实平台、不启动实际采集、不进行外部消息发送。

定向命令（desktop 目录、Node 24）：

```sh
npx vitest run tests/taskOperations.test.ts tests/ui/task-recovery.test.tsx tests/ui/task-actions.test.tsx tests/ui/tasks.test.tsx tests/ui/task-wizard.test.tsx tests/ui/task-start-contract.test.tsx
npm run typecheck
```

真实执行服务、平台账号权限与风控、跨端事务/幂等、旧锁原始配置迁移、Windows 实机安装运行仍需各自证据。此契约不代表这些条件已经验收。

## P05 会话模板与 P08 草稿展开

P05“保存的模板”与任务列表独立。只从本机草稿命名保存条件，使用 `useLocalDraft` 的会话存储及用户、可信客户空间 ID/版本隔离，文案明确“本机会话模板 · 未同步”。退出登录或清除本机草稿时一起清除；存储受限时沿用当前会话内存回退，不承诺磁盘持久备份。删除模板不删除任何任务或原请求记录。模板数最多50个，名称必填且最多60字。

模板条件采用明确字段白名单，不保存任务ID、revision、savedAt、执行状态、统计或未知请求。每次从模板新建使用全新任务ID、revision=1、savedAt=null，保留人工条件/排除词/平台/画像版本/账号选择/日程，随后仍走正常编辑、连接核验和最终人工确认，不直接调用执行服务。

`research` 的可复用白名单为 `version / demandTypes / maxSoubei / limits / stopAtAnyLimit / evidenceOrder`：保留人工需求类型、搜贝上限、来源/分钟/模型调用上限及固定停止和补证规则；`executionLimits` 保留 `max_records / max_runtime_seconds`。不将人工设置重置为默认值。尚未填完但符合本机草稿 schema 的有限数字、空需求选择或 null 上限允许保存；这不等于有效执行配置，估算与启动仍须通过严格校验。停止条件必须保持 `stopAtAnyLimit=true`，NaN、非法枚举等损坏配置不静默丢弃。

保存模板与从模板新建两处均执行字段过滤；不继承 quote、授权令牌、执行/研究 requestId，或 `research.provenance / coverageProvenance` 中绑定原建议、来源、运行和预算版本的快照。原报价不构成新任务授权，新草稿须按当前画像、账号、空间及完整配置重新估算和确认，沿用[搜贝契约](UI_RESEARCH_USAGE_CONTRACT.md)。缺少新增字段的旧模板仍可载入；既有入口对缺失 research 初始化默认配置，不从旧模板猜测已经丢失的人工上限。

模板另带来源草稿ID链；`TaskDraft.templateSourceDraftIds?` 保留派生关系，最多50个去重非空ID。保存模板时追加当前源草稿ID；从模板新建和再次另存时继续保留祖先。保存、使用前重新读取已有启动 ledger，任一来源未决或存储无法可靠检查则阻止。创建草稿之后祖先才变为未决时，最终启动页仍检查所有祖先，且派发前在 ledger updater 内再次核验；原祖先查询使用独立面板，不把祖先成功误当本派生任务已创建。链条达到上限不再另存；本机制不代替服务端跨设备幂等或防止人为修改本机存储。

P08 本机监控草稿“查看配置/收起配置”只读展示当前保存条件、五平台、画像版本、日程和时区。未运行的草稿不展示虚构上次/下次执行或新增量。前往确认启动恢复当前任务草稿并打开既有P19；未知本任务或祖先请求仍可查看配置，但不能启动。

追加定向测试：`tests/ui/task-templates.test.tsx`（模板命名/新ID和字段剥离/祖先链/命名后并发未决/读取失败/身份和清空隔离/只读监控配置）、`tests/ui/task-template-research.test.tsx`（人工研究与执行上限往返、两处过滤原授权与溯源、未完成合法输入、损坏配置拒绝、旧模板兼容及真实 P05 操作），以及 task-wizard 的祖先锁初始与预检后晚到回归。
