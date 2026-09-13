# 研究交接与阶段效率 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. 本批为一个可独立审核的端到端任务；不要拆成多轮提示词补丁。

**Goal:** 降低研究阶段无关输入和格式风险，让多候选判断拥有预留额度并准确报告背景页处理完成。
**Architecture:** 保留现有Codex/Bridge、持久READ、严格逐页parser、普通assessment。仅添加原生final schema和固定阶段投影，调整runtime确定性额度分配及已有进度聚合。
**Tech Stack:** Python、Codex CLI Responses、PostgreSQL、pytest。

## Global Constraints

- 不放宽原文哈希/引用/完整性校验，不增加模糊修复、默认全选或静默重试。
- 不更改登录、租户/owner隔离、SSRF/redirect、凭据、UNKNOWN、取消、确认外联、资源计量与付款门禁。
- 个人Skill及仓库原Skill包不改；不删普通assessment、不虚构作者或原文日期。
- 不新增来源连接器、不改生产、不构包，不声称新线索或商业证明。
- 同字节已通过证据复用，只跑本批定向测试；独立整批审核，发现项合并修复后只差量复核。

## Task 1: 完整研究交接改进

**Files:**
- Create: `pilot/research_stage_rules.py`
- Modify: `pilot/research_page_selection.py`, `pilot/codex_research_worker.py`, `pilot/research_context.py`, `pilot/dynamic_research_runtime.py`
- Test: `tests/test_codex_research_worker.py`, `tests/test_research_context.py`, `tests/test_research_page_selection.py`, `tests/test_responses_bridge.py`, `tests/test_dynamic_research_runtime.py`
- Test (root independent integration): `tests/test_research_handoff_postgres.py`；root与实现Agent文件不重叠，最终同批独立审核。
- 只有真实payload测试证明必要时修改 `pilot/responses_bridge.py`，不改provider全局策略。

**Interfaces:** 保留现有public/internal返回字段、`parse_page_selection(summary,evidences)`及绑定字段；增加纯函数 `page_selection_schema()` 每次返回独立schema。新阶段模块输出常量 `RESEARCH_STAGE_INSTRUCTIONS`。`_instructions(documents)`仍以已校验全部规则包为输入，输出包含其规范摘要和投影的固定文本，`rule_sha256=sha256(instructions)`不变。runtime私有 `_assessment_reserve(model_calls,max_records,max_reads)` 返回上述A；内部claim结果增加maxRecords供本轮使用，不扩外部DTO。

- [x] Step 1 — 添加定向失败测试，先运行记录RED。

```python
def test_selection_schema_is_exact_and_detached():
    first = page_selection_schema()
    assert set(first['properties']) == {'schema_version', 'summary', 'pages'}
    assert first['additionalProperties'] is False
    assert set(first['properties']['pages']['items']['properties']) == {
        'url', 'content_sha256', 'decision', 'reason', 'quote'}
    first['properties'].clear()
    assert page_selection_schema()['properties']

def test_multiple_candidate_budget_is_reserved():
    assert _assessment_reserve(8, 20, 7) == 4
    assert _assessment_reserve(8, 1, 7) == 1
    assert _assessment_reserve(2, 20, 1) == 1
```

另在已有worker夹具检查 `--output-schema`实际文件JSON和stdin画像仅一次，legacy不带；已有bridge输入添`text.format`断言出站保留精确schema。context检查新版本、原规则任何变化会变rule_sha、缺失包仍拒绝、投影长度小于原输入且包含买方/未知/反证/只读规则。保留已有严格parser反例。

- [x] Step 2 — 实施最小代码。

```python
def _assessment_reserve(model_calls, max_records, max_reads):
    return min(max_records, max_reads, max(1, model_calls // 2))

# claim使用task['max_records']; _run已有max_reads
reserve = _assessment_reserve(limits['modelCalls'], limits['maxRecords'], max_reads)
# mission max_requests=limits['modelCalls']-reserve

# _command在research_instructions is not None时写临时schema并加参数：
schema_path = root / 'page-selection.schema.json'
schema_path.write_text(json.dumps(page_selection_schema()), encoding='utf-8')
command += ['--output-schema', str(schema_path)]
```

