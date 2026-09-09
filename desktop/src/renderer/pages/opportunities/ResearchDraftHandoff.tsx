import { useEffect, useRef, useState } from "react";
import { useApp } from "../../app/context";
import { useTaskDraft, useTaskLibrary } from "../../app/taskDraft";
import { createDraftFromResearch } from "../../app/researchHandoff";
import { Confirm, Notice } from "../../components/ui";
import type { Opportunity, TaskDraft } from "../../domain/models";
import {
  researchBinding,
  sameResearchBinding,
  type SimilarResearchHandoff,
} from "../../domain/opportunityResearch";
import { SimilarResearchDrawer } from "./SimilarResearchDrawer";

function hasContent(draft: TaskDraft) {
  return Boolean(
    draft.name.trim() ||
    draft.profileId ||
    draft.terms.length ||
    draft.exclusions.length ||
    draft.links.trim() ||
    draft.platforms.length,
  );
}
export function ResearchDraftHandoff({
  opportunity,
  onClose,
}: {
  opportunity: Opportunity;
  onClose: () => void;
}) {
  const { session, navigate } = useApp();
  const [currentDraft, setDraft] = useTaskDraft(
    session.userId,
    "once",
    session.accountScope,
  );
  const [, setLibrary] = useTaskLibrary(session.userId, session.accountScope);
  const [pending, setPending] = useState<SimilarResearchHandoff | null>(null);
  const [accepted, setAccepted] = useState(false);
  const [error, setError] = useState("");
  const completed = useRef<string | null>(null);
  const current = useRef({ session, opportunity, currentDraft });
  current.current = { session, opportunity, currentDraft };
  const needsConfirmation = Boolean(
    pending &&
    currentDraft.id !== pending.draftId &&
    hasContent(currentDraft) &&
    !currentDraft.savedAt,
  );
  useEffect(() => {
    if (
      !pending ||
      (needsConfirmation && !accepted) ||
      completed.current === pending.requestId
    )
      return;
    try {
      const state = current.current;
      const binding = researchBinding(
        state.opportunity,
        state.session.authenticated ? state.session.userId : undefined,
        state.session.accountScope,
      );
      if (!binding || !sameResearchBinding(binding, pending.binding))
        throw new Error("工作空间或机会版本已变化，未创建新草稿。");
      const next = createDraftFromResearch(pending);
      // Only local draft writes: preserve the current input before selecting the new draft.
      setLibrary((old) => {
        const rows = old.filter(
          (item) => item.id !== next.id && item.id !== state.currentDraft.id,
        );
        if (hasContent(state.currentDraft) && state.currentDraft.id !== next.id)
          rows.push(state.currentDraft);
        return [...rows, next];
      });
      setDraft(next);
      completed.current = pending.requestId;
      onClose();
      navigate("/tasks/new?mode=once&step=conditions");
    } catch (e) {
      setError(e instanceof Error ? e.message : "未能创建本机草稿，请重试。");
    }
  }, [pending, accepted, needsConfirmation]);
  if (!pending)
    return (
      <SimilarResearchDrawer
        opportunity={opportunity}
        onClose={onClose}
        onCreateDraft={setPending}
      />
    );
  return (
    <Confirm
      title={error ? "任务草稿尚未创建" : "切换到相似研究草稿？"}
      onCancel={() => {
        setPending(null);
        setAccepted(false);
        setError("");
      }}
      onConfirm={() => {
        setAccepted(true);
      }}
      confirmText="保留旧草稿并继续"
      confirmDisabled={Boolean(error)}
    >
      <p>
        当前任务有未保存修改。继续后会保留到本机草稿列表，再打开新草稿；不会启动研究。
      </p>
      {error && <Notice tone="error">{error}</Notice>}
    </Confirm>
  );
}
