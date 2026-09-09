import { useApp } from "../../app/context";
import { useLocalDraft } from "../../app/hooks";
import { Field } from "../../components/ui";
import type { Opportunity } from "../../domain/models";
import { isSample } from "../Opportunities";

/** Personal preparation notes stay outside ContactDraft and every send payload. */
export function ContactNotes({ row }: { row: Opportunity }) {
  const { session } = useApp();
  const readOnly = isSample(row) || !session.authenticated;
  const [note, setNote] = useLocalDraft(
    `contact-note:${session.userId || "public"}:${row.id}:${row.profileVersionId}`,
    "",
    (value) => typeof value === "string" && Array.from(value).length <= 500,
  );
  return (
    <section className="contact-notes">
      <Field
        label="备注"
        hint={readOnly ? "公开样例只读。" : "仅保留在本机会话，不随消息发送。"}
      >
        <textarea
          aria-label="联系准备备注"
          placeholder="添加备注（选填）"
          rows={4}
          value={readOnly ? "" : note}
          readOnly={readOnly}
          onChange={(event) => {
            if (!readOnly)
              setNote(Array.from(event.target.value).slice(0, 500).join(""));
          }}
        />
      </Field>
      <p className="character-count">
        {readOnly ? 0 : Array.from(note).length}/500
      </p>
    </section>
  );
}
