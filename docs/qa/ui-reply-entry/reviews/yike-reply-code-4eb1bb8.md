# P14/P15 回复入口独立代码审核

日期：2026-09-10。最终绑定提交：`4eb1bb88b97d5f1d9ff3db569d80f9d9e79855b4`。

结论：**限定本轮 P14/P15 产品增量 PASS；当前审核范围未发现剩余 P0/P1/P2。** 已核对最终提交与本次通过测试的产品及 UI 测试工作树一致。本结论不代替真实回复服务、视觉或 Windows 验收。

## 审核范围与作者边界

非作者读取并复核根代理实现的四个产品文件：`desktop/src/renderer/pages/Followups.tsx`、`pages/followups/RelatedReplies.tsx`、`FollowupEditor.tsx`、`useRelatedReplies.ts`；独立读取和执行根代理的 `tests/ui/followup-reply-flow.test.tsx` 六项真实 AppProvider/hash 路由测试。

本人未修改上述产品源码。本人编写 `followup-reply-entry.test.tsx`，并适配四个旧测试文件的精确商机 mock、弹窗内选项查询和预检 mock：`followup-completion.test.tsx`、`followup-scope.test.tsx`、`followup-routing.test.tsx`、`followups.test.tsx`。这些测试的作者身份明确；本报告的独立批准对象是他人编写的产品实现，不将自己的测试修改称为非作者审核。四个未提交 raw candidate 草稿不在范围内，未改动、未纳入。

## 已核对的状态边界

- 匹配回复入口不再依赖人工跟进行。先以当前服务和会话精确读取 `service.opportunity(id)`，检查返回 ID 和非样例身份，才请求 `followup.replies(id)`；不因商机未出现在列表中而拒绝已授权详情，也不在目标失败后回落到未匹配回复。
- 目标、用户、客户空间及空间版本变化使旧读取失效；晚到授权不能启动新回复查询，晚到回复不能覆盖新目标。列表仅用于选择候选，不批量逐个查询全部商机。
- 回复读取、商机读取、人工历史错误各自保留，不把失败当成空记录；查看匹配回复或标为已读不创建人工事实。添加跟进保留精确目标与当前标签，关闭后可恢复草稿。
- 标已读、撤销和 P15 保存使用精确商机预检；版本和样例限制继续存在。切换目标后旧预检不派发 mutation；已派发操作的晚到结果保留原持久请求，不因卸载右栏而解锁或显示新目标成功。
- 人工表格筛选与回复目标分离。异步初始列表不能覆盖后来选择的日期、标签或回复目标，也不能通过旧深链强制聚焦而绕过用户过滤。

## 独立反例、修复与验证

初始 `27ed49949c3c8aa7baab12cdff159057b96c9890` 的独立回复入口回归为 **12 failed / 1 passed**：没有人工行时仅请求 `replies(undefined)`，未查询精确商机；原始日志 `/tmp/yike-followup-reply-entry-red-27ed499.log` 保留。

复核 `53d506b7ba439facda0d7725a72f8c1c2ee945a5` 时发现窄 P2：`Followups.tsx` 原 151–152 行在人工列表异步完成后清除 owner/date。反例让匹配回复先显示、人工列表挂起，用户选定 `2026-09-01` 后列表返回，日期被清空。有效 RED 为 **1 failed / 16 passed**，日志 `/tmp/yike-reply-final-review-date-red-53d506b.log`。更早一次补测的两条空锁断言误用 undefined 而接口返回 null，已修正测试；不把它们计为产品缺陷。

根代理将过滤重置移到路由 intent 同步处理，并在本地标签／筛选／选行／回复选择发生后标记 intent 已处理。本人未改产品。强化回归用非空 `[manual]` 列表验证日期过滤及强制聚焦，再补选择 B 后晚到 A 行不能重新选中的反例；均已通过。

- 最终独立执行新旧 **7 个文件、75 passed**：`/tmp/yike-reply-final-review-green.log`。
- 最终类型检查退出码 0：`/tmp/yike-reply-final-review-typecheck.log`；`git diff --check` 通过。
- 根代理六项路由流程曾独立单跑 **6 passed**：`/tmp/yike-reply-flow-independent-53d506b.log`；与最终 75 项重叠，不累加。

## 准入限制

上述服务均为隔离测试注入，未调用客户平台或发送外部消息。本报告不宣称 optional `FollowupService` 的真实回复回流已接通，不批准平台写入、实际客户数据、视觉一致性、Mac 安装包或 Windows 原生验收；最终构包与可见验收须使用主线程另行绑定的证据。模板 `dd09d0f` 的独立复核见 `/tmp/yike-template-research-review-dd09d0f.md`，不与本片结果混算。
