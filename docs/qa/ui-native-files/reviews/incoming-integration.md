# f20b404 来件与本地 Modal 修复：限定集成复核

2026-09-10。审核集成提交 **`f20b404240bfe87733bee62ffb4b9142d18d8567`**，父提交为本地 `9b137fccfd8cb91acc7d568bf6f7d7f1d8d575dc` 与来件 `d6d9ff551b9414d14a3607ba6e91a23db7a7d847`。原包候选 `e65e3fe36692cd4b0100434b90751556e46bb0ec` 的包审核保留，不追认含本次合并。

**限定 PASS：合并保留两方产品字节；本次查验的候选原文读取、显式请求和恢复边界未发现新增 P0/P1/P2 阻断。** 这是源码集成审查，不代表候选页面已完整接线，也不代表新包或真实后端验收完成。

## 字节与集合

- `git diff e65e3fe..d6d9ff5 -- desktop` 为来件 **16 文件**；本地 `e65e3fe..9b137fc` 仅 `src/renderer/components/ui.tsx` 和 `tests/ui/modal.test.tsx`，两组无重叠。
- 实际对集成提交的全部 **354 个 tracked desktop 文件**逐项比较 Git blob：上述 16 文件与 d6d9ff5 相同，其余与本地 9b137fc 相同，**0 个不匹配**。本地活动 Modal 的无障碍隔离与打开时焦点修复没有被来件覆盖。
- `git diff --check e65e3fe..f20b404 -- desktop` 通过。四个原有 rawCandidates/rawCandidateRead untracked 草稿仍未纳入 tracked 集合，本审核未移动、清理或提交它们。

## 候选读取边界

- 新 `candidates.rawEvidence` 进入固定 IPC 操作白名单，主进程只接受严格 `candidateId`，映射 `GET /api/ui/raw-candidates/{encodeURIComponent(id)}`。浏览器 transport 使用同一 `/api/ui` 前缀与 GET，无任意地址或写方法输入。
- 服务返回必须通过 `parseRawCandidateEvidence`：绑定 candidate/revision/source/profile-version/strategy 与可选平台；保留原文、父评论和未知值，不由标题补造买方事实。历史最多 100 条，total/truncated/page_size、观察身份、版本内容一致性及发布时间/观察时间/接收时间关系均被检查。解析失败只返回固定错误，不泄露原文。
- 对已存在后端仅核了相关入口和读取实现：`candidate_api` 要求 HTTPS/有效 session，服务缺失返回 501；`get_candidate` 按 tenant+owner+candidate 查询，投影/count/有界历史共享 SQL 快照。该 GET 不触发采集、模型判断、复核或入库动作。

## 显式请求与恢复边界

- 新 `useCandidateRequests` 无挂载 effect 自动 POST 或自动重试。`submit` 先严格复制请求、计算完整指纹、可靠写入原请求 ledger，再执行显式 review/verifySource。
- `reconcile` 只 GET 原 requestId；回执需通过绑定、原始请求指纹、动作及终态校验才更新原记录。404、超时或不匹配不清保护。跨账户空间/版本或组件身份变化时不向新界面采纳迟到结果，原用户 ledger 可按合法回执结算。
- `retryAssessment` 仅 ASSESS、明确 confirmed=true、先查询原请求后对已知失败或 UNKNOWN 走显式新尝试，保留 retryOf；PROCESSING 不放行。持久写点复核候选既有记录与父子关系，旧 candidate-reviews 未决记录继续阻止新请求。没有把读取原请求当成再次发起判断。
- 只读查验新增测试源码覆盖上述存储失败、旧锁、并发、切 scope、迟到、原请求查询、显式重试和 30 秒超时；**本审核没有重新运行该套或全量后端测试，不计入主线程随后报告的执行数**。

## 不能扩大的结论

当前默认 `client` 新增 `rawCandidateEvidence` 读取方法，但没有赋值可选 `candidateReview` 写服务；全仓产品源码中 `useCandidateRequests` 目前只有定义，尚无页面调用。此次是可复用的严格读取/恢复契约与 hook，并非 P07 新审核界面或真实审核流程已经启用。原文只读 DTO 也不构成联系、发送、采集或付费授权。

原 e65 的 ASAR/ZIP 与原生文件证据继续属于旧候选。新集成包需用自己的输入清单、ASAR/ZIP 及实际原生记录核对，不能沿用旧包哈希。Mac 不等于 Windows；未做生产会话、真实模型/数据库/平台授权或 Windows 验收。

本次仅新增此报告，无产品修改、Git commit、构包或 GUI 操作。
