# 工作台待办与联系准备接入契约

2026-09-09。范围为 R3 P02/P07/P12 前端；可选组尚未接入生产服务。代码以 `desktop/src/renderer/services/workbench.ts` 为准。

## 待办读取与定位

`YikeService.workbench.queue(kind)` 接受 `review | contact | reply | followup`，返回当前认证客户空间内的完整快照 `{queue, items, total}`。每项包含 `id`、`targetId`、`title`、`detail` 和固定 `sample:false`。返回队列必须与请求一致，ID 不重复，`total === items.length`，最多 1000 项；更多记录需要先扩展明确的服务端分页契约，不能把一页记录伪装成完整快照。

工作台显示前六项，有更多项时提供“查看全部”。未完成读取或读取失败不能显示为空。读取 30 秒超时可重试；切换队列、服务或账号后旧响应不能回填。客户身份与租户范围由服务端认证推导，不信任客户端自报客户空间。

| 队列 | 目标含义 | 目标页面 |
|---|---|---|
| review | 原始候选 ID | `/candidates?candidate=ID`，按 `candidates({ids:[ID]})` 精确读取，不使用列表第一条替代 |
| contact | 客户商机 ID | `/outreach?opportunity=ID` |
| reply | 客户商机 ID | `/followups?tab=replies&opportunity=ID` |
| followup | 客户商机 ID | `/followups?tab=todo&opportunity=ID` |

不存在或无权查看的目标明确提示缺失。切换候选目标清除旧勾选及尚未发送的确认框，保留原候选的未决请求和人工草稿。跟进页选择目标商机的最新登记；无登记时不能悄悄选择别的商机。公开样例不进入客户待办；缺少 `workbench` 组时保留真实人工入口，旧兼容商机列表同样过滤样例，不能当成完整待办队列。

## 联系准备

P12 按商机真实 `updatedAt` 升/降序或标题排序，缺失日期排最后。搜索标题、需求方、平台及来源 URL，搜索/排序状态在本机会话内按账号保存。

备注单独以 `userId + opportunityId + profileVersionId` 为键保存于当前会话草稿，限制 500 个 Unicode 字符。备注不进入 `ContactDraft`、生成请求、保存消息正文或发送载荷；公开样例和未登录状态只读。它不是团队共享 CRM 备注，未接后端前不能声称已同步。

## 验收入口

`desktop/tests/ui/workbench-queue.test.tsx` 覆盖四类精确目标、完整/失败/迟到快照、样例隔离、目标切换、超时和缺失状态。`contact-preparation.test.tsx` 覆盖日期排序、搜索恢复、备注键隔离、长度及消息载荷边界。真实队列查询、权限与租户隔离仍须由后端集成验收证明。
