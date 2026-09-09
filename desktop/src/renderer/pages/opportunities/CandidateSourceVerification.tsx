import { useEffect, useRef, useState } from "react";
import {
  sourceVerificationRequestSchema,
  type CandidateReviewBinding,
  type CandidateSourceVerificationDto,
  type SourceVerificationRequest,
} from "../../../shared/candidateReviewApi";
import { useUnsavedChanges } from "../../app/hooks";
import { Button, Field, Notice } from "../../components/ui";
import "./candidateSourceVerification.css";

export interface CandidateSourceVerificationProps {
  binding: CandidateReviewBinding;
  verification?: CandidateSourceVerificationDto;
  disabled?: boolean;
  onSubmit: (request: SourceVerificationRequest) => Promise<unknown>;
  onChange?: () => void;
}

function bindingKey(binding: CandidateReviewBinding) {
  return JSON.stringify([
    binding.candidateId,
    binding.candidateRevision,
    binding.sourceVersionId,
    binding.profileId,
    binding.profileVersion,
  ]);
}

// A changed identity unmounts the entire draft during render, including A → B → A.
export function CandidateSourceVerification(
  props: CandidateSourceVerificationProps,
) {
  return <VerificationForm key={bindingKey(props.binding)} {...props} />;
}

type SourceFields = Pick<
  SourceVerificationRequest,
  "status" | "openingMethod" | "locator" | "excerpt" | "contactMethod"
>;
const statusLabels = {
  OPEN: "已打开",
  BLOCKED: "访问受阻",
  EXPIRED: "已过期",
  UNVERIFIED: "未核实",
};
const openingLabels = { DIRECT: "直接打开", IN_PLATFORM: "平台内定位" };
const contactLabels = {
  COMMENT: "评论",
  DM: "私信",
  PUBLIC_CONTACT: "公开联系信息",
  NONE: "无可核实联系路径",
};

function BindingDetails({ binding }: { binding: CandidateReviewBinding }) {
  return (
    <dl className="candidate-verification-binding">
      <dt>候选 ID</dt>
      <dd>{binding.candidateId}</dd>
      <dt>候选版本</dt>
      <dd>{binding.candidateRevision}</dd>
      <dt>来源版本</dt>
      <dd>{binding.sourceVersionId}</dd>
      <dt>画像 ID</dt>
      <dd>{binding.profileId}</dd>
      <dt>画像版本</dt>
      <dd>{binding.profileVersion}</dd>
    </dl>
  );
}