schema只用object/array/string、properties/required/additionalProperties/enum，不用provider不支持的长度约束。decision enum为ASSESS/BACKGROUND，reason为现有7项，schema_version只有现有值；组合语义仍parser负责。阶段指令按spec逐项覆盖，无草稿、文件写入职责；每份原规则SHA按文件名稳定排序写入文本，不注入其全文。只在compiled存在时以HOST_RESEARCH_CONTEXT_JSON代替重复description；无context原行为保留。

进度仅当存在合法背景跳过标记且无其他跳过时从未发布中扣除；原缺batch、invalid/budget跳过仍保留。查询补取现有 `batch.execution_context` 的跳过计数与page_selection；receipt仍只提供items，不新增其字段。

- [x] Step 3 — 受限PG端到端定向RED/GREEN。

复用 `dynamic_env`，mission经真实dispatch记录分配上限数量的MODEL和两页READ，输出两项ASSESS；核验普通assessment两条、最终COMPLETED、总消耗不超确认限制。已有all_background测试补unpublished=0；另验证skipped_budget/无batch仍非0。用同一个owned临时PG，不建立生产数据。root提供端口与连接参数，提供前先做纯测试，不自行启动多个DB。

为并行加速，root负责独立文件中的两候选纵切；先用仅测试进程插件将预留还原为旧1次公式确认RED，不回退共享产品文件；再无插件运行GREEN。其余现有文件用例由实现Agent完成。

- [x] Step 4 — 只运行一次相关组与自审、提交代码。

Run: `.venv/bin/python -m pytest -q tests/test_codex_research_worker.py tests/test_research_context.py tests/test_research_page_selection.py tests/test_responses_bridge.py`；PG只跑本批新增/改动的命名用例。目标全部通过，保留初次失败，不把skipped当通过。

- [x] Step 5 — 一次独立Spec/Quality审核；合并发现项，定向修复、差量复核。
- [x] Step 6 — root用固定公开快照＋fresh模型核验实际schema，比较输入/缓存/耗时，不声称稳定率；本批成功证据见下。新有界真实买方任务留到统一试用验收，不能重放旧UNKNOWN；这仍是未完成的产品效果门禁，不因背景页成功而省略。
- [ ] Step 7 — 更新本页证据及唯一任务书/整合状态，核验远端main后正常合并推送。纯文档不构包。完整Goal继续ACTIVE。

## Evidence

### 初版实现和独立审核

基线`79427c0`，实现`7b66d4c`，独立两候选纵切测试`a23c0ce`。contextual native schema、单份画像、6276字节研究阶段投影、普通判断预留及背景进度修正已实现；原四份包23941字节，个人Skill/原包不改。

实现者先RED；首次缺函数collection随后改为行为断言，148通过/43失败中6项是预期功能缺口，其余为sandbox loopback禁止，不当产品缺陷。GREEN：预算边界及纯定向149项/19.99秒；worker/context/parser/Bridge四文件191项/41.43秒；背景/预算跳过/无batch的受限PG3项/5.58秒。组间有重叠，不累加为独立总数。

root独立两候选纵切通过测试进程插件还原旧1-slot预留，真实受限PG RED是2入库/1判断/STOPPED（session8093，1失败/6.70秒）；新分配GREEN1项/5.55秒。独立审核指出当次runtime blob与最终字节不同，因此不追认该GREEN：在干净`a23c0ce`仅补跑此项，session11703 exit0、1通过/5.94秒，runtime blob`83548649bdb1bc4975df3e19f3dd00f60e74edb4`/test blob`8b8ebc3c46cd352a4f1ae23c25fda4d64e1aa16d`。变化是背景进度收紧，原失败记录保留。

非作者一次整批审核`79427c0..a23c0ce`：Spec PASS、Quality PASS、无代码阻断项；额外只读188100组合法M/R/P检查未越界，不重跑套件或构包。报告`/tmp/yike-efficient-handoff-independent-review.md`；真实提供商门禁仍单独待验，不能把代码GO升级为产品完成。

### 固定快照真实模型暴露引用交接缺口

`a23c0ce`新任务（不是旧UNKNOWN重试）：同已存V2EX目录与1239289供方页快照，**来源网络调用0**，真实Codex/豆包/Bridge/受限PG及客户测试HTTP。session2589 exit1，pytest30.60秒，任务27.77秒；3次MODEL、2次快照READ、0候选/普通判断，STOPPED/research_selection_invalid。

