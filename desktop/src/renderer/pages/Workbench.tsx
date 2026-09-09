import { useState } from "react";
import { ArrowRight, CaretRight, Check } from "@phosphor-icons/react";
import { useApp } from "../app/context";
import { useResource } from "../app/hooks";
import { boundedRequest } from "../app/boundedRequest";
import { OpportunityBrief } from "./workbench/OpportunityBrief";
import { TodoQueue } from "./workbench/TodoQueue";
import { isSample } from "./Opportunities";
import type { WorkbenchQueue } from "../services/workbench";
import {
  Badge,
  Button,
  Empty,
  Notice,
  PageHeader,
  ResourceStatus,
  Tabs,
} from "../components/ui";

export function WorkbenchPage() {
  const { service, session, navigate } = useApp();
  const [tab, setTab] = useState("review");
  const deps = [
    service,
    session.userId,
    session.authenticated,
    session.accountScope?.id,
    session.accountScope?.version,
  ];
  const profiles = useResource(
    () =>
      session.authenticated
        ? boundedRequest(() => service.profiles(), {
            timeoutMessage: "业务画像读取超时，请重试。",
          })
        : Promise.resolve([]),
    deps,
  );
  const opportunities = useResource(
    () =>
      session.authenticated
        ? boundedRequest(() => service.opportunities(), {
            timeoutMessage: "客户商机读取超时，请重试。",
          })
        : Promise.resolve([]),
    deps,
  );
  const connections = useResource(
    () =>
      session.authenticated
        ? boundedRequest(() => service.connections(), {
            timeoutMessage: "平台连接读取超时，请重试。",
          })
        : Promise.resolve([]),
    deps,
  );
  const tasks = useResource(
    () =>
      session.authenticated
        ? boundedRequest(() => service.tasks(), {
            timeoutMessage: "任务状态读取超时，请重试。",
          })
        : Promise.resolve([]),
    deps,
  );
  const completed = profiles.data?.some((p) => p.status === "CONFIRMED");
  const customerOpportunities = (opportunities.data || []).filter(
    (row) => !isSample(row),
  );
  const connected = connections.data?.some((c) => c.status === "CONNECTED");
  const steps = [
    {
      title: "完善业务画像",
      status:
        profiles.loading || profiles.error
          ? "待核验"
          : completed
            ? "已确认"
            : "未完成",
      path: "/profile",
      done: completed,
    },
    {
      title: "连接目标平台",
      status:
        connections.loading || connections.error
          ? "待核验"
          : connected
            ? "已连接"
            : "待连接",
      path: "/connections",
      done: connected,
    },
    {
      title: "创建获客任务",
      status:
        tasks.loading || tasks.error
          ? "待核验"
          : tasks.data?.length
            ? "已有任务"
            : "未开始",
      path: "/tasks/new",
      done: !!tasks.data?.length,
    },
  ];
  return (
    <>
      <PageHeader
        title="商机工作台"
        description="把值得处理的机会，放在今天。"
        extra={
          <Button variant="primary" onClick={() => navigate("/tasks/new")}>
            创建获客任务
          </Button>
        }
      />
      <OpportunityBrief
        profiles={profiles.data || []}
        profilesLoading={profiles.loading}
        profilesError={profiles.error}
        onProfilesRetry={profiles.reload}
        connections={connections.data || []}
        connectionsLoading={connections.loading}
        connectionsError={connections.error}
        onConnectionsRetry={connections.reload}
      />
      <details className="workbench-existing">
        <summary>全部待办与准备步骤</summary>
        <div className="onboarding-strip">
          {steps.map((step, i) => (
            <button
              key={step.path}
              onClick={() => navigate(step.path)}
              className="onboarding-step"
            >
              <span
                className={`step-number ${i === 0 || step.done ? "current" : ""}`}
              >
                {step.done ? <Check /> : i + 1}
              </span>
              <span>
                <strong>{step.title}</strong>
                <Badge tone={step.done ? "green" : i === 0 ? "red" : "neutral"}>
                  {step.status}
                </Badge>
              </span>
              {i < 2 && <CaretRight className="step-arrow" />}
            </button>
          ))}
        </div>
        <div className="workbench-columns">
          <section>
            <h2>今日待办</h2>
            <Tabs
              items={[
                { key: "review", label: "待复核" },
                { key: "contact", label: "待联系" },
                { key: "reply", label: "待回复" },
                { key: "followup", label: "待跟进" },
              ]}
              active={tab}
              onChange={setTab}
            />
            {!session.authenticated ? (
              <Empty
                title="登录后查看客户待办"
                description="也可以先准备业务与任务草稿。"
              />
            ) : service.workbench ? (
              <TodoQueue queue={tab as WorkbenchQueue} />
            ) : tab === "contact" ? (
              <>
                <Notice>待联系队列尚未接通，以下为客户空间的商机。</Notice>
                <ResourceStatus
                  loading={opportunities.loading}
                  error={opportunities.error}
                  onRetry={opportunities.reload}
                />
                {!opportunities.loading &&
                  !opportunities.error &&
                  (customerOpportunities.length ? (
                    <div className="todo-list">
                      {customerOpportunities.slice(0, 6).map((o) => (
                        <button
                          key={o.id}
                          onClick={() =>
                            navigate(
                              `/opportunities/${encodeURIComponent(o.id)}`,
                            )
                          }
                        >
                          <span>
                            <strong>{o.title}</strong>
                            <small>{o.buyer}</small>
                          </span>
                          <ArrowRight />
                        </button>
                      ))}
                    </div>
                  ) : (
                    <Empty title="暂无客户商机" />
                  ))}
              </>
            ) : (
              <Empty
                title={
                  tab === "review"
                    ? "待复核队列尚未接通"
                    : tab === "reply"
                      ? "回复回流尚未接通"
                      : "到期提醒尚未接通"
                }
                action={
                  <Button
                    onClick={() =>
                      navigate(
                        tab === "review"
                          ? "/candidates"
                          : tab === "reply"
                            ? "/outreach"
                            : "/followups",
                      )
                    }
                  >
                    {tab === "review"
                      ? "查看原始线索"
                      : tab === "reply"
                        ? "打开触达中心"
                        : "查看跟进记录"}
                  </Button>
                }
              />
            )}
          </section>
          <aside className="usage-path">
            <h2>使用路径</h2>
            <ol>
              {[
                "确认业务画像",
                "发现需求",
                "核对证据",
                "确认联系",
                "记录跟进",
              ].map((label, i) => (
                <li key={label}>
                  <span>{i + 1}</span>
                  {label}
                </li>
              ))}
            </ol>
          </aside>
        </div>
      </details>
      <section className="sample-section">
        <div className="section-heading">
          <h2>公开研究样例</h2>
          <p>样例仅供预览，不计入客户商机。</p>
        </div>
        <button
          className="sample-row"
          onClick={() => navigate("/opportunities/sample")}
        >
          <span>
            <strong>180㎡高交会展区设计搭建预算询价</strong>
            <small>
              湖南省商务厅对外贸易发展处 · 2026-09-08 16:54 · 深圳国际会展中心
            </small>
          </span>
          <Badge tone="orange">待人工复核</Badge>
          <span className="text-link">
            查看样例 <ArrowRight />
          </span>
        </button>
      </section>
    </>
  );
}
