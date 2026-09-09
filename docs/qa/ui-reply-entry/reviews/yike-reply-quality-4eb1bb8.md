# Reply entry delivery quality audit

Candidate: `4eb1bb88b97d5f1d9ff3db569d80f9d9e79855b4`.

**Limited PASS. No P0/P1 delivery-evidence blocker found.** This permits committing the documented candidate and its evidence; it does not complete 05A or certify production, Windows, or visible native acceptance.

## Scope and independence

Read-only audit of `docs/qa/ui-reply-entry/README.md`, manifests, final and historical logs, five code/architecture reviews, both task/followup contracts, taskbook, integration status and `design-qa.md`. No product source changed, no tests/builds/browser/native lifecycle rerun. The reviewer authored the P05 template change, replies-only TEST fixture and the two contract updates; their implementation is not self-approved here. P05 relies on Peirce's independent dd09d0f review; root P14 relies on the final 4eb1bb8 code and architecture reviews. The independent P02 review is retained with its four-test scope.

## Independently checked bytes

- Both final test and build manifests contain exactly all 330 tracked desktop files at the candidate. Every input SHA matches `git show 4eb1bb8:path`; each isolated build input also matches the file in `/tmp/yike-reply-release-4eb1bb8`.
- The separate app and ZIP in `desktop/out/reply-entry-4eb1bb8/` exist. SHA-256 of app ASAR: `72b597705c7fde8a1bd80a5b3134c48373a453658dca0c8f87cc0fdf56056c99`.
- ZIP SHA-256: `c203b93e9212d0af93ddff3bdc8ac6fed17cf9cba2a606ed270ee24b357d99d7`. ZIP CRC passes; its sole embedded application ASAR equals the separate app's ASAR byte-for-byte.
- All 37 listed renderer assets match bytes extracted from the actual ASAR. Package main is `.vite/build/main.cjs`, version remains `0.2.0`.
- The four raw-candidate drafts are absent from the commit/input manifests; package path inspection found no raw-candidate or visual-harness/test fixture paths. Final production-exclusion log separately records zero manifest harness references and no failures.
- `git diff eb507bf 4eb1bb8 -- pilot deploy tests` is empty. This verifies retained remote-owned backend bytes, not ownership of their tests or new backend acceptance.
- Two large failed logs were losslessly compressed. Both compressed hashes/sizes and decompressed hashes/sizes match `compressed-logs.json`; decompressed contents equal the surviving `/tmp` originals. RED evidence has not been removed or rewritten.
- Checked 211 local links across the audited Markdown entries: no missing targets.
- The late-added TEST preview manifest binds 37 current static files; every listed file hash matches. Its source is 4eb1bb8, old build path is separately retained, build log finishes successfully, and the manifest reports HTTP 200 with `visibleAcceptance: false`. HTTP was not independently re-requested; no CUA or visible-flow result is inferred.

## Test and review evidence boundaries

The final full-suite log actually reports **108 passed files / 1 skipped; 1253 passed tests / 22 skipped**. This is read evidence from the candidate-bound invocation and inputs, not a new independent test run. The old full-suite log remains **1248/22** and is identified as the pre-final ffd1248 merge snapshot. The earlier 53d506b 70-test flow result and 21-test architecture result are not used to cover the subsequently discovered late-date filter issue; the final 4eb1bb8 review, RED counterexample and **7 files / 75 tests** GREEN report cover that change. Counts are not added across overlapping suites.

Final make output completes the darwin/arm64 ZIP. The strict packaged-smoke log reports main/preload/renderer and fixed IPC checks, controlled temporary export writes and substituted-dialog quit checks. These are correctly distinguished from a human-operated native chooser and actual visible lifecycle. The final typecheck log is empty stdout; no diagnostic is present, but the empty file alone is not treated as independent exit-code evidence. Producer reports record successful typecheck. Secret-scan log records clean.

The five reviews preserve authorship, candidate and narrow follow-up coverage. Contracts describe manual research/execution-limit whitelisting without inherited quote/authorization/request/provenance, exact reply target verification independent of manual rows, independent channel/manual errors, no error fallback to unmatched, and add/save/cancel target/tab preservation. Existing operation locks and legacy facade boundaries remain explicit. Taskbook and integration state remain IN_PROGRESS rather than converting documentation or fixture completion into actual service completion.

## Acceptance still open

- Mac was locked; this candidate has no new visible browser flow, native cold-start/quit/restart or same-state visual acceptance. No unlock bypass is claimed. Existing images retain their original candidate/state scope.
- The replies-only fixture and static preview are isolated TEST preparation. They do not prove real replies, platform authorization, external sending, customer writes or a connected structured FollowupService. Backend ownership/evidence from the merged branch is not counted as work performed by this UI slice.
- Windows real-machine scaling, installation/lifecycle and evidence return, signing/notarization, and actual production-service acceptance remain open.

The current README, contracts and overall status accurately retain these limits. There is no evidence-based reason to block committing this candidate and QA bundle, and there is no basis to declare the complete frontend Goal finished.
