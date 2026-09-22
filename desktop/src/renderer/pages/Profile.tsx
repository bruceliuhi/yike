import { useEffect, useLayoutEffect, useRef, useState, type ChangeEvent } from "react";
import { Plus, UploadSimple } from "@phosphor-icons/react";
import { useApp } from "../app/context";
import {
  useAction,
  useLocalDraft,
  useResource,
  useUnsavedChanges,
} from "../app/hooks";
import {
  Badge,
  Button,
  Confirm,
  Drawer,
  Empty,
  Field,
  Modal,
  Notice,
  PageHeader,
  ResourceStatus,
  Tabs,
} from "../components/ui";
import {
  EMPTY_PROFILE,
  newTaskDraft,
  type Profile,
  type ProfileFields,
  type TaskDraft,
} from "../domain/models";
import { boundedRequest } from "../app/boundedRequest";
import { MaterialsWorkspace } from "./profile/MaterialsWorkspace";
import { LocalMaterialDrafts, type LocalMaterialDraft as Material } from "./profile/LocalMaterialDrafts";
import { taskDraftOwner, useTaskDraft, useTaskLibrary } from "../app/taskDraft";
import { defaultResearchSettings } from "../domain/researchUsage";
import {adoptedBindings,bindingOptions,savedBindings,type ReferenceBindings} from './profile/profileReferenceBindings';

interface ProfileEditor {
  profileEntityId?: string;
  newBusiness?: {requestId:string;name:string};
  referenceBindings?: ReferenceBindings;
  baselineReferenceBindings?: ReferenceBindings;
  fields: ProfileFields;
  baseline: ProfileFields;
  versionId: string | null;
  example: boolean;
}
function validMaterials(value: unknown): value is Material[] {
  return (
    Array.isArray(value) &&
    value.length <= 500 &&
    new Set(value.map((item) => item?.id)).size === value.length &&
    value.every((item) => {
      if (!item || typeof item !== "object" || Array.isArray(item))
        return false;
      const entry = item as Record<string, unknown>;
      return (
        Object.keys(entry).every((key) =>
          [
            "id",
            "name",
            "text",
            "purpose",
            "visibility",
            "updatedAt",
            "fileName",
            "bytes",
          ].includes(key),
        ) &&
        typeof entry.id === "string" &&
        /^[\w-]{1,128}$/.test(entry.id) &&
        typeof entry.name === "string" &&
        !!entry.name.trim() &&
        entry.name.length <= 100 &&
        typeof entry.text === "string" &&
        !!entry.text.trim() &&
        entry.text.length <= 2000 &&
        typeof entry.purpose === "string" &&
        ["产品介绍", "真实案例", "服务说明"].includes(entry.purpose) &&
        (entry.visibility === "internal" || entry.visibility === "external") &&
        typeof entry.updatedAt === "string" &&
        entry.updatedAt.length <= 40 &&
        Number.isFinite(Date.parse(entry.updatedAt)) &&
        (entry.fileName === undefined ||
          (typeof entry.fileName === "string" &&
            entry.fileName.length <= 255)) &&
        (entry.bytes === undefined ||
          (typeof entry.bytes === "number" &&
            Number.isInteger(entry.bytes) &&
            entry.bytes >= 0 &&
            entry.bytes <= 200 * 1024))
      );
    })
  );
}
const labels: Record<keyof ProfileFields, string> = {
  service: "服务内容",
  customer: "目标客户",
  regions: "服务地区",
  preference: "项目偏好",
  exclusions: "排除项",
};
const example: ProfileFields = {
  service: "展台设计与搭建",
  customer: "有参展或展区建设需求的企业与机构",
  regions: "",
  preference: "",
  exclusions: "同行推广、招聘、课程培训",
};
const emptyMaterial = () => ({
  name: "",
  text: "",
  purpose: "产品介绍",
  visibility: "internal" as "internal" | "external",
  fileName: "",
  bytes: 0,
});
const statusLabel = (status?: string) =>
  status === "CONFIRMED"
    ? "已确认"
    : status === "REVOKED"
      ? "历史版本"
      : "草稿";

