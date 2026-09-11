"""Read-only, evidence-bounded coverage projection for an existing execution."""
from __future__ import annotations

from datetime import timedelta
import hashlib
import json
from uuid import UUID

from pilot.auth import InvalidPilotToken
from pilot.sessions import PilotSessionRegistry


class SearchCoverageError(ValueError):
    def __init__(self, code, status=409):
        self.code, self.status = code, status
        super().__init__(code)


def _row(cursor):
    value = cursor.fetchone()
    return dict(zip((column.name for column in cursor.description), value)) if value else None


def _instant(value):
    return value.isoformat(timespec="milliseconds")


class SearchCoverageService:
    _KEYS = {"contractVersion", "requestId", "taskId", "profileId", "profileVersion", "expectedScope"}
    _SCOPE_KEYS = {"userId", "accountScopeId", "scopeVersion"}
    _PLATFORMS = {"XIAOHONGSHU": "xhs", "DOUYIN": "douyin", "BILIBILI": "bilibili",
                  "ZHIHU": "zhihu", "PUBLIC_WEB": "web"}

    def __init__(self, database):
        self.database = getattr(database, "database", database)
        self.sessions = PilotSessionRegistry(self.database)

    def _active(self, claims):
        try:
            with self.database.connect() as connection, connection.cursor() as cursor:
                return self.sessions.require_active(cursor, claims)
        except (InvalidPilotToken, PermissionError):
            raise SearchCoverageError("invalid_session", 401) from None

    @classmethod
    def _request(cls, value):
        try:
            if type(value) is not dict or set(value) != cls._KEYS:
                raise ValueError
            scope = value["expectedScope"]
            for key in ("requestId", "taskId", "profileId"):
                if type(value[key]) is not str or len(value[key]) > 128 or str(UUID(value[key])) != value[key]:
                    raise ValueError
            if (type(scope) is not dict or set(scope) != cls._SCOPE_KEYS
                    or type(value["contractVersion"]) is not int or value["contractVersion"] != 1
                    or type(value["profileVersion"]) is not int
                    or not 1 <= value["profileVersion"] <= 9_007_199_254_740_991
                    or type(scope["scopeVersion"]) is not int or scope["scopeVersion"] != 1
                    or any(type(scope[key]) is not str or not scope[key] for key in ("userId", "accountScopeId"))):
                raise ValueError
        except (KeyError, TypeError, ValueError):
            raise SearchCoverageError("invalid_request", 422) from None
        return value

    def query(self, claims, request_dict):
        request = self._request(request_dict)
        tenant = self._active(claims)
        expected = request["expectedScope"]
        if expected != {"userId": claims.user_id, "accountScopeId": tenant, "scopeVersion": 1}:
            raise SearchCoverageError("scope_conflict")
        try:
            with self.database.connect() as connection:
                connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
                connection.execute("SELECT set_config('yike.user_id',%s,true),set_config('yike.tenant_id',%s,true)",
                                   (claims.user_id, tenant))
                with connection.cursor() as cursor:
                    cursor.execute("""
                        SELECT t.task_id,r.run_id,t.profile_version_id,v.version AS profile_version,
                               t.strategy_version_id,s.draft_revision,t.configuration_snapshot,t.created_at,t.deadline_at,
                               t.status,clock_timestamp() AS generated_at
                          FROM pilot_collection_tasks t
                          JOIN pilot_collection_runs r
                            ON r.tenant_id=t.tenant_id AND r.owner_user_id=t.owner_user_id AND r.task_id=t.task_id
                          JOIN business_profile_versions v
                            ON v.tenant_id=t.tenant_id AND v.profile_version_id=t.profile_version_id
                          JOIN pilot_research_strategy_versions s
                            ON s.tenant_id=t.tenant_id AND s.owner_user_id=t.owner_user_id
                           AND s.strategy_version_id=t.strategy_version_id
                         WHERE t.tenant_id=%s AND t.owner_user_id=%s AND t.task_id=%s
                    """, (tenant, claims.user_id, request["taskId"]))
                    task = _row(cursor)
                    if task is None:
                        raise SearchCoverageError("task_not_found", 404)
                    if (str(task["profile_version_id"]) != request["profileId"]
                            or task["profile_version"] != request["profileVersion"]):
                        raise SearchCoverageError("profile_conflict")
                    cursor.execute("""
                        WITH observed AS MATERIALIZED (
                            SELECT o.*,v.content,
                                   row_number() OVER (PARTITION BY o.platform_run_id,o.source_id
                                       ORDER BY o.received_at DESC,o.observation_id) AS source_rank
                              FROM pilot_candidate_observations o
                              JOIN pilot_candidate_versions v
                                ON v.tenant_id=o.tenant_id AND v.owner_user_id=o.owner_user_id
                               AND v.source_id=o.source_id AND v.version_id=o.version_id
                             WHERE o.tenant_id=%s AND o.owner_user_id=%s
                               AND EXISTS (SELECT 1 FROM pilot_collection_platform_runs selected_run
                                    WHERE selected_run.tenant_id=o.tenant_id
                                      AND selected_run.owner_user_id=o.owner_user_id
                                      AND selected_run.platform_run_id=o.platform_run_id
                                      AND selected_run.task_id=%s)
                        )
                        SELECT p.platform_run_id,p.platform,p.status,
                               count(o.observation_id) AS raw_contents,
                               count(DISTINCT o.source_id) AS independent_sources,e.evidence
                          FROM pilot_collection_platform_runs p
                          LEFT JOIN observed o
                            ON o.tenant_id=p.tenant_id AND o.owner_user_id=p.owner_user_id
                           AND o.platform_run_id=p.platform_run_id
                          LEFT JOIN LATERAL (
                              SELECT COALESCE(jsonb_agg(jsonb_build_object(
                                  'id',sample.observation_id,'sourceId',sample.source_id,
                                  'sourceVersionId',sample.version_id,'excerpt',left(sample.content->>'body',4000),
                                  'url',sample.content->>'public_url') ORDER BY sample.received_at DESC,
                                  sample.observation_id),'[]'::jsonb) AS evidence
                                FROM (SELECT * FROM observed selected
                                       WHERE selected.platform_run_id=p.platform_run_id AND selected.source_rank=1
                                       ORDER BY selected.received_at DESC,selected.observation_id LIMIT 20) sample
                          ) e ON true
                         WHERE p.tenant_id=%s AND p.owner_user_id=%s AND p.task_id=%s
                         GROUP BY p.target_order,p.platform_run_id,p.platform,p.status,e.evidence
                         ORDER BY p.target_order
                    """, (tenant, claims.user_id, request["taskId"], tenant, claims.user_id, request["taskId"]))
                    units = [self._unit(task, _row_from(cursor, row)) for row in cursor.fetchall()]
        except SearchCoverageError:
            raise
        except Exception:
            raise SearchCoverageError("coverage_unavailable", 503) from None
        self._active(claims)
        generated = task["generated_at"]
        coverage = self._overall(units)
        stable = json.dumps([str(task["task_id"]), str(task["run_id"]), task["status"],
                             task["profile_version"], task["draft_revision"], units],
                            sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        return {"contractVersion": 1, "requestId": request["requestId"],
                "snapshotId": hashlib.sha256(stable.encode()).hexdigest(), "audience": "CUSTOMER",
                "userId": claims.user_id, "accountScopeId": tenant, "scopeVersion": 1,
                "taskId": str(task["task_id"]), "runId": str(task["run_id"]),
                "profileId": str(task["profile_version_id"]), "profileVersion": task["profile_version"],
                "configurationRevision": task["draft_revision"],
                "window": {"id": "window:" + str(task["run_id"]), "start": _instant(task["created_at"]),
                           "end": _instant(task["deadline_at"]), "timezone": "UTC"},
                "generatedAt": _instant(generated), "expiresAt": _instant(generated + timedelta(seconds=30)),
                "deduplicationVersion": "candidate-source-identity-v1", "coverage": coverage,
                "screening": "UNKNOWN", "units": units, "usage": None}

    @staticmethod
    def _overall(units):
        states = {unit["coverage"] for unit in units}
        if states == {"NOT_STARTED"}: return "NOT_STARTED"
        if states <= {"RUNNING", "NOT_STARTED"} and "RUNNING" in states: return "RUNNING"
        return "PARTIAL"

    def _unit(self, task, row):
        raw, independent = row["raw_contents"], row["independent_sources"]
        if row["status"] == "PENDING" and raw == 0:
            coverage, stop = "NOT_STARTED", "NOT_EXECUTED"
        elif task["deadline_at"] <= task["generated_at"]:
            coverage, stop = "PARTIAL", "LIMIT_REACHED"
        elif row["status"] == "RUNNING":
            coverage, stop = "RUNNING", "NONE"
        else:
            coverage, stop = "PARTIAL", "CANCELED" if row["status"] == "CANCELED" else "UNKNOWN"
        configuration = task["configuration_snapshot"].get("configuration", {})
        keywords = configuration.get("keywords") if type(configuration) is dict else None
        scope = "已确认关键词：" + "、".join(keywords) if isinstance(keywords, list) and keywords else "已确认的平台方向（未记录逐关键词范围）"
        evidence = [{key: str(value) if key in ("id", "sourceId", "sourceVersionId") else value
                     for key, value in item.items()} for item in row["evidence"][:20]]
        return {"id": str(row["platform_run_id"]), "platform": self._PLATFORMS[row["platform"]],
                "direction": f'{self._PLATFORMS[row["platform"]]} 平台已确认方向', "scope": scope,
                "coverage": coverage, "screening": "UNKNOWN", "stopReason": stop,
                "explanation": "仅统计本授权窗口已持久化的上传观察；窗口不是实际在线时长，未记录逐关键词或页码结束凭证。",
                "unchecked": ["未记录逐关键词、页码及平台结果穷尽凭证"],
                "counts": {"requests": None, "rawContents": raw, "duplicates": raw-independent,
                           "independentSources": independent, "newCandidates": None,
                           "confirmedOpportunities": None, "pendingReviews": None},
                "countingBasis": "本平台运行 observation_id 条目数及 source_id 去重数；原文示例最多20条。不是平台浏览总量、买方数；筛选统计未知。",
                "exclusions": [], "evidence": evidence, "recovery": "UNKNOWN"}


def _row_from(cursor, value):
    return dict(zip((column.name for column in cursor.description), value))
