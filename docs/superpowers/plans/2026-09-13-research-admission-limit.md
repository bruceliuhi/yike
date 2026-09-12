# Research admission limit recovery

## Observed failure and scope

Real new task at `5e3f88a`: 6 SEARCH + 2 READ + 4 MODEL succeeded, then STOPPED/runtime_failed with zero accepted/analyzed and two unpublished originals. Both read threads were from 2025, not current qualified opportunities. Source allowance 8/8 was exhausted; the next source admission failed, then the next model call failed locally. Raw diagnostic evidence remains `/tmp/yike-buyer-diagnostic-20260913.json` (not customer/production evidence). No ordinary assessment ran; previous assessment diagnostics do not diagnose this failure.

Code tracing shows DurableResearchDispatcher closes on every begin exception. Restricted-PG reproduction consumes its actual source allowance, denies additional source work without issuing records, then incorrectly rejects a still-permitted MODEL. Initial regression: 1 failed / 1 passed (cancellation control), 8.04s. This confirms the failure mechanism, not a replay of the original task.

## Minimal approved-scope correction

Only the trusted journal `begin` error `resource_limit_exceeded` is a nonfatal, pre-permit rejection. Reuse that unissued sequence; subsequent work must pass all normal authority, context, deadline, generation, prior receipt and resource checks. It does not retry any issued effect, increase limits, refund usage, claim completion, or continue on cancellation/unknown/IO/ACK failure. No database migration, customer protocol or platform permission change.

Tests cover repeated denial with no extra records or network work, subsequent MODEL with contiguous sequence, cancellation after denial, and the same error during perform/finish remaining fatal. Existing journal and dispatcher cases cover lost acknowledgments, mismatches and unknown receipts.

## Remaining product work

This fixes an unnecessary shutdown, not research quality. Skill rules are already loaded; observed searches still over-select vendor/old results. Native recent-source pivots, selective buyer-candidate publishing, informative limit feedback, real completed research, platform depth and full V0.2 deployment/customer gates remain. No new real provider run, outbound, deployment or desktop build is authorized by this evidence record.
