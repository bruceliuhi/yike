import { describe, expect, it } from "vitest";
import { parseRawCandidateEvidence } from "../src/shared/rawCandidateEvidence";
import { rawEvidenceBinding, rawEvidenceFixture, rawObservationFixture } from "./fixtures/rawCandidateEvidence";

const invalid = "INVALID_RAW_CANDIDATE_EVIDENCE";
const otherId = "dddddddd-dddd-4ddd-8ddd-dddddddddddd";
type WireRecord = Record<string, unknown>;
function at(raw: unknown, path: string): WireRecord {
  return path.split(".").filter(Boolean).reduce((value, key) =>
    (value as WireRecord)[key], raw) as WireRecord;
}
function set(raw: unknown, path: string, value: unknown) {
  const keys = path.split("."), key = keys.pop()!;
  at(raw, keys.join("."))[key] = value;
}
function history(count: number, total = count) {
  const raw = rawEvidenceFixture();
  raw.observations.items = Array.from({ length: count }, (_, index) => ({
    ...rawObservationFixture(),
    observation_id: `eeeeeeee-eeee-4eee-8eee-${index.toString().padStart(12, "0")}`,
    request_id: `TEST.batch:${index}`,
  }));
  raw.observations.total = total;
  raw.observations.truncated = total > 100;
  return raw;
}

