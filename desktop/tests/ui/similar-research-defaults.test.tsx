// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import "@testing-library/jest-dom/vitest";
import type { AppContextValue } from "../../src/renderer/app/context";
import { PLATFORMS } from "../../src/renderer/domain/models";
import { defaultResearchSettings } from "../../src/renderer/domain/researchUsage";
import { parseRoute } from "../../src/renderer/domain/routes";
import { SimilarResearchDrawer } from "../../src/renderer/pages/opportunities/SimilarResearchDrawer";
import type { YikeService } from "../../src/renderer/services/contracts";
import { binding, collection, researchProfile, researchRow, similar } from "./r4-opportunity-research-fixtures";

let context: AppContextValue;
vi.mock("../../src/renderer/app/context", () => ({ useApp: () => context }));
beforeEach(() => {
  context = {
    session: { authenticated: true, userId: binding.userId, accountScope: binding.accountScope },
    route: parseRoute("#/opportunities"),
    navigate: vi.fn(), notify: vi.fn(), refreshSession: vi.fn(),
    service: {
      opportunityResearch: {
        list: vi.fn().mockResolvedValue(collection),
        similar: vi.fn(async (_binding, requestId) => ({
          ...structuredClone(similar), requestId,
          supportedPlatforms: PLATFORMS.map((p) => p.id),
        })),
      },
      profiles: vi.fn().mockResolvedValue([researchProfile]),
      startTask: vi.fn(),
      researchUsage: { quote: vi.fn() },
      execution: { researchContractVersion: 1, execute: vi.fn() },
    } as unknown as YikeService,
  };
});
afterEach(cleanup);

it.each(PLATFORMS.flatMap((p) => [
  { source: p.id, expected: p.name },
  { source: p.name, expected: p.name },
]))("preselects only the supported current source $source", async ({ source, expected }) => {
  render(<SimilarResearchDrawer opportunity={{ ...researchRow, platform: source }} onClose={vi.fn()} onCreateDraft={vi.fn()} />);
  await screen.findByDisplayValue(researchProfile.description);
  for (const p of PLATFORMS) {
    expect((screen.getByRole("checkbox", { name: p.name }) as HTMLInputElement).checked).toBe(p.name === expected);
  }
  expect(screen.getByText(/仅预选当前机会来源/)).toBeVisible();
});

it.each(["未知平台", "抖音 + 公开网站", "https://www.zhihu.com/", "当前原任务包含全部平台"])(
  "never infers a platform for %s", async (platform) => {
    render(<SimilarResearchDrawer opportunity={{ ...researchRow, platform }} onClose={vi.fn()} onCreateDraft={vi.fn()} />);
    await screen.findByDisplayValue(researchProfile.description);
    expect(screen.getAllByRole("checkbox").every((node) => !(node as HTMLInputElement).checked)).toBe(true);
    expect(screen.getByRole("button", { name: "创建任务草稿" })).toBeDisabled();
  },
);

it("leaves unsupported current sources unselected instead of choosing a supported alternative", async () => {
  context.service.opportunityResearch!.similar = vi.fn(async (_binding, requestId) => ({ ...similar, requestId }));
  render(<SimilarResearchDrawer opportunity={{ ...researchRow, platform: "抖音" }} onClose={vi.fn()} onCreateDraft={vi.fn()} />);
  await screen.findByDisplayValue(researchProfile.description);
  expect(screen.getByRole("checkbox", { name: "公开网站" })).not.toBeChecked();
  expect(screen.getByText(/请手动选择本次搜索平台/)).toBeVisible();
  expect(screen.getByRole("button", { name: "创建任务草稿" })).toBeDisabled();
});

it("defaults only the visible soubei ceiling and hands off bounded configuration after an explicit click", async () => {
  const handoff = vi.fn();
  render(<SimilarResearchDrawer opportunity={researchRow} onClose={vi.fn()} onCreateDraft={handoff} />);
  await screen.findByDisplayValue(researchProfile.description);
  expect(screen.getByRole("spinbutton", { name: "单次搜贝上限" })).toHaveValue(defaultResearchSettings().maxSoubei);
  expect(screen.getByRole("spinbutton", { name: "独立来源上限", hidden: true })).toHaveValue(30);
  expect(screen.getByRole("spinbutton", { name: "研究时长上限", hidden: true })).toHaveValue(10);
  expect(handoff).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "创建任务草稿" }));
  await waitFor(() => expect(handoff).toHaveBeenCalledOnce());
  expect(handoff.mock.calls[0][0]).toMatchObject({
    platforms: ["web"], originalScope: similar.originalScope, additionalScope: similar.additionalScope,
    limits: { sources: 30, minutes: 10, soubei: defaultResearchSettings().maxSoubei, stopAtAnyLimit: true },
  });
  expect(context.service.startTask).not.toHaveBeenCalled();
  expect(context.service.researchUsage!.quote).not.toHaveBeenCalled();
  expect(context.service.execution!.execute).not.toHaveBeenCalled();
});

it("preserves manual platform and soubei edits across rerenders, including an explicitly cleared ceiling", async () => {
  const handoff = vi.fn();
  const props = { opportunity: researchRow, onClose: vi.fn(), onCreateDraft: handoff };
  const ui = render(<SimilarResearchDrawer {...props} />);
  await screen.findByDisplayValue(researchProfile.description);
  fireEvent.click(screen.getByRole("checkbox", { name: "公开网站" }));
  fireEvent.click(screen.getByRole("checkbox", { name: "抖音" }));
  fireEvent.change(screen.getByRole("spinbutton", { name: "单次搜贝上限" }), { target: { value: "45" } });
  ui.rerender(<SimilarResearchDrawer {...props} opportunity={{ ...researchRow }} />);
  expect(screen.getByRole("checkbox", { name: "公开网站" })).not.toBeChecked();
  expect(screen.getByRole("checkbox", { name: "抖音" })).toBeChecked();
  expect(screen.getByRole("spinbutton", { name: "单次搜贝上限" })).toHaveValue(45);
  fireEvent.change(screen.getByRole("spinbutton", { name: "单次搜贝上限" }), { target: { value: "" } });
  ui.rerender(<SimilarResearchDrawer {...props} />);
  expect(screen.getByRole("spinbutton", { name: "单次搜贝上限" })).toHaveValue(null);
  fireEvent.click(screen.getByRole("button", { name: "创建任务草稿" }));
  await waitFor(() => expect(handoff).toHaveBeenCalledOnce());
  expect(handoff.mock.calls[0][0]).toMatchObject({ platforms: ["douyin"], limits: { soubei: null }, usage: { status: "UNKNOWN" } });
});
