// @vitest-environment jsdom
import { webcrypto } from "node:crypto";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { AppContextValue } from "../../src/renderer/app/context";
import { clearLocalDrafts } from "../../src/renderer/app/hooks";
import type { DraftSaveInput, DraftSaveReceipt } from "../../src/renderer/domain/shortCoach";
import { parseRoute } from "../../src/renderer/domain/routes";
import { operationLedgerKey } from "../../src/renderer/app/operationLedger";
import { PUBLIC_SAMPLE } from "../../src/renderer/pages/Opportunities";
import { ContactEditor } from "../../src/renderer/pages/outreach/ContactEditor";
import type { YikeService } from "../../src/renderer/services/contracts";

let context: AppContextValue;
vi.mock("../../src/renderer/app/context", () => ({ useApp: () => context }));

const row = {
  ...PUBLIC_SAMPLE,
  id: "TEST-persisted-draft",
  sample: false,
  sourceStatus: "OPEN",
  profileStatus: "CONFIRMED",
  profileVersionId: "profile-v1",
  sourceEvidenceVersion: "source-v1",
  sourceObservedAt: "2026-09-11T00:00:00Z",
  comment: "初始评论",
  dm: "初始私信",
};

function receipt(channel: "comment" | "dm", requestId: string, version = 4): DraftSaveReceipt {
  const content = channel === "comment" ? "云端评论" : "云端私信";
  return {
    binding: { opportunityId: row.id, channel, requestId, contentHash: "a".repeat(64) },
    status: "SUCCEEDED",
    confirmed: true,
    snapshot: {
      accountScope: { id: "space-a", version: 1 },
      profileVersionId: row.profileVersionId,
      sourceEvidenceVersion: row.sourceEvidenceVersion,
      draft: {
        opportunityId: row.id,
        channel,
        content,
        savedContent: content,
        version,
        accountId: "account-a",
        recipient: "recipient-a",
      },
    },
  };
}

const content = () => screen.getByRole("textbox", { name: "沟通内容" }) as HTMLTextAreaElement;

