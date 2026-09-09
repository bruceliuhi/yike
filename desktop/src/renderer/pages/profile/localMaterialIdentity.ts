import type { MaterialOwner } from "./materialOperationStorage";

/** Stable opaque target identity; authorization still belongs to the service. */
export async function localMaterialIdentity(owner: MaterialOwner, profileVersionId: string, localId: string) {
  const source = JSON.stringify([
    "local-material-v1", owner.userId, owner.accountScope?.id ?? null,
    owner.accountScope?.version ?? null, profileVersionId, localId,
  ]);
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(source));
  return "local-" + Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, "0")).join("");
}
