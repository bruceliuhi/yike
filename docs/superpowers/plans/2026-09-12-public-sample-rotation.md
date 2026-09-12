# 公开来源抽样轮换 Implementation Plan

> 使用 subagent-driven-development / TDD；后端Agent与root客户端分文件工作，用户要求整批一次独立审核，不重复全量/构包。完整V0.2不缩为公开抽样功能。

**Goal:** 正式监控链根据已入库批次固定抽样轮数，在原预算内读到当前公开列表后部并重复复查作者回复。

**Architecture:** 复用monitor occurrences、candidate batches和不可变CLAIM操作回执；无迁移/新上传协议/进度endpoint。只读capability opt-in使旧客户端/旧服务保持原行为。

**Tech Stack:** Python/Pydantic/PostgreSQL/FastAPI；Electron既有固定私有IPC、TypeScript/Zod/Vitest。

## Global Constraints

- 基线 `c8c272a6f7257a2ab184f36811ceba050f81b614`，既有独占worktree `/tmp/yike-v02-scope.Pwf9Fs`，分支 `codex/public-sample-rotation`。不部署/构包/模型或平台实网/外发。设计见同日 `specs/2026-09-12-public-sample-rotation-design.md`。
- `ExecutionOperation.public_sampling_version` 可选且只允许精确整数1（拒bool/null/其他值），只用于CLAIM；缺省model_dump/TS parse不得添null/undefined字段。旧请求签名字节、回执、租约和代次语义不变。
- 仅显式CLAIM回执增加 `public_sampling:{schema_version:"public-sampling-round-v1",plan_id:<canonical UUID>,source_id:<既有PublicSourceId>,round:<int 0..2147483647>}`。普通/原生/无monitor归属/错误capability拒绝opt-in，无flag旧请求不扩字段；RENEW不带新字段，CLAIM重放返回原round。
- 在当前CLAIM事务derive同tenant/owner/plan/profile/strategy/PUBLIC_WEB匿名来源的 `COUNT(DISTINCT b.platform_run_id)`，JOIN `pilot_monitor_occurrences` 的task_id/run_id及既有真实表，排除当前platform_run。source来自当前不可变configuration.publicSource。计数含空batch/已入库但FINISH未完成/后来取消，不能计未上传运行、记录数或重复请求，也不按plan revision/device清零。
- 候选COMMIT就是读取进度；candidate ingestion及FINISH代码不新增写入、不变形。未知上传/完成只走原恢复路径，不能新增盲目重试；限流/预算/凭据/租约/原文隔离不放宽。
- 能力协商仅 `GET /execution-support?sampling_version=1` 返回可选 `public_sampling:"committed-round-v1"`，且须已有public_monitor=True；无query精确旧形状。带sampling_version时拒重复/其他query/非1。旧handler忽略query返回legacy，新客户端无capability时仍旧行为，不重试未知执行。
- 固定源index 0..100项；project预算b=min(3,maxRecords)，其他maxRecords。有round且b<length时：b>=2选择0及其余环形窗口 `(round*(b-1))%(length-1)`；b=1偶数最新/奇数轮换其余；否则旧slice。选择后再过滤，不补满；原1MiB/20秒/60秒冷却/项目最多4次请求不增。每次选中的匹配作者项目仍读回复，不能永久跳过旧ID。
- 本批是当前index抽样轮换，不是native分页游标、全网穷举或index外旧帖跟踪；这些仍保留完整Goal。合成测试不计实际商机。

### Task 1: 服务端固定抽样轮数（backend Agent）

**Files:** 修改 `pilot/execution_contract.py`、`pilot/execution_runtime.py`、`pilot/execution_api.py`；可新增单一 `pilot/public_sampling_progress.py` 容纳SQL读取。新增 `tests/test_public_sampling_progress.py`，仅必要既有 execution/support 测试。不要改desktop/docs/迁移/candidate ingestion/monitor runtime；不commit/push。

