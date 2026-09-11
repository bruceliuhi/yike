import { useState } from "react";
import { CheckCircle, Info, WarningCircle } from "@phosphor-icons/react";
import { useApp } from "../../app/context";
import { Badge, Button, Confirm, Modal, Notice } from "../../components/ui";
import type { ContactDraft, Opportunity } from "../../domain/models";
import { coachSourceProblem, type CoachPurpose } from "../../domain/shortCoach";
import { useShortCoach } from "./useShortCoach";
import { AdoptedCoachSummary } from "./AdoptedCoachSummary";
import "./short-coach.css";

export function ShortCoachPanel({
  row,
  draft,
  purpose,
  onApply,
}: {
  row: Opportunity;
  draft: ContactDraft;
  purpose: CoachPurpose;
  onApply: (content: string) => void;
}) {
  const { service, session } = useApp();
  const sample = row.sample === true || row.id === "sample";
  const coach = useShortCoach(row, draft, purpose, onApply);
  const [showEvidence, setShowEvidence] = useState(false);
  const [confirmGenerate, setConfirmGenerate] = useState(false);
  const problem = sample ? "" : coachSourceProblem(row);
  return (
    <section className="short-coach" aria-label="短句教练">
      <div className="section-heading">
        <h3>短句教练</h3>
        {sample ? (
          <Button variant="ghost" onClick={() => setShowEvidence(true)}>
            查看建议依据
          </Button>
        ) : (
          <Button
            variant="ghost"
            disabled={!session.authenticated || coach.busy}
            onClick={() =>
              draft.content.trim() && service.shortCoach && !service.shortCoach.preview && !problem
                ? setConfirmGenerate(true)
                : void coach.generate()
            }
          >
            {coach.candidate || coach.adopted
              ? "重新生成短句建议"
              : "生成短句建议"}
          </Button>
        )}
      </div>
      {sample ? (
        <>
          <div className="coach-checks">
            <p>
              <Info aria-hidden />
              依据当前公开原文准备资料询问
            </p>
            <p>
              <CheckCircle aria-hidden />
              评论与私信用途分别保留
            </p>
            <p>
              <WarningCircle aria-hidden />
              技术资料获取方式仍待核实
            </p>
          </div>
          <p className="field-hint">
            本区为只读样例；客户草稿支持编辑与建议预览。
          </p>
        </>
      ) : (
        <>
          {!service.shortCoach ? (
            <p className="field-hint">
              短句教练服务尚未接通，可继续编辑或使用原草稿生成。
            </p>
          ) : problem ? (
            <Notice tone="warning">{problem}</Notice>
          ) : (
            !coach.candidate &&
            !coach.adopted &&
            !coach.busy && (
              <p className="field-hint">
                引用原文，提出一个明确问题；先预览，由你决定是否替换。
              </p>
            )
          )}
          {coach.adopted && (
            <AdoptedCoachSummary
              key={coach.adopted.suggestionId}
              candidate={coach.adopted}
            />
          )}
          {coach.busy && (
            <div className="coach-wait">
              <span role="status">
                {coach.phase === "applying"
                  ? "正在核对引用，尚未替换…"
                  : "正在生成建议，仍可编辑当前草稿…"}
              </span>
              <Button onClick={coach.cancel}>停止等待</Button>
            </div>
          )}
          {coach.error && !coach.candidate && (
            <Notice tone="error">{coach.error}</Notice>
          )}
        </>
      )}
      {confirmGenerate && (
        <Confirm
          title="生成短句建议"
          confirmText="生成建议"
          onCancel={() => setConfirmGenerate(false)}
          onConfirm={() => {
            setConfirmGenerate(false);
            void coach.generate();
          }}
        >
          <p>当前人工内容完整保留。新建议先预览，不会自动覆盖或发送。</p>
        </Confirm>
      )}
      {coach.preview && coach.input && (
        <Confirm title="确认模型生成" confirmText="确认并生成" onCancel={coach.dismiss}
          onConfirm={() => void coach.confirmGenerate()}>
          <p>将把以下公开原文与当前草稿交给配置模型，生成结果先预览，不会自动保存或发送。</p>
          <p>{coach.preview.modelProvider} · {coach.preview.modelName}</p>
          <details open>
            <summary>本次发送的内容</summary>
            <h3>公开原文</h3><pre className="draft-preview">{coach.input.sourceText}</pre>
            <h3>当前草稿</h3><pre className="draft-preview">{coach.input.content || '空草稿'}</pre>
          </details>
          <p>不附带账号、收件对象、资料库或登录信息。取消不会调用模型。</p>
        </Confirm>
      )}
      {showEvidence && (
        <Modal
          title="公开样例的原文依据"
          onClose={() => setShowEvidence(false)}
          footer={
            <Button onClick={() => setShowEvidence(false)}>返回草稿</Button>
          }
        >
          <Badge tone="orange">只读公开研究样例</Badge>
          <h3>{row.title}</h3>
          <blockquote className="coach-quote">
            {row.excerpt || "暂无原始摘录"}
          </blockquote>
          <p>
            联系内容仅用于询问原文尚未明确的信息，不表示对方已同意采购或已经回复。
          </p>
        </Modal>
      )}
      {coach.candidate && (
        <Modal
          title="短句建议与当前草稿"
          onClose={coach.dismiss}
          footer={
            <>
              <Button disabled={coach.busy} onClick={coach.dismiss}>
                保留当前草稿
              </Button>
              <Button
                variant="primary"
                loading={coach.phase === "applying"}
                onClick={() => void coach.applyCandidate()}
              >
                核对并替换当前草稿
              </Button>
            </>
          }
        >
          {coach.input &&
            (coach.input.binding.draftVersion !== draft.version ||
              coach.input.content !== draft.content) && (
              <Notice tone="warning">
                生成期间你修改了草稿，人工内容仍保留。替换将使用右侧完整建议。
              </Notice>
            )}
          <div className="coach-comparison">
            <section>
              <h3>当前草稿</h3>
              <pre className="draft-preview">{draft.content || "尚无文字"}</pre>
            </section>
            <section>
              <h3>建议短句</h3>
              <pre className="draft-preview">{coach.candidate.content}</pre>
              <p className="field-hint">
                {Array.from(coach.candidate.content).length} 字
              </p>
            </section>
          </div>
          <h3>一个明确问题</h3>
          <p>{coach.candidate.question}</p>
          <h3>引用上下文</h3>
          <p>{coach.candidate.context.summary}</p>
          {coach.candidate.quotes.map((quote) => (
            <blockquote key={quote.id} className="coach-quote">
              <p>{quote.text}</p>
              <small>
                原文版本 {quote.sourceEvidenceVersion} · 位置 {quote.start}–
                {quote.end}
              </small>
            </blockquote>
          ))}
          {!!coach.candidate.checks.length && (
            <>
              <h3>建议检查</h3>
              <ul className="coach-check-list">
                {coach.candidate.checks.map((check, index) => (
                  <li key={index}>
                    <Badge
                      tone={
                        check.status === "NEEDS_REVIEW" ? "orange" : "neutral"
                      }
                    >
                      {check.status === "NEEDS_REVIEW" ? "待核实" : "建议依据"}
                    </Badge>{" "}
                    {check.message}
                  </li>
                ))}
              </ul>
            </>
          )}
          <p className="field-hint">
            应用前重新核对来源版本；替换后需保存并重新确认发送。
          </p>
          {coach.error && <Notice tone="error">{coach.error}</Notice>}
        </Modal>
      )}
    </section>
  );
}
