import { afterEach, expect, it, vi } from "vitest";
import { configuredService, createServiceClient } from "../../src/main/serviceClient";
import { service } from "../../src/renderer/services/client";
import { candidateBindingSchema, type CandidateReviewRequest } from "../../src/shared/candidateReviewApi";

const names = ["BASE", "TOKEN", "STRANGER_TOKEN", "PEER_TOKEN", "BINDING_JSON", "TIMES_JSON", "MODE"] as const;
const enabled = names.some(name => Boolean(process.env[`YIKE_CANDIDATE_LIVE_${name}`]));
afterEach(() => vi.unstubAllGlobals());

// The Python parent alone provisions the loopback HTTP server and restricted PG.
// Only platform/model inputs are synthetic; no response or business store is mocked.
it.skipIf(!enabled)("consumes actual candidate review HTTP receipts and fixed original evidence", async () => {
  expect(process.versions.node.split(".")[0]).toBe("24");
  const values = Object.fromEntries(names.map(name => [name, process.env[`YIKE_CANDIDATE_LIVE_${name}`]]));
  expect(Object.values(values).every(Boolean)).toBe(true);
  expect(Object.keys(process.env).filter(name => /DATABASE|^POSTGRES_/i.test(name))).toEqual([]);
  const base = values.BASE!;
  expect(new URL(base).hostname).toBe("127.0.0.1");
  const baseUrl = configuredService(base, { packaged: false, allowLoopbackHttp: true });
  expect(baseUrl).toBe(base);
  const binding = candidateBindingSchema.parse(JSON.parse(values.BINDING_JSON!));
  expect(["flow", "prepare", "stale"]).toContain(values.MODE);

  const actualFetch = globalThis.fetch;
  let cookie = "";
  let loseNextInclude = false;
  const calls: { method: string; path: string; action?: string; requestId?: string }[] = [];
  const client = createServiceClient({
    baseUrl,
    clearSession: async () => { cookie = ""; },
    fetch: async (url, options) => {
      expect(new URL(url).origin).toBe(base);
      const payload = typeof options.body === "string" ? JSON.parse(options.body) : {};
      calls.push({ method: options.method!, path: new URL(url).pathname,
        ...(payload.action ? { action: payload.action, requestId: payload.requestId } : {}) });
      const headers = new Headers(options.headers);
      if (cookie) headers.set("Cookie", cookie);
      const response = await actualFetch(url, { ...options, headers });
      const session = response.headers.getSetCookie().find(value => value.startsWith("pilot_session="));
      if (session) cookie = session.split(";", 1)[0];
      expect(response.headers.get("cache-control")).toBe("no-store");
      if (loseNextInclude && payload.action === "INCLUDE" && response.ok) {
        loseNextInclude = false;
        await response.arrayBuffer(); // Server committed; discard its real response at the network boundary.
        throw new TypeError("synthetic response loss after server commit");
      }
      return response;
    },
  });
  vi.stubGlobal("window", { yikeDesktop: { requestApi: client.request } });
  const api = service.candidateReview!;
  expect(api).toBeDefined();
  expect((await service.loginToken(values.TOKEN!)).authenticated).toBe(true);

  const page = await api.list({ ids: [binding.candidateId], page: 1, pageSize: 1 });
  expect(page.total).toBe(1);
  const candidate = page.items[0];
  expect(candidate.id).toBe(binding.candidateId);
  const rawBinding = { candidateId: binding.candidateId, candidateRevision: binding.candidateRevision,
    sourceVersionId: binding.sourceVersionId, profileId: binding.profileId,
    strategyVersionId: candidate.strategyVersionId };
  const verifyInput = { ...binding, requestId: crypto.randomUUID(), humanConfirmed: true as const,
    status: "OPEN" as const, openingMethod: "DIRECT" as const,
    locator: "https://example.com/synthetic", excerpt: "采购输送设备", contactMethod: "COMMENT" as const };

  if (values.MODE === "stale") {
    const previous = JSON.parse(process.env.YIKE_CANDIDATE_LIVE_EXPECTED_JSON!);
    expect(previous.binding).toEqual(binding);
    expect(candidate.currentBindingValid === false || candidate.revision !== binding.candidateRevision ||
      candidate.sourceVersionId !== binding.sourceVersionId).toBe(true);
    const request = { ...binding, requestId: crypto.randomUUID(), action: "INCLUDE" as const,
      assessmentId: previous.assessmentId, sourceVerificationId: previous.sourceVerificationId,
      evidence: previous.evidence, reason: "", humanConfirmed: true };
    await expect(api.review(request)).rejects.toMatchObject({ status: 409 });
    await expect(api.verifySource(verifyInput)).rejects.toMatchObject({ status: 409 });
    expect(calls.filter(call => call.action === "ASSESS")).toHaveLength(0);
    console.log("CANDIDATE_LIVE_RESULT:" + JSON.stringify({ ...previous, staleRejected: true }));
    return;
  }

  expect(candidate).toMatchObject({ revision: binding.candidateRevision, sourceVersionId: binding.sourceVersionId,
    profileId: binding.profileId, profileVersion: binding.profileVersion, currentBindingValid: true,
    historical: false, status: "PENDING_REVIEW" });
  const raw = await api.getRawEvidence(rawBinding);
  const times = JSON.parse(values.TIMES_JSON!);
  const instant = (value: string) => new Date(value).getTime();
  expect(instant(times.publishedAt)).toBeLessThan(instant(times.observedAt));
  expect(instant(raw.candidate.current_version.published_at!)).toBe(instant(times.publishedAt));
  const observation = raw.observations.items.find(item => item.observation_id === raw.candidate.current_observation_id)!;
  expect(observation).toBeDefined();
  expect(instant(observation.observed_at)).toBe(instant(times.observedAt));
  expect(instant(observation.received_at)).toBeGreaterThan(instant(observation.observed_at));
  expect(raw.candidate.current_version.body).toBe("我们工厂想采购输送设备，月底前找团队报价。");
  expect(raw.candidate.kind).toBe("COMMENT");
  expect(raw.candidate.current_version.parent?.body).toBe("父评论  原文");
  expect(raw.candidate.current_version.parent?.published_at).toBeNull();
  const assessRequest = { ...binding, requestId: crypto.randomUUID(), action: "ASSESS" as const };
  const assessed = await api.review(assessRequest);
  expect(assessed.kind).toBe("assessment");
  if (assessed.kind !== "assessment") throw new Error("real assessment receipt required");
  expect(assessed.assessment.sendingAuthorized).toBe(false);
  expect(assessed.assessment.strategyVersionId).toBe(candidate.strategyVersionId);
  expect(assessed.assessment.intent.citations).toContainEqual({ field: "body", quote: "采购输送设备" });
  expect(assessed.assessment.draftComment).not.toBe(assessed.assessment.draftDm);
  const verified = await api.verifySource(verifyInput);
  expect(verified.binding).toEqual(binding);
  expect(verified).toMatchObject({ requestId: verifyInput.requestId, status: "OPEN", excerpt: "采购输送设备" });
  const prepared = { binding, assessmentId: assessed.assessment.id, sourceVerificationId: verified.id,
    evidence: assessed.assessment.evidence, rawVersionId: raw.candidate.current_version.version_id };
  if (values.MODE === "prepare") {
    expect(calls.filter(call => call.action === "INCLUDE")).toHaveLength(0);
    console.log("CANDIDATE_LIVE_RESULT:" + JSON.stringify(prepared));
    return;
  }

  const decision: CandidateReviewRequest = { ...binding, requestId: crypto.randomUUID(), action: "INCLUDE",
    assessmentId: prepared.assessmentId, sourceVerificationId: verified.id,
    evidence: prepared.evidence, reason: "", humanConfirmed: true };
  loseNextInclude = true;
  await expect(api.review(decision)).rejects.toMatchObject({ status: 0 });
  expect(calls.filter(call => call.action === "INCLUDE")).toHaveLength(1);
  const recovered = await api.getRequest(decision.requestId, { request: decision });
  expect(calls.filter(call => call.action === "INCLUDE")).toHaveLength(1);
  expect(recovered.kind).toBe("decision");
  if (recovered.kind !== "decision") throw new Error("persisted decision required");
  expect(recovered.receipt).toMatchObject({ requestId: decision.requestId, outcome: "IMPORTED",
    review: { sourceVerificationId: verified.id, sourceVersionId: binding.sourceVersionId } });
  const opportunityId = recovered.receipt.opportunityId!;
  expect(await api.review(decision)).toEqual(recovered); // Explicit same-ID replay, not automatic recovery retry.
  const duplicate = await api.review({ ...decision, requestId: crypto.randomUUID() });
  expect(duplicate.kind).toBe("decision");
  if (duplicate.kind !== "decision") throw new Error("duplicate receipt required");
  expect(duplicate.receipt).toMatchObject({ outcome: "ALREADY_IMPORTED", opportunityId,
    review: { sourceVerificationId: verified.id } });
  const historical = await api.list({ ids: [binding.candidateId], reviewRequestId: decision.requestId, page: 1, pageSize: 1 });
  expect(historical.items[0]).toMatchObject({ historical: true, opportunityId });

  const opportunity = await service.opportunity(opportunityId);
  expect(opportunity.sourceEvidence?.status).toBe("CAPTURED");
  if (opportunity.sourceEvidence?.status !== "CAPTURED") throw new Error("fixed evidence required");
  const fixed = opportunity.sourceEvidence.snapshot;
  expect(fixed.source).toMatchObject({ kind: "COMMENT", title: null, container_title: "食品工厂扩产",
    version_id: binding.sourceVersionId, body: raw.candidate.current_version.body,
    parent: raw.candidate.current_version.parent });
  expect(fixed.assessment.id).toBe(prepared.assessmentId);
  expect(instant(fixed.source.published_at!)).toBe(instant(times.publishedAt));
  expect(fixed.observation.id).toBe(raw.candidate.current_observation_id);
  expect(instant(fixed.observation.observed_at)).toBe(instant(observation.observed_at));
  expect(instant(fixed.observation.received_at)).toBe(instant(observation.received_at));
  expect(fixed.verification).toMatchObject({ status_at_capture: "OPEN", contact_method: "COMMENT" });
  expect(fixed.assessment.citations).toContainEqual({ dimension: "intent", field: "source.body", quote: "采购输送设备" });
  expect(fixed.assessment.citations).toContainEqual({ dimension: "businessMatch", field: "source.parent.body", quote: "父评论  原文" });
  expect(calls.filter(call => call.action === "ASSESS")).toHaveLength(1);

  await service.logout();
  expect(cookie).toBe("");
  await expect(api.list()).rejects.toMatchObject({ status: 401 });
  await expect(api.review(decision)).rejects.toMatchObject({ status: 401 });
  await expect(api.getRequest(decision.requestId)).rejects.toMatchObject({ status: 401 });
  for (const token of [values.PEER_TOKEN!, values.STRANGER_TOKEN!]) {
    expect((await service.loginToken(token)).authenticated).toBe(true);
    expect((await api.list({ ids: [binding.candidateId] })).items).toEqual([]);
    await expect(api.getRawEvidence(rawBinding)).rejects.toMatchObject({ status: 404 });
    await expect(api.getRequest(decision.requestId)).rejects.toMatchObject({ status: 404 });
    // The write contract resolves tenant-visible profile before private candidate scope.
    const deniedWrite = token === values.STRANGER_TOKEN
      ? { status: 409, code: "profile_unavailable" }
      : { status: 404, code: "candidate_not_found" };
    await expect(api.review({ ...decision, requestId: crypto.randomUUID() })).rejects.toMatchObject(deniedWrite);
    await expect(api.verifySource({ ...verifyInput, requestId: crypto.randomUUID() })).rejects.toMatchObject(deniedWrite);
    if (token === values.STRANGER_TOKEN) await expect(service.opportunity(opportunityId)).rejects.toMatchObject({ status: 404 });
    else expect((await service.opportunity(opportunityId)).sourceEvidence).toEqual(opportunity.sourceEvidence);
    await service.logout();
  }
  console.log("CANDIDATE_LIVE_RESULT:" + JSON.stringify({ ...prepared, opportunityId, decisionRequestId: decision.requestId }));
}, 45_000);
