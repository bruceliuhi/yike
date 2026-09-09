// @vitest-environment jsdom
import { webcrypto } from "node:crypto";
import { useEffect } from "react";
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { OutreachPage } from "../../src/renderer/pages/Outreach";
import { ContactEditor } from "../../src/renderer/pages/outreach/ContactEditor";
import { PUBLIC_SAMPLE } from "../../src/renderer/pages/Opportunities";
import { clearLocalDrafts } from "../../src/renderer/app/hooks";
import {
  operationLedgerKey,
  useOperationLedger,
} from "../../src/renderer/app/operationLedger";
import type { AppContextValue } from "../../src/renderer/app/context";
import { parseRoute } from "../../src/renderer/domain/routes";
import type {
  CoachInput,
  CoachSuggestion,
  DraftSaveInput,
  DraftSaveReceipt,
} from "../../src/renderer/domain/shortCoach";
import type { YikeService } from "../../src/renderer/services/contracts";
import { ServiceError } from "../../src/renderer/services/contracts";
let context: AppContextValue;
vi.mock("../../src/renderer/app/context", () => ({ useApp: () => context }));
const row = {
  ...PUBLIC_SAMPLE,
  id: "TEST-coach",
  sample: false,
  sourceStatus: "OPEN",
  profileStatus: "CONFIRMED",
  profileVersionId: "TEST-profile",
  sourceEvidenceVersion: "v1",
  sourceObservedAt: "2026-09-09T08:00:00Z",
  excerpt: "TEST原文：服务范围需要核对。",
  comment: "TEST评论原稿",
  dm: "TEST私信原稿",
};
function suggestion(input: CoachInput): CoachSuggestion {
  return {
    suggestionId: "TEST-suggestion",
    binding: input.binding,
    content: "TEST请问服务范围如何获取？",
    question: "TEST请问服务范围如何获取？",
    context: { summary: "TEST依据服务范围原文", quoteIds: ["quote-1"] },
    quotes: [
      {
        id: "quote-1",
        text: row.excerpt,
        start: 0,
        end: row.excerpt.length,
        sourceUrl: row.url,
        sourceEvidenceVersion: "v1",
      },
    ],
    checks: [
      {
        kind: "PROMISE",
        status: "NEEDS_REVIEW",
        message: "TEST待核实服务能力",
        quoteIds: ["quote-1"],
      },
    ],
    createdAt: new Date(Date.now() - 1000).toISOString(),
    expiresAt: new Date(Date.now() + 60_000).toISOString(),
  };
}
function saved(input: DraftSaveInput): DraftSaveReceipt {
  return {
    binding: input.binding,
    status: "SUCCEEDED",
    confirmed: true,
    snapshot: {
      ...input.snapshot,
      draft: {
        ...input.snapshot.draft,
        savedContent: input.snapshot.draft.content,
      },
    },
  };
}
const content = () =>
  screen.getByRole("textbox", { name: "沟通内容" }) as HTMLTextAreaElement;
const stored = (userId = context.session.userId!) =>
  JSON.parse(
    localStorage.getItem(operationLedgerKey("contact-draft-saves", userId)) ||
      "{}",
  );
