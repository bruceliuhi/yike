import { createPublicKey, generateKeyPairSync, verify } from "node:crypto";
import { describe, expect, it } from "vitest";
import { signDeviceChallenge } from "../src/main/deviceProofSigner";
import type { DeviceKeyMaterial } from "../src/main/deviceKeyVault";
import {
  deviceCompletionSchema,
  parseDeviceChallenge,
  type ExpectedDeviceChallenge,
} from "../src/shared/deviceProof";

const NOW = 1_789_000_000;
const REQUEST_ID = "00000000-0000-0000-0000-000000000001";
const DEVICE_ID = "00000000-0000-0000-0000-000000000002";
const CHALLENGE_ID = "00000000-0000-0000-0000-000000000003";
const FAILURE = "DEVICE_PROOF_SIGNING_FAILED";

function material(): DeviceKeyMaterial {
  const pair = generateKeyPairSync("ed25519");
  return Object.freeze({
    scope: Object.freeze({
      serviceOrigin: "https://pilot.example",
      userId: "TEST-device-owner",
      deviceId: DEVICE_ID,
    }),
    publicKey: pair.publicKey.export({ format: "jwk" }).x!,
    privateKey: pair.privateKey.export({ format: "pem", type: "pkcs8" }).toString(),
  });
}

function fixture(operation: "BIND" | "PROVE" = "BIND") {
  const key = material();
  const expected: ExpectedDeviceChallenge = {
    ...key.scope,
    publicKey: key.publicKey,
    request: {
      request_id: REQUEST_ID,
      operation,
      expected_credential_version: operation === "BIND" ? 0 : 3,
      public_key: operation === "BIND" ? key.publicKey : null,
    },
  };
  // ASCII fixture: this is Python's sorted, compact, ensure_ascii JSON spelling.
  const payload = {
    challenge_id: CHALLENGE_ID,
    device_id: DEVICE_ID,
    expected_credential_version: expected.request.expected_credential_version,
    expires_at: NOW + 120,
    nonce: Buffer.alloc(32, 7).toString("base64url"),
    operation,
    protocol: "yike-device-proof-v1",
    request_id: REQUEST_ID,
    session_digest: "a".repeat(64),
    target_public_key: key.publicKey,
    tenant_id: "TEST-tenant",
    user_id: expected.userId,
  };
  const challenge = {
    request_id: REQUEST_ID,
    challenge_id: CHALLENGE_ID,
    signing_payload: JSON.stringify(payload),
    expires_at: payload.expires_at,
  };
  return { key, expected, challenge, nowSeconds: NOW };
}

function rejected(input: Parameters<typeof signDeviceChallenge>[0]) {
  let caught: unknown;
  try {
    signDeviceChallenge(input);
  } catch (error) {
    caught = error;
  }
  expect(caught).toBeInstanceOf(Error);
  expect((caught as Error).message).toBe(FAILURE);
  expect((caught as Error).cause).toBeUndefined();
}

describe("main-only device challenge signer", () => {
  it.each(["BIND", "PROVE"] as const)("signs the exact %s bytes with the actual local Ed25519 key", operation => {
    const input = fixture(operation);
    const original = structuredClone(input);
    const completion = signDeviceChallenge(input);
    expect(deviceCompletionSchema.parse(completion)).toEqual(completion);
    expect(Object.keys(completion).sort()).toEqual(["previous_signature", "signature"]);
    expect(completion.previous_signature).toBeNull();
    const signature = Buffer.from(completion.signature, "base64url");
    expect(signature.length).toBe(64);
    expect(signature.toString("base64url")).toBe(completion.signature);
    const publicKey = createPublicKey(input.key.privateKey);
    expect(verify(null, Buffer.from(input.challenge.signing_payload, "utf8"), publicKey, signature)).toBe(true);
    expect(verify(null, Buffer.from(input.challenge.signing_payload + "\n", "utf8"), publicKey, signature)).toBe(false);
    expect(verify(null, Buffer.from(input.challenge.signing_payload, "utf8"), createPublicKey(material().privateKey), signature)).toBe(false);
    expect(input).toEqual(original);
    expect(signDeviceChallenge(input)).toEqual(completion);
  });

  it.each(["serviceOrigin", "userId", "deviceId"] as const)("rejects a key from a different %s", field => {
    const input = fixture();
    const changed = {
      serviceOrigin: "https://another.example",
      userId: "TEST-another-owner",
      deviceId: "00000000-0000-0000-0000-000000000004",
    };
    rejected({ ...input, key: { ...input.key, scope: { ...input.key.scope, [field]: changed[field] } } });
  });

  it("rejects an advertised public key different from the trusted expectation", () => {
    const input = fixture();
    rejected({ ...input, key: { ...input.key, publicKey: material().publicKey } });
  });

  it("rejects a different private key even when the advertised public key matches", () => {
    const input = fixture();
    rejected({ ...input, key: { ...input.key, privateKey: material().privateKey } });
  });

  it("rejects a non-Ed25519 private key", () => {
    const input = fixture();
    const pair = generateKeyPairSync("ec", { namedCurve: "prime256v1" });
    rejected({ ...input, key: { ...input.key, privateKey: pair.privateKey.export({ format: "pem", type: "pkcs8" }).toString() } });
  });

  it("does not expose invalid private material or crypto failure details", () => {
    const input = fixture();
    rejected({ ...input, key: { ...input.key, privateKey: "TEST-private-material-must-not-leak" } });
  });

  it("rejects noncanonical private PEM instead of silently accepting another record spelling", () => {
    const input = fixture();
    rejected({ ...input, key: { ...input.key, privateKey: input.key.privateKey + "\n" } });
  });

  it("rechecks expiry at signing rather than trusting an earlier successful parse", () => {
    const input = fixture();
    expect(parseDeviceChallenge(input.challenge, input.expected, NOW)).toBe(input.challenge.signing_payload);
    rejected({ ...input, nowSeconds: NOW + 120 });
  });

  it("rechecks a changed challenge after an earlier successful parse", () => {
    const input = fixture();
    parseDeviceChallenge(input.challenge, input.expected, NOW);
    input.challenge.signing_payload = input.challenge.signing_payload.replace("TEST-device-owner", "TEST-another-owner");
    rejected(input);
  });

  it("rejects another protocol domain", () => {
    const input = fixture();
    input.challenge.signing_payload = input.challenge.signing_payload.replace("yike-device-proof-v1", "yike-execution-operation-v1");
    rejected(input);
  });

  it("rejects an envelope expiry different from the payload", () => {
    const input = fixture();
    input.challenge.expires_at += 1;
    rejected(input);
  });

  it("does not accept a formerly parsed string as permission to sign arbitrary bytes", () => {
    const input = fixture();
    rejected({ ...input, challenge: parseDeviceChallenge(input.challenge, input.expected, NOW) });
  });
});
