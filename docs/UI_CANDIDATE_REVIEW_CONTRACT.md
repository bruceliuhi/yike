# P07 复核未知结果恢复契约

## 2026-09-10 新真实接口接线补充

以下原2026-09-09章节保留旧R3账本含义，不适用于新ASSESS/人工来源核验。当前实际客户端已接候选和原始证据读取；新写入仍待现有P07显式按钮/确认面板接线，不能以基础hook完成称用户已可复核。

新版使用独立`candidate-request-operations` scope，外层按userId隔离，键`[accountScopeId|null,scopeVersion|null,candidateId,requestId]`；值仅包含版本、动作、候选/来源/画像绑定、原请求摘要、assessmentId、核验ID与retryOf的省略/null/有值标记、invocationId及状态。不保存原文、人工说明或回执正文，不改写旧账本或旧hash；旧候选待确认记录仍阻止新写。

四类操作均先可靠落盘再POST；存储失败、账号/空间/目标改变或hash期间同候选记录变化时不提交。所有恢复仅GET原requestId；404、401、普通失败/错回执和超时均保留。仅用户明确要求重新分析，并新鲜GET确认FAILED/UNKNOWN后，才创建新requestId，retryOf指原实际invocation；PROCESSING、已存在重试子请求不再次POST。缓存别名中的requestId仍是本机原请求，invocationRequestId不是可替代它的回执匹配键。

原始证据严格核对来源版本与候选revision，评论者正文、原帖标题、父评论及发布/观察/接收时间各自保留。OPEN只是人工声明已打开，不代表平台真实性、可发送或发过消息。实际服务/PG及Windows界面接收仍按[05G验收记录](qa/V02-05G_CANDIDATE_CLIENT_WIN_REVIEW.md)分别验证。

## 旧R3记录（保留适用版本）

日期：2026-09-09。范围仅为前端原请求保留与核对；默认 `candidates` / `reviewCandidate` 仍为明确不可用，本文没有创建新后端接口或宣称真实入库已接通。

## 请求与持久保护

人工确认的 INCLUDE / EXCLUDE 在网络派发前计算确认快照 SHA-256，再将记录写入用户隔离的 `candidate-reviews` 操作 ledger。键为 JSON 数组 `[candidateId, action, requestId, reviewHash]`，值为 `PENDING`；不存原文摘录、人工证据、账号凭据或令牌。摘要按固定次序包含候选版本、来源版本、画像 ID 与版本、判断 ID、五项人工证据及排除原因。写入失败、已有同候选未核对请求、摘要期间离页或身份/目标范围改变，都不会派发请求。

该记录独立于普通会话草稿，清除草稿和退出不删除；再次登录同一身份时恢复，其他身份不可见。网络超时、一般4xx/5xx、格式不符或回执不匹配均保留原请求。只有服务契约明确的 `REVIEW_REJECTED` 4xx（不含408）表示事务未执行，或 `CAPABILITY_UNAVAILABLE` 501，才可作为派发拒绝解除本次记录；后端必须保证这些错误不发生在事务可能已提交之后。重新提交仍需用户重新确认。

客户端不提供“忽略未知结果”“清除保护并重试”入口。ledger 不是跨设备服务端锁；真正的租户授权、幂等、来源/画像版本和事务检查继续由服务端负责。

## 只读核对

保留现有可选查询合同：`service.candidates({ids:[candidateId], reviewRequestId:originalRequestId, page:1, pageSize:1})`。该查询不得创建或重试复核。离页/重启后即使列表只返回普通待复核候选、不含 lastReview，前端仍依据本机原请求阻止再次派发；原候选离开当前筛选结果时另有“核对原复核结果”入口。

查询必须返回唯一、同 ID、非样例的候选及 `lastReview`。任何终态都需同 requestId、同 INCLUDE/EXCLUDE、完整原始 `review`，且其摘要与持久记录一致：

- 成功仍按既有 `completedCandidateReview` 验证存储后的候选状态、商机 ID、人工复核人/时间及结果，再解除原记录。
- `FAILED` 只有原确认摘要完全匹配、候选仍为 PENDING_REVIEW 才解除；随后保留数据供用户重新确认。只返回 FAILED 字样或不同确认版本不能解除。
- PROCESSING、UNKNOWN、空结果、404、无权限、候选缺失或回执不匹配均保持未决。一般 HTTP 错误不证明入库未发生。

判断建议 ASSESS 不执行入库，不使用该决策 ledger。旧版/服务端提供的未决回执若带完整原确认快照，可使用它只读核对；没有原快照时不把当前编辑内容补成原确认，提示服务端核对。前端无法重建历史版本从未保存且服务端也未返回的请求；此限制不影响新版本发前持久记录。

## 验收边界

隔离测试覆盖真实挂起超时、离页与清草稿后原请求恢复、候选不在列表时的核对入口、身份隔离、同摘要失败与失配失败、普通4xx不解锁、发前存储失败/损坏、摘要期间离页及并发出现旧锁、五项证据和版本摘要变更、重复点击与批量遇未知即停。没有使用真实客户数据、发送外部消息或执行生产入库。实际候选复核服务、跨设备幂等及 PostgreSQL 原子写入仍须独立验收。
