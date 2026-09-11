import { describe, expect, it } from "vitest";
import {
  confirmStrategySchema,
  prepareStrategySchema,
  revokeStrategySchema,
  strategyConfigurationSchema,
  strategyReceiptSchema,
  strategyUuidSchema,
  strategyViewSchema,
  type ConfirmStrategyRequest,
  type PrepareStrategyRequest,
  type RevokeStrategyRequest,
  type StrategyReceipt,
  type StrategyView,
} from "../src/shared/researchStrategies";
import {
  parseStrategyReceipt,
  parseStrategyView,
  strategyPrepareRequest,
} from "../src/renderer/domain/researchStrategies";
import type { TaskDraft } from "../src/renderer/domain/models";

const PROFILE_ID = "11111111-1111-4111-8111-111111111111";
const STRATEGY_ID = "22222222-2222-4222-8222-222222222222";
const PREPARE_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
const CONFIRM_ID = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";
const REVOKE_ID = "cccccccc-cccc-4ccc-8ccc-cccccccccccc";
const DRAFT_ID = "dddddddd-dddd-4ddd-8ddd-dddddddddddd";
const PROFILE_SHA = "a".repeat(64);
const CONFIGURATION_SHA = "b".repeat(64);

function draft(): TaskDraft {
  return {
    id: DRAFT_ID,
    revision: 7,
    name: "跨行业中文研究",
    profileId: PROFILE_ID,
    profileVersion: 3,
    terms: [
      { id: "term-1", value: "  设备  采购  ", origin: "manual", edited: true },
      { id: "term-2", value: "CRM 服务", origin: "ai", edited: false },
    ],
    exclusions: [
      { id: "exclude-1", value: "招聘", origin: "manual", edited: false },
    ],
    removed: [],
    source: "links",
    links:
      "  https://example.com/公开需求?a=1,2;3  \r\n\rhttps://example.org/path  \n  ",
    platforms: ["xhs", "douyin", "bilibili", "zhihu"],
    accounts: { xhs: "account-xhs", douyin: "account-douyin" },
    mode: "monitor",
    schedule: {
      kind: "interval",
      times: ["08:00", "19:30"],
      interval: 2.5,
      start: "08:00",
      end: "20:00",
      timezone: "Asia/Shanghai",
    },
    research: {
      version: 1,
      demandTypes: ["INQUIRY", "COMPARISON", "CHANGE"],
      maxSoubei: 120,
      limits: { sources: 80, minutes: 25, modelCalls: 30 },
      stopAtAnyLimit: true,
      evidenceOrder: "SOURCE_MATCH_CONTEXT",
    },
    savedAt: null,
    suggestionProfile: null,
  };
}

function prepareRequest(): PrepareStrategyRequest {
  return strategyPrepareRequest(draft(), PREPARE_ID, {
    max_records: 250,
    max_runtime_seconds: 900,
  });
}

function origin() {
  return {requestId:PREPARE_ID,suggestionId:`suggestion_${'e'.repeat(64)}`,userId:'user-1',
    opportunityId:'opportunity-1',profileVersionId:PROFILE_ID,sourceUrl:'https://example.com/buyer',
    evidenceVersion:'version-1',accountScope:{id:'tenant-1',version:1},
    originalScope:'原始范围',additionalScope:'同类需求'};
}

/** Synthetic complete receipt fixture. Cross-language receipts belong to the live test. */
function preparedReceipt(
  state: StrategyReceipt["state"] = "DRAFT",
): StrategyReceipt {
  const request = prepareRequest();
  return {
    schema_version: "strategy-confirmation-v1",
    request_id: request.request_id,
    operation: "PREPARE",
    strategy_version_id: STRATEGY_ID,
    draft_id: request.draft_id,
    draft_revision: request.draft_revision,
    profile_version_id: request.profile_version_id,
    profile_sha256: PROFILE_SHA,
    configuration_sha256: CONFIGURATION_SHA,
    snapshot: {
      profile_version_id: request.profile_version_id,
      strategy_version_id: STRATEGY_ID,
      configuration: request.configuration,
      platforms: request.platforms,
      max_records: request.max_records,
      max_runtime_seconds: request.max_runtime_seconds,
    },
    state,
    recorded_at: "2026-09-10T10:20:30.123456+08:00",
  };
}

