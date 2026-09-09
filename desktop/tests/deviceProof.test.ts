import { describe, expect, it } from "vitest";
import * as deviceProofModule from "../src/shared/deviceProof";
import {
  deviceChallengeRequestSchema,
  deviceCompletionSchema,
  deviceProofReceiptSchema,
  parseDeviceChallenge,
  type DeviceChallengeRequest,
  type DeviceProofReceipt,
  type ExpectedDeviceChallenge,
} from "../src/shared/deviceProof";

const DEVICE_ID = "11111111-1111-4111-8111-111111111111";
const REQUEST_ID = "22222222-2222-4222-8222-222222222222";
const CHALLENGE_ID = "33333333-3333-4333-8333-333333333333";
const PUBLIC_KEY = "11qYAYKxCrfVS_7TyWQHOg7hcvPapiMlrwIaaPcHURo";
const ZERO_KEY = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA";
const SIGNATURE = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA";
const NOW = 1_700_000_000;
const EXPIRES = NOW + 120;

const request: DeviceChallengeRequest = {
  request_id: REQUEST_ID,
  operation: "BIND",
  expected_credential_version: 0,
  public_key: PUBLIC_KEY,
};

const expected: ExpectedDeviceChallenge = {
  serviceOrigin: "https://service.example",
  userId: "user-1",
  deviceId: DEVICE_ID,
  publicKey: PUBLIC_KEY,
  request,
};

const basePayload = {
  challenge_id: CHALLENGE_ID,
  device_id: DEVICE_ID,
  expected_credential_version: 0,
  expires_at: EXPIRES,
  nonce: ZERO_KEY,
  operation: "BIND",
  protocol: "yike-device-proof-v1",
  request_id: REQUEST_ID,
  session_digest: "a".repeat(64),
  target_public_key: PUBLIC_KEY,
  tenant_id: "tenant-1",
  user_id: "user-1",
} as const;

function canonicalPayload(patch: Record<string, unknown> = {}) {
  return JSON.stringify(
    Object.fromEntries(
      Object.entries({ ...basePayload, ...patch }).sort(([left], [right]) =>
        left.localeCompare(right),
      ),
    ),
  );
}

function challenge(
  signing_payload = canonicalPayload(),
  patch: Record<string, unknown> = {},
) {
  return {
    request_id: REQUEST_ID,
    challenge_id: CHALLENGE_ID,
    signing_payload,
    expires_at: EXPIRES,
    ...patch,
  };
}

