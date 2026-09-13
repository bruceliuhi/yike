// @vitest-environment jsdom
import { afterEach, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { StrategySnapshotDetails } from "../../src/renderer/pages/tasks/StrategySnapshotDetails";
import { strategyReceiptSchema, type StrategyReceipt } from "../../src/shared/researchStrategies";

const id = "11111111-1111-4111-8111-111111111111";

function receipt(mode: "once" | "monitor", publicSource = true): StrategyReceipt {
  return strategyReceiptSchema.parse({
    schema_version: "strategy-confirmation-v1",
    operation: "PREPARE",
    draft_id: id,
    draft_revision: 1,
    profile_version_id: id,
    strategy_version_id: id,
    profile_sha256: "a".repeat(64),
    configuration_sha256: "b".repeat(64),
    request_id: id,
    state: "DRAFT",
    recorded_at: "2026-09-11T00:00:00Z",
    snapshot: {
      profile_version_id: id,
      platforms: [publicSource ? "PUBLIC_WEB" : "BILIBILI"],
      max_records: 10,
      max_runtime_seconds: 600,
      strategy_version_id: id,
      configuration: {
        schema_version: "research-strategy-v1",
        name: "公开来源任务",
        source: "search",
        mode,
        keywords: ["采购"],
        exclusions: [],
        links: [],
        schedule: mode === "monitor" ? {
          kind: "interval",
          times: [],
          interval: 6,
          start: "09:00",
          end: "18:00",
          timezone: "Asia/Shanghai",
          policyVersion: 1,
        } : null,
        research: null,
        ...(publicSource ? { publicSource: "v2ex-latest-v1" as const } : {}),
      },
    },
  });
}

afterEach(cleanup);

it("describes public once and monitor snapshots as bounded recent-topic filtering while retaining native keyword search", () => {
  const once = render(<StrategySnapshotDetails receipt={receipt("once")} />);
  expect(screen.getByText("本次近期主题筛选")).toBeTruthy();
  expect(screen.getByText(/V2EX最新主题.*不覆盖历史\/全站\/评论.*本次筛选/)).toBeTruthy();
  expect(screen.queryByText(/不支持持续监控/)).toBeNull();
  once.unmount();

  const monitor = render(<StrategySnapshotDetails receipt={receipt("monitor")} />);
  expect(screen.getByText("近期主题定时抽样")).toBeTruthy();
  expect(screen.getByText(/V2EX最新主题.*不覆盖历史\/全站\/评论.*定时抽样/)).toBeTruthy();
  expect(screen.queryByText(/不支持持续监控/)).toBeNull();
  monitor.unmount();

  render(<StrategySnapshotDetails receipt={receipt("once", false)} />);
  expect(screen.getByText("关键词搜索")).toBeTruthy();
  expect(screen.queryByText(/近期主题/)).toBeNull();
  expect(screen.queryByText(/非当前执行许可/)).toBeNull();
});
it('removes internal identifiers, revisions and timezone codes even inside configuration details',()=>{
 const value=receipt('monitor');
 const {container}=render(<StrategySnapshotDetails receipt={value}/>);
 expect(container.textContent).not.toMatch(/11111111|Asia\/Shanghai|版本|配置摘要|画像摘要|历史回执|原准备请求|v2ex-latest-v1/);
 expect(container.textContent).toContain('09:00–18:00');
 expect(container.textContent).toContain('10 条');
 expect(container.textContent).toContain('600 秒');
});
it('shows bounded project sources, supported old-topic revisit and unread supplements',()=>{
 const value=receipt('once');value.snapshot.configuration.publicSource='v2ex-outsourcing-authors-v1';
 render(<StrategySnapshotDetails receipt={strategyReceiptSchema.parse(value)}/>);
 expect(screen.getByText(/最多3篇；支持的监控可轮流复查已发现旧帖，附言未读，不覆盖全站历史/)).toBeTruthy();
 expect(screen.queryByText(/不覆盖历史\/全站\/评论/)).toBeNull();
});
