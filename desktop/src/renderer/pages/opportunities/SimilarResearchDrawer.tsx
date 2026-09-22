import { useEffect, useRef, useState } from "react";
import { useApp } from "../../app/context";
import { boundedRequest } from "../../app/boundedRequest";
import { useResource, useUnsavedChanges } from "../../app/hooks";
import {
  Badge,
  Button,
  Confirm,
  Field,
  Modal,
  Notice,
  ResourceStatus,
} from "../../components/ui";
import { TermEditor } from "../../components/TermEditor";
import { PlatformLabel } from "../../components/Platform";
import {
  PLATFORMS,
  type Opportunity,
  type PlatformId,
  type Profile,
  type Term,
} from "../../domain/models";
import {
  hasResearchScope,
  parseSimilarResearch,
  researchBinding,
  researchQuoteMatches,
  researchQuoteLabel,
  sameResearchBinding,
  type SimilarDraftHandoff,
  type SimilarResearchPlan,
  type ResearchBinding,
} from "../../domain/opportunityResearch";
import { errorMessage } from "../../services/contracts";
import { readResearchRecord } from "../../services/opportunityResearch";
import { defaultResearchSettings } from "../../domain/researchUsage";
import { similarResearchDefaultPlatforms } from "../../domain/similarResearchDefaults";
import { isSample } from "./OpportunityEvidence";
import "./research.css";

