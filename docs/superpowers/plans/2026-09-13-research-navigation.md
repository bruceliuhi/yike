# Research navigation implementation plan

> **For agentic workers:** Use superpowers:executing-plans; one batch and one independent review per repository cost constraint.

**Goal:** Let customer research follow links from a successfully read public listing and retain budget for original evidence.

**Architecture:** Optional bounded links on existing READ evidence; existing three URL gates admit validated page links. Per-kind ceilings reserve at least one attempt for the other kind; the shared persistent source grant stays authoritative.

**Tech Stack:** Python HTMLParser, MCP, existing durable READ dispatcher and Codex worker.

## Global constraints

Follow the paired specification. No new providers, external sends, schema migration or desktop redesign. Old six-field evidence accepted. Links never establish demand.

## Task 1: Navigation and budget vertical slice

Files: pilot/open_web_reader_worker.py (visible anchors); pilot/open_web_reader.py (sanitize/validate optional links); pilot/public_read_session.py, pilot/research_tools.py, pilot/codex_research_worker.py (mission admission); pilot/dynamic_research_runtime.py (source allocation); tests/test_research_navigation.py (vertical regressions).

- [ ] RED: actual worker transport fixture HTML with relative, hidden, credential and duplicate anchors; assert result links retain original path case. Test parent sanitization separately.
- [ ] RED: real in-memory MCP using PublicReadSession and deterministic dispatcher reads searched listing then linked original, replays without reread and refuses undiscovered URL. Feed equivalent SEARCH/READ events to _ReadEvents.
- [ ] RED: per-kind ceilings `(searches, reads)` for 2/3/8/100 must be `(1,1)/(2,2)/(7,7)/(10,99)`. Test READ after2SEARCH then continue using total8, and7SEARCH then1READ; ninth action denied for either type.
- [ ] Implement optional `links: list[str]` bounded50. Sanitization uses `normalize_public_url`; validity requires canonical unique URLs, unknown fields still invalid. On READ success add only these validated URLs to each mission's admission set.
- [ ] Implement `_discovery_limits(sources)` returning `min(10,sources-1), sources-1`, call from runtime. Instructions describe navigation, buyer language, per-kind ceilings and shared total.
- [ ] Run `.venv/bin/python -m pytest tests/test_research_navigation.py -q` RED then GREEN, followed by affected reader/session/tools/worker/effect contracts only. Preserve failures before fixes.
- [ ] Commit and independent code/architecture/quality review exact SHA. Fix only findings, delta checks. Update taskbook and merge/push main, no duplicate desktop build.

## Evidence

Pending implementation; no success claim.