三次实际出站`text.format`均为精确strict json_schema且未被Bridge删除；模型final严格JSON、每页URL/hash/规则绑定均正确。第二页quote123字符不是持久text逐字连续片段，原parser第95行拒绝；未保存原final文本，不能断言具体拼接/改写/空白原因。输入24291（缓存5944）、输出890；旧同快照成功基线输入39929（缓存19056）、输出815、32.17秒。新输入少但任务失败，**不能把27.77秒作为成功效率提升或省费证据**。

安全artifact：`/tmp/yike-efficient-handoff-{snapshot,structure,transport}-20260913.json`，未存模型输入/密钥；旧artifact保留。此证据支持下列定点quote_ref修订，暂不扩大来源、不再付费盲试、不降低逐字校验。没有新商机/生产/Windows构包/外发；完整Goal ACTIVE。

## Task 1 实网门禁发现后的单一修订：quote_ref

前置证据：`a23c0ce`整批独立Spec/Quality PASS；固定快照真实模型strict schema送达，但第二页quote非逐字导致STOPPED。按同日spec末尾修订继续本批，暂不合并/部署；不是再新增一组泛化功能。

**Files:** 新增 `pilot/research_citation_selection.py`、`tests/test_research_citation_selection.py`；修改 `pilot/research_tools.py`、`pilot/codex_research_worker.py`、`pilot/research_context.py`及其三份定向测试。不改 `research_page_selection.py`、runtime、Bridge、原Skill包或DB。
**Interfaces:** `citation_fragments(text: str) -> list[dict]`（q1起，每段原文400字符）；`citation_choice_schema() -> dict`（detached内部schema）；`CITATION_CHOICE_INSTRUCTIONS`；`expand_citation_choices(summary: str, evidences: list[dict]) -> str`（严格新final→旧v1 JSON）。`build_server(..., citation_mode=False)`仅显式True投影TextContent，新增CLI `--citation-mode`开关；legacy完全不变。

- [x] 先添加RED：缺新纯函数、contextual命令/schema、MCP片段显示及原structured不变；原v1改写引文反例仍失败。

```python
def test_citation_fragments_preserve_original():
    text = '甲\n🙂e\u0301 ' * 101
    pieces = citation_fragments(text)
    assert ''.join(p['text'] for p in pieces) == text
    assert all(1 <= len(p['text']) <= 400 for p in pieces)
    assert pieces[0]['quote_ref'] == 'q1'

# 展开后只交给旧parser验证；错误ref/错页hash/重复缺页/JSON重键必须失败。
```

- [x] 实施纯引用选择器和contextual工具/worker接线。

```python
def citation_fragments(text):
    return [{'quote_ref': f'q{i // 400 + 1}', 'text': text[i:i + 400]}
            for i in range(0, len(text), 400)]

# schema从现有detached page_selection_schema()派生：版本变citation-choice-v1，
# pages.items.properties删除quote新增quote_ref:string，required对应替换。
# expand严格读取JSON后按精确(url,sha)找到同版evidence；解析q1等存在编号；
# 只取citation_fragments(evidence['text'])对应片段，生成旧v1 root；
# 用原parse_page_selection(expanded,evidences)验证后返回JSON；不重试/降级。
# call_tool只投影content中的evidence.text为text_fragments，structuredContent原result不动。
# _command仅contextual加--citation-mode，使用新schema与绑定指令；
# _run_mission仅COMPLETED且compiled时展开已验证events.reads，失败固定错误且无原始摘要回显。
```

- [x] 一次定向组：新纯函数、research_tools、worker、context；不重跑原parser/Bridge/PG全套。新接点必须通过实际MCP工具及worker事件夹具，不以字符串存在代替转换验证。原legacy/frame大小测试如需改，只改新版contextual final夹具，保留原目的。
- [x] 提交修订代码并完成独立差量复核；root以新输出路径跑同快照fresh模型，旧失败保留。新的真实买方验收留到统一候选交付，不追加本轮付费盲搜；最终文档/主线同步见Step7。

### quote_ref实现及新实际模型检查

`969aa1b`实现引用编号选择、MCP TextContent片段展示、worker展开到原严格v1；RED21失败/148通过，最终定向169通过/23.56秒。独立审核唯一P2是超长编号整数转换逃逸固定错误；`2516f5d`改有限映射查找，RED2、GREEN2/0.85秒，selector13/0.12秒。仅该差量复核后Spec/Quality PASS，不追认原失败。

