# Research navigation implementation plan

> **For agentic workers:** Use superpowers:executing-plans; one batch and one independent review per repository cost constraint.

**Goal:** Let customer research follow links from a successfully read public listing and retain budget for original evidence.

**Architecture:** Optional bounded links on existing READ evidence; existing three URL gates admit validated page links. Per-kind ceilings reserve at least one attempt for the other kind; the shared persistent source grant stays authoritative.

**Tech Stack:** Python HTMLParser, MCP, existing durable READ dispatcher and Codex worker.

## Global constraints

Follow the paired specification. No new providers, external sends, schema migration or desktop redesign. Old six-field evidence accepted. Links never establish demand.

## Task 1: Navigation and budget vertical slice

Files: pilot/open_web_reader_worker.py (visible anchors); pilot/open_web_reader.py (sanitize/validate optional links); pilot/public_read_session.py, pilot/research_tools.py, pilot/codex_research_worker.py (mission admission); pilot/dynamic_research_runtime.py (source allocation); tests/test_research_navigation.py (vertical regressions).

- [x] RED: actual worker transport fixture HTML with relative, hidden, credential and duplicate anchors; assert result links retain original path case. Test parent sanitization separately.
- [x] RED: real in-memory MCP using PublicReadSession and deterministic dispatcher reads searched listing then linked original, replays without reread and refuses undiscovered URL. Feed equivalent SEARCH/READ events to _ReadEvents.
- [x] RED: per-kind ceilings `(searches, reads)` for 2/3/8/100 must be `(1,1)/(2,2)/(7,7)/(10,99)`. Test READ after2SEARCH then continue using total8, and7SEARCH then1READ; ninth action denied for either type.
- [x] Implement optional `links: list[str]` bounded50. Sanitization uses `normalize_public_url`; validity requires canonical unique URLs, unknown fields still invalid. On READ success add only these validated URLs to each mission's admission set.
- [x] Implement `_discovery_limits(sources)` returning `min(10,sources-1), sources-1`, call from runtime. Instructions describe navigation, buyer language, per-kind ceilings and shared total.
- [x] Run `.venv/bin/python -m pytest tests/test_research_navigation.py -q` RED then GREEN, followed by affected reader/session/tools/worker/effect contracts only. Preserve failures before fixes.
- [x] Independent delta review PASS at d6b6b17; batch prepared for main integration. No duplicate desktop build.

## Evidence

Code `a4d663e` navigation; revised budget `d6b6b17`. Initial synthetic RED8failed/1passed, affected reader/session/MCP/worker/effect contracts212passed23.71s. Independent navigation review found no P1/P2 in that portion; actual DurableResearchDispatcher with synthetic journal confirmed linked READ persistence/replay and ACK loss/deadline/close denial. These are not customer PG/platform acceptance.

Independent review of the actual run rejected the initial fixed one-third search budget (P2): sources8 allowed2search, stranded5unused source slots after one READ and prevented community correction queries. New regression RED4failed/6passed reproduced this restriction; changed only ceilings/docs, final navigation+worker70passed20.63s, including2SEARCH→1READ→remaining searches and7SEARCH→1READ, ninth action rejected. Shared persistent total unchanged. Independent delta review at d6b6b17496be88c13c247420cd7ebebc810f9423: Spec/Quality PASS, P2 CLOSED, READY_TO_MERGE; independent11passed0.44s and shared persistent permission implementation checked. These new exhaustion tests use a bounded synthetic dispatcher, not a new PG exhaustion measurement. Local review report `/tmp/yike-navigation-review.md`.

### Actual public evidence (a4d663e, 2026-09-13 China time)

- Actual reader read `https://www.v2ex.com/go/outsourcing` at2026-09-12T21:49:39Z,1876chars,48sanitized links; opened returned `https://www.v2ex.com/t/1241570` at21:50:17Z,610chars, SHA19029d5c966d707f7a4b513a783ab2341c19538c030805365536a457b1bfb75b. Supplier advertising, EXCLUDE. This proves reader list→link extraction and target read, not complete customer navigation or buyer supply.
- New synthetic customer/price/device/auth, actual Codex/Ark/Serper/reader, ordinary assessment and restricted-PG in-process HTTP run0c069d6f-9d27-4a74-a6ff-37a018fa0bd9, task760a6104-4481-4d8b-b425-2c33980e53d2. Same broad profile as previous run, no supplied answer URL. Record `/tmp/yike-navigation-live-20260913.json`;72.29s.2SEARCH/1READ/4researchMODEL succeeded, research mission COMPLETED, candidate1persisted. Read `https://www.kaiyan.net/blog/enterprise-knowledge-base-pricing-and-roi/`,6828chars/38links. It is a vendor pricing article, not a buyer; qualified new opportunities0.
- Subsequent ordinary assessment UNKNOWN; final STOPPED/effect_unknown, analyzed0, total model actions5 with1unknown, settlementPENDING. Research model input51978/output849, cached22128; not a low-cost or commercial success. No raw assessment failure diagnostic was preserved; do not guess timeout or claim this batch fixes it. The old unknown operation was not retried.
- The real run belongs to a4d663e before the budget correction. d6b6b17 has targeted regression only; no attribution of old platform/model results to new bytes, no same-condition quality superiority claim. Owned PostgreSQL container yike-navigation-pg-20260913 stopped after terminal run; no shared services touched.

Next: improve actual buyer-source selection rather than feeding generic supplier articles into ordinary assessment, retain safe diagnostics for the still-unresolved assessment failure, and validate normal-profile research/authorized-comment depth. No sends, deployment, desktop package or customer UAT in this batch. Full Goal ACTIVE.
