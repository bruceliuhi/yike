import {spawn, type ChildProcessWithoutNullStreams} from 'node:child_process';
import {randomUUID} from 'node:crypto';
import {lstatSync} from 'node:fs';
import {win32 as path} from 'node:path';

export interface PlatformLoginDriverOptions {
  pythonExecutable: string;
  projectRoot: string;
  runtimePath: string;
  profileRoot: string;
  outputRoot: string;
  spawn?: typeof spawn;
}
export interface PlatformLoginObservation {account_public_id: string; checked_at: string}
export interface PlatformLoginRun {
  opened: Promise<void>;
  completed: Promise<PlatformLoginObservation>;
  stop(): Promise<void>;
}
const SCHEMA = 'windows-platform-login-v1';
const MAX_OUTPUT = 16 * 1024;
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const FAILURE_STATES = new Set(['CANCELLED', 'TIMED_OUT', 'FAILED', 'BLOCKED_INPUT']);
const SAFE_CODES = new Set(['PLATFORM_AUTH_REQUIRED', 'PLATFORM_PERMISSION_DENIED',
  'PLATFORM_VERIFICATION_REQUIRED', 'PLATFORM_RATE_LIMITED', 'PLATFORM_RESPONSE_CHANGED',
  'PLATFORM_ACCOUNT_UNVERIFIED', 'COLLECTION_NETWORK_FAILED', 'COLLECTION_PARSE_FAILED',
  'COLLECTION_PROCESS_FAILED', 'PLATFORM_LOGIN_CANCELLED', 'PLATFORM_LOGIN_FAILED',
  'PLATFORM_LOGIN_INPUT_INVALID', 'SOURCE_HOST_FAILED']);
const failure = (code: string) => new Error(code);

/** Every host field is a string. Reject duplicate keys, including escaped names. */
function decodeFrame(bytes: Buffer): Record<string, string> {
  const text = new TextDecoder('utf-8', {fatal: true}).decode(bytes).trim();
  const value: unknown = JSON.parse(text);
  if (!value || typeof value !== 'object' || Array.isArray(value) || text[0] !== '{') throw failure('SOURCE_HOST_FAILED');
  const pair = /\s*("(?:[^"\\]|\\.)*")\s*:\s*("(?:[^"\\]|\\.)*")\s*/y;
  const keys = new Set<string>();
  let offset = 1;
  while (true) {
    pair.lastIndex = offset;
    const match = pair.exec(text);
    if (!match) throw failure('SOURCE_HOST_FAILED');
    const key: string = JSON.parse(match[1]);
    if (keys.has(key)) throw failure('SOURCE_HOST_FAILED');
    keys.add(key); offset = pair.lastIndex;
    if (text[offset] === '}' && offset === text.length - 1) break;
    if (text[offset++] !== ',') throw failure('SOURCE_HOST_FAILED');
  }
  const result = value as Record<string, string>;
  if (result.schema_version !== SCHEMA) throw failure('SOURCE_HOST_FAILED');
  return result;
}

function validatePaths(options: PlatformLoginDriverOptions, profileId: string): void {
  if (typeof profileId !== 'string' || !UUID.test(profileId)) throw failure('PLATFORM_LOGIN_INPUT_INVALID');
  for (const key of ['pythonExecutable', 'projectRoot', 'runtimePath', 'profileRoot', 'outputRoot'] as const) {
    const value = options[key];
    if (typeof value !== 'string' || !/^[A-Za-z]:[\\/]/.test(value) || !path.isAbsolute(value) ||
        /[\p{Cc}\p{Cf}\p{Cs}]/u.test(value)) throw failure('PLATFORM_LOGIN_INPUT_INVALID');
    const info = lstatSync(value);
    if (info.isSymbolicLink() || (key === 'pythonExecutable' ? !info.isFile() : !info.isDirectory())) throw failure('PLATFORM_LOGIN_INPUT_INVALID');
  }
  const roots = [options.runtimePath, options.profileRoot, options.outputRoot].map(p => path.resolve(p).toLowerCase());
  for (let i = 0; i < roots.length; i++) for (let j = i + 1; j < roots.length; j++) {
    if (roots[i] === roots[j] || roots[i].startsWith(roots[j] + '\\') || roots[j].startsWith(roots[i] + '\\')) throw failure('PLATFORM_LOGIN_INPUT_INVALID');
  }
}

