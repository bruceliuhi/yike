import { useState } from "react";
import { useUnsavedChanges } from "../../app/hooks";
import { Button, Confirm, Drawer, Field, Notice } from "../../components/ui";
import {
  extractedFieldsSchema,
  materialFieldLabels,
  materialFields,
  type Material,
} from "../../domain/materials";
import type { ProfileFields } from "../../domain/models";

export function MaterialExtraction({
  record,
  currentFields,
  mode,
  busy,
  locked,
  error,
  onClose,
  onConfirm,
}: {
  record: Material;
  currentFields: ProfileFields;
  mode: "review" | "apply";
  busy: boolean;
  locked: boolean;
  error: string;
  onClose: () => void;
  onConfirm: (fields: Partial<ProfileFields>) => void;
}) {
  const original = record.extraction?.fields || {};
  const [values, setValues] = useState<Partial<ProfileFields>>({ ...original });
  const [selected, setSelected] = useState<Set<keyof ProfileFields>>(
    () => new Set(materialFields.filter((key) => original[key]?.trim())),
  );
  const [baseline] = useState(JSON.stringify(currentFields));
  const [verified, setVerified] = useState(false);
  const [failure, setFailure] = useState("");
  const [discard, setDiscard] = useState(false);
  const dirty = JSON.stringify(values) !== JSON.stringify(original);
  const changed =
    mode === "apply" && baseline !== JSON.stringify(currentFields);
  useUnsavedChanges(dirty);
  const close = () => (dirty || busy ? setDiscard(true) : onClose());
  const submit = () => {
    if (!verified || changed || locked || busy) return;
    const fields = Object.fromEntries(
      [...selected].map((key) => [key, values[key]?.trim() || ""]),
    );
    const parsed = extractedFieldsSchema.safeParse(fields);
    if (!parsed.success || Object.values(fields).some((value) => !value)) {
      setFailure("请选择并填写至少一项有效提取内容。");
      return;
    }
    onConfirm(parsed.data);
  };
  return (
    <>
      <Drawer
        title={mode === "review" ? "确认资料提取" : "填入画像草稿"}
        onClose={close}
        footer={
          <>
            <Button onClick={close}>取消</Button>
            <Button
              variant="primary"
              loading={busy}
              disabled={locked || changed || !verified || !selected.size}
              onClick={submit}
            >
              {mode === "review" ? "确认提取结果" : "填入画像草稿"}
            </Button>
          </>
        }
      >
        <p>
          {record.name} · 资料版本 {record.version}
        </p>
        <Notice>
          {mode === "review"
            ? "对照原文核实并编辑提取内容；确认不等于确认业务画像。"
            : "仅填入勾选字段，替换前请核对当前人工内容；画像仍需单独保存和确认。"}
        </Notice>
        <details className="material-source">
          <summary>查看资料原文</summary>
          <p>{record.text}</p>
        </details>
        <fieldset
          className="material-fieldset"
          disabled={busy || locked || changed}
        >
          {materialFields
            .filter((key) => Object.hasOwn(original, key))
            .map((key) => (
              <section className="material-extraction-field" key={key}>
                <label className="checkbox-row">
                  <input
                    type="checkbox"
                    aria-label={`采用${materialFieldLabels[key]}`}
                    checked={selected.has(key)}
                    onChange={(e) => {
                      setSelected((previous) => {
                        const next = new Set(previous);
                        if (e.target.checked) next.add(key);
                        else next.delete(key);
                        return next;
                      });
                      setVerified(false);
                    }}
                  />
                  {materialFieldLabels[key]}
                </label>
                {mode === "apply" && (
                  <p className="field-hint">
                    当前内容：{currentFields[key] || "未填写"}
                  </p>
                )}
                {record
                  .extraction!.evidence.filter(
                    (evidence) => evidence.field === key,
                  )
                  .map((evidence, index) => (
                    <blockquote key={index}>{evidence.quote}</blockquote>
                  ))}
                <Field label={`${materialFieldLabels[key]}提取内容`}>
                  <textarea
                    aria-label={`${materialFieldLabels[key]}提取内容`}
                    disabled={!selected.has(key)}
                    maxLength={key === "preference" ? 200 : 500}
                    value={values[key] || ""}
                    onChange={(e) => {
                      setValues((previous) => ({
                        ...previous,
                        [key]: e.target.value,
                      }));
                      setVerified(false);
                    }}
                  />
                </Field>
              </section>
            ))}
          <label className="checkbox-row">
            <input
              type="checkbox"
              checked={verified}
              onChange={(e) => setVerified(e.target.checked)}
            />
            {mode === "review"
              ? "已核对原文，确认所选提取内容准确"
              : "已核对当前画像，确认替换所选字段"}
          </label>
        </fieldset>
        {changed && (
          <Notice tone="warning">
            画像内容已变化，请关闭后重新核对，当前不会覆盖人工修改。
          </Notice>
        )}
        {(failure || error) && <Notice tone="error">{failure || error}</Notice>}
        {locked && !busy && (
          <Notice>原操作结果待确认，请关闭面板后核对原操作。</Notice>
        )}
      </Drawer>
      {discard && (
        <Confirm
          title="离开提取确认？"
          confirmText="关闭面板"
          onCancel={() => setDiscard(false)}
          onConfirm={onClose}
        >
          <p>
            {busy
              ? "关闭不会撤销已提交操作；未提交修改将丢弃。"
              : "未提交的提取修改将丢弃。"}
          </p>
        </Confirm>
      )}
    </>
  );
}