describe("device proof DTOs", () => {
  it("accepts only the fixed BIND and PROVE request shapes", () => {
    expect(deviceChallengeRequestSchema.parse(request)).toEqual(request);
    expect(
      deviceChallengeRequestSchema.parse({
        request_id: REQUEST_ID,
        operation: "PROVE",
        expected_credential_version: 7,
        public_key: null,
      }),
    ).toEqual({
      request_id: REQUEST_ID,
      operation: "PROVE",
      expected_credential_version: 7,
      public_key: null,
    });
    expect(
      deviceChallengeRequestSchema.parse({
        ...request,
        request_id: "00000000-0000-0000-0000-000000000000",
      }).request_id,
    ).toBe("00000000-0000-0000-0000-000000000000");
  });

  it.each([
    { ...request, request_id: "AAAAAAAA-AAAA-4AAA-8AAA-AAAAAAAAAAAA" },
    { ...request, operation: "ROTATE" },
    { ...request, expected_credential_version: true },
    { ...request, expected_credential_version: 1 },
    { ...request, public_key: null },
    { ...request, public_key: `${PUBLIC_KEY}=` },
    { ...request, public_key: `${PUBLIC_KEY.slice(0, -1)}B` },
    { ...request, extra: "field" },
    {
      request_id: REQUEST_ID,
      operation: "PROVE",
      expected_credential_version: 0,
      public_key: null,
    },
    {
      request_id: REQUEST_ID,
      operation: "PROVE",
      expected_credential_version: 1,
      public_key: PUBLIC_KEY,
    },
  ])("rejects a malformed or out-of-scope request: %j", (candidate) => {
    expect(deviceChallengeRequestSchema.safeParse(candidate).success).toBe(false);
  });

  it("normalizes the optional previous signature and rejects non-canonical proofs", () => {
    expect(deviceCompletionSchema.parse({ signature: SIGNATURE })).toEqual({
      signature: SIGNATURE,
      previous_signature: null,
    });
    for (const invalid of [
      { signature: `${SIGNATURE}=` },
      { signature: `${SIGNATURE.slice(0, -1)}B` },
      { signature: SIGNATURE, previous_signature: SIGNATURE },
      { signature: SIGNATURE, previous_signature: SIGNATURE, extra: true },
    ]) {
      expect(deviceCompletionSchema.safeParse(invalid).success).toBe(false);
    }
  });

  it("keeps receipts narrow and permits versions only for successful proof history", () => {
    expect(
      deviceProofReceiptSchema.parse({
        request_id: REQUEST_ID,
        device_id: DEVICE_ID,
        operation: "BIND",
        state: "SUCCEEDED",
        credential_version: 1,
      }),
    ).toEqual({
      request_id: REQUEST_ID,
      device_id: DEVICE_ID,
      operation: "BIND",
      state: "SUCCEEDED",
      credential_version: 1,
    });
    for (const invalid of [
      {
        request_id: REQUEST_ID,
        device_id: DEVICE_ID,
        operation: "BIND",
        state: "PENDING",
        credential_version: 1,
      },
      {
        request_id: REQUEST_ID,
        device_id: DEVICE_ID,
        operation: "PROVE",
        state: "SUCCEEDED",
        credential_version: null,
      },
      {
        request_id: REQUEST_ID,
        device_id: DEVICE_ID,
        operation: "ROTATE",
        state: "PENDING",
        credential_version: null,
      },
      {
        request_id: REQUEST_ID,
        device_id: DEVICE_ID,
        operation: "BIND",
        state: "PENDING",
        credential_version: null,
        token: "not-allowed",
      },
    ]) {
      expect(deviceProofReceiptSchema.safeParse(invalid).success).toBe(false);
    }
  });

  it("binds a receipt to its original request, device, operation, and result version", () => {
    const parseReceipt = (
      deviceProofModule as unknown as {
        parseDeviceProofReceipt?: (
          raw: unknown,
          expectedReceipt: {
            request: DeviceChallengeRequest;
            deviceId: string;
          },
        ) => DeviceProofReceipt;
      }
    ).parseDeviceProofReceipt;
    expect(parseReceipt).toBeTypeOf("function");
    const succeeded = {
      request_id: REQUEST_ID,
      device_id: DEVICE_ID,
      operation: "BIND",
      state: "SUCCEEDED",
      credential_version: 1,
    };
    expect(parseReceipt!(succeeded, { request, deviceId: DEVICE_ID })).toEqual(
      succeeded,
    );
    for (const invalid of [
      { ...succeeded, request_id: CHALLENGE_ID },
      { ...succeeded, device_id: CHALLENGE_ID },
      { ...succeeded, operation: "PROVE" },
      { ...succeeded, credential_version: 2 },
    ]) {
      expect(() =>
        parseReceipt!(invalid, { request, deviceId: DEVICE_ID }),
      ).toThrowError("INVALID_DEVICE_PROOF_RECEIPT");
    }
    const proveRequest: DeviceChallengeRequest = {
      request_id: REQUEST_ID,
      operation: "PROVE",
      expected_credential_version: 7,
      public_key: null,
    };
    expect(
      parseReceipt!(
        { ...succeeded, operation: "PROVE", credential_version: 7 },
        { request: proveRequest, deviceId: DEVICE_ID },
      ),
    ).toEqual({ ...succeeded, operation: "PROVE", credential_version: 7 });
  });
});