function hasTaskDraftContent(draft: TaskDraft) {
  const empty = { ...newTaskDraft(), research: defaultResearchSettings() };
  return Object.entries(draft).some(([key, value]) =>
    key !== "id" && JSON.stringify(value) !== JSON.stringify(empty[key as keyof TaskDraft]),
  );
}

export function ProfilePage() {
  const { session } = useApp();
  return <ProfileWorkspace key={JSON.stringify([session.authenticated, taskDraftOwner(session.userId, session.accountScope)])} />;
}

function ProfileWorkspace() {
  const { service, session, route, navigate, notify } = useApp();
  const alive = useRef(true);
  const activeService = useRef(service);
  activeService.current = service;
  const currentScope = () => alive.current && activeService.current === service;
  useLayoutEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);
  const tab =
    route.query.get("tab") === "materials" ? "materials" : "description";
  const profiles = useResource(
    () =>
      boundedRequest(() => service.profiles(), {
        timeoutMessage: "画像加载超时，请重试。",
      }),
    [service, session.authenticated, session.userId, session.accountScope?.id, session.accountScope?.version],
  );
  const action = useAction();
  const [editor, setEditor] = useLocalDraft<ProfileEditor>(
    "profile." + taskDraftOwner(session.userId, session.accountScope),
    () => ({
      fields: { ...EMPTY_PROFILE },
      baseline: { ...EMPTY_PROFILE },
      versionId: null,
      example: false,
    }),
  );
  const [materials, setMaterials] = useLocalDraft<Material[]>(
    "materials." + taskDraftOwner(session.userId, session.accountScope),
    [],
    validMaterials,
  );
  const [fieldErrors, setFieldErrors] = useState<
    Partial<Record<keyof ProfileFields, string>>
  >({});
  const [confirming, setConfirming] = useState<Profile | null>(null);
  const [taskDraft, setTaskDraft] = useTaskDraft(session.userId, "once", session.accountScope);
  const [taskLibrary, setTaskLibrary] = useTaskLibrary(session.userId, session.accountScope);
  const [researchChoice, setResearchChoice] = useState(false);
  const [verified, setVerified] = useState(false);
  const [leaving, setLeaving] = useState<{
    path?: string;
    profile?: Profile;
    newBusiness?: boolean;
  } | null>(null);
  const [materialOpen, setMaterialOpen] = useState(false);
  const [material, setMaterial] = useState(emptyMaterial);
  const [materialMode, setMaterialMode] = useState("text");
  const [materialId, setMaterialId] = useState<string | null>(null);
  const [materialError, setMaterialError] = useState("");
  const [reading, setReading] = useState(false);
  const readGeneration = useRef(0);
  const [discardMaterial, setDiscardMaterial] = useState(false);
  const [deleteMaterial, setDeleteMaterial] = useState<Material | null>(null);
  const [materialBaseline, setMaterialBaseline] = useState(
    JSON.stringify(emptyMaterial()),
  );
  const dirty =
    !!editor.newBusiness ||
    JSON.stringify(editor.fields) !== JSON.stringify(editor.baseline) ||
    JSON.stringify(editor.referenceBindings??{}) !== JSON.stringify(editor.baselineReferenceBindings??{});
  const materialDirty =
    materialOpen && JSON.stringify(material) !== materialBaseline;
  useUnsavedChanges(dirty || materialDirty);
  const current = profiles.data?.find((p) => p.id === editor.versionId);
  const researchReady = session.authenticated && !!session.userId && !dirty && current?.status === "CONFIRMED";
  const newerTaskDraft = taskLibrary.some((draft) => draft.id === taskDraft.id && draft.revision > taskDraft.revision);
  const createResearch = () => {
    if (!researchReady || !currentScope() || !current || newerTaskDraft) return;
    if (hasTaskDraftContent(taskDraft)) {
      setTaskLibrary((old) => [taskDraft, ...old.filter((draft) => draft.id !== taskDraft.id)]);
    }
    setTaskDraft({
      ...newTaskDraft(),
      profileId: current.id,
      profileVersion: current.version,
      research: defaultResearchSettings(),
    });
    setResearchChoice(false);
    navigate("/tasks/new");
  };
  const activeEditor = useRef(editor);
  activeEditor.current = editor;
  const applyProfile = (profile: Profile) => {
    setEditor({
      profileEntityId:profile.profileEntityId,
      fields: { ...profile.fields },
      baseline: { ...profile.fields },
      versionId: profile.id,
      example: false,
      referenceBindings: savedBindings(profile),
      baselineReferenceBindings: savedBindings(profile),
    });
    setFieldErrors({});
    action.setError("");
  };
  const startBusiness = () => {
    setEditor({fields:{...EMPTY_PROFILE},baseline:{...EMPTY_PROFILE},versionId:null,example:false,
      newBusiness:{requestId:crypto.randomUUID(),name:''},referenceBindings:{},baselineReferenceBindings:{}});
    setFieldErrors({});action.setError('');
  };
  useEffect(() => {
    if (
      profiles.data?.length &&
      !editor.versionId &&
      !editor.newBusiness &&
      !Object.values(editor.fields).some(Boolean)
    )
      applyProfile(profiles.data[0]);
  }, [profiles.data]);
  useEffect(
    () => () => {
      readGeneration.current++;
    },
    [],
  );
  const go = (path: string) => navigate(path);
  const changeField = (key: keyof ProfileFields, value: string) => {
    if(editor.referenceBindings?.[key]&&value!==editor.fields[key])notify(`${labels[key]}已改为人工内容，不再继承原资料引用。`, 'info');
    setEditor((old) => {
      const bindings={...old.referenceBindings};
      if(value!==old.fields[key])delete bindings[key];
      return {...old,fields:{...old.fields,[key]:value},referenceBindings:bindings};
    });
    setFieldErrors((old) => ({ ...old, [key]: undefined }));
  };
  const validate = () => {
    const errors: Partial<Record<keyof ProfileFields, string>> = {};
    for (const key of ["service", "customer", "regions"] as const)
      if (!editor.fields[key].trim()) errors[key] = `请填写${labels[key]}。`;
    setFieldErrors(errors);
    return !Object.keys(errors).length;
  };
  const save = async (forConfirmation = false) => {
    if (!validate()) return;
    if(editor.newBusiness&&!editor.newBusiness.name.trim()){
      action.setError('请填写业务名称。');return;
    }
    if(editor.versionId&&!editor.profileEntityId&&!current){
      action.setError('请先重新读取当前画像，再保存修改。');return;
    }
    if(Object.values(editor.referenceBindings??{}).some(binding=>!binding?.valid)){
      action.setError('资料引用已失效，请重新采用有效资料或改为人工内容后保存。');return;
    }
    const snapshot = { ...editor.fields };
    const referenceSnapshot=JSON.stringify(editor.referenceBindings??{});
    const references=bindingOptions(editor.referenceBindings??{},editor.versionId)??
      (Object.keys(editor.baselineReferenceBindings??{}).length&&editor.versionId?
        {baseProfileVersionId:editor.versionId,materialReferences:[]}:undefined);
    const originalVersion = editor.versionId;
    const businessSnapshot=JSON.stringify([editor.profileEntityId,editor.newBusiness]);
    const entity=editor.profileEntityId??current?.profileEntityId;
    const options={...references,...(editor.newBusiness?{newBusiness:editor.newBusiness}:entity?{profileEntityId:entity}:{})};
    const saved = await action.run(() =>
      boundedRequest(() => Object.keys(options).length?service.saveProfile(snapshot,options):service.saveProfile(snapshot), {
        timeoutMessage:
          "画像保存等待超时，尚未确认保存结果；输入保留，请刷新核对版本。",
      }),
    );
    if (
      !saved ||
      !currentScope() ||
      activeEditor.current.versionId !== originalVersion ||
      JSON.stringify([activeEditor.current.profileEntityId,activeEditor.current.newBusiness])!==businessSnapshot ||
      JSON.stringify(activeEditor.current.referenceBindings??{})!==referenceSnapshot ||
      JSON.stringify(activeEditor.current.fields) !== JSON.stringify(snapshot)
    )
      return;
    setEditor((old) => ({
      ...old,
      fields: { ...saved.fields },
      baseline: { ...saved.fields },
      versionId: saved.id,
      profileEntityId:saved.profileEntityId,
      newBusiness:undefined,
      referenceBindings: savedBindings(saved),
      baselineReferenceBindings: savedBindings(saved),
    }));
    profiles.setData((old) => [
      saved,
      ...(old || []).filter((p) => p.id !== saved.id),
    ]);
    if (forConfirmation) {
      setVerified(false);
      setConfirming(saved);
    } else
      notify(
        saved.status === "CONFIRMED"
          ? "该内容已是已确认版本。"
          : "画像草稿已保存。",
        "success",
      );
  };
  const requestConfirm = () => {
    if (!validate()) return;
    if(Object.values(editor.referenceBindings??{}).some(binding=>!binding?.valid)){
      action.setError('资料引用已失效，请重新采用有效资料或改为人工内容后保存。');return;
    }
    if (!dirty && current) {
      setVerified(false);
      setConfirming(current);
    } else void save(true);
  };
  const confirm = async () => {
    if (!confirming || !verified) return;
    const result = await action.run(() =>
      boundedRequest(() => service.confirmProfile(confirming.id), {
        timeoutMessage:
          "画像确认等待超时，尚未确认结果；请刷新核对原画像版本。",
      }),
    );
    if (!result || !currentScope()) return;
    if (result.id !== confirming.id || result.status !== "CONFIRMED") {
      action.setError("画像状态已发生变化，请取消并刷新后核对。");
      await profiles.reload();
      return;
    }
    applyProfile(result);
    setConfirming(null);
    await profiles.reload();
    notify("画像已确认，可继续配置获客任务。", "success");
  };
  const openMaterial = (entry?: Material) => {
    readGeneration.current++;
    const value = entry
      ? {
          name: entry.name,
          text: entry.text,
          purpose: entry.purpose,
          visibility: entry.visibility,
          fileName: entry.fileName || "",
          bytes: entry.bytes || 0,
        }
      : emptyMaterial();
    setMaterial(value);
    setMaterialBaseline(JSON.stringify(value));
    setMaterialId(entry?.id || null);
    setMaterialMode("text");
    setMaterialError("");
    setReading(false);
    setMaterialOpen(true);
  };
  const closeMaterial = () => {
    if (materialDirty || reading) {
      setDiscardMaterial(true);
      return;
    }
    readGeneration.current++;
    setMaterialOpen(false);
  };
  const readFile = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;
    const generation = ++readGeneration.current;
    setMaterialError("");
    setReading(false);
    if (!/\.(txt|md)$/i.test(file.name) || file.size > 200 * 1024) {
      setMaterialError("请选择不超过 200 KB 的 TXT 或 Markdown 文件。");
      event.target.value = "";
      return;
    }
    setReading(true);
    try {
      const text = await boundedRequest(() => file.text(), {
        timeoutMessage: "文件读取超时，请重新选择或粘贴文字。",
      });
      if (generation !== readGeneration.current) return;
      if (!text.trim() || text.length > 2000 || text.includes("\u0000")) {
        setMaterialError("文件内容须为有效文字，且不超过 2000 字。");
        return;
      }
      setMaterial((old) => ({
        ...old,
        text,
        fileName: file.name,
        bytes: file.size,
        name: old.name || file.name.replace(/\.(txt|md)$/i, ""),
      }));
    } catch (error) {
      if (generation === readGeneration.current)
        setMaterialError(
          error instanceof Error
            ? error.message
            : "文件读取失败，请重试或粘贴文字。",
        );
    } finally {
      if (generation === readGeneration.current) setReading(false);
      event.target.value = "";
    }
  };
  const saveMaterial = () => {
    if (!materialId && materials.length >= 500) {
      setMaterialError("本机最多保存 500 份资料草稿，请先清理不再使用的草稿。");
      return;
    }
    if (!material.name.trim() || !material.text.trim()) {
      setMaterialError("请填写资料名称和内容。");
      return;
    }
    if (material.name.length > 100 || material.text.length > 2000) {
      setMaterialError("资料名称最多 100 字，内容最多 2000 字。");
      return;
    }
    const entry: Material = {
      ...material,
      id: materialId || crypto.randomUUID(),
      name: material.name.trim(),
      updatedAt: new Date().toISOString(),
    };
    setMaterials((old) => [entry, ...old.filter((m) => m.id !== entry.id)]);
    readGeneration.current++;
    setMaterialOpen(false);
    notify("已保存本机资料草稿，尚未同步到客户服务。", "success");
  };
  return (
    <>
      <PageHeader
        title={tab === "materials" ? "业务资料" : "业务画像"}
        description={
          tab === "materials" ? "管理产品介绍与真实案例。" : undefined
        }
      />
      <Tabs
        items={[
          { key: "description", label: "业务描述" },
          { key: "materials", label: "资料与案例" },
        ]}
        active={tab}
        onChange={(key) =>
          go(key === "materials" ? "/profile?tab=materials" : "/profile")
        }
      />
      {tab === "description" ? (
        <>
          <ResourceStatus
            loading={profiles.loading}
            error={profiles.error}
            onRetry={() => void profiles.reload()}
          />
          <section className="profile-section">
            <div className="section-heading">
              <h2>业务描述</h2>
              <div className="inline-actions">
                <Button variant="ghost" disabled={action.busy||profiles.loading} onClick={()=>dirty?setLeaving({newBusiness:true}):startBusiness()}>
                  新建业务画像
                </Button>
                {editor.example && <Badge tone="blue">填写示例 · 未确认</Badge>}
                <Badge
                  tone={
                    !dirty && current?.status === "CONFIRMED"
                      ? "green"
                      : "neutral"
                  }
                >
                  {dirty ? "未保存修改" : statusLabel(current?.status)}
                </Badge>
                <Button
                  variant="ghost"
                  disabled={action.busy || profiles.loading}
                  onClick={() => {
                    setEditor((old) => ({
                      ...old,
                      fields: { ...example },
                      example: true,
                      referenceBindings: {},
                    }));
                    setFieldErrors({});
                  }}
                >
                  使用填写示例
                </Button>
              </div>
            </div>
            {profiles.data && profiles.data.length > 0 && (
              <Field label="画像版本">
                <select
                  aria-label="画像版本"
                  value={editor.versionId || ""}
                  disabled={action.busy}
                  onChange={(e) => {
                    const selected = profiles.data?.find(
                      (p) => p.id === e.target.value,
                    );
                    if (selected) {
                      if (dirty) setLeaving({ profile: selected });
                      else applyProfile(selected);
                    }
                  }}
                >
                  {!editor.versionId && <option value="">本机新草稿</option>}
                  {profiles.data.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.businessName||p.fields.service||'业务画像'} · 版本 {p.version} · {statusLabel(p.status)}
                    </option>
                  ))}
                </select>
              </Field>
            )}
            {editor.newBusiness&&<Field label="业务名称" required>
              <input aria-label="业务名称" maxLength={100} disabled={action.busy}
                placeholder="例如：制造业软件、教育业务"
                value={editor.newBusiness.name} onChange={event=>setEditor(old=>({...old,newBusiness:old.newBusiness?{...old.newBusiness,name:event.target.value}:undefined}))}/>
            </Field>}
            {current?.status === "CONFIRMED" && (
              <Notice>
                修改后需保存并重新确认；已有任务仍保留原画像版本。
              </Notice>
            )}
            {current?.status === "REVOKED" && (
              <Notice tone="warning">
                这是历史画像版本。修改内容并保存后，可确认新的版本。
              </Notice>
            )}
            <fieldset
              className="profile-fieldset"
              disabled={action.busy || profiles.loading}
            >
              <div className="profile-grid">
                <div>
                  <Field label="服务内容" required error={fieldErrors.service}>
                    <input
                      aria-label="服务内容"
                      list="service-options"
                      maxLength={500}
                      placeholder="描述你提供的产品或服务"
                      value={editor.fields.service}
                      onChange={(e) => changeField("service", e.target.value)}
                    />
                    <datalist id="service-options">
                      <option value="展台设计与搭建" />
                      <option value="企业软件定制开发" />
                    </datalist>
                  </Field>
                  <Field label="目标客户" required error={fieldErrors.customer}>
                    <input
                      aria-label="目标客户"
                      maxLength={500}
                      placeholder="描述需要这些服务的企业或个人"
                      value={editor.fields.customer}
                      onChange={(e) => changeField("customer", e.target.value)}
                    />
                  </Field>
                  <Field label="排除项">
                    <input
                      aria-label="排除项"
                      maxLength={500}
                      placeholder="例如同行推广、招聘、培训"
                      value={editor.fields.exclusions}
                      onChange={(e) =>
                        changeField("exclusions", e.target.value)
                      }
                    />
                  </Field>
                </div>
                <div>
                  <Field label="服务地区" required error={fieldErrors.regions}>
                    <input
                      aria-label="服务地区"
                      maxLength={500}
                      placeholder="填写实际可服务地区"
                      value={editor.fields.regions}
                      onChange={(e) => changeField("regions", e.target.value)}
                    />
                  </Field>
                  <Field
                    label="项目偏好"
                    hint={`${editor.fields.preference.length}/200`}
                  >
                    <textarea
                      aria-label="项目偏好"
                      maxLength={200}
                      rows={4}
                      placeholder="填写预算、规模或行业偏好"
                      value={editor.fields.preference}
                      onChange={(e) =>
                        changeField("preference", e.target.value)
                      }
                    />
                  </Field>
                </div>
              </div>
            </fieldset>
          </section>
          {Object.entries(editor.referenceBindings??{}).map(([field,binding])=>binding&&(
            <Notice key={field} tone={binding.valid?'info':'warning'}>
              <p>{labels[field as keyof ProfileFields]}：{binding.valid?'已记录资料引用。':'资料引用已失效，请重新采用有效资料或改为人工内容。'}</p>
              <Button variant="ghost" disabled={action.busy} onClick={()=>{
                setEditor(old=>{const referenceBindings={...old.referenceBindings};delete referenceBindings[field as keyof ProfileFields];return {...old,referenceBindings};});
                notify(`${labels[field as keyof ProfileFields]}已改为人工内容，文字保留；保存后仍需确认。`,'info');
              }}>{labels[field as keyof ProfileFields]}改为人工内容</Button>
            </Notice>
          ))}
          <details className="profile-summary">
            <summary>查看画像摘要</summary>
            <dl className="detail-list">
              {(Object.keys(labels) as (keyof ProfileFields)[]).map((key) => (
                <div key={key}>
                  <dt>{labels[key]}</dt>
                  <dd>{editor.fields[key] || "—"}</dd>
                </div>
              ))}
            </dl>
          </details>
          {action.error && <Notice tone="error">{action.error}</Notice>}
          <footer className="profile-actions">
            <span className="muted">确认后可配置获客任务，尚未启动采集。</span>
            <div className="inline-actions">
              <Button loading={action.busy} onClick={() => void save()}>
                保存草稿
              </Button>
              {researchReady ? <Button
                variant="primary"
                loading={action.busy}
                onClick={() => hasTaskDraftContent(taskDraft) ? setResearchChoice(true) : createResearch()}
              >
                用此画像新建研究
              </Button> : <Button
                variant="primary"
                loading={action.busy}
                disabled={!dirty && current?.status === "CONFIRMED"}
                onClick={requestConfirm}
              >
                {!dirty && current?.status === "CONFIRMED"
                  ? "画像已确认"
                  : "确认画像"}
              </Button>}
            </div>
          </footer>
        </>
      ) : service.materials && session.authenticated && current ? (
        <MaterialsWorkspace
          key={`${taskDraftOwner(session.userId, session.accountScope)}:${current.id}`}
          api={service.materials}
          profile={current}
          currentFields={editor.fields}
          localDrafts={materials}
          onEditLocal={openMaterial}
          onRemoveLocal={setDeleteMaterial}
          onApply={(fields,record) => {
            setEditor((old) => ({
              ...old,
              fields: { ...old.fields, ...fields },
              referenceBindings: {...old.referenceBindings,...adoptedBindings(fields,record)},
              example: false,
            }));
            notify("所选提取内容已填入画像草稿，尚未保存或确认。", "info");
          }}
        />
      ) : (
        <>
          {service.materials && (
            <Notice>
              请先保存业务画像到客户空间，再同步和解析资料。当前可编辑本机草稿。
            </Notice>
          )}
          <div className="section-heading">
            <span className="muted">本机资料草稿 · 尚未同步</span>
            <Button variant="primary" onClick={() => openMaterial()}>
              <Plus />
              添加资料
            </Button>
          </div>
          <LocalMaterialDrafts drafts={materials} onEdit={openMaterial} onRemove={setDeleteMaterial} />
          {!materials.length && (
            <Empty title="暂无资料" description="添加产品介绍或真实案例。" />
          )}
        </>
      )}
      {researchChoice && researchReady && (
        <Modal
          title="已有任务草稿"
          onClose={() => setResearchChoice(false)}
          footer={<>
            <Button onClick={() => setResearchChoice(false)}>取消</Button>
            <Button onClick={() => {
              setResearchChoice(false);
              navigate(taskDraft.mode === "monitor" ? "/tasks/new?mode=monitor" : "/tasks/new");
            }}>继续已有草稿</Button>
            <Button variant="primary" disabled={newerTaskDraft} onClick={createResearch}>保留草稿并新建</Button>
          </>}
        >
          <p>{taskDraft.name || "未命名任务草稿"}</p>
          <p>继续已有草稿会保留原画像和任务条件；另开研究会先将它保留在线索采集或监控任务的本机草稿列表，再使用当前已确认画像。</p>
          <p className="muted">这里只配置任务，不会启动研究。</p>
          {newerTaskDraft && <Notice tone="warning">草稿列表中已有更新版本，请先在线索采集或监控任务中核对；当前草稿未改动。</Notice>}
        </Modal>
      )}
      {confirming && (
        <Modal
          title={`确认画像版本 ${confirming.version}`}
          onClose={() => {
            if (!action.busy) setConfirming(null);
          }}
          footer={
            <>
              <Button
                disabled={action.busy}
                onClick={() => setConfirming(null)}
              >
                取消
              </Button>
              <Button
                variant="primary"
                loading={action.busy}
                disabled={!verified}
                onClick={() => void confirm()}
              >
                确认画像
              </Button>
            </>
          }
        >
          <dl className="detail-list">
            {(Object.keys(labels) as (keyof ProfileFields)[]).map((key) => (
              <div key={key}>
                <dt>{labels[key]}</dt>
                <dd>{confirming.fields[key] || "—"}</dd>
              </div>
            ))}
          </dl>
          <label className="check-row">
            <input
              type="checkbox"
              checked={verified}
              onChange={(e) => setVerified(e.target.checked)}
            />
            我已核实以上信息符合实际业务
          </label>
          {!verified && <p className="field-hint">请核实画像信息后确认。</p>}
          <p className="muted">
            本次确认用于后续研究；采集范围与账号还需在新建任务中配置。
          </p>
          {action.error && <Notice tone="error">{action.error}</Notice>}
        </Modal>
      )}
      {leaving && (
        <Confirm
          title="保留当前画像修改？"
          confirmText="放弃修改并继续"
          onCancel={() => setLeaving(null)}
          onConfirm={() => {
            const target = leaving;
            setLeaving(null);
            if (target.profile) applyProfile(target.profile);
            else if(target.newBusiness)startBusiness();
            else {
              setEditor((old) => ({ ...old, fields: { ...old.baseline },referenceBindings:{...old.baselineReferenceBindings} }));
              if (target.path) navigate(target.path);
            }
          }}
        >
          <p>当前画像尚未保存到客户空间。放弃后将恢复上次保存的内容。</p>
        </Confirm>
      )}
      {materialOpen && (
        <Drawer
          title={materialId ? "编辑资料" : "添加资料"}
          onClose={closeMaterial}
          footer={
            <>
              <Button onClick={closeMaterial}>取消</Button>
              <Button
                variant="primary"
                disabled={reading}
                onClick={saveMaterial}
              >
                保存草稿
              </Button>
            </>
          }
        >
          <Field label="资料名称" required>
            <input
              aria-label="资料名称"
              maxLength={100}
              placeholder="请输入资料名称"
              value={material.name}
              onChange={(e) =>
                setMaterial((old) => ({ ...old, name: e.target.value }))
              }
            />
          </Field>
          <Field label="内容" required>
            <Tabs
              items={[
                { key: "file", label: "上传文件" },
                { key: "text", label: "粘贴文字" },
              ]}
              active={materialMode}
              onChange={(mode) => {
                readGeneration.current++;
                setReading(false);
                setMaterialMode(mode);
              }}
            />
            {materialMode === "file" ? (
              <div className="upload-field">
                <UploadSimple size={32} aria-hidden />
                <label htmlFor="material-file">选择 TXT 或 Markdown 文件</label>
                <input
                  id="material-file"
                  aria-label="上传资料文件"
                  type="file"
                  accept=".txt,.md,text/plain,text/markdown"
                  disabled={reading}
                  onChange={(e) => void readFile(e)}
                />
                <p className="field-hint">
                  最多 200 KB、2000 字；仅在本机读取，不上传。
                </p>
                {reading && <p role="status">正在读取文件…</p>}
                {material.fileName && (
                  <p>
                    {material.fileName} · {material.text.length} 字
                  </p>
                )}
              </div>
            ) : (
              <>
                <textarea
                  aria-label="资料内容"
                  maxLength={2000}
                  rows={7}
                  placeholder="请输入资料内容，支持粘贴文字…"
                  value={material.text}
                  onChange={(e) =>
                    setMaterial((old) => ({
                      ...old,
                      text: e.target.value,
                      fileName: "",
                      bytes: 0,
                    }))
                  }
                />
                <p className="field-hint">{material.text.length}/2000</p>
              </>
            )}
          </Field>
          <Field label="用途" required>
            <select
              aria-label="资料用途"
              value={material.purpose}
              onChange={(e) =>
                setMaterial((old) => ({ ...old, purpose: e.target.value }))
              }
            >
              <option>产品介绍</option>
              <option>真实案例</option>
              <option>服务说明</option>
            </select>
          </Field>
          <Field label="引用范围" required>
            <label className="radio-row">
              <input
                type="radio"
                name="material-visibility"
                checked={material.visibility === "internal"}
                onChange={() =>
                  setMaterial((old) => ({ ...old, visibility: "internal" }))
                }
              />
              <span>
                仅供内部判断<small>仅在团队内部使用，不对外展示。</small>
              </span>
            </label>
            <label className="radio-row">
              <input
                type="radio"
                name="material-visibility"
                checked={material.visibility === "external"}
                onChange={() =>
                  setMaterial((old) => ({ ...old, visibility: "external" }))
                }
              />
              <span>
                允许对外引用<small>同步并确认后才可用于联系准备。</small>
              </span>
            </label>
          </Field>
          <p className="field-hint">
            资料保存为本机草稿，AI 提取和客户空间同步尚未接通。
          </p>
          {materialError && <Notice tone="error">{materialError}</Notice>}
        </Drawer>
      )}
      {discardMaterial && (
        <Confirm
          title="放弃未保存的资料？"
          confirmText="放弃修改"
          onCancel={() => setDiscardMaterial(false)}
          onConfirm={() => {
            readGeneration.current++;
            setReading(false);
            setDiscardMaterial(false);
            setMaterialOpen(false);
          }}
        >
          <p>当前资料的未保存内容会被丢弃。</p>
        </Confirm>
      )}
      {deleteMaterial && (
        <Confirm
          title="删除本机资料草稿？"
          danger
          confirmText="删除草稿"
          onCancel={() => setDeleteMaterial(null)}
          onConfirm={() => {
            setMaterials((old) =>
              old.filter((m) => m.id !== deleteMaterial.id),
            );
            setDeleteMaterial(null);
            notify("本机草稿已删除。");
          }}
        >
          <p>将删除“{deleteMaterial.name}”。该草稿尚未同步或被客户服务引用。</p>
        </Confirm>
      )}
    </>
  );
}
