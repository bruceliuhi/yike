# 83e76be 有界接收兼容性复核

本地基线：`d5ee8c27532ff15436eaa2bcfeafca1a9e0e86a0`。
来件：`83e76be9e00a627af2286b52e0087966b812831d`。
日期：2026-09-10。只读 Git 对比和源码/QA 阅读；未合并、未改双方源码、未执行测试/PG/CUA、未重建包。

**限定结论：此精确来件未改变当前桌面生产运行入口；未发现阻止正常接收的新增 P0/P1。新增候选协议是尚未装配的独立模块，不是 P07 已完成接入。8af 实际包与当前浏览器证据继续保留原绑定。** 新模块的完整协议正确性沿其原非作者审核记录，本报告不替代底层全量重审。

## 精确变化与实际运行路径

`git diff d5ee8c2..83e76be` 共 10 文件。桌面仅新增三文件：

- `desktop/src/shared/candidateReviewApi.ts`：586 行严格请求/响应协议，唯一 import 为 `zod`。
- `desktop/tests/candidateReviewApi.test.ts`。
- `desktop/tests/fixtures/candidateReviewApi.ts`。

已通过 `git grep` 核对模块名、`parseCandidatePage`、`parseCandidateReviewResult`、两种写请求 schema：外部引用只在新增测试；没有 renderer、main、preload 或生产 service 导入。没有新增 IPC、URL 路由、运行时工厂、持钥消费或页面副作用。

`git diff --name-only --diff-filter=MDRT d5ee8c2..83e76be -- desktop` 为空。另核对 **8af8eaf..83e76be** 的 `src/renderer`、`src/main`、`src/preload`、shared/contracts、Vite/Forge 配置、package/lock，无差异。因此：

1. P04 本机稿带入/紧凑空态、P06/P09 返回参数与局部选择、P14/P15 exact detail 读取/回复选择、P11 固定证据及 P12 编辑器都没有被此次来件改写。
2. P07 当前页面和 service 仍走原路径；不会因为新增 schema 自动开始 ASSESS/核验/入库。
3. 8af 的已构建运行图没有变化，不因这三份未被入口引用的源码/测试强制重包。不能把 8af 包写成“含已接通新候选功能”，也不能把新 HEAD 的完整源码树摘要冒称与旧包输入树完全相同。
4. `tsconfig.json` 包含 `src/**/*.ts` 与 `tests/**/*.ts`，新模块虽然不运行，仍需合并后类型检查。

## 候选合同边界

新 schema 保留独立人工核验 `sourceVerificationId`、ASSESS `retryOf`、原 `requestId`/别名、候选/来源/画像/策略版本、历史与当前绑定标志。INCLUDE 新请求要求核验 ID；新请求比对不能拿缺 ID 的历史回执当本次成功。UNKNOWN/FAILED 保留其实际缺省字段，不补造版本；`sendingAuthorized` 固定 false，SEND_READY 降为待审核含义，不授权发送。严格分页和按单 ID/原请求读取未换成 raw 列表。

这些只是数据边界。固定 HTTP/IPC 传输、P07 明确判断按钮、人工源核验、持久原请求恢复与 UI 映射仍须 Win 后续 Task2–5。原 QA `docs/qa/V02-05G_CANDIDATE_CLIENT_WIN_REVIEW.md` 和任务书均如实保持 IN_PROGRESS；未用已完成的固定商机原文片代替候选接入。

## Reply payload 修正及 P14 影响

`pilot/reply_store.py:132–142` 新增单独 `sql_record`，将 `record['payload']` 经既有 `_json` 编码为字符串再传入 `%(payload)s::jsonb`。既有 `_json` 使用 UTF-8 可表达的 JSON、确定 key 顺序、紧凑分隔和 `allow_nan=False`；原 `event_record` 字典、`payload_sha256`、来源/用户/租户校验、去重/版本、返回 event 及读回校验均未改。

这是 PostgreSQL 参数编码修正，不是新增回复服务装配。当前来件 `git grep ReplyEventStore` 在 `pilot` 内只找到该类自身及导出；desktop 默认 client 仍调用原 `followups.list/add` facade，没有装配可选结构化 `FollowupService`。因此本次不改变 P14 的 matched/unmatched selector、读状态或已有人工记录行为，不能宣称真实回复已回流/已读已同步。

来件另改两份 PostgreSQL 测试夹具：补机会证据表授权，显式选择受限应用 URL，并设置非超级用户/不绕 RLS 角色。这些没有改变生产授权脚本、迁移或 P14 契约。本报告没有重做全后端安全审核。