describe("raw candidate evidence boundary", () => {
  it("accepts the complete store response without rewriting untrusted original evidence", () => {
    const raw = rawEvidenceFixture();
    expect(parseRawCandidateEvidence(raw, rawEvidenceBinding)).toEqual(raw);
  });

  it("keeps unknown fields null, without title/body/author/time fallbacks", () => {
    const raw = rawEvidenceFixture();
    for (const content of [raw.candidate.current_version, raw.observations.items[0].content]) {
      content.title = null;
      content.author_public_id = null;
      content.parent = {
        external_comment_id: "parent-unknown", body: null, author_public_id: null,
        published_at: null, public_url: null,
      };
    }
    raw.candidate.external_source_id = null;
    raw.observations.items[0].query = null;
    expect(parseRawCandidateEvidence(raw, rawEvidenceBinding)).toEqual(raw);
  });

  it("keeps COMMENT container title, own author/body and parent attribution separate", () => {
    const raw = rawEvidenceFixture();
    const result = parseRawCandidateEvidence(raw, rawEvidenceBinding);
    expect(result).toEqual(raw);
    expect(result).not.toHaveProperty("buyer");
    expect(result).not.toHaveProperty("assessment");
    expect(result).toHaveProperty("candidate.status", "UNVERIFIED");
    expect(result).toHaveProperty("candidate.current_version.published_at", null);
    expect(result).toHaveProperty("observations.items.0.received_at", "2026-09-10T02:02:03.123456+00:00");
  });

  it.each(["POST", "PAGE"])("accepts %s evidence without COMMENT context", (kind) => {
    const raw = rawEvidenceFixture();
    raw.candidate.kind = kind;
    raw.candidate.external_comment_id = null;
    raw.candidate.current_version.parent = null;
    raw.observations.items[0].content.parent = null;
    expect(parseRawCandidateEvidence(raw, rawEvidenceBinding)).toEqual(raw);
  });

  const objectPaths = ["", "candidate", "candidate.current_version", "candidate.current_version.parent",
    "observations", "observations.items.0", "observations.items.0.content",
    "observations.items.0.content.parent", "observations.items.0.execution_context"];
  it.each(objectPaths)("rejects unknown keys at %s", (path) => {
    const raw = rawEvidenceFixture();
    at(raw, path).untrustedExtra = "must never be accepted";
    expect(() => parseRawCandidateEvidence(raw, rawEvidenceBinding)).toThrow(invalid);
  });
  for (const path of objectPaths) {
    it.each(Object.keys(at(rawEvidenceFixture(), path)))(`requires ${path || "envelope"}.%s even when nullable`, (key) => {
      const raw = rawEvidenceFixture();
      delete at(raw, path)[key];
      expect(() => parseRawCandidateEvidence(raw, rawEvidenceBinding)).toThrow(invalid);
    });
  }

  it.each([
    ["schema_version", "candidate-inbox-v2"], ["candidate", null],
    ["candidate.candidate_id", "not-a-uuid"], ["candidate.revision", "2"],
    ["candidate.revision", 0], ["candidate.revision", Number.MAX_SAFE_INTEGER + 1],
    ["candidate.ambiguous", "false"], ["candidate.status", "APPROVED"],
    ["candidate.kind", "BUYER"], ["candidate.source_identity", "not-a-hash"],
    ["candidate.current_version.content_version", "B".repeat(64)],
    ["candidate.current_version.body", null], ["candidate.current_version.title", ""],
    ["candidate.current_version.body", "\t\r\n"], ["candidate.current_version.body", "x\u0000"],
    ["candidate.current_version.body", "\uD800"], ["candidate.current_version.body", "🙂".repeat(20001)],
    ["candidate.current_version.public_url", "javascript:alert(1)"],
    ["candidate.current_version.public_url", "https://name:password@example.com"],
    ["candidate.current_version.public_url", " https://example.com"],
    ["candidate.current_version.published_at", "2026-02-30T00:00:00Z"],
    ["candidate.current_version.published_at", ""],
    ["candidate.current_version.published_at", "2026-09-09T00:00:00+00:00"],
    ["candidate.latest_observed_at", "not-a-time"],
    ["observations.items.0.observed_at", null], ["observations.items.0.received_at", 1],
    ["observations.items.0.record_index", -1], ["observations.items.0.record_index", 100],
    ["observations.items.0.query", ""], ["observations.items.0.collector_version", "bad version"],
    ["observations.items.0.execution_context.credential_version", true],
    ["observations.items.0.execution_context.execution_generation", 2147483648],
    ["observations.items.0.execution_context.access_mode", "ADMIN"],
    ["observations.items.0.execution_context.connection_version", 0],
    ["observations.items", null], ["observations.page_size", 20],
    ["observations.total", "1"], ["observations.total", 0], ["observations.truncated", true],
  ])("rejects malformed %s (%#)", (path, value) => {
    const raw = rawEvidenceFixture();
    set(raw, path as string, value);
    expect(() => parseRawCandidateEvidence(raw, rawEvidenceBinding)).toThrow(invalid);
  });

  it.each(Object.keys(rawEvidenceBinding))("binds expected %s exactly", (key) => {
    const expected = { ...rawEvidenceBinding, [key]: key === "candidateRevision" ? 3 : otherId };
    expect(() => parseRawCandidateEvidence(rawEvidenceFixture(), expected)).toThrow(invalid);
  });
  it.each([null, {}, { ...rawEvidenceBinding, profileVersion: 3 }, { ...rawEvidenceBinding, platform: "DOUYIN" },
    { ...rawEvidenceBinding, candidateRevision: "2" }])("rejects unverifiable or malformed expected binding %#", (expected) => {
    expect(() => parseRawCandidateEvidence(rawEvidenceFixture(), expected)).toThrow(invalid);
  });
  it("optionally binds the requested platform", () => {
    const raw = rawEvidenceFixture();
    expect(parseRawCandidateEvidence(raw, { ...rawEvidenceBinding, platform: "PUBLIC_WEB" })).toEqual(raw);
  });

  it("preserves maximum codepoint text and known publication time without replacing it", () => {
    const raw = rawEvidenceFixture();
    for (const content of [raw.candidate.current_version, raw.observations.items[0].content]) {
      content.title = "🙂".repeat(512);
      content.body = "🙂".repeat(20000);
      content.published_at = "2026-09-09T00:01:00Z";
    }
    expect(parseRawCandidateEvidence(raw, rawEvidenceBinding)).toEqual(raw);
  });

  it.each([
    ["published", "2026-09-10T02:00:00Z"],
    ["parent", "2026-09-10T02:00:00Z"],
    ["received", "2026-09-10T01:00:59.999999+00:00"],
  ])("rejects impossible %s chronology rather than repairing timestamps", (field, time) => {
    const raw = rawEvidenceFixture();
    if (field === "received") raw.observations.items[0].received_at = time;
    else for (const content of [raw.candidate.current_version, raw.observations.items[0].content]) {
      if (field === "published") content.published_at = time;
      else content.parent!.published_at = time;
    }
    expect(() => parseRawCandidateEvidence(raw, rawEvidenceBinding)).toThrow(invalid);
  });

  it("rejects a parent published after the candidate even when both precede observation", () => {
    const raw = rawEvidenceFixture();
    for (const content of [raw.candidate.current_version, raw.observations.items[0].content]) {
      content.published_at = "2026-09-09T00:00:00Z";
      content.parent!.published_at = "2026-09-09T00:00:01Z";
    }
    expect(() => parseRawCandidateEvidence(raw, rawEvidenceBinding)).toThrow(invalid);
  });

  it.each([
    ["observations.items.0.platform", "DOUYIN"],
    ["observations.items.0.profile_version_id", otherId],
    ["observations.items.0.strategy_version_id", otherId],
    ["observations.items.0.task_id", otherId], ["observations.items.0.run_id", otherId],
    ["observations.items.0.platform_run_id", otherId],
    ["observations.items.0.version_id", otherId],
    ["observations.items.0.content_version", "d".repeat(64)],
    ["observations.items.0.content.body", "other content"],
    ["observations.items.0.content.parent.author_public_id", "other parent"],
    ["observations.items.0.observed_at", "2026-09-10T01:02:00+00:00"],
    ["candidate.current_observation_id", otherId],
    ["candidate.kind", "POST"], ["candidate.external_comment_id", null],
    ["candidate.current_version.parent.external_comment_id", "comment-2"],
    ["observations.items.0.execution_context.connection_id", otherId],
    ["observations.items.0.execution_context.access_mode", "PLATFORM_ACCOUNT"],
  ])("rejects cross-version, attribution or immutable metadata mismatch at %s", (path, value) => {
    const raw = rawEvidenceFixture();
    set(raw, path, value);
    expect(() => parseRawCandidateEvidence(raw, rawEvidenceBinding)).toThrow(invalid);
  });

  it("preserves older original task and execution identity rather than applying current metadata", () => {
    const raw = rawEvidenceFixture(), old = rawObservationFixture();
    old.observation_id = otherId;
    old.version_id = "ffffffff-ffff-4fff-8fff-ffffffffffff";
    old.content_version = "e".repeat(64);
    old.content.body = "earlier source snapshot";
    old.observed_at = "2026-09-09T01:01:00+00:00";
    old.task_id = otherId;
    old.execution_context.task_id = otherId;
    old.execution_context.lease_id = otherId;
    old.execution_context.execution_generation = 1;
    raw.observations.items.push(old);
    raw.observations.total = 2;
    expect(parseRawCandidateEvidence(raw, rawEvidenceBinding)).toEqual(raw);
  });

  it("permits truncated same-time history to omit the current observation", () => {
    const raw = history(100, 101);
    expect(parseRawCandidateEvidence(raw, rawEvidenceBinding)).toEqual(raw);
  });
  it("does not assume the first equal-time observation is the current snapshot", () => {
    const raw = rawEvidenceFixture(), other = rawObservationFixture();
    other.observation_id = otherId;
    other.version_id = "ffffffff-ffff-4fff-8fff-ffffffffffff";
    other.content_version = "e".repeat(64);
    other.content.body = "conflicting same-time evidence";
    raw.candidate.ambiguous = true;
    raw.observations.items.unshift(other);
    raw.observations.total = 2;
    expect(parseRawCandidateEvidence(raw, rawEvidenceBinding)).toEqual(raw);
  });
  it.each([
    () => history(100, 100), () => history(99, 101), () => history(101, 101),
    () => history(1, 2), () => history(0, 0),
    () => { const raw = history(100, 101); raw.observations.truncated = false; return raw; },
    () => { const raw = rawEvidenceFixture(); raw.observations.items.push(rawObservationFixture()); raw.observations.total = 2; return raw; },
    () => { const raw = history(100, 101); raw.observations.items[0].content.body = "different bytes for same version"; return raw; },
  ])("rejects inconsistent history or snapshot %#", (fixture) => {
    expect(() => parseRawCandidateEvidence(fixture(), rawEvidenceBinding)).toThrow(invalid);
  });

  it("returns an independent immutable snapshot without mutating its input", () => {
    const raw = rawEvidenceFixture(), original = structuredClone(raw);
    const result = parseRawCandidateEvidence(raw, rawEvidenceBinding);
    expect(raw).toEqual(original);
    expect(result).not.toBe(raw);
    expect(Object.isFrozen(result)).toBe(true);
    expect(Object.isFrozen(at(result, "observations.items.0.execution_context"))).toBe(true);
    raw.observations.items[0].content.body = "changed after parsing";
    expect(result).toEqual(original);
  });
  it("throws only a fixed safe error with no original content or validation details", () => {
    const raw = rawEvidenceFixture();
    raw.candidate.status = "SECRET-RAW-CLAIM";
    try { parseRawCandidateEvidence(raw, rawEvidenceBinding); expect.fail("must reject"); }
    catch (error) { expect(error).toBeInstanceOf(Error); expect((error as Error).message).toBe(invalid); }
  });
});
