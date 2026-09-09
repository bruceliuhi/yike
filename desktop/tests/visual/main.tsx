import "../../src/renderer/app/validationRuntime";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App, AppErrorBoundary } from "../../src/renderer/app/App";
import { AppProvider } from "../../src/renderer/app/context";
import {
  HARNESS_MARKER,
  TEST_USER,
  profile,
  taskDraft,
  opportunity,
} from "./fixtures";
import { createVisualService, type VisualState } from "./service";
import { isolateBrowser } from "./isolation";
import { applyReferenceState } from "./reference";
import { makeVisualMaterials } from "./materials";
import { makeVisualFollowup } from "./followup";
import { configureRecovery, selectRecovery } from "./recovery";
import { RecoveryControls } from "./RecoveryControls";
import { referenceRoute } from "./routing";
import "../../src/renderer/styles.css";
import "./visual.css";
import { configureR4Visual, r4TaskDraft, R4_TEST_SCOPE } from "./r4";
import { taskDraftOwner } from "../../src/renderer/app/taskDraft";
import { configureRegistryVisual } from "./connectionRegistry";
import { makeMaterialRecovery } from "./materialRecovery";
import { MaterialRecoveryControls } from "./MaterialRecoveryControls";
import { selectManagementRecovery, configureManagementRecovery } from "./managementRecovery";
import { ManagementRecoveryControls } from "./ManagementRecoveryControls";