async function startCoach() {
  fireEvent.click(screen.getByRole("button", { name: "生成短句建议" }));
  fireEvent.click(await screen.findByRole("button", { name: "生成建议" }));
}
beforeEach(() => {
  vi.stubGlobal("crypto", webcrypto);
  localStorage.clear();
  sessionStorage.clear();
  clearLocalDrafts();
  context = {
    session: {
      authenticated: true,
      userId: crypto.randomUUID(),
      accountScope: { id: "TEST-space", version: 1 },
    },
    route: parseRoute("#/outreach?opportunity=" + row.id),
    navigate: vi.fn(),
    notify: vi.fn(),
    refreshSession: vi.fn(),
    service: {
      opportunities: vi.fn().mockResolvedValue([row]),
      opportunity: vi.fn().mockResolvedValue(row),
      connections: vi.fn().mockResolvedValue([]),
      copy: vi.fn().mockResolvedValue(undefined),
      generateContact: vi.fn().mockResolvedValue("TEST普通生成文本"),
      saveContact: vi.fn().mockResolvedValue(undefined),
      shortCoach: { generate: vi.fn(async (input) => suggestion(input)) },
      contactDrafts: {
        save: vi.fn(async (input) => saved(input)),
        operation: vi.fn(),
      },
    } as unknown as YikeService,
  };
});
afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.restoreAllMocks();
});
async function mount() {
  const view = render(<OutreachPage />);
  await screen.findByDisplayValue("TEST评论原稿");
  return view;
}
describe("R4 structured short coach", () => {
  it("keeps edits during generation, compares complete text, verifies evidence and only then replaces", async () => {
    let resolve!: (value: CoachSuggestion) => void;
    vi.mocked(context.service.shortCoach!.generate).mockImplementation(
      () =>
        new Promise((done) => {
          resolve = done;
        }),
    );
    await mount();
    await startCoach();
    await waitFor(() =>
      expect(context.service.shortCoach!.generate).toHaveBeenCalledOnce(),
    );
    fireEvent.change(content(), { target: { value: "TEST生成期间人工编辑" } });
    const input = vi.mocked(context.service.shortCoach!.generate).mock
      .calls[0][0];
    await act(async () => resolve(suggestion(input)));
    await screen.findByRole("dialog", { name: "短句建议与当前草稿" });
    expect(content().value).toBe("TEST生成期间人工编辑");
    expect(
      screen.getByText(/生成期间你修改了草稿，人工内容仍保留/),
    ).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "核对并替换当前草稿" }));
    await waitFor(() =>
      expect(content().value).toBe("TEST请问服务范围如何获取？"),
    );
    expect(context.service.opportunity).toHaveBeenCalledTimes(2);
    expect(
      (screen.getByRole("button", { name: "准备发送" }) as HTMLButtonElement)
        .disabled,
    ).toBe(true);
    fireEvent.click(screen.getByRole("tab", { name: "私信草稿" }));
    expect(content().value).toBe("TEST私信原稿");
  });
  it("does not turn the legacy string generator into checked coaching", async () => {
    context.service.shortCoach = undefined;
    await mount();
    expect(
      screen.getByText("短句教练服务尚未接通，可继续编辑或使用原草稿生成。"),
    ).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "重新生成" }));
    fireEvent.click(await screen.findByRole("button", { name: "生成新建议" }));
    await screen.findByRole("dialog", { name: "新草稿预览" });
    expect(context.service.generateContact).toHaveBeenCalledOnce();
    expect(screen.queryByText("引用上下文")).toBeNull();
  });
  it("cancels waiting and discards a late suggestion without overwriting the draft", async () => {
    let resolve!: (v: CoachSuggestion) => void;
    vi.mocked(context.service.shortCoach!.generate).mockImplementation(
      () =>
        new Promise((done) => {
          resolve = done;
        }),
    );
    await mount();
    await startCoach();
    await waitFor(() =>
      expect(context.service.shortCoach!.generate).toHaveBeenCalledOnce(),
    );
    const [input, signal] = vi.mocked(context.service.shortCoach!.generate).mock
      .calls[0];
    fireEvent.click(screen.getByRole("button", { name: "停止等待" }));
    await screen.findByText(/已停止等待/);
    expect(signal!.aborted).toBe(true);
    await act(async () => resolve(suggestion(input)));
    expect(
      screen.queryByRole("dialog", { name: "短句建议与当前草稿" }),
    ).toBeNull();
    expect(content().value).toBe(row.comment);
  });
  it("bounds a hung generation and permits a new request without applying the old one", async () => {
    vi.mocked(context.service.shortCoach!.generate).mockImplementation(
      () => new Promise(() => {}),
    );
    await mount();
    await startCoach();
    await waitFor(() =>
      expect(context.service.shortCoach!.generate).toHaveBeenCalledOnce(),
    );
    // Start a fresh generation under controlled time so its full waiting window is measured.
    fireEvent.click(screen.getByRole("button", { name: "停止等待" }));
    await screen.findByText(/已停止等待/);
    vi.useFakeTimers();
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "生成短句建议" }));
    });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "生成建议" }));
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(30_001);
    });
    expect(screen.getByText(/短句建议生成超时/)).toBeTruthy();
    expect(content().value).toBe(row.comment);
  });
  it.each(["用途", "身份", "来源"])(
    "discards responses after %s changes",
    async (change) => {
      let resolve!: (v: CoachSuggestion) => void;
      vi.mocked(context.service.shortCoach!.generate).mockImplementation(
        () =>
          new Promise((done) => {
            resolve = done;
          }),
      );
      const view = await mount();
      await startCoach();
      await waitFor(() =>
        expect(context.service.shortCoach!.generate).toHaveBeenCalledOnce(),
      );
      const input = vi.mocked(context.service.shortCoach!.generate).mock
        .calls[0][0];
      if (change === "用途")
        fireEvent.click(screen.getByRole("tab", { name: "私信草稿" }));
      else {
        if (change === "身份")
          context = {
            ...context,
            session: { authenticated: true, userId: "OTHER" },
          };
        else {
          context = {
            ...context,
            service: {
              ...context.service,
              opportunity: vi
                .fn()
                .mockResolvedValue({ ...row, sourceEvidenceVersion: "v2" }),
            },
          };
        }
        view.rerender(<OutreachPage />);
      }
      await act(async () => resolve(suggestion(input)));
      expect(
        screen.queryByRole("dialog", { name: "短句建议与当前草稿" }),
      ).toBeNull();
    },
  );
  it("refuses to replace from a changed or revoked source at application time", async () => {
    await mount();
    await startCoach();
    await screen.findByRole("dialog", { name: "短句建议与当前草稿" });
    vi.mocked(context.service.opportunity).mockResolvedValue({
      ...row,
      sourceEvidenceVersion: "v2",
    });
    fireEvent.click(screen.getByRole("button", { name: "核对并替换当前草稿" }));
    await screen.findAllByText(/原文或画像版本已变化/);
    expect(content().value).toBe(row.comment);
  });
  it("does not apply a suggestion after its expiry and retains the current text", async () => {
    await mount();
    await startCoach();
    await screen.findByRole("dialog", { name: "短句建议与当前草稿" });
    const time = Date.now();
    vi.spyOn(Date, "now").mockReturnValue(time + 120_000);
    fireEvent.click(screen.getByRole("button", { name: "核对并替换当前草稿" }));
    await screen.findByText(/短句建议已过期/);
    expect(content().value).toBe(row.comment);
    expect(context.service.opportunity).toHaveBeenCalledOnce();
  });
  it("keeps customer text and gives a retryable error when structured generation fails", async () => {
    vi.mocked(context.service.shortCoach!.generate).mockRejectedValue(
      new Error("TEST短句服务失败"),
    );
    await mount();
    fireEvent.change(content(), { target: { value: "TEST需要保留的编辑" } });
    await startCoach();
    await screen.findByText("TEST短句服务失败");
    expect(content().value).toBe("TEST需要保留的编辑");
    expect(
      screen.queryByRole("dialog", { name: "短句建议与当前草稿" }),
    ).toBeNull();
  });
  it("requires another comparison when the user edits during evidence recheck", async () => {
    await mount();
    await startCoach();
    await screen.findByRole("dialog", { name: "短句建议与当前草稿" });
    let resolve!: (v: typeof row) => void;
    vi.mocked(context.service.opportunity).mockImplementation(
      () =>
        new Promise((done) => {
          resolve = done;
        }),
    );
    fireEvent.click(screen.getByRole("button", { name: "核对并替换当前草稿" }));
    await waitFor(() =>
      expect(context.service.opportunity).toHaveBeenCalledTimes(2),
    );
    fireEvent.change(content(), { target: { value: "TEST核对时人工补充" } });
    await act(async () => resolve(row));
    await screen.findAllByText(/核对期间你又修改了草稿/);
    expect(content().value).toBe("TEST核对时人工补充");
  });
  it("keeps public samples read-only and copying does not call a coach or save service", async () => {
    context.route = parseRoute("#/outreach?opportunity=sample");
    render(<OutreachPage />);
    await screen.findByRole("button", { name: "查看建议依据" });
    expect(content().readOnly).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "复制联系草稿" }));
    await waitFor(() => expect(context.service.copy).toHaveBeenCalledOnce());
    expect(context.service.shortCoach!.generate).not.toHaveBeenCalled();
    expect(context.service.contactDrafts!.save).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "查看建议依据" }));
    await screen.findByRole("dialog", { name: "公开样例的原文依据" });
  });
  it("retains only the applied checks through saving, then removes them after editing even when text is restored", async () => {
    await mount();
    await startCoach();
    await screen.findByRole("dialog", { name: "短句建议与当前草稿" });
    fireEvent.click(screen.getByRole("button", { name: "核对并替换当前草稿" }));
    await screen.findByRole("region", { name: "已采用建议检查" });
    fireEvent.click(screen.getByRole("button", { name: "查看建议依据" }));
    const evidence = await screen.findByRole("dialog", {
      name: "已采用短句的建议依据",
    });
    expect(within(evidence).getByText(row.excerpt)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "返回草稿" }));
    fireEvent.click(screen.getByRole("button", { name: "保存草稿" }));
    await waitFor(() =>
      expect(context.notify).toHaveBeenCalledWith(
        "原草稿保存已确认完成，请核对当前内容。",
        "success",
      ),
    );
    expect(screen.getByRole("region", { name: "已采用建议检查" })).toBeTruthy();
    const adopted = content().value;
    fireEvent.change(content(), {
      target: { value: adopted + "TEST人工修改" },
    });
    expect(screen.queryByRole("region", { name: "已采用建议检查" })).toBeNull();
    fireEvent.change(content(), { target: { value: adopted } });
    expect(screen.queryByRole("region", { name: "已采用建议检查" })).toBeNull();
  });
  it.each(["purpose", "channel", "source", "space", "expiry"])(
    "clears adopted checks after %s changes and never resurrects them when switching back",
    async (change) => {
      const view = render(
        <ContactEditor row={row} renderConfirmation={() => null} />,
      );
      await startCoach();
      await screen.findByRole("dialog", { name: "短句建议与当前草稿" });
      fireEvent.click(
        screen.getByRole("button", { name: "核对并替换当前草稿" }),
      );
      await screen.findByRole("region", { name: "已采用建议检查" });
      const originalSession = context.session;
      const clock =
        change === "expiry"
          ? vi.spyOn(Date, "now").mockReturnValue(Date.now() + 120_000)
          : null;
      if (change === "purpose")
        fireEvent.change(screen.getByRole("combobox", { name: "沟通目的" }), {
          target: { value: "materials" },
        });
      else if (change === "channel")
        fireEvent.click(screen.getByRole("tab", { name: "私信草稿" }));
      else {
        if (change === "space")
          context = {
            ...context,
            session: {
              ...context.session,
              accountScope: { id: "OTHER-space", version: 1 },
            },
          };
        view.rerender(
          <ContactEditor
            row={
              change === "source"
                ? { ...row, sourceEvidenceVersion: "v2" }
                : row
            }
            renderConfirmation={() => null}
          />,
        );
      }
      expect(
        screen.queryByRole("region", { name: "已采用建议检查" }),
      ).toBeNull();
      clock?.mockRestore();
      if (change === "purpose")
        fireEvent.change(screen.getByRole("combobox", { name: "沟通目的" }), {
          target: { value: "requirement" },
        });
      else if (change === "channel")
        fireEvent.click(screen.getByRole("tab", { name: "评论草稿" }));
      else {
        context = { ...context, session: originalSession };
        view.rerender(
          <ContactEditor row={row} renderConfirmation={() => null} />,
        );
      }
      expect(
        screen.queryByRole("region", { name: "已采用建议检查" }),
      ).toBeNull();
    },
  );
  it("places routing behind a closed disclosure after the coach and retains its values across collapse", async () => {
    context.service.connections = vi.fn().mockResolvedValue([
      {
        platform: "xhs",
        status: "CONNECTED",
        accountId: "TEST-account",
        accountName: "TEST账号",
        capabilities: ["comment"],
      },
    ]);
    const view = await mount();
    const details = view.container.querySelector<HTMLDetailsElement>(
      "details.contact-routing",
    )!;
    expect(details.open).toBe(false);
    const coach = screen.getByRole("region", { name: "短句教练" });
    expect(
      coach.compareDocumentPosition(details) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    fireEvent.click(details.querySelector("summary")!);
    await screen.findByRole("option", { name: "TEST账号 · xhs" });
    fireEvent.change(screen.getByRole("textbox", { name: "收件对象" }), {
      target: { value: "TEST对象" },
    });
    fireEvent.change(screen.getByRole("combobox", { name: "发送账号" }), {
      target: { value: "TEST-account" },
    });
    expect(details.querySelector("summary")!.textContent).toContain(
      "对象已填写 · 账号已选择",
    );
    fireEvent.click(details.querySelector("summary")!);
    fireEvent.click(details.querySelector("summary")!);
    expect(
      (screen.getByRole("textbox", { name: "收件对象" }) as HTMLInputElement)
        .value,
    ).toBe("TEST对象");
    expect(
      (screen.getByRole("combobox", { name: "发送账号" }) as HTMLSelectElement)
        .value,
    ).toBe("TEST-account");
  });
});
describe("P12 durable draft save recovery", () => {
  it("saves only after the bound receipt and preserves edits made while saving", async () => {
    let resolve!: (v: DraftSaveReceipt) => void;
    vi.mocked(context.service.contactDrafts!.save).mockImplementation(
      () =>
        new Promise((done) => {
          resolve = done;
        }),
    );
    await mount();
    fireEvent.change(content(), { target: { value: "TEST已提交内容" } });
    fireEvent.click(screen.getByRole("button", { name: "保存草稿" }));
    await waitFor(() =>
      expect(context.service.contactDrafts!.save).toHaveBeenCalledOnce(),
    );
    expect(Object.values(stored())).toEqual(["PENDING"]);
    const input = vi.mocked(context.service.contactDrafts!.save).mock
      .calls[0][0];
    fireEvent.change(content(), { target: { value: "TEST保存时继续编辑" } });
    await act(async () => resolve(saved(input)));
    await waitFor(() => expect(stored()).toEqual({}));
    expect(content().value).toBe("TEST保存时继续编辑");
    expect(screen.getByText("本机修改未同步")).toBeTruthy();
  });
  it("keeps the original request across network failure, closing and draft cleanup; query cannot resave", async () => {
    vi.mocked(context.service.contactDrafts!.save).mockRejectedValue(
      new Error("TEST未知结果"),
    );
    const view = await mount();
    fireEvent.click(screen.getByRole("button", { name: "保存草稿" }));
    await screen.findByText("TEST未知结果");
    const input = vi.mocked(context.service.contactDrafts!.save).mock
      .calls[0][0];
    const before = stored();
    view.unmount();
    clearLocalDrafts();
    await mount();
    expect(stored()).toEqual(before);
    expect(
      (screen.getByRole("button", { name: "保存草稿" }) as HTMLButtonElement)
        .disabled,
    ).toBe(true);
    vi.mocked(context.service.contactDrafts!.operation).mockResolvedValue({
      ...saved(input),
      binding: { ...input.binding, requestId: "wrong" },
    });
    fireEvent.click(screen.getByRole("button", { name: "核对原保存请求" }));
    await screen.findByText(/保存回执与原请求不匹配/);
    expect(stored()).toEqual(before);
    vi.mocked(context.service.contactDrafts!.operation).mockResolvedValue(
      saved(input),
    );
    fireEvent.click(screen.getByRole("button", { name: "核对原保存请求" }));
    await waitFor(() => expect(stored()).toEqual({}));
    expect(context.service.contactDrafts!.save).toHaveBeenCalledOnce();
    expect(context.service.contactDrafts!.operation).toHaveBeenLastCalledWith(
      input.binding,
    );
  });
  it("does not dispatch when durable storage fails", async () => {
    await mount();
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    fireEvent.click(screen.getByRole("button", { name: "保存草稿" }));
    await screen.findByText(/操作确认记录暂时无法可靠保存/);
    expect(context.service.contactDrafts!.save).not.toHaveBeenCalled();
  });
  it("times out legacy saving and cannot re-save after reopening or apply late success", async () => {
    context.service.contactDrafts = undefined;
    let resolve!: () => void;
    let started!: () => void;
    const requestStarted = new Promise<void>((done) => {
      started = done;
    });
    vi.mocked(context.service.saveContact).mockImplementation(() => {
      started();
      return new Promise((done) => {
        resolve = done;
      });
    });
    const view = await mount();
    vi.useFakeTimers();
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "保存草稿" }));
      // The real WebCrypto digest must finish before the save timeout begins.
      await requestStarted;
    });
    expect(context.service.saveContact).toHaveBeenCalledOnce();
    expect(Object.values(stored())).toEqual(["PENDING"]);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(29_999);
    });
    expect(screen.queryByText(/原同步接口暂不支持请求核对/)).toBeNull();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2);
    });
    expect(screen.getByText(/原同步接口暂不支持请求核对/)).toBeTruthy();
    expect(Object.values(stored())).toEqual(["PENDING"]);
    await act(async () => resolve());
    expect(context.notify).not.toHaveBeenCalled();
    vi.useRealTimers();
    view.unmount();
    await mount();
    expect(
      (screen.getByRole("button", { name: "保存草稿" }) as HTMLButtonElement)
        .disabled,
    ).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "核对原保存请求" }));
    await screen.findByText(/原同步接口没有保存请求查询能力/);
    expect(context.service.saveContact).toHaveBeenCalledOnce();
  });
  it("settles the original user only and never notifies a new identity", async () => {
    let resolve!: (v: DraftSaveReceipt) => void;
    vi.mocked(context.service.contactDrafts!.save).mockImplementation(
      () =>
        new Promise((done) => {
          resolve = done;
        }),
    );
    const view = await mount();
    const user = context.session.userId!;
    fireEvent.click(screen.getByRole("button", { name: "保存草稿" }));
    await waitFor(() =>
      expect(context.service.contactDrafts!.save).toHaveBeenCalledOnce(),
    );
    const input = vi.mocked(context.service.contactDrafts!.save).mock
      .calls[0][0];
    context = { ...context, session: { authenticated: true, userId: "OTHER" } };
    view.rerender(<OutreachPage />);
    await act(async () => resolve(saved(input)));
    expect(context.notify).not.toHaveBeenCalled();
    expect(stored(user)).toEqual({});
    expect(stored()).toEqual({});
  });
  it("does not show an old space's local draft or notify its late save under the same user", async () => {
    let resolve!: (v: DraftSaveReceipt) => void;
    vi.mocked(context.service.contactDrafts!.save).mockImplementation(
      () =>
        new Promise((done) => {
          resolve = done;
        }),
    );
    const view = await mount();
    fireEvent.change(content(), { target: { value: "TEST旧空间人工内容" } });
    fireEvent.click(screen.getByRole("button", { name: "保存草稿" }));
    await waitFor(() =>
      expect(context.service.contactDrafts!.save).toHaveBeenCalledOnce(),
    );
    const input = vi.mocked(context.service.contactDrafts!.save).mock
      .calls[0][0];
    context = {
      ...context,
      session: {
        ...context.session,
        accountScope: { id: "OTHER-space", version: 1 },
      },
    };
    view.rerender(<OutreachPage />);
    await screen.findByDisplayValue(row.comment);
    await act(async () => resolve(saved(input)));
    await waitFor(() => expect(stored()).toEqual({}));
    expect(context.notify).not.toHaveBeenCalled();
    expect(content().value).toBe(row.comment);
  });
  it.each(["id", "version", "missing"])(
    "does not apply a recovered save from another account scope (%s)",
    async (change) => {
      vi.mocked(context.service.contactDrafts!.save).mockRejectedValue(
        new Error("TEST保存结果未知"),
      );
      const view = await mount();
      fireEvent.change(content(), { target: { value: "TEST原空间保存内容" } });
      fireEvent.click(screen.getByRole("button", { name: "保存草稿" }));
      await screen.findByText("TEST保存结果未知");
      const input = vi.mocked(context.service.contactDrafts!.save).mock
        .calls[0][0];
      view.unmount();
      context = {
        ...context,
        session: {
          ...context.session,
          accountScope:
            change === "missing"
              ? undefined
              : {
                  id: change === "id" ? "OTHER-space" : "TEST-space",
                  version: change === "version" ? 2 : 1,
                },
        },
      };
      vi.mocked(context.service.contactDrafts!.operation).mockResolvedValue(
        saved(input),
      );
      await mount();
      fireEvent.change(content(), {
        target: { value: "TEST当前空间人工内容" },
      });
      fireEvent.click(screen.getByRole("button", { name: "核对原保存请求" }));
      await screen.findByText(/保存快照不属于当前客户空间/);
      expect(stored()).toEqual({});
      expect(content().value).toBe("TEST当前空间人工内容");
      expect(context.notify).not.toHaveBeenCalled();
      expect(context.service.contactDrafts!.save).toHaveBeenCalledOnce();
    },
  );
  it("uses one save request for repeated clicks and remounts old send confirmation after saving", async () => {
    let resolve!: (v: DraftSaveReceipt) => void;
    vi.mocked(context.service.contactDrafts!.save).mockImplementation(
      () =>
        new Promise((done) => {
          resolve = done;
        }),
    );
    const mounted = vi.fn();
    function Confirmation() {
      useEffect(() => {
        mounted();
      }, []);
      return <span>TEST发送核验状态</span>;
    }
    context.route = parseRoute(
      "#/outreach?opportunity=" + row.id + "&confirm=send",
    );
    render(
      <ContactEditor row={row} renderConfirmation={() => <Confirmation />} />,
    );
    expect(mounted).toHaveBeenCalledOnce();
    const button = screen.getByRole("button", { name: "保存草稿" });
    fireEvent.click(button);
    fireEvent.click(button);
    await waitFor(() =>
      expect(context.service.contactDrafts!.save).toHaveBeenCalledOnce(),
    );
    const input = vi.mocked(context.service.contactDrafts!.save).mock
      .calls[0][0];
    await act(async () => resolve(saved(input)));
    await waitFor(() => expect(stored()).toEqual({}));
    await waitFor(() => expect(mounted).toHaveBeenCalledTimes(2));
  });
  it("releases only a confirmed rejection while keeping the manual content", async () => {
    vi.mocked(context.service.contactDrafts!.save).mockRejectedValue(
      new ServiceError("DRAFT_SAVE_REJECTED", "TEST确定拒绝", 409),
    );
    await mount();
    fireEvent.change(content(), { target: { value: "TEST保留人工内容" } });
    fireEvent.click(screen.getByRole("button", { name: "保存草稿" }));
    await screen.findByText("TEST确定拒绝");
    expect(stored()).toEqual({});
    expect(content().value).toBe("TEST保留人工内容");
  });
  it("rejects malformed save ledger keys before any caller can dispatch", async () => {
    function Fixture() {
      const [, set] = useOperationLedger("contact-draft-saves", "TEST-invalid");
      return (
        <button
          onClick={() => {
            expect(() =>
              set({ '["id","comment","request","bad"]': "PENDING" }),
            ).toThrow();
          }}
        >
          validate
        </button>
      );
    }
    render(<Fixture />);
    fireEvent.click(screen.getByRole("button", { name: "validate" }));
    expect(
      localStorage.getItem(
        operationLedgerKey("contact-draft-saves", "TEST-invalid"),
      ),
    ).toBeNull();
  });
});
