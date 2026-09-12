import { ServiceError, type YikeService } from "../../src/renderer/services/contracts";
import { EMPTY_PROFILE } from "../../src/renderer/domain/models";
import { createCandidateReviewService, CANDIDATE_PLATFORM_LABELS } from "../../src/renderer/services/candidateReview";
import {
  candidateQuerySchema, candidateReviewRequestSchema, sourceVerificationRequestSchema,
  parseCandidatePage, parseCandidateReviewResult,
  type CandidateReviewResultDto,
} from "../../src/shared/candidateReviewApi";
import { assessmentFixture, candidateBinding, candidateFixture, opportunityId } from "../fixtures/candidateReviewApi";
import { rawEvidenceFixture } from "../fixtures/rawCandidateEvidence";

/** TEST memory transport only; no API/IPC/network escape and no production imports of this addon. */
export function configureCandidateReviewVisual(
  service: YikeService, params: URLSearchParams,
  record: (operation: string, detail?: string) => void,
): boolean {
  if (!params.has("candidateReview")) return false;
  const mode = params.get("candidateReview");
  if (!mode || !["live", "recovery", "raw-error", "dynamic"].includes(mode)
    || params.get("scenario") !== "P07" || (params.has("state") && params.get("state") !== "populated")
    || [...params.keys()].some(key => !["scenario", "candidateReview", "state"].includes(key) || params.getAll(key).length !== 1))
    throw new Error("TEST 候选场景仅接受 scenario=P07、candidateReview=live/recovery/raw-error/dynamic 与可选 state=populated。");

  const createdAt = new Date().toISOString();
  const raw = rawEvidenceFixture();
  const content: typeof raw.candidate.current_version = {
    ...raw.candidate.current_version,
    title: "TEST 原帖标题，不是评论人的采购意向",
    author_public_id: "TEST 评论作者",
    body: "TEST 合成评论：采购输送设备，需要报价。\n  原文保留空格🙂",
    published_at: "2026-09-09T08:00:00Z",
  };
  if (mode === "dynamic") {
    Object.assign(raw.candidate,{kind:"PAGE",external_source_id:null,external_comment_id:null});
    Object.assign(content,{title:"TEST 混合网页，需要确认发言人",author_public_id:null,parent:null,published_at:null,
      body:"TEST采购人，第2楼 · TEST原文日期\n采购输送设备，需要报价。\nTEST第三方：我已经找到供应商。"});
  }
  raw.candidate.current_version = content;
  raw.candidate.latest_observed_at = "2026-09-09T09:00:00Z";
  const { version_id: _version, content_version: _hash, ...observedContent } = content;
  raw.observations.items[0] = { ...raw.observations.items[0], content: observedContent,
    observed_at: raw.candidate.latest_observed_at, received_at: "2026-09-09T09:00:01Z", query: "TEST 设备采购",
    ...(mode === "dynamic" ? {normalizer_version:"dynamic-public-read-v1",collector_version:"public-web-agent-v1"} : {}) };
  let candidate = parseCandidatePage({ items: [{ ...candidateFixture(), title: content.title,
    buyer: content.author_public_id ?? "", excerpt: content.body, url: content.public_url,
    publishedAt: content.published_at ?? "", collectedAt: raw.observations.items[0].received_at }], total: 1, page: 1, pageSize: 20 }).items[0];
  const receipts = new Map<string, CandidateReviewResultDto>();
  const requests = new Map<string, string>();
  let lostDecision = false;
  service.profiles = async () => [{ id: candidateBinding.profileId, version: candidateBinding.profileVersion,
    status: "CONFIRMED", description: "TEST 合成设备服务画像；无客户数据", fields: { ...EMPTY_PROFILE, service: "TEST 输送设备" } }];
  const fail = (code: string, message: string, status = 409): never => { throw new ServiceError(code, message, status); };
  const api = createCandidateReviewService(async (operation, _path, _method, payload) => {
    if (!(await service.session()).authenticated) fail("UNAUTHORIZED", "TEST 请先登录", 401);
    if (operation === "candidates.list") {
      record("candidateReview.LIST");
      const query = candidateQuerySchema.parse(payload);
      let row = candidate;
      if (query.reviewRequestId) {
        const result = receipts.get(query.reviewRequestId);
        row = result?.kind === "decision" ? { ...result.candidate, historical: true } : candidate;
      }
      const matches = (!query.ids || query.ids.includes(row.id)) && (!query.platform || row.platform === query.platform)
        && (!query.status || row.status === query.status) && (!query.query || `${row.title}\n${row.excerpt}`.includes(query.query))
        && (!query.reviewRequestId || (row.historical && row.lastReview?.requestId === query.reviewRequestId));
      const page = query.page ?? 1, pageSize = query.pageSize ?? 20;
      return structuredClone({ items: matches && page === 1 ? [row] : [], total: matches ? 1 : 0, page, pageSize });
    }
    if (operation === "candidates.rawEvidence") {
      record("candidateReview.RAW");
      if (mode === "raw-error") fail("VISUAL_TEST_RAW_ERROR", "TEST 原始证据读取失败；未调用真实来源。", 503);
      return structuredClone(raw);
    }
    if (operation === "candidates.request") {
      record("candidateReview.GET_REQUEST");
      const result = receipts.get((payload as { requestId: string }).requestId);
      if (!result) fail("request_not_found", "TEST 原请求不存在", 404);
      return structuredClone(result);
    }
    const request = operation === "candidates.verifySource" ? sourceVerificationRequestSchema.parse(payload) : candidateReviewRequestSchema.parse(payload);
    const action = "action" in request ? request.action : "VERIFY";
    record(`candidateReview.${action}`);
    if (Object.entries(candidateBinding).some(([key, value]) => request[key as keyof typeof candidateBinding] !== value))
      fail("VISUAL_TEST_BINDING_MISMATCH", "TEST 候选绑定不匹配");
    const original = receipts.get(request.requestId);
    if (original) {
      if (requests.get(request.requestId) !== JSON.stringify(request)) fail("conflict", "TEST 原请求内容不同");
      return structuredClone(original);
    }
    let result: CandidateReviewResultDto;
    if (!("action" in request)) {
      result = parseCandidateReviewResult({ kind: "sourceVerification", requestId: request.requestId,
        candidateId: request.candidateId, id: crypto.randomUUID(), method: "HUMAN_REOPENED", checkedBy: "TEST-owner",
        checkedAt: createdAt, binding: candidateBinding, status: request.status, openingMethod: request.openingMethod,
        locator: request.locator, excerpt: request.excerpt, contactMethod: request.contactMethod,
        ...(request.demandEvidence ? {demandEvidence:request.demandEvidence} : {}) }, { requestId: request.requestId, request });
      if (result.kind === "sourceVerification") candidate = { ...candidate, sourceStatus: result.status, sourceVerification: result };
    } else if (request.action === "ASSESS") {
      result = parseCandidateReviewResult({ kind: "assessment", requestId: request.requestId, candidateId: request.candidateId,
        assessment: { ...assessmentFixture(), assessedAt: createdAt,
          ...(candidate.sourceVerification?.demandEvidence ? {demandEvidenceId:candidate.sourceVerification.id} : {}) } }, { requestId: request.requestId, request });
      if (result.kind === "assessment") candidate = { ...candidate, assessment: result.assessment };
    } else {
      if (!candidate.assessment || candidate.assessment.id !== request.assessmentId) fail("conflict", "TEST 请先显式判断");
      if (request.action === "INCLUDE" && (candidate.sourceVerification?.id !== request.sourceVerificationId
        || candidate.sourceVerification.status !== "OPEN" || candidate.sourceVerification.contactMethod === "NONE"))
        fail("conflict", "TEST 请先完成人工来源核验");
      const { candidateId: _id, requestId, action: decisionAction, humanConfirmed: _confirmed, ...review } = request;
      const receipt = { requestId, action: decisionAction, status: "SUCCEEDED", outcome: decisionAction === "INCLUDE" ? "IMPORTED" : "EXCLUDED",
        reviewedBy: "TEST-owner", reviewedAt: createdAt,
        review: { ...review, sourceVerificationId: request.sourceVerificationId ?? null },
        ...(decisionAction === "INCLUDE" ? { opportunityId } : {}) };
      const { opportunityId: _priorOpportunity, ...before } = candidate;
      result = parseCandidateReviewResult({ kind: "decision", requestId,
        candidate: { ...before, status: receipt.outcome, lastReview: receipt, ...(decisionAction === "INCLUDE" ? { opportunityId } : {}) },
        receipt }, { requestId, request });
      if (result.kind === "decision") candidate = result.candidate;
    }
    receipts.set(request.requestId, structuredClone(result));
    requests.set(request.requestId, JSON.stringify(request));
    if (mode === "recovery" && result.kind === "decision" && !lostDecision) {
      lostDecision = true;
      fail("NETWORK_ERROR", "TEST 回执响应丢失；请仅核对原请求，不要重复提交。", 0);
    }
    return structuredClone(result);
  });
  service.candidateReview = api;
  service.candidates = async (query, signal) => {
    const page = await api.list(query, signal);
    return { ...page, items: page.items.map(item => ({ ...item,
      platform: CANDIDATE_PLATFORM_LABELS[item.platform], sourceLabel: CANDIDATE_PLATFORM_LABELS[item.platform] })) };
  };
  service.rawCandidateEvidence = api.getRawEvidence;
  return true;
}
