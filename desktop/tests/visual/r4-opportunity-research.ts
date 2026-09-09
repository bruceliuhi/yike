import type { YikeService } from "../../src/renderer/services/contracts";
import { ServiceError } from "../../src/renderer/services/contracts";
import type { Opportunity, Session } from "../../src/renderer/domain/models";
import {
  hasResearchScope,
  researchBinding,
  sameResearchBinding,
  type ResearchBinding,
  type ResearchCollection,
  type ResearchRecord,
  type ResearchTimeline,
  type SimilarResearchPlan,
} from "../../src/renderer/domain/opportunityResearch";
import type { VisualState } from "./service";
import { opportunity, profile, TEST_TIME } from "./fixtures";

/** Isolated visual harness only. No network, charging, collection, messages or
 * customer writes. All objects are synthetic TEST records with .invalid URLs. */
export function configureResearchVisual(
  service: YikeService,
  state: VisualState,
): void {
  const primary: Opportunity = {
    ...structuredClone(opportunity),
    excerpt: "TEST 本次报价仅用于预算测算。TEST 现增加技术资料要求。",
  };
  const records: ResearchRecord[] = [
    {
      opportunity: primary,
      classification: {
        category: "OPPORTUNITY",
        type: "TEST 预算询价",
        reason: "TEST 原文含预算询价表达；不代表已签合同或成交。",
        ruleVersion: "TEST-rule-v1",
        evidence: [
          {
            sourceUrl: primary.url,
            evidenceVersion: primary.sourceEvidenceVersion!,
            quote: "TEST 本次报价仅用于预算测算。",
          },
        ],
        review: {
          status: "RECOGNIZED",
          reviewer: "TEST 复核人",
          reviewedAt: TEST_TIME,
        },
      },
    },
    {
      opportunity: {
        ...primary,
        id: "TEST-observation",
        title: "TEST 新展厅开业观察",
        url: "https://visual-test.invalid/TEST-observation",
        excerpt: "TEST 企业公布新展厅开业，未说明采购需求。",
        libraryFacts: undefined,
        intentStatus: "REVIEW",
        comment: "",
        dm: "",
      },
      classification: {
        category: "OBSERVATION",
        type: "TEST 开业变化",
        reason: "TEST 只有业务变化，没有可核验的采购表达。",
        ruleVersion: "TEST-rule-v1",
        evidence: [
          {
            sourceUrl: "https://visual-test.invalid/TEST-observation",
            evidenceVersion: primary.sourceEvidenceVersion!,
            quote: "TEST 企业公布新展厅开业，未说明采购需求。",
          },
        ],
        review: { status: "NEEDS_EVIDENCE", reviewer: "", reviewedAt: null },
      },
    },
    {
      opportunity: {
        ...primary,
        id: "TEST-excluded",
        title: "TEST 人员招聘信息",
        url: "https://visual-test.invalid/TEST-excluded",
        excerpt: "TEST 招聘施工人员，不是采购服务。",
        libraryFacts: undefined,
        intentStatus: "REVIEW",
        comment: "",
        dm: "",
      },
      classification: {
        category: "EXCLUDED",
        type: "TEST 招聘",
        reason: "TEST 当前画像排除招聘类信息。",
        ruleVersion: "TEST-rule-v1",
        evidence: [
          {
            sourceUrl: "https://visual-test.invalid/TEST-excluded",
            evidenceVersion: primary.sourceEvidenceVersion!,
            quote: "TEST 招聘施工人员，不是采购服务。",
          },
        ],
        review: { status: "PENDING", reviewer: "", reviewedAt: null },
      },
    },
  ];
  const read = async (signal?: AbortSignal): Promise<Session> => {
    if (signal?.aborted) throw new DOMException("TEST cancelled", "AbortError");
    const session = await service.session();
    if (!hasResearchScope(session.accountScope))
      throw new ServiceError(
        "UNVERIFIED_SCOPE",
        "TEST 研究需要可信账户空间",
        403,
      );
    if (!session.authenticated || !session.userId)
      throw new ServiceError("UNAUTHORIZED", "TEST 请先登录隔离测试空间", 401);
    if (state === "error")
      throw new ServiceError(
        "VISUAL_TEST_ERROR",
        "TEST 研究服务读取失败；不是空结果",
        503,
      );
    if (state === "loading")
      return new Promise<Session>((_resolve, reject) => {
        if (signal?.aborted)
          reject(new DOMException("TEST cancelled", "AbortError"));
        else
          signal?.addEventListener(
            "abort",
            () => reject(new DOMException("TEST cancelled", "AbortError")),
            { once: true },
          );
      });
    return session;
  };
  const stamp = () => ({
    generatedAt: new Date().toISOString(),
    expiresAt: new Date(Date.now() + 60 * 60_000).toISOString(),
  });
  const recordFor = (id: string) => {
    const value =
      state === "empty"
        ? undefined
        : records.find((r) => r.opportunity.id === id);
    if (!value || id === "sample")
      throw new ServiceError("NOT_FOUND", "TEST 授权研究记录不存在", 404);
    return structuredClone(value);
  };
  const checked = async (binding: ResearchBinding, signal?: AbortSignal) => {
    const session = await read(signal),
      record = recordFor(binding.opportunityId);
    const expected = researchBinding(
      record.opportunity,
      session.userId,
      session.accountScope,
    );
    if (!expected || !sameResearchBinding(expected, binding))
      throw new ServiceError(
        "STALE_BINDING",
        "TEST 研究身份或来源版本不匹配",
        409,
      );
    return record;
  };
  service.opportunityResearch = {
    async list(signal): Promise<ResearchCollection> {
      const session = await read(signal);
      return {
        schemaVersion: 1,
        userId: session.userId!,
        accountScope: structuredClone(session.accountScope!),
        snapshotId: "TEST-research-collection",
        ...stamp(),
        records: state === "empty" ? [] : structuredClone(records),
      };
    },
    async timeline(binding, signal): Promise<ResearchTimeline> {
      const record = await checked(binding, signal),
        row = record.opportunity;
      const original =
        row.id === primary.id ? "TEST 本次报价仅用于预算测算。" : row.excerpt;
      const hasChange = row.id === primary.id;
      return {
        schemaVersion: 1,
        binding: structuredClone(binding),
        snapshotId: `TEST-timeline-${row.id}`,
        ...stamp(),
        versions: [
          {
            id: "TEST-original-v0",
            ordinal: 1,
            previousVersionId: null,
            sourceUrl: row.url,
            content: original,
            publishedAt: row.publishedAt,
            observedAt: null,
            access: "AVAILABLE",
          },
          {
            id: row.sourceEvidenceVersion!,
            ordinal: 2,
            previousVersionId: "TEST-original-v0",
            sourceUrl: row.url,
            content: row.excerpt,
            publishedAt: null,
            observedAt: TEST_TIME,
            access: "AVAILABLE",
          },
        ],
        changes: hasChange
          ? [
              {
                id: "TEST-source-change-1",
                kind: "CONTENT",
                label: "TEST 资料范围新增说明",
                from: {
                  sourceUrl: row.url,
                  evidenceVersion: "TEST-original-v0",
                  quote: original,
                },
                to: {
                  sourceUrl: row.url,
                  evidenceVersion: row.sourceEvidenceVersion!,
                  quote: row.excerpt,
                },
                occurredAt: null,
              },
            ]
          : [],
        contacts: hasChange
          ? [
              {
                id: "TEST-manual-research-event",
                opportunityId: row.id,
                kind: "MANUAL",
                label: "TEST 人工登记示意",
                detail:
                  "TEST 已整理待核实资料；未进行真实联系，也不是平台回复。",
                occurredAt: null,
                recordedAt: TEST_TIME,
                operator: "TEST 复核人",
                receiptId: "",
              },
            ]
          : [],
        gaps: ["TEST 实际采购预算", "TEST 技术资料获取方式"],
      };
    },
    async similar(binding, requestId, signal): Promise<SimilarResearchPlan> {
      const record = await checked(binding, signal);
      if (!requestId.trim() || requestId.length > 128)
        throw new ServiceError("INVALID_REQUEST", "TEST 请求 ID 无效", 400);
      const eligible =
        record.classification.category === "OPPORTUNITY" &&
        record.classification.review.status === "RECOGNIZED";
      return {
        schemaVersion: 1,
        requestId,
        suggestionId: `TEST-similar-${record.opportunity.id}`,
        binding: structuredClone(binding),
        ...stamp(),
        eligible,
        ineligibleReason: eligible ? "" : "TEST 尚不是已认可的明确需求",
        recognition: eligible
          ? {
              reviewer: record.classification.review.reviewer,
              reviewedAt: record.classification.review.reviewedAt!,
              evidenceVersion: binding.evidenceVersion,
            }
          : null,
        rationale: "TEST 同类展区设计搭建公开需求；仅用于检验配置预览。",
        evidence: record.classification.evidence,
        profileId: profile.id,
        profileVersion: profile.version,
        keywords: [
          "TEST 展区预算询价",
          "TEST 会展服务范围",
          "TEST 展台技术资料",
        ],
        exclusions: ["TEST 招聘", "TEST 培训"],
        supportedPlatforms: ["xhs", "douyin", "web"],
        originalScope: "TEST 原任务：公开网站中的展区预算询价",
        additionalScope: "TEST 新草稿：用户选定的新搜索词与平台；不变更原任务",
        usage: {
          status: "UNKNOWN",
          reason: "TEST 仅内存预览，未接真实搜贝计量。",
        },
      };
    },
  };
  service.opportunities = async () => {
    await read();
    return state === "empty" ? [] : [structuredClone(primary)];
  };
  service.opportunity = async (id) => {
    await read();
    return recordFor(id).opportunity;
  };
}
