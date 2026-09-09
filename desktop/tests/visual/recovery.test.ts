// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { createVisualService } from "./service";
import { configureRecovery, selectRecovery } from "./recovery";
import { MemoryStorage } from "./isolation";
import { TEST_USER, opportunity, profile } from "./fixtures";
import type { ContactDraft, TaskDraft } from "../../src/renderer/domain/models";
import { parseSendReceipt } from "../../src/renderer/domain/outreach";
import {
  configurationHash,
  parseStartReceipt,
} from "../../src/renderer/domain/taskOperations";
afterEach(() => vi.restoreAllMocks());

describe("opt-in recovery transport fixtures", () => {
  it("accepts only the finite, matching authenticated TEST scenarios", () => {
    expect(selectRecovery(null, "P13", "populated", false)).toBeUndefined();
    expect(selectRecovery("ai-late", "P20", "populated", false)).toBe(
      "ai-late",
    );
    for (const args of [
      ["missing", "P13", "populated", false],
      ["send-unknown", "P12", "populated", false],
      ["send-unknown", "P13", "error", false],
      ["send-unknown", "P13", "populated", true],
    ] as const)
      expect(() => selectRecovery(args[0], args[1], args[2], args[3])).toThrow(
        /TEST/,
      );
  });
  it("releases only explicitly requested advice, including intentionally late cancelled transport results", async () => {
    const h = createVisualService();
    const c = configureRecovery(h, "ai-late");
    const abort = new AbortController();
    const request = h.service.suggest(profile.id, "TEST-suggest", abort.signal);
    await Promise.resolve();
    await Promise.resolve();
    expect(c.snapshot().pendingSuggestions).toBe(1);
    abort.abort();
    c.releaseSuggestions();
    expect(await request).toMatchObject({
      profileId: profile.id,
      requestId: "TEST-suggest",
      keywords: ["TEST 后到展台需求建议"],
    });
    expect(c.snapshot().pendingSuggestions).toBe(0);
    await expect(
      h.service.suggest("OTHER", "TEST-invalid"),
    ).rejects.toMatchObject({ code: "VISUAL_SCOPE_REJECTED" });
  });
  it("keeps send UNKNOWN bound to its one original request, with no network and only explicit TEST non-delivery", async () => {
    const network = vi
      .spyOn(globalThis, "fetch")
      .mockRejectedValue(new Error("must not call"));
    const h = createVisualService();
    const c = configureRecovery(h, "send-unknown");
    const storage = new MemoryStorage();
    c.seed(storage, "P13");
    const draft: ContactDraft = JSON.parse(
      storage.getItem(
        `yike.ui.draft.v1.contact:${TEST_USER}:${opportunity.id}`,
      )!,
    ).comment;
    const proof = await h.service.verifyContact(draft, "TEST-fingerprint");
    const receipt = await h.service.outreach!.send(draft, {
      requestId: "TEST-send-request",
      confirmationToken: proof.confirmationToken,
    });
    const binding = {
      opportunityId: draft.opportunityId,
      channel: draft.channel,
      version: draft.version,
      requestId: receipt.requestId,
    };
    expect(parseSendReceipt(receipt, binding).status).toBe("UNKNOWN");
    expect((await h.service.outreach!.reconcile(binding)).status).toBe(
      "UNKNOWN",
    );
    await expect(
      h.service.outreach!.reconcile({ ...binding, version: 3 }),
    ).rejects.toThrow(/原发送请求/);
    await expect(
      h.service.outreach!.send(draft, {
        requestId: "TEST-other",
        confirmationToken: proof.confirmationToken,
      }),
    ).rejects.toThrow(/第二个/);
    c.confirmNotExecuted();
    expect(
      parseSendReceipt(await h.service.outreach!.reconcile(binding), binding),
    ).toMatchObject({
      status: "FAILED",
      confirmed: true,
      confirmedNotDelivered: true,
    });
    const other = createVisualService();
    configureRecovery(other, "send-unknown");
    await expect(other.service.outreach!.reconcile(binding)).rejects.toThrow(
      /原发送请求/,
    );
    await h.service.logout();
    await expect(h.service.outreach!.reconcile(binding)).rejects.toMatchObject({
      code: "UNAUTHORIZED",
    });
    expect(network).not.toHaveBeenCalled();
  });
  it("requires exact startup configuration and only ever resolves UNKNOWN or confirmed not-started", async () => {
    const h = createVisualService();
    const c = configureRecovery(h, "start-unknown");
    const storage = new MemoryStorage();
    c.seed(storage, "P19");
    const draft: TaskDraft = JSON.parse(
      storage.getItem(`yike.ui.draft.v1.task.${TEST_USER}`)!,
    );
    const binding = {
      requestId: `task:${draft.id}:${draft.revision}`,
      draftId: draft.id,
      revision: draft.revision,
      configurationHash: await configurationHash(draft),
      mode: draft.mode,
    };
    await expect(
      h.service.taskOperations!.start(draft, {
        ...binding,
        configurationHash: "a".repeat(64),
      }),
    ).rejects.toThrow(/摘要不匹配/);
    const receipt = await h.service.taskOperations!.start(draft, binding);
    expect(parseStartReceipt(receipt, binding).status).toBe("UNKNOWN");
    const lookup = {
      draftId: binding.draftId,
      requestId: binding.requestId,
      revision: binding.revision,
      mode: binding.mode,
      configurationHash: binding.configurationHash,
    };
    expect(
      (await h.service.taskOperations!.reconcileStart(lookup)).status,
    ).toBe("UNKNOWN");
    c.confirmNotExecuted();
    expect(
      parseStartReceipt(
        await h.service.taskOperations!.reconcileStart(lookup),
        binding,
      ),
    ).toMatchObject({ status: "REJECTED", confirmedNotStarted: true });
    expect(await h.service.tasks()).toEqual(
      await createVisualService().service.tasks(),
    );
    await expect(
      h.service.startTask(draft, binding.requestId),
    ).rejects.toMatchObject({ code: "CAPABILITY_UNAVAILABLE" });
  });
  it("models only an opened TEST connection with no verified capability and preserves other instances", async () => {
    const h = createVisualService();
    configureRecovery(h, "connection-limited");
    await expect(h.service.checkConnection("xhs")).rejects.toThrow(/先推进/);
    await h.service.connect("xhs");
    expect(await h.service.checkConnection("xhs")).toMatchObject({
      status: "CONNECTED",
      capabilities: [],
      accountName: expect.stringContaining("TEST"),
    });
    expect((await h.service.connections())[0].capabilities).toEqual([]);
    expect((await createVisualService().service.connections())[0].status).toBe(
      "DISCONNECTED",
    );
  });
});
