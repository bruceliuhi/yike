# 05C 真实策略确认客户端 Implementation Plan

> **For agentic workers:** REQUIRED: Use `subagent-driven-development`; steps use TDD and independent spec then code/architecture/quality review. 用户授权直接main，所有Git由根代理串行执行；独立文件分工，不改Mac的pilot共享入口/113。

**Goal:** 将已交付真实策略后台接到现有Windows/Web客户端和P19，用户能核对完整快照、主动确认、撤销并按原请求恢复，不将确认当启动或原文判断。

**Architecture:** 共享严格线协议→受限IPC/真实HTTP服务→独立原请求记录及页面控制器→现有P19。保留旧taskFingerprint、启动ledger、R4搜贝和类似/覆盖草稿；新策略ID/摘要不冒充旧启动协议。

**Tech Stack:** TypeScript/Zod/React/Vitest；现有Electron固定API桥接，真实FastAPI/PostgreSQL后台。

基线`36fef5b`；继承已批准[R4交互](../../../design/v02-suite-r4/INTERACTION_CONTRACT.md)、[R3搜索确认](../../../design/v02-suite-r3/AI_SEARCH_CONDITIONS.md)及[真实策略合同](../../contracts/V02_CONFIRMED_RESEARCH_STRATEGIES.md)，接续原计划Chunk3。不是重新设计R4或缩小完整Goal。当前Mac仍负责04C/113及pilot共享入口，Win负责本片desktop文件；若远端出现重叠先整合，不覆盖。

## 已选边界

- Profile.id已经是服务端画像版本UUID。draft.id/request UUID必须真实规范小写，revision1..2147483647；不将旧`task:...`键截断或转换成新请求ID。
- 配置原值无静默截断/去重/清空，平台五枚举显式映射且保留顺序。链接按非空行读取，首尾分隔空白仅作为输入分隔去除，禁止用逗号/分号拆坏URL；若旧草稿使用其他分隔，提示用户逐行整理而不猜测。两侧输入及schedule均保留。
- research基础设置逐字段保留；provenance/coverageProvenance在当前后端不支持时明确拒绝提交并保留草稿，不降级删除。完整监控/用量护栏仍由执行能力决定，策略保存不宣布它们可用。
- 服务端SHA作为绑定完整服务端快照的opaque值保留。客户端先严格核对六字段及全部预期内容，再固定SHA；不复制Python浮点JSON哈希算法。后续confirm/revoke/查询校验原请求、策略和同一快照/SHA，执行端继续权威重算。旧UI摘要另存，用户/空间/账号或技术预算改变使本地确认失效。
- localStorage操作ledger仅opaque IDs/摘要/状态，不存配置正文、业务资料或令牌；原配置在既有可编辑草稿/页面内存，历史事实向服务端查。保存记录失败则不发送。404保留未决，不代表此前确定失败；允许用户在原配置仍能核对时显式重试同一UUID，不自动换键或重试。未知confirm不能被新prepare覆盖。
- 两个执行保护上限独立显式传入，范围records1..10000、seconds1..86400；P06/P20沿用高级设置的原字段控件显示/编辑建议值100记录、900秒，P19只读展示并返回配置页修改，遵守已有确认页约定。明确只是本次执行保护，不从搜贝/去重来源/研究分钟数推导。TaskDraft可选executionLimits保留未完成输入（有限number或null），旧草稿无值时显示明确建议值，不能静默认定已确认。修改上限增加revision、纳入新本地绑定并需prepare/确认。

## Chunk 1：共享线协议与真实传输

### 新主线兼容补充（168872a → aac3fe9）

主线已纳入a31069f日程契约：新once/monitor草稿均带`Schedule.policyVersion=1`，旧六字段日程不自动换版。05C不能删除此字段来通过旧后台，也不能永久拒绝所有新草稿。Win在自己所有的`pilot/research_strategy_contract.py`与合同专项测试增加旧六字段/带必填严格整数1的新七字段两种形状；新字段原样进入配置及摘要，旧缺字段JSON/快照/摘要保持不变，拒绝null、布尔、未知版本和其他extra。不改Mac在途store/resolver/共享入口或114 SQL，不添加可空默认值污染旧快照。客户端共享schema/mapper随后同步，真实Node/HTTP/PG测试使用实际`newTaskDraft()`映射，验证新旧回执和显式换版的冲突；完整执行门禁和`scheduleContractVersion`要求不变，这仅保存/核对配置，不声明监控或DST执行已实现。顺序为兼容反例RED→最小实现→旧合同/真实往返GREEN→独立审核后提交。

