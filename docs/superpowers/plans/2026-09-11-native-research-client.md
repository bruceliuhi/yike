# Native research client implementation plan

Use subagent-driven-development; root serial git, one whole-batch independent review, no repeated broad suites. User preauthorized technical design within V0.2. Follow the complete spec at `../specs/2026-09-11-native-research-client-design.md`.

## Global constraints

- Deliver ordinary-client confirmation→signed research START→persisted bounded advancement/status→original results/cancel/recovery as one batch. Full goal unchanged; scope explicitly fixed V2EX index, not full-web search. Missing rule/model/runtime remains unavailable, no invented pricing/deployment/sends.
- Token only invocation memory; exact nonsecret journal before POST; original UNKNOWN protected; no research fallback to ordinary execution.apply/FINISH or silent quote replacement. Authentication identity/device from main/server, never renderer claims.
- At most one fresh external effect per advance, sequential client advancement, GET is read-only; source/review effect IDs stable, no automatic retryOf. Coordinator lease/generation, current task/cancel and resource permits remain authoritative; no network transaction. Preserve post-permit final disclosure guard from bac5df1.
- Exact shared camelCase API contract in spec. Source original/analysis counts not qualified opportunities; actualSoubei:null/settlementState:PENDING. New migration137 only;136 belongs to separate SMS/trial task. No auth/session/login edits in this worktree.
- Work only /tmp/yike-v02-scope.Pwf9Fs. Agents use apply_patch, never stage/commit/push or modify other checkout. Root provides test PG port; no production DB, external model/network or new package build before final integration.

## Task 1 — Native research protocol

Owner native implementation agent. Read current executionSession/controller/journal/servicePolicy/shared desktopExecution/main.ts/preload and prior shared/researchExecution.ts. Own changes there plus renderer/services/desktopExecution.ts ONLY; root owns other renderer files. Add shared `researchRuntime.ts` strict capability/status schemas from spec and main service API routing if needed. Notify root names/interfaces before implementation.

- [x] RED exact research START journal→prepare/sign→research POST and full receipt binding, unknown/restart recovery with no token storage/no ordinary fallback; ordinary compatibility.
- [x] Extend encrypted versioned research journal safely using existing protection/owner/service boundaries; main user/device resolution, epoch guards, no automatic retry after404.
- [x] Expose RESEARCH_START/RECOVER/LIST via existing execution bridge, strict union/result and renderer service `researchContractVersion:1`; implement new read/run API transport operations `researchRuntime.capability/status/advance` with spec routes. Root uses schemas/service.
- [x] Targeted tests/tsc and report exact files/results/limitations, no commit. No UI activation by this task alone.

## Task 2 — Persisted bounded research runtime

Owner backend implementation agent. Own new pilot/research_runtime.py, relevant API module research_execution_api.py (prefer optional runtime parameter), pilot/research_orchestrator.py incremental/read-only status helpers, migration137/db registration/minimal grants and focused PG/HTTP tests. Do not edit pilot/runtime.py, web.py or ui_api.py without coordinating with root (root assembly). No auth/login changes.

- [x] RED actual confirmed research START→single fresh source advance→single model advances→persisted terminal/result status; GET performs no effect/writes; completed recovery no second effects.
- [x] Internal coordinator API `ResearchRuntimeService(orchestrator)` exposes `capability(claims)`, `status(claims,task_id)`, `advance(claims,task_id,run_id)` returning spec DTO. Current owner/session on each; active/expired lease behavior conservative; exact generation/terminal checks, no redoing UNKNOWN.
- [x] Completion only from server-derived stored source/review evidence; record terminal task/run/platform state by internal research path; cancellation and effectsPending distinguished. Usage derives exact resource event counts, no actualSoubei computation/settlement.
- [x] Add authenticated GET capability/status and POST advance to research_execution_api registration with optional runtime dependency, fixed errors/limits/HTTPS/no-store. Root injects it through web/ui/runtime.
- [x] Dedicated restricted-PG and HTTP targeted tests, current cancel/concurrent advance/session/unknown isolation cases, report actual evidence. No live models/sources or commits.

## Task 3 — Ordinary UI and runtime assembly

Owner root. Add explicit validated research runtime configuration only when actual model/rule/secret/source available; no defaults for production rates. Pass dependencies through web/ui. Reuse selected TaskWizard native flow, current quote state, task details/filtered candidate list and existing controls. Server capability gates actual source scope; quote/strategy/source changes invalidate user confirmation. Token never enters unknown-start localStorage; main journal owns research recovery. Add progress controller with serial advance/read-only recovery and no automatic unknown retry. Test the real renderer flow in proportion to changes, no visual redesign.

## Task 4 — Integrated evidence / independent review

