import { z } from "zod";

const MAX_REQUEST_BYTES = 4_096;
const MAX_CREDENTIAL_VERSION = 2_147_483_647;
const BASE64URL_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_";
// Python str.strip uses Unicode White_Space plus U+001C..U+001F, not JS trim's BOM.
const PYTHON_EDGE_WHITESPACE = /^[\u0009-\u000d\u001c-\u0020\u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]+|[\u0009-\u000d\u001c-\u0020\u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]+$/g;

export const deviceUuidSchema = z.string().length(36)
  .regex(/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/);

function stripLabel(value: string): string {
  return value.replace(PYTHON_EDGE_WHITESPACE, "");
}

const unicodeLabelSchema = z.string().refine((value) => {
  for (const character of value) {
    const point = character.codePointAt(0)!;
    if (point === 0 || (point >= 0xd800 && point <= 0xdfff)) return false;
  }
  return true;
}, "invalid device label");

function validLabelLength(value: string): boolean {
  const length = Array.from(value).length;
  return length >= 1 && length <= 128;
}

export const deviceRegistrationRequestSchema = z.object({
  request_id: deviceUuidSchema,
  device_label: unicodeLabelSchema,
}).strict().superRefine((request, context) => {
  // Check serialized raw fields before stripping: huge whitespace is still input.
  if (new TextEncoder().encode(JSON.stringify(request)).length > MAX_REQUEST_BYTES) {
    context.addIssue({ code: "custom", message: "device registration request too large" });
  }
  if (!validLabelLength(stripLabel(request.device_label))) {
    context.addIssue({ code: "custom", message: "invalid device label length" });
  }
}).transform((request) => ({
  request_id: request.request_id,
  device_label: stripLabel(request.device_label),
}));

export type DeviceRegistrationRequest = z.infer<typeof deviceRegistrationRequestSchema>;

const deviceRegistrationReceiptSchema = z.object({
  request_id: deviceUuidSchema,
  device_id: deviceUuidSchema,
  device_label: unicodeLabelSchema.refine((value) =>
    value === stripLabel(value) && validLabelLength(value),
  "invalid canonical device label"),
  registered_at: z.string().datetime({ offset: true })
    .refine((value) => !value.startsWith("0000-"), "invalid registration time"),
  state: z.literal("SUCCEEDED"),
}).strict();

export type DeviceRegistrationReceipt = z.infer<typeof deviceRegistrationReceiptSchema>;

const publicKeySchema = z.string().length(43).regex(/^[A-Za-z0-9_-]+$/)
  .refine((value) => {
    const finalIndex = BASE64URL_ALPHABET.indexOf(value.at(-1) ?? "");
    // 32 bytes occupy 43 base64url characters, leaving two unused zero bits.
    return finalIndex >= 0 && finalIndex % 4 === 0;
  }, "invalid canonical public key");

const deviceIdentitySchema = z.object({
  device_id: deviceUuidSchema,
  device_status: z.enum(["ACTIVE", "REVOKED"]),
  credential_version: z.number().int().min(0).max(MAX_CREDENTIAL_VERSION),
  public_key: publicKeySchema.nullable(),
}).strict().refine((identity) =>
  (identity.credential_version === 0) === (identity.public_key === null),
"invalid device credential state");

export type DeviceIdentity = z.infer<typeof deviceIdentitySchema>;

export function parseDeviceRegistrationReceipt(
  raw: unknown,
  expectedRequest: unknown,
): DeviceRegistrationReceipt {
  try {
    const receipt = deviceRegistrationReceiptSchema.parse(raw);
    const expected = deviceRegistrationRequestSchema.parse(expectedRequest);
    if (receipt.request_id !== expected.request_id || receipt.device_label !== expected.device_label) {
      throw new Error("receipt mismatch");
    }
    return receipt;
  } catch {
    throw new Error("INVALID_DEVICE_REGISTRATION_RECEIPT");
  }
}

export function parseDeviceIdentity(
  raw: unknown,
  expectedDeviceId: unknown,
): DeviceIdentity {
  try {
    const identity = deviceIdentitySchema.parse(raw);
    if (identity.device_id !== deviceUuidSchema.parse(expectedDeviceId)) {
      throw new Error("identity mismatch");
    }
    // REVOKED is readable historical state, never permission to bind/prove/execute.
    return identity;
  } catch {
    throw new Error("INVALID_DEVICE_IDENTITY");
  }
}