function VerificationForm({
  binding,
  verification,
  disabled = false,
  onSubmit,
  onChange,
}: CandidateSourceVerificationProps) {
  const [fields, setFields] = useState<SourceFields>({
    status: "UNVERIFIED",
    openingMethod: "DIRECT",
    locator: "",
    excerpt: "",
    contactMethod: "NONE",
  });
  const [confirmed, setConfirmed] = useState(false);
  const [edited, setEdited] = useState(false);
  const [submittedId, setSubmittedId] = useState<string>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const lock = useRef(false);
  const alive = useRef(true);
  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);
  const currentReceipt =
    !!verification &&
    bindingKey(verification.binding) === bindingKey(binding) &&
    verification.candidateId === binding.candidateId;
  const saved = currentReceipt && verification?.requestId === submittedId;
  useUnsavedChanges((edited && !saved) || busy || confirmed);

  function change<K extends keyof SourceFields>(
    key: K,
    value: SourceFields[K],
  ) {
    if (disabled || lock.current) return;
    setFields((previous) => ({ ...previous, [key]: value }));
    setConfirmed(false);
    setEdited(true);
    setSubmittedId(undefined);
    setError("");
    onChange?.();
  }

  async function submit() {
    if (disabled || lock.current || !confirmed) return;
    const parsed = sourceVerificationRequestSchema.safeParse({
      ...binding,
      ...fields,
      requestId: crypto.randomUUID(),
      humanConfirmed: true,
    });
    if (!parsed.success) {
      setError(
        "请填写有效的定位描述和原文逐字摘录（各不超过 2000 字），并确认当前核验信息。",
      );
      return;
    }
    lock.current = true;
    setBusy(true);
    setError("");
    setSubmittedId(parsed.data.requestId);
    try {
      await onSubmit(parsed.data);
      // The parent's authenticated receipt prop is the only success evidence.
    } catch {
      if (alive.current)
        setError("核验请求未取得可确认结果，请先核对原请求，不要重复提交。");
    } finally {
      if (alive.current) {
        lock.current = false;
        setBusy(false);
        setConfirmed(false);
      }
    }
  }

  return (
    <section
      className="candidate-source-verification"
      aria-label="人工来源核验"
    >
      <h3>人工来源核验</h3>
      <Notice>
        “已打开”仅是你的人工核对声明，不是平台验证或发送授权。仅点击回源链接不会保存核验；未核实的信息请如实记录。
      </Notice>
      <details className="candidate-verification-identity">
        <summary>本次核验绑定（当前版本）</summary>
        <BindingDetails binding={binding} />
      </details>
      {verification ? (
        <div className="candidate-verification-receipt">
          <h4>
            {currentReceipt
              ? "当前版本核验记录"
              : "历史核验记录，与当前版本不匹配"}
          </h4>
          <dl className="candidate-verification-binding">
            <dt>核验 ID</dt>
            <dd>{verification.id}</dd>
            <dt>原请求 ID</dt>
            <dd>{verification.requestId}</dd>
            <dt>核验人</dt>
            <dd>{verification.checkedBy}</dd>
            <dt>核验时间</dt>
            <dd>{verification.checkedAt}</dd>
            <dt>来源状态</dt>
            <dd>{statusLabels[verification.status]}</dd>
            <dt>打开方式</dt>
            <dd>{openingLabels[verification.openingMethod]}</dd>
            <dt>联系路径</dt>
            <dd>{contactLabels[verification.contactMethod]}</dd>
            <dt>已保存定位描述</dt>
            <dd className="candidate-verification-verbatim">
              {verification.locator}
            </dd>
            <dt>已保存逐字摘录</dt>
            <dd className="candidate-verification-verbatim">
              {verification.excerpt}
            </dd>
          </dl>
          {!currentReceipt ? (
            <Notice tone="warning">
              此记录不能用作当前版本核验，请重新核对。
            </Notice>
          ) : null}
          <details>
            <summary>查看核验记录绑定</summary>
            <BindingDetails binding={verification.binding} />
          </details>
        </div>
      ) : null}
      <form
        onSubmit={(event) => {
          event.preventDefault();
          void submit();
        }}
      >
        <fieldset disabled={disabled || busy}>
          <legend>记录本次亲自核对的结果</legend>
          <div className="candidate-verification-options">
            <Field label="来源状态" required>
              <select
                aria-label="来源状态"
                value={fields.status}
                onChange={(event) =>
                  change("status", event.target.value as SourceFields["status"])
                }
              >
                {Object.entries(statusLabels).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="打开方式" required>
              <select
                aria-label="打开方式"
                value={fields.openingMethod}
                onChange={(event) =>
                  change(
                    "openingMethod",
                    event.target.value as SourceFields["openingMethod"],
                  )
                }
              >
                {Object.entries(openingLabels).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="联系路径" required>
              <select
                aria-label="联系路径"
                value={fields.contactMethod}
                onChange={(event) =>
                  change(
                    "contactMethod",
                    event.target.value as SourceFields["contactMethod"],
                  )
                }
              >
                {Object.entries(contactLabels).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </Field>
          </div>
          <Field
            label="定位描述"
            required
            hint="填写实际打开地址或平台内定位步骤；没有核实到的情况请明确说明。"
          >
            <textarea
              aria-label="定位描述"
              rows={2}
              value={fields.locator}
              onChange={(event) => change("locator", event.target.value)}
            />
          </Field>
          <Field
            label="原文逐字摘录"
            required
            hint="保留实际看到的原文；无法查看时如实写明，不补造原文。"
          >
            <textarea
              aria-label="原文逐字摘录"
              rows={3}
              value={fields.excerpt}
              onChange={(event) => change("excerpt", event.target.value)}
            />
          </Field>
          <label className="candidate-verification-confirm">
            <input
              type="checkbox"
              checked={confirmed}
              onChange={(event) => {
                if (disabled || lock.current) return;
                setConfirmed(event.target.checked);
                onChange?.();
              }}
            />
            我已亲自核对上述来源信息，并确认这是当前版本的核验结果
          </label>
          {error ? <Notice tone="error">{error}</Notice> : null}
          <Button
            variant="primary"
            type="submit"
            loading={busy}
            disabled={disabled || !confirmed}
          >
            保存来源核验
          </Button>
        </fieldset>
      </form>
    </section>
  );
}