- [x] One actual HTTP+restrictedPG+native/renderer integration with explicitly synthetic source/model boundaries; scope/unknown/cancel/results visible, no fake lead counts.
- [ ] Whole-batch nonauthor review, directed fixes/delta review, one relevant candidate build if UI/package inputs changed. Update this single evidence record/taskbook, push main and verify parity; stop owned resources.

## 实施证据

基线 `c4993b6`；设计 `872e829`，实现 `5aabae6`，审核修复 `e26d664`。完整V0.2 Goal保持进行中。本记录集中维护本批证据，下列任务文字不扩大已经实现的来源范围。

### 已接普通客户端与服务端

- TaskWizard 在原策略/估算确认页发原生 `RESEARCH_START`，非秘密原请求先加密保存，授权token仅存在调用内存；原请求重开不重发START。双journal串行读取，旧bridge不探测研究协议。
- 明确配置后组装专用research ExecutionRuntime、quote、resource、source、assessment、orchestrator与持久化runtime；普通采集capability函数身份不变。migration137及最小权限，136仍留给短信/试用任务。
- 真实任务feed新增可选 `research:true`（仅依据服务端快照）；详情不走普通本机重采/FINISH，改用研究进度、原文候选入口和原有签名取消。
- 点击“继续研究”后本页串行推进，每次最多一个新外部效果；离页/停止本页只停后续推进，不谎称撤回已发请求。查询原状态不产生新效果。完成、未知、取消与原文/分析数量分开显示，实际搜贝为待结算。
- 仅固定V2EX最新主题单源研究，非全网关键词搜索；其他平台普通采集保持原实现，研究多源规划/监控仍待接。不默认启用生产或收费规则。

### 定向验证与首次否决

- 配置/原runtime组合：26 passed。原生协议、journal、合同、controller及受影响UI：164 passed；真实TaskWizard研究启动与绑定边界增量18 passed。根进度/service/feed相关12 passed，TypeScript检查通过。
- 受限PG与HTTP后端30 passed，补持久STOPPED/有效租约和真实 `build_runtime_app` HTTP路径后28 passed；根HTTP整链加普通任务feed4 passed。来源与模型为明确合成边界，不是实际客户结果。
- 独立整批审核 `5aabae6` 为NO-GO：P1并行LIST撞真实身份锁；P2分事务完成写入可永久矛盾；P2旧generation能在接管后先发模型、后被拒绝。没有把初审测试或包当作通过。
- `e26d664` 定向关闭：真实identity/controller/session桥接测试RED→GREEN，17 passed；终态故障恢复与序列2项PG通过（7.07秒）；租约接管禁止旧模型请求和UNKNOWN2项PG通过（7.07秒）。资源许可事务同时核对owner/generation/lease与现有来源资格；完成状态与task/run/platform同事务。
- 独立审核者对 `e26d664` 做差量复核，结论DELTA GO，无重复全量测试或构包。审核原文临时档 `/tmp/yike-native-research-full-review.md`；本记录保留可持久接续的三项问题、修复与结论。
- 内置浏览器实际点击真实ResearchProgress组件，TEST合成状态从待推进到2原文/2分析、1来源请求/2模型请求，完成后禁用继续按钮、保留原状态查询。窄视口文字及按钮可见。仅界面证据，不是来源/模型/客户验收。
- Mac `package:dev` 在审核前的 `5aabae6` 成功但该候选被否决；修复后的 `e26d664` 再构建一次成功，目录 `desktop/out/意客AI-darwin-arm64/意客AI.app`。没有重复全套测试，不将旧包背书新源码；Mac构包不是Windows或生产验收。
- 最终原生socket联验：`tests/test_desktop_research_http_postgres.py` 启动真实 `build_runtime_app` 和受限PG，调用Node24的 `desktop/tests/integration/research-execution-live.test.ts`。实际serviceClient/identity/journal/session/controller完成签名START、重建恢复、两次推进及严格status/feed解析，task状态SUCCEEDED且只POST一次START；1 passed（4.80秒），无跳过，随后tsc与diff-check通过。仅登录fixture/密钥保护及来源模型为合成；不向Node子进程传DB配置。测试退出清理fixture及临时HTTP。
- `e26d664` Mac包 `Contents/Resources/app.asar` SHA-256：`d0319432c4513fe4d03897672cba9d64361173d3ba37d6f2f7420aac8ab9a8c0`。后续收尾提交仅新增该联合测试和文档，不改变此包生产代码。

### 仍待验收

没有真实生产规则或模型启用、结算/余额扣款、Windows新包、部署或跨行业客户UAT；来源数量不等于合格商机。完整多源研究规划、计费及其他V0.2目标继续推进。Git远端核对和资源停止由本次主Agent收尾执行，不以代码候选GO标记完整Goal完成。
