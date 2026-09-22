# P18 账号、设备与客户数据管理契约

P18 已有前端状态和受控操作路径；2026-09-22 第一批接入正式代码的只读账号状态与商机 CSV，仍待独立审核和真实客户验收，不代表已部署。其余管理能力继续使用 `unavailableManagement`，返回 `MANAGEMENT_UNAVAILABLE` / 501，不把按钮、预览或测试结果解释成设备已绑定、数据已恢复或版本已安装。隔离视觉服务只提供 TEST 状态与影响预览；执行、导出、查询回执和取消仍被拦截。

## 2026-09-22 只读纵切计划（V02-09F 第一批，已实现待独立审核）

- 复用当前认证、试用有效性与 PostgreSQL RLS，新增固定 `GET /api/ui/management/account` 和 `GET /api/ui/management/export?kind=csv`；不接收客户空间、用户或设备选择参数，不新增数据库权限、收费或写操作。
- 账号只读实际试用状态与到期日；没有试用记录时标记 `UNKNOWN`，不把会话有效期当许可到期。空间名称使用“当前客户空间”通用标签，不为显示名称扩大数据库读取权限。未核实商业设备绑定时 `device: null`，不能解释为 `UNBOUND` 或授权任何设备操作；已有非空设备合同继续兼容。
- 账号与导出回执必须带服务端认证所得 `userId` 与 `accountScope: {id, version}`（与会话同一版本合同），`spaceId` 必须匹配 scope。接收方用发起请求时页面持有的认证 Session 校验用户、空间及版本，不能把新 Cookie 所对应的服务端身份当成旧页面的新基线；身份缺失/不匹配时不采用账号信息、不保存 CSV。作用域包括页面 Session 的 `accountScope.id/version`，异步读取和保存回执跨身份/空间版本后丢弃，不发成功提示。
- CSV 仅导出当前认证本人可见的已纳入商机公开业务字段：商机标题、需求方、来源平台、意向状态、来源状态、来源页面、来源时间、更新时间。不读取或导出私密消息、跟进备注、联系方式/手机号字段、平台会话、凭据、签名或完整数据库行。来源页面不携带查询参数和片段，可能无法直接定位原文；导出窗口明确提示回产品内查看完整证据，不声称所有去参 URL 均可重开。表格公式字符转义；至多 1000 条，内容及 JSON 响应均限制在现有 2 MiB 保存/传输范围内，超限明确失败，不静默截断或声称完整导出；用户可到商机库筛选、勾选后使用独立的“导出所选客户商机”入口，而非给此端点传过滤参数。
- `backup-json`、绑定/解绑、恢复、更新/回退及所有管理写操作仍明确不可用；本批不构成整个 V02-09F 完成。复用既有导出保存回执及跨作用域保护。
- 测试先红后绿：认证/撤销、跨租户及同租户本人可见性、字段白名单、公式转义、超限、固定只读 IPC 路由、账号未知状态、实际保存/取消/迟到回执。使用独立临时 PostgreSQL 和受限应用角色做 HTTP 纵切，非生产数据；独立审核前不提交、构包或部署。

## 类型与显示状态

定义见 [domain/management.ts](../desktop/src/renderer/domain/management.ts) 和 [services/management.ts](../desktop/src/renderer/services/management.ts)。

| 对象 | 契约 |
| --- | --- |
| `AccountState` | 必填服务端 `userId`、`accountScope: {id, version}`、`spaceId`、空间名称、`revision`；授权状态 `UNKNOWN / INACTIVE / ACTIVE / EXPIRED / SUSPENDED` 及可空有效期；`device` 可为 `null`（尚未核实，不等于未绑定），非空时包含设备 ID/名称与 `UNBOUND / BOUND / REVOKED / OFFLINE`；空设备不能产生管理变更计划 |
| `UpdateState` | 是否有更新、目标版本、说明；下载状态 `NONE / DOWNLOADING / READY / FAILED`；可选 0–100 进度、回退版本；有更新时必须有版本 |
| `ManagementInput` | 操作类型、空间 ID、当前 revision、设备 ID、可选目标版本与备份全文 hash |
| `ManagementPlan` | 服务端计划 ID、类型、空间、revision、输入 hash、到期时间、影响摘要；至多 20 项影响明细，每项新增/更新/移除数量为非负整数 |
| `ManagementReceipt` | 原 requestId、操作类型、空间 ID，以及 `PENDING / UNKNOWN / SUCCEEDED / FAILED / CANCELLED`；可选解释文字 |

