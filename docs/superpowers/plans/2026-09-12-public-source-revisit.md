# 已发现公开来源复查 Implementation Plan

> 使用subagent-driven-development与TDD；独立整批一次审核，用户授权省略逐项设计等待及重复构包。

**Goal:** 公开项目源不因帖子滑出index而永久丢失作者更新。
**Architecture:** 服务端从已提交事实冻结旧帖→CLAIM v2→固定driver读取→签名batch原文/复查结果原子保存→原时间线。
**Tech Stack:** Python/PostgreSQL/FastAPI，Electron TypeScript/Zod。

## Global Constraints

- 基线`031c14a170a6a45fe51677fabf6067340bb1b57a`；已有隔离worktree`/tmp/yike-v02-scope.Pwf9Fs`，分支`codex/public-source-revisit`。无生产/构包/外发，不读凭据或无关账号。
- 固定协议以[同日spec](../specs/2026-09-12-public-source-revisit-design.md)为准：v1/plain不变，v2只CLAIM；旧服务明确422/invalid_request仅只读降级v1。
- 仅项目作者源奇数round复查1条；max3主题、max5请求、1MiB/20秒/60秒本机冷却不扩；最新与旧帖去重。当前正文失去关键词仍保留原query和作者更新。
- 同scope已提交事实做公平队列；复查结果与原文同batch事务，READ/UNAVAILABLE不等于需求有效/已关闭，未知不盲重试。无真实资料证明不得标客户验收。
- 后台仅agent写pilot/tests；root写desktop/docs；不交叉覆盖。主实现者不最终验收，仅冻结整批后独立review一次。

### Task 1: 后台固定复查对象与签名提交

**Files:** `pilot/public_sampling_progress.py`、`execution_contract.py`、`execution_runtime.py`、`execution_api.py`、`candidate_contract.py`、`candidate_ingestion.py`；新`pilot/public_source_revisit.py`，新`tests/test_public_source_revisit.py`及必要原sampling测试。不改desktop/docs/vendor。

**Interfaces:** `committed_public_sampling_round(...,version=1)`保留旧调用；v2返回spec精确嵌套。`PublicSourceRevisit` Pydantic严格DTO供candidate可选字段使用。入库内部校验需绑定当前CLAIM receipt＋执行context，所有结果原receipt回显。复用原数据库事实，不新建游标表。

- [ ] RED：`ExecutionOperation.model_validate(operation_payload('CLAIM')|{'public_sampling_version':2}).model_dump(mode='json')['public_sampling_version']==2`；旧v1及无字段字节不变。新增v2来源/奇偶/空队列，非法结果、跨owner/plan/query/原生平台拒绝。
- [ ] 在`committed_public_sampling_round`权威检查后为v2选同计划历史PAGE；查询已有observations→batches→occurrences，校验URL/topic/query；以同计划已提交batch.receipt.public_revisit的最新received_at排序，无新表。候选DTO增加可选结果，省略缺省，在prepare/apply原fence内验证冻结CLAIM与READ记录/UNAVAILABLE无记录。
- [ ] 专用PG沿`tests/test_public_sampling_progress.py` fixture的新隔离数据，验证真实CLAIM→batch→FINISH→下一轮：新增发现、奇数复查A、后续复查B、空返回推进、失败不推进、重放固定与隔离。认证HTTPS保存无凭据合成产物`/tmp/yike-public-revisit-http.json`，形状`{events:[{kind:'execution',request,receipt},{kind:'candidate',request,prepared:{batch_fingerprint},receipt}]}`。
- [ ] 执行`uv run --frozen --extra dev pytest tests/test_public_source_revisit.py tests/test_public_sampling_progress.py -q`，补受影响候选旧合同最小组。报告`/tmp/yike-public-revisit-backend-report.md`含RED/GREEN、未验范围。不得commit/push/停止共享容器。

### Task 2: 客户端协商、读取与原文闭环（root）

**Files:** 新`desktop/src/shared/publicSourceRevisit.ts`；执行/候选schema、controller/service policy/worker/publicCommunityDriver及其测试；`publicSources.ts`范围说明。不改pilot。因candidate合同新增DTO依赖，`app/windows_portable_inventory.py`纳入其独立文件，复用现有隔离host导入测试，不构包。

