import { expect, it } from "vitest";
import { makeVisualFollowup } from "./followup";
import { opportunity, profile, TEST_TIME, TEST_USER } from "./fixtures";
import {
  readReceipt,
  readReplies,
  readSnapshot,
  type FollowupBinding,
  type FollowupFields,
} from "../../src/renderer/domain/followup";

const binding = (overrides: Partial<FollowupBinding> = {}): FollowupBinding => ({
  opportunityId: opportunity.id,
  profileVersionId: profile.id,
  action: "create",
  targetId: "",
  targetRevision: 0,
  requestId: "TEST-followup-operation",
  ...overrides,
});
const values: FollowupFields = {
  status: "CONTACTED",
  note: "TEST 内存沟通记录，无真实联系。",
  occurredAt: TEST_TIME,
  nextStep: "TEST 核对资料",
  nextFollowupAt: "2026-09-10T09:00:00+08:00",
  ownerId: TEST_USER,
};

it("uses isolated TEST identities and deep copies with valid followup/reply contracts", async () => {
  const first = makeVisualFollowup();
  const second = makeVisualFollowup();
  const snapshot = readSnapshot(await first.list());
  expect(snapshot.members).toEqual([{ id: TEST_USER, name: "TEST 当前成员" }]);
  expect(snapshot.records).toHaveLength(1);
  snapshot.records[0].note = "caller mutation";
  expect((await first.list()).records[0].note).toContain("TEST");
  expect((await second.list()).records).toHaveLength(1);
  const replies = readReplies(await first.replies(opportunity.id), opportunity.id);
  expect(replies).toHaveLength(1);
  expect(replies[0].content).toContain("并非真实来源消息");
  expect(replies[0].sendRequestId).toBe("TEST-synthetic-send-record");
  expect(await first.replies()).toEqual([]);
  expect(await first.replies("other-customer")).toEqual([]);
});

it("creates, corrects and voids memory records while retaining audit history and exact receipts", async () => {
  const api = makeVisualFollowup();
  const create = binding();
  const created = readReceipt(await api.mutate({ binding: create, values }), create);
  expect(created.status).toBe("SUCCEEDED");
  expect(created.record).toMatchObject(values);
  const correct = binding({
    action: "correct", targetId: created.record!.id,
    targetRevision: created.record!.revision, requestId: "TEST-correct",
  });
  const corrected = readReceipt(await api.mutate({
    binding: correct, values: { ...values, note: "TEST 修正事实" }, reason: "TEST 原记录有误",
  }), correct);
  expect(corrected.record!.correctsId).toBe(created.record!.id);
  const afterCorrection = await api.list();
  expect(afterCorrection.records.find(row => row.id === created.record!.id)).toMatchObject({ state: "CORRECTED", note: values.note });
  const withdraw = binding({
    action: "void", targetId: corrected.record!.id,
    targetRevision: corrected.record!.revision, requestId: "TEST-void",
  });
  expect(readReceipt(await api.mutate({ binding: withdraw, reason: "TEST 重复登记" }), withdraw).record!.state).toBe("VOID");
  expect((await api.list()).records).toHaveLength(3);
});

it("marks only the original reply read and preserves immutable original request receipts", async () => {
  const api = makeVisualFollowup();
  const reply = (await api.replies(opportunity.id))[0];
  const markRead = binding({ action: "mark-read", targetId: reply.id, targetRevision: reply.revision });
  const result = readReceipt(await api.mutate({ binding: markRead }), markRead);
  expect(result.reply).toMatchObject({ read: true, revision: 2 });
  expect(await api.mutate({ binding: markRead })).toEqual(result);
  result.reply!.content = "caller mutation";
  expect((await api.operation(markRead)).reply!.content).toContain("TEST 合成回复");
  await expect(api.mutate({ binding: { ...markRead, targetRevision: 2 } })).rejects.toThrow("原请求内容发生变化");
});

it("rejects stale versions and wrong scope without mutating memory, and keeps missing requests unknown", async () => {
  const api = makeVisualFollowup();
  const before = await api.list();
  const invalid = binding({ action: "correct", targetId: before.records[0].id, targetRevision: 99 });
  expect(readReceipt(await api.mutate({ binding: invalid, values, reason: "TEST" }), invalid).status).toBe("FAILED");
  expect(await api.list()).toEqual(before);
  await expect(api.mutate({ binding: binding({ opportunityId: "customer-real" }), values })).rejects.toThrow("隔离跟进对象");
  expect((await api.operation(binding({ requestId: "TEST-never-observed" }))).status).toBe("UNKNOWN");
  expect(await api.list()).toEqual(before);
});
