export const UI_REQUEST_TIMEOUT_MS = 30_000;
export const SUGGESTION_TIMEOUT_MS = 45_000;

export class RequestCancelled extends Error {
  constructor() {
    super("请求等待已取消。");
    this.name = "RequestCancelled";
  }
}
export class RequestTimeout extends Error {
  constructor(message: string) {
    super(message);
    this.name = "RequestTimeout";
  }
}

/** Bounds UI waiting even when a service ignores AbortSignal. Cancellation does
 * not assert that an external side effect was undone; pages discard late data. */
export function boundedRequest<T>(
  operation: (signal: AbortSignal) => Promise<T>,
  options: { signal?: AbortSignal; timeoutMs?: number; timeoutMessage: string },
): Promise<T> {
  const controller = new AbortController();
  return new Promise<T>((resolve, reject) => {
    let settled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const finish = (callback: () => void) => {
      if (settled) return;
      settled = true;
      if (timer !== undefined) clearTimeout(timer);
      options.signal?.removeEventListener("abort", cancel);
      callback();
    };
    const cancel = () => finish(() => {
      controller.abort();
      reject(new RequestCancelled());
    });
    if (options.signal?.aborted) { cancel(); return; }
    options.signal?.addEventListener("abort", cancel, { once: true });
    timer = setTimeout(() => finish(() => {
      controller.abort();
      reject(new RequestTimeout(options.timeoutMessage));
    }), options.timeoutMs ?? UI_REQUEST_TIMEOUT_MS);
    Promise.resolve().then(() => {
      if (settled) return;
      return operation(controller.signal).then(
        value => finish(() => resolve(value)),
        error => finish(() => reject(error)),
      );
    }).catch(error => finish(() => reject(error)));
  });
}
