import { afterEach, describe, expect, it, vi } from "vitest";
import { boundedRequest, RequestCancelled } from "../src/renderer/app/boundedRequest";

afterEach(() => vi.useRealTimers());

describe("bounded UI requests", () => {
  it("settles on cancellation even if the service ignores abort and resolves later", async () => {
    const controller = new AbortController();
    let signal!: AbortSignal;
    let resolve!: (value: string) => void;
    const pending = boundedRequest(s => { signal = s; return new Promise<string>(done => { resolve = done; }); }, { signal: controller.signal, timeoutMessage: "timeout" });
    const assertion = expect(pending).rejects.toBeInstanceOf(RequestCancelled);
    await Promise.resolve();
    controller.abort();
    await assertion;
    expect(signal.aborted).toBe(true);
    resolve("stale");
  });

  it("times out a hanging request, aborts its transport and consumes late rejection", async () => {
    vi.useFakeTimers();
    let signal!: AbortSignal;
    let reject!: (reason: Error) => void;
    const pending = boundedRequest(s => { signal = s; return new Promise<string>((_, fail) => { reject = fail; }); }, { timeoutMs: 100, timeoutMessage: "request timed out" });
    const assertion = expect(pending).rejects.toThrow("request timed out");
    await vi.advanceTimersByTimeAsync(100);
    await assertion;
    expect(signal.aborted).toBe(true);
    reject(new Error("late transport failure"));
    await Promise.resolve();
    expect(vi.getTimerCount()).toBe(0);
  });

  it("does not invoke an already cancelled operation and removes successful timers", async () => {
    vi.useFakeTimers();
    const controller = new AbortController();
    controller.abort();
    const operation = vi.fn().mockResolvedValue("ready");
    await expect(boundedRequest(operation, { signal: controller.signal, timeoutMessage: "timeout" })).rejects.toBeInstanceOf(RequestCancelled);
    expect(operation).not.toHaveBeenCalled();
    await expect(boundedRequest(operation, { timeoutMessage: "timeout" })).resolves.toBe("ready");
    expect(vi.getTimerCount()).toBe(0);
  });
});
