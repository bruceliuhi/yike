import { useEffect, useState } from "react";
import { useApp } from "../../app/context";
import { useLocalDraft } from "../../app/hooks";
import { taskDraftOwner, useTaskDraft } from "../../app/taskDraft";
import { defaultResearchSettings } from "../../domain/researchUsage";
import { useOperationLedger } from "../../app/operationLedger";
import {
  Button,
  Confirm,
  Field,
  Modal,
  Notice,
  formatDate,
} from "../../components/ui";
import type { TaskDraft } from "../../domain/models";
import { errorMessage } from "../../services/contracts";
import {
  draftFromTemplate,
  draftSourceIds,
  localTemplatesSchema,
  templateFromDraft,
  type LocalTaskTemplate,
} from "./localTemplates";
import { TaskPlatforms } from "./TaskPlatforms";
import { useTaskScope } from "./useTaskScope";
export function useTaskTemplates() {
  const { session, route, navigate, notify } = useApp();
  const scope = useTaskScope(route.path);
  const [templates, setTemplates] = useLocalDraft<LocalTaskTemplate[]>(
    `task-templates.${taskDraftOwner(session.userId, session.accountScope)}`,
    [],
    (value) => localTemplatesSchema.safeParse(value).success,
  );
  const [, setDraft] = useTaskDraft(
    session.userId,
    "once",
    session.accountScope,
  );
  const [unknown, setUnknown] = useOperationLedger(
    "unknown-task-starts",
    session.userId,
  );
  const [saving, setSaving] = useState<{
    draft: TaskDraft;
    identity: object;
  } | null>(null);
  const [deleting, setDeleting] = useState<{
    template: LocalTaskTemplate;
    identity: object;
  } | null>(null);
  const [name, setName] = useState("");
  const [error, setError] = useState("");
  useEffect(() => {
    setSaving(null);
    setDeleting(null);
    setName("");
    setError("");
  }, [scope.identity]);
  const blocked = (ids: string[]) => ids.some((id) => !!unknown[id]);
  const assertClear = (ids: string[]) => {
    if (!session.authenticated || !session.userId || !scope.current())
      throw new Error("请登录当前客户空间后使用本机模板。");
    // Re-read the durable map inside its updater, including changes from another window.
    // Returning it unchanged verifies the guard without deleting any unresolved record.
    setUnknown((old) => {
      if (ids.some((id) => !!old[id]))
        throw new Error(
          "源草稿或其模板来源有启动结果待核对，当前不能保存或使用模板。",
        );
      return old;
    });
  };
  const open = (draft: TaskDraft) => {
    setError("");
    try {
      assertClear(draftSourceIds(draft));
      setSaving({ draft: structuredClone(draft), identity: scope.identity });
      setName(draft.name);
    } catch (e) {
      setError(errorMessage(e));
    }
  };
  const save = () => {
    if (!saving || saving.identity !== scope.identity) return;
    try {
      if (!name.trim() || Array.from(name.trim()).length > 60)
        throw new Error("请填写1至60字的模板名称。");
      assertClear(draftSourceIds(saving.draft));
      const template = templateFromDraft(saving.draft, name.trim());
      setTemplates((old) => {
        if (old.length >= 50)
          throw new Error("本机会话最多保存50个模板，请先删除不再使用的模板。");
        if (old.some((item) => item.name === template.name))
          throw new Error("已有同名模板，请使用其他名称。");
        return [...old, template];
      });
      setSaving(null);
      setError("");
      notify("模板已保留在本机会话，未同步到服务端。", "success");
    } catch (e) {
      setError(errorMessage(e));
    }
  };
  const create = (template: LocalTaskTemplate) => {
    try {
      assertClear(template.sourceDraftIds);
      const next = draftFromTemplate(template);
      next.research ??= defaultResearchSettings();
      setDraft(next);
      navigate(
        next.mode === "monitor" ? "/tasks/new?mode=monitor" : "/tasks/new",
      );
    } catch (e) {
      setError(errorMessage(e));
    }
  };
  const remove = () => {
    if (
      !deleting ||
      deleting.identity !== scope.identity ||
      !scope.current() ||
      !session.authenticated
    ) return;
    setTemplates((old) => old.filter((item) => item.id !== deleting.template.id));
    setDeleting(null);
    notify("本机会话模板已删除。");
  };
  const visible = session.authenticated ? templates : [];
  return {
    saveTemplate: open,
    section: (
      <section className="task-templates" aria-label="保存的模板">
        <div className="section-heading">
          <h2>保存的模板</h2>
          <span className="muted text-small">本机会话模板 · 未同步</span>
        </div>
        {visible.length ? (
          visible.map((template) => (
            <div className="task-template-row" key={template.id}>
              <div>
                <strong>{template.name}</strong>
                <p className="task-template-platforms">
                  <TaskPlatforms
                    platforms={template.conditions.platforms}
                    size={16}
                  />
                </p>
                <p className="field-hint">
                  保存于 {formatDate(template.savedAt)}
                  {blocked(template.sourceDraftIds)
                    ? " · 来源启动结果待核对"
                    : ""}
                </p>
              </div>
              <div className="inline-actions">
                <Button
                  variant="ghost"
                  disabled={blocked(template.sourceDraftIds)}
                  onClick={() => create(template)}
                >
                  从模板新建
                </Button>
                <Button variant="ghost" onClick={() => setDeleting({ template, identity: scope.identity })}>
                  删除模板
                </Button>
              </div>
            </div>
          ))
        ) : (
          <p className="muted">
            {session.authenticated
              ? "暂无保存的模板，可从本机草稿保存条件。"
              : "登录后可保存和使用本机会话模板。"}
          </p>
        )}
        {error && !saving && <Notice tone="error">{error}</Notice>}
      </section>
    ),
    dialog: (
      <>
        {saving && saving.identity === scope.identity && (
          <Modal
            title="保存本机模板"
            size="small"
            onClose={() => setSaving(null)}
            footer={
              <>
                <Button onClick={() => setSaving(null)}>取消</Button>
                <Button
                  variant="primary"
                  disabled={blocked(draftSourceIds(saving.draft))}
                  onClick={save}
                >
                  保存模板
                </Button>
              </>
            }
          >
            <Field label="模板名称" hint="仅保存条件，不包含运行结果。">
              <input
                aria-label="模板名称"
                value={name}
                maxLength={60}
                onChange={(event) => setName(event.target.value)}
              />
            </Field>
            <p className="field-hint">
              本机会话模板 · 未同步；退出登录或清除本机草稿时一并清除。
            </p>
            {error && <Notice tone="error">{error}</Notice>}
          </Modal>
        )}
        {deleting && deleting.identity === scope.identity && (
          <Confirm
            title="删除本机模板？"
            danger
            confirmText="删除模板"
            onCancel={() => setDeleting(null)}
            onConfirm={remove}
          >
            <p>删除“{deleting.template.name}”的本机会话模板，不会删除任务或核对记录。</p>
          </Confirm>
        )}
      </>
    ),
  };
}
