# Backup authentication V2 independent review

## Verdict

NO-GO pending two P2 fixes, bound to `42ebce8..2342d01494951179c15f4c3ac1a445b7a6079e23`. No P1 finding.

## Findings

1. **P2 — Pin the same secret bytes across encryption and authentication.** `scripts/backup_pilot.sh:60-62` lets OpenSSL and the helper independently reopen the mutable passphrase path. Rotation from A to B after OpenSSL reads A but before the helper reads B produces ciphertext encrypted with A and a MAC derived from B, then publishes success. Neither A nor B alone can restore the result. Validate and capture one private per-operation secret snapshot, using it for both steps. The analogous verify/decrypt pair at `scripts/restore_pilot.sh:53-54` should also share that snapshot. A targeted secret-rotation fixture should show a restorable artifact using the captured secret, or fail without publishing.

2. **P2 — Publish to an exact destination, not ln's directory operand.** `scripts/backup_pilot.sh:64-66` uses two-operand `ln`, which treats an existing destination directory (or directory symlink) as a container. If either target becomes a directory after its precheck, the link can succeed inside it and the script can announce success although the specified backup/sidecar path is not a file. The current inode-based cleanup does not find that nested link either. Use an exact-destination no-clobber primitive such as `os.link`, preserving any preexisting object; cover directory appearance between precheck and publication with a bounded fixture.

## Other reviewed boundaries

The helper derives the authentication key from private secret contents with a separate PBKDF2 domain, authenticates the complete ciphertext, uses constant-time comparison and strictly rejects legacy/unknown/malformed sidecars. Restore authenticates and decrypts the same private ciphertext snapshot; an authentication failure exits before pg_restore. No automatic legacy conversion or rewriting was introduced.

## Evidence boundary

This was a static review of the frozen diff, full scripts/helper, specification and affected tests. No implementation change, test rerun, database operation or production action was performed. Reused implementer evidence: three RED reproductions, real OpenSSL plus fixture-PG script set 6 PASS, subsequently added snapshot case 1 PASS, bash syntax and diff checks passing. These are not real PostgreSQL restoration, production recovery or CP-06 completion evidence.
