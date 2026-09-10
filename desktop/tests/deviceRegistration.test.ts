import { describe, expect, it } from "vitest";
import {
  deviceRegistrationRequestSchema,
  deviceUuidSchema,
  parseDeviceIdentity,
  parseDeviceRegistrationReceipt,
} from "../src/shared/deviceRegistration";

const requestId = "aabbccdd-1234-5678-9012-abcdefabcdef";
const deviceId = "11223344-1234-5678-9012-abcdefabcdef";
const otherId = "22334455-1234-5678-9012-abcdefabcdef";
const request = { request_id: requestId, device_label: "Windows 工作机" };
const receipt = {
  ...request,
  device_id: deviceId,
  registered_at: "2026-09-10T12:13:14.123456+08:00",
  state: "SUCCEEDED",
};
const identity = {
  device_id: deviceId,
  device_status: "ACTIVE",
  credential_version: 0,
  public_key: null,
};
const publicKey = "A".repeat(43);

describe("device registration request", () => {
  it("normalizes Python strip whitespace, including C0 separators and NEL", () => {
    expect(deviceRegistrationRequestSchema.parse({
      ...request, device_label: "\u001c\u0085\u3000 Windows 工作机 \u001f\u00a0",
    })).toEqual(request);
  });

  it("preserves BOM and zero-width space, unlike JavaScript trim", () => {
    const input = { ...request, device_label: "\ufeff\u200b" };
    expect(deviceRegistrationRequestSchema.parse(input)).toEqual(input);
  });

  it("counts Unicode codepoints rather than UTF-16 units", () => {
    expect(deviceRegistrationRequestSchema.parse({
      ...request, device_label: ` ${"😀".repeat(128)} `,
    }).device_label).toBe("😀".repeat(128));
  });

  it.each([
    null, [], "{}", 3,
    {}, { request_id: requestId }, { device_label: "Windows" },
    { ...request, owner_user_id: "other" },
    { ...request, tenant_id: "other" },
    { ...request, device_id: deviceId },
    { ...request, public_key: publicKey },
    { ...request, registered_at: receipt.registered_at },
    { ...request, credential_version: 0 },
    { ...request, device_label: 123 },
    { ...request, device_label: null },
    { ...request, device_label: "" },
    { ...request, device_label: "\u001c\u0085 \t\n" },
    { ...request, device_label: "😀".repeat(129) },
    { ...request, device_label: "hello\0world" },
    { ...request, device_label: "\ud800" },
    { ...request, device_label: "\udfff" },
    { ...request, device_label: "\ud800x\udfff" },
  ])("rejects invalid request %#", (value) => {
    expect(deviceRegistrationRequestSchema.safeParse(value).success).toBe(false);
  });

  it.each(["", requestId.toUpperCase(), `${requestId}\n`, ` ${requestId}`, requestId.replaceAll("-", ""), "../identity", 42, null])(
    "rejects noncanonical UUID %#", (value) => {
      expect(deviceUuidSchema.safeParse(value).success).toBe(false);
      expect(deviceRegistrationRequestSchema.safeParse({ ...request, request_id: value }).success).toBe(false);
    },
  );

  it("accepts a canonical lowercase UUID", () => {
    expect(deviceUuidSchema.parse(requestId)).toBe(requestId);
  });

  it("enforces the 4096 UTF-8 byte boundary before normalization", () => {
    const prefix = { ...request, device_label: "x" };
    const overhead = new TextEncoder().encode(JSON.stringify(prefix)).length;
    const atLimit = { ...request, device_label: `${" ".repeat(4096 - overhead)}x` };
    expect(new TextEncoder().encode(JSON.stringify(atLimit)).length).toBe(4096);
    expect(deviceRegistrationRequestSchema.parse(atLimit).device_label).toBe("x");
    expect(deviceRegistrationRequestSchema.safeParse({
      ...atLimit, device_label: ` ${atLimit.device_label}`,
    }).success).toBe(false);
    expect(deviceRegistrationRequestSchema.safeParse({
      ...request, device_label: `${"\u3000".repeat(1400)}x`,
    }).success).toBe(false);
    expect(deviceRegistrationRequestSchema.safeParse({
      ...request, device_label: `${"\n".repeat(2200)}x`,
    }).success).toBe(false);
  });
});

