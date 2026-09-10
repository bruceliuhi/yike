import {
  createCipheriv,
  createDecipheriv,
  randomBytes,
  randomUUID,
} from "node:crypto";
import { existsSync } from "node:fs";
import {
  mkdtemp,
  mkdir,
  readFile,
  readdir,
  rm,
  symlink,
  writeFile,
} from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { DeviceKeyProtection } from "../src/main/deviceKeyVault";
import type { OutreachResultRecord } from "../src/main/outreachResultOutbox";

const faults = vi.hoisted(() => ({ denyCreate: false, failSync: false }));
vi.mock("node:fs/promises", async (importOriginal) => {
  const original = await importOriginal<typeof import("node:fs/promises")>();
  return {
    ...original,
    open: async (...args: Parameters<typeof original.open>) => {
      if (faults.denyCreate && args[1] === "wx")
        throw Object.assign(new Error("/private/store"), { code: "EACCES" });
      const handle = await original.open(...args),
        sync = handle.sync.bind(handle);
      handle.sync = async () => {
        if (faults.failSync) throw new Error("/private/sync");
        return sync();
      };
      return handle;
    },
  };
});

const modulePath = fileURLToPath(
  new URL("../src/main/outreachResultOutbox.ts", import.meta.url),
);
const scope = {
  serviceOrigin: "https://service.example",
  userId: randomUUID(),
  tenantId: randomUUID(),
};
const roots: string[] = [];
function protection(secret = randomBytes(32)): DeviceKeyProtection {
  return {
    isEncryptionAvailable: () => true,
    encryptString(plain) {
      const iv = randomBytes(12),
        cipher = createCipheriv("aes-256-gcm", secret, iv);
      return Buffer.concat([
        iv,
        cipher.update(plain),
        cipher.final(),
        cipher.getAuthTag(),
      ]);
    },
    decryptString(bytes) {
      const cipher = createDecipheriv(
        "aes-256-gcm",
        secret,
        bytes.subarray(0, 12),
      );
      cipher.setAuthTag(bytes.subarray(-16));
      return Buffer.concat([
        cipher.update(bytes.subarray(12, -16)),
        cipher.final(),
      ]).toString();
    },
  };
}
function record(
  status: "UNKNOWN" | "SENT" | "FAILED" = "SENT",
): OutreachResultRecord {
  const outcome =
    status === "UNKNOWN"
      ? { status, confirmed: null, confirmedNotDelivered: null, proof: null }
      : status === "SENT"
        ? {
            status,
        confirmed: true as const,
            confirmedNotDelivered: null,
            proof: {
              kind: "ACCEPTED" as const,
              externalId: "opaque.receipt:1",
              sha256: "b".repeat(64),
              observedAt: "2026-09-10T10:00:00+08:00",
            },
          }
        : {
            status,
        confirmed: true as const,
        confirmedNotDelivered: true as const,
            proof: {
              kind: "REJECTED_NOT_DELIVERED" as const,
              externalId: "reject_1",
              sha256: "c".repeat(64),
              observedAt: "2026-09-10T02:00:00Z",
            },
          };
  return {
    requestId: randomUUID(),
    claimId: randomUUID(),
    deviceId: randomUUID(),
    contextSha256: "a".repeat(64),
    resultId: randomUUID(),
    outcome,
  };
}
async function setup() {
  expect(existsSync(modulePath), "outbox implementation exists").toBe(true);
  const { createOutreachResultOutbox } =
    await import("../src/main/outreachResultOutbox");
  const root = await mkdtemp(path.join(os.tmpdir(), "yike-result-outbox-"));
  roots.push(root);
  const options = {
    directory: path.join(root, "outbox"),
    protection: protection(),
  };
  return {
    ...options,
    root,
    create: createOutreachResultOutbox,
    outbox: createOutreachResultOutbox(options),
  };
}
async function oneFile(directory: string) {
  const names = await readdir(directory);
  expect(names).toHaveLength(1);
  expect(names[0]).toMatch(/^[0-9a-f]{64}\.result$/);
  return path.join(directory, names[0]);
}
afterEach(async () => {
  vi.restoreAllMocks();
  Object.assign(faults, { denyCreate: false, failSync: false });
  for (const root of roots.splice(0))
    await rm(root, { recursive: true, force: true });
});

