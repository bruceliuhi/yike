import { useEffect, useMemo, useRef, useState } from "react";
import { useApp } from "../../app/context";
import { useOperationLedger } from "../../app/operationLedger";
import { boundedRequest } from "../../app/boundedRequest";
import type { ContactDraft, Opportunity } from "../../domain/models";
import {
  coachSourceKey,
  draftSaveBindingFromKey,
  draftSaveKey,
  draftSnapshot,
  readDraftSaveReceipt,
  snapshotDigest,
  type DraftSaveBinding,
  type DraftSnapshot,
} from "../../domain/shortCoach";
import { errorMessage, ServiceError } from "../../services/contracts";

export function useContactDraftSave(
  row: Opportunity,
  draft: ContactDraft,
  onSaved: (snapshot: DraftSnapshot) => void,
) {
  const { service, session, notify } = useApp();
  const [entries, setEntries] = useOperationLedger(
    "contact-draft-saves",
    session.userId,
  );
  const identity = JSON.stringify([
    session.authenticated,
    session.userId,
    session.accountScope,
    coachSourceKey(row),
    draft.channel,
  ]);
  const scope = useMemo(() => ({}), [identity, service]);
  const live = useRef(scope);
  live.current = scope;
  const mounted = useRef(true),
    lock = useRef(false);
  const [state, setState] = useState({ scope, busy: false, error: "" });
  const current = () => mounted.current && live.current === scope;
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);
  useEffect(() => {
    lock.current = false;
    setState({ scope, busy: false, error: "" });
  }, [scope]);
  const shown =
    state.scope === scope ? state : { scope, busy: false, error: "" };
  const matches = (key: string) => {
    const b = draftSaveBindingFromKey(key);
    return b.opportunityId === row.id && b.channel === draft.channel;
  };
  const pending = Object.keys(entries).filter(matches);
  const remove = (binding: DraftSaveBinding) =>
    setEntries((old) => {
      const next = { ...old };
      delete next[draftSaveKey(binding)];
      return next;
    });
  const accept = async (raw: unknown, binding: DraftSaveBinding) => {
    const receipt = await readDraftSaveReceipt(raw, binding);
    if (["SUCCEEDED", "FAILED"].includes(receipt.status)) remove(binding);
    if (!current()) return;
    if (receipt.status === "SUCCEEDED" && receipt.snapshot) {
      const savedScope = receipt.snapshot.accountScope;
      const activeScope = session.accountScope ?? null;
      if (
        savedScope?.id !== activeScope?.id ||
        savedScope?.version !== activeScope?.version
      )
        throw new Error(
          "已核对原请求；保存快照不属于当前客户空间，当前草稿未更改。",
        );
      if (
        receipt.snapshot.profileVersionId === row.profileVersionId &&
        receipt.snapshot.sourceEvidenceVersion ===
          (row.sourceEvidenceVersion || null)
      )
        onSaved(receipt.snapshot);
      notify("原草稿保存已确认完成，请核对当前内容。", "success");
    } else if (receipt.status === "FAILED")
      throw new Error("服务已确认原草稿未保存，输入已保留，可核对后重新保存。");
    else throw new Error("草稿保存结果仍待确认，请核对原操作，不要重复保存。");
  };
  const run = async (operation: () => Promise<void>) => {
    if (
      lock.current ||
      !current() ||
      !session.authenticated ||
      row.sample ||
      row.id === "sample"
    )
      return;
    lock.current = true;
    setState({ scope, busy: true, error: "" });
    try {
      await operation();
    } catch (error) {
      if (current())
        setState({ scope, busy: false, error: errorMessage(error) });
    } finally {
      if (current()) {
        lock.current = false;
        setState((old) => ({ ...old, busy: false }));
      }
    }
  };
  const save = () =>
    run(async () => {
      const snapshot = draftSnapshot(row, draft, session.accountScope);
      const contentHash = await boundedRequest(() => snapshotDigest(snapshot), {
        timeoutMessage: "草稿检查超时，尚未发起保存。",
      });
      if (!current()) return;
      const binding: DraftSaveBinding = {
        opportunityId: row.id,
        channel: draft.channel,
        requestId:
          (service.contactDrafts ? "" : "legacy:") + crypto.randomUUID(),
        contentHash,
      };
      setEntries((old) => {
        if (Object.keys(old).some(matches))
          throw new Error("此用途还有保存结果待确认，请先核对原操作。");
        return { ...old, [draftSaveKey(binding)]: "PENDING" };
      });
      try {
        if (service.contactDrafts) {
          const receipt = await boundedRequest(
            () => service.contactDrafts!.save({ binding, snapshot }),
            {
              timeoutMessage:
                "草稿保存结果未确认，当前文字已保留，请核对原操作。",
            },
          );
          await accept(receipt, binding);
        } else {
          await boundedRequest(() => service.saveContact(snapshot.draft), {
            timeoutMessage:
              "草稿保存结果未确认，当前文字已保留；原同步接口暂不支持请求核对，请勿重复保存。",
          });
          remove(binding);
          if (current()) {
            onSaved(snapshot);
            notify("草稿已保存到客户空间。", "success");
          }
        }
      } catch (error) {
        const rejected =
          error instanceof ServiceError &&
          ((["CAPABILITY_UNAVAILABLE", "UNAVAILABLE"].includes(error.code) &&
            error.status === 501) ||
            (error.code === "DRAFT_SAVE_REJECTED" &&
              error.status >= 400 &&
              error.status < 500 &&
              error.status !== 408));
        if (rejected) remove(binding);
        // No generic HTTP or transport error proves that the write did not occur.
        throw error;
      }
    });
  const reconcile = (key: string) =>
    run(async () => {
      const binding = draftSaveBindingFromKey(key);
      if (!matches(key)) throw new Error("保存操作不属于当前商机与用途。");
      if (binding.requestId.startsWith("legacy:") || !service.contactDrafts)
        throw new Error(
          "原同步接口没有保存请求查询能力，请核对客户空间草稿并由服务管理员确认；当前不会重复保存。",
        );
      await accept(
        await boundedRequest(() => service.contactDrafts!.operation(binding), {
          timeoutMessage: "原草稿保存核对超时，保护继续保留。",
        }),
        binding,
      );
    });
  return { ...shown, pending, blocked: pending.length > 0, save, reconcile };
}
