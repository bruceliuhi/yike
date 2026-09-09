import { z } from "zod";

const MAX_REQUEST_VERSION = 2_147_483_646;
const MAX_RESULT_VERSION = 2_147_483_647;
const MAX_SIGNING_PAYLOAD_BYTES = 8_192;
const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const BASE64URL_PATTERN = /^[A-Za-z0-9_-]+$/;
const BASE64URL_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_";

const uuidSchema = z.string().length(36).regex(UUID_PATTERN);
const boundedIdentitySchema = z
  .string()
  .min(1)
  .refine((value) => Array.from(value).length <= 256);
const sessionDigestSchema = z.string().length(64).regex(/^[0-9a-f]{64}$/);

function canonicalBase64Url(size: number) {
  const length = Math.ceil((size * 8) / 6);
  const unusedBits = length * 6 - size * 8;
  return z
    .string()
    .length(length)
    .regex(BASE64URL_PATTERN)
    .refine((value) => {
      const finalIndex = BASE64URL_ALPHABET.indexOf(value.at(-1) ?? "");
      return finalIndex >= 0 && finalIndex % 2 ** unusedBits === 0;
    });
}

const publicKeySchema = canonicalBase64Url(32);
const signatureSchema = canonicalBase64Url(64);

export const deviceChallengeRequestSchema = z
  .object({
    request_id: uuidSchema,
    operation: z.enum(["BIND", "PROVE"]),
    expected_credential_version: z
      .number()
      .int()
      .min(0)
      .max(MAX_REQUEST_VERSION),
    public_key: publicKeySchema.nullable(),
  })
  .strict()
  .superRefine((request, context) => {
    const validBind =
      request.operation === "BIND" &&
      request.expected_credential_version === 0 &&
      request.public_key !== null;
    const validProve =
      request.operation === "PROVE" &&
      request.expected_credential_version > 0 &&
      request.public_key === null;
    if (!validBind && !validProve) {
      context.addIssue({ code: "custom", message: "invalid request binding" });
    }
  });

export type DeviceChallengeRequest = z.infer<
  typeof deviceChallengeRequestSchema
>;

export const deviceCompletionSchema = z
  .object({
    signature: signatureSchema,
    previous_signature: z.null().default(null),
  })
  .strict();

export type DeviceCompletion = z.infer<typeof deviceCompletionSchema>;

export const deviceProofReceiptSchema = z
  .object({
    request_id: uuidSchema,
    device_id: uuidSchema,
    operation: z.enum(["BIND", "PROVE"]),
    state: z.enum(["PENDING", "SUCCEEDED", "REJECTED", "EXPIRED"]),
    credential_version: z
      .number()
      .int()
      .min(1)
      .max(MAX_RESULT_VERSION)
      .nullable(),
  })
  .strict()
  .superRefine((receipt, context) => {
    const succeeded = receipt.state === "SUCCEEDED";
    if (succeeded !== (receipt.credential_version !== null)) {
      context.addIssue({ code: "custom", message: "invalid receipt state" });
    }
    if (
      succeeded &&
      receipt.operation === "BIND" &&
      receipt.credential_version !== 1
    ) {
      context.addIssue({ code: "custom", message: "invalid receipt version" });
    }
  });

export type DeviceProofReceipt = z.infer<typeof deviceProofReceiptSchema>;

export interface ExpectedDeviceProofReceipt {
  readonly request: DeviceChallengeRequest;
  readonly deviceId: string;
}

const expectedDeviceProofReceiptSchema = z
  .object({
    request: deviceChallengeRequestSchema,
    deviceId: uuidSchema,
  })
  .strict();

export function parseDeviceProofReceipt(
  raw: unknown,
  expected: ExpectedDeviceProofReceipt,
): DeviceProofReceipt {
  try {
    const receipt = deviceProofReceiptSchema.parse(raw);
    const binding = expectedDeviceProofReceiptSchema.parse(expected);
    const succeededVersion =
      binding.request.expected_credential_version +
      (binding.request.operation === "BIND" ? 1 : 0);
    if (
      receipt.request_id !== binding.request.request_id ||
      receipt.device_id !== binding.deviceId ||
      receipt.operation !== binding.request.operation ||
      (receipt.state === "SUCCEEDED" &&
        receipt.credential_version !== succeededVersion)
    ) {
      throw new Error("receipt mismatch");
    }
    return receipt;
  } catch {
    throw new Error("INVALID_DEVICE_PROOF_RECEIPT");
  }
}

export interface ExpectedDeviceChallenge {
  readonly serviceOrigin: string;
  readonly userId: string;
  readonly deviceId: string;
  readonly publicKey: string;
  readonly request: DeviceChallengeRequest;
}