独立审核后补齐仅v1间隔窗口相同起止拒绝，旧未版本化配置不改写。Mac `f4e9b71`已共享注册策略入口；实际Node用例改用`build_app(..., research_strategies=service(env))`，不再手动追加同路径router，避免前面的默认501遮蔽。只有测试loopback监听使用既有`dev_login=True`选项。Task1/2实现与整合证据见[05C限定验收](../../qa/V02-05C_STRATEGY_CLIENT_WIN_REVIEW.md)；Task3/4继续，不将基础传输片当整卡完成。

### Task 1：严格共享DTO和草稿映射

**Files:** Create `desktop/src/shared/researchStrategies.ts`, `desktop/src/renderer/domain/researchStrategies.ts`, `desktop/tests/researchStrategies.test.ts`。

共享导出`strategyConfigurationSchema`、`prepareStrategySchema`、`confirmStrategySchema`、`revokeStrategySchema`、`strategyReceiptSchema`、`strategyViewSchema`、`strategyUuidSchema`及对应推导类型`PrepareStrategyRequest/ConfirmStrategyRequest/RevokeStrategyRequest/StrategyReceipt/StrategyView/StrategyConfiguration`。精确字段、必填nullable、UTF-8字节限额、严格整数/布尔/有限数、数组顺序与不重复遵守Python合同；普通公开URL结构、时区按本平台能力检查，后端冻结URL验证仍权威。不引入网络检查或承诺DNS安全。

domain导出`strategyPrepareRequest(draft, requestId, limits)`，limits为显式`{max_records,max_runtime_seconds}`；`parseStrategyReceipt(raw, expectedRequest, preparedReceipt?)`及`parseStrategyView(raw, preparedReceipt)`。prepare响应核对request、operation、draft/revision/profile、完整公开配置/平台/预算和snapshot内策略ID等；prepare可以重放DRAFT/CONFIRMED/REVOKED历史状态，不能当新许可。confirm响应必须同策略/快照/SHA/画像SHA并CONFIRMED；revoke响应同绑定并REVOKED。视图所有字段严格验证，历史receipt与当前view分离。安全统一错误，不回显不可信正文。这里的预期请求来自调用前内存；丢失后的恢复由Task3独立`recoverStrategyReceipt`核对原已存摘要后重建，禁止直接用回包当expected。

- [ ] 先写有效中文草稿/链接/五平台及三操作匹配测试；缺模块时明确断言失败，然后实现。反例覆盖额外权限字段/非法ID/预算/缺字段/乱序/旧revision/改快照/改SHA/未知provenance；原草稿不改变。
- [ ] 运行 `node node_modules/vitest/vitest.mjs run tests/researchStrategies.test.ts`（cwd desktop），GREEN；与Python严格配置/六字段快照实际序列化核对少量样本，真实PG回执由Task2跨语言往返验收。Task1纯回执反例可用明确夹具，不把自行拼接回执当真实服务证明。
- [ ] 独立规格和代码/架构/质量审核，根代理提交本三文件。

### Task 2：固定IPC白名单与服务适配

**Files:** Modify `desktop/src/shared/contracts.ts`, `desktop/src/main/servicePolicy.ts`, `desktop/src/renderer/services/contracts.ts`, `desktop/src/renderer/services/client.ts`；Create `desktop/src/renderer/services/researchStrategies.ts`, `desktop/tests/researchStrategyTransport.test.ts`, `desktop/tests/integration/research-strategy-live.test.ts`；append one integration case to Win-owned `tests/test_research_strategies_postgres.py`复用原48项同module夹具，避免重复创建固定数据库角色；extend `desktop/tests/servicePolicy.test.ts` / `serviceClient.test.ts` only if needed。