const params = new URLSearchParams(location.search);
const state = (
  ["populated", "empty", "error", "loading"].includes(params.get("state") || "")
    ? params.get("state")
    : "populated"
) as VisualState;
const requested =
  params.get("scenario") || location.hash.replace(/^#\/?/, "") || "P09";
const page = /^P(?:0[1-9]|1[0-9]|20)$/.test(requested) ? requested : "P09";
const routes: Record<string, string> = {
  P01: "/login",
  P02: "/workbench",
  P03: "/profile",
  P04: "/profile?tab=materials",
  P05: "/collection",
  P06: "/tasks/new",
  P07: "/candidates",
  P08: "/monitors",
  P09: "/monitors/TEST-monitor",
  P10: "/opportunities",
  P11: "/opportunities/TEST-opportunity",
  P12: "/outreach?opportunity=TEST-opportunity",
  P13: "/outreach?opportunity=TEST-opportunity&confirm=send",
  P14: "/followups",
  P15: "/followups?add=1&opportunity=TEST-opportunity",
  P16: "/connections",
  P17: "/connections?connect=xhs",
  P18: "/settings",
  P19: "/tasks/new?step=confirm",
  P20: "/tasks/new?mode=monitor",
};
const harness = createVisualService(
  state,
  page === "P01" || params.get("session") === "guest",
);
const reference = params.get("reference") === "r3";
const r4 = params.get("suite") === "r4";
if (reference && state !== "error" && state !== "loading")
  applyReferenceState(harness.service, page);
if (r4) configureR4Visual(harness.service, state);
if (params.get("registry") === "registered" && page === "P16" && state === "populated")
  configureRegistryVisual(harness.service, harness.record);
// Isolated read-only lineage case; never infer versions in the production adapter.
if (params.get("lineage") === "updated" && page === "P09" && state === "populated") {
  harness.service.profiles = async () => {
    harness.record("profiles.TEST-lineage");
    return [
      {...structuredClone(profile), profileEntityId: "TEST-profile-entity", status: "REVOKED"},
      {...structuredClone(profile), id: "TEST-profile-v2", profileEntityId: "TEST-profile-entity", version: 2, status: "CONFIRMED"},
    ];
  };
}
if (params.get("capabilities") === "complete" && state === "populated") {
  harness.service.materials = makeVisualMaterials();
  harness.service.followup = makeVisualFollowup();
}
const materialRecovery = params.get("materials") === "recovery"
  && page === "P04" && state === "populated" && params.get("session") !== "guest"
  ? makeMaterialRecovery(harness.record) : undefined;
if (params.has("materials") && !materialRecovery)
  throw new Error("TEST 资料恢复仅接受 P04/populated/TEST 登录身份与 materials=recovery。");
if (materialRecovery) harness.service.materials = materialRecovery.service;
const managementRecovery = selectManagementRecovery(
  params.get("management"), page, state, page === "P01" || params.get("session") === "guest",
) ? configureManagementRecovery(harness) : undefined;
const recoveryName = selectRecovery(
  params.get("recovery"),
  page,
  state,
  page === "P01" || params.get("session") === "guest",
);
const recovery = recoveryName
  ? configureRecovery(harness, recoveryName)
  : undefined;
const storage = isolateBrowser(harness.record, { saveExport: managementRecovery?.saveExport });
const seed = (name: string, value: unknown) =>
  storage.session.setItem("yike.ui.draft.v1." + name, JSON.stringify(value));
if (state === "populated") {
  const owner = taskDraftOwner(TEST_USER, r4 ? R4_TEST_SCOPE : undefined);
  const makeTask = r4 ? r4TaskDraft : taskDraft;
  seed(`task.${owner}`, makeTask(page === "P20" ? "monitor" : "once"));
  seed(`task-library.${owner}`, [makeTask("once"), makeTask("monitor")]);
  if (!reference) {
    seed(`materials.${TEST_USER}`, [
      {
        id: "TEST-material",
        name: "TEST 展台服务说明",
        text: "TEST 提供展台设计、搭建与现场维护。仅供视觉验收。",
        purpose: "服务说明",
        visibility: "external",
        updatedAt: "2026-09-09T09:00:00+08:00",
      },
    ]);
    seed(`followup:${TEST_USER}`, {
      opportunityId: opportunity.id,
      status: "CONTACTED",
      note: "TEST 已整理展区资料核对事项；本内容仅保存到测试内存。",
      next: "",
    });
  }
}
recovery?.seed(storage.session, page);
history.replaceState(
  null,
  "",
  location.pathname +
    location.search +
    "#" +
    (referenceRoute(page, reference, state, recoveryName) ||
      (recoveryName === "send-unknown"
        ? "/outreach?opportunity=TEST-opportunity&channel=comment"
        : undefined) ||
      (recoveryName === "connection-limited"
        ? "/connections?connect=xhs&returnTo=" +
          encodeURIComponent("/tasks/new?step=connect")
        : undefined) ||
      routes[requested] ||
      (location.hash.startsWith("#/") && !/^#\/P\d+$/.test(location.hash)
        ? location.hash.slice(1)
        : routes[page])),
);
Object.defineProperty(window, "__YIKE_VISUAL__", {
  value: {
    marker: HARNESS_MARKER,
    events: harness.events,
    scenario: page,
    state,
    profileId: profile.id,
  },
  configurable: false,
});
createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <>
      <div id="visual-harness-banner" role="note">
        TEST 隔离视觉验收 · 内存夹具 · 禁止采集 / 发送 / 客户库写入
        {recoveryName && ` · 恢复场景 ${recoveryName}`}
        {managementRecovery && " · TEST 模拟保存/取消，不写文件"}
      </div>
      <details id="visual-harness-controls">
        <summary>TEST 场景</summary>
        {recovery && <RecoveryControls controller={recovery} />}
        {materialRecovery && <MaterialRecoveryControls controller={materialRecovery} />}
        {managementRecovery && <ManagementRecoveryControls controller={managementRecovery} />}
        <div>
          {Object.keys(routes).map((id) => (
            <a key={id} href={`/?scenario=${id}&state=${state}`}>
              {id}
            </a>
          ))}
        </div>
        <p>
          状态：
          {(["populated", "empty", "error", "loading"] as const).map(
            (value) => (
              <a key={value} href={`/?scenario=${page}&state=${value}`}>
                {value}{" "}
              </a>
            ),
          )}
        </p>
      </details>
      <AppErrorBoundary>
        <AppProvider service={harness.service}>
          <App />
        </AppProvider>
      </AppErrorBoundary>
    </>
  </StrictMode>,
);
