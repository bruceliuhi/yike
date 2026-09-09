# P14/P15 精确回复入口：独立架构复核

## 结论与绑定

**PASS：本次限定增量未发现未解决的 P0/P1/P2。** 可继续本轮前端可见验收与交付检查，不代表完整 Goal、生产回复回流或 Windows 验收完成。

- 仓库：`/Users/bruce/Developer/work/yike-ai-product-design`
- 审核候选：`53d506b7ba439facda0d7725a72f8c1c2ee945a5`
- 基线：`dd09d0fbd4e900b020e41a8486f0343ff9f33c56`
- 审核者为本次四个生产文件增量的非作者。早前本人编写的跟进 ACK / 未知操作存储逻辑不在此次独立批准范围内，沿用其已完成的非作者审核。

## 独立审核范围

审核 `Followups.tsx`、`followups/RelatedReplies.tsx`、`followups/FollowupEditor.tsx`、新增 `followups/useRelatedReplies.ts`，并对照 R3 P14/P15 图册、PAGE_STATE_MATRIX、现有 FollowupService 与路由契约。

1. 无人工登记的有效商机可经选择或深链进入回复。先使用 `service.opportunity(id)` 精确验证可访问对象，不以分页列表缺失判断无权限；拒绝不同 ID 和公开样例响应后才查询回复。
2. 明确未匹配状态与目标查询失败分开。403、404、错误或未完成授权不会转换为 `replies(undefined)`，也不会自动选择其他商机。
3. 精确目标、服务、身份及客户空间 ID/版本参与请求生命周期。目标与空间变化立即隔离旧内容；迟到授权不再派发回复查询，迟到回复不覆盖新对象。
4. 左侧人工记录筛选不会隐式切换右侧回复对象。通道读取失败与人工列表失败分别呈现；没有人工记录时不捏造登记或触达事实。
5. 由当前精确对象打开 P15，可预选列表之外但精确可访问的商机；保存前继续精确复核。已核验保存、取消、保留未保存内容及重新打开后的原目标保持路径。
6. 已读变更继续使用原回复 ID/revision、商机及画像绑定，并保留原请求保护；浏览回复本身不触发新增人工登记或外发消息。

## 独立运行证据

实际执行以下三套定向测试：

```text
tests/ui/followup-reply-entry.test.tsx
tests/ui/followup-reply-flow.test.tsx
tests/ui/followup-routing.test.tsx
```

结果：**3 files / 21 passed**。日志：`/tmp/yike-reply-architecture-53d506b.log`。

运行期间主线程正常推进了集成提交；已再次比较，以上四个生产文件及三份测试与 `53d506b` 相同。测试使用隔离 TEST 数据，不调用真实渠道。本审核未重跑全仓、PostgreSQL、生产服务、安装包或浏览器/原生可见流程，也不把主线程报告的其他测试数量相加。

## 集成兼容性追加：ffd7d80

只读核对提交 `ffd7d80ea28b54d9432cd5a4dcad72c1ddf7b05e`：

- 两个直接父提交分别为 `ff64d61c4fe6888182ec25c3a2582eb8baa364ce` 与 `eb507bfbf18c1f90b0216cd25cb8d79908c35cc0`，双方历史保留。
- 集成提交与 `ff64d61` 的整个 `desktop` Git tree 完全一致，均为 `9df06f76306399ea51f6af0f6ee37e924c556693`。
- 以双方共同基线 `27ed49949c3c8aa7baab12cdff159057b96c9890` 识别远端变更：排除两份共享文档后的 12 个远端独有文件，在集成提交中的 blob 与 `eb507bf` 完全一致，未发现覆盖。`pilot/`、`deploy/`、`tests/` 相对该远端提交无差异。
- `docs/INTEGRATION_STATUS.md` 与 `docs/V02_IMPLEMENTATION_TASKBOOK.md` 保留本地父提交全部原有行及顺序，并完整保留远端新增记录；当前两文件与 `eb507bf` 相同，无冲突标记。
- 新增普通运行装配、部署和签名字节接续记录明确区分已验证范围、后续认领与未验收能力，未将该合并写成整个 UI Goal 或真实平台闭环完成。

**限定兼容性结论：未发现集成覆盖或当前前端审核失效的证据。** 此段仅确认历史、文件字节与文档边界；不替代远端后端、容器、真实 HTTP/PG 或客户端签名的作者测试及独立验收，也不追加批准另组 TEST harness 的全部行为。

## 保留边界

真实渠道回复、发送关联来源、服务端权限与幂等仍需对应真实服务验收；图册一致性、可见交互和 Windows 实机检查需使用最终候选分别取得证据。当前报告不据条件 UI 或绿色测试宣称上述能力已上线。