const serviceOriginSchema = z
  .string()
  .min(1)
  .max(2_048)
  .refine((value) => {
    try {
      const url = new URL(value);
      const loopbackHttp =
        url.protocol === "http:" &&
        ["localhost", "127.0.0.1", "[::1]"].includes(url.hostname);
      return (
        (url.protocol === "https:" || loopbackHttp) &&
        !url.username &&
        !url.password &&
        url.origin === value
      );
    } catch {
      return false;
    }
  });

const expectedDeviceChallengeSchema = z
  .object({
    serviceOrigin: serviceOriginSchema,
    userId: boundedIdentitySchema,
    deviceId: uuidSchema,
    publicKey: publicKeySchema,
    request: deviceChallengeRequestSchema,
  })
  .strict()
  .superRefine((expected, context) => {
    if (
      expected.request.operation === "BIND" &&
      expected.request.public_key !== expected.publicKey
    ) {
      context.addIssue({ code: "custom", message: "invalid expected key" });
    }
  });

const deviceChallengeSchema = z
  .object({
    request_id: uuidSchema,
    challenge_id: uuidSchema,
    signing_payload: z.string().min(2).max(MAX_SIGNING_PAYLOAD_BYTES),
    expires_at: z.number().int().positive().max(Number.MAX_SAFE_INTEGER),
  })
  .strict();

const signingPayloadSchema = z
  .object({
    protocol: z.literal("yike-device-proof-v1"),
    tenant_id: boundedIdentitySchema,
    user_id: boundedIdentitySchema,
    device_id: uuidSchema,
    request_id: uuidSchema,
    challenge_id: uuidSchema,
    session_digest: sessionDigestSchema,
    operation: z.enum(["BIND", "PROVE"]),
    expected_credential_version: z
      .number()
      .int()
      .min(0)
      .max(MAX_REQUEST_VERSION),
    target_public_key: publicKeySchema,
    nonce: canonicalBase64Url(32),
    expires_at: z.number().int().positive().max(Number.MAX_SAFE_INTEGER),
  })
  .strict();

function pythonAsciiString(value: string): string {
  let encoded = '"';
  const shortEscapes: Record<number, string> = {
    8: "\\b",
    9: "\\t",
    10: "\\n",
    12: "\\f",
    13: "\\r",
  };
  for (let index = 0; index < value.length; index += 1) {
    const code = value.charCodeAt(index);
    if (code === 34) encoded += '\\"';
    else if (code === 92) encoded += "\\\\";
    else if (shortEscapes[code]) encoded += shortEscapes[code];
    else if (code < 32 || code > 126) {
      encoded += `\\u${code.toString(16).padStart(4, "0")}`;
    } else encoded += value[index];
  }
  return `${encoded}"`;
}

function pythonCanonicalJson(value: unknown): string {
  if (value === null) return "null";
  if (typeof value === "string") return pythonAsciiString(value);
  if (typeof value === "number" && Number.isSafeInteger(value)) {
    return String(value);
  }
  if (typeof value === "boolean") return value ? "true" : "false";
  if (typeof value === "object" && !Array.isArray(value)) {
    return `{${Object.entries(value)
      .sort(([left], [right]) => (left < right ? -1 : left > right ? 1 : 0))
      .map(
        ([key, item]) =>
          `${pythonAsciiString(key)}:${pythonCanonicalJson(item)}`,
      )
      .join(",")}}`;
  }
  throw new Error("unsupported value");
}

function invalidChallenge(): never {
  throw new Error("INVALID_DEVICE_CHALLENGE");
}

export function parseDeviceChallenge(
  raw: unknown,
  expected: ExpectedDeviceChallenge,
  nowSeconds: number,
): string {
  try {
    if (!Number.isSafeInteger(nowSeconds)) invalidChallenge();
    const envelope = deviceChallengeSchema.parse(raw);
    const binding = expectedDeviceChallengeSchema.parse(expected);
    if (
      envelope.signing_payload.length > MAX_SIGNING_PAYLOAD_BYTES ||
      [...envelope.signing_payload].some(
        (character) => character.charCodeAt(0) > 127,
      )
    ) {
      invalidChallenge();
    }
    const payload = signingPayloadSchema.parse(
      JSON.parse(envelope.signing_payload) as unknown,
    );
    if (pythonCanonicalJson(payload) !== envelope.signing_payload) {
      invalidChallenge();
    }
    if (
      envelope.request_id !== binding.request.request_id ||
      payload.user_id !== binding.userId ||
      payload.device_id !== binding.deviceId ||
      payload.request_id !== binding.request.request_id ||
      payload.operation !== binding.request.operation ||
      payload.expected_credential_version !==
        binding.request.expected_credential_version ||
      payload.target_public_key !== binding.publicKey ||
      payload.challenge_id !== envelope.challenge_id ||
      payload.expires_at !== envelope.expires_at ||
      payload.expires_at <= nowSeconds ||
      payload.expires_at - nowSeconds > 150
    ) {
      invalidChallenge();
    }
    return envelope.signing_payload;
  } catch {
    return invalidChallenge();
  }
}
