import { createHash } from "node:crypto";
import { constants } from "node:fs";
import { lstat, mkdir, open } from "node:fs/promises";
import path from "node:path";
import { z } from "zod";
import type { DeviceKeyProtection } from "./deviceKeyVault";
import type { NativeOutreachOutcome } from "./outreachConsumer";
import type { OutreachConsumptionScope } from "./outreachConsumptionJournal";

export interface OutreachResultRecord {
  readonly requestId: string;
  readonly claimId: string;
  readonly deviceId: string;
  readonly contextSha256: string;
  readonly resultId: string;
  readonly outcome: NativeOutreachOutcome;
}
export interface OutreachResultOutbox {
  read(
    scope: OutreachConsumptionScope,
    requestId: string,
  ): Promise<OutreachResultRecord | null>;
  put(
    scope: OutreachConsumptionScope,
    record: OutreachResultRecord,
  ): Promise<OutreachResultRecord>;
}

const MAX_BYTES = 65_536;
const uuid = z
  .string()
  .regex(
    /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/,
  );
const sha = z.string().regex(/^[0-9a-f]{64}$/);
const opaque = z.string().regex(/^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$/);
const time = z.string().max(48).datetime({ offset: true });
const proof = z
  .object({
    kind: z.enum(["ACCEPTED", "REJECTED_NOT_DELIVERED"]),
    externalId: opaque,
    sha256: sha,
    observedAt: time,
  })
  .strict();
const outcomeSchema = z.discriminatedUnion("status", [
  z
    .object({
      status: z.literal("SENT"),
      confirmed: z.literal(true),
      confirmedNotDelivered: z
        .null()
        .optional()
        .transform((value) => value ?? null),
      proof: proof.extend({ kind: z.literal("ACCEPTED") }),
    })
    .strict(),
  z
    .object({
      status: z.literal("FAILED"),
      confirmed: z.literal(true),
      confirmedNotDelivered: z.literal(true),
      proof: proof.extend({ kind: z.literal("REJECTED_NOT_DELIVERED") }),
    })
    .strict(),
]);
const recordSchema = z
  .object({
    requestId: uuid,
    claimId: uuid,
    deviceId: uuid,
    contextSha256: sha,
    resultId: uuid,
    outcome: outcomeSchema,
  })
  .strict();
type ErrorCode =
  | "INVALID_SCOPE"
  | "INVALID_RECORD"
  | "PROTECTION_UNAVAILABLE"
  | "PROTECTION_FAILED"
  | "STORAGE_FAILED"
  | "CONFLICT";
