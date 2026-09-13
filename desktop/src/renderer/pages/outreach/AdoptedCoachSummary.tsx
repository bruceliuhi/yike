import { useState } from "react";
import { Info, WarningCircle } from "@phosphor-icons/react";
import { Badge, Button, Modal } from "../../components/ui";
import type { CoachSuggestion } from "../../domain/shortCoach";

export function AdoptedCoachSummary({
  candidate,
}: {
  candidate: CoachSuggestion;
}) {
  const [show, setShow] = useState(false);
  return (
    <>
      <div className="coach-adopted-heading">
        <span>已采用文字的检查摘要</span>
        <Button variant="ghost" onClick={() => setShow(true)}>
          查看建议依据
        </Button>
      </div>
      <div className="coach-checks" role="region" aria-label="已采用建议检查">
        {candidate.checks.length ? (
          candidate.checks.map((check, index) => (
            <p key={index}>
              {check.status === "NEEDS_REVIEW" ? (
                <WarningCircle aria-hidden />
              ) : (
                <Info aria-hidden />
              )}
              <span>
                {check.status === "NEEDS_REVIEW" ? "待核实：" : "建议依据："}
                {check.message}
              </span>
            </p>
          ))
        ) : (
          <p>
            <Info aria-hidden />
            <span>{candidate.context.summary}</span>
          </p>
        )}
      </div>
      <p className="field-hint">对应本次采用的文字；修改后需重新生成建议。</p>
      {show && (
        <Modal
          title="已采用短句的建议依据"
          onClose={() => setShow(false)}
          footer={<Button onClick={() => setShow(false)}>返回草稿</Button>}
        >
          <Badge>已采用建议 · 保留原检查记录</Badge>
          <h3>对应文字</h3>
          <pre className="draft-preview">{candidate.content}</pre>
          <h3>引用上下文</h3>
          <p>{candidate.context.summary}</p>
          {candidate.quotes.map((quote) => (
            <blockquote className="coach-quote" key={quote.id}>
              <p>{quote.text}</p>
            </blockquote>
          ))}
          {!!candidate.materialReferences?.length && <>
            <h3>采用时的业务资料出处</h3>
            {candidate.materialReferences.map((ref,index)=><blockquote className="coach-quote" key={index}>
              <p>{ref.quote}</p><small>业务资料 {index+1}</small>
            </blockquote>)}
          </>}
          <p className="field-hint">
            这是本次建议的原文引用与检查记录，不代表此后发生了新的审核。有效至{" "}
            {new Date(candidate.expiresAt).toLocaleString("zh-CN")}。
          </p>
        </Modal>
      )}
    </>
  );
}
