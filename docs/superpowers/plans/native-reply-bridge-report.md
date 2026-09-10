# Native reply Python bridge report

## Scope

Implemented the private Python host/worker `READ_REPLIES` action only. The external second frame is translated to the unique internal operation `{"readReplies":{"rootCommentId","claimedAt"}}`; the worker dispatches it to `channel.read_replies(...)` and never to `execute(...)`.

The existing `EXECUTE` operation shape and return dictionary remain unchanged. Input/context frames remain capped at 128 KiB. Only an accepted read operation permits a 512 KiB RESULT frame and a 512 KiB + 32 KiB total host stdout budget; normal sending remains under the existing limits.

## TDD evidence

RED (before production changes):

```text
/tmp/yike-main-merge.PZkSlU/.venv/bin/python -m pytest -q tests/test_native_reply_bridge.py
FFFFF
```

The failures were caused by the missing `_read_operation` and missing worker read dispatch. The initial multi-case run then waited in the pre-existing execute-only worker path, so it was stopped rather than represented as a completed test run.

GREEN / affected send regression:

```text
/tmp/yike-main-merge.PZkSlU/.venv/bin/python -m pytest -q tests/test_native_reply_bridge.py tests/test_windows_platform_outreach.py
...................................                                      [100%]
35 passed in 0.14s
```

Additional syntax and diff checks:

```text
/tmp/yike-main-merge.PZkSlU/.venv/bin/python -m py_compile app/windows_platform_outreach.py app/platform_outreach_worker.py
git diff --check
```

Both exited 0.

## Covered behavior

- Exact root comment ID and claimed timestamp reach `read_replies` once; `execute` is not called.
- Read RESULT larger than 32 KiB is accepted; a RESULT larger than 512 KiB is rejected.
- Mixed and extra internal fields are rejected, as are uppercase/non-24-hex roots and timezone-naive timestamps.
- EOF during an in-flight read cancels the owner task and exits the channel lifecycle.
- Existing READY/EXECUTE, malformed frame, cancellation, terminal-tail, cleanup-failure, and UNKNOWN tests remain passing.

## Evidence boundary

No full suite, bundle/package build, Windows-machine execution, real profile, real platform call, send, DM, read-state mutation, or production/UAT validation was performed. These are synthetic loopback/socket tests on macOS and do not establish Windows or platform availability.

Commit SHA is recorded in the commit itself and in the parent integrator's final ledger; this report is committed atomically with the implementation, so it cannot truthfully contain its own final SHA beforehand.
