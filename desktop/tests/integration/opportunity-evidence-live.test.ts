import { afterEach, expect, it, vi } from "vitest";
import {
  configuredService,
  createServiceClient,
} from "../../src/main/serviceClient";
import { service } from "../../src/renderer/services/client";

const names = [
  "YIKE_EVIDENCE_LIVE_BASE",
  "YIKE_EVIDENCE_LIVE_TOKEN",
  "YIKE_EVIDENCE_LIVE_STRANGER_TOKEN",
  "YIKE_EVIDENCE_LIVE_OPPORTUNITY_ID",
  "YIKE_EVIDENCE_LIVE_EXPECTED_JSON",
] as const;
const enabled = names.some((name) => Boolean(process.env[name]));

afterEach(() => vi.unstubAllGlobals());

// Only the Python test provisions this isolated loopback server and restricted PG.
it.skipIf(!enabled)(
  "reads the first fixed comment evidence through the actual desktop service",
  async () => {
    expect(process.versions.node.split(".")[0]).toBe("24");
    const values = Object.fromEntries(
      names.map((name) => [name, process.env[name]]),
    ) as Record<(typeof names)[number], string | undefined>;
    expect(Object.values(values).every((value) => Boolean(value))).toBe(true);

    const base = values.YIKE_EVIDENCE_LIVE_BASE!;
    const token = values.YIKE_EVIDENCE_LIVE_TOKEN!;
    const strangerToken = values.YIKE_EVIDENCE_LIVE_STRANGER_TOKEN!;
    const opportunityId = values.YIKE_EVIDENCE_LIVE_OPPORTUNITY_ID!;
    const expectedEvidence: unknown = JSON.parse(
      values.YIKE_EVIDENCE_LIVE_EXPECTED_JSON!,
    );
    expect(new URL(base).hostname).toBe("127.0.0.1");
    const baseUrl = configuredService(base, {
      packaged: false,
      allowLoopbackHttp: true,
    });
    expect(baseUrl).toBe(base);

    const actualFetch = globalThis.fetch;
    let cookie = "";
    const calls: string[] = [];
    const client = createServiceClient({
      baseUrl,
      clearSession: async () => {
        cookie = "";
      },
      // Node has no Electron cookie jar; retain only this fixture's session cookie.
      fetch: async (url, options) => {
        expect(new URL(url).origin).toBe(base);
        calls.push(`${options.method} ${new URL(url).pathname}`);
        const headers = new Headers(options.headers);
        if (cookie) headers.set("Cookie", cookie);
        const response = await actualFetch(url, { ...options, headers });
        const session = response.headers
          .getSetCookie()
          .find((value) => value.startsWith("pilot_session="));
        if (session) cookie = session.split(";", 1)[0];
        expect(response.headers.get("cache-control")).toBe("no-store");
        return response;
      },
    });
    vi.stubGlobal("window", { yikeDesktop: { requestApi: client.request } });

    expect((await service.loginToken(token)).authenticated).toBe(true);
    const opportunity = await service.opportunity(opportunityId);
    expect(opportunity.id).toBe(opportunityId);
    expect(opportunity.sourceStatus).toBe("BLOCKED");
    expect(opportunity.sourceEvidence).toEqual(expectedEvidence);
    expect(opportunity.sourceEvidence?.status).toBe("CAPTURED");
    if (opportunity.sourceEvidence?.status !== "CAPTURED") {
      throw new Error("captured evidence required");
    }
    const snapshot = opportunity.sourceEvidence.snapshot;
    expect(snapshot.source).toMatchObject({
      kind: "COMMENT",
      title: null,
      container_title: "食品工厂扩产",
      body: "我们工厂想采购输送设备，月底前找团队报价。",
      author_public_id: null,
      parent: {
        external_comment_id: "synthetic-parent-comment",
        body: "父评论  原文",
        author_public_id: "synthetic-parent-author",
      },
    });
    expect(snapshot.assessment.citations).toEqual([
      {
        dimension: "businessMatch",
        field: "source.container_title",
        quote: "食品工厂扩产",
      },
      {
        dimension: "businessMatch",
        field: "source.parent.body",
        quote: "父评论  原文",
      },
      {
        dimension: "intent",
        field: "source.body",
        quote: "采购输送设备",
      },
      {
        dimension: "urgency",
        field: "source.body",
        quote: "月底前",
      },
    ]);
    expect("unknowns" in snapshot.assessment).toBe(false);
    expect(snapshot.verification).toMatchObject({
      status_at_capture: "OPEN",
      contact_method: "COMMENT",
    });

    await service.logout();
    expect(cookie).toBe("");
    await expect(service.opportunity(opportunityId)).rejects.toMatchObject({
      status: 401,
    });

    expect((await service.loginToken(strangerToken)).authenticated).toBe(true);
    await expect(service.opportunity(opportunityId)).rejects.toMatchObject({
      code: "opportunity_not_found",
      status: 404,
    });
    expect(calls.map((call) => call.split(" ", 1)[0])).toEqual([
      "POST",
      "GET",
      "DELETE",
      "GET",
      "POST",
      "GET",
    ]);
  },
  30_000,
);