固定操作名`strategies.prepare/confirm/revoke/receipt/get`；三POST精确路径`/api/ui/research-strategies/{operation}`，receipt GET payload `{request_id}`、get GET `{strategy_version_id}`。调用共享schema，128KiB实际JSON字节上限，禁止caller path/method/headers/tenant/owner/token；GET ID规范验证，不允许任意URL。保留现有受信窗口/Origin/HTTPS/串行会话/限额/无重定向。

`ResearchStrategiesService`接口prepare/confirm/revoke/getReceipt/getStrategy；以注入的固定request函数实现一次调用，返回unknown供domain绑定核对。`client.ts`现有导出的`service`常量增加此独立接口，不另造客户端factory，旧TaskOperationsService语义不改。缺服务/401/409/422/501/timeout透传固定ServiceError，不返回假成功/假策略/假能力，不自动retry。

- [ ] RED固定路径和严格body、无payload查询和多余字段拒绝、一次调用及失败/超时；GREEN后在desktop执行 `node node_modules/vitest/vitest.mjs run tests/researchStrategyTransport.test.ts tests/servicePolicy.test.ts tests/serviceClient.test.ts tests/ui/client.test.ts` 及 `node node_modules/typescript/bin/tsc --noEmit`，预期全部通过/退出0。
- [ ] `tests/test_research_strategies_postgres.py::test_real_node_client_strategy_roundtrip`启动仅loopback的临时Uvicorn，使用共享build_app注入实际受限PG服务和真实会话，然后通过Node24 Vitest运行`desktop/tests/integration/research-strategy-live.test.ts`。Node使用实际renderer service→requestApi→createServiceClient/validatedOperation→fetch，不替换策略请求/响应。仅本地测试允许现有unpackaged loopback HTTP选择（不当生产HTTPS验收）；测试认证数据走环境/进程输入，错误输出不泄密。测试后关闭精确HTTP句柄。专用Node fixture缺环境明确skip，不将skip当通过。
- [ ] Windows根目录执行 `$env:YIKE_STRATEGY_NODE_BINARY='<已验证Node24绝对路径>'; & ./.runtime/research-strategy-pg.ps1 -Selection real_node_client`；脚本创建并精确清理一次性PG，预期1实际Python桥接用例passed、其Node子测试passed、脚本退出0/清理确认。其他环境可按上轮PG夹具设置专用两个DSN后运行 `python -m pytest -q tests/test_research_strategies_postgres.py -k real_node_client`。验证prepare/confirm/读取/撤销/原键不重复和logout后拒绝；只用测试身份/画像/来源，不访问外部，不只注入返回成功mock。
- [ ] 独立双阶段审核并提交；Mac共享入口仍按上轮合同串行接收，不改pilot模块。

## Chunk 2：原请求恢复与现有P19

### Task 3：确认操作状态与记录

**Files:** Create `desktop/src/renderer/domain/strategyConfirmation.ts`, `desktop/src/renderer/pages/tasks/useStrategyConfirmation.ts`, `desktop/tests/strategyConfirmation.test.ts`；Modify `desktop/src/renderer/app/operationLedger.ts`及相应专项测试。

新增专属`research-strategy-operations` scope；保留原scope/迁移格式。每draft的记录绑定user/可获得accountScope、本地配置摘要、prepare UUID、原请求摘要、策略UUID/服务端hash/画像摘要（已知后）、confirm/revoke UUID/状态。记录内不含配置原文或完整receipt，不使用本地数据代替服务端许可。

控制器先持久登记再调用；准备成功逐字段核对并显示快照，明确用户动作后才confirm。有效确认需本轮核对的current view、用户未编辑的相同本地绑定及原confirm回执；reload/切账号/编辑后不能自动恢复勾选。未决操作先getReceipt，404或超时保持待核对，同UUID重试须显式且原请求可恢复核对；新操作不能覆盖未决。成功历史回执不表示当前有效，需getStrategy。旧作用域迟到响应不得更新新用户UI，但保留原用户未决记录供后续核对。撤销后不可本地复活。

