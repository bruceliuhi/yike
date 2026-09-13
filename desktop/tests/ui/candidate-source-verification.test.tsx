// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import "@testing-library/jest-dom/vitest";
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
} from "@testing-library/react";
import { CandidateSourceVerification } from "../../src/renderer/pages/opportunities/CandidateSourceVerification";
import {
  parseCandidateReviewResult,
  sourceVerificationRequestSchema,
  type CandidateSourceVerificationDto,
  type SourceVerificationRequest,
} from "../../src/shared/candidateReviewApi";
import {
  candidateBinding,
  verificationFixture,
} from "../fixtures/candidateReviewApi";

afterEach(cleanup);
const checkbox = () =>
  screen.getByRole("checkbox", { name: /我已亲自核对/ }) as HTMLInputElement;
const save = () =>
  screen.getByRole("button", { name: "保存来源核验" }) as HTMLButtonElement;
const field = (name: string) => screen.getByLabelText(name) as HTMLInputElement;
function fill() {
  fireEvent.change(field("定位描述"), {
    target: { value: "平台内检索标题，第二条评论" },
  });
  fireEvent.change(field("原文逐字摘录"), {
    target: { value: "  需要设备报价\n请联系  " },
  });
}
function receipt() {
  return parseCandidateReviewResult(verificationFixture(), {
    requestId: "TEST.verify:1",
  }) as CandidateSourceVerificationDto;
}

