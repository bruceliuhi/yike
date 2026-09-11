# Ordinary-client controlled research path

Authorized V0.2 technical refinement; full multi-platform goal remains. Deliver one coherent ordinary-client path, not another standalone backend primitive: confirm strategy/quote → signed durable research START → bounded advancement → visible progress and original candidate results → cancel/recover.

## Honest scope

The implemented source adapter is only `PUBLIC_WEB / V2EX_LATEST_INDEX`, displayed as “V2EX最新主题 · 公开单源研究”. This is not full-web keyword search or full V0.2. Keep ordinary social-platform collection unchanged. Research capability is advertised only when explicitly configured with a validated rule, signing secret, bounded model, source adapter and all services. No default rule/pricing, balances, paid enabling, external sends or production deployment. Missing capability remains 501; actualSoubei=null and settlementState=PENDING are honest, not zero consumption or completed billing.

## Native START and recovery

Extend the current authenticated main controller/session and encrypted journal. Persist the exact execution START plus nonsecret ResearchReservationBinding before prepare/sign/POST. Store the quote token only in invocation memory, never journal/localStorage/logs. Use existing researchExecution.start/receipt transport and parseResearchStartReceipt. No research request can fall back to ordinary execution.apply. Existing journal formats/readers stay compatible; research records have explicit version/type and exact bindings. Restart supports read-only recovery without token. 404 is not authorization to replace an old quote or resubmit; fresh estimate/confirmation must use a new request only after an authoritative no-start disposition. Unknown originals remain protected and visible.

Use a dedicated research command/result union on the existing execution IPC: RESEARCH_START, RESEARCH_RECOVER, RESEARCH_LIST; do not disturb ordinary START/CANCEL/LIST. Main resolves user/session/device, renderer supplies only confirmed strategy/targets, quote binding/token and humanConfirmed. Return RESEARCH_RECORDED with the full strict research receipt, UNKNOWN with original requestId, or fixed failure/session states. Token-bearing START never appears in LIST. Native service exposes researchContractVersion=1 only for this implemented protocol; server capability remains separately checked.

## Execution and status

Reuse existing ResearchOrchestrator stable source/review IDs and CandidateReviewStore, including final post-permit disclosure check. Each authenticated advance performs at most one fresh external effect (source read OR model assessment); cached history does not consume this allowance. Normal GET status only reads persisted state/events/receipts; polling never starts work. Client advances sequentially after authoritative status, and on timeout/UNKNOWN reads status before deciding the next action. Never synthesize retries for UNKNOWN/FAILED source/model requests.

Persist research coordinator ownership and progress per tenant/owner/task/run, with lease/generation fencing around each bounded advance. No transaction spans I/O. Admission checks existing task/run ownership/current permissions; resource permits remain final authority. Active lease returns RUNNING without a second worker; expired lease recovery checks original effects and does not blindly restart them. Terminal commit is bound to current generation, cancellation and durable evidence; use an internal research completion path, never ordinary FINISH. COMPLETED means sequence completed, not qualified leads or settled billing. All accepted originals may still be UNVERIFIED/PENDING_REVIEW. Cancellation blocks new work; pending/unknown effects remain visible and are not represented as rolled back or refunded.

## Shared wire contract (camelCase)

GET `/api/ui/research-execution/capability` returns `{contractVersion:1, sourceScope:'V2EX_LATEST_INDEX', sourceLabel:'V2EX最新主题 · 公开单源研究', maxFreshEffectsPerAdvance:1, settlementState:'PENDING'}` when available; otherwise501.

GET `/api/ui/research-execution/tasks/{taskId}` and POST `/api/ui/research-execution/tasks/{taskId}/advance` (strict JSON `{runId}`) return:

```
{contractVersion:1, taskId, runId,
 phase:'QUEUED'|'RUNNING'|'STOPPED'|'CANCELED'|'COMPLETED',
 sourceScope:'V2EX_LATEST_INDEX', sourceLabel:'V2EX最新主题 · 公开单源研究',
 acceptedOriginals:number|null, analyzedOriginals:number, skippedOriginals:number,
 candidateIds:string[], canAdvance:boolean, stopCode:string|null,
 newActionsBlocked:boolean, effectsPending:boolean,
 usage:{sourceReads:{issued,pending,succeeded,failed,unknown},
        modelCalls:{issued,pending,succeeded,failed,unknown},
        actualSoubei:null, settlementState:'PENDING'}}
```

IDs canonical UUID; counts nonnegative ints, candidateIds distinct≤100, analyzed+skipped≤accepted when known; issued=sum(other four statuses). Source/assessment counts are not opportunity counts. GET query parameters and POST extra/body identity fields are rejected. Authentication/HTTPS/no-store/fixed errors follow existing research API. Use application RLS, no admin runtime DB. Migration137 reserved here (136 belongs to independent SMS/trial task).

## Ordinary interface

Reuse TaskWizard current strategy/estimate/confirmation and current task details + candidate review. Remove old research blockers only for the actual native protocol plus available backend source capability and fresh quote; reject unsupported multi-platform/research-monitor combinations explicitly. Preserve existing ordinary/monitor paths. Show starting UNKNOWN separately from execution STOPPED/unknown effects, source scope label, raw counts and unsettled usage. Offer original-request recovery, run/continue, signed cancel, and existing task-filtered candidate entry. No new visual redesign, CRM, or extra model-generated capability claims.

## Verification and remaining gates

TDD the new protocol/state boundaries, dedicated restricted PG lifecycle and actual HTTP, one integrated ordinary-client/renderer flow with source/model doubles explicitly labeled. Reuse unchanged evidence, one whole-batch independent review, only corrective delta checks. If real model credentials are unavailable, report that limit rather than claiming true model quality. Windows, actual sources/models/customer UAT and production remain required for full goal; this slice does not close them.
