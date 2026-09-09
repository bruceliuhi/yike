// @vitest-environment jsdom
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import {
  PlatformIcon,
  PlatformLabel,
} from "../../src/renderer/components/Platform";

afterEach(cleanup);

describe("本地平台品牌资源", () => {
  it.each([
    ["小红书", ["xhs", "XHS", "小红书", "XiaoHongShu", "rednote"]],
    ["抖音", ["douyin", "DouYin", "抖音", "DY"]],
    ["B站", ["bilibili", "BILIBILI", "B站", "b站", "哔哩哔哩"]],
    ["知乎", ["zhihu", "ZhiHu", "知乎"]],
  ])("%s 的常见别名保留相同官方图标与名称", (name, aliases) => {
    const sources = new Set<string>();
    for (const alias of aliases) {
      const view = render(<PlatformLabel platform={alias} />);
      expect(screen.getByText(name)).toBeTruthy();
      const image = view.container.querySelector("img")!;
      expect(image).toBeTruthy();
      expect(image.alt).toBe("");
      expect(image.closest('[aria-hidden="true"]')).toBeTruthy();
      const source = image.getAttribute("src")!;
      expect(source).not.toMatch(/^(?:https?:)?\/\//i);
      sources.add(source);
      view.unmount();
    }
    expect(sources.size).toBe(1);
  });

  it("公开网站使用统一地球图标，未知来源保留原名", () => {
    for (const alias of ["web", "WEB", "公开网站", "Public Web"]) {
      const view = render(<PlatformLabel platform={alias} />);
      expect(screen.getByText("公开网站")).toBeTruthy();
      expect(view.container.querySelector("img")).toBeNull();
      expect(view.container.querySelector("svg")).toBeTruthy();
      view.unmount();
    }
    for (const name of ["某行业协会官网", "TikTok", "constructor"]) {
      const view = render(<PlatformLabel platform={name} />);
      expect(screen.getByText(name)).toBeTruthy();
      expect(view.container.querySelector("img")).toBeNull();
      expect(view.container.querySelector("svg")).toBeTruthy();
      view.unmount();
    }
  });

  it("图标与组合标签支持指定尺寸和独立样式，不重复朗读图标", () => {
    const view = render(
      <PlatformIcon platform="douyin" size={32} className="test-icon" />,
    );
    const icon = view.container.querySelector(".brand-platform-icon")!;
    expect(icon.classList.contains("test-icon")).toBe(true);
    expect(icon.getAttribute("aria-hidden")).toBe("true");
    expect(view.container.querySelector("img")!.width).toBe(32);
    expect(screen.queryByRole("img")).toBeNull();
    view.rerender(<PlatformLabel platform="bilibili" className="test-label" />);
    expect(
      view.container
        .querySelector(".brand-platform-label")!
        .classList.contains("test-label"),
    ).toBe(true);
    expect(view.container.querySelector("img")!.width).toBe(18);
  });
});