**Interfaces:** v2嵌套的revisit严格schema；completed `{records,publicRevisit}`接原签名batch的`public_revisit`，与nativeProgress互斥。controller仅monitor先协商v2，严格旧422转v1；已有v1广告保留v1运行。

- [ ] RED：v2回执与新增签名结果，字段缺失/多余/伪造claim拒绝；正式driver用合成index与真实适配方法读取脱离index的旧帖，`expect(records.find(r=>r.external_source_id==='101')?.body).toBe('已经找到团队了')`，断言保存作者新回复。
- [ ] schema与worker在正式链传递，不改FINISH或执行context；`sampledTopics`前去重并预留1槽，固定数字topic endpoint读取后做当前规范校验；UNAVAILABLE不编record，不因当前正文失去原关键词而漏掉变化。
- [ ] 合成传输覆盖取消、500/429/畸形旧帖、错误节点与URL、无旧帖、maxRecords1、index重复、字节预算及旧服务v1；沿真实签名/加密journal/回执parser核验新字段。
- [ ] Node24受影响Vitest＋tsc；正式parser消费Task1认证HTTPS产物，测试输入无外部副作用。仅真实失败追加定向复测。

### Task 3: 整批审核与合main

- [ ] 冻结产品提交；非作者审核spec、全差量、定向证据及未验边界，发现P0/P1/P2修复后只差量复核。
- [ ] 统一在本节写证据；任务书/整合状态仅链接摘要。fetch并正常合main，push后回读SHA；不重跑相同产品字节，不把本片GO算完整Goal完成。

## Evidence

2026-09-12，实施完成，待独立整批审核；未部署/构包/真实平台/外发。上方checkbox保留原实施步骤，本节是实际证据，不用计划代替完成。

- 后台初次RED为v2/DTO缺失；首轮22 passed后，补充负例发现伪造lease/run并省略复查结果可在prepare被当作旧协议。改为先按服务端当前CLAIM定位、再核对完整context。最终受限PG/认证HTTPS/API 68 passed；合同/真实旧路由184 passed、2 deselected；纯函数奇偶及其它源4 passed。记录`/tmp/yike-public-revisit-backend-report.md`保留具体命令、夹具错误与边界。
- 客户端首轮18 failed/9 passed，确认新schema/driver缺失；修正租约截止、Vitest数组参数及轮换顺序夹具后27 passed。worker新v2负例先3 failed，再与controller/reader/签名/加密journal/回执组共435 passed、2 failed（两条旧测试把现已批准v2当非法）。将非法版本改为3；后续源/采样3文件75 passed。上述组有重叠，不累加为全仓成绩。
- 已实现controller→正式worker→真实reader方法的合成传输组合：脱离index的旧帖正文“已找到团队”不因关键词消失而被丢弃，作者回复留存；无结果也带原CLAIM结果签名，重放从原加密journal恢复。真实外部HTTP 403/404/429/500不计作UNAVAILABLE，只有合法200空/隐藏响应有此记录。
- 补充deleted标记但URL为外站的负例先1 failed，修复为先校验旧帖URL，再判断可读性；最终75项包含该回归。取消/截止/字节上限复用同reader共用边界，未单独声称Windows/平台实跑。
- 正式TS解析器消费`/tmp/yike-public-revisit-http.json`的实际本机认证HTTPS/受限PG产物：六轮CLAIM/入库、READ与UNAVAILABLE精确回显及Python指纹，1 passed。数据为合成，不含凭据。`YIKE_PUBLIC_REVISIT_HTTP_ARTIFACT`缺省时该测试skip，不能当联验通过。
- 基线`031c14a`实际旧handler输出v2 422与v1 200；正式ServiceClient+controller消费`/tmp/yike-public-revisit-legacy-support.json`，1 passed。新版只读协商明确拒绝后退到v1，不重试执行；其它错误/会话变化有单独拒绝测试。类型检查tsc成功。
- 既有隔离Python进程的HOST_FILES导入测试发现新增DTO依赖未进清单，先1 failed（ModuleNotFoundError），补清单后同测试1 passed；未改变vendor，未给旧Windows包背书。

完整V0.2 Goal ACTIVE。待独立冻结审核后正常合main；其它原生平台游标、完整评论深读、多源研究、生产/Windows及跨行业客户验收继续。
