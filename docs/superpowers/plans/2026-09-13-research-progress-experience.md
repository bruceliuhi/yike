# Research Progress Experience Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. One cohesive UI task, one independent whole-batch review; no redundant full suites or desktop packaging.

**Goal:** Existing customer research tells users what is known, why it stopped and what to do next, without exposing engineering counters as the primary experience.
**Architecture:** Apply the approved-in-scope `design/RESEARCH_EXPERIENCE_ALIGNMENT.md` first phase to the existing ResearchProgress component. A pure presentation helper maps validated server state; no new capability, network calls, execution semantics or data contract.
**Tech Stack:** Existing React, TypeScript, native details/summary, Vitest and shared R3/R4 components.

## Global Constraints

- Preserve eight-entry R3/R4 navigation, panel styles and existing button execution/disabled/abort/reload/navigation semantics. No new frontend dependency or CSS design system; no marketing redesign or generated-image substitute.
- Counts are source and analysis progress, never qualified opportunities. `null` remains unknown, not zero. SourceLabel and per-source table stay visible and exact; no all-web or comment coverage invented.
- Detail disclosure defaults closed and is keyboard accessible. All unknown/failed/pending/canceled warnings stay OUTSIDE details. Completed research is not a qualified lead, financial settlement or proof of absent market demand.
- Scope is renderer-only. Backend integration architecture is separately audited; do not claim new Codex runner is connected to this UI. Synthetic UI states are visual/behavior fixtures, not source/lead/UAT evidence.

### Task 1: Plain-language progress and actionable status

**Files:**
- Create `desktop/src/renderer/domain/researchProgressPresentation.ts` and `desktop/tests/researchProgressPresentation.test.ts`.
- Modify `desktop/src/renderer/pages/tasks/ResearchProgress.tsx` and `desktop/tests/ui/research-progress.test.tsx`.

**Interface:** `researchProgressPresentation(value: ResearchRuntimeStatus): {title:string; explanation:string; nextStep:string; warning:string|null}`. Pure, deterministic, no input mutations or IO.

- [ ] Write failing tests for status mapping and actual UI disclosure, then run only these two files. Existing status regression cases remain, updating expectations for intentionally changed title text/disclosure only.
- [ ] Implement helper. Titles: QUEUED `已准备好，等待开始`; RUNNING `研究进行中`; STOPPED `研究已暂停`; CANCELED `已停止新增研究`; COMPLETED `本轮研究已完成`.
- [ ] Explanations/next steps: queued tells user to use `继续研究`; running may say “当前已确认” but not claim background work unless known; completed acceptedOriginals=0 says `本轮没有取得可供分析的原文，不代表没有市场需求。` and suggests adjusting source/confirmed strategy in a new task; completed >0 says analyses await source/purchase-intent review and directs `查看原文与分析`; completed null says original count unconfirmed, query original state. Canceled explicitly says prior requests are not recalled; do not suggest restarting canceled work.
- [ ] Map actual stop codes to cautious user text: effect_unknown/assessment_unknown: `已有请求的结果尚未核实。` and query existing state, no resend; effect_failed/assessment_failed: `本轮读取或分析未完成。` and inspect existing results/details; resource_limit_exceeded: `本轮已达到确认的研究用量上限。` and inspect results before changing strategy/new task; task_unavailable: `当前任务暂时不能继续。` (do not guess expired profile); capability_unavailable: `当前服务暂不支持这项研究。`; resource_unavailable: `研究服务暂时不可用。`; lease_conflict: `执行状态发生变化，请查询原任务。`; all unknown codes: `研究已停止，请查看执行明细。` without rendering raw code in the primary text. Raw code appears only in details.
- [ ] Warning independently reflects ANY effectsPending, source/model pending or unknown/failed, sourceProgress UNKNOWN/FAILED, or resourceCloseout UNCERTAIN/overdue/DRAINING. Must remain visible even COMPLETED/CANCELED. Explain “尚有请求或执行记录待核实，不会自动重做；停止本页不代表撤回已发请求。” for uncertain/pending; failures explicitly say reading/analysis failure, not empty results. No automatic retry suggestion.
- [ ] Restructure existing render (preserve effects/run function): primary title+explanation, exact sourceLabel/table, `入库原文：… · 已分析：… · 已跳过：…`, count disclaimer, visible warning/nextStep. Use the existing Notice for warnings. Move existing permit counters, resource closeout snapshot text, pending settlement disclaimer and raw stopCode into:

```tsx
<details>
  <summary>执行明细</summary>
  {/* existing actual counters / closeout / stopCode, unchanged semantics */}
</details>
```

- [ ] Tests verify helper is pure, pending/unknown/failed risk not hidden behind success/cancel, unknown stopCode stays only in closed details, null vs zero, no inferred all-web capability, disclosure toggles without advance calls, candidate navigation and all existing serial-run/cancel/no-progress tests. Representative RED assertions:

```tsx
const summary = await screen.findByText('执行明细');
expect(summary.closest('details')?.open).toBe(false);
expect(screen.getByText(/来源许可/).closest('details')).toBe(summary.closest('details'));
expect(screen.getByText('已有请求的结果尚未核实。').closest('details')).toBeNull();
expect(advance).not.toHaveBeenCalled();
```

- [ ] GREEN: `npm --prefix desktop test -- tests/researchProgressPresentation.test.ts tests/ui/research-progress.test.tsx`; `npm --prefix desktop run typecheck`; `git diff --check`. No full suite or build.
- [ ] Commit only own four files. Report exact RED/GREEN and concerns. Root performs real browser rendering at wide/narrow viewport with labeled UI fixtures, checks keyboard summary expansion/risk visibility/no overflow; no fake backend or lead success claims. Independent review includes this whole task once.

## Evidence

Pending implementation. Backend remains fixed-source customer runtime; full V0.2 Goal remains ACTIVE.