操作类型限于 `bind-device`、`unbind-device`、`restore`、`download-update`、`install-update`、`rollback`。界面读取服务端状态后显示授权、绑定、下载失败与回退入口，不从本机按钮点击推断成功。

## 影响预览与输入绑定

用户先“检查影响并预览”，再核对空间、设备、目标版本和影响范围并勾选确认。未取得有效计划、计划已过期、输入已改变或存在未决操作时，不能执行。

备份 `fileHash` 为原始文本 UTF-8 的 SHA-256。`inputHash` 为以下固定顺序数组的 JSON 文本的 UTF-8 SHA-256，输出 64 位小写十六进制：

```text
[kind, spaceId, revision, deviceId, targetVersion ?? null, fileHash ?? null]
```

`prepare(input, inputHash, backupContent?)` 返回的计划必须匹配类型、空间、revision 和输入 hash，且未到期。`execute(planId, requestId)` 前再次检查有效期与当前作用域；备份文件、目标版本、用户、空间、revision、设备或服务实例改变时，旧预览不能继续使用。

作用域检查覆盖异步 hash、预览响应、导出响应和下载回执。关闭窗口或换作用域后，旧请求不能继续上传备份、发起文件保存或在新作用域显示成功。已发起的外部操作不会因关闭窗口被假定取消。

## 服务端责任与原请求核对

服务端必须从认证身份解析空间和权限，重新核验授权、设备、revision、目标版本、备份空间与 hash；客户端传入的 ID、hash 或勾选不是授权证据。计划 ID 应绑定这些已验证事实、全文备份和影响清单，并在执行时重新检查有效性。设备解绑、安装/回退、恢复等动作须执行各自的权限、完整性和前置条件检查；安装包的来源、签名、兼容性及回退可用性不能只依赖客户端返回的版本字符串。

执行前，前端将随机 requestId 与操作类型写入用户隔离的 `management-operations` ledger，写入失败则不调用 execute。记录不包含备份全文、凭据或确认计划正文。关闭窗口、清草稿、退出与同用户重登不会删除未决记录；同用户存在未决管理操作时，新的管理执行继续受阻。

服务端必须持久化 requestId 幂等和执行回执。重复 execute 不能重复改动；`operation(requestId)` 只查询原操作。当前“取消下载”调用 `cancel(requestId)`，取消请求本身不代表取消已经完成。

| 返回情况 | 前端行为与服务端语义 |
| --- | --- |
| 匹配 requestId、类型、空间的 `SUCCEEDED` | 清原未决记录并刷新状态；只能表示实际操作已完成 |
| 匹配的 `FAILED` | 清原未决记录并显示确定失败；必须是服务端已经确定的终态，不能表示超时、查无记录或结果未知 |
| 匹配的 `CANCELLED` | 清原未决记录；服务端必须确认原动作不会继续执行，不能只表示已收到取消申请 |
| `PENDING / UNKNOWN` | 保留原请求，允许继续只读核对 |
| 超时、HTTP/网络错误、无回执、字段无效、原请求/类型/空间不匹配 | 保留原请求，禁止盲目重做 |

管理服务调用等待上限为 30 秒。等待结束不会撤销已提交动作；超时后只能按原请求核对。恢复若失败可能留下部分修改，服务端不能返回会被理解成“没有完成更改”的简单失败；须实现事务或可核验的补偿，再给出确定终态。本轮未实现这些生产后台能力。

**同用户跨空间的保守限制：**本机 ledger 目前存 `requestId → kind`，按 userId 隔离，没有保存空间副本。若同一个 userId 的所属空间改变，原空间回执将因与当前空间不匹配而继续受阻。应回到原空间核对或由后台完成原操作核验；页面不能以切空间或清草稿解除锁。正式接入若支持同用户多空间，需要服务端提供原请求的可授权空间定位契约，再扩展前端处理；不能把现有行为宣称为完整多空间操作管理。

## 导出与保存回执