export function SimilarResearchDrawer({
  opportunity: row,
  onClose,
  onCreateDraft,
}: {
  opportunity: Opportunity;
  onClose: () => void;
  onCreateDraft?: SimilarDraftHandoff;
}) {
  const { service, session } = useApp();
  const sample = isSample(row);
  const binding = researchBinding(
    row,
    session.authenticated ? session.userId : undefined,
    session.accountScope,
  );
  const [requestId] = useState(() => crypto.randomUUID());
  const resource = useResource(async () => {
    if (
      sample ||
      !binding ||
      !service.opportunityResearch ||
      row.sourceStatus !== "OPEN" ||
      row.profileStatus !== "CONFIRMED"
    )
      return null;
    const [raw, profiles] = await boundedRequest(
      (signal) =>
        Promise.all([
          service.opportunityResearch!.similar(binding, requestId, signal),
          service.profiles(),
        ]),
      { timeoutMessage: "相似研究建议读取超时，请重试。" },
    );
    const plan = parseSimilarResearch(raw, binding, requestId);
    if (plan.evidence.some((q) => !researchQuoteMatches(row,q)))
      throw new Error("建议引用与当前原文不匹配，请刷新机会证据。");
    const profile = profiles.find(
      (p) =>
        p.id === plan.profileId &&
        p.version === plan.profileVersion &&
        p.status === "CONFIRMED",
    );
    if (!profile)
      throw new Error("建议绑定的画像版本已不可用，请重新确认画像。");
    return { plan, profile };
  }, [
    service,
    JSON.stringify(binding),
    row.sourceStatus,
    row.profileStatus,
    requestId,
    sample,
  ]);
  if (sample) return <SampleSimilarPreview onClose={onClose} />;
  if (resource.data && binding)
    return (
      <SimilarForm
        key={`${requestId}:${resource.data.plan.suggestionId}`}
        row={row}
        binding={binding}
        {...resource.data}
        onClose={onClose}
        onCreateDraft={onCreateDraft}
      />
    );
  const unavailable = !service.opportunityResearch
    ? "多找类似的研究建议服务尚未接通。当前机会仍可查看、准备联系或添加跟进。"
    : !hasResearchScope(session.accountScope)
      ? "当前账户空间尚未核验，研究建议暂不可用。"
      : !binding ||
          row.sourceStatus !== "OPEN" ||
          row.profileStatus !== "CONFIRMED"
        ? "仅来源有效、画像已确认且经认可的客户机会可发起扩展。"
        : "";
  return (
    <Modal
      title="多找类似"
      drawer
      onClose={onClose}
      footer={
        <>
          <Button onClick={onClose}>取消</Button>
          <Button variant="primary" disabled>
            创建任务草稿
          </Button>
        </>
      }
    >
      <Badge tone="orange">配置预览 · 不会立即执行</Badge>
      {unavailable ? (
        <Notice tone="warning">{unavailable}</Notice>
      ) : (
        <ResourceStatus
          loading={resource.loading}
          error={resource.error}
          onRetry={resource.reload}
        />
      )}
    </Modal>
  );
}
function SimilarForm({
  row,
  binding,
  plan,
  profile,
  onClose,
  onCreateDraft,
}: {
  row: Opportunity;
  binding: ResearchBinding;
  plan: SimilarResearchPlan;
  profile: Profile;
  onClose: () => void;
  onCreateDraft?: SimilarDraftHandoff;
}) {
  const { service, session } = useApp();
  const makeTerms = (values: string[]): Term[] =>
    values.map((value, i) => ({
      id: `similar-${i}`,
      value,
      origin: "ai",
      edited: false,
    }));
  const [terms, setTerms] = useState(() => makeTerms(plan.keywords));
  const [exclusions, setExclusions] = useState(() =>
    makeTerms(plan.exclusions),
  );
  const [defaultPlatforms] = useState(() =>
    similarResearchDefaultPlatforms(row.platform, plan.supportedPlatforms),
  );
  const [platforms, setPlatforms] = useState<PlatformId[]>(defaultPlatforms);
  const [name, setName] = useState(`${row.title.slice(0, 50)} · 相似研究`);
  const [sources, setSources] = useState("30");
  const [minutes, setMinutes] = useState("10");
  const [soubei, setSoubei] = useState(() =>
    String(defaultResearchSettings().maxSoubei ?? ""),
  );
  const [dirty, setDirty] = useState(false);
  const [confirmClose, setConfirmClose] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [draftId] = useState(() => crypto.randomUUID());
  const [handoffId] = useState(() => crypto.randomUUID());
  const request = useRef<AbortController | null>(null);
  const alive = useRef(true);
  const current = useRef({
    binding,
    userId: session.userId,
    authenticated: session.authenticated,
  });
  current.current = {
    binding,
    userId: session.userId,
    authenticated: session.authenticated,
  };
  const editVersion = useRef(0);
  const touch = () => {
    editVersion.current++;
    setDirty(true);
  };
  useUnsavedChanges(dirty);
  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
      request.current?.abort();
    };
  }, []);
  const close = () => {
    if (busy) return;
    if (dirty) setConfirmClose(true);
    else onClose();
  };
  const validLimits =
    Number.isSafeInteger(Number(sources)) &&
    Number(sources) > 0 &&
    Number(sources) <= 10000 &&
    Number.isSafeInteger(Number(minutes)) &&
    Number(minutes) > 0 &&
    Number(minutes) <= 1440 &&
    (!soubei ||
      (Number.isSafeInteger(Number(soubei)) &&
        Number(soubei) > 0 &&
        Number(soubei) <= 1000000));
  const eligible =
    plan.eligible &&
    row.sourceStatus === "OPEN" &&
    row.profileStatus === "CONFIRMED" &&
    session.authenticated &&
    session.userId === binding.userId;
  const canCreate =
    eligible &&
    Boolean(onCreateDraft) &&
    !busy &&
    name.trim().length > 0 &&
    name.trim().length <= 80 &&
    terms.length > 0 &&
    terms.every((t) => t.value.length <= 80) &&
    exclusions.every((t) => t.value.length <= 80) &&
    platforms.length > 0 &&
    validLimits;
  const create = async () => {
    if (
      !canCreate ||
      request.current ||
      !service.opportunityResearch ||
      !onCreateDraft
    )
      return;
    const abort = new AbortController();
    request.current = abort;
    setBusy(true);
    setError("");
    const editing = editVersion.current;
    const unchanged = () =>
      alive.current &&
      !abort.signal.aborted &&
      current.current.authenticated &&
      current.current.userId === binding.userId &&
      sameResearchBinding(current.current.binding, binding);
    try {
      const [freshRecord, profiles, raw] = await boundedRequest(
        (signal) =>
          Promise.all([
            readResearchRecord(
              service.opportunityResearch!,
              session,
              row.id,
              signal,
            ),
            service.profiles(),
            service.opportunityResearch!.similar(
              binding,
              plan.requestId,
              signal,
            ),
          ]),
        {
          signal: abort.signal,
          timeoutMessage: "创建草稿前核验超时；尚未创建，请重试。",
        },
      );
      if (!unchanged()) return;
      const freshRow = freshRecord.opportunity;
      const freshBinding = researchBinding(
        freshRow,
        binding.userId,
        binding.accountScope,
      );
      if (
        !freshBinding ||
        !sameResearchBinding(freshBinding, binding) ||
        freshRow.sourceStatus !== "OPEN" ||
        freshRow.profileStatus !== "CONFIRMED" ||
        !profiles.some(
          (p) =>
            p.id === plan.profileId &&
            p.version === plan.profileVersion &&
            p.status === "CONFIRMED",
        )
      )
        throw new Error("来源或画像已变化，未创建草稿。请刷新机会后重试。");
      const freshPlan = parseSimilarResearch(raw, binding, plan.requestId);
      const semanticPlan = (value: SimilarResearchPlan) =>
        JSON.stringify({
          suggestionId: value.suggestionId,
          recognition: value.recognition,
          profileId: value.profileId,
          profileVersion: value.profileVersion,
          evidence: value.evidence,
          rationale: value.rationale,
          keywords: value.keywords,
          exclusions: value.exclusions,
          supportedPlatforms: value.supportedPlatforms,
          originalScope: value.originalScope,
          additionalScope: value.additionalScope,
        });
      if (
        !freshPlan.eligible ||
        freshRecord.classification.category !== "OPPORTUNITY" ||
        freshRecord.classification.review.status !== "RECOGNIZED" ||
        freshRecord.classification.review.reviewer !==
          freshPlan.recognition?.reviewer ||
        freshRecord.classification.review.reviewedAt !==
          freshPlan.recognition?.reviewedAt ||
        freshPlan.evidence.some((q) => !researchQuoteMatches(freshRow,q)) ||
        semanticPlan(freshPlan) !== semanticPlan(plan) ||
        platforms.some((p) => !freshPlan.supportedPlatforms.includes(p))
      )
        throw new Error("认可记录或建议已变化，未创建草稿。请重新打开建议。");
      if (editing !== editVersion.current)
        throw new Error("核验期间配置已修改，请确认当前配置后再创建。");
      onCreateDraft({
        requestId: handoffId,
        draftId,
        binding,
        suggestionId: plan.suggestionId,
        name: name.trim(),
        profileId: plan.profileId,
        profileVersion: plan.profileVersion,
        keywords: terms.map((t) => t.value),
        exclusions: exclusions.map((t) => t.value),
        platforms: [...platforms],
        originalScope: plan.originalScope,
        additionalScope: plan.additionalScope,
        limits: {
          sources: Number(sources),
          minutes: Number(minutes),
          soubei: soubei ? Number(soubei) : null,
          stopAtAnyLimit: true,
        },
        usage: dirty
          ? {
              status: "UNKNOWN",
              reason: "配置已编辑，需在最终确认前重新计量。",
            }
          : plan.usage,
      });
      setDirty(false);
    } catch (e) {
      if (unchanged()) setError(errorMessage(e));
    } finally {
      request.current = null;
      if (alive.current) setBusy(false);
    }
  };
  return (
    <>
      <Modal
        title="多找类似"
        drawer
        onClose={close}
        footer={
          <>
            <Button disabled={busy} onClick={close}>
              取消
            </Button>
            <Button
              variant="primary"
              disabled={!canCreate}
              loading={busy}
              onClick={() => void create()}
            >
              创建任务草稿
            </Button>
          </>
        }
      >
        <div className="similar-research-fields">
          <Badge tone="orange">配置预览 · 不会立即执行</Badge>
          <Field label="相似依据">
            <p>{plan.rationale}</p>
            <details className="similar-source-evidence">
              <summary>查看依据原文 · {plan.evidence.length} 处</summary>
              {plan.evidence.map((q, i) => (
                <blockquote key={i} className="evidence-quote">
                  {q.field && <div className="muted text-small">{researchQuoteLabel(q)}</div>}
                  {q.quote}
                </blockquote>
              ))}
            </details>
          </Field>
          <Field label="目标画像">
            <input
              aria-label="目标画像"
              value={profile.description || profile.fields.service}
              readOnly
            />
            <small className="muted">
              已确认版本 v{profile.version}；修改画像需重新取得建议。
            </small>
          </Field>
          <Field label="新任务名称" required>
            <input
              aria-label="新任务名称"
              maxLength={80}
              value={name}
              onChange={(e) => {
                setName(e.target.value);
                touch();
              }}
            />
          </Field>
          <Field label="建议新增搜索词">
            <TermEditor
              label="新增搜索词"
              terms={terms}
              onChange={(value) => {
                setTerms(value);
                touch();
              }}
              onRemove={(id) => {
                setTerms((old) => old.filter((t) => t.id !== id));
                touch();
              }}
            />
          </Field>
          <Field label="排除词">
            <TermEditor
              label="排除词"
              terms={exclusions}
              neutral
              onChange={(value) => {
                setExclusions(value);
                touch();
              }}
              onRemove={(id) => {
                setExclusions((old) => old.filter((t) => t.id !== id));
                touch();
              }}
            />
          </Field>
          <Field label="搜索平台" required>
            <div className="similar-platforms">
              {PLATFORMS.filter((p) =>
                plan.supportedPlatforms.includes(p.id),
              ).map((p) => (
                <label key={p.id}>
                  <input
                    type="checkbox"
                    aria-label={p.name}
                    checked={platforms.includes(p.id)}
                    onChange={(e) => {
                      setPlatforms((old) =>
                        e.target.checked
                          ? [...old, p.id]
                          : old.filter((id) => id !== p.id),
                      );
                      touch();
                    }}
                  />
                  <PlatformLabel platform={p.id} />
                </label>
              ))}
            </div>
            <small className="muted">
              {defaultPlatforms.length
                ? "仅预选当前机会来源，可修改；不继承原任务全部平台。"
                : "当前机会来源未匹配服务支持的平台，请手动选择本次搜索平台。"}
              账号与采集能力在任务确认前检查。
            </small>
          </Field>
          <Field label="范围变化">
            <dl className="detail-list">
              <div>
                <dt>原范围</dt>
                <dd>{plan.originalScope}</dd>
              </div>
              <div>
                <dt>建议增量</dt>
                <dd>{plan.additionalScope}</dd>
              </div>
              <div>
                <dt>本次新草稿</dt>
                <dd>
                  {terms.length} 个搜索词，{platforms.length}{" "}
                  个平台；不修改原任务。
                </dd>
              </div>
            </dl>
          </Field>
          <Field label="单次搜贝上限">
            <input
              aria-label="单次搜贝上限"
              type="number"
              min={1}
              max={1000000}
              placeholder="待设置"
              value={soubei}
              onChange={(e) => {
                setSoubei(e.target.value);
                touch();
              }}
            />
            <small className="muted">
              可先保存草稿；计量或硬上限未确认时不能启动收费研究。
            </small>
          </Field>
          <div className="similar-usage">
            <strong>预计搜贝用量</strong>
            <p>
              {dirty
                ? "暂不可计量 · 配置已编辑"
                : plan.usage.status === "UNKNOWN"
                  ? `暂不可计量 · ${plan.usage.reason}`
                  : `${plan.usage.amount} 搜贝 · ${plan.usage.status === "ESTIMATED" ? "估算" : "已计量记录，非本次预测"}`}
            </p>
            {!dirty && plan.usage.status !== "UNKNOWN" && (
              <small>{plan.usage.basis}</small>
            )}
          </div>
          <details>
            <summary>高级资源上限</summary>
            <div className="similar-limits">
              <Field label="独立来源上限">
                <input
                  aria-label="独立来源上限"
                  type="number"
                  min={1}
                  max={10000}
                  value={sources}
                  onChange={(e) => {
                    setSources(e.target.value);
                    touch();
                  }}
                />
              </Field>
              <Field label="研究时长上限（分钟）">
                <input
                  aria-label="研究时长上限"
                  type="number"
                  min={1}
                  max={1440}
                  value={minutes}
                  onChange={(e) => {
                    setMinutes(e.target.value);
                    touch();
                  }}
                />
              </Field>
            </div>
            <p>任一上限到达即停止；执行端必须支持硬上限。</p>
          </details>
          {!validLimits && (
            <Notice tone="warning">上限需填写范围内的正整数。</Notice>
          )}
          {!plan.eligible && (
            <Notice tone="warning">
              {plan.ineligibleReason || "当前机会尚未达到已认可条件。"}
            </Notice>
          )}
          {!onCreateDraft && (
            <Notice>本机任务草稿接入尚未完成，暂不能创建。</Notice>
          )}
          {error && <Notice tone="error">{error}</Notice>}
          <p className="muted">
            创建后仍需连接平台并最终确认，不会立即采集、联系或扣除搜贝。
          </p>
        </div>
      </Modal>
      {confirmClose && (
        <Confirm
          title="放弃本次相似研究配置？"
          onCancel={() => setConfirmClose(false)}
          onConfirm={onClose}
          confirmText="放弃更改"
        >
          <p>本次修改尚未创建为任务草稿，原任务保持不变。</p>
        </Confirm>
      )}
    </>
  );
}
function SampleSimilarPreview({ onClose }: { onClose: () => void }) {
  return (
    <Modal
      title="多找类似"
      drawer
      onClose={onClose}
      footer={
        <>
          <Button onClick={onClose}>取消</Button>
          <Button variant="primary" disabled>
            创建任务草稿
          </Button>
        </>
      }
    >
      <div className="similar-research-fields">
        <Badge tone="orange">公开样例 · 配置预览</Badge>
        <Field label="相似依据">
          <p>展区设计搭建 / 公开预算询价</p>
        </Field>
        <Field label="目标画像" required>
          <select aria-label="目标画像" disabled>
            <option>选择已确认画像</option>
          </select>
        </Field>
        <Field label="新增搜索方向（样例）">
          <p>展区搭建预算询价 · 会展设计服务范围 · 展台技术资料</p>
        </Field>
        <Field label="搜索平台">
          <div className="similar-platforms">
            {["xhs", "douyin", "web"].map((p) => (
              <label key={p}>
                <input type="checkbox" disabled />
                <PlatformLabel platform={p} />
              </label>
            ))}
          </div>
        </Field>
        <Field label="预计搜贝用量">
          <p>暂不可计量</p>
        </Field>
        <Notice>
          仅已认可的真实客户机会可创建新任务草稿；公开样例只用于查看，不会入库或执行。
        </Notice>
      </div>
    </Modal>
  );
}
