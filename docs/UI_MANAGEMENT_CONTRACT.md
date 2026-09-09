# P18 账号、设备与客户数据管理契约

本轮完成 P18 的前端状态和受控操作路径。生产 `YikeService.management` 尚未接入；缺少该可选服务组时使用 `unavailableManagement`，返回 `MANAGEMENT_UNAVAILABLE` / 501，不把按钮、预览或测试结果解释成设备已绑定、数据已恢复或版本已安装。隔离视觉服务只提供 TEST 状态与影响预览；执行、导出、查询回执和取消仍被拦截。

## 类型与显示状态

定义见 [domain/management.ts](../desktop/src/renderer/domain/management.ts) 和 [services/management.ts](../desktop/src/renderer/services/management.ts)。

| 对象 | 契约 |
| --- | --- |
| `AccountState` | `spaceId`、空间名称、`revision`、设备 ID/名称；授权状态 `UNKNOWN / INACTIVE / ACTIVE / EXPIRED / SUSPENDED` 及可空有效期；设备状态 `UNBOUND / BOUND / REVOKED / OFFLINE` |
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

`exportData('csv'|'backup-json')` 返回空间 ID、建议文件名和内容。客户端先核对当前空间，备份再核对其内部空间与格式，然后交给已有下载接口。

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

这些测试使用隔离服务。生产 ManagementService、真实设备绑定、真实备份恢复、更新安装/回退、后台幂等及 Windows 实机仍需独立验收；本契约不将其标记为已完成。
