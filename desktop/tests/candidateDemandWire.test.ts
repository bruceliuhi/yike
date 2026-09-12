import { readFileSync } from "node:fs";
import { expect, it } from "vitest";
import { parseCandidatePage, parseCandidateReviewResult } from "../src/shared/candidateReviewApi";
import { parseOpportunitySourceEvidence } from "../src/renderer/domain/opportunitySourceEvidence";

// Produced by the real restricted-PG HTTP test with explicitly synthetic source/model input.
// Opt in to cross-language verification; absence is not evidence of an integration pass.
const wirePath = process.env.YIKE_DEMAND_WIRE_PATH;
it.skipIf(!wirePath)("accepts actual Python HTTP receipts in the shipped TS parsers", () => {
  const wire = JSON.parse(readFileSync(wirePath!, "utf8"));
  expect(wire.synthetic).toBe(true);
  for (const key of ["check", "assessed", "decision"]) {
    expect(parseCandidateReviewResult(wire[key], {requestId: wire[key].requestId})).toEqual(wire[key]);
  }
  const page = {items: [wire.current], total: 1, page: 1, pageSize: 20};
  expect(parseCandidatePage(page).items[0]).toEqual(wire.current);
  expect(wire.current.publishedAt).toBe("");
  const snapshot = wire.source_evidence.snapshot;
  expect(parseOpportunitySourceEvidence(wire.source_evidence, {
    opportunityId: snapshot.opportunity_id,
    profileVersionId: snapshot.assessment.profile_version_id,
  })).toEqual(wire.source_evidence);
  expect(snapshot.source.published_at).toBeNull();
  expect(snapshot.source.author_updates).toEqual([wire.check.demandEvidence.demandExcerpt]);
  expect(wire.assessed.assessment.demandEvidenceId).toBe(wire.check.id);
});
