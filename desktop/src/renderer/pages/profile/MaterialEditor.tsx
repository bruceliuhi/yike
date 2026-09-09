import { useEffect, useRef, useState } from "react";
import { boundedRequest } from "../../app/boundedRequest";
import { useUnsavedChanges } from "../../app/hooks";
import {
  Button,
  Confirm,
  Drawer,
  Field,
  Notice,
  Tabs,
} from "../../components/ui";
import {
  MATERIAL_LIMIT_BYTES,
  materialInputSchema,
  type Material,
  type MaterialInput,
} from "../../domain/materials";

export function MaterialEditor({
  record,
  busy,
  locked,
  error,
  progress,
  onClose,
  onSave,
}: {
  record?: Material;
  busy: boolean;
  locked: boolean;
  error: string;
  progress: number | null;
  onClose: () => void;
  onSave: (input: MaterialInput) => void;
}) {
  const [input, setInput] = useState<MaterialInput>(() =>
    record
      ? {
          name: record.name,
          text: record.text,
          purpose: record.purpose,
          visibility: record.visibility,
          ...(record.fileName
            ? { fileName: record.fileName, bytes: record.bytes }
            : {}),
        }
      : { name: "", text: "", purpose: "产品介绍", visibility: "internal" },
  );
  const [baseline] = useState(JSON.stringify(input));
  const [mode, setMode] = useState("text");
  const [failure, setFailure] = useState("");
  const [reading, setReading] = useState(false);
  const [discard, setDiscard] = useState(false);
  const generation = useRef(0);
  const controller = useRef<AbortController | null>(null);
  const dirty = JSON.stringify(input) !== baseline;
  useUnsavedChanges(dirty);
  useEffect(
    () => () => {
      generation.current++;
      controller.current?.abort();
    },
    [],
  );
  const close = () => {
    if (dirty || busy || reading) setDiscard(true);
    else onClose();
  };
  const read = async (file?: File) => {
    const request = ++generation.current;
    controller.current?.abort();
    setReading(false);
    setFailure("");
    if (!file) return;
    if (!/\.(txt|md)$/i.test(file.name) || file.size > MATERIAL_LIMIT_BYTES) {
      setFailure("请选择不超过 200 KB 的 TXT 或 Markdown 文件。");
      return;
    }
    const abort = new AbortController();
    controller.current = abort;
    setReading(true);
    try {
      const text = await boundedRequest(() => file.text(), {
        signal: abort.signal,
        timeoutMessage: "文件读取超时，请重新选择或粘贴文字。",
      });
      if (request !== generation.current) return;
      if (
        !text.trim() ||
        text.length > 2000 ||
        text.includes("\0") ||
        new TextEncoder().encode(text).length > MATERIAL_LIMIT_BYTES
      )
        throw new Error("文件内容须为有效文字，且不超过 2000 字。");
      setInput((old) => ({
        ...old,
        text,
        name: old.name || file.name.replace(/\.(txt|md)$/i, "").slice(0, 100),
        fileName: file.name,
        bytes: file.size,
      }));
    } catch (reason) {
      if (request === generation.current)
        setFailure(
          reason instanceof Error ? reason.message : "读取失败，请重试。",
        );
    } finally {
      if (request === generation.current) setReading(false);
    }
  };
  return (
    <>
      <Drawer
        title={record ? "编辑资料" : "添加资料"}
        onClose={close}
        footer={
          <>
            <Button onClick={close}>取消</Button>
            <Button
              variant="primary"
              loading={busy}
              disabled={locked || reading}
              onClick={() => {
                const parsed = materialInputSchema.safeParse(input);
                if (!parsed.success) {
                  setFailure(
                    "请填写资料名称和内容；名称最多 100 字，内容最多 2000 字。",
                  );
                  return;
                }
                setFailure("");
                onSave(parsed.data);
              }}
            >
              保存草稿
            </Button>
          </>
        }
      >
        <fieldset className="material-fieldset" disabled={busy || locked}>
          <Field label="资料名称" required>
            <input
              aria-label="资料名称"
              maxLength={100}
              value={input.name}
              placeholder="请输入资料名称"
              onChange={(e) =>
                setInput((old) => ({ ...old, name: e.target.value }))
              }
            />
          </Field>
          <Field label="内容" required>
            <Tabs
              active={mode}
              items={[
                { key: "file", label: "上传文件" },
                { key: "text", label: "粘贴文字" },
              ]}
              onChange={(value) => {
                generation.current++;
                controller.current?.abort();
                setReading(false);
                setMode(value);
              }}
            />
            {mode === "file" ? (
              <div className="upload-field">
                <input
                  aria-label="上传资料文件"
                  type="file"
                  accept=".txt,.md,text/plain,text/markdown"
                  disabled={reading}
                  onChange={(event) => {
                    void read(event.target.files?.[0]);
                    event.target.value = "";
                  }}
                />
                <p className="field-hint">
                  TXT / Markdown，最多 200 KB、2000
                  字。保存草稿时同步文字至当前画像。
                </p>
                {reading && <p role="status">正在读取文件…</p>}
                {input.fileName && (
                  <p>
                    {input.fileName} · {input.text.length} 字
                  </p>
                )}
              </div>
            ) : (
              <>
                <textarea
                  aria-label="资料内容"
                  rows={7}
                  maxLength={2000}
                  placeholder="请输入资料内容，支持粘贴文字…"
                  value={input.text}
                  onChange={(e) =>
                    setInput((old) => ({
                      ...old,
                      text: e.target.value,
                      fileName: undefined,
                      bytes: undefined,
                    }))
                  }
                />
                <p className="field-hint">{input.text.length}/2000</p>
              </>
            )}
          </Field>
          <Field label="用途" required>
            <select
              aria-label="资料用途"
              value={input.purpose}
              onChange={(e) =>
                setInput((old) => ({
                  ...old,
                  purpose: e.target.value as MaterialInput["purpose"],
                }))
              }
            >
              <option>产品介绍</option>
              <option>真实案例</option>
              <option>服务说明</option>
            </select>
          </Field>
          <Field label="引用范围" required>
            {(["internal", "external"] as const).map((value) => (
              <label className="radio-row" key={value}>
                <input
                  type="radio"
                  name="material-visibility"
                  checked={input.visibility === value}
                  onChange={() =>
                    setInput((old) => ({ ...old, visibility: value }))
                  }
                />
                <span>
                  {value === "internal" ? "仅供内部判断" : "允许对外引用"}
                  <small>
                    {value === "internal"
                      ? "仅用于内部画像与判断，不用于外发内容。"
                      : "需先确认提取结果，才可用于联系准备。"}
                  </small>
                </span>
              </label>
            ))}
          </Field>
        </fieldset>
        {busy && (
          <p role="status">
            {progress === null ? "正在同步资料…" : `正在同步资料：${progress}%`}
          </p>
        )}
        {progress !== null && (
          <progress aria-label="资料上传进度" max={100} value={progress} />
        )}
        {record?.status === "READY" && (
          <Notice>
            修改会产生新资料版本，需重新解析和确认；旧引用保留版本记录。
          </Notice>
        )}
        {(failure || error) && <Notice tone="error">{failure || error}</Notice>}
        {locked && !busy && (
          <Notice>
            原操作结果待确认；当前输入保留，关闭面板后可核对原操作。
          </Notice>
        )}
      </Drawer>
      {discard && (
        <Confirm
          title="离开资料编辑？"
          confirmText="关闭面板"
          onCancel={() => setDiscard(false)}
          onConfirm={onClose}
        >
          <p>
            {busy || locked
              ? "已提交的操作不会因关闭被撤销。稍后可核对原操作；未提交的输入将丢弃。"
              : "未保存的资料修改将丢弃。"}
          </p>
        </Confirm>
      )}
    </>
  );
}
