// @vitest-environment jsdom
import { afterEach, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { AppProvider, useApp } from "../../src/renderer/app/context";
import { OutreachPage } from "../../src/renderer/pages/Outreach";
import { createVisualService } from "./service";
import { referenceRoute } from "./routing";
afterEach(cleanup);
it("routes only the five R3 reference states to explicit public samples", () => {
  expect(referenceRoute("P07", true, "populated")).toBe(
    "/candidates?scope=sample",
  );
  expect(referenceRoute("P10", true, "populated")).toBe(
    "/opportunities?scope=sample",
  );
  expect(referenceRoute("P11", true, "populated")).toBe(
    "/opportunities/sample",
  );
  expect(referenceRoute("P12", true, "populated")).toBe(
    "/outreach?opportunity=sample&channel=comment",
  );
  expect(referenceRoute("P13", true, "populated")).toBe(
    "/outreach?opportunity=sample&channel=comment&confirm=send",
  );
  for (const state of ["error", "loading"])
    expect(referenceRoute("P13", true, state)).toBeUndefined();
  expect(
    referenceRoute("P13", true, "populated", "send-unknown"),
  ).toBeUndefined();
  expect(referenceRoute("P13", false, "populated")).toBeUndefined();
});
function ReadyOutreach() {
  return useApp().sessionReady ? <OutreachPage /> : null;
}
it("the actual P13 reference route cannot verify, write or send a public sample", async () => {
  history.replaceState(
    null,
    "",
    "#" + referenceRoute("P13", true, "populated"),
  );
  const h = createVisualService();
  render(
    <AppProvider service={h.service}>
      <ReadyOutreach />
    </AppProvider>,
  );
  await screen.findByRole("dialog", { name: "确认发送" });
  fireEvent.click(
    screen.getByRole("checkbox", { name: "我已核对联系对象、发送账号和内容" }),
  );
  expect(
    (screen.getByRole("button", { name: "确认并发送" }) as HTMLButtonElement)
      .disabled,
  ).toBe(true);
  expect(
    (screen.getByRole("button", { name: "保存草稿" }) as HTMLButtonElement)
      .disabled,
  ).toBe(true);
  expect(
    (screen.getByRole("textbox", { name: "沟通内容" }) as HTMLTextAreaElement)
      .readOnly,
  ).toBe(true);
  expect(
    h.events.some((e) => /verifyContact|saveContact|send/.test(e.operation)),
  ).toBe(false);
});
