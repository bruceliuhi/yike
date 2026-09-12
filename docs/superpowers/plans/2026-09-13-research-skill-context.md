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
- [x] RED missing function, complete valid sample for AI and nonAI service, extra/missing/forged scalars/timezone/unicode/size/history_scope/credentialURL reject fixed errors; dict insertion order produces same hash, changed context changeshash.
- [x] RED packaged resource missing fails; source fourfile names/text participate inrulehash. No monkeypatch business outcome; mock filesystem only for corrupt/missing resource boundary.
- [x] Implement strict plainJSON validation, read fixed resource files, build host rules/scope header and canonical JSON/binding; add four force-include paths `pilot/_research_rules/...`. Do not alter current assessment rules mapping.
- [x] GREEN `uv run --frozen --extra dev --extra research pytest -q tests/test_research_context.py`, diffcheck, commit ownfiles and report `/tmp/yike-research-context-report.md`. No actual key/provider access.

### Task 2: Worker integration and delivery evidence (root)

**Own:** `pilot/codex_research_worker.py`, `tests/test_codex_research_worker.py`, docs.
- [x] Add omitted sentinel optionalcontext, fail early with nullbinding for invalidcontext; compile before creating tempdir/bridge. Retain rawdescription4000 bound and check keys in compiledcontext before writing files.
- [x] RED fixture tests for actual instructions and stdin, no business/keys inargv/env, finalbinding is hostmade notmodel, explicitNone nofallback, oldreadonly/searchcompat.
- [x] `_command` accepts optional rule instructions; append exact compiled rule text after existing budget/tool boundaries; `_execute` receives description+clearlydelimited contextJSON. Return binding only explicitcontext mode even failure/cancel.
- [x] Targeted GREEN workerfile; once wheel content parity check in tmpdirectory; do not rebuilddesktop.
- [x] One bounded real profile-driven research if prerequisitesavailable; record lineage/time/gradeunknown honestly, no artificial datedlead success.
- [x] Independent wholebatch review and deltafix; merged remote `916df9c` preserving Win changes. Main push/parity is recorded in the handoff after this commit. Frontend progress alignment remains linked companion work, not claimed implemented here.

## Evidence

### Implementation and bounded verification

Baseline `ba0ae76` validated tool search/read but did not load the full original research Skill or host business context. Commits `fcfdb7a`, `a48c175`, `74e353a` add the fixed four-file loader, strict context compiler, packaged resources and actual worker instructions/stdin integration. Original personal/repo Skill wording is unchanged. Host context is not authentication, a customer-confirmed snapshot or permission to send.

- Worker integration: 9 new tests initially failed for the missing keyword; affected worker suite then passed 46 tests. Fixture subprocess captures actual loaded rules and stdin scope, not only file existence.
- Independent review of `74e353a` found a stale UTC-negative test and escaped actual-key inspection gap. `af672be` removed the contradictory test, added `Z`/`+00:00` positive cases and inspected decoded values. Compiler plus worker: **83 passed in 16.36s**. Subsequent URL-normalization delta is recorded below, not hidden by this earlier pass.
- Reviewer found URL normalization could still encode a literal actual credential before inspection. `bb3b61e` also scans the original successfully-validated context values. New regression RED 1 failed, GREEN 1 passed; affected compiler/worker suites **84 passed in 17.95s**. No extra real-provider request for this safety fix.
- One wheel was built to check the four packaged rules byte-for-byte against source. All four matched. This archive preceded final fixes: it is resource-packaging evidence only, not the final candidate or a desktop build.
- Model-behavior comparison against fixed business evidence (unknown budget/comment-only/closed/history cases) is **not yet completed**. These tests establish transport/validation, not search quality or grading accuracy.

### Actual research, failure and targeted protocol fix

Both runs used Codex, `doubao-seed-2-1-turbo-260628` and actual Serper; no external sending. Self-use AI development context, a 60-day window and PARTIAL history containing two old V2EX posts. The sample UUIDs are test scope identifiers, not saved customer-version evidence. Limits: 3 searches, 3 reads, 8 model requests, 120 seconds. Original text previews are bounded, not full-page archives.

1. Frozen `74e353a`: **FAILED / runtime_failed**, 13.89s. Three searches returned index results, but no successful original read. First provider request succeeded (9,279 input / 218 output tokens); second failed, with unknown usage. Context SHA `46cef7e1316a5d35dd4b67d5e472ee26cce1cff5c53ecc929502ee99d0ac7b63`. No qualified lead or successful research claim.
2. Four tiny synthetic protocol requests isolated the domestic Responses API difference: assistant history missing `status` returned 400 `MissingParameter input.status`, with or without `phase`; adding `status:completed` returned 200 in both variants. No real customer text in this differential. `f783b3b` supplies only a missing top-level assistant-message status, preserving explicit statuses and content. Regression RED 1 failed, then **29 bridge tests passed in 13.69s**. This protocol status is not task completion.
3. Frozen `f783b3b`: **COMPLETED**, 63.67s; 3 searches, 2 successful original reads, 4 successful provider requests. Temporary diagnostic printed only assistant-history field names and confirmed `had_status:false` before adaptation. Context SHA `ac661b6abcf8905b255b5e411d117c3823d5a1ebe6bb817adebd846a9a7845de`. CLI usage: 54,945 input, 37,800 cached input, 2,648 output tokens. This is execution cost, not a commercial price or proof of efficiency. Do not rerun unchanged providers merely to associate later safety fixes with this run.

Both rule SHAs: `bdda7218ae21279b275271397d0d5a1f1a0d6a56c38194ea42ce57cf95374946`.

Read originals: [V2EX 1238323](https://www.v2ex.com/t/1238323), enterprise DIY knowledge-base consultation (author date 2026-08-31); [V2EX 1232068](https://www.v2ex.com/t/1232068), technical-lead recruitment (2026-08-04). **0 qualified leads**. Commenter allegations in the latter are not verified facts; recruitment form is sufficient for exclusion under this run's profile. Electric Duck channel read was unavailable; later over-budget search/read attempts were rejected. The model's coverage narrative is not a separate measurement system, and a failed channel read does not prove the whole platform unreadable. Its suggested seller-oriented “接私活” search is not accepted as a proven buyer-search improvement.

### Integration and remaining work

Independent final delta review of `bb3b61e`: **Ready to merge for the reviewed code scope**; original findings and URL-normalization variant resolved. Final merge/push follows this evidence commit; report remote parity in handoff, not by rebuilding the same bytes. No customer API, task permit/evidence transaction, frontend implementation, Windows package or production deployment in this batch. Frontend companion source audit remains `design/RESEARCH_EXPERIENCE_ALIGNMENT.md`; preserve eight-entry R3/R4 rather than invent another app. Next integrate the scoped research into that actual customer path and compare business outcomes, not simply add keywords. Full Goal stays ACTIVE.
