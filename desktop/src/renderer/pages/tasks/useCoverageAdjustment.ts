import { useEffect, useRef, useState } from "react";
import { useApp } from "../../app/context";
import { boundedRequest } from "../../app/boundedRequest";
import { useOperationLedger } from "../../app/operationLedger";
import { errorMessage } from "../../services/contracts";
import {
  coverageAdjustmentKey,
  coverageConfirmationHash,
  readCoverageAdjustmentKey,
  readCoverageAdjustmentReceipt,
  readCoveragePreview,
  type CoverageAdjustmentBinding,
  type CoveragePlanPreview,
  type CoveragePreviewRequest,
} from "../../domain/coveragePlan";
import { useTaskScope } from "./useTaskScope";

export function useCoverageAdjustment(taskId: string) {
  const { service, session, notify } = useApp();
  const scope = useTaskScope(taskId);
  const [entries, setEntries] = useOperationLedger(
    "coverage-adjustments",
    session.userId,
  );
  const matches = (key: string) => {
    const binding = readCoverageAdjustmentKey(key);
    return (
      binding.taskId === taskId &&
      binding.accountScopeId === session.accountScope?.id &&
      binding.scopeVersion === session.accountScope.version
    );
  };
  const pending = Object.keys(entries).filter(matches);
  const locked = useRef(false);
  const rejected = useRef(new Set<string>());
  const [state, setState] = useState({
    identity: scope.identity,
    busy: false,
    error: "",
    applied: false,
    rejectedHash: "",
  });
  useEffect(() => {
    locked.current = false;
    setState({
      identity: scope.identity,
      busy: false,
      error: "",
      applied: false,
      rejectedHash: "",
    });
  }, [scope.identity]);
  const shown =
    state.identity === scope.identity
      ? state
      : { busy: false, error: "", applied: false, rejectedHash: "" };
  const settle = async (raw: unknown, binding: CoverageAdjustmentBinding) => {
    const receipt = await readCoverageAdjustmentReceipt(raw, binding);
    if (!scope.current()) return;
    if (receipt.status === "APPLIED" || receipt.status === "REJECTED") {
      setEntries((old) => {
        const next = { ...old };
        delete next[coverageAdjustmentKey(binding)];
        return next;
      });
      if (receipt.status === "APPLIED") {
        setState({
          identity: scope.identity,
          busy: false,
          error: "",
          applied: true,
          rejectedHash: "",
        });
        notify(
          `搜贝上限已调整为 ${receipt.maximum}；任务尚未恢复。`,
          "success",
        );
      } else {
        rejected.current.add(binding.confirmationHash);
        setState((old) => ({ ...old, rejectedHash: binding.confirmationHash }));
        throw new Error("原请求已确认未调整上限，可重新读取预览后再决定。");
      }
    } else throw new Error("上限调整结果仍待核对，请核对原请求，勿重新提交。");
  };
  const perform = async (work: () => Promise<void>) => {
    if (locked.current || !scope.current() || !session.authenticated) return;
    locked.current = true;
    setState({
      identity: scope.identity,
      busy: true,
      error: "",
      applied: false,
      rejectedHash: "",
    });
    try {
      await work();
    } catch (e) {
      if (scope.current())
        setState((old) => ({ ...old, error: errorMessage(e) }));
    } finally {
      if (scope.current()) {
        locked.current = false;
        setState((old) => ({ ...old, busy: false }));
      }
    }
  };
  const adjust = (
    preview: CoveragePlanPreview,
    expected: CoveragePreviewRequest,
  ) =>
    perform(async () => {
      if (!service.coveragePlans || preview.kind !== "ADJUST_LIMIT")
        throw new Error("上限调整服务尚未接通，原任务保持不变。");
      readCoveragePreview(preview, expected, session);
      const confirmationHash = await boundedRequest(
        () => coverageConfirmationHash(preview),
        { timeoutMessage: "确认摘要检查超时，尚未调整上限。" },
      );
      if (!scope.current()) return;
      readCoveragePreview(preview, expected, session);
      if (rejected.current.has(confirmationHash))
        throw new Error("原调整已被明确拒绝，请重新读取预览后确认。");
      const binding: CoverageAdjustmentBinding = {
        accountScopeId: preview.plan.accountScopeId,
        scopeVersion: preview.plan.scopeVersion,
        taskId,
        requestId: crypto.randomUUID(),
        confirmationHash,
      };
      setEntries((old) => {
        if (Object.keys(old).some(matches))
          throw new Error("原上限调整仍待核对，当前不会重复提交。");
        return { ...old, [coverageAdjustmentKey(binding)]: "PENDING" };
      });
      await settle(
        await boundedRequest(
          () => service.coveragePlans!.adjust({ binding, preview }),
          {
            timeoutMessage:
              "调整结果尚未确认，原请求已保留；请核对，勿重复提交。",
          },
        ),
        binding,
      );
    });
  const reconcile = (key: string) =>
    perform(async () => {
      if (!matches(key)) throw new Error("原调整不属于当前客户空间或任务。");
      if (!service.coveragePlans)
        throw new Error("原调整查询服务尚未接通，保护继续保留。");
      const binding = readCoverageAdjustmentKey(key);
      await settle(
        await boundedRequest(() => service.coveragePlans!.reconcile(binding), {
          timeoutMessage: "原调整查询超时，保护继续保留。",
        }),
        binding,
      );
    });
  return { ...shown, pending, adjust, reconcile };
}
