import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import {
  parseNativeCollectionLink,
  planNativeCollectionLinks,
} from "../src/shared/nativeCollectionLinks";
import {
  prepareStrategySchema,
  strategyViewSchema,
} from "../src/shared/researchStrategies";

type ExpectedLink = {
  platform: "XIAOHONGSHU" | "DOUYIN" | "BILIBILI" | "ZHIHU";
  kind: "detail" | "creator";
  external_id: string;
  canonical_url: string;
};

const fixture = JSON.parse(
  readFileSync(
    fileURLToPath(new URL("../../tests/fixtures/native_collection_links.json", import.meta.url)),
    "utf8",
  ),
) as { valid: Array<{ url: string; expected: ExpectedLink }>; invalid: unknown[] };

const UUID = "11111111-1111-4111-8111-111111111111";

function prepare(platforms: string[] = ["BILIBILI"], links: string[] = [fixture.valid[0].url]) {
  return {
    schema_version: "strategy-confirmation-v1",
    request_id: UUID,
    draft_id: UUID,
    draft_revision: 1,
    profile_version_id: UUID,
    platforms,
    max_records: 25,
    max_runtime_seconds: 120,
    configuration: {
      schema_version: "research-strategy-v1",
      name: "指定内容",
      source: "links",
      keywords: [],
      exclusions: [],
      links,
      mode: "once",
      schedule: null,
      research: null,
    },
  };
}

describe("native collection links", () => {
  it.each(fixture.valid)("parses $url to the exact four-field target", ({ url, expected }) => {
    expect(parseNativeCollectionLink(url)).toEqual(expected);
    expect(parseNativeCollectionLink(expected.canonical_url)).toEqual(expected);
  });

  it.each([...fixture.invalid, null, true, 42, {}, [], ""])(
    "rejects ambiguous or unsafe input without echoing it %#",
    (value) => {
      expect(() => parseNativeCollectionLink(value)).toThrowError(
        /^INVALID_NATIVE_COLLECTION_LINK$/,
      );
    },
  );

  it("plans multiple platforms in input order without mutating input", () => {
    const indexes = [6, 1, 8, 2];
    const urls = indexes.map((index) => fixture.valid[index].url);
    const before = structuredClone(urls);
    expect(
      planNativeCollectionLinks(
        ["BILIBILI", "DOUYIN", "XIAOHONGSHU", "ZHIHU"],
        urls,
      ),
    ).toEqual(indexes.map((index) => fixture.valid[index].expected));
    expect(urls).toEqual(before);
  });

  it.each([
    [[], [fixture.valid[0].url]],
    [["PUBLIC_WEB"], [fixture.valid[0].url]],
    [["BILIBILI", "BILIBILI"], [fixture.valid[0].url]],
    [["BILIBILI", "DOUYIN"], [fixture.valid[0].url]],
    [["DOUYIN"], [fixture.valid[0].url]],
    ["BILIBILI", [fixture.valid[0].url]],
    [["BILIBILI"], fixture.valid[0].url],
    [["BILIBILI"], []],
    [["BILIBILI"], [fixture.valid[0].url, fixture.valid[0].expected.canonical_url]],
    [["XIAOHONGSHU"], [fixture.valid[4].url, fixture.valid[5].url]],
    [["ZHIHU"], [fixture.valid[8].url, fixture.valid[9].url]],
    [["BILIBILI"], ["https://b23.tv/test"]],
    [[null], [fixture.valid[0].url]],
  ])("rejects invalid scope without echoing it %#", (platforms, links) => {
    expect(() =>
      planNativeCollectionLinks(platforms as readonly string[], links as readonly string[]),
    ).toThrowError(/^INVALID_NATIVE_LINK_SCOPE$/);
  });

  it("enforces link, identifier, slug, URL, and token bounds", () => {
    const urls = Array.from(
      { length: 101 },
      (_, index) => `https://www.douyin.com/video/${index + 1}`,
    );
    expect(planNativeCollectionLinks(["DOUYIN"], urls.slice(0, 100))).toHaveLength(100);
    expect(() => planNativeCollectionLinks(["DOUYIN"], urls)).toThrowError(
      /^INVALID_NATIVE_LINK_SCOPE$/,
    );
    for (const value of [
      `https://www.douyin.com/video/${"1".repeat(21)}`,
      `https://www.douyin.com/user/${"a".repeat(129)}`,
      `https://www.douyin.com/video/1?x=${"a".repeat(2048)}`,
      `${fixture.valid[4].url}?xsec_source=pc&xsec_token=${"a".repeat(1025)}`,
      `${fixture.valid[4].url}?xsec_source=pc&xsec_token=${"/".repeat(1024)}`,
    ])
      expect(() => parseNativeCollectionLink(value)).toThrowError(
        /^INVALID_NATIVE_COLLECTION_LINK$/,
      );
  });

  it("applies native scope only to new plain-link PREPARE", () => {
    expect(prepareStrategySchema.safeParse(prepare(["DOUYIN"])).success).toBe(false);
    expect(
      prepareStrategySchema.parse(prepare(["XIAOHONGSHU"], [fixture.valid[5].url])),
    ).toEqual(prepare(["XIAOHONGSHU"], [fixture.valid[5].url]));

    const research = prepare(["DOUYIN"], ["https://example.com/legacy-research"]);
    research.configuration.research = {
      version: 1,
      demandTypes: ["INQUIRY"],
      maxSoubei: 100,
      limits: { sources: 20, minutes: 30, modelCalls: 10 },
      stopAtAnyLimit: true,
      evidenceOrder: "SOURCE_MATCH_CONTEXT",
    } as never;
    expect(prepareStrategySchema.safeParse(research).success).toBe(true);

    const snapshot = {
      schema_version: "strategy-confirmation-v1",
      strategy_version_id: UUID,
      draft_id: UUID,
      draft_revision: 1,
      profile_version_id: UUID,
      profile_sha256: "a".repeat(64),
      configuration_sha256: "b".repeat(64),
      snapshot: {
        strategy_version_id: UUID,
        profile_version_id: UUID,
        configuration: prepare(["DOUYIN"], ["https://example.com/legacy-link"]).configuration,
        platforms: ["DOUYIN"],
        max_records: 25,
        max_runtime_seconds: 120,
      },
      state: "CONFIRMED",
      created_at: "2026-09-12T00:00:00Z",
      confirmed_at: "2026-09-12T00:00:01Z",
      revoked_at: null,
      is_current: true,
      profile_current: true,
    };
    expect(strategyViewSchema.parse(snapshot)).toEqual(snapshot);
  });
});