绑定`2516f5d`，session44341固定快照新模型检查：exit1，1失败/25.85秒；2次READ、3次MODEL成功，最终STOPPED/research_selection_invalid。实际strict schema精确送达，但三次出站input均不含text_fragments/quote_ref；模型两页返回q0，未进入原runtime逐字parser。输入24060（缓存12200）、输出475。仅更改工具TextContent尚未证明能让实际模型看见编号；继续定位实际MCP展示通道，不放宽不存在编号校验、不再追加来源搜索。安全证据`/tmp/yike-citation-choice-{snapshot,structure,transport}-20260913.json`保留；来源网络调用0、合成租户、无生产/外联/新商机。

根因已按本机Codex源码确认：structuredContent优先，TextContent被忽略。按同spec“实际Codex工具通道修订”继续该引用接点：仅citation成功READ的模型投影移入structuredContent，完整原READ放宿主JSONL_meta；worker对原证据及其确定性投影双重核验。不改持久READ/最终parser，不加付费搜索。新增一次真实CLI＋本机假provider往返覆盖实际工具通道，定向RED/GREEN后差量审核；仅当无费接点检查通过才做新输出路径的固定快照真实模型检查。旧失败证据保留。

### 通道修复后的成功证据与整合

`f343a64`仅6个工具/worker/citation和测试文件实现上述通道修复。定向RED4失败/2通过；GREEN6通过/1.88秒；相关三文件组115通过/26.14秒。临时无费CLI探针先因错误resolve到系统Python而无法加载MCP，纠正venv入口后又发现采集器误计开始事件；均为夹具问题，不改产品规避。root接手修正计数后，session15474、1通过/4.40秒，真实Codex＋本机假provider证明模型只见片段编号、JSONL保留原meta、worker从原文展开成功。

独立新增差量`f343a64`及UI两行`00f35ba`审核PASS，无剩余阻断；复用之前Task2审核，不重跑全套。最大单事件测试不是任意多页上限保证，既有整轮2MiB stdout上限仍会明确output_limit。正常合入远端`a0142c7`为`5426a27`：保留设备自动准备、XHS自导航和可选MCP导入隔离；worker冲突只合并导入，`_valid_page`仍指同一个reader函数。合并后只补默认runtime无MCP导入1通过/1.03秒和desktop typecheck，不重复其余已测字节。

**实际模型成功绑定`5426a27`**：session52196、1通过/23.71秒，任务21.01秒；同两份已存V2EX公开快照，来源网络0，3次真实MODEL/2次快照READ。后两次模型input实际含text_fragments/quote_ref，strict schema全程一致；两页q1展开后原parser接受，URL/hash/绑定和400字符逐字引用全过。最终COMPLETED，2BACKGROUND（目录/供方）、0候选、0普通判断，unpublishedOriginals=0，UNKNOWN=0。本批没有新增合格商机，也不是新实时来源验证或生产验收。

本次输入24162（缓存16808）、输出430；旧同快照成功基线39929（缓存19056）/输出815/32.17秒。单个同快照观察输入约少39.5%、任务时间约少34.7%；输出/缓存等条件亦不同，不能推断普遍加速、稳定率或计费节省。安全证据保留`/tmp/yike-citation-transport-{snapshot,structure,outbound}-20260913.json`，不覆盖前两次失败。下一步把本批作为统一试用候选，同版本部署/客户端与新的真实买方任务验收；不再重复修已解决的引用接点。未构包、部署、外联或完成完整Goal。

## Task 2：研究原文只读回查（唯一前端补口）

### 统一交付前置检查（2026-09-13）

Docker 源码复制布局未携带 `research_context` 所需的四份规则；wheel 的 force-include 不适用于当前 `--no-install-project` 镜像。补两条 COPY，不改变规则内容、默认研究开关、可选 MCP 依赖、权限或收费参数。既有 COPY 布局隔离 Python 检查先以 `research_rules_unavailable` 失败，修复后 `tests/test_deploy_contracts.py` 4 passed / 1.23s，并校验打包规则逐字节一致。这不是实际镜像构建或云端研究可用证明；Linux Codex/MCP 运行环境及完整已批准配置仍须交付验证。

本机对已批准服务器 `101.200.137.138` 的只读 SSH 检查返回 `Permission denied (publickey)`；详细诊断确认本地 `id_ed25519` 存在且已提供，服务器拒绝该公钥。未修改授权或生产服务，不能据仓库部署记录断言当前线上版本。恢复服务器授权后继续统一部署与真实任务验收，不重复已通过的同字节本地测试。

