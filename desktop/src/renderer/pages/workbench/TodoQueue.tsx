import { ArrowRight } from "@phosphor-icons/react";
import { useApp } from "../../app/context";
import { boundedRequest } from "../../app/boundedRequest";
import { useResource } from "../../app/hooks";
import { Button, Empty, ResourceStatus } from "../../components/ui";
import {
  taskQueueEmptyCopy,
  type WorkbenchTaskState,
} from "../../domain/workbenchStatus";
import {
  parseWorkbenchSnapshot,
  type WorkbenchQueue,
} from "../../services/workbench";

export function TodoQueue({
  queue,
  taskState = "NO_TASK",
}: {
  queue: WorkbenchQueue;
  taskState?: WorkbenchTaskState;
}) {
  const { service, session, navigate } = useApp();
  const state = useResource(async () => {
    if (!session.authenticated || !session.userId)
      throw new Error("请先登录客户空间。");
    if (!service.workbench) throw new Error("待办服务尚未接通。");
    return parseWorkbenchSnapshot(
      await boundedRequest(() => service.workbench!.queue(queue), {
        timeoutMessage: "待办读取超时，请重试。",
      }),
      queue,
    );
  }, [
    service,
    service.workbench,
    session.userId,
    session.authenticated,
    session.accountScope?.id,
    session.accountScope?.version,
    queue,
  ]);
  const target = (id?: string) => {
    if (queue === "review")
      return "/candidates" + (id ? "?candidate=" + encodeURIComponent(id) : "");
    if (queue === "contact")
      return "/outreach" + (id ? "?opportunity=" + encodeURIComponent(id) : "");
    return (
      "/followups?tab=" +
      (queue === "reply" ? "replies" : "todo") +
      (id ? "&opportunity=" + encodeURIComponent(id) : "")
    );
  };
  return (
    <>
      <ResourceStatus
        loading={state.loading}
        error={state.error}
        onRetry={state.reload}
      />
      {!state.loading &&
        !state.error &&
        state.data &&
        (state.data.items.length ? (
          <>
            <div className="todo-list">
              {state.data.items.slice(0, 6).map((row) => (
                <button
                  key={row.id}
                  onClick={() => navigate(target(row.targetId))}
                >
                  <span>
                    <strong>{row.title}</strong>
                    <small>{row.detail}</small>
                  </span>
                  <ArrowRight />
                </button>
              ))}
            </div>
            {state.data.total > 6 && (
              <Button variant="ghost" onClick={() => navigate(target())}>
                查看全部 {state.data.total} 项
              </Button>
            )}
          </>
        ) : (() => {
          const copy = taskQueueEmptyCopy(taskState);
          return (
            <Empty
              title={copy.title}
              description={copy.description}
              action={
                copy.action ? (
                  <Button onClick={() => navigate("/monitors")}>
                    {copy.action}
                  </Button>
                ) : undefined
              }
            />
          );
        })())}
    </>
  );
}
