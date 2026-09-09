import type { YikeService } from "../../src/renderer/services/contracts";
import { ServiceError } from "../../src/renderer/services/contracts";
import {
  coachSourceKey,
  draftSaveBindingSchema,
  draftSaveKey,
  draftSnapshotSchema,
  makeCoachInput,
  readCoachSuggestion,
  snapshotDigest,
  type CoachSuggestion,
  type DraftSaveReceipt,
} from "../../src/renderer/domain/shortCoach";
import type { VisualState } from "./service";

/** TEST-only structured coaching and in-memory draft receipts. No model,
 * platform, backend, charge, message, or filesystem operation is performed. */
export function configureShortCoachVisual(
  service: YikeService,
  state: VisualState,
): void {
  const receipts = new Map<string, DraftSaveReceipt>();
  const fail = (message: string): never => {
    throw new ServiceError("VISUAL_SCOPE_REJECTED", "TEST " + message, 400);
  };
  const identity = async () => {
    const session = await service.session();
    if (
      !session.authenticated ||
      !session.userId?.startsWith("TEST-") ||
      !session.accountScope
    )
      return fail("短句演练只接受带客户空间版本的合成身份");
    return {
      session,
      key: JSON.stringify([session.userId, session.accountScope]),
    };
  };
  const wait = async (signal?: AbortSignal) => {
    if (state === "error")
      throw new ServiceError(
        "VISUAL_TEST_ERROR",
        "TEST 建议或保存失败，当前输入保留",
        503,
      );
    if (state === "empty") return fail("当前没有 TEST 商机");
    if (state === "loading") return new Promise<never>(() => {});
    await new Promise<void>((resolve) => setTimeout(resolve, 350));
    if (signal?.aborted) throw new Error("TEST 已停止等待；没有外部操作");
  };
  const rowFor = async (opportunityId: string) => {
    if (!opportunityId.startsWith("TEST-"))
      return fail("不接受真实商机或公开样例");
    const row = await service.opportunity(opportunityId);
    if (
      !row ||
      row.sample ||
      row.id !== opportunityId ||
      !row.excerpt.includes("TEST")
    )
      return fail("商机不是本实例的合成原文");
    return row;
  };
  service.shortCoach = {
    async generate(input, signal) {
      const before = await identity();
      const row = await rowFor(input.binding.opportunityId);
      const expected = await makeCoachInput(
        row,
        {
          opportunityId: row.id,
          channel: input.binding.channel,
          content: input.content,
          savedContent: "",
          version: input.binding.draftVersion,
          accountId: "",
          recipient: "",
        },
        input.binding.purpose,
        input.binding.requestId,
        before.session.accountScope!,
      );
      if (
        JSON.stringify(expected.binding) !== JSON.stringify(input.binding) ||
        expected.sourceText !== input.sourceText
      )
        return fail("短句输入与当前来源、画像、空间或草稿不一致");
      await wait(signal);
      if (
        (await identity()).key !== before.key ||
        coachSourceKey(await rowFor(row.id)) !== coachSourceKey(row)
      )
        return fail("等待期间 TEST 身份或来源变化");
      const question = {
        requirement: "请问本次预算测算需要先确认哪项具体需求？",
        materials: "请问本次预算测算所需的技术资料如何获取？",
        scope: "请问本次预算测算涵盖哪些服务范围？",
      }[input.binding.purpose];
      const suggestion: CoachSuggestion = {
        suggestionId: "TEST-coach-" + crypto.randomUUID(),
        binding: input.binding,
        content: `TEST 您好，关注到本次预算测算。${question}本内容仅供隔离交互演练，未进行真实联系。`,
        question,
        context: {
          summary: "TEST 依据当前合成原文准备一个待核对问题。",
          quoteIds: ["TEST-quote-1"],
        },
        quotes: [
          {
            id: "TEST-quote-1",
            text: row.excerpt,
            start: 0,
            end: row.excerpt.length,
            sourceUrl: row.url,
            sourceEvidenceVersion: row.sourceEvidenceVersion!,
          },
        ],
        checks: [
          {
            kind: "CONTEXT",
            status: "SUPPORTED",
            message: "TEST 上下文来自本次合成原文。",
            quoteIds: ["TEST-quote-1"],
          },
          {
            kind: "ONE_QUESTION",
            status: "SUPPORTED",
            message: "TEST 候选包含一个明确问题。",
            quoteIds: [],
          },
          {
            kind: "PROMISE",
            status: "NEEDS_REVIEW",
            message: "TEST 服务能力仍需人工核实。",
            quoteIds: [],
          },
        ],
        createdAt: new Date().toISOString(),
        expiresAt: new Date(Date.now() + 600_000).toISOString(),
      };
      return structuredClone(readCoachSuggestion(suggestion, input));
    },
  };
  service.contactDrafts = {
    async save(input) {
      const before = await identity();
      const binding = draftSaveBindingSchema.parse(input.binding);
      const snapshot = draftSnapshotSchema.parse(input.snapshot);
      const row = await rowFor(binding.opportunityId);
      if (
        JSON.stringify(snapshot.accountScope) !==
          JSON.stringify(before.session.accountScope) ||
        snapshot.draft.opportunityId !== row.id ||
        snapshot.draft.channel !== binding.channel ||
        snapshot.profileVersionId !== row.profileVersionId ||
        snapshot.sourceEvidenceVersion !== row.sourceEvidenceVersion ||
        (await snapshotDigest(snapshot)) !== binding.contentHash
      )
        return fail("保存快照与当前空间、版本或内容摘要不一致");
      const key = before.key + ":" + binding.requestId;
      const previous = receipts.get(key);
      if (previous) {
        if (draftSaveKey(previous.binding) !== draftSaveKey(binding))
          return fail("同一保存请求不得改变内容");
        return structuredClone(previous);
      }
      await wait();
      if ((await identity()).key !== before.key)
        return fail("保存前客户空间变化");
      const receipt: DraftSaveReceipt = {
        binding,
        status: "SUCCEEDED",
        confirmed: true,
        snapshot: {
          ...snapshot,
          draft: { ...snapshot.draft, savedContent: snapshot.draft.content },
        },
      };
      receipts.set(key, structuredClone(receipt));
      return structuredClone(receipt);
    },
    async operation(binding) {
      const current = await identity();
      draftSaveBindingSchema.parse(binding);
      await wait();
      if ((await identity()).key !== current.key)
        return fail("查询期间客户空间变化");
      const receipt = receipts.get(current.key + ":" + binding.requestId);
      if (!receipt) return { binding, status: "UNKNOWN", confirmed: false };
      if (draftSaveKey(receipt.binding) !== draftSaveKey(binding))
        return fail("核对参数不是原保存请求");
      return structuredClone(receipt);
    },
  };
}