function confirmRequest(): ConfirmStrategyRequest {
  return {
    schema_version: "strategy-confirmation-v1",
    request_id: CONFIRM_ID,
    strategy_version_id: STRATEGY_ID,
    configuration_sha256: CONFIGURATION_SHA,
    human_confirmed: true,
  };
}

function revokeRequest(): RevokeStrategyRequest {
  return {
    schema_version: "strategy-confirmation-v1",
    request_id: REVOKE_ID,
    strategy_version_id: STRATEGY_ID,
  };
}

function operationReceipt(
  request: ConfirmStrategyRequest | RevokeStrategyRequest,
): StrategyReceipt {
  return {
    ...preparedReceipt(),
    request_id: request.request_id,
    operation: "human_confirmed" in request ? "CONFIRM" : "REVOKE",
    state: "human_confirmed" in request ? "CONFIRMED" : "REVOKED",
  };
}

function strategyView(): StrategyView {
  const prepared = preparedReceipt();
  return {
    schema_version: "strategy-confirmation-v1",
    strategy_version_id: prepared.strategy_version_id,
    draft_id: prepared.draft_id,
    draft_revision: prepared.draft_revision,
    profile_version_id: prepared.profile_version_id,
    profile_sha256: prepared.profile_sha256,
    configuration_sha256: prepared.configuration_sha256,
    snapshot: prepared.snapshot,
    state: "CONFIRMED",
    created_at: "2026-09-10T10:00:00+08:00",
    confirmed_at: "2026-09-10T10:21:00+08:00",
    revoked_at: null,
    is_current: false,
    profile_current: true,
  };
}

