import { describe, it, expect, vi } from "vitest";
import { validatedOperation } from "../src/main/servicePolicy";
import { createTaskFeedService } from "../src/renderer/services/taskFeed";
const id = "11111111-1111-4111-8111-111111111111";
const item = {
  task_id: id,
  run_id: id,
  device_id: id,
  profile_version_id: id,
  strategy_version_id: id,
  start_request_id: id,
  name: "客户需求搜索",
  mode: "once",
  created_at: "2026-09-11T01:00:00Z",
  deadline_at: "2026-09-11T01:10:00Z",
  status: "RUNNING",
  max_records: 20,
  records_used: 2,
  stop_confirmed: false,
  platform_runs: [
    {
      platform_run_id: id,
      platform: "BILIBILI",
      status: "RUNNING",
      execution_generation: 1,
      records_used: 2,
    },
  ],
};
describe("real execution task feed boundary", () => {
  it("maps bounded read-only routes and rejects owner injection or arbitrary paths", () => {
    expect(
      validatedOperation({
        operation: "taskFeed.list",
        payload: { limit: 20, cursor: "abc==" },
      }),
    ).toEqual({
      path: "/api/ui/execution-task-feed?limit=20&cursor=abc%3D%3D",
      method: "GET",
      logout: false,
    });
    expect(
      validatedOperation({
        operation: "taskFeed.get",
        payload: { taskId: id },
      }),
    ).toMatchObject({
      path: `/api/ui/execution-task-feed/${id}`,
      method: "GET",
    });
    for (const payload of [
      { limit: 51 },
      { limit: 0 },
      { tenant_id: "other" },
      { cursor: "x".repeat(1025) },
    ])
      expect(
        validatedOperation({ operation: "taskFeed.list", payload }),
      ).toBeNull();
    expect(
      validatedOperation({
        operation: "taskFeed.get",
        payload: { taskId: "../session" },
      }),
    ).toBeNull();
  });
  it("validates item binding, totals, unique platforms and successful empty pages", async () => {
    const transport = vi
      .fn()
      .mockResolvedValue({
        schema_version: "execution-task-feed-v1",
        items: [item],
        next_cursor: null,
      });
    const api = createTaskFeedService(transport);
    expect((await api.list()).items[0].records_used).toBe(2);
    transport.mockResolvedValue({
      schema_version: "execution-task-feed-v1",
      items: [],
      next_cursor: null,
    });
    expect((await api.list()).items).toEqual([]);
    for (const bad of [
      { ...item, records_used: 0 },
      {
        ...item,
        platform_runs: [...item.platform_runs, ...item.platform_runs],
      },
      { ...item, credential: "private" },
    ]) {
      transport.mockResolvedValue({
        schema_version: "execution-task-feed-v1",
        items: [bad],
        next_cursor: null,
      });
      await expect(api.list()).rejects.toThrow();
    }
    transport.mockResolvedValue({
      schema_version: "execution-task-feed-item-v1",
      item,
    });
    await expect(
      api.get("22222222-2222-4222-8222-222222222222"),
    ).rejects.toThrow();
  });
});
