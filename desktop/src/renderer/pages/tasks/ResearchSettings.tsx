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
        <p className="field-hint">近 {value.dynamicScope.maxAgeDays} 天。依据需求作者原文时间；未核实日期的内容不能冒充近期商机。</p>
        {!dynamicLimitsValid(value.limits)&&<Notice tone="warning">当前设置超出可用范围，请展开高级设置调整。</Notice>}
      </>}
      {error && <Notice tone="warning">{error}</Notice>}
      {!researchSettingsSchema.safeParse(value).success && (
        <Notice tone="warning">
          请核对需求类型和用量上限；更多参数可在高级设置中调整。
        </Notice>
      )}
      <details className="usage-advanced">
        <summary>
          高级设置
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
      {onPreview && (
        <Button variant="ghost" onClick={onPreview}>
          查看启动确认内容
        </Button>
      )}
    </section>
  );
}
