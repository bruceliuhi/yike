import { describe, it, expect } from "vitest";
import { parseRoute, safeReturnTo } from "../../src/renderer/domain/routes";
describe("route contracts", () => {
  it("resolves all 20 design IDs to semantic routes without injecting records", () => {
    for (let i = 1; i <= 20; i++) {
      const id = `P${String(i).padStart(2, "0")}`;
      const route = parseRoute("#" + id);
      expect(route.page).toBe(id);
      expect(route.path.startsWith("/")).toBe(true);
    }
  });
  it("does not crash on malformed or unrecognized fragments", () => {
    for (const route of [
      "#//[",
      "#/%E0%A4%A",
      "#/unknown",
      "#https://other.example",
    ])
      expect(() => parseRoute(route)).not.toThrow();
    expect(parseRoute("#/unknown").page).toBe("UNKNOWN");
  });
  it("keeps platform return paths inside supported local routes", () => {
    expect(safeReturnTo("/tasks/new?step=connect")).toBe(
      "/tasks/new?step=connect",
    );
    expect(safeReturnTo("https://evil.example")).toBe("/connections");
    expect(safeReturnTo("//evil.example")).toBe("/connections");
  });
});
