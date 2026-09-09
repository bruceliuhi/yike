import type { FollowupService } from "../../src/renderer/services/followup";
import {
  followupFieldsSchema,
  followupKey,
  readReceipt,
  readSnapshot,
  type FollowupBinding,
  type FollowupMutation,
  type FollowupReceipt,
  type FollowupRecord,
  type LinkedReply,
} from "../../src/renderer/domain/followup";
import { opportunity, profile, TEST_TIME, TEST_USER } from "./fixtures";

/** TEST-only memory service. No platform messages, network, customer DB or storage IO. */
export function makeVisualFollowup(): FollowupService {
  const member = { id: TEST_USER, name: "TEST 当前成员" };
  let sequence = 0;
  let records: FollowupRecord[] = [
    {
      id: "TEST-followup-initial",
      opportunityId: opportunity.id,
      profileVersionId: profile.id,
      revision: 1,
      title: opportunity.title,
      status: "CONTACTED",
      note: "TEST 人工登记示意：仅用于检查跟进流程，没有进行真实联系。",
      createdAt: TEST_TIME,
      occurredAt: TEST_TIME,
      nextStep: "TEST 核对资料要求，仅测试内存内容。",
      nextFollowupAt: "2026-09-10T09:00:00+08:00",
      ownerId: member.id,
      ownerName: member.name,
      state: "ACTIVE",
      kind: "manual",
      sample: false,
      replyCount: 1,
    },
  ];
  let replies: LinkedReply[] = [
    {
      id: "TEST-followup-reply",
      revision: 1,
      opportunityId: opportunity.id,
      profileVersionId: profile.id,
      sendRequestId: "TEST-synthetic-send-record",
      platform: "TEST 内存通道",
      content: "TEST 合成回复，仅用于已读与关联布局验收，并非真实来源消息。",
      receivedAt: TEST_TIME,
      read: false,
      sample: false,
    },
  ];
  const operations = new Map<
    string,
    { key: string; input: string; receipt: FollowupReceipt }
  >();
  const clone = <T,>(value: T): T => structuredClone(value);
  const requireBinding = (binding: FollowupBinding) => {
    if (
      binding.opportunityId !== opportunity.id ||
      binding.profileVersionId !== profile.id ||
      typeof binding.requestId !== "string" ||
      !binding.requestId.trim() ||
      binding.requestId.length > 128 ||
      !["create", "correct", "void", "mark-read"].includes(binding.action) ||
      typeof binding.targetId !== "string" ||
      !Number.isSafeInteger(binding.targetRevision) ||
      binding.targetRevision < 0
    )
      throw new Error("TEST 请求不属于此隔离跟进对象。");
  };
  const mutate = async (input: FollowupMutation): Promise<FollowupReceipt> => {
    const binding = clone(input.binding);
    requireBinding(binding);
    const key = followupKey(binding);
    const fingerprint = JSON.stringify(input);
    const existing = operations.get(binding.requestId);
    if (existing) {
      if (existing.key !== key || existing.input !== fingerprint)
        throw new Error("TEST 原请求内容发生变化，未执行第二次操作。");
      return clone(existing.receipt);
    }
    const settle = (receipt: FollowupReceipt) => {
      const checked = readReceipt(receipt, binding);
      operations.set(binding.requestId, {
        key,
        input: fingerprint,
        receipt: clone(checked),
      });
      return clone(checked);
    };
    const fail = (message: string) =>
      settle({ binding, status: "FAILED", confirmed: true, message });
    if (binding.action === "mark-read") {
      const reply = replies.find((row) => row.id === binding.targetId);
      if (!reply || reply.read || reply.revision !== binding.targetRevision)
        return fail("TEST 回复已变化，未修改。");
      const updated = { ...reply, read: true, revision: reply.revision + 1 };
      replies = replies.map((row) => (row.id === reply.id ? updated : row));
      return settle({
        binding,
        status: "SUCCEEDED",
        confirmed: true,
        reply: updated,
      });
    }
    const previous = records.find((row) => row.id === binding.targetId);
    if (binding.action === "create") {
      if (binding.targetId || binding.targetRevision !== 0)
        return fail("TEST 新登记不应指向已有记录。");
    } else if (
      !previous ||
      previous.state !== "ACTIVE" ||
      previous.revision !== binding.targetRevision ||
      !input.reason?.trim() ||
      input.reason.length > 500
    )
      return fail("TEST 原登记版本或更正原因不符合要求，未修改。");
    if (binding.action === "void") {
      const updated: FollowupRecord = {
        ...previous!,
        revision: previous!.revision + 1,
        state: "VOID",
        reason: input.reason!.trim(),
      };
      records = records.map((row) =>
        row.id === updated.id ? updated : row,
      );
      return settle({
        binding,
        status: "SUCCEEDED",
        confirmed: true,
        record: updated,
      });
    }
    const fields = followupFieldsSchema.safeParse(input.values);
    if (!fields.success || fields.data.ownerId !== member.id)
      return fail("TEST 跟进内容或成员不匹配，未保存。");
    const record: FollowupRecord = {
      ...fields.data,
      id: `TEST-followup-created-${++sequence}`,
      opportunityId: opportunity.id,
      profileVersionId: profile.id,
      revision: 1,
      title: opportunity.title,
      createdAt: new Date().toISOString(),
      ownerName: member.name,
      state: "ACTIVE",
      kind: "manual",
      sample: false,
      replyCount: replies.length,
      ...(binding.action === "correct"
        ? { correctsId: previous!.id, reason: input.reason!.trim() }
        : {}),
    };
    records = [
      record,
      ...records.map((row) =>
        binding.action === "correct" && row.id === previous!.id
          ? { ...row, state: "CORRECTED" as const, revision: row.revision + 1 }
          : row,
      ),
    ];
    return settle({
      binding,
      status: "SUCCEEDED",
      confirmed: true,
      record,
    });
  };
  return {
    list: async () => clone(readSnapshot({ records, members: [member] })),
    replies: async (id) =>
      clone(id === opportunity.id ? replies : []),
    mutate,
    operation: async (binding) => {
      requireBinding(binding);
      const existing = operations.get(binding.requestId);
      if (existing && existing.key !== followupKey(binding))
        throw new Error("TEST 原请求与核对对象不匹配。");
      return existing
        ? clone(existing.receipt)
        : { binding: clone(binding), status: "UNKNOWN" };
    },
  };
}
