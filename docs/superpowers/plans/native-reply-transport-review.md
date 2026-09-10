# Native reply transport independent review

## Verdict

GO for the bounded implementation slice `4f61f26..53990d6f1b4adb419c1fdf19f43b32aec8e26a3e`. No actionable P1/P2 findings from this independent static review. This is not a product, real-platform, or Windows acceptance verdict.

## Reviewed boundaries

- Python external READ_REPLIES and unique internal readReplies operations remain distinct from EXECUTE; strict shapes and the existing single post-READY operation fence prevent mixed/repeated actions. Worker reads do not call execute.
- Input budgets remain 128 KiB; larger bounded output is enabled only in read mode. EOF/cancellation retain the existing owner-task and supervised process cleanup path.
- The Node driver binds the original CHECK context, makes read/send mutually exclusive, validates batch author/IDs/times/duplicates/count, and returns replies only after successful physical host close and cleanup confirmation. UNKNOWN/failure is not converted into an empty successful read.
- New service operations use fixed private routes, not the renderer API allowlist. Signing checks canonical bytes, the complete expected request, reply protocol domain, user/tenant/event ownership and the existing service/user/device-scoped Ed25519 primitive.

## Evidence and limits

Reviewed the complete frozen diff, implementation plan and relevant lifecycle, signing and service context. No tests, build, platform actions or implementation edits were performed by this reviewer.

Implementer-supplied evidence: Python affected tests 35 PASS; initial Node set 23 PASS and one test-fixture defect, followed by the corrected affected set 9 PASS; TypeScript check PASS. These sets overlap and are not summed. Synthetic tests do not establish platform access or Windows behavior.

Main identity/profile assembly, customer UI synchronization, real-platform checks and Windows acceptance are explicitly the next slice, not delivered here. Customer reply sync must remain unavailable until that chain is assembled and verified.