beforeEach(() => {
  vi.stubGlobal("crypto", webcrypto);
  sessionStorage.clear();
  localStorage.clear();
  clearLocalDrafts();
  const latest = vi.fn(async (_id: string, channel: "comment" | "dm") =>
    receipt(channel, channel === "comment" ? "saved-comment" : "saved-dm"),
  );
  context = {
    session: { authenticated: true, userId: crypto.randomUUID(), accountScope: { id: "space-a", version: 1 } },
    route: parseRoute("#/outreach?opportunity=" + row.id),
    navigate: vi.fn(),
    notify: vi.fn(),
    refreshSession: vi.fn(),
    service: {
      connections: vi.fn().mockResolvedValue([{ platform: "xhs", status: "CONNECTED", accountId: "account-a", accountName: "账号A", capabilities: ["comment", "dm"] }]),
      opportunity: vi.fn().mockResolvedValue(row),
      copy: vi.fn(),
      generateContact: vi.fn(),
      saveContact: vi.fn(),
      contactDrafts: { latest, save: vi.fn(), operation: vi.fn() },
    } as unknown as YikeService,
  };
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("ordinary client contact draft persistence", () => {
  it("adopts an external material quote without sending and saves its provenance", async () => {
    const profileVersionId=crypto.randomUUID();
    const source={id:'material-1',profileVersionId,version:4,name:'产品说明',text:'支持产品资料检索。',purpose:'产品介绍',visibility:'external',status:'READY',updatedAt:'2026-09-11T00:00:00Z',extraction:{id:'extract-1',materialVersion:4,fields:{service:'资料检索'},evidence:[{field:'service',quote:'支持产品资料检索。'}]}};
    context.service.materials={list:vi.fn().mockResolvedValue([source,{...source,id:'private',name:'内部成本',visibility:'internal'}])} as never;
    vi.mocked(context.service.contactDrafts!.latest!).mockResolvedValue(null);
    vi.mocked(context.service.contactDrafts!.save).mockImplementation(async input=>({binding:input.binding,snapshot:{...input.snapshot,draft:{...input.snapshot.draft,savedContent:input.snapshot.draft.content}},status:'SUCCEEDED',confirmed:true}));
    render(<ContactEditor row={{...row,profileVersionId}} renderConfirmation={()=>null}/>);
    fireEvent.click(await screen.findByRole('button',{name:'带入资料片段'}));
    expect(content().value).toContain(source.text);
    expect(screen.queryByText('内部成本')).toBeNull();
    expect(context.service.contactDrafts!.save).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button',{name:'保存草稿'}));
    await waitFor(()=>expect(context.service.contactDrafts!.save).toHaveBeenCalledTimes(1));
    const saved=vi.mocked(context.service.contactDrafts!.save).mock.calls[0][0];
    expect(saved.snapshot.draft).toMatchObject({materialReferences:[{sourceProfileVersionId:profileVersionId,materialId:'material-1',materialVersion:4,extractionId:'extract-1',quote:source.text}]});
    await waitFor(()=>expect((screen.getByRole('button',{name:'保存草稿'}) as HTMLButtonElement).disabled).toBe(true));
    fireEvent.click(screen.getByRole('button',{name:'移除引用片段'}));
    expect(content().value).toBe('初始评论\n');
    expect((screen.getByRole('button',{name:'保存草稿'}) as HTMLButtonElement).disabled).toBe(false);
  });

  it("does not use material responses from a previous account", async () => {
    let resolve!:(value:unknown)=>void;
    context.service.materials={list:vi.fn(()=>new Promise(r=>{resolve=r;}))} as never;
    vi.mocked(context.service.contactDrafts!.latest!).mockResolvedValue(null);
    const profileVersionId=crypto.randomUUID();
    const view=render(<ContactEditor row={{...row,profileVersionId}} renderConfirmation={()=>null}/>);
    await waitFor(()=>expect(context.service.materials!.list).toHaveBeenCalled());
    context={...context,session:{...context.session,authenticated:false,userId:'other'}};
    view.rerender(<ContactEditor row={{...row,profileVersionId}} renderConfirmation={()=>null}/>);
    await act(async()=>resolve([{id:'late',profileVersionId,version:4,name:'过期私有资料',text:'旧账号原文',visibility:'external',status:'READY',extraction:{id:'e',materialVersion:4,evidence:[{field:'service',quote:'旧账号原文'}]}}]));
    expect(screen.queryByText('旧账号原文')).toBeNull();
    expect(screen.queryByRole('button',{name:'带入资料片段'})).toBeNull();
  });
  it("does not resave an unchanged restored draft but enables saving after a routing edit", async () => {
    render(<ContactEditor row={row} renderConfirmation={() => null} />);
    await waitFor(() => expect(content().value).toBe("云端评论"));
    const save = screen.getByRole("button", { name: "保存草稿" }) as HTMLButtonElement;
    expect(save.disabled).toBe(true);
    fireEvent.click(save);
    expect(context.service.contactDrafts!.save).not.toHaveBeenCalled();
    fireEvent.change(screen.getByRole("textbox", { name: "收件对象" }), {
      target: { value: "新对象" },
    });
    expect(save.disabled).toBe(false);
  });

  it("restores each channel including routing and advances its own predecessor", async () => {
    vi.mocked(context.service.contactDrafts!.save).mockImplementation(async (input: DraftSaveInput) => ({
      ...receipt(input.binding.channel, input.binding.requestId, input.snapshot.draft.version),
      binding: input.binding,
      snapshot: {
        ...input.snapshot,
        draft: {
          ...input.snapshot.draft,
          savedContent: input.snapshot.draft.content,
        },
      },
    }));
    render(<ContactEditor row={row} renderConfirmation={() => null} />);
    await waitFor(() => expect(content().value).toBe("云端评论"));
    expect((screen.getByRole("textbox", { name: "收件对象" }) as HTMLInputElement).value).toBe("recipient-a");
    fireEvent.change(content(), { target: { value: "评论新修改" } });
    fireEvent.click(screen.getByRole("button", { name: "保存草稿" }));
    await waitFor(() => expect(context.service.contactDrafts!.save).toHaveBeenCalledOnce());
    expect(vi.mocked(context.service.contactDrafts!.save).mock.calls[0][0]).toMatchObject({ previousRequestId: "saved-comment" });

    fireEvent.click(screen.getByRole("tab", { name: "私信草稿" }));
    await waitFor(() => expect(content().value).toBe("云端私信"));
    expect(vi.mocked(context.service.contactDrafts!.latest!).mock.calls.map((call) => call.slice(0, 2))).toEqual([
      [row.id, "comment"],
      [row.id, "dm"],
    ]);
  });

  it("never overwrites typing with a late read and only adopts it explicitly", async () => {
    let resolve!: (value: DraftSaveReceipt | null) => void;
    vi.mocked(context.service.contactDrafts!.latest!).mockImplementation(() => new Promise((done) => { resolve = done; }));
    render(<ContactEditor row={row} renderConfirmation={() => null} />);
    await waitFor(() => expect(context.service.contactDrafts!.latest).toHaveBeenCalledOnce());
    fireEvent.change(content(), { target: { value: "读取期间人工编辑" } });
    await act(async () => resolve(receipt("comment", "late-request")));
    expect(content().value).toBe("读取期间人工编辑");
    fireEvent.click(await screen.findByRole("button", { name: "采用已保存草稿" }));
    expect(content().value).toBe("云端评论");
  });

  it("does not use latest as an implicit predecessor for an old local cache", async () => {
    const key = `yike.ui.draft.v1.contact:${context.session.userId}:${row.id}:${JSON.stringify(context.session.accountScope)}`;
    sessionStorage.setItem(key, JSON.stringify({
      comment: { ...receipt("comment", "ignored").snapshot!.draft, content: "旧本机草稿", savedContent: "旧服务草稿", version: 7 },
      dm: { opportunityId: row.id, channel: "dm", content: row.dm, savedContent: row.dm, version: 1, accountId: "", recipient: "" },
    }));
    render(<ContactEditor row={row} renderConfirmation={() => null} />);
    expect(content().value).toBe("旧本机草稿");
    const adopt = await screen.findByRole("button", { name: "采用已保存草稿" });
    expect((screen.getByRole("button", { name: "保存草稿" }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(adopt);
    expect(content().value).toBe("云端评论");
  });

  it("blocks saving after a failed latest read, allows retry, and does not invent a predecessor", async () => {
    vi.mocked(context.service.contactDrafts!.latest!)
      .mockRejectedValueOnce(new Error("读取失败"))
      .mockResolvedValueOnce(null);
    render(<ContactEditor row={row} renderConfirmation={() => null} />);
    await screen.findByText("读取失败");
    expect((screen.getByRole("button", { name: "保存草稿" }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "重新读取已保存草稿" }));
    await waitFor(() => expect(context.service.contactDrafts!.latest).toHaveBeenCalledTimes(2));
    await waitFor(() => expect((screen.getByRole("button", { name: "保存草稿" }) as HTMLButtonElement).disabled).toBe(false));
  });

  it("discards late reads after account scope or source changes", async () => {
    let resolve!: (value: DraftSaveReceipt | null) => void;
    vi.mocked(context.service.contactDrafts!.latest!).mockImplementation(() => new Promise((done) => { resolve = done; }));
    const view = render(<ContactEditor row={row} renderConfirmation={() => null} />);
    await waitFor(() => expect(context.service.contactDrafts!.latest).toHaveBeenCalledOnce());
    context = { ...context, session: { ...context.session, accountScope: { id: "space-b", version: 1 } } };
    view.rerender(<ContactEditor row={{ ...row, sourceEvidenceVersion: "source-v2" }} renderConfirmation={() => null} />);
    await act(async () => resolve(receipt("comment", "stale-request")));
    expect(content().value).toBe("初始评论");
    expect(screen.queryByRole("button", { name: "采用已保存草稿" })).toBeNull();
  });

  it("keeps edits after UNKNOWN recovery and advances the next version above the saved snapshot", async () => {
    context.service.contactDrafts!.latest = undefined;
    vi.mocked(context.service.contactDrafts!.save)
      .mockRejectedValueOnce(new Error("结果未知"))
      .mockImplementationOnce(async (input) => ({
        binding: input.binding,
        status: "SUCCEEDED",
        confirmed: true,
        snapshot: { ...input.snapshot, draft: { ...input.snapshot.draft, savedContent: input.snapshot.draft.content } },
      }));
    const view = render(<ContactEditor row={row} renderConfirmation={() => null} />);
    for (const value of ["v2", "v3", "v4", "原保存v5"])
      fireEvent.change(content(), { target: { value } });
    fireEvent.click(screen.getByRole("button", { name: "保存草稿" }));
    await screen.findByText("结果未知");
    const original = vi.mocked(context.service.contactDrafts!.save).mock.calls[0][0];
    expect(original.snapshot.draft.version).toBe(5);
    view.unmount();
    clearLocalDrafts();
    render(<ContactEditor row={row} renderConfirmation={() => null} />);
    fireEvent.change(content(), { target: { value: "恢复后人工v2" } });
    vi.mocked(context.service.contactDrafts!.operation).mockResolvedValue({
      binding: original.binding,
      status: "SUCCEEDED",
      confirmed: true,
      snapshot: { ...original.snapshot, draft: { ...original.snapshot.draft, savedContent: original.snapshot.draft.content } },
    });
    fireEvent.click(screen.getByRole("button", { name: "核对原保存请求" }));
    await waitFor(() => expect(context.service.contactDrafts!.operation).toHaveBeenCalledOnce());
    await waitFor(() =>
      expect(JSON.parse(localStorage.getItem(operationLedgerKey("contact-draft-saves", context.session.userId!)) || "{}")).toEqual({}),
    );
    expect(content().value).toBe("恢复后人工v2");
    fireEvent.click(screen.getByRole("button", { name: "保存草稿" }));
    await waitFor(() => expect(context.service.contactDrafts!.save).toHaveBeenCalledTimes(2));
    const next = vi.mocked(context.service.contactDrafts!.save).mock.calls[1][0];
    expect(next.previousRequestId).toBe(original.binding.requestId);
    expect(next.snapshot.draft.version).toBe(6);
  });

  it("adopts the complete successful snapshot when UNKNOWN recovery finds an untouched initial draft", async () => {
    context.service.contactDrafts!.latest = undefined;
    vi.mocked(context.service.contactDrafts!.save).mockRejectedValueOnce(new Error("结果未知"));
    const view = render(<ContactEditor row={row} renderConfirmation={() => null} />);
    for (const value of ["v2", "v3", "v4", "原保存v5"])
      fireEvent.change(content(), { target: { value } });
    fireEvent.change(screen.getByRole("textbox", { name: "收件对象" }), { target: { value: "原对象" } });
    fireEvent.click(screen.getByRole("button", { name: "保存草稿" }));
    await screen.findByText("结果未知");
    const original = vi.mocked(context.service.contactDrafts!.save).mock.calls[0][0];
    view.unmount();
    clearLocalDrafts();
    render(<ContactEditor row={row} renderConfirmation={() => null} />);
    vi.mocked(context.service.contactDrafts!.operation).mockResolvedValue({
      binding: original.binding,
      status: "SUCCEEDED",
      confirmed: true,
      snapshot: { ...original.snapshot, draft: { ...original.snapshot.draft, savedContent: original.snapshot.draft.content } },
    });
    fireEvent.click(screen.getByRole("button", { name: "核对原保存请求" }));
    await waitFor(() => expect(content().value).toBe("原保存v5"));
    expect((screen.getByRole("textbox", { name: "收件对象" }) as HTMLInputElement).value).toBe("原对象");
    expect(JSON.parse(localStorage.getItem(operationLedgerKey("contact-draft-saves", context.session.userId!)) || "{}")).toEqual({});
  });
});