describe("research strategy shared contract", () => {
  it.each([false,true])('preserves similar-research origin through actual preparation and receipt parsing, public=%s',publicSource=>{
    const source=draft();if(publicSource){source.platforms=['web'];source.source='search';source.links='';source.mode='once';}
    source.research!.provenance=origin();const before=structuredClone(source);
    const request=strategyPrepareRequest(source,PREPARE_ID,{max_records:250,max_runtime_seconds:900});
    expect(request.configuration.research!.provenance).toEqual(origin());
    const receipt=preparedReceipt();receipt.snapshot.configuration=request.configuration;receipt.snapshot.platforms=request.platforms;
    expect(parseStrategyReceipt(receipt,request).snapshot.configuration.research!.provenance).toEqual(origin());
    source.research!.provenance!.accountScope!.id='changed';
    expect(request.configuration.research!.provenance!.accountScope.id).toBe('tenant-1');
    expect(before.research!.provenance).toEqual(origin());
  });

  it('rejects mismatched or malformed origins without dropping their fields',()=>{
    for(const change of [{accountScope:undefined},{accountScope:{id:'tenant-1',version:2}},
      {profileVersionId:STRATEGY_ID},{requestId:'not-uuid'},{suggestionId:'invented'},
      {sourceUrl:'https://name:password@example.com/buyer'},{extra:true},{originalScope:'bad\u0000'}]){
      const source=draft();source.research!.provenance={...origin(),...change} as any;
      expect(()=>strategyPrepareRequest(source,PREPARE_ID,{max_records:250,max_runtime_seconds:900})).toThrow();
    }
  });

  it('omits absent provenance exactly and includes every origin field in the configuration',()=>{
    const plain=prepareRequest();expect(plain.configuration.research).not.toHaveProperty('provenance');
    for(const field of ['opportunityId','evidenceVersion','originalScope','additionalScope'] as const){
      const source=draft();source.research!.provenance={...origin(),[field]:`${origin()[field]}-changed`};
      const request=strategyPrepareRequest(source,PREPARE_ID,{max_records:250,max_runtime_seconds:900});
      expect(request.configuration.research!.provenance![field]).toBe(`${origin()[field]}-changed`);
    }
  });
  it("accepts public domain names beginning with fc/fd without allowing private IPv6 literals", () => {
    const request = prepareRequest();
    for (const link of ["https://fc.example.com/a", "https://fd.example.com/a"]) {
      const configuration = { ...request.configuration, links: [link] };
      expect(strategyConfigurationSchema.safeParse(configuration).success).toBe(true);
    }
    for (const link of ["https://[fc00::1]/a", "https://[fd12::1]/a"]) {
      expect(strategyConfigurationSchema.safeParse({ ...request.configuration, links: [link] }).success).toBe(false);
    }
  });

  it("rejects equal interval bounds only for policy v1 and preserves unversioned history", () => {
    const request = prepareRequest();
    const schedule = { ...request.configuration.schedule!, kind: "interval" as const, start: "08:00", end: "08:00" };
    const legacy = { ...request.configuration, schedule };
    expect(strategyConfigurationSchema.parse(legacy)).toEqual(legacy);
    const modern = { ...legacy, schedule: { ...schedule, policyVersion: 1 as const } };
    expect(strategyConfigurationSchema.safeParse(modern).success).toBe(false);
    expect(strategyConfigurationSchema.safeParse({ ...modern, schedule: { ...modern.schedule, end: "07:00" } }).success).toBe(true);
    expect(strategyConfigurationSchema.safeParse({ ...modern, schedule: { ...modern.schedule, kind: "daily" } }).success).toBe(true);
  });

  it("maps the full Chinese draft without changing or silently narrowing it", () => {
    const source = draft();
    const before = structuredClone(source);
    const request = strategyPrepareRequest(source, PREPARE_ID, {
      max_records: 250,
      max_runtime_seconds: 900,
    });

    expect(request).toEqual({
      schema_version: "strategy-confirmation-v1",
      request_id: PREPARE_ID,
      draft_id: DRAFT_ID,
      draft_revision: 7,
      profile_version_id: PROFILE_ID,
      configuration: {
        schema_version: "research-strategy-v1",
        name: "跨行业中文研究",
        source: "links",
        keywords: ["  设备  采购  ", "CRM 服务"],
        exclusions: ["招聘"],
        links: [
          "https://example.com/公开需求?a=1,2;3",
          "https://example.org/path",
        ],
        mode: "monitor",
        schedule: before.schedule,
        research: before.research,
      },
      platforms: ["XIAOHONGSHU", "DOUYIN", "BILIBILI", "ZHIHU"],
      max_records: 250,
      max_runtime_seconds: 900,
    });
    expect(source).toEqual(before);
    expect(prepareStrategySchema.parse(request)).toEqual(request);
  });

  it("maps absent research to null and still preserves inactive search, links, and schedule", () => {
    const source = draft();
    delete source.research;
    source.source = "search";
    const request = strategyPrepareRequest(source, PREPARE_ID, {
      max_records: 1,
      max_runtime_seconds: 1,
    });
    expect(request.configuration.research).toBeNull();
    expect(request.configuration.keywords).toEqual([
      "  设备  采购  ",
      "CRM 服务",
    ]);
    expect(request.configuration.links).toHaveLength(2);
    expect(request.configuration.schedule).toEqual(source.schedule);
  });

  it("rejects unsupported provenance without mutating the caller draft", () => {
    for (const field of ["provenance", "coverageProvenance"] as const) {
      const source = draft();
      Object.assign(source.research!, { [field]: { marker: "DO_NOT_ECHO" } });
      const before = structuredClone(source);
      expect(() =>
        strategyPrepareRequest(source, PREPARE_ID, {
          max_records: 10,
          max_runtime_seconds: 30,
        }),
      ).toThrowError(/^[^]*$/);
      expect(source).toEqual(before);
      try {
        strategyPrepareRequest(source, PREPARE_ID, {
          max_records: 10,
          max_runtime_seconds: 30,
        });
      } catch (error) {
        expect(String(error)).not.toContain("DO_NOT_ECHO");
      }
    }
  });

  it("preserves either the legacy schedule or the explicit policy version without defaulting", () => {
    const legacy = draft();
    const legacyRequest = strategyPrepareRequest(legacy, PREPARE_ID, {
      max_records: 10,
      max_runtime_seconds: 30,
    });
    expect(legacyRequest.configuration.schedule).not.toHaveProperty("policyVersion");

    const current = draft();
    Object.assign(current.schedule, { policyVersion: 1 });
    const before = structuredClone(current);
    const currentRequest = strategyPrepareRequest(current, PREPARE_ID, {
      max_records: 10,
      max_runtime_seconds: 30,
    });
    expect(currentRequest.configuration.schedule).toEqual(current.schedule);
    expect(current).toEqual(before);

    for (const invalid of [null, false, undefined, 2]) {
      const source = draft();
      Object.assign(source.schedule, { policyVersion: invalid });
      const original = structuredClone(source);
      expect(() =>
        strategyPrepareRequest(source, PREPARE_ID, {
          max_records: 10,
          max_runtime_seconds: 30,
        }),
      ).toThrow();
      expect(source).toEqual(original);
    }
  });

  it("enforces exact required nullable fields and rejects extras without echoing them", () => {
    const request = prepareRequest();
    expect(strategyConfigurationSchema.safeParse(request.configuration).success).toBe(true);
    expect(strategyConfigurationSchema.safeParse({ ...request.configuration, mode:'once', schedule: null }).success).toBe(true);
    const { schedule: _schedule, ...missingSchedule } = request.configuration;
    expect(strategyConfigurationSchema.safeParse(missingSchedule).success).toBe(false);
    const extra = strategyConfigurationSchema.safeParse({
      ...request.configuration,
      SYNTHETIC_SECRET_MUST_NOT_APPEAR: true,
    });
    expect(extra.success).toBe(false);
    if (!extra.success)
      expect(extra.error.message).not.toContain("SYNTHETIC_SECRET_MUST_NOT_APPEAR");

    for (const schema of [
      prepareStrategySchema,
      confirmStrategySchema,
      revokeStrategySchema,
      strategyReceiptSchema,
      strategyViewSchema,
    ]) {
      expect(schema).toBeDefined();
    }
  });

  it("rejects malformed identifiers, numbers, booleans, arrays, URLs, timezones, and Unicode", () => {
    const request = prepareRequest();
    const invalid: unknown[] = [
      { ...request, request_id: PREPARE_ID.toUpperCase() },
      { ...request, draft_revision: true },
      { ...request, max_records: 1.5 },
      { ...request, max_runtime_seconds: Number.POSITIVE_INFINITY },
      { ...request, platforms: ["PUBLIC_WEB", "PUBLIC_WEB"] },
      {
        ...request,
        configuration: { ...request.configuration, keywords: ["A  B", " a b "] },
      },
      {
        ...request,
        configuration: { ...request.configuration, links: ["ftp://example.com/a"] },
      },
      {
        ...request,
        configuration: {
          ...request.configuration,
          schedule: { ...request.configuration.schedule!, timezone: "Mars/Olympus" },
        },
      },
      {
        ...request,
        configuration: { ...request.configuration, name: "bad\u0000name" },
      },
      {
        ...request,
        configuration: {
          ...request.configuration,
          research: { ...request.configuration.research!, maxSoubei: true },
        },
      },
    ];
    for (const value of invalid)
      expect(prepareStrategySchema.safeParse(value).success).toBe(false);
    expect(strategyUuidSchema.safeParse(PROFILE_ID).success).toBe(true);
  });

  it("enforces the 65536-byte configuration limit", () => {
    const request = prepareRequest();
    const oversized = {
      ...request.configuration,
      links: Array.from(
        { length: 40 },
        (_, index) => `https://example.com/${index}/${"中".repeat(600)}`,
      ),
    };
    expect(new TextEncoder().encode(JSON.stringify(oversized)).length).toBeGreaterThan(65536);
    expect(strategyConfigurationSchema.safeParse(oversized).success).toBe(false);
  });

  it("counts Unicode code points like the Python contract", () => {
    const request = prepareRequest();
    expect(
      strategyConfigurationSchema.safeParse({
        ...request.configuration,
        name: "🚀".repeat(60),
      }).success,
    ).toBe(true);
    expect(
      strategyConfigurationSchema.safeParse({
        ...request.configuration,
        name: "🚀".repeat(61),
      }).success,
    ).toBe(false);
  });
});

