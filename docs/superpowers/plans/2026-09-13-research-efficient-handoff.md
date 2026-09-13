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

- [ ] Step 1 — 添加定向失败测试，先运行记录RED。

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

- [ ] Step 2 — 实施最小代码。

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

- [ ] Step 3 — 受限PG端到端定向RED/GREEN。

复用 `dynamic_env`，mission经真实dispatch记录分配上限数量的MODEL和两页READ，输出两项ASSESS；核验普通assessment两条、最终COMPLETED、总消耗不超确认限制。已有all_background测试补unpublished=0；另验证skipped_budget/无batch仍非0。用同一个owned临时PG，不建立生产数据。root提供端口与连接参数，提供前先做纯测试，不自行启动多个DB。

为并行加速，root负责独立文件中的两候选纵切；先用仅测试进程插件将预留还原为旧1次公式确认RED，不回退共享产品文件；再无插件运行GREEN。其余现有文件用例由实现Agent完成。

- [ ] Step 4 — 只运行一次相关组与自审、提交代码。

Run: `.venv/bin/python -m pytest -q tests/test_codex_research_worker.py tests/test_research_context.py tests/test_research_page_selection.py tests/test_responses_bridge.py`；PG只跑本批新增/改动的命名用例。目标全部通过，保留初次失败，不把skipped当通过。

- [ ] Step 5 — 一次独立Spec/Quality审核；合并发现项，定向修复、差量复核。
- [ ] Step 6 — root用固定公开快照＋fresh模型核验实际schema，比较输入/缓存/耗时，不声称稳定率；必要时另一个明确业务样本打通普通判断。确认后一次新有界实网任务，不能重放旧UNKNOWN。
- [ ] Step 7 — 更新本页证据及唯一任务书/整合状态，核验远端main后正常合并推送。纯文档不构包。完整Goal继续ACTIVE。

## Evidence

开始：基线79427c0；已复用上一轮定位证据，尚未实施/测试。

## Task 1 实网门禁发现后的单一修订：quote_ref

前置证据：`a23c0ce`整批独立Spec/Quality PASS；固定快照真实模型strict schema送达，但第二页quote非逐字导致STOPPED。按同日spec末尾修订继续本批，暂不合并/部署；不是再新增一组泛化功能。

**Files:** 新增 `pilot/research_citation_selection.py`、`tests/test_research_citation_selection.py`；修改 `pilot/research_tools.py`、`pilot/codex_research_worker.py`、`pilot/research_context.py`及其三份定向测试。不改 `research_page_selection.py`、runtime、Bridge、原Skill包或DB。
**Interfaces:** `citation_fragments(text: str) -> list[dict]`（q1起，每段原文400字符）；`citation_choice_schema() -> dict`（detached内部schema）；`CITATION_CHOICE_INSTRUCTIONS`；`expand_citation_choices(summary: str, evidences: list[dict]) -> str`（严格新final→旧v1 JSON）。`build_server(..., citation_mode=False)`仅显式True投影TextContent，新增CLI `--citation-mode`开关；legacy完全不变。

- [ ] 先添加RED：缺新纯函数、contextual命令/schema、MCP片段显示及原structured不变；原v1改写引文反例仍失败。

```python
def test_citation_fragments_preserve_original():
    text = '甲\n🙂e\u0301 ' * 101
    pieces = citation_fragments(text)
    assert ''.join(p['text'] for p in pieces) == text
    assert all(1 <= len(p['text']) <= 400 for p in pieces)
    assert pieces[0]['quote_ref'] == 'q1'

# 展开后只交给旧parser验证；错误ref/错页hash/重复缺页/JSON重键必须失败。
```

- [ ] 实施纯引用选择器和contextual工具/worker接线。

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

- [ ] 一次定向组：新纯函数、research_tools、worker、context；不重跑原parser/Bridge/PG全套。新接点必须通过实际MCP工具及worker事件夹具，不以字符串存在代替转换验证。原legacy/frame大小测试如需改，只改新版contextual final夹具，保留原目的。
- [ ] 提交修订代码，交同独立reviewer差量复核；root随后以新输出路径跑同快照fresh模型一次，旧失败保留。通过后才进行已准备的新有界实网任务，最后更新唯一证据/状态并同步main。
