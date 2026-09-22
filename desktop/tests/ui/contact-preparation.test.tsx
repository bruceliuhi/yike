// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { OutreachPage } from "../../src/renderer/pages/Outreach";
import { ContactNotes } from "../../src/renderer/pages/outreach/ContactNotes";
import { PUBLIC_SAMPLE } from "../../src/renderer/pages/Opportunities";
import { parseRoute } from "../../src/renderer/domain/routes";
import { sortContactRows } from "../../src/renderer/domain/contactList";
import type { AppContextValue } from "../../src/renderer/app/context";
import type { YikeService } from "../../src/renderer/services/contracts";
import type { Opportunity } from "../../src/renderer/domain/models";
import { service as productionService } from "../../src/renderer/services/client";
let context: AppContextValue;
vi.mock("../../src/renderer/app/context", () => ({ useApp: () => context }));
const row = (id: string, updatedAt = "2026-09-09T08:00:00Z"): Opportunity => ({
  ...PUBLIC_SAMPLE,
  id,
  sample: false,
  title: "TEST " + id,
  updatedAt,
  url: "https://source.invalid/" + id,
});
beforeEach(() => {
  sessionStorage.clear();
  context = {
    session: { authenticated: true, userId: crypto.randomUUID() },
    service: {
      opportunities: vi.fn().mockResolvedValue([]),
      opportunity: vi.fn(),
      connections: vi.fn().mockResolvedValue([]),
      saveContact: vi.fn().mockResolvedValue(undefined),
      send: vi.fn(),
    } as unknown as YikeService,
    route: parseRoute("#/outreach"),
    navigate: vi.fn(),
    notify: vi.fn(),
    refreshSession: vi.fn(),
  };
});
afterEach(cleanup);
it("does not advertise the unconnected legacy generator in the production client", () => {
  expect(productionService.generateContact).toBeUndefined();
  expect(productionService.shortCoach).toBeDefined();
});
it("keeps manual copy available without a legacy generation endpoint", async () => {
  context.route = parseRoute("#/outreach?opportunity=manual");
  vi.mocked(context.service.opportunity).mockResolvedValue(row("manual"));
  context.service.copy = vi.fn().mockResolvedValue(undefined);
  render(<OutreachPage />);
  const editor = await screen.findByRole("textbox", { name: "沟通内容" });
  expect(screen.queryByRole("button", { name: /^(生成联系草稿|重新生成|重试生成)$/ })).toBeNull();
  expect(screen.queryByText(/可继续编辑或使用原草稿生成/)).toBeNull();
  fireEvent.change(editor, { target: { value: "您提到的资料检索问题还需要处理吗？" } });
  expect(screen.getByRole("button", { name: "复制联系草稿" }).textContent).toContain("复制草稿");
  fireEvent.click(screen.getByRole("button", { name: "复制联系草稿" }));
  await waitFor(() => expect(context.service.copy).toHaveBeenCalledWith("您提到的资料检索问题还需要处理吗？"));
  expect(context.navigate).not.toHaveBeenCalled();
  expect(context.service.saveContact).not.toHaveBeenCalled();
  expect(context.service.send).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "记录实际跟进" }));
  expect(context.navigate).toHaveBeenCalledWith("/followups?add=1&opportunity=manual");
  expect(context.service.send).not.toHaveBeenCalled();
});
it("does not offer actual followup for a public sample", async () => {
  context.route = parseRoute("#/outreach?opportunity=sample");
  render(<OutreachPage />);
  await screen.findByRole("textbox", { name: "沟通内容" });
  expect(screen.queryByRole("button", { name: "记录实际跟进" })).toBeNull();
  expect(context.service.send).not.toHaveBeenCalled();
});
it("sorts actual update timestamps, keeps unknown times last, and preserves the input array", () => {
  const input = [
    row("unknown", ""),
    row("old", "2026-09-08T00:00:00Z"),
    row("new"),
  ];
  expect(sortContactRows(input, "newest").map((r) => r.id)).toEqual([
    "new",
    "old",
    "unknown",
  ]);
  expect(sortContactRows(input, "oldest").map((r) => r.id)).toEqual([
    "old",
    "new",
    "unknown",
  ]);
  expect(input.map((r) => r.id)).toEqual(["unknown", "old", "new"]);
});
it("searches source URLs and restores the selected sort/filter after reopening", async () => {
  vi.mocked(context.service.opportunities).mockResolvedValue([
    row("second"),
    row("first", "2026-09-08T00:00:00Z"),
  ]);
  const view = render(<OutreachPage />);
  await screen.findByRole("button", { name: /TEST second/ });
  const titles = () =>
    screen
      .getAllByRole("button", { name: /TEST (first|second)/ })
      .map((el) => el.textContent);
  expect(titles()[0]).toContain("second");
  fireEvent.change(screen.getByRole("combobox", { name: "联系准备排序" }), {
    target: { value: "oldest" },
  });
  expect(titles()[0]).toContain("first");
  fireEvent.change(screen.getByRole("textbox", { name: "搜索联系准备" }), {
    target: { value: "source.invalid/second" },
  });
  expect(screen.queryByRole("button", { name: /TEST first/ })).toBeNull();
  view.unmount();
  render(<OutreachPage />);
  await screen.findByRole("button", { name: /TEST second/ });
  expect(
    (
      screen.getByRole("combobox", {
        name: "联系准备排序",
      }) as HTMLSelectElement
    ).value,
  ).toBe("oldest");
  expect(
    (screen.getByRole("textbox", { name: "搜索联系准备" }) as HTMLInputElement)
      .value,
  ).toBe("source.invalid/second");
});
it("keeps preparation notes outside saved message payloads", async () => {
  const current = row("notes");
  context.route = parseRoute("#/outreach?opportunity=notes");
  vi.mocked(context.service.opportunity).mockResolvedValue(current);
  render(<OutreachPage />);
  fireEvent.change(
    await screen.findByRole("textbox", { name: "联系准备备注" }),
    { target: { value: "TEST 内部核对，不能外发" } },
  );
  fireEvent.click(screen.getByRole("button", { name: "保存草稿" }));
  await waitFor(() =>
    expect(context.service.saveContact).toHaveBeenCalledOnce(),
  );
  const payload = JSON.stringify(
    vi.mocked(context.service.saveContact).mock.calls[0],
  );
  expect(payload).not.toContain("内部核对");
  expect(context.service.saveContact).toHaveBeenCalledWith(
    expect.not.objectContaining({ note: expect.anything() }),
  );
});
it("separates notes by user, opportunity and profile version", () => {
  const current = row("scope");
  const user = context.session.userId;
  const view = render(<ContactNotes row={current} />);
  const note = () =>
    screen.getByRole("textbox", {
      name: "联系准备备注",
    }) as HTMLTextAreaElement;
  fireEvent.change(note(), { target: { value: "TEST 原资料版本备注" } });
  view.rerender(
    <ContactNotes row={{ ...current, profileVersionId: "another-version" }} />,
  );
  expect(note().value).toBe("");
  view.rerender(<ContactNotes row={row("other")} />);
  expect(note().value).toBe("");
  context = {
    ...context,
    session: { authenticated: true, userId: "other-user" },
  };
  view.rerender(<ContactNotes row={current} />);
  expect(note().value).toBe("");
  context = { ...context, session: { authenticated: true, userId: user } };
  view.rerender(<ContactNotes row={current} />);
  expect(note().value).toBe("TEST 原资料版本备注");
});
it("limits notes to 500 characters without splitting supplementary Unicode", () => {
  render(<ContactNotes row={row("limit")} />);
  const input = screen.getByRole("textbox", {
    name: "联系准备备注",
  }) as HTMLTextAreaElement;
  fireEvent.change(input, { target: { value: "😀".repeat(501) } });
  expect(Array.from(input.value)).toHaveLength(500);
  expect(screen.getByText("500/500")).toBeTruthy();
});
it("does not accept or persist notes for public samples", () => {
  render(<ContactNotes row={PUBLIC_SAMPLE} />);
  const input = screen.getByRole("textbox", {
    name: "联系准备备注",
  }) as HTMLTextAreaElement;
  expect(input.readOnly).toBe(true);
  fireEvent.change(input, { target: { value: "must not persist" } });
  expect(input.value).toBe("");
  expect(Object.values(sessionStorage).join("")).not.toContain(
    "must not persist",
  );
});