describe("research strategy receipt and current-view binding", () => {
  it("accepts a fully bound PREPARE receipt in every historical replay state", () => {
    for (const state of ["DRAFT", "CONFIRMED", "REVOKED"] as const) {
      const receipt = preparedReceipt(state);
      expect(Object.keys(receipt)).toHaveLength(12);
      expect(parseStrategyReceipt(receipt, prepareRequest())).toEqual(receipt);
    }
  });

  it("accepts fully bound CONFIRM and REVOKE receipts", () => {
    const prepared = preparedReceipt();
    const confirmation = operationReceipt(confirmRequest());
    const revocation = operationReceipt(revokeRequest());
    expect(parseStrategyReceipt(confirmation, confirmRequest(), prepared)).toEqual(
      confirmation,
    );
    expect(parseStrategyReceipt(revocation, revokeRequest(), prepared)).toEqual(
      revocation,
    );
  });

  it("rejects malformed expected requests before trusting a valid-looking receipt", () => {
    const malformed = { ...prepareRequest(), max_records: true } as unknown as PrepareStrategyRequest;
    expect(() => parseStrategyReceipt(preparedReceipt(), malformed)).toThrow();
  });

  it("rejects extra or missing receipt fields and inconsistent top-level snapshot IDs", () => {
    const request = prepareRequest();
    const receipt = preparedReceipt();
    const { recorded_at: _recordedAt, ...missing } = receipt;
    for (const value of [
      { ...receipt, authority: "SYNTHETIC_SECRET_MUST_NOT_APPEAR" },
      missing,
      {
        ...receipt,
        snapshot: { ...receipt.snapshot, strategy_version_id: CONFIRM_ID },
      },
      {
        ...receipt,
        snapshot: { ...receipt.snapshot, profile_version_id: CONFIRM_ID },
      },
    ]) {
      expect(() => parseStrategyReceipt(value, request)).toThrow();
      try {
        parseStrategyReceipt(value, request);
      } catch (error) {
        expect(String(error)).not.toContain("SYNTHETIC_SECRET_MUST_NOT_APPEAR");
      }
    }
  });

  it("rejects mismatched prepare configuration, platform order, budgets, and draft binding", () => {
    const request = prepareRequest();
    const receipt = preparedReceipt();
    const changedValues = [
      { ...receipt, draft_revision: request.draft_revision - 1 },
      {
        ...receipt,
        snapshot: {
          ...receipt.snapshot,
          configuration: { ...receipt.snapshot.configuration, name: "另一个任务" },
        },
      },
      {
        ...receipt,
        snapshot: {
          ...receipt.snapshot,
          platforms: [...receipt.snapshot.platforms].reverse(),
        },
      },
      {
        ...receipt,
        snapshot: { ...receipt.snapshot, max_records: receipt.snapshot.max_records + 1 },
      },
      {
        ...receipt,
        snapshot: {
          ...receipt.snapshot,
          max_runtime_seconds: receipt.snapshot.max_runtime_seconds + 1,
        },
      },
    ];
    for (const value of changedValues)
      expect(() => parseStrategyReceipt(value, request)).toThrow();
  });

  it("requires the prepared binding and exact original confirm/revoke request", () => {
    const prepared = preparedReceipt();
    const confirmation = operationReceipt(confirmRequest());
    const revocation = operationReceipt(revokeRequest());
    expect(() => parseStrategyReceipt(confirmation, confirmRequest())).toThrow();
    expect(() => parseStrategyReceipt(revocation, revokeRequest())).toThrow();
    expect(() =>
      parseStrategyReceipt(
        { ...confirmation, request_id: REVOKE_ID },
        confirmRequest(),
        prepared,
      ),
    ).toThrow();
    expect(() =>
      parseStrategyReceipt(
        confirmation,
        { ...confirmRequest(), configuration_sha256: "c".repeat(64) },
        prepared,
      ),
    ).toThrow();
    expect(() =>
      parseStrategyReceipt(
        { ...confirmation, profile_sha256: "c".repeat(64) },
        confirmRequest(),
        prepared,
      ),
    ).toThrow();
    expect(() =>
      parseStrategyReceipt(
        { ...revocation, state: "CONFIRMED" },
        revokeRequest(),
        prepared,
      ),
    ).toThrow();
  });

  it("parses the full current view while treating mutable current state separately", () => {
    const prepared = preparedReceipt("DRAFT");
    const view = strategyView();
    expect(Object.keys(view)).toHaveLength(14);
    expect(parseStrategyView(view, prepared)).toEqual(view);
    expect(parseStrategyView({ ...view, state: "REVOKED", revoked_at: "2026-09-10T11:00:00Z" }, prepared).state).toBe(
      "REVOKED",
    );
    for (const changed of [
      { ...view, draft_id: REVOKE_ID },
      { ...view, configuration_sha256: "c".repeat(64) },
      { ...view, profile_sha256: "c".repeat(64) },
      { ...view, snapshot: { ...view.snapshot, max_records: 999 } },
      { ...view, extra: true },
    ])
      expect(() => parseStrategyView(changed, prepared)).toThrow();
  });
});