describe("immutable encrypted outreach result outbox", () => {
  it("persists and reconstructs the original result id and normalized outcome without plaintext", async () => {
    const f = await setup(),
      input = record("SENT"),
      saved = await f.outbox.put(scope, input),
      filename = await oneFile(f.directory),
      bytes = await readFile(filename);
    expect(saved).toEqual(input);
    expect(saved).not.toBe(input);
    expect(saved.outcome).not.toBe(input.outcome);
    for (const value of [
      input.requestId,
      input.resultId,
      input.outcome.proof!.externalId,
    ])
      expect(bytes.includes(Buffer.from(value))).toBe(false);
    const restored = await f.create(f).read(scope, input.requestId);
    expect(restored).toEqual(input);
    expect(restored).not.toBe(saved);
  });
  it("accepts and preserves the valid FAILED 123 outcome", async () => {
    const f = await setup(),
      input = record("FAILED");
    expect(await f.outbox.put(scope, input)).toEqual(input);
    expect(await f.outbox.read(scope, input.requestId)).toEqual(input);
  });
  it("snapshots input before awaiting and isolates origin, user, tenant and request", async () => {
    const f = await setup(),
      input = record(),
      suppliedScope = { ...scope },
      supplied: any = structuredClone(input),
      pending = f.outbox.put(suppliedScope, supplied);
    suppliedScope.tenantId = randomUUID();
    supplied.resultId = randomUUID();
    supplied.outcome.proof.externalId = "changed";
    expect(await pending).toEqual(input);
    for (const alternate of [
      { ...scope, tenantId: randomUUID() },
      { ...scope, userId: randomUUID() },
      { ...scope, serviceOrigin: "https://other.example" },
    ])
      expect(await f.outbox.read(alternate, input.requestId)).toBeNull();
    expect(await f.outbox.read(scope, randomUUID())).toBeNull();
  });
  it("rejects changed identity or outcome fields and preserves original bytes", async () => {
    const f = await setup(),
      input = record();
    await f.outbox.put(scope, input);
    const filename = await oneFile(f.directory),
      bytes = await readFile(filename);
    for (const field of [
      "claimId",
      "deviceId",
      "contextSha256",
      "resultId",
      "outcome",
    ] as const) {
      const changed: any = structuredClone(input);
      changed[field] =
        field === "contextSha256"
          ? "d".repeat(64)
          : field === "outcome"
            ? record("FAILED").outcome
            : randomUUID();
      await expect(f.outbox.put(scope, changed)).rejects.toThrow(
        /^OUTREACH_RESULT_CONFLICT$/,
      );
      expect(await readFile(filename)).toEqual(bytes);
    }
    expect(await f.outbox.read(scope, input.requestId)).toEqual(input);
  });
  it("permits one exclusive persistent creation and idempotently replays identical content", async () => {
    const f = await setup(),
      input = record(),
      other = f.create({ ...f, directory: path.join(f.directory, ".") });
    const values = await Promise.all(
      Array.from({ length: 12 }, (_, i) =>
        (i % 2 ? other : f.outbox).put(scope, input),
      ),
    );
    expect(values).toHaveLength(12);
    for (const value of values) {
      expect(value).toEqual(input);
      expect(value).not.toBe(input);
    }
    await oneFile(f.directory);
  });
  it("fails closed on corrupt records without replacement", async () => {
    for (const mode of ["empty", "ciphertext", "scope", "extra"] as const) {
      const f = await setup(),
        input = record();
      await f.outbox.put(scope, input);
      const filename = await oneFile(f.directory);
      const plain: any = {
        version: 1,
        scope: { ...scope },
        record: structuredClone(input),
      };
      if (mode === "scope") plain.scope.tenantId = randomUUID();
      if (mode === "extra") plain.secret = "no";
      const bytes =
        mode === "empty"
          ? Buffer.alloc(0)
          : mode === "ciphertext"
            ? Buffer.from("broken")
            : f.protection.encryptString(JSON.stringify(plain));
      await writeFile(filename, bytes);
      await expect(f.outbox.read(scope, input.requestId)).rejects.toThrow(
        /^OUTREACH_RESULT_(INVALID_RECORD|PROTECTION_FAILED)$/,
      );
      await expect(f.outbox.put(scope, input)).rejects.toThrow(
        /^OUTREACH_RESULT_(INVALID_RECORD|PROTECTION_FAILED)$/,
      );
      expect(await readFile(filename)).toEqual(bytes);
    }
  });
  it("rejects invalid 123 outcomes and extra or malformed record fields", async () => {
    const f = await setup(),
      input: any = record();
    for (const changed of [
      { ...input, outcome: record("UNKNOWN").outcome },
      { ...input, outcome: { ...input.outcome, confirmed: false } },
      {
        ...input,
        outcome: {
          ...input.outcome,
          proof: { ...input.outcome.proof, observedAt: "2026-09-10" },
        },
      },
      { ...input, body: "secret" },
      { ...input, resultId: "../bad" },
    ])
      await expect(f.outbox.put(scope, changed)).rejects.toThrow(
        /^OUTREACH_RESULT_INVALID_RECORD$/,
      );
    expect(await readdir(f.root)).toEqual([]);
  });
  it("rejects record and directory symlinks without following them", async () => {
    const f = await setup(),
      input = record();
    await f.outbox.put(scope, input);
    const filename = await oneFile(f.directory),
      bytes = await readFile(filename),
      target = path.join(f.root, "target");
    await writeFile(target, bytes);
    await rm(filename);
    await symlink(target, filename);
    await expect(f.outbox.read(scope, input.requestId)).rejects.toThrow(
      /^OUTREACH_RESULT_INVALID_RECORD$/,
    );
    expect(await readFile(target)).toEqual(bytes);
    const linked = path.join(f.root, "linked");
    await symlink(
      f.directory,
      linked,
      process.platform === "win32" ? "junction" : "dir",
    );
    await expect(
      f.create({ ...f, directory: linked }).put(scope, record()),
    ).rejects.toThrow(/^OUTREACH_RESULT_STORAGE_FAILED$/);
  });
  it("uses fixed failures for unavailable protection, encryption and persistent storage faults", async () => {
    const f = await setup(),
      input = record(),
      available = vi
        .spyOn(f.protection, "isEncryptionAvailable")
        .mockReturnValue(false);
    await expect(f.outbox.read(scope, input.requestId)).rejects.toThrow(
      /^OUTREACH_RESULT_PROTECTION_UNAVAILABLE$/,
    );
    await expect(f.outbox.put(scope, input)).rejects.toThrow(
      /^OUTREACH_RESULT_PROTECTION_UNAVAILABLE$/,
    );
    available.mockRestore();
    vi.spyOn(f.protection, "encryptString").mockImplementationOnce(() => {
      throw new Error("/secret");
    });
    await expect(f.outbox.put(scope, input)).rejects.toThrow(
      /^OUTREACH_RESULT_PROTECTION_FAILED$/,
    );
    faults.denyCreate = true;
    await expect(f.outbox.put(scope, input)).rejects.toThrow(
      /^OUTREACH_RESULT_STORAGE_FAILED$/,
    );
    faults.denyCreate = false;
    faults.failSync = true;
    await expect(f.outbox.put(scope, input)).rejects.toThrow(
      /^OUTREACH_RESULT_STORAGE_FAILED$/,
    );
    faults.failSync = false;
    expect(await f.create(f).read(scope, input.requestId)).toEqual(input);
  });
});