**Interfaces:** ExecutionOperation加可选CLAIM整数 `public_sampling_version=1`，serializer缺省pop；`_mutate`CLAIM已完成原授权/锁校验后计算round，合并到返回dict，随后原apply负责持久回执。support handler在调用原foreground_collection_support返回后仅根据精确query和public_monitor值增加capability，不改原support函数调用签名。SQL helper由runtime传cursor/tenant/claims.user_id/task/platform，不让客户端传plan等。

- [x] TDD先写合同RED：缺省旧dict不变；只CLAIM接受1；null/True/2/RENEW/START拒绝；旧support无新字段、新query受认证并按public_monitor返回capability。
- [x] 实现合同/SQL/CLAIM合并。核心计数等价：
  ```sql
  SELECT count(DISTINCT b.platform_run_id)
  FROM pilot_candidate_batches b
  JOIN pilot_monitor_occurrences o ON o.tenant_id=b.tenant_id AND o.owner_user_id=b.owner_user_id
    AND o.task_id=b.task_id AND o.run_id=b.run_id
  WHERE b.tenant_id=%s AND b.owner_user_id=%s AND o.plan_id=%s
    AND b.profile_version_id=%s AND b.strategy_version_id=%s AND b.platform='PUBLIC_WEB'
    AND b.execution_context->>'access_mode'='PUBLIC_ANONYMOUS' AND b.platform_run_id<>%s
  ```
  当前occurrence/plan/profile/strategy/源须实际关联，不能仅相信输入字段；当前非monitor/错误platform/capability不应返回进度。
- [x] 用既有自有PG容器 `yike-research-resources-task1-pg` 新建本批隔离DB；真实受限角色、签名START/CLAIM/upload，跨轮0→1→2（含空batch），CLAIM重放不重算，同run重放不双计、未FINISH但已上传计入、未上传/其他owner/plan不计；保留旧CLI/API签名用例通过。运行 `uv run --frozen --extra dev pytest -q tests/test_public_sampling_progress.py` 及实际受影响原测试，不重跑全仓。
- [x] 保存一次受认证HTTP的新CLAIM response及对应请求为脱敏合成JSON（无token/key/签名/凭据），供root正式TS parser读取；报告含RED/GREEN、命令、文件、DB名及未验项。停止修改等待root合并，不自行停他人容器。

### Task 2: 正式客户端协商、轮换与验证（root）

**Files:** `desktop/src/shared/executionOperation.ts`、`executionReceipt.ts`、`desktop/src/main/executionServicePolicy.ts`、`foregroundCollectionController.ts`、`collectionWorker.ts`、`publicCommunityDriver.ts`；新 `desktop/tests/publicSampleRotation.test.ts`，必要已有controller/worker/receipt测试。

**Interfaces:** 私有 `execution.support` 可选 `{samplingVersion:1}` 映射固定query；只在公开monitor启动时读取，并严格解析support的可选public_sampling字段。`launchSequence`→`worker.run`加main-only `allowPublicSampling?:true`；只有anonymous PUBLIC_WEB+monitor才允许。CLAIM operation条件加入flag；`parseExecutionReceipt`核对flag与public_sampling有无一致、只能CLAIM；driver仅使用原CLAIM lease中的固定progress，source_id必须等于冻结configuration.publicSource。

- [x] 写RED：无flag旧序列化/回执原样；CLAIM新flag/进度可读、错版本/来源/operation拒绝；固定私有route query；新controller询问capability并传worker，旧capability不发flag，native/once不改变。
- [x] 实现根端合同及正式controller→worker→driver路径，无只用于测试的绕行。抽样核心：
  ```ts
  if (budget >= items.length || progress === undefined) return items.slice(0,budget);
  if (budget === 1) return [items[round%2===0?0:1+Math.floor(round/2)%(items.length-1)]];
  return [items[0],...Array.from({length:budget-1},(_,i)=>items[1+(round*(budget-1)+i)%(items.length-1)])];
  ```
  原source/author字段和预算验证保持；已选内容query不匹配不继续加读，空结果正常上传。