const pendingFiles = new Map<string, Promise<void>>();
function fail(code: ErrorCode): never {
  throw new Error(`OUTREACH_RESULT_${code}`);
}
function hasCode(error: unknown, code: string) {
  return error instanceof Error && "code" in error && error.code === code;
}
function exact(
  value: unknown,
  fields: string[],
): value is Record<string, unknown> {
  return (
    value !== null &&
    typeof value === "object" &&
    !Array.isArray(value) &&
    Reflect.ownKeys(value).length === fields.length &&
    fields.every((field) => Object.hasOwn(value, field))
  );
}
function identity(value: unknown): value is string {
  return (
    typeof value === "string" &&
    Array.from(value).length >= 1 &&
    Array.from(value).length <= 256 &&
    value === value.trim() &&
    !/^[\u0085]|[\u0085]$/.test(value) &&
    !/[\x00-\x1f]/.test(value) &&
    !Array.from(value).some((character) => /^[\ud800-\udfff]$/.test(character))
  );
}
function parseScope(value: unknown): OutreachConsumptionScope {
  try {
    if (!exact(value, ["serviceOrigin", "userId", "tenantId"]))
      throw new Error();
    const { serviceOrigin, userId, tenantId } = value;
    if (
      typeof serviceOrigin !== "string" ||
      serviceOrigin.length > 2048 ||
      !identity(userId) ||
      !identity(tenantId)
    )
      throw new Error();
    const url = new URL(serviceOrigin),
      loopback =
        url.protocol === "http:" &&
        ["localhost", "127.0.0.1", "[::1]"].includes(url.hostname);
    if (
      url.origin !== serviceOrigin ||
      (url.protocol !== "https:" && !loopback) ||
      url.username ||
      url.password
    )
      throw new Error();
    return { serviceOrigin, userId, tenantId };
  } catch {
    return fail("INVALID_SCOPE");
  }
}
function parseRecord(value: unknown): OutreachResultRecord {
  const parsed = recordSchema.safeParse(value);
  if (!parsed.success) return fail("INVALID_RECORD");
  return parsed.data;
}
function copy(record: OutreachResultRecord): OutreachResultRecord {
  return structuredClone(record);
}
function requireProtection(protection: DeviceKeyProtection) {
  let available = false;
  try {
    available = protection.isEncryptionAvailable() === true;
  } catch {
    /* fixed error */
  }
  if (!available) fail("PROTECTION_UNAVAILABLE");
}
async function directoryReady(
  directory: string,
  create: boolean,
): Promise<boolean> {
  try {
    if (create) await mkdir(directory, { recursive: true, mode: 0o700 });
    const info = await lstat(directory);
    if (!info.isDirectory() || info.isSymbolicLink()) throw new Error();
    return true;
  } catch (error) {
    if (!create && hasCode(error, "ENOENT")) return false;
    return fail("STORAGE_FAILED");
  }
}
async function syncDirectory(directory: string) {
  if (process.platform === "win32") return;
  let handle;
  let failed = false;
  try {
    handle = await open(
      directory,
      constants.O_RDONLY | (constants.O_NOFOLLOW ?? 0),
    );
    if (!(await handle.stat()).isDirectory()) throw new Error();
    await handle.sync();
  } catch {
    failed = true;
  } finally {
    try {
      await handle?.close();
    } catch {
      failed = true;
    }
  }
  if (failed) fail("STORAGE_FAILED");
}
async function syncResultDirectories(directory: string) {
  await syncDirectory(directory);
  await syncDirectory(path.dirname(directory));
}
function same(left: OutreachResultRecord, right: OutreachResultRecord) {
  return JSON.stringify(left) === JSON.stringify(right);
}
async function readExisting(
  filename: string,
  scope: OutreachConsumptionScope,
  requestId: string,
  protection: DeviceKeyProtection,
): Promise<OutreachResultRecord | null> {
  let metadata;
  try {
    metadata = await lstat(filename);
  } catch (error) {
    if (hasCode(error, "ENOENT")) return null;
    return fail("STORAGE_FAILED");
  }
  if (
    !metadata.isFile() ||
    metadata.isSymbolicLink() ||
    metadata.size < 1 ||
    metadata.size > MAX_BYTES
  )
    fail("INVALID_RECORD");
  let bytes: Buffer;
  try {
    const handle = await open(
      filename,
      constants.O_RDWR | (constants.O_NOFOLLOW ?? 0),
    );
    try {
      const actual = await handle.stat();
      if (
        !actual.isFile() ||
        actual.dev !== metadata.dev ||
        actual.ino !== metadata.ino
      )
        throw new Error();
      const buffer = Buffer.alloc(MAX_BYTES + 1);
      let size = 0;
      while (size < buffer.length) {
        const result = await handle.read(
          buffer,
          size,
          buffer.length - size,
          size,
        );
        if (!result.bytesRead) break;
        size += result.bytesRead;
      }
      if (!size || size > MAX_BYTES) throw new Error();
      bytes = buffer.subarray(0, size);
      await handle.sync();
    } finally {
      await handle.close();
    }
  } catch {
    return fail("STORAGE_FAILED");
  }
  let plain: string;
  try {
    plain = protection.decryptString(bytes);
  } catch {
    return fail("PROTECTION_FAILED");
  }
  try {
    if (typeof plain !== "string" || Buffer.byteLength(plain) > MAX_BYTES)
      throw new Error();
    const raw: unknown = JSON.parse(plain);
    if (!exact(raw, ["version", "scope", "record"]) || raw.version !== 1)
      throw new Error();
    const savedScope = parseScope(raw.scope),
      record = parseRecord(raw.record);
    if (
      JSON.stringify(savedScope) !== JSON.stringify(scope) ||
      record.requestId !== requestId ||
      JSON.stringify({ version: 1, scope: savedScope, record }) !== plain
    )
      throw new Error();
    return record;
  } catch {
    return fail("INVALID_RECORD");
  }
}
async function serialized<T>(
  filename: string,
  action: () => Promise<T>,
): Promise<T> {
  const key = process.platform === "win32" ? filename.toLowerCase() : filename,
    result = (pendingFiles.get(key) ?? Promise.resolve()).then(action),
    settled = result.then(
      () => undefined,
      () => undefined,
    );
  pendingFiles.set(key, settled);
  void settled.then(() => {
    if (pendingFiles.get(key) === settled) pendingFiles.delete(key);
  });
  return result;
}

