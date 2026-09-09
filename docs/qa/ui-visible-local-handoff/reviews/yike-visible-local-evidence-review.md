# Visible local handoff — independent evidence review

Repository HEAD checked: `d5ee8c27532ff15436eaa2bcfeafca1a9e0e86a0`; desktop product/build candidate: `8af8eafba0faef68ae48ea76f3d5d4a70c7b06c8`. Evidence read from `docs/qa/ui-visible-local-handoff/`. README was not yet present and browser visual QA was still in progress at review time.

**Artifact binding PASS; no product/packaging P0/P1 found.** The native records are compatible with the new package, but the current directory needs the small record completions below before it is described as a fully documented visible lifecycle. This is not an instruction to rerun that lifecycle or to rebuild.

## Independently verified

- `git diff 8af8eaf d5ee8c2 -- desktop` is empty.
- All 342 build-manifest paths exactly match the candidate's tracked desktop paths; each SHA-256 matches both its Git blob and the isolated build file under `/tmp/yike-visible-local-release-8af8eaf`.
- Actual app ASAR SHA-256: `98debe8e3c1e58e93e3da04209abc38d7773909ff4a3fb5ff317e7068c9fd067`.
- Actual ZIP SHA-256: `f580c225264db5cd23f9033e235ecf2f35e3a9e1fd3e682e19f78647033d8569`. ZIP CRC passes, with its sole embedded ASAR equal to the separate app.
- All 37 renderer hashes in the package-structure report match extraction from the actual ASAR. No raw-candidate or TEST visual-harness paths appear in the archive. Four untracked raw drafts were not modified or counted as features.
- `test-preview-build.json` contains all 37 current static files; actual directory path set and every hash agree. That bundle is isolated TEST, distinct from the production renderer. No CUA or browser request was made by this reviewer.
- Read-only `ps` during this review shows only PID 44236 among 15583, 41032 and 44236. PID 44236's executable and `lsof` open ASAR both resolve under `desktop/out/visible-local-8af8eaf/意客AI.app`. This corroborates current new-package identity and the earlier PIDs being absent now; it alone cannot reconstruct the historical quit button sequence.
- The build and strict-smoke logs complete successfully; exclusion reports zero harness manifest references. The compact-material targeted log reports 4 files / 33 passed. None of these tests/builds was rerun for this review.

## Existing visible records and what they actually prove

- Viewed both native screenshot files through view_image. The cold-start image visibly shows the workbench, approved logo/navigation and an unauthenticated/unconfigured-service state, not a failed renderer or fake customer success.
- `native-unsaved-prompt.txt` and its actual native dialog image show the unsaved/session-draft warning and both “继续编辑” and “放弃更改并关闭” choices.
- `native-saved-session-draft.txt` is a full AX tree showing `TEST 原生验收 8af8eaf`, “本机草稿 · 未启动”, and the Save button. It supports the saved local-session state; it does not prove a customer-space write or durable persistence across application shutdown.
- `native-restarted-workbench.txt` is a full workbench AX tree. `native-restarted-empty-task.txt` shows an empty task-name field and “尚未启动”, compatible with the documented session-draft clearing on quit.
- `native-cold-start.txt` is only a seven-line incremental AX diff, not a full initial tree. The separate full-window image still supports the displayed cold-start UI, but this text file must not be described as a complete first-start AX dump.
- Strict packaged smoke uses dialog substitutes. It remains separate from the actual native prompt above and must not substitute for the visible continue-edit/quit/restart narrative.

## Minimal record completions / misleading wording to avoid

1. **Chronology missing, not a demonstrated product defect.** Add one concise native lifecycle section linking the existing files and actual CUA sequence: cold start/new PID → input → close prompt → continue editing → local save → close/explicit discard → first new process exits → restart PID 44236 → workbench/empty task. Only include actions the root actually performed. Link the underlying tool observation or retained execution result for exit if available; the two booleans in `native-process-binding.json` are a summary, not a complete raw command log. Do not turn “empty after restart” into “saved session draft survived restart”. No rerun is required merely to add this truthful sequence.
2. **Screenshot extensions are wrong.** At inspection all five `screenshots/*.png` files are JPEG by magic bytes, independently confirmed by `file`/`sips`. Native workbench is 1080×768; native dialog 260×162; the P04 images are 1280×720. Preserve original bytes and rename to `.jpg`/update links, or clearly record actual JPEG MIME if retaining the names. Do not call them lossless PNGs, full-window dialog images, or infer a native CSS viewport from bitmap dimensions.
3. **Separate pre/post-compact browser images.** `p04-local-drafts-1280x720` and `p04-transfer-drawer-1280x720` predate the newly captured `p04-local-drafts-compact-1280x720` file. The root must bind each to its actual capture candidate/state and label any pre-fix picture as comparison evidence; modification time alone was not used here to invent a source SHA. The existing static build manifest proves the bundle, not which bundle a previously captured browser image used. Add actual screenshot route/state/browser/CSS-size observations in the coming README or a small capture manifest, rather than claiming all pictures are automatically 8af8eaf.

The current package summary correctly says Windows and actual service acceptance are separate. No stale lock-screen claim appears in the package fields; Mac is now visibly usable, but this review does not certify all P01–P20 states, Windows, native chooser, real login/platform/data operations or full product completion. Source and four raw drafts were left untouched; only this /tmp report was written.
