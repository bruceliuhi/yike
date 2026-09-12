import { CheckCircle, ListChecks } from "@phosphor-icons/react";
import { Badge, Button, Field, Notice } from "../../components/ui";
import {
  defaultResearchSettings,
  DEMAND_TYPES,
  researchSettingsSchema,
  type ResearchSettings as Settings,
  type UsageQuote,
} from "../../domain/researchUsage";
import "./research-settings.css";
import {dynamicLimitsValid} from '../../../shared/dynamicResearch';

export function DemandSettings({
  value,
  onChange,
}: {
  value?: Settings;
  onChange: (value: Settings) => void;
}) {
  if (!value) return null;
  return (
    <section className="form-section demand-settings">
      <h2>需求类型</h2>
      <div className="checkbox-group">
        {Object.entries(DEMAND_TYPES).map(([key, label]) => (
          <label key={key}>
            <input
              type="checkbox"
              checked={value.demandTypes.includes(
                key as keyof typeof DEMAND_TYPES,
              )}
              onChange={(event) =>
                onChange({
                  ...value,
                  demandTypes: event.target.checked
                    ? [...value.demandTypes, key as keyof typeof DEMAND_TYPES]
                    : value.demandTypes.filter((item) => item !== key),
                })
              }
            />
            {label}
          </label>
        ))}
      </div>
      <p className="field-hint">业务变化进入观察池，补充采购依据后再复核。</p>
    </section>
  );
}
export function ResearchSettingsPanel({
  value,
  onChange,
  quote,
  busy,
  error,
  onEstimate,
  onCancel,
  onPreview,
}: {
  value?: Settings;
  onChange: (value: Settings) => void;
  quote: UsageQuote | null;
  busy: boolean;
  error: string;
  onEstimate: () => void;
  onCancel: () => void;
  onPreview?: () => void;
}) {
  if (!value)
    return (
      <section className="research-settings">
        <h2>研究用量</h2>
        <p className="muted">此历史草稿尚未配置搜贝上限。</p>
        <Button onClick={() => onChange(defaultResearchSettings())}>
          配置研究用量
        </Button>
      </section>
    );
  return (
    <section className="research-settings" aria-label="研究用量">
      <div className="section-heading">
        <h2>研究用量</h2>
        <Badge tone="blue">搜贝</Badge>
      </div>
      <div className="usage-estimate">
        <span>{quote?.strategyBinding ? '资源上限估算' : '预计消耗'}</span>
        <strong>
          {quote
            ? `${quote.estimatedSoubei} 搜贝`
            : busy
              ? "正在估算"
              : "待估算"}
        </strong>
        <Button variant="ghost" onClick={busy ? onCancel : onEstimate}>
          {busy ? "取消估算" : "估算用量"}
        </Button>
      </div>
      <Field label="本次最多使用" className="usage-cap">
        <div className="soubei-input">
          <input
            type="number"
            aria-label="本次最多使用搜贝"
            min={1}
            max={1000000}
            step={1}
            placeholder="填写上限"
            value={value.maxSoubei ?? ""}
            onChange={(event) =>
              onChange({
                ...value,
                maxSoubei:
                  event.target.value === "" ? null : Number(event.target.value),
              })
            }
          />
          <span>搜贝</span>
        </div>
      </Field>
      <p className="field-hint">达到上限暂停，扩大范围需再次确认。</p>
      {value.dynamicScope&&<>
        <Field label="需求时间窗口">
          <input type="number" aria-label="需求时间窗口（天）" min={1} max={365} step={1} value={value.dynamicScope.maxAgeDays}
            onChange={event=>onChange({...value,dynamicScope:{...value.dynamicScope!,maxAgeDays:Number(event.target.value)}})}/>
        </Field>
        <p className="field-hint">近 {value.dynamicScope.maxAgeDays} 天 · {value.dynamicScope.timezone}。依据需求作者原文时间；未核实日期的内容不能冒充近期商机。</p>
        <p className="field-hint">搜索和读取共用来源上限（2–100次）；最多10次独立搜索、30分钟、最多20次模型调用（规划和判断合计）。至少预留一次判断额度，不保证固定候选数量。</p>
        {!dynamicLimitsValid(value.limits)&&<Notice tone="warning">当前上限超出自主研究能力，请调整来源、时长或模型调用次数；系统不会静默调低。</Notice>}
      </>}
      <dl className="usage-status">
        <div>
          <dt>已使用</dt>
          <dd>尚未启动</dd>
        </div>
      </dl>
      {quote && <p className="field-hint">{quote.basis}</p>}
      {error && <Notice tone="warning">{error}</Notice>}
      {!researchSettingsSchema.safeParse(value).success && (
        <Notice tone="warning">
          请选择需求类型，用量上限需为 1 至 1,000,000 的整数。
        </Notice>
      )}
      <details className="usage-advanced">
        <summary>
          高级设置 <small>来源、时长与调用上限</small>
        </summary>
        {(
          [
            ["sources", value.dynamicScope?"搜索与读取合计上限":"独立来源上限", value.dynamicScope?"次":"条"],
            ["minutes", "运行时长上限", "分钟"],
            ["modelCalls", "模型调用上限", "次"],
          ] as const
        ).map(([key, label, unit]) => (
          <Field key={key} label={label}>
            <div className="soubei-input">
              <input
                type="number"
                aria-label={label}
                min={value.dynamicScope&&key!=='minutes'?2:1}
                max={value.dynamicScope?{sources:100,minutes:30,modelCalls:20}[key]:1000000}
                step={1}
                value={value.limits[key]}
                onChange={(event) =>
                  onChange({
                    ...value,
                    limits: {
                      ...value.limits,
                      [key]: Number(event.target.value),
                    },
                  })
                }
              />
              <span>{unit}</span>
            </div>
          </Field>
        ))}
      </details>
      <div className="evidence-order">
        <h3>
          <ListChecks size={18} />
          补证顺序
        </h3>
        <ol>
          {["原文与发布时间", "需求依据与目标匹配", "联系上下文"].map(
            (label, index) => (
              <li key={label}>
                <span className="step-number">{index + 1}</span>
                {label}
              </li>
            ),
          )}
        </ol>
      </div>
      <div className="research-stops">
        <h3>停止条件</h3>
        <p className="research-stop">
          <CheckCircle size={17} />
          任一用量上限触达即停止继续研究
        </p>
      </div>
      <p className="field-hint">证据不足如实显示，搜贝用量不代表商机数量。</p>
      <dl className="usage-status">
        <div>
          <dt>计量规则</dt>
          <dd>{quote?.ruleVersion || "待服务确认"}</dd>
        </div>
      </dl>
      {onPreview && (
        <Button variant="ghost" onClick={onPreview}>
          查看启动确认内容
        </Button>
      )}
    </section>
  );
}