describe("registration receipt", () => {
  it("returns the unchanged historical receipt bound to normalized original input", () => {
    expect(parseDeviceRegistrationReceipt(receipt, {
      ...request, device_label: `\u0085${request.device_label}\u001c`,
    })).toEqual(receipt);
  });

  it.each([
    "2026-09-10T12:13:14Z", "2024-02-29T00:00:00+00:00",
    "2026-09-10T12:13:14.000001-03:30",
  ])("accepts timezone ISO timestamps %s", (registered_at) => {
    const input = { ...receipt, registered_at };
    expect(parseDeviceRegistrationReceipt(input, request)).toEqual(input);
  });

  it.each([
    null, [], "{}", {}, { ...receipt, extra: "do-not-echo-secret" },
    { ...receipt, request_id: otherId }, { ...receipt, device_id: "not-uuid" },
    { ...receipt, device_id: deviceId.toUpperCase() },
    { ...receipt, device_label: "other" }, { ...receipt, device_label: ` ${request.device_label}` },
    { ...receipt, device_label: "\ud800" }, { ...receipt, state: "ACTIVE" },
    { ...receipt, state: "PENDING" }, { ...receipt, registered_at: null },
    ...["2026-09-10", "2026-09-10T12:13:14", "2026-02-29T12:13:14Z",
      "2026-09-31T12:13:14Z", "2026-09-10T25:00:00Z", "2026-09-10T12:13:14+25:00",
      "2026-09-10T12:13:14+08:99", "not-a-date", "0000-01-01T00:00:00Z",
    ].map((registered_at) => ({ ...receipt, registered_at })),
  ])("rejects malformed or mismatched receipt with fixed error %#", (value) => {
    expect(() => parseDeviceRegistrationReceipt(value, request))
      .toThrow(/^INVALID_DEVICE_REGISTRATION_RECEIPT$/);
  });

  it.each(Object.keys(receipt))("requires receipt field %s", (key) => {
    const value = { ...receipt } as Record<string, unknown>;
    delete value[key];
    expect(() => parseDeviceRegistrationReceipt(value, request)).toThrow(/^INVALID_DEVICE_REGISTRATION_RECEIPT$/);
  });

  it.each([
    null, { ...request, extra: "do-not-echo-secret" },
    { ...request, request_id: requestId.toUpperCase() },
    { ...request, device_label: ` ${" ".repeat(4096)}${request.device_label}` },
  ])("validates expected request strictly %#", (expected) => {
    expect(() => parseDeviceRegistrationReceipt(receipt, expected))
      .toThrow(/^INVALID_DEVICE_REGISTRATION_RECEIPT$/);
  });
});

describe("current device identity", () => {
  it("accepts the unbound 0/null identity", () => {
    expect(parseDeviceIdentity(identity, deviceId)).toEqual(identity);
  });

  it.each([1, 2_147_483_647])("accepts bound version %s and canonical Ed25519 key", (credential_version) => {
    const input = { ...identity, credential_version, public_key: publicKey };
    expect(parseDeviceIdentity(input, deviceId)).toEqual(input);
  });

  it("reports REVOKED truthfully without treating it as authorization", () => {
    const input = { ...identity, device_status: "REVOKED", credential_version: 1, public_key: publicKey };
    expect(parseDeviceIdentity(input, deviceId)).toEqual(input);
  });

  it.each([
    null, [], "{}", {}, { ...identity, extra: "do-not-echo-secret" },
    { ...identity, device_id: otherId }, { ...identity, device_id: deviceId.toUpperCase() },
    { ...identity, device_status: "CONNECTED" }, { ...identity, device_status: "active" },
    { ...identity, credential_version: 1 }, { ...identity, public_key: publicKey },
    ...[-1, 0.1, 2_147_483_648, Infinity, NaN, "1", true, null]
      .map((credential_version) => ({ ...identity, credential_version, public_key: publicKey })),
    ...["", "A".repeat(42), "A".repeat(44), `${"A".repeat(42)}B`, `${publicKey}=`, `${"A".repeat(42)}+`, `${"A".repeat(42)}/`, `${publicKey}\n`, 123]
      .map((public_key) => ({ ...identity, credential_version: 1, public_key })),
  ])("rejects malformed identity with fixed error %#", (value) => {
    expect(() => parseDeviceIdentity(value, deviceId)).toThrow(/^INVALID_DEVICE_IDENTITY$/);
  });

  it.each(Object.keys(identity))("requires identity field %s", (key) => {
    const value = { ...identity } as Record<string, unknown>;
    delete value[key];
    expect(() => parseDeviceIdentity(value, deviceId)).toThrow(/^INVALID_DEVICE_IDENTITY$/);
  });

  it.each([otherId, deviceId.toUpperCase(), "../device", null, 7])("rejects invalid expected device %#", (expected) => {
    expect(() => parseDeviceIdentity(identity, expected)).toThrow(/^INVALID_DEVICE_IDENTITY$/);
  });
});
