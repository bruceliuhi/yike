import { webcrypto } from "node:crypto";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { configureShortCoachVisual } from "../visual/r4-short-coach";
import { createVisualService } from "../visual/service";
import { opportunity } from "../visual/fixtures";
import {
  draftSnapshot,
  makeCoachInput,
  readCoachSuggestion,
  readDraftSaveReceipt,
  snapshotDigest,
} from "../../src/renderer/domain/shortCoach";

beforeEach(() => {
  vi.stubGlobal("crypto", webcrypto);
});
afterEach(() => {
  vi.unstubAllGlobals();
});
function fixture() {
  const { service } = createVisualService();
  const session = {
    authenticated: true,
    userId: "TEST-user",
    accountScope: { id: "TEST-space", version: 1 },
  };
  service.session = async () => structuredClone(session);
  const draft = {
    opportunityId: opportunity.id,
    channel: "comment" as const,
    content: "TEST人工文字",
    savedContent: "",
    version: 1,
    accountId: "",
    recipient: "",
  };
  configureShortCoachVisual(service, "populated");
  return { service, session, draft };
}
it("generates exact source-bound TEST references without changing manual input", async () => {
  const { service, session, draft } = fixture();
  const input = await makeCoachInput(
    opportunity,
    draft,
    "scope",
    "TEST-request",
    session.accountScope,
  );
  const response = await service.shortCoach!.generate(input);
  expect(readCoachSuggestion(response, input).quotes[0].text).toBe(
    opportunity.excerpt,
  );
  expect(response.content).toContain("TEST");
  expect(draft.content).toBe("TEST人工文字");
});
it("persists only an in-memory bound snapshot and queries the original idempotent receipt", async () => {
  const { service, session, draft } = fixture();
  const snapshot = draftSnapshot(opportunity, draft, session.accountScope);
  const binding = {
    opportunityId: opportunity.id,
    channel: draft.channel,
    requestId: "TEST-save",
    contentHash: await snapshotDigest(snapshot),
  };
  const response = await service.contactDrafts!.save({ binding, snapshot });
  expect(
    (await readDraftSaveReceipt(response, binding)).snapshot?.draft
      .savedContent,
  ).toBe(draft.content);
  expect(await service.contactDrafts!.operation(binding)).toEqual(response);
  expect(await service.contactDrafts!.save({ binding, snapshot })).toEqual(
    response,
  );
  expect(
    (
      await service.contactDrafts!.operation({
        ...binding,
        requestId: "TEST-missing",
      })
    ).status,
  ).toBe("UNKNOWN");
  session.accountScope.id = "TEST-other-space";
  expect((await service.contactDrafts!.operation(binding)).status).toBe(
    "UNKNOWN",
  );
});
it("rejects non-TEST scope and error state without a false saved result", async () => {
  const { service, session, draft } = fixture();
  const input = await makeCoachInput(
    opportunity,
    draft,
    "scope",
    "TEST-request",
    session.accountScope,
  );
  session.userId = "real-user";
  await expect(service.shortCoach!.generate(input)).rejects.toThrow(/合成身份/);
  session.userId = "TEST-user";
  configureShortCoachVisual(service, "error");
  await expect(service.shortCoach!.generate(input)).rejects.toThrow(/失败/);
});