**Files:** 后端 `pilot/research_runtime.py`（委托dynamic）、`pilot/dynamic_research_runtime.py`（只读方法）、`pilot/research_execution_api.py`（GET）；客户端 `desktop/src/shared/researchRuntime.ts`、`desktop/src/shared/contracts.ts`、`desktop/src/main/servicePolicy.ts`、`desktop/src/renderer/services/researchRuntime.ts`、`desktop/src/renderer/pages/tasks/ResearchProgress.tsx`，新增同目录 `ResearchReadEvidence.tsx`。对应API/PG和desktop现有定向测试；必要时新建独立测试文件以免碰citation实现者文件。不改tools/worker/context/引用选择器，不改既有schema或DB迁移。

**Interfaces:** 按spec末尾固定GET/JSON；后端`reads(claims,task_id,*,run_id,after=0,limit=5)`，fixed仅委托已配置dynamic否则501。客户端可选`reads(taskId,runId,after?,signal?)`接口保留旧fixture兼容；服务调用必须校验响应taskId/runId、序号递增/唯一、分页前进、来源URL与字符串范围、严格DTO。IPC操作`researchRuntime.reads`仍使用主进程固定路径，不接收自由URL。

- [x] RED：成功READ但模型筛选停止仍可GET原文；相邻tenant/owner和错误run拒绝；FAILED/UNKNOWN/MODEL不在列表；limit/after严格，序号分页无重复，损坏结果不暴露。每次读取前后持久动作数量不变。

```python
# 复用受限PG已有成功READ/STOPPED夹具，不执行真实网络或模型：
before = effect_count()
result = runtime.reads(claims, task_id, run_id=run_id, after=0, limit=1)
assert result['items'][0]['text'] == original_text
assert result['items'][0]['contentSha256'] == original_sha
assert effect_count() == before
```

- [x] 最小实现：验证身份/任务/run→查询最多limit+1条本身份成功READ→复用journal配对和effect_result/hash校验→只投影六个原文字段→确定nextAfter。原始payload/context或异常文本不返回。API严格query绑定；前端通过既有transport/IPC固定operation，使用现有受控折叠/长文展开样式，不换皮或另造信息架构。
- [x] 一次受影响定向测试：后端真实受限PG纵切/API及客户端合同/transport/取消换任务隔离；旧服务不支持仍可查看原进度/候选。root提供唯一owned PG端口62169，不自行新开多个数据库；和citation纯测试并行可行，双方不要同时用同一DB夹具。
- [x] 提交本切片并完成独立差量审核；root已做一次界面宽/窄视口检查，与引用修复合并到同一个试用候选，不另构包。不把fixture原文当新商机或生产证据。

### Task2实施证据

代码`2b118fa`（14文件）完成只读成功READ API、严格客户/任务/运行与原动作配对校验、固定IPC/客户端DTO、现有进度页按需展开及手动分页。API after/limit有0/5默认；Unicode上限按后端码点而非UTF-16计算，完整原文不截断。旧服务不可用不影响候选链路；读取不产生模型/网络动作。

定向API14通过/3.88秒；前端三文件33通过/4.83秒，末次UI21通过/3.05秒（有重叠，不累加）；typecheck通过。真实受限PG纵切1通过/4.15秒，覆盖身份/分页/动作数量不变/损坏配对拒绝。root复用既有隔离visual入口添加合成“有原文、筛选未完成”状态，Node Playwright实际Chrome检查1366×900和390×844均无横向溢出、展开收起通过、JS错误0；截图`/tmp/yike-read-visibility-{1366,390}-20260913.png`。初尝Python无Playwright依赖，切用已有Node依赖，未安装新依赖；不是产品失败。此处是界面及合同证据，不是实网商机/客户/生产验收，待独立差量审核。

独立审核`2b118fa` PASS，无P0/P1/P2；唯一P3是卡片仅有安全打开按钮，未直接显示URL。`00f35ba`补一行可折行纯文本URL和一条现有测试断言；同名定向RED1/3.34秒、GREEN1/2.03秒，20项未选不当通过；截图为补此行前的显示证据，不追认为最终像素验收。报告`/tmp/yike-trial-finish-independent-review.md`，后续仅合并citation新差量及此两行核对，不重审Task2整批。
