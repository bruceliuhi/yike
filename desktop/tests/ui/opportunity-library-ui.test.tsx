// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from "@testing-library/react";
import {
  OpportunitiesPage,
  PUBLIC_SAMPLE,
  customerCsv,
} from "../../src/renderer/pages/Opportunities";
import type { AppContextValue } from "../../src/renderer/app/context";
import type { Opportunity } from "../../src/renderer/domain/models";
import type { YikeService } from "../../src/renderer/services/contracts";
import { parseRoute } from "../../src/renderer/domain/routes";

let context: AppContextValue;
vi.mock("../../src/renderer/app/context", () => ({ useApp: () => context }));
const now = Date.parse("2026-09-09T18:00:00+08:00");
function customer(
  id: string,
  stage = "预算询价",
  at = "2026-09-15T18:00:00+08:00",
): Opportunity {
  return {
    ...PUBLIC_SAMPLE,
    id,
    sample: false,
    title: `TEST ${id}`,
    platform: "douyin",
    url: `https://example.test/${id}`,
    libraryFacts: {
      ...PUBLIC_SAMPLE.libraryFacts!,
      opportunity_id: id,
      source_url: `https://example.test/${id}`,
      stage: {
        status: "KNOWN",
        label: stage,
        evidence_excerpt: "TEST 仅用于组件测试。",
      },
      materials_deadline: {
        status: "KNOWN",
        at,
        evidence_excerpt: "TEST 仅用于组件测试。",
      },
    },
  };
}
beforeEach(() => {
  vi.spyOn(Date, "now").mockReturnValue(now);
  context = {
    service: {
      opportunities: vi
        .fn()
        .mockResolvedValue([
          customer("a"),
          customer("b", "方案征集", "2026-09-08T00:00:00+08:00"),
        ]),
    } as unknown as YikeService,
    session: { authenticated: true, userId: "TEST-library-a" },
    route: parseRoute("#/opportunities"),
    navigate: vi.fn(),
    notify: vi.fn(),
    refreshSession: vi.fn(),
  };
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.useRealTimers();
});
describe("P10 library columns and interactive filters", () => {
  it("renders independent facts/status columns and preserves the original platform logo", async () => {
    render(<OpportunitiesPage />);
    await screen.findByText("TEST a");
    expect(
      screen.getAllByRole("columnheader").map((node) => node.textContent),
    ).toEqual(["", "商机标题", "来源", "阶段", "状态", "资料截止", "操作"]);
    const row = screen.getByText("TEST a").closest("tr")!;
    expect(within(row).getByText("预算询价")).toBeTruthy();
    expect(within(row).getByText("09-15 18:00")).toBeTruthy();
    expect(within(row).getByText("2026 · UTC+08:00")).toBeTruthy();
    expect(row.querySelector('img[src*="douyin.ico"]')).toBeTruthy();
  });
  it("combines exact stage and deadline filters, resets them and preserves them in the return route", async () => {
    render(<OpportunitiesPage />);
    await screen.findByText("TEST a");
    fireEvent.change(screen.getByRole("combobox", { name: "筛选阶段" }), {
      target: { value: "known:预算询价" },
    });
    fireEvent.change(screen.getByRole("combobox", { name: "筛选资料截止" }), {
      target: { value: "week" },
    });
    expect(screen.queryByText("TEST b")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "查看证据" }));
    const destination = vi.mocked(context.navigate).mock.calls[0][0];
    const returnTo = new URLSearchParams(destination.split("?")[1]).get(
      "returnTo",
    )!;
    expect(new URLSearchParams(returnTo.split("?")[1]).get("stage")).toBe(
      "known:预算询价",
    );
    expect(new URLSearchParams(returnTo.split("?")[1]).get("deadline")).toBe(
      "week",
    );
    fireEvent.click(screen.getByRole("button", { name: "重置筛选" }));
    expect(screen.getByText("TEST b")).toBeTruthy();
  });
  it("keeps missing fields and version mismatches visible and independently filterable", async () => {
    const missing = { ...customer("missing"), libraryFacts: undefined };
    const mismatch = {
      ...customer("mismatch"),
      sourceEvidenceVersion: "TEST-new-version",
    };
    context.service.opportunities = vi
      .fn()
      .mockResolvedValue([missing, mismatch]);
    render(<OpportunitiesPage />);
    await screen.findByText("TEST missing");
    expect(
      within(screen.getByText("TEST missing").closest("tr")!).getAllByText(
        "尚未提供",
      ),
    ).toHaveLength(2);
    expect(
      within(screen.getByText("TEST mismatch").closest("tr")!).getAllByText(
        "待核验",
      ),
    ).toHaveLength(2);
    fireEvent.change(screen.getByRole("combobox", { name: "筛选资料截止" }), {
      target: { value: "missing" },
    });
    expect(screen.queryByText("TEST mismatch")).toBeNull();
    fireEvent.change(screen.getByRole("combobox", { name: "筛选资料截止" }), {
      target: { value: "unverified" },
    });
    expect(screen.getByText("TEST mismatch")).toBeTruthy();
    expect(screen.queryByText("TEST missing")).toBeNull();
  });
  it("sorts known deadlines earliest first, keeps absent values last and exports exact timezone", async () => {
    context.service.opportunities = vi
      .fn()
      .mockResolvedValue([
        { ...customer("missing"), libraryFacts: undefined },
        customer("later"),
        customer("earlier", "询价", "2026-09-08T00:00:00+08:00"),
      ]);
    render(<OpportunitiesPage />);
    await screen.findByText("TEST later");
    fireEvent.change(screen.getByRole("combobox", { name: "排序方式" }), {
      target: { value: "deadline" },
    });
    const rows = screen.getAllByRole("row").slice(1);
    expect(rows.map((row) => row.querySelector("strong")?.textContent)).toEqual(
      ["TEST earlier", "TEST later", "TEST missing"],
    );
    const csv = customerCsv([
      customer("earlier", "=TEST-formula", "2026-09-08T00:00:00+08:00"),
      PUBLIC_SAMPLE,
    ]);
    expect(csv).toContain("'=TEST-formula");
    expect(csv).toContain("2026-09-08 00:00 UTC+08:00");
    expect(csv).not.toContain(PUBLIC_SAMPLE.title);
  });
  it("keeps source-backed public sample read-only and clears customer fact filters on scope change", async () => {
    render(<OpportunitiesPage />);
    await screen.findByText("TEST a");
    fireEvent.change(screen.getByRole("combobox", { name: "筛选资料截止" }), {
      target: { value: "overdue" },
    });
    fireEvent.click(screen.getByRole("tab", { name: "公开研究样例" }));
    cleanup();
    context.route = parseRoute("#/opportunities?scope=sample");
    render(<OpportunitiesPage />);
    expect(screen.getByText(PUBLIC_SAMPLE.title)).toBeTruthy();
    expect(screen.getByText("09-15 18:00")).toBeTruthy();
    expect(
      (
        screen.getByRole("button", {
          name: "导出所选客户商机",
        }) as HTMLButtonElement
      ).disabled,
    ).toBe(true);
    expect(
      (
        screen.getByRole("checkbox", {
          name: `选择${PUBLIC_SAMPLE.title}`,
        }) as HTMLInputElement
      ).disabled,
    ).toBe(true);
  });
  it("shows no-match feedback without hiding a saved stage filter", async () => {
    context.route = parseRoute(
      "#/opportunities?stage=known%3ATEST-missing-stage",
    );
    render(<OpportunitiesPage />);
    await screen.findByText("没有符合条件的商机");
    expect(
      (screen.getByRole("combobox", { name: "筛选阶段" }) as HTMLSelectElement)
        .value,
    ).toBe("known:TEST-missing-stage");
    fireEvent.click(screen.getByRole("button", { name: "重置筛选" }));
    expect(screen.getByText("TEST a")).toBeTruthy();
  });
  it("exposes a permission failure as an error instead of empty or made-up fields", async () => {
    context.service.opportunities = vi
      .fn()
      .mockRejectedValue(new Error("TEST 无权限"));
    render(<OpportunitiesPage />);
    await screen.findByText("TEST 无权限");
    expect(screen.queryByRole("table")).toBeNull();
    expect(screen.queryByText("暂无客户商机")).toBeNull();
    expect(screen.getByRole("button", { name: "重试" })).toBeTruthy();
  });
  it("bounds a hanging list and ignores a late response after retry", async () => {
    vi.useFakeTimers();
    let resolve!: (rows: Opportunity[]) => void;
    context.service.opportunities = vi
      .fn()
      .mockImplementationOnce(
        () =>
          new Promise((done) => {
            resolve = done;
          }),
      )
      .mockResolvedValue([customer("new")]);
    render(<OpportunitiesPage />);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(30000);
    });
    expect(screen.getByText("商机读取超时，请重试。")).toBeTruthy();
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "重试" }));
    });
    expect(screen.getByText("TEST new")).toBeTruthy();
    await act(async () => {
      resolve([customer("old")]);
    });
    expect(screen.queryByText("TEST old")).toBeNull();
  });
  it("discards pending source facts and selections after changing identity", async () => {
    let resolve!: (rows: Opportunity[]) => void;
    context.service.opportunities = vi
      .fn()
      .mockImplementationOnce(
        () =>
          new Promise((done) => {
            resolve = done;
          }),
      )
      .mockResolvedValue([customer("new-user")]);
    const view = render(<OpportunitiesPage />);
    await act(async () => {});
    context = {
      ...context,
      session: { authenticated: true, userId: "TEST-library-b" },
    };
    view.rerender(<OpportunitiesPage />);
    await screen.findByText("TEST new-user");
    await act(async () => {
      resolve([customer("old-user")]);
    });
    expect(screen.queryByText("TEST old-user")).toBeNull();
    expect(
      (
        screen.getByRole("button", {
          name: "导出所选客户商机",
        }) as HTMLButtonElement
      ).disabled,
    ).toBe(true);
  });
});
