# Research Skill Context Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. One whole-batch independent review; affected tests only.

**Goal:** Original versioned research method and bounded customer scope actually reach the Codex search mission, with host-generated provenance.
**Architecture:** Fixed rule loader + strict context compiler; optional keyword-only context in existing worker. No new framework or database.
**Tech Stack:** Existing Python/Pydantic/importlib resources, Codex worker, hatch wheel.

## Global Constraints

- Exact fields, bounds, failure codes and compatibility in `docs/superpowers/specs/2026-09-13-research-skill-context-design.md` bind this plan.
- Personal/repo Skill source text unchanged. Only fixed four rules from repo/wheel; no user-supplied paths or arbitrary-file tool.
- Explicit invalid/None context must fail before subprocess/provider I/O, not fall back. Missing optional field keeps old result fields and behavior.
- Host binding, original evidence and model interpretation separate; this is internal context not authorization/customer rollout. No sending, model-key exposure, unrelated full suites or desktop build.

### Task 1: Compile context and fixed original rules

**Own:** new `pilot/research_context.py`, `tests/test_research_context.py`, `pyproject.toml` force-include entries only.
**Interfaces:**
```python
class ResearchContextError(Exception):
    code: str  # invalid_research_context or research_rules_unavailable

def compile_research_context(value: dict) -> dict:
    # {instructions: str, context_json: str, binding: dict}
    # binding exact fields per design; all host-generated, fresh immutable-by-copy data
    ...
```
- [ ] RED missing function, complete valid sample for AI and nonAI service, extra/missing/forged scalars/timezone/unicode/size/history_scope/credentialURL reject fixed errors; dict insertion order produces same hash, changed context changeshash.
- [ ] RED packaged resource missing fails; source fourfile names/text participate inrulehash. No monkeypatch business outcome; mock filesystem only for corrupt/missing resource boundary.
- [ ] Implement strict plainJSON validation, read fixed resource files, build host rules/scope header and canonical JSON/binding; add four force-include paths `pilot/_research_rules/...`. Do not alter current assessment rules mapping.
- [ ] GREEN `uv run --frozen --extra dev --extra research pytest -q tests/test_research_context.py`, diffcheck, commit ownfiles and report `/tmp/yike-research-context-report.md`. No actual key/provider access.

### Task 2: Worker integration and delivery evidence (root)

**Own:** `pilot/codex_research_worker.py`, `tests/test_codex_research_worker.py`, docs.
- [ ] Add omitted sentinel optionalcontext, fail early with nullbinding for invalidcontext; compile before creating tempdir/bridge. Retain rawdescription4000 bound and check keys in compiledcontext before writing files.
- [ ] RED fixture tests for actual instructions and stdin, no business/keys inargv/env, finalbinding is hostmade notmodel, explicitNone nofallback, oldreadonly/searchcompat.
- [ ] `_command` accepts optional rule instructions; append exact compiled rule text after existing budget/tool boundaries; `_execute` receives description+clearlydelimited contextJSON. Return binding only explicitcontext mode even failure/cancel.
- [ ] Targeted GREEN workerfile; once wheel content parity check in tmpdirectory; do not rebuilddesktop.
- [ ] One bounded real profile-driven research if prerequisitesavailable; record lineage/time/gradeunknown honestly, no artificial datedlead success.
- [ ] Independent wholebatch review and deltafix ifneeded; merge latestremote preservingWinchanges, pushmain, record evidence once. Frontend progress alignment remains linked companion work, notclaimedimplementedhere.

## Evidence

Pending implementation. Baseline `ba0ae76` validated tool search/read but didn't load full original search Skill or host business context; original personalSkill remains usable and unchanged.
