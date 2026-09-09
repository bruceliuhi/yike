// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import {
  OpportunitiesPage,
  OpportunityDetailPage,
  PUBLIC_SAMPLE,
  customerCsv,
} from "../../src/renderer/pages/Opportunities";
import { parseRoute } from "../../src/renderer/domain/routes";
import type { AppContextValue } from "../../src/renderer/app/context";
import type { YikeService } from "../../src/renderer/services/contracts";
let context: AppContextValue;
vi.mock("../../src/renderer/app/context", () => ({ useApp: () => context }));
beforeEach(() => {
  context = {
    service: {
      opportunities: vi.fn().mockResolvedValue([]),
      opportunity: vi.fn(),
      copy: vi.fn().mockResolvedValue(undefined),
      openExternal: vi.fn().mockResolvedValue(undefined),
    } as unknown as YikeService,
    session: { authenticated: true, userId: "test-a" },
    route: parseRoute("#/opportunities?scope=sample"),
    navigate: vi.fn(),
    notify: vi.fn(),
    refreshSession: vi.fn(),
  };
});
afterEach(cleanup);
describe("customer and public sample boundaries", () => {
  it("keeps public sample selection and customer export disabled", async () => {
    render(<OpportunitiesPage />);
    await screen.findByText(PUBLIC_SAMPLE.title);
    expect(
      (
        screen.getByRole("checkbox", {
          name: "选择本页客户商机",
        }) as HTMLInputElement
      ).disabled,
    ).toBe(true);
    expect(
      (
        screen.getByRole("button", {
          name: "导出所选客户商机",
        }) as HTMLButtonElement
      ).disabled,
    ).toBe(true);
    expect(customerCsv([PUBLIC_SAMPLE])).not.toContain(PUBLIC_SAMPLE.title);
  });
  it("filters actual service results and retains the list query when opening details", async () => {
    context.route = parseRoute("#/opportunities");
    context.service.opportunities = vi.fn().mockResolvedValue([
      {
        ...PUBLIC_SAMPLE,
        id: "real-a",
        sample: false,
        title: "北京展厅",
        buyer: "测试需求方",
        intentStatus: "READY",
      },
      {
        ...PUBLIC_SAMPLE,
        id: "real-b",
        sample: false,
        title: "上海展台",
        buyer: "测试需求方",
        intentStatus: "NEW",
      },
    ]);
    render(<OpportunitiesPage />);
    await screen.findByText("北京展厅");
    fireEvent.change(screen.getByRole("textbox", { name: "搜索商机" }), {
      target: { value: "上海" },
    });
    expect(screen.queryByText("北京展厅")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "查看证据" }));
    expect(context.navigate).toHaveBeenCalledWith(
      expect.stringContaining("/opportunities/real-b?returnTo="),
    );
    expect(
      decodeURIComponent(vi.mocked(context.navigate).mock.calls[0][0]),
    ).toContain("q=");
  });
  it("opens the verified exact source and copies without fabricating a sent fact", async () => {
    context.route = parseRoute("#/opportunities/sample");
    render(<OpportunityDetailPage />);
    await screen.findByText(PUBLIC_SAMPLE.title);
    fireEvent.click(screen.getByRole("button", { name: /查看官方原文/ }));
    await waitFor(() =>
      expect(context.service.openExternal).toHaveBeenCalledWith(
        PUBLIC_SAMPLE.url,
      ),
    );
    fireEvent.click(screen.getByRole("button", { name: "复制草稿" }));
    await waitFor(() =>
      expect(context.service.copy).toHaveBeenCalledWith(PUBLIC_SAMPLE.comment),
    );
    expect(screen.queryByText("已发送")).toBeNull();
  });
  it("escapes CSV formula prefixes and excludes samples even if supplied in a batch", () => {
    const result = customerCsv([
      {
        ...PUBLIC_SAMPLE,
        id: "customer-id",
        sample: false,
        title: '=HYPERLINK("bad")',
      },
      PUBLIC_SAMPLE,
    ]);
    expect(result).toContain("'=HYPERLINK");
    expect(result).not.toContain(PUBLIC_SAMPLE.title);
  });
});
