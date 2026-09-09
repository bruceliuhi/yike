import { useLayoutEffect, useRef, useState } from "react";
import { Plus, X } from "@phosphor-icons/react";
import { addTerms, termKey } from "../domain/task";
import type { Term } from "../domain/models";
import { Button } from "./ui";
export function TermEditor({
  label,
  terms,
  onChange,
  onRemove,
  neutral = false,
}: {
  label: string;
  terms: Term[];
  onChange: (terms: Term[]) => void;
  onRemove: (id: string) => void;
  neutral?: boolean;
}) {
  const [adding, setAdding] = useState(false);
  const [input, setInput] = useState("");
  const [editing, setEditing] = useState<string | null>(null);
  const [edit, setEdit] = useState("");
  const [error, setError] = useState("");
  const addInput = useRef<HTMLInputElement>(null);
  const pasteCaret = useRef<number | null>(null);
  useLayoutEffect(() => {
    if (pasteCaret.current !== null && addInput.current) {
      addInput.current.setSelectionRange(pasteCaret.current, pasteCaret.current);
      pasteCaret.current = null;
    }
  }, [input]);
  const add = () => {
    if (!input.trim()) {
      setAdding(false);
      return;
    }
    const result = addTerms(terms, input);
    if (result.length > 20) {
      setError("最多可填写20个词项。");
      return;
    }
    if (result.some((t) => t.value.length > 80)) {
      setError("每个词项最多80个字符。");
      return;
    }
    onChange(result);
    setInput("");
    setAdding(false);
    setError("");
  };
  const saveEdit = (id: string) => {
    if (!edit.trim()) {
      setError("词项不能为空，可使用删除按钮移除。");
      return;
    }
    if (
      edit.length > 80 ||
      terms.some((t) => t.id !== id && termKey(t.value) === termKey(edit))
    ) {
      setError("词项已存在或超过80个字符。");
      return;
    }
    onChange(
      terms.map((t) =>
        t.id === id ? { ...t, value: edit.trim(), edited: true } : t,
      ),
    );
    setEditing(null);
    setError("");
  };
  return (
    <div>
      <div
        className={`term-editor ${neutral ? "neutral" : ""}`}
        aria-label={label}
      >
        {terms.map((term) => (
          <div className="term" key={term.id}>
            {editing === term.id ? (
              <input
                aria-label={`修改${term.value}`}
                value={edit}
                autoFocus
                onChange={(e) => setEdit(e.target.value)}
                onBlur={() => saveEdit(term.id)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.nativeEvent.isComposing) {
                    e.preventDefault();
                    saveEdit(term.id);
                  }
                  if (e.key === "Escape") {
                    e.preventDefault();
                    setEditing(null);
                  }
                }}
              />
            ) : (
              <button
                type="button"
                title="点击编辑"
                onClick={() => {
                  setEdit(term.value);
                  setEditing(term.id);
                }}
              >
                {term.value}
              </button>
            )}
            <button
              type="button"
              className="term-remove"
              aria-label={`删除${term.value}`}
              onClick={() => onRemove(term.id)}
            >
              <X size={12} />
            </button>
          </div>
        ))}
        {adding ? (
          <div className="term-add">
            <input
              ref={addInput}
              autoFocus
              aria-label={`新增${label}`}
              value={input}
              placeholder="逗号或换行可批量添加"
              onChange={(e) => setInput(e.target.value)}
              onPaste={(e) => {
                const text = e.clipboardData.getData("text/plain");
                if (!/[\r\n]/.test(text)) return;
                // A single-line input strips pasted line breaks before onChange.
                // Preserve their meaning as separators without committing the draft.
                e.preventDefault();
                const field = e.currentTarget;
                const start = field.selectionStart ?? input.length;
                const end = field.selectionEnd ?? start;
                const pasted = text.replace(/\r\n?|\n/g, ", ");
                const next = input.slice(0, start) + pasted + input.slice(end);
                const caret = start + pasted.length;
                // An unchanged value does not trigger the input layout effect.
                if (next === input) {
                  field.setSelectionRange(caret, caret);
                  pasteCaret.current = null;
                } else {
                  pasteCaret.current = caret;
                  setInput(next);
                }
              }}
              onBlur={add}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.nativeEvent.isComposing) {
                  e.preventDefault();
                  add();
                }
                if (e.key === "Escape") {
                  setInput("");
                  setAdding(false);
                }
              }}
            />
            <Button variant="ghost" onClick={add}>
              添加
            </Button>
          </div>
        ) : (
          <Button variant="ghost" onClick={() => setAdding(true)}>
            <Plus />
            添加
          </Button>
        )}
      </div>
      {error && (
        <p role="alert" className="field-error">
          {error}
        </p>
      )}
    </div>
  );
}
