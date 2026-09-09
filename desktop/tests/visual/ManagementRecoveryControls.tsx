import { useSyncExternalStore } from "react";
import type {
  ManagementRecoveryController,
  ManagementResultMode,
  ManagementSaveMode,
  ManagementCancelMode,
} from "./managementRecovery";

export function ManagementRecoveryControls({
  controller,
}: {
  controller: ManagementRecoveryController;
}) {
  const state = useSyncExternalStore(controller.subscribe, controller.snapshot);
  return (
    <section aria-label="TEST 管理生命周期控制">
      <p>TEST 内存管理 · {state.phase}。保存/恢复/更新均为模拟，不创建文件。</p>
      <label>
        TEST 保存回执{" "}
        <select
          aria-label="TEST 保存回执"
          value={state.saveMode}
          onChange={(event) =>
            controller.setSaveMode(event.target.value as ManagementSaveMode)
          }
        >
          <option value="cancelled">取消保存</option>
          <option value="saved">内存模拟已保存</option>
          <option value="error">保存失败</option>
        </select>
      </label>
      <p>
        <label>
          TEST 执行回执{" "}
          <select
            aria-label="TEST 执行回执"
            value={state.executeMode}
            onChange={(event) =>
              controller.setExecuteMode(
                event.target.value as ManagementResultMode,
              )
            }
          >
            <option value="UNKNOWN">结果未知</option>
            <option value="FAILED">确定未执行</option>
            <option value="SUCCEEDED">仅内存完成</option>
          </select>
        </label>
      </p>
      <p>
        <label>
          TEST 原请求查询{" "}
          <select
            aria-label="TEST 原请求查询"
            value={state.queryMode}
            onChange={(event) =>
              controller.setQueryMode(
                event.target.value as ManagementResultMode,
              )
            }
          >
            <option value="UNKNOWN">仍未知</option>
            <option value="FAILED">确定未执行</option>
            <option value="SUCCEEDED">仅内存完成</option>
          </select>
        </label>
      </p>
      <p>
        <label>
          TEST 取消回执{" "}
          <select
            aria-label="TEST 取消回执"
            value={state.cancelMode}
            onChange={(event) =>
              controller.setCancelMode(
                event.target.value as ManagementCancelMode,
              )
            }
          >
            <option value="PENDING">仅收到取消请求</option>
            <option value="CANCELLED">确定已取消</option>
          </select>
        </label>
      </p>
      <p>改变选择后，请点击产品页的原操作按钮；不直接清除待确认记录。</p>
      {state.requestId && (
        <p style={{ overflowWrap: "anywhere" }}>
          原请求：{state.requestId} · {state.kind}
        </p>
      )}
      <p role="status">{state.lastSave}</p>
    </section>
  );
}
