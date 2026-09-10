# 07B host implementation report

- Added the fixed two-frame Python host and private one-shot loopback worker.
- Host output is compact UTF-8 JSON only, bounded to 32 KiB; input rejects duplicate keys, constants and oversized frames.
- The worker receives context only over the authenticated 127.0.0.1 channel. It checks one page before the one allowed execute operation and treats host EOF as cancellation.
- A received terminal outcome survives a later supervised-cleanup failure with `cleanupConfirmed:false`; no real platform action was exercised.

Verification: `/tmp/yike-main-merge.PZkSlU/.venv/bin/python -m pytest -q tests/test_windows_platform_outreach.py` — `6 passed`.

Known boundary: Windows Job/private-directory enforcement and live XHS delivery need the separate Windows/platform acceptance run.

## Independent NO-GO repair (2026-09-11)

The initial 6 parsing/injected-host tests did **not** exercise the actual bridge and did not establish the preceding end-to-end claims. A new socket-backed READY callback test reproduced the blocking stdin read (interrupted after 20 seconds; only the first 4 parsing cases had passed). Repairs replace callback reads with a daemon stdin reader and pending-operation state; the supervisor poll never waits for EXECUTE. EOF, early/duplicate/extra input cancel the lifetime. The worker now concurrently reads bounded strict frames through asyncio, cancels pending setup/check/execute awaits on EOF or extra frames, and sends the actual `channel.check(context)` observation from the same channel used by execute.

Loopback host reads are bounded before authentication, token comparison is constant-time, and host sends are queued nonblocking writes. Both normal supervisor return and exceptions receive a bounded terminal tail drain. Nonzero worker exit, supervisor cleanup exceptions and later private-tree verification errors retain a previously validated outcome with `cleanupConfirmed:false`. No supervisor/Job assignment gate was changed.

Targeted verification: `/tmp/yike-main-merge.PZkSlU/.venv/bin/python -m pytest -q tests/test_windows_platform_outreach.py` — **24 passed**. New tests include actual host/worker loopback transport with a synthetic channel (full READY observation and same-channel execute), normal terminal tail receipt, worker/supervisor/private-tree cleanup failure receipt retention, worker cancellation while awaiting setup/operation/execute, malformed/oversized authentication input, stdin phase/EOF enforcement, and supervisor responsiveness without an operation. This remains synthetic boundary evidence, not Windows Job/ACL acceptance or real platform delivery. No installs, full suite, production integration or external sends were performed.
