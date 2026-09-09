import { useSyncExternalStore } from "react";
import type { RecoveryController } from "./recovery";

export function RecoveryControls({
  controller,
}: {
  controller: RecoveryController;
}) {
  const state = useSyncExternalStore(controller.subscribe, controller.snapshot);
  return (
    <section aria-label="TEST 恢复场景控制">
      <p>
        TEST {state.name} · {state.phase}
      </p>
      <p>只改变隔离内存状态，不执行真实登录、任务或发送。</p>
      {state.name === "ai-late" && (
        <button
          disabled={!state.pendingSuggestions}
          onClick={controller.releaseSuggestions}
        >
          TEST 返回等待中的 AI 建议
        </button>
      )}
      {["send-unknown", "start-unknown"].includes(state.name) && (
        <button
          disabled={
            !state.originalRequest || state.phase === "CONFIRMED_NOT_EXECUTED"
          }
          onClick={controller.confirmNotExecuted}
        >
          TEST 确认原请求未执行
        </button>
      )}
      {!!state.originalRequest && <p>原请求：{state.originalRequest}</p>}
    </section>
  );
}