`strategyRequestDigest(request)`使用客户端严格请求的递归key排序/UTF-8/SHA256，专用于本地原请求核对，不等同服务端configuration_sha256。`recoverStrategyReceipt(raw, savedRecord)`先严格解析回执，再由其字段重建原prepare（使用原prepare UUID、draft/revision、画像、六字段配置与预算），计算请求摘要与**调用前已保存**的prepareRequestSha256比较；confirm/revoke另外重建其原操作并核对相应requestSha256、已保存策略ID/配置SHA/画像SHA。验证通过才向Task1解析器提供重建的预期请求，恢复结果默认只读历史，不恢复勾选。摘要缺失/损坏/不匹配，或原请求未能重建时保持未决/只读，不确认、不重发；不能拿服务器返回值自我验证。若当前草稿已编辑，旧回执可完成旧请求核对，但不能将旧确认挂到新草稿。404同UUID重试只有当前完整请求重算摘要仍匹配且用户明确点击时才允许。

- [ ] RED双击、未知/reload、404、保存失败、改配置/账号/预算、迟到响应、历史已撤销/非当前，原草稿丢失后正确/不匹配摘要恢复；确保没有正文入ledger或未知换键。最小实现后在desktop运行 `node node_modules/vitest/vitest.mjs run tests/strategyConfirmation.test.ts tests/ui/operation-ledger.test.tsx`，预期GREEN、旧记录不受影响。
- [ ] 独立双阶段审核，不替换旧启动ledger或引入新全局状态框架。

### Task 4：接入R4确认页和验收

**Files:** Modify `desktop/src/renderer/pages/TaskWizard.tsx`, `desktop/src/renderer/pages/tasks/TaskConfirmationSummary.tsx`, `desktop/src/renderer/domain/models.ts`, `desktop/src/renderer/app/taskDraft.ts`；Create `desktop/src/renderer/pages/tasks/StrategyExecutionLimits.tsx`, `desktop/tests/ui/strategy-confirmation.test.tsx`；update plan/taskbook/handoff/QA。

P06/P20高级设置复用字段控件编辑独立executionLimits，P19只读展示。已有P19摘要/控件/Notice中接入prepare、逐项核对、用户confirm、原请求查询及撤销，避免继续扩大TaskWizard，将状态保留在Task3控制器。须能展开全部绑定字段：生效source与非生效keywords/links（明确“保留但本次不执行”）、once时保留的schedule（明确本次不调度）、research的全部demandTypes/maxSoubei/三硬上限/停止条件/补证顺序以及技术预算；不能只展示当前原摘要中的一部分。未提供新服务的旧注入适配继续原有受控路径；真实client启用新服务时必须新策略确认，不能回退旧本地checkbox绕过。现有启动设备/连接/搜贝/旧未知请求门禁全部保留；新策略确认不表示05F签名启动、实际来源或所有研究模式已可用。新签名执行接续仍是独立下一片，不将旧taskOperations回执当新协议。

- [ ] RED→GREEN用户进入P19 prepare/预览→主动confirm、编辑失效、未知查询/撤销及缺服务不假成功、全部绑定字段可查看；desktop执行 `node node_modules/vitest/vitest.mjs run tests/ui/strategy-confirmation.test.tsx tests/ui/task-wizard.test.tsx tests/ui/task-start-contract.test.tsx tests/ui/task-recovery.test.tsx tests/ui/tasks-draft-resume.test.tsx`，并按改动选择R4用量/类似覆盖现有测试；`node node_modules/typescript/bin/tsc --noEmit` 和 `node node_modules/vite/bin/vite.js build --config vite.renderer.config.ts`均应退出0。
- [ ] 按原P19视口真实渲染检查新增摘要/状态不溢出、不丢原亮点；新增布局若超过已有设计语义则先停下确认，不替换R4图稿。
- [ ] 独立规格及代码/架构/质量审核，绑定代码与实际Node→HTTP→PG和UI证据。正常fetch/整合/push main，更新任务板为实得状态；05C整卡、真实来源/原文证据、多找类似、短句联系、Windows及完整Goal继续。