`exportData('csv'|'backup-json')` 返回必填服务端用户 ID、`accountScope: {id, version}`、空间 ID、建议文件名和内容（本批只有 CSV 可用）。客户端先将账号和回执与捕获的页面 Session 比较用户、空间和版本，备份再核对其内部空间与格式，然后交给已有下载接口。不能只比较空间 ID：同一空间的两位用户仍各有私有商机。

- 桌面保存只有取得 `saved` 回执后才提示已保存；取消不提示成功，错误显示保存失败。
- 浏览器下载只返回 `initiated`，提示“下载已发起”，由用户在下载列表确认文件；不能据此宣称落盘完成。
- 文件名与格式只按导出契约传递，前端不指定任意文件路径。大小、格式和文件名校验由下载层及桌面保存层再次执行。

这里的保存回执证明文件保存路径的结果，不证明备份的业务完整性、服务端恢复成功或客户数据已经经过真实验收。

## 备份格式与敏感字段防御

恢复只接受 `.yike-backup.json`，最大 **2 MiB（2,097,152 字节）**。同时检查文件大小和原始文本 UTF-8 字节数；拒绝 NUL、无效 JSON、未知产品/版本、异空间备份。根对象固定为 `product: "yike-ai"`、`schemaVersion: 1`、空间 ID、创建时间及 data；data 只允许 `profiles / tasks / opportunities / followups` 四组数组。

嵌套字段扫描深度不超过 20，拒绝原型相关字段，并在去除下划线、短横线、空白后，按不区分大小写匹配 password、passwd、cookie、token、authorization、secret、apikey、databaseurl、session、credential、privatekey 等字段。文件读取中禁用再次选择，作用域或读取代次改变后不应用旧文件。

这属于额外防御，**不是业务字段白名单或凭据不存在的证明**。四组数组中的业务对象当前仍由通用键值结构承载；服务端必须以明确的可导出/可恢复业务字段白名单构造和验证数据，逐项校验类型、关系、归属、版本及完整性，并拒绝凭据和部署配置。不能让数据库连接、管理员口令、Cookie、平台会话或授权材料进入客户备份，也不能将客户 JSON 当作整库或服务端运行环境的恢复包。

## 验证范围

定向测试为 [management.test.tsx](../desktop/tests/ui/management.test.tsx) 和 [management-scope.test.tsx](../desktop/tests/ui/management-scope.test.tsx)。包含影响确认、原请求错误/终态、持久记录写入失败、保存取消与回执、异空间备份、文件 hash、更新失败/回退状态、敏感字段，以及空间/revision 变化和关闭窗口期间的异步边界。

2026-09-22 新增 [test_management_read_postgres.py](../tests/test_management_read_postgres.py)：一次性本地 PostgreSQL、真实 RLS/受限应用角色与 HTTP 路由，覆盖账号未知状态/真实试用到期日、认证撤销、作用域注入、同租户他人原始商机不可见、跨租户 RLS、CSV 白名单与公式处理、CSV/JSON 字节及行数边界；仅合成业务数据，不是客户或平台证据。前端新增 [management-read.test.ts](../desktop/tests/ui/management-read.test.ts) 覆盖生产适配器、固定 GET IPC、无权限扩张、响应校验与明确超限错误，现有界面测试补充空设备下导出与禁止设备变更预览。

独立审核指出同租户 Cookie 身份切换不能仅用 `spaceId` 防串用后，补充 [management-identity.test.tsx](../desktop/tests/ui/management-identity.test.tsx)：页面仍持有 A 身份而 Cookie 已是 B 时不采用账号/不保存 CSV；包含生产浏览器适配器、身份缺失/错误、scope ID/版本变化、迟到保存回执无成功提示。新增 8 项先失败再修复通过；修复后 9 项受限 PG 测试与 59 项桌面定向测试通过，统一类型检查通过，独立差量复审 GO。审查者另独立复跑 9 项身份回归（与新任务向导47项合计56项），不与作者59项重复相加。

真实设备绑定、真实备份恢复、更新安装/回退、后台幂等及 Windows 实机仍需独立验收；本契约不将其标记为已完成。正式代码接线与本地受限角色测试也不证明已部署或真实客户导出验收。