/** Main-owned isolated paths only; opening a browser never proves authentication. */
export function createPlatformLoginDriver(options: PlatformLoginDriverOptions) {
  const owned = {...options};
  const launch = owned.spawn ?? spawn;
  return {start(input: {profileId: string; signal?: AbortSignal}): PlatformLoginRun {
    const {profileId, signal} = input;
    let child: ChildProcessWithoutNullStreams | null = null;
    let settled = false, sawOpened = false, unknownCleanup = false;
    let cancelled = signal?.aborted ?? false, timedOut = false;
    let reason: Error | undefined;
    let terminal: Record<string, string> | null = null;
    let deadline: ReturnType<typeof setTimeout> | undefined;
    let grace: ReturnType<typeof setTimeout> | undefined;
    let resolveOpened!: () => void, rejectOpened!: (error: Error) => void;
    let resolveCompleted!: (value: PlatformLoginObservation) => void, rejectCompleted!: (error: Error) => void;
    const opened = new Promise<void>((resolve, reject) => {resolveOpened = resolve; rejectOpened = reject;});
    const completed = new Promise<PlatformLoginObservation>((resolve, reject) => {resolveCompleted = resolve; rejectCompleted = reject;});
    // Cancellation may happen before the main controller attaches its handlers.
    void opened.catch(() => {}); void completed.catch(() => {});

    function settle(error?: Error, value?: PlatformLoginObservation) {
      if (settled) return;
      settled = true;
      if (deadline) clearTimeout(deadline);
      if (grace) clearTimeout(grace);
      signal?.removeEventListener('abort', onAbort);
      if (!sawOpened) rejectOpened(error ?? failure('SOURCE_HOST_FAILED'));
      if (error) rejectCompleted(error); else resolveCompleted(value!);
    }
    function requestStop(error?: Error) {
      if (settled) return;
      cancelled = true;
      reason ??= error;
      if (!child || grace) return;
      const active = child;
      grace = setTimeout(() => {
        unknownCleanup = true;
        try {active.kill();} catch { /* Killing one process cannot prove tree cleanup. */ }
        settle(failure('SOURCE_STOP_FAILED'));
      }, 30_000);
      try {active.stdin.end();} catch {unknownCleanup = true; reason = failure('SOURCE_HOST_FAILED');}
    }
    function onAbort() {requestStop(failure('PLATFORM_LOGIN_CANCELLED'));}
    function protocolFailure() {
      unknownCleanup = true;
      reason = failure('SOURCE_HOST_FAILED');
      requestStop(reason);
    }
    signal?.addEventListener('abort', onAbort, {once: true});

    // The handle exists before creation, allowing synchronous cancellation.
    void Promise.resolve().then(() => {
      if (cancelled) {settle(failure('PLATFORM_LOGIN_CANCELLED')); return;}
      let wire: Buffer;
      try {
        validatePaths(owned, profileId);
        wire = Buffer.from(JSON.stringify({schema_version: SCHEMA, runtime_path: owned.runtimePath,
          profile_path: path.join(owned.profileRoot, profileId), output_path: path.join(owned.outputRoot, randomUUID()),
          platform: 'XIAOHONGSHU', timeout_seconds: 180}) + '\n', 'utf8');
        if (wire.length > 65536) throw failure('PLATFORM_LOGIN_INPUT_INVALID');
      } catch {settle(failure('PLATFORM_LOGIN_INPUT_INVALID')); return;}
      const env: NodeJS.ProcessEnv = {PYTHONIOENCODING: 'utf-8', PYTHONUTF8: '1'};
      for (const key of ['SystemRoot', 'WINDIR', 'USERNAME']) if (process.env[key]) env[key] = process.env[key];
      try {
        child = launch(owned.pythonExecutable, ['-X', 'utf8', '-m', 'app.windows_platform_login'],
          {cwd: owned.projectRoot, shell: false, windowsHide: true, stdio: ['pipe', 'pipe', 'pipe'], env});
      } catch {unknownCleanup = true; settle(failure('SOURCE_HOST_FAILED')); return;}
      const active = child;
      let total = 0, pending = Buffer.alloc(0);
      deadline = setTimeout(() => {timedOut = true; requestStop(failure('PLATFORM_LOGIN_TIMED_OUT'));}, 180_000);
      active.stderr.resume(); // Drain without retaining or disclosing raw logs.
      active.on('error', protocolFailure);
      active.stdin.on('error', protocolFailure);
      active.stdout.on('error', protocolFailure);
      active.stderr.on('error', protocolFailure);
      active.stdout.on('data', (chunk: Buffer) => {
        if (settled || unknownCleanup) return;
        total += chunk.length;
        if (total > MAX_OUTPUT) {protocolFailure(); return;}
        pending = Buffer.concat([pending, chunk]);
        try {
          let end: number;
          while ((end = pending.indexOf(10)) >= 0) {
            if (terminal) throw failure('SOURCE_HOST_FAILED');
            const frame = decodeFrame(pending.subarray(0, end));
            pending = pending.subarray(end + 1);
            const keys = Object.keys(frame).sort().join(',');
            if (frame.state === 'OPENED' && keys === 'schema_version,state' && !sawOpened) {
              sawOpened = true; resolveOpened();
            } else if (frame.state === 'AUTHENTICATED' && sawOpened && keys === 'account_public_id,checked_at,schema_version,state') {
              if (!/^[A-Za-z0-9]{8,32}$/.test(frame.account_public_id) ||
                  !/^(?!0000)\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/.test(frame.checked_at) ||
                  new Date(frame.checked_at).toISOString() !== frame.checked_at.replace('Z', '.000Z')) throw failure('SOURCE_HOST_FAILED');
              terminal = frame;
            } else if (FAILURE_STATES.has(frame.state) && (keys === 'schema_version,state' ||
                keys === 'error_code,schema_version,state' && SAFE_CODES.has(frame.error_code))) {
              terminal = frame;
              if (frame.error_code === 'SOURCE_HOST_FAILED') unknownCleanup = true;
            } else throw failure('SOURCE_HOST_FAILED');
          }
          if (terminal && pending.length) throw failure('SOURCE_HOST_FAILED');
        } catch {protocolFailure();}
      });
      active.on('close', (code, terminationSignal) => {
        if (settled) return;
        if (code !== 0 || terminationSignal || !terminal || pending.length) unknownCleanup = true;
        if (unknownCleanup) {settle(failure('SOURCE_HOST_FAILED')); return;}
        if (cancelled) {settle(reason ?? failure(timedOut ? 'PLATFORM_LOGIN_TIMED_OUT' : 'PLATFORM_LOGIN_CANCELLED')); return;}
        if (terminal!.state === 'AUTHENTICATED') {
          settle(undefined, {account_public_id: terminal!.account_public_id, checked_at: terminal!.checked_at});
        } else {
          settle(failure(terminal!.error_code ?? (terminal!.state === 'CANCELLED' ? 'PLATFORM_LOGIN_CANCELLED' :
            terminal!.state === 'TIMED_OUT' ? 'PLATFORM_LOGIN_TIMED_OUT' : 'PLATFORM_LOGIN_FAILED')));
        }
      });
      try {active.stdin.write(wire);} catch {protocolFailure();}
      if (cancelled) requestStop(reason);
    }).catch(() => {
      if (child) protocolFailure();
      else {unknownCleanup = true; settle(failure('SOURCE_HOST_FAILED'));}
    });
    return {opened, completed, async stop() {
      requestStop(failure('PLATFORM_LOGIN_CANCELLED'));
      await completed.catch(() => {});
      if (unknownCleanup) throw failure('SOURCE_STOP_FAILED');
    }};
  }};
}
