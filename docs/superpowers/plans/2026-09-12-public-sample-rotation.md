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

- [ ] TDD先写合同RED：缺省旧dict不变；只CLAIM接受1；null/True/2/RENEW/START拒绝；旧support无新字段、新query受认证并按public_monitor返回capability。
- [ ] 实现合同/SQL/CLAIM合并。核心计数等价：
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
- [ ] 用既有自有PG容器 `yike-research-resources-task1-pg` 新建本批隔离DB；真实受限角色、签名START/CLAIM/upload，跨轮0→1→2（含空batch），CLAIM重放不重算，同run重放不双计、未FINISH但已上传计入、未上传/其他owner/plan不计；保留旧CLI/API签名用例通过。运行 `uv run --frozen --extra dev pytest -q tests/test_public_sampling_progress.py` 及实际受影响原测试，不重跑全仓。
- [ ] 保存一次受认证HTTP的新CLAIM response及对应请求为脱敏合成JSON（无token/key/签名/凭据），供root正式TS parser读取；报告含RED/GREEN、命令、文件、DB名及未验项。停止修改等待root合并，不自行停他人容器。

### Task 2: 正式客户端协商、轮换与验证（root）

**Files:** `desktop/src/shared/executionOperation.ts`、`executionReceipt.ts`、`desktop/src/main/executionServicePolicy.ts`、`foregroundCollectionController.ts`、`collectionWorker.ts`、`publicCommunityDriver.ts`；新 `desktop/tests/publicSampleRotation.test.ts`，必要已有controller/worker/receipt测试。

**Interfaces:** 私有 `execution.support` 可选 `{samplingVersion:1}` 映射固定query；只在公开monitor启动时读取，并严格解析support的可选public_sampling字段。`launchSequence`→`worker.run`加main-only `allowPublicSampling?:true`；只有anonymous PUBLIC_WEB+monitor才允许。CLAIM operation条件加入flag；`parseExecutionReceipt`核对flag与public_sampling有无一致、只能CLAIM；driver仅使用原CLAIM lease中的固定progress，source_id必须等于冻结configuration.publicSource。

- [ ] 写RED：无flag旧序列化/回执原样；CLAIM新flag/进度可读、错版本/来源/operation拒绝；固定私有route query；新controller询问capability并传worker，旧capability不发flag，native/once不改变。
- [ ] 实现根端合同及正式controller→worker→driver路径，无只用于测试的绕行。抽样核心：
  ```ts
  if (budget >= items.length || progress === undefined) return items.slice(0,budget);
  if (budget === 1) return [items[round%2===0?0:1+Math.floor(round/2)%(items.length-1)]];
  return [items[0],...Array.from({length:budget-1},(_,i)=>items[1+(round*(budget-1)+i)%(items.length-1)])];
  ```
  原source/author字段和预算验证保持；已选内容query不匹配不继续加读，空结果正常上传。
- [ ] 源响应合成但driver真实函数三轮应选[0,1,2]/[0,3,4]/[0,5,6]及回绕，动态短列表无越界/重复、budget1公平、旧源行为保留、作者每次复查、取消/失败不后台重试；worker传flag且原CLAIM进度冻结不被RENEW污染。
- [ ] Node24 Vitest新+受影响既有tests及tsc定向一次；root读真实PG/HTTP产物交正式parseExecutionReceipt确认，必要本机组合验收不调用实际平台。

## 收口

- [ ] 固定SHA整批独立审核；修复只复审差量；记录边界及下一待办，正常合入main并回读远端SHA。没有新产品字节的检查不重跑，goal不关闭。