## 最小接收验证建议

准确正常合并后运行即可，不为此次来件重跑原生 CUA 或全页面截图：

```sh
# desktop，Node 24
node node_modules/vitest/vitest.mjs run tests/candidateReviewApi.test.ts tests/ui/candidates.test.tsx tests/ui/candidate-review-operation.test.ts tests/serviceClient.test.ts --maxWorkers=4
npm run typecheck

# 仓库根；纯领域兼容性，不当 PG 验证
uv run --frozen pytest -q tests/test_reply_contract.py tests/test_reply_store.py --tb=short
```

新候选专项应核对精确分页、UNKNOWN/别名、历史核验 ID 与当前请求匹配；旧两套候选与 serviceClient 确认独立模块未改变现有页面/固定传输。当前 P04/返回/P14 生产文件无差异，没有必要仅因这片新增合同重复它们的整套或 CUA；正常 merge 后若另有冲突或源码修改再增加相应定向。

`tests/test_reply_store.py` 目前只有 `event_record`/`decode_event` 摘要与域对象测试，没有调用 `ReplyEventStore.record()` 的真实 SQL INSERT。因此这两套纯测试不能证明新 JSON 参数已被 PostgreSQL 接受。若后端责任人将此修正宣布为 PG 实写闭环，应单独保留 record→JSONB→读取→摘要一致的实际受限 PG 证据；本次按指令不跑 PG，也不把导入/RLS 的 11 项结果当回复 INSERT 证据。

## 来件证据归属

原 Win QA 记录该候选纯协议 43 项、与旧候选/客户端合跑 80 项及原非作者 PASS；这些均为对方实跑，本人没有重跑。INTEGRATION_STATUS 中的桌面 1337/26、Python 32、全量 2108/485、受限 PG 11 及 CP-06 配置预检也分别是来件责任人的记录，不能计入本报告实测。配置预检通过不等于上线、备份恢复、实际平台或客户 UAT。

未来最终 merge SHA 需要重新绑定本报告；当前结论只针对上述 d5→83e 增量，不提前审批随后远端推进。

## 最终正常合并 62e7a1c：限定 PASS

追加只读核验绑定 **`62e7a1c5e4fc76155b2208fbdcbf5961f53c1f1f`**。Git 对象双亲精确为本地 `b95d7539a9330415403e518e2e744e111880b298` 和远端 `83e76be9e00a627af2286b52e0087966b812831d`，不是强制覆盖。

已实际通过 Git blob 对比确认：

- 本地父提交原有 **342 个 desktop 文件全部原字节保留，0 项变化/缺失**；只增加上文三份候选协议/测试/夹具。
- 来件 **345 个 desktop 文件全部原字节保留，0 项变化/缺失**；`git diff 83e76be 62e7a1c -- desktop pilot tests` 为空。
- `pilot` 43 文件、`tests` 90 文件的 Git blob 树分别与来件完全相同。没有用本地旧回复存储覆盖新 payload 编码，也没有修改来件 PostgreSQL 测试夹具。
- 两份共享状态/任务书相对本地父仅追加来件段落，本地可见 QA 与认领保持；相对远端多出的本地文件均为既有 QA/文档。
- **8af8eaf..62e7a1c** 的 renderer/main/preload、既有 shared/contracts、Vite/Forge 与 package/lock 均无差异。P04 紧凑空态、P06/P09 返回和 P14/P15 可见流程仍是原生产字节；8af 包和浏览器检查保持原绑定，不宣称新候选协议已装配。

主线程在该合并候选实际执行，我仅读取日志确认其内容和归属：

| 主线程接收验证 | 实际记录 |
|---|---|
| 4 套候选/旧页面/固定客户端 | **80 passed / 2.83s**，`docs/qa/ui-visible-local-handoff/logs/incoming-83e-desktop-tests.log` |
| TypeScript | 退出 0，`docs/qa/ui-visible-local-handoff/logs/incoming-83e-typecheck.log` |
| 两套 reply 纯契约/存储领域 | **20 passed / 0.09s**，`docs/qa/ui-visible-local-handoff/logs/incoming-83e-reply-tests.log` |

以上不是本审核者重跑，也不与来件原 80/43 或历史全量相加；20 项仍不替代实际 ReplyEventStore JSONB INSERT/PG 验证。此次最终合并兼容性 **PASS，无新增已发现 P0/P1 或接收阻断**，允许继续按原边界交付资料；不扩大为全后端、实际平台、候选完整接线、原生重新构包、Windows 发行或产品上线批准。原报告中的“待合并”是此前时点，现由本节准确绑定取代。