describe("candidate human source verification", () => {
  it("keeps human verification facts without record identifiers", () => {
    const verification = receipt();
    render(<CandidateSourceVerification binding={candidateBinding} verification={verification} onSubmit={vi.fn()} />);
    expect(screen.getByText(verification.checkedBy)).toBeVisible();
    expect(screen.getByText(verification.checkedAt)).toBeVisible();
    expect(screen.getByText(verification.excerpt, { normalizer: text => text })).toBeVisible();
    expect(screen.queryByText(verification.id)).toBeNull();
    expect(screen.queryByText(verification.requestId)).toBeNull();
    expect(screen.queryByText("查看核验记录绑定")).toBeNull();
    expect(screen.queryByText("本次核验绑定（当前版本）")).toBeNull();
  });
  it("collects optional person/date proof, clears confirmation on edits and resets with identity", async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    const view = render(<CandidateSourceVerification binding={candidateBinding} allowDemandEvidence onSubmit={onSubmit} />);
    fill();
    fireEvent.change(field("来源状态"), {target:{value:"OPEN"}});
    fireEvent.click(screen.getByRole("checkbox", {name:"确认需求发言人和时间"}));
    for (const [name,value] of Object.entries({"需求作者定位":"TEST采购人，第2楼", "原文作者标记":"TEST采购人",
      "本人需求摘录":"采购输送设备", "需求日期":"2026-09-10", "原文时间表示":"2026年9月10日"})) {
      fireEvent.change(field(name), {target:{value}});
    }
    fireEvent.click(checkbox());
    fireEvent.change(field("需求作者定位"), {target:{value:"TEST采购人，第3楼"}});
    expect(checkbox().checked).toBe(false);
    expect(onSubmit).not.toHaveBeenCalled();
    fireEvent.click(checkbox());
    await act(async () => fireEvent.click(save()));
    expect(onSubmit).toHaveBeenCalledOnce();
    expect(onSubmit.mock.calls[0][0].demandEvidence).toEqual({schemaVersion:"human-demand-evidence-v1",
      authorLocator:"TEST采购人，第3楼",authorExcerpt:"TEST采购人",demandExcerpt:"采购输送设备",
      publishedDate:"2026-09-10",dateExcerpt:"2026年9月10日"});
    view.rerender(<CandidateSourceVerification binding={{...candidateBinding,candidateRevision:3}} allowDemandEvidence onSubmit={onSubmit} />);
    expect(screen.queryByLabelText("本人需求摘录")).toBeNull();
    expect(checkbox().checked).toBe(false);
  });

  it("requires explicit confirmation and save; never pre-fills or submits inferred source facts", async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    render(
      <CandidateSourceVerification
        binding={candidateBinding}
        verification={receipt()}
        onSubmit={onSubmit}
      />,
    );
    expect(field("来源状态").value).toBe("UNVERIFIED");
    expect(field("打开方式").value).toBe("DIRECT");
    expect(field("联系路径").value).toBe("NONE");
    expect(field("定位描述").value).toBe("");
    expect(field("原文逐字摘录").value).toBe("");
    expect(checkbox().checked).toBe(false);
    fill();
    fireEvent.click(save());
    expect(onSubmit).not.toHaveBeenCalled();
    fireEvent.click(checkbox());
    expect(onSubmit).not.toHaveBeenCalled();
    await act(async () => fireEvent.click(save()));
    expect(onSubmit).toHaveBeenCalledTimes(1);
    expect(onSubmit.mock.calls[0][0]).toEqual({
      ...candidateBinding,
      requestId: expect.stringMatching(/^[0-9a-f-]{36}$/),
      humanConfirmed: true,
      status: "UNVERIFIED",
      openingMethod: "DIRECT",
      locator: "平台内检索标题，第二条评论",
      excerpt: "  需要设备报价\n请联系  ",
      contactMethod: "NONE",
    });
    expect(
      sourceVerificationRequestSchema.safeParse(onSubmit.mock.calls[0][0])
        .success,
    ).toBe(true);
    expect(checkbox().checked).toBe(false);
    expect(screen.getByText(/不是平台验证或发送授权/)).toBeTruthy();
  });

  it.each(["来源状态", "打开方式", "联系路径", "定位描述", "原文逐字摘录"])(
    "changing %s resets confirmation and notifies the owner",
    (name) => {
      const onChange = vi.fn();
      render(
        <CandidateSourceVerification
          binding={candidateBinding}
          onSubmit={vi.fn()}
          onChange={onChange}
        />,
      );
      fill();
      fireEvent.click(checkbox());
      const values: Record<string, string> = {
        来源状态: "OPEN",
        打开方式: "IN_PLATFORM",
        联系路径: "COMMENT",
        定位描述: "新定位",
        原文逐字摘录: "新摘录",
      };
      onChange.mockClear();
      fireEvent.change(field(name), { target: { value: values[name] } });
      expect(checkbox().checked).toBe(false);
      expect(save().disabled).toBe(true);
      expect(onChange).toHaveBeenCalledTimes(1);
    },
  );

  it.each(["OPEN", "BLOCKED", "EXPIRED", "UNVERIFIED"])(
    "permits explicitly recorded %s without conferring inclusion permission",
    async (status) => {
      const onSubmit = vi.fn().mockResolvedValue(undefined);
      render(
        <CandidateSourceVerification
          binding={candidateBinding}
          onSubmit={onSubmit}
        />,
      );
      fill();
      fireEvent.change(field("来源状态"), { target: { value: status } });
      fireEvent.change(field("打开方式"), { target: { value: "IN_PLATFORM" } });
      fireEvent.click(checkbox());
      await act(async () => fireEvent.click(save()));
      expect(onSubmit.mock.calls[0][0].status).toBe(status);
    },
  );

  it.each(["", " \n ", "x".repeat(2001), "secret\0raw", "\ud800"])(
    "rejects invalid human text without echoing it",
    async (value) => {
      const onSubmit = vi.fn();
      render(
        <CandidateSourceVerification
          binding={candidateBinding}
          onSubmit={onSubmit}
        />,
      );
      fill();
      fireEvent.change(field("原文逐字摘录"), { target: { value } });
      fireEvent.click(checkbox());
      await act(async () => fireEvent.click(save()));
      expect(onSubmit).not.toHaveBeenCalled();
      expect(screen.getByRole("alert").textContent).toBe(
        "请填写有效的定位描述和原文逐字摘录（各不超过 2000 字），并确认当前核验信息。",
      );
    },
  );

  it("shows current receipt identity and full binding, but marks mismatched receipts stale", () => {
    const verification = receipt();
    const view = render(
      <CandidateSourceVerification
        binding={candidateBinding}
        verification={verification}
        onSubmit={vi.fn()}
      />,
    );
    expect(screen.getByText("当前版本核验记录")).toBeTruthy();
    expect(screen.getByText(verification.checkedBy)).toBeTruthy();
    expect(screen.getByText(verification.checkedAt)).toBeTruthy();
    expect(screen.queryByText(verification.id)).toBeNull();
    expect(screen.queryByText(candidateBinding.sourceVersionId)).toBeNull();
    view.rerender(
      <CandidateSourceVerification
        binding={{ ...candidateBinding, candidateRevision: 3 }}
        verification={verification}
        onSubmit={vi.fn()}
      />,
    );
    expect(screen.queryByText("当前版本核验记录")).toBeNull();
    expect(screen.getByText(/历史核验记录，与当前版本不匹配/)).toBeTruthy();
  });

  it.each([false, true])(
    "preserves read-only saved request and verbatim source details for stale=%s",
    (stale) => {
      const verification = receipt();
      verification.locator = "  平台内定位\n<em>第二条评论</em>  ";
      verification.excerpt =
        "  <script>alert('source')</script>\n需要设备报价  ";
      const { container } = render(
        <CandidateSourceVerification
          binding={{
            ...candidateBinding,
            candidateRevision: stale ? 3 : candidateBinding.candidateRevision,
          }}
          verification={verification}
          onSubmit={vi.fn()}
        />,
      );
      expect(screen.queryByText(verification.requestId)).toBeNull();
      const locator = screen.getByText(
        (_content, element) =>
          element?.tagName === "DD" &&
          element.textContent === verification.locator,
      );
      const excerpt = screen.getByText(
        (_content, element) =>
          element?.tagName === "DD" &&
          element.textContent === verification.excerpt,
      );
      expect(locator.textContent).toBe(verification.locator);
      expect(excerpt.textContent).toBe(verification.excerpt);
      expect(
        locator.classList.contains("candidate-verification-verbatim"),
      ).toBe(true);
      expect(
        excerpt.classList.contains("candidate-verification-verbatim"),
      ).toBe(true);
      expect(container.querySelector("script, em")).toBeNull();
      expect(field("定位描述").value).toBe("");
      expect(field("原文逐字摘录").value).toBe("");
      expect(checkbox().checked).toBe(false);
    },
  );

  it("locks double submission and all fields while pending", async () => {
    let resolve!: () => void;
    const onSubmit = vi.fn(
      (_request: SourceVerificationRequest) =>
        new Promise<void>((done) => {
          resolve = done;
        }),
    );
    render(
      <CandidateSourceVerification
        binding={candidateBinding}
        onSubmit={onSubmit}
      />,
    );
    fill();
    fireEvent.click(checkbox());
    fireEvent.click(save());
    fireEvent.click(save());
    expect(onSubmit).toHaveBeenCalledTimes(1);
    expect(save().disabled).toBe(true);
    expect(field("定位描述").closest("fieldset")?.disabled).toBe(true);
    await act(async () => resolve());
    fireEvent.click(checkbox());
    await act(async () => {
      fireEvent.click(save());
      resolve();
    });
    expect(onSubmit).toHaveBeenCalledTimes(2);
    expect(onSubmit.mock.calls[0][0].requestId).not.toBe(
      onSubmit.mock.calls[1][0].requestId,
    );
  });

  it("binding changes clear words and confirmation permanently and ignore late rejection", async () => {
    let reject!: (error: Error) => void;
    const onSubmit = vi.fn(
      () =>
        new Promise<void>((_done, fail) => {
          reject = fail;
        }),
    );
    const view = render(
      <CandidateSourceVerification
        binding={candidateBinding}
        onSubmit={onSubmit}
      />,
    );
    fill();
    fireEvent.click(checkbox());
    fireEvent.click(save());
    view.rerender(
      <CandidateSourceVerification
        binding={{ ...candidateBinding, profileVersion: 4 }}
        onSubmit={onSubmit}
      />,
    );
    expect(field("定位描述").value).toBe("");
    expect(checkbox().checked).toBe(false);
    fill();
    fireEvent.click(checkbox());
    await act(async () => reject(new Error("secret server detail")));
    expect(checkbox().checked).toBe(true);
    expect(screen.queryByRole("alert")).toBeNull();
    view.rerender(
      <CandidateSourceVerification
        binding={candidateBinding}
        onSubmit={onSubmit}
      />,
    );
    expect(field("定位描述").value).toBe("");
    expect(checkbox().checked).toBe(false);
  });

  it("disabled is read-only and unsaved edits protect navigation", () => {
    const onSubmit = vi.fn();
    const view = render(
      <CandidateSourceVerification
        binding={candidateBinding}
        onSubmit={onSubmit}
      />,
    );
    const clean = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(clean);
    expect(clean.defaultPrevented).toBe(false);
    fill();
    const dirty = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(dirty);
    expect(dirty.defaultPrevented).toBe(true);
    view.rerender(
      <CandidateSourceVerification
        binding={candidateBinding}
        disabled
        onSubmit={onSubmit}
      />,
    );
    expect(field("定位描述").closest("fieldset")?.disabled).toBe(true);
    fireEvent.click(save());
    expect(onSubmit).not.toHaveBeenCalled();
  });
});