- [x] 源响应合成但driver真实函数三轮应选[0,1,2]/[0,3,4]/[0,5,6]及回绕，短列表无越界/重复、budget1公平、旧源行为保留、作者每次复查、取消/失败不后台重试；worker传flag且原CLAIM进度冻结不被RENEW污染。
- [x] Node24 Vitest新+受影响既有tests及tsc定向一次；root读真实PG/HTTP产物交正式parseExecutionReceipt确认，必要本机组合验收不调用实际平台。

## 收口

- [x] 固定SHA整批独立审核；无阻断修复项；记录边界及下一待办。按既定main收口流程提交，远端结果由最终Git回读确认；文档提交不重跑同字节测试，goal不关闭。

## Evidence

- 客户端实现 `c0b8349`。新增测试先RED（12 failed，根因为缺请求字段/协商/轮次接线；原生误授予测试因旧代码继续等待输出而超时），实现后定向17项GREEN。
- 最终客户端一次受影响集合：Node24 `vitest run tests/publicSampleRotation.test.ts tests/publicCommunityDriver.test.ts tests/collectionWorker.test.ts tests/foregroundCollectionController.test.ts tests/executionOperation.test.ts tests/executionReceipt.test.ts tests/executionSession.test.ts tests/executionJournal.test.ts` → **428 passed**；`tsc --noEmit` exit 0。
- 实际客户端组合测试使用正式controller→worker→public driver→上传/FINISH，在新能力时round1选12/15/16、旧服务无能力时保留12/13/14；来源响应和外部服务替身为合成输入。混合平台只给PUBLIC_WEB轮换授权；能力响应失效/异常/会话变化在START前停止，不降级重试。
- root用本次真实受限PG＋认证本机HTTPS的CLAIM请求/回执，经Vite加载正式`executionOperationSchema`与`parseExecutionReceipt`读取：`v2ex-qna-v1 / round=0`通过；请求JSON规范域不变。脱敏临时产物`/tmp/yike-public-sampling-http.json`不入仓库、不含token/key/签名，不是实际平台证据。
- 服务端实现 `cf28724`。合同/support先RED5项→GREEN15项，PG缺字段RED1项后实现；最终`YIKE_PUBLIC_SAMPLING_TEST_DATABASE_URL=<专用隔离库> uv run --frozen --extra dev pytest -q tests/test_public_sampling_progress.py` → **18 passed**，使用本机`yike_public_sampling_task1`和受限角色。批次COMMIT后重放原CLAIM仍round0；无upload的终止轮次后仍round2，上传/关闭时序用合成任务验证。
- 服务端旧接口定向一次：`uv run --frozen --extra dev pytest -q tests/test_execution_contract.py tests/test_execution_signing_payload.py tests/test_execution_api.py tests/test_foreground_collection.py tests/test_public_collection_policy.py tests/test_public_node_collection.py tests/test_public_author_context_backend.py tests/test_bili_link_collection_policy.py` → **156 passed**；限定Python编译与`git diff --check` exit0。
- 固定`c8c272a→cf28724`由非作者`sampling_round_review`整批独立**GO（仅允许本批合并）**，P0/P1/P2为0；核对全部16个差量文件及相邻事务/权限/恢复路径，产品与测试工作树等于固定HEAD，diff check exit0；复用实现者限定测试证据，不冒称审核者重复运行。后续仅追加本段证据/状态文档，不改变已审产品字节。没有构包、部署、实网平台/模型或外发。

### 仍未完成

原生四平台持久游标、index外已留存旧帖的有界公平复查、多源研究与覆盖补查、生产真实周期/同版本客户端及客户闭环仍待推进。当前轮数只使固定公开index预算位置轮换；动态插入/删除/重排仍可能重复或漏项，不能称全站增量或全网覆盖。没有实际线索增量/效果证据，本批不计任何新增商机。

本批未另建完整PG错误capability矩阵或实际暂停/恢复revision时序；已有helper拒native/nonmonitor与support无public_monitor不广告的测试，SQL明确不按revision清零。跨租户运行隔离继承既有RLS/ACL，本批额外实测同tenant其他owner和同owner其他plan，不把它扩大为所有并发故障已验。
