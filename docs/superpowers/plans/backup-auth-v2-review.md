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

## Incremental re-review

GO for source `e389ee9dbd80d53b1b867fb8f38190d90a4ece44`, reviewing only the changes since `2342d01` and reusing the remaining original review conclusions. Both P2 findings are closed; no new actionable P1/P2 finding in this delta.

- Backup validates and captures one exclusive mode-0600 secret snapshot before encryption; encryption and MAC creation both use that snapshot. Restore likewise uses one snapshot for verification and decryption. Original-file rotation no longer changes the secret between those operations, and EXIT cleanup owns the snapshot.
- Publication now uses exact-destination `os.link` rather than ln's directory operand semantics. Existing destination files, directories and symlinks cause failure without publishing inside or overwriting them; partial backup cleanup retains the inode ownership check.
- The helper resolves and rejects an in-repository snapshot destination before reading/writing secret content. Backup also rejects an in-repository destination before creating its temporary output directory.

Reused fix-report evidence: affected backup-script file 12 PASS / 9.36 seconds, bash syntax, Python compile and diff checks exit 0. No reviewer test rerun or implementation modification. This closes the source-review blockers only; real PostgreSQL restoration, production recovery and CP-06 acceptance remain unverified.