/** Immutable result metadata only. The trusted main process supplies the fixed directory. */
export function createOutreachResultOutbox(options: {
  directory: string;
  protection: DeviceKeyProtection;
}): OutreachResultOutbox {
  if (
    typeof options.directory !== "string" ||
    !path.isAbsolute(options.directory) ||
    path.resolve(options.directory) === path.parse(options.directory).root
  )
    fail("STORAGE_FAILED");
  const directory = path.resolve(options.directory),
    protection = options.protection;
  const filename = (scope: OutreachConsumptionScope, requestId: string) =>
    path.join(
      directory,
      `${createHash("sha256").update(JSON.stringify({ scope, requestId })).digest("hex")}.result`,
    );
  return {
    async read(inputScope, inputRequestId) {
      const scope = parseScope(inputScope),
        requestId = uuid.safeParse(inputRequestId);
      if (!requestId.success) fail("INVALID_RECORD");
      const target = filename(scope, requestId.data);
      return serialized(target, async () => {
        requireProtection(protection);
        if (!(await directoryReady(directory, false))) return null;
        const record = await readExisting(
          target,
          scope,
          requestId.data,
          protection,
        );
        if (!record) return null;
        await syncResultDirectories(directory);
        return copy(record);
      });
    },
    async put(inputScope, inputRecord) {
      const scope = parseScope(inputScope),
        record = parseRecord(inputRecord),
        target = filename(scope, record.requestId);
      return serialized(target, async () => {
        requireProtection(protection);
        await directoryReady(directory, true);
        const existing = await readExisting(
          target,
          scope,
          record.requestId,
          protection,
        );
        if (existing) {
          if (!same(existing, record)) fail("CONFLICT");
          await syncResultDirectories(directory);
          return copy(existing);
        }
        let bytes: Buffer;
        try {
          const encrypted = protection.encryptString(
            JSON.stringify({ version: 1, scope, record }),
          );
          if (
            !Buffer.isBuffer(encrypted) ||
            !encrypted.length ||
            encrypted.length > MAX_BYTES
          )
            throw new Error();
          bytes = Buffer.from(encrypted);
        } catch {
          return fail("PROTECTION_FAILED");
        }
        let handle;
        try {
          handle = await open(target, "wx", 0o600);
        } catch (error) {
          if (hasCode(error, "EEXIST")) {
            const concurrent = await readExisting(
              target,
              scope,
              record.requestId,
              protection,
            );
            if (concurrent) {
              if (!same(concurrent, record)) fail("CONFLICT");
              await syncResultDirectories(directory);
              return copy(concurrent);
            }
          }
          return fail("STORAGE_FAILED");
        }
        try {
          try {
            await handle.writeFile(bytes);
            await handle.sync();
          } finally {
            await handle.close();
          }
          await syncResultDirectories(directory);
        } catch {
          return fail("STORAGE_FAILED");
        }
        return copy(record);
      });
    },
  };
}
