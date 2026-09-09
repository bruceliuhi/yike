import { useSyncExternalStore } from "react";
import type { MaterialRecoveryController } from "./materialRecovery";

export function MaterialRecoveryControls({ controller }: { controller: MaterialRecoveryController }) {
  const state = useSyncExternalStore(controller.subscribe, controller.snapshot);
  return <section aria-label="TEST 资料回执控制">
    <p>TEST 资料内存恢复 · {state.phase} · 下一次：{state.next || "正常"}</p>
    <p>只暂扣隔离内存回执，不访问真实资料、文件或 AI。释放后仍需点击页面“核对原资料操作”。</p>
    {([['save', '保存'], ['revoke', '撤销'], ['remove', '移除']] as const).map(([kind, label]) =>
      <button key={kind} disabled={state.phase === "UNKNOWN"} onClick={() => controller.arm(kind)}>
        TEST 下一次{label}回执置为未知
      </button>)}
    <button disabled={state.phase !== "UNKNOWN"} onClick={controller.release}>TEST 释放原资料回执</button>
    {state.requestId && <p>TEST 原请求：{state.requestId}</p>}
  </section>;
}
