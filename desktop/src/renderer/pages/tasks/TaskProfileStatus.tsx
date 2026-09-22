import { useEffect, useMemo, useState } from "react";
import { useApp } from "../../app/context";
import { useResource } from "../../app/hooks";
import { boundedRequest } from "../../app/boundedRequest";
import { Button, Notice } from "../../components/ui";
import type { TaskRun } from "../../domain/models";
import {
  compareTaskProfile,
  parseTaskProfiles,
  taskProfileComparisonKey,
  type TaskProfileComparison,
} from "../../domain/taskProfile";
import "./task-profile.css";

type ProfileVersionStatusNoticeProps = {
  comparison: TaskProfileComparison | null;
  loading: boolean;
  error: string;
  identity: object;
  onNavigate: () => void;
  onReload: () => void;
};

/** Shared customer-facing status for legacy tasks and native monitoring plans. */
export function ProfileVersionStatusNotice({
  comparison,
  loading,
  error,
  identity,
  onNavigate,
  onReload,
}: ProfileVersionStatusNoticeProps) {
  const [acknowledged, setAcknowledged] = useState<{
    identity: object;
    key: string;
  } | null>(null);
  const key = comparison ? taskProfileComparisonKey(comparison) : null;
  useEffect(() => setAcknowledged(null), [identity]);
  useEffect(() => {
    // Acknowledging one observed lineage must not survive a later different or
    // unreadable result, even when the earlier version is returned again.
    if (!loading)
      setAcknowledged((old) =>
        old?.identity === identity && old.key === key ? old : null,
      );
  }, [identity, key, loading]);
  const keeping =
    !!key && acknowledged?.identity === identity && acknowledged.key === key;
  const historical = comparison?.status === "HISTORICAL";
  const hasCurrent = comparison?.status === "CURRENT" || historical;
  const canUpdate = historical || comparison?.status === "NO_CONFIRMED";
  const tone = error
    ? "error"
    : historical && !keeping
      ? "warning"
      : "info";
  return (
    <section className="task-profile-status" aria-label="任务画像版本核对">
      <Notice
        tone={tone}
        action={
          <div className="task-profile-actions">
            {canUpdate && (
              <Button variant="ghost" onClick={onNavigate}>
                去更新
              </Button>
            )}
            {historical && !keeping && (
              <Button
                onClick={() => {
                  if (key) setAcknowledged({ identity, key });
                }}
              >
                保持历史
              </Button>
            )}
            <Button
              variant="ghost"
              disabled={loading}
              onClick={onReload}
            >
              {loading ? "正在核对" : "重新核对"}
            </Button>
          </div>
        }
      >
        {loading ? (
          <p>正在核对任务绑定与当前业务画像。</p>
        ) : error ? (
          <p>当前画像待核对：{error}</p>
        ) : comparison?.status === "UNKNOWN" ? (
          <p>{comparison.reason}</p>
        ) : comparison?.status === "NO_CONFIRMED" ? (
          <>
            <p>该业务画像当前尚未确认，任务仍保留原业务画像。</p>
            <p className="field-hint">请前往业务画像确认。</p>
          </>
        ) : hasCurrent ? (
          <>
            <p>
              {historical
                ? keeping
                  ? "已知悉保留历史：任务仍使用原业务画像。"
                  : "业务画像已有更新：任务仍使用原业务画像。"
                : "任务使用的业务画像与当前已确认画像一致。"}
            </p>
            {historical && (
              <p className="field-hint">
                更新画像后，本任务仍保留原搜索条件。
              </p>
            )}
          </>
        ) : (
          <p>当前画像版本关系待核对。</p>
        )}
      </Notice>
    </section>
  );
}

/** Read-only comparison. These controls never mutate or restart the bound task. */
export function TaskProfileStatus({ run }: { run: TaskRun }) {
  const { service, session, navigate } = useApp();
  const deps = [
    service,
    session.authenticated,
    session.userId,
    session.accountScope?.id,
    session.accountScope?.version,
    run.id,
    run.profileId,
    run.profileVersion,
  ];
  const identity = useMemo(() => ({}), deps);
  const profiles = useResource(async (signal) => {
    if (!session.authenticated || !session.userId)
      throw new Error("登录后可核对当前业务画像。任务绑定不会在此修改。");
    if (!run.profileId || !run.profileVersion) return [];
    if (typeof service.profiles !== "function")
      throw new Error("画像读取服务尚未接通，当前版本关系待核对。");
    return parseTaskProfiles(
      await boundedRequest(() => service.profiles(), {
        signal,
        timeoutMessage: "画像读取超时，当前版本关系待核对。",
      }),
    );
  }, deps);
  const comparison =
    profiles.data === undefined ? null : compareTaskProfile(run, profiles.data);
  return (
    <ProfileVersionStatusNotice
      comparison={comparison}
      loading={profiles.loading}
      error={profiles.error}
      identity={identity}
      onNavigate={() => navigate("/profile")}
      onReload={() => void profiles.reload()}
    />
  );
}
