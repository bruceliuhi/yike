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
