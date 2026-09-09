import { createPrivateKey, createPublicKey, sign, verify } from "node:crypto";
import type { DeviceKeyMaterial } from "./deviceKeyVault";
import {
  deviceCompletionSchema,
  parseDeviceChallenge,
  type DeviceCompletion,
  type ExpectedDeviceChallenge,
} from "../shared/deviceProof";

/** Main-process only: accepts a bound server challenge, never arbitrary sign bytes. */
export function signDeviceChallenge(input: {
  readonly key: DeviceKeyMaterial;
  readonly challenge: unknown;
  readonly expected: ExpectedDeviceChallenge;
  readonly nowSeconds: number;
}): DeviceCompletion {
  try {
    const { key, expected, challenge, nowSeconds } = input;
    // Revalidate at the moment of signing; an earlier parse is not a grant.
    const payload = parseDeviceChallenge(challenge, expected, nowSeconds);
    if (
      key.scope.serviceOrigin !== expected.serviceOrigin ||
      key.scope.userId !== expected.userId ||
      key.scope.deviceId !== expected.deviceId ||
      key.publicKey !== expected.publicKey ||
      typeof key.privateKey !== "string" ||
      key.privateKey.length > 4096
    ) {
      throw new Error();
    }
    const privateKey = createPrivateKey(key.privateKey);
    if (
      privateKey.asymmetricKeyType !== "ed25519" ||
      privateKey.export({ format: "pem", type: "pkcs8" }) !== key.privateKey
    ) {
      throw new Error();
    }
    const publicKey = createPublicKey(privateKey);
    if (publicKey.export({ format: "jwk" }).x !== key.publicKey) {
      throw new Error();
    }
    const bytes = Buffer.from(payload, "utf8");
    const signature = sign(null, bytes, privateKey);
    if (!verify(null, bytes, publicKey, signature)) throw new Error();
    return deviceCompletionSchema.parse({
      signature: signature.toString("base64url"),
      previous_signature: null,
    });
  } catch {
    // No crypto diagnostics, challenge bytes, identity or private material escape.
    throw new Error("DEVICE_PROOF_SIGNING_FAILED");
  }
}