describe("parseDeviceChallenge", () => {
  it("returns the exact Python ensure_ascii payload bytes for Unicode and controls", () => {
    // Generated with Python json.dumps(sort_keys=True,separators=(",", ":"),ensure_ascii=True).
    const golden =
      '{"challenge_id":"33333333-3333-4333-8333-333333333333","device_id":"11111111-1111-4111-8111-111111111111","expected_credential_version":0,"expires_at":1700000120,"nonce":"AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA","operation":"BIND","protocol":"yike-device-proof-v1","request_id":"22222222-2222-4222-8222-222222222222","session_digest":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","target_public_key":"11qYAYKxCrfVS_7TyWQHOg7hcvPapiMlrwIaaPcHURo","tenant_id":"\\u79df\\u6237\\ud83d\\ude00","user_id":"\\u7528\\u007f\\u6237\\n"}';
    const unicodeExpected = {
      ...expected,
      userId: "用\u007f户\n",
    };

    expect(parseDeviceChallenge(challenge(golden), unicodeExpected, NOW)).toBe(
      golden,
    );
  });

  it("counts bounded identities by Unicode code point", () => {
    const emojiIdentity = "😀".repeat(256);
    const escapedIdentity = "\\ud83d\\ude00".repeat(256);
    const unicodePayload = canonicalPayload().replace(
      '"user_id":"user-1"',
      `"user_id":"${escapedIdentity}"`,
    );
    expect(
      parseDeviceChallenge(
        challenge(unicodePayload),
        { ...expected, userId: emojiIdentity },
        NOW,
      ),
    ).toBe(unicodePayload);
  });

  it("accepts only canonical HTTPS or loopback HTTP service origins", () => {
    expect(() =>
      parseDeviceChallenge(
        challenge(),
        { ...expected, serviceOrigin: "http://service.example" },
        NOW,
      ),
    ).toThrowError("INVALID_DEVICE_CHALLENGE");
    expect(
      parseDeviceChallenge(
        challenge(),
        { ...expected, serviceOrigin: "http://127.0.0.1:8000" },
        NOW,
      ),
    ).toBe(canonicalPayload());
  });

  it.each([
    ["wrong outer request", challenge(canonicalPayload(), { request_id: CHALLENGE_ID }), expected],
    ["wrong user", challenge(canonicalPayload({ user_id: "other" })), expected],
    ["wrong device", challenge(canonicalPayload({ device_id: CHALLENGE_ID })), expected],
    ["wrong request", challenge(canonicalPayload({ request_id: CHALLENGE_ID })), expected],
    ["wrong operation", challenge(canonicalPayload({ operation: "PROVE" })), expected],
    ["wrong version", challenge(canonicalPayload({ expected_credential_version: 1 })), expected],
    ["wrong key", challenge(canonicalPayload({ target_public_key: ZERO_KEY })), expected],
    ["wrong inner challenge", challenge(canonicalPayload({ challenge_id: REQUEST_ID })), expected],
    ["wrong inner expiry", challenge(canonicalPayload({ expires_at: EXPIRES - 1 })), expected],
    ["execution domain", challenge(canonicalPayload({ protocol: "yike-execution-v1" })), expected],
    ["bad session digest", challenge(canonicalPayload({ session_digest: "A".repeat(64) })), expected],
    ["bad nonce", challenge(canonicalPayload({ nonce: `${ZERO_KEY.slice(0, -1)}B` })), expected],
    ["extra payload field", challenge(canonicalPayload({ extra: "field" })), expected],
    ["extra envelope field", { ...challenge(), extra: "field" }, expected],
  ])("rejects binding mismatch: %s", (_name, raw, binding) => {
    expect(() => parseDeviceChallenge(raw, binding, NOW)).toThrowError(
      "INVALID_DEVICE_CHALLENGE",
    );
  });

  it.each([
    ["non-ASCII", canonicalPayload().replace("tenant-1", "租户")],
    ["whitespace", ` ${canonicalPayload()}`],
    [
      "duplicate key",
      canonicalPayload().replace(
        "{",
        `{"challenge_id":"${CHALLENGE_ID}",`,
      ),
    ],
    ["oversized", "{" + " ".repeat(8_192) + "}"],
  ])("rejects non-canonical signing bytes: %s", (_name, payload) => {
    expect(() => parseDeviceChallenge(challenge(payload), expected, NOW)).toThrowError(
      "INVALID_DEVICE_CHALLENGE",
    );
  });

  it("enforces the bounded current-time window without extending server validity", () => {
    expect(() => parseDeviceChallenge(challenge(), expected, EXPIRES)).toThrowError(
      "INVALID_DEVICE_CHALLENGE",
    );
    const tooFar = NOW + 151;
    expect(() =>
      parseDeviceChallenge(
        challenge(canonicalPayload({ expires_at: tooFar }), { expires_at: tooFar }),
        expected,
        NOW,
      ),
    ).toThrowError("INVALID_DEVICE_CHALLENGE");
    for (const invalidNow of [Number.NaN, 1.5, Number.MAX_SAFE_INTEGER + 1]) {
      expect(() => parseDeviceChallenge(challenge(), expected, invalidNow)).toThrowError(
        "INVALID_DEVICE_CHALLENGE",
      );
    }
  });

  it("does not echo rejected challenge content", () => {
    const secretMarker = "untrusted-secret-marker";
    expect(() =>
      parseDeviceChallenge(
        challenge(canonicalPayload({ user_id: secretMarker })),
        expected,
        NOW,
      ),
    ).toThrowError(/^INVALID_DEVICE_CHALLENGE$/);
  });
});
