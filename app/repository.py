from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
import hashlib
import json
import sqlite3
from typing import Callable, TYPE_CHECKING
from uuid import uuid4
from zoneinfo import ZoneInfo

if TYPE_CHECKING:
    from app.config import Settings
    from app.model_contract import DraftDecision, ScoreDecision


_PLATFORMS = frozenset(("bili", "dy"))
_COLLECTION_BACKENDS = frozenset(
    ("MEDIACRAWLER_AUTHORIZED", "SIMULATION_ONLY")
)
_COLLECTION_TERMINAL_ERROR_CODES = {
    "BLOCKED_INPUT": frozenset(
        (
            "PLATFORM_AUTH_REQUIRED",
            "PLATFORM_PERMISSION_DENIED",
            "PLATFORM_VERIFICATION_REQUIRED",
            "PLATFORM_RATE_LIMITED",
            "COLLECTION_RUNTIME_MISSING",
            "COLLECTION_RUNTIME_MISMATCH",
        )
    ),
    "FAILED": frozenset(
        (
            "PLATFORM_RESPONSE_CHANGED",
            "COLLECTION_NETWORK_FAILED",
            "COLLECTION_PARSE_FAILED",
            "COLLECTION_PROCESS_FAILED",
            "COLLECTION_OUTPUT_FAILED",
            "SIGNAL_IDENTITY_CONFLICT",
        )
    ),
    "CANCELLED": frozenset(("COLLECTION_CANCELLED",)),
}
_FINAL_DECISIONS = frozenset(
    ("STOP_DISCOVERY", "BLOCKED_INPUT", "PROCEED_TO_V03_REVIEW", "REVISE_MVP")
)
_QUERY_SET = [
    ["B2B 获客困难", ["B2B获客", "企业获客", "销售线索", "怎么找企业客户"]],
    ["销售跟进低效", ["客户跟进", "销售跟进", "CRM自动化", "销售漏斗"]],
    ["AI 销售意图", ["AI销售Agent", "销售智能体", "AI获客", "智能销售助手"]],
    ["Agent 落地需求", ["AI Agent定制", "智能体开发", "Agent企业落地", "企业AI应用"]],
    ["明确业务摩擦", ["线索筛选", "客户不回复", "销售团队效率", "销售自动化"]],
]
_THRESHOLDS = {
    "success": {
        "signals": 300, "reviewed": 100, "reviewed_ab": 40,
        "precision": 0.5, "outreach": 30, "responses": 5,
        "interviews": 2, "quotes": 1, "daily_seconds": 5400,
        "day8_12_signal_median_seconds": 240, "incidents": 0,
    },
    "loss_stop": {
        "reviewed_200_high_intent_lt": 10,
        "outreach_30_valid_responses_lt": 3,
        "outreach_40_interviews": 0,
        "high_intent_20_personalized": 0,
        "consecutive_over_90_minute_days": 3,
        "unsolvable_interview": True,
    },
}
_EMPTY_QUERY_SET_SHA256 = hashlib.sha256(
    json.dumps(_QUERY_SET, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
).hexdigest()
_THRESHOLDS_SHA256 = hashlib.sha256(
    json.dumps(_THRESHOLDS, sort_keys=True, separators=(",", ":")).encode("utf-8")
).hexdigest()
_RUN_PROMPT_VERSION = "DISCOVERY_SCORE_V1+DISCOVERY_DRAFT_V1"
_RUN_SCHEMA_VERSION = "DISCOVERY_SCHEMA_V8+DISCOVERY_SCORE_SCHEMA_V1"


class ActiveRunError(RuntimeError):
    pass


class FinalizedRunError(RuntimeError):
    pass


class SignalIdentityConflict(ValueError):
    pass


class RunRevisionError(ValueError):
    pass


class CollectionDailyLimitError(RuntimeError):
    code = "COLLECTION_DAILY_LIMIT_REACHED"


@dataclass(frozen=True)
class NormalizedSignal:
    platform: str
    body: str
    external_source_id: str | None = None
    source_title: str | None = None
    source_url: str | None = None
    source_author_public_id: str | None = None
    external_comment_id: str | None = None
    parent_comment_id: str | None = None
    parent_body: str | None = None
    comment_url: str | None = None
    normalized_comment_url: str | None = None
    author_public_id: str | None = None
    source_published_at: str | None = None
    published_at: str | None = None
    collected_at: str | None = None
    raw_sha256: str | None = None
    body_sha256: str | None = None
    envelope_sha256: str | None = None
    query_cluster: str | None = None
    query_text: str | None = None
    collection_run_id: str | None = None
    normalizer_version: str | None = None
    verifiable: bool = False


@dataclass(frozen=True)
class ImportResult:
    signal_id: str
    created: bool
    observation_id: str


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _parse_canonical_timestamp(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError("timestamp must be canonical RFC3339 UTC")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as error:
        raise ValueError("timestamp must be canonical RFC3339 UTC") from error
    return parsed.replace(tzinfo=UTC)


class Repository:
    def __init__(
        self, connection: sqlite3.Connection, *, now: Callable[[], datetime] | None = None
    ):
        self.connection = connection
        self._now = now or (lambda: datetime.now(UTC))

    @classmethod
    def from_settings(cls, settings: "Settings") -> "Repository":
        from app.db import connect, migrate

        connection = connect(settings.data_dir / "discovery.sqlite3")
        migrate(connection)
        return cls(connection)

    def create_run(
        self, platforms: list[str], revision_of_run_id: str | None = None
    ) -> str:
        if len(platforms) != 2 or set(platforms) != _PLATFORMS or platforms != ["bili", "dy"]:
            raise ValueError("platform scope must be exactly ['bili', 'dy']")
        if revision_of_run_id is not None:
            parent = self.connection.execute(
                """
                SELECT state, revision_of_run_id
                FROM mvp_runs WHERE mvp_run_id = ?
                """,
                (revision_of_run_id,),
            ).fetchone()
            if parent is None:
                raise RunRevisionError("revision base run does not exist")
            if parent["state"] != "FINALIZED":
                raise RunRevisionError("revision base run must be FINALIZED")
            if parent["revision_of_run_id"] is not None:
                raise RunRevisionError("a revision cannot be revised")
            if self.connection.execute(
                "SELECT 1 FROM mvp_runs WHERE revision_of_run_id = ?",
                (revision_of_run_id,),
            ).fetchone():
                raise RunRevisionError("a base run permits only one revision")

        run_id = str(uuid4())
        started = self._now()
        if started.tzinfo is None:
            started = started.replace(tzinfo=UTC)
        started = started.astimezone(UTC)
        started_at = started.isoformat(timespec="seconds").replace("+00:00", "Z")
        shanghai = ZoneInfo("Asia/Shanghai")
        due_local = datetime.combine(
            started.astimezone(shanghai).date() + timedelta(days=14),
            time(23, 59, 59),
            tzinfo=shanghai,
        )
        due_at = due_local.astimezone(UTC).isoformat(timespec="seconds").replace(
            "+00:00", "Z"
        )
        try:
            with self.connection:
                self.connection.execute(
                    """
                    INSERT INTO mvp_runs (
                        mvp_run_id, revision_of_run_id, state, authorization_basis,
                        platform_scope_json, query_set_sha256, prompt_version,
                        schema_version, thresholds_sha256, started_at, day14_due_at
                    ) VALUES (?, ?, 'ACTIVE', ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        revision_of_run_id,
                        "USER_ATTESTED_PLATFORM_AUTHORIZATION",
                        json.dumps(platforms, separators=(",", ":")),
                        _EMPTY_QUERY_SET_SHA256,
                        _RUN_PROMPT_VERSION,
                        _RUN_SCHEMA_VERSION,
                        _THRESHOLDS_SHA256,
                        started_at,
                        due_at,
                    ),
                )
        except sqlite3.IntegrityError as error:
            if "mvp_runs.state" in str(error):
                raise ActiveRunError("an ACTIVE mvp run already exists") from error
            if "mvp_runs.revision_of_run_id" in str(error):
                raise RunRevisionError("a base run permits only one revision") from error
            if "RUN_REVISION" in str(error):
                raise RunRevisionError(str(error)) from error
            raise
        return run_id

    def _server_timestamp(self) -> str:
        current = self._now()
        if current.tzinfo is None:
            current = current.replace(tzinfo=UTC)
        return current.astimezone(UTC).isoformat(timespec="seconds").replace(
            "+00:00", "Z"
        )

    def _require_open_day14(self, run_id: str) -> str:
        run = self.connection.execute(
            "SELECT state, day14_due_at FROM mvp_runs WHERE mvp_run_id = ?",
            (run_id,),
        ).fetchone()
        if run is None:
            raise KeyError(f"unknown mvp run: {run_id}")
        if run["state"] == "FINALIZED":
            raise FinalizedRunError("FINALIZED_RUN_IMMUTABLE")
        if run["state"] != "ACTIVE":
            raise ValueError(f"mvp run is not active: {run['state']}")
        received_at = self._server_timestamp()
        if received_at > str(run["day14_due_at"]):
            raise ValueError("mvp run is closed after the Day 14 cutoff")
        return received_at

    def import_signal(self, run_id: str, item: NormalizedSignal) -> ImportResult:
        return self.import_signals(run_id, [item])[0]

    def import_signals(
        self, run_id: str, items: list[NormalizedSignal]
    ) -> list[ImportResult]:
        received_at = self._require_open_day14(run_id)
        prepared = [self._prepare_signal(run_id, item, received_at) for item in items]
        results: list[ImportResult] = []
        try:
            with self.connection:
                for item, values in zip(items, prepared, strict=True):
                    results.append(
                        self._import_prepared_signal(
                            run_id, item, received_at, *values
                        )
                    )
        except sqlite3.IntegrityError as error:
            if "FINALIZED_RUN_IMMUTABLE" in str(error):
                raise FinalizedRunError("FINALIZED_RUN_IMMUTABLE") from error
            raise
        return results

    def begin_collection(
        self,
        *,
        run_id: str,
        collection_run_id: str,
        platform: str,
        query_cluster: str,
        query_text: str,
        max_contents: int,
        max_comments_per_content: int,
        started_by: str,
        runtime_lock_sha256: str,
        backend: str = "SIMULATION_ONLY",
    ) -> str:
        if platform not in _PLATFORMS:
            raise ValueError("platform must be one of: bili, dy")
        if not query_cluster.strip() or not query_text.strip():
            raise ValueError("collection query identity is required")
        if (
            type(max_contents) is not int
            or type(max_comments_per_content) is not int
            or not 1 <= max_contents <= 10
            or not 1 <= max_comments_per_content <= 50
        ):
            raise ValueError("collection limit is outside the allowed range")
        if not started_by.strip():
            raise ValueError("collection started_by is required")
        if not _is_sha256(runtime_lock_sha256):
            raise ValueError("collection runtime lock SHA-256 is required")
        if backend not in _COLLECTION_BACKENDS:
            raise ValueError("collection backend is invalid")
        if self.connection.in_transaction:
            raise RuntimeError("cannot begin collection inside a transaction")
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            run = self.connection.execute(
                "SELECT state, platform_scope_json, day14_due_at FROM mvp_runs WHERE mvp_run_id = ?",
                (run_id,),
            ).fetchone()
            if run is None or run["state"] != "ACTIVE":
                raise ValueError("collection requires an ACTIVE mvp run")
            if platform not in json.loads(run["platform_scope_json"]):
                raise ValueError("collection platform is outside the run scope")
            current = self._now()
            if current.tzinfo is None:
                current = current.replace(tzinfo=UTC)
            current = current.astimezone(UTC)
            now = current.isoformat(timespec="seconds").replace("+00:00", "Z")
            if now > str(run["day14_due_at"]):
                raise ValueError("collection is closed after the Day 14 cutoff")
            shanghai = ZoneInfo("Asia/Shanghai")
            local_day = current.astimezone(shanghai).date()
            day_start_local = datetime.combine(local_day, time.min, tzinfo=shanghai)
            day_end_local = day_start_local + timedelta(days=1)
            day_start = day_start_local.astimezone(UTC).isoformat(
                timespec="seconds"
            ).replace("+00:00", "Z")
            day_end = day_end_local.astimezone(UTC).isoformat(
                timespec="seconds"
            ).replace("+00:00", "Z")
            query_count = self.connection.execute(
                """
                SELECT count(*) FROM collection_runs
                WHERE mvp_run_id = ? AND platform = ?
                  AND started_at >= ? AND started_at < ?
                """,
                (run_id, platform, day_start, day_end),
            ).fetchone()[0]
            new_signal_count = self.connection.execute(
                """
                SELECT count(*)
                FROM mvp_run_signals membership
                WHERE membership.mvp_run_id = ?
                  AND membership.added_at >= ? AND membership.added_at < ?
                """,
                (run_id, day_start, day_end),
            ).fetchone()[0]
            if query_count >= 8 or new_signal_count >= 300:
                raise CollectionDailyLimitError(CollectionDailyLimitError.code)
            campaign_id = str(uuid4())
            self.connection.execute(
                """
                INSERT INTO campaigns (
                    campaign_id, mvp_run_id, platform, query_cluster, query_text,
                    max_contents, max_comments_per_content, state, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'ACTIVE', ?)
                """,
                (
                    campaign_id,
                    run_id,
                    platform,
                    query_cluster,
                    query_text,
                    max_contents,
                    max_comments_per_content,
                    now,
                ),
            )
            self.connection.execute(
                """
                INSERT INTO collection_runs (
                    collection_run_id, mvp_run_id, campaign_id, platform,
                    attempt, backend, started_by, runtime_lock_sha256, state, started_at
                ) VALUES (?, ?, ?, ?, 1, ?, ?, ?, 'RUNNING', ?)
                """,
                (
                    collection_run_id,
                    run_id,
                    campaign_id,
                    platform,
                    backend,
                    started_by,
                    runtime_lock_sha256,
                    now,
                ),
            )
        except BaseException:
            self.connection.rollback()
            raise
        else:
            self.connection.commit()
        return campaign_id

    def finish_collection(
        self,
        collection_run_id: str,
        *,
        state: str,
        raw_count: int,
        unique_count: int,
        error_code: str | None,
        output_manifest_sha256: str | None = None,
    ) -> None:
        terminal_states = frozenset(
            ("SUCCEEDED", "SUCCEEDED_NO_DATA", "FAILED", "CANCELLED", "BLOCKED_INPUT")
        )
        if state not in terminal_states:
            raise ValueError("collection terminal state is invalid")
        if (
            not isinstance(raw_count, int)
            or not isinstance(unique_count, int)
            or raw_count < 0
            or unique_count < 0
            or unique_count > raw_count
        ):
            raise ValueError("collection terminal counts are invalid")
        if output_manifest_sha256 is not None and not _is_sha256(
            output_manifest_sha256
        ):
            raise ValueError("collection output manifest SHA-256 is invalid")
        if state == "SUCCEEDED":
            valid = (
                raw_count > 0
                and error_code is None
                and output_manifest_sha256 is not None
            )
        elif state == "SUCCEEDED_NO_DATA":
            valid = (
                raw_count == 0
                and unique_count == 0
                and error_code is None
                and output_manifest_sha256 is not None
            )
        else:
            valid = error_code in _COLLECTION_TERMINAL_ERROR_CODES[state]
        if not valid:
            if state in ("FAILED", "CANCELLED", "BLOCKED_INPUT"):
                raise ValueError("collection terminal error code is invalid")
            raise ValueError("collection terminal evidence is invalid")
        finished_at = self._server_timestamp()
        with self.connection:
            collection = self.connection.execute(
                """
                SELECT run.day14_due_at
                FROM collection_runs collection
                JOIN mvp_runs run ON run.mvp_run_id = collection.mvp_run_id
                WHERE collection.collection_run_id = ?
                """,
                (collection_run_id,),
            ).fetchone()
            if (
                collection is not None
                and finished_at > str(collection["day14_due_at"])
            ):
                raise ValueError("collection is closed after the Day 14 cutoff")
            result = self.connection.execute(
                """
                UPDATE collection_runs
                SET state = ?, finished_at = ?, raw_count = ?, unique_count = ?,
                    error_code = ?, output_manifest_sha256 = ?
                WHERE collection_run_id = ?
                  AND state IN ('WAITING_LOGIN', 'RUNNING', 'IMPORTING')
                  AND finished_at IS NULL
                """,
                (
                    state,
                    finished_at,
                    raw_count,
                    unique_count,
                    error_code,
                    output_manifest_sha256,
                    collection_run_id,
                ),
            )
        if result.rowcount != 1:
            raise KeyError(f"unknown running collection: {collection_run_id}")

    def _prepare_signal(
        self, run_id: str, item: NormalizedSignal, received_at: str
    ) -> tuple[str | None, str, str, str, str, str]:
        if item.platform not in _PLATFORMS:
            raise ValueError("platform must be one of: bili, dy")
        observed_at = item.collected_at or received_at
        try:
            observed_instant = _parse_canonical_timestamp(observed_at)
        except ValueError as error:
            if item.verifiable:
                raise ValueError("VERIFIABLE_PROVENANCE_REQUIRED") from error
            raise
        if item.verifiable:
            required_provenance = (
                item.external_source_id,
                item.source_url,
                item.external_comment_id,
                item.collection_run_id,
                item.query_cluster,
                item.query_text,
                item.raw_sha256,
                item.envelope_sha256,
                item.normalizer_version,
            )
            if any(
                not isinstance(value, str) or not value.strip()
                for value in required_provenance
            ):
                raise ValueError("VERIFIABLE_PROVENANCE_REQUIRED")
            if not _is_sha256(item.raw_sha256) or not _is_sha256(
                item.envelope_sha256
            ):
                raise ValueError("VERIFIABLE_PROVENANCE_REQUIRED")
            collection = self.connection.execute(
                "SELECT collection.platform, collection.runtime_lock_sha256, "
                "collection.state, collection.started_at, collection.finished_at, "
                "campaign.query_cluster, campaign.query_text "
                "FROM collection_runs collection "
                "JOIN campaigns campaign ON campaign.campaign_id = collection.campaign_id "
                "AND campaign.mvp_run_id = collection.mvp_run_id "
                "AND campaign.platform = collection.platform "
                "WHERE collection.collection_run_id = ? AND collection.mvp_run_id = ?",
                (item.collection_run_id, run_id),
            ).fetchone()
            if (
                collection is None
                or collection["platform"] != item.platform
                or collection["state"] not in ("RUNNING", "IMPORTING")
                or collection["finished_at"] is not None
                or collection["query_cluster"] != item.query_cluster
                or collection["query_text"] != item.query_text
                or not _is_sha256(collection["runtime_lock_sha256"])
            ):
                raise ValueError("VERIFIABLE_PROVENANCE_REQUIRED")
            try:
                collection_started = _parse_canonical_timestamp(
                    collection["started_at"]
                )
                received_instant = _parse_canonical_timestamp(received_at)
            except ValueError as error:
                raise ValueError("VERIFIABLE_PROVENANCE_REQUIRED") from error
            if not collection_started <= observed_instant <= received_instant:
                raise ValueError("VERIFIABLE_PROVENANCE_REQUIRED")
        if not item.body or not item.body.strip():
            raise ValueError("signal body is required")
        comment_url = item.normalized_comment_url or item.comment_url
        if not comment_url or not comment_url.strip():
            raise ValueError("normalized comment URL is required")
        comment_url = comment_url.strip()
        if not item.author_public_id or not item.author_public_id.strip():
            raise ValueError("author public ID is required")
        author_public_id = item.author_public_id.strip()
        external_comment_id = item.external_comment_id
        if external_comment_id is not None:
            external_comment_id = external_comment_id.strip()
            if not external_comment_id:
                raise ValueError("external comment ID must not be blank")

        run = self.connection.execute(
            "SELECT state, platform_scope_json FROM mvp_runs WHERE mvp_run_id = ?", (run_id,)
        ).fetchone()
        if run is None:
            raise KeyError(f"unknown mvp run: {run_id}")
        if run["state"] == "FINALIZED":
            raise FinalizedRunError("FINALIZED_RUN_IMMUTABLE")
        if run["state"] != "ACTIVE":
            raise ValueError(f"mvp run is not active: {run['state']}")
        if item.platform not in json.loads(run["platform_scope_json"]):
            raise ValueError("signal platform is outside the run scope")

        body_sha256 = _sha256(item.body)
        if item.body_sha256 is not None and item.body_sha256 != body_sha256:
            raise ValueError("signal body SHA-256 does not match body")
        raw_sha256 = item.raw_sha256 or _sha256(item.body)
        return (
            external_comment_id,
            comment_url,
            author_public_id,
            body_sha256,
            raw_sha256,
            observed_at,
        )

    def _import_prepared_signal(
        self,
        run_id: str,
        item: NormalizedSignal,
        received_at: str,
        external_comment_id: str | None,
        comment_url: str,
        author_public_id: str,
        body_sha256: str,
        raw_sha256: str,
        observed_at: str,
    ) -> ImportResult:
        observation_id = str(uuid4())
        source_author_public_id = (
            item.source_author_public_id.strip()
            if item.source_author_public_id and item.source_author_public_id.strip()
            else author_public_id
        )
        source_id = self._resolve_source(item, source_author_public_id)
        signal_id, created = self._resolve_signal(
            item,
            source_id,
            external_comment_id,
            comment_url,
            author_public_id,
            body_sha256,
        )
        self.connection.execute(
            """
            INSERT OR IGNORE INTO mvp_run_signals (mvp_run_id, signal_id, added_at)
            VALUES (?, ?, ?)
            """,
            (run_id, signal_id, received_at),
        )
        self.connection.execute(
            """
            INSERT INTO signal_observations (
                observation_id, mvp_run_id, collection_run_id, signal_id,
                query_cluster, query_text, observed_at, raw_sha256, envelope_sha256
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                observation_id,
                run_id,
                item.collection_run_id,
                signal_id,
                item.query_cluster,
                item.query_text,
                observed_at,
                raw_sha256,
                item.envelope_sha256,
            ),
        )
        return ImportResult(signal_id=signal_id, created=created, observation_id=observation_id)

    def finalize_run(
        self,
        run_id: str,
        decision: str,
        facts: dict[str, object],
        *,
        final_report_sha256: str | None = None,
    ) -> None:
        if decision not in _FINAL_DECISIONS:
            raise ValueError("decision is not a final discovery conclusion")
        facts_json = json.dumps(facts, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        report_json = json.dumps(
            {"conclusion": decision, "facts": json.loads(facts_json)},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )

        def update() -> sqlite3.Cursor:
            return self.connection.execute(
                """
                UPDATE mvp_runs
                SET state = 'FINALIZED', finalized_at = ?, conclusion = ?,
                    conclusion_facts_json = ?, conclusion_facts_sha256 = ?,
                    final_report_sha256 = ?
                WHERE mvp_run_id = ? AND state IN ('ACTIVE', 'CANCELLED')
                """,
                (
                    _utc_now(),
                    decision,
                    facts_json,
                    _sha256(facts_json),
                    final_report_sha256 or _sha256(report_json + "\n"),
                    run_id,
                ),
            )
        if self.connection.in_transaction:
            result = update()
        else:
            with self.connection:
                result = update()
        if result.rowcount != 1:
            raise FinalizedRunError("mvp run is already finalized or not active")

    def cancel_run(self, run_id: str) -> None:
        def update() -> sqlite3.Cursor:
            return self.connection.execute(
                """
                UPDATE mvp_runs SET state = 'CANCELLED'
                WHERE mvp_run_id = ? AND state = 'ACTIVE'
                  AND NOT EXISTS (
                    SELECT 1 FROM collection_runs collection
                    WHERE collection.mvp_run_id = mvp_runs.mvp_run_id
                      AND collection.state IN (
                        'WAITING_LOGIN', 'RUNNING', 'IMPORTING'
                      )
                  )
                """,
                (run_id,),
            )
        if self.connection.in_transaction:
            result = update()
        else:
            with self.connection:
                result = update()
        if result.rowcount != 1:
            raise FinalizedRunError(
                "mvp run is already finalized, not active, or has an active collection"
            )

    def count_signals(self, run_id: str) -> int:
        return self.connection.execute(
            "SELECT COUNT(*) FROM mvp_run_signals WHERE mvp_run_id = ?", (run_id,)
        ).fetchone()[0]

    def count_observations(self, run_id: str) -> int:
        return self.connection.execute(
            "SELECT COUNT(*) FROM signal_observations WHERE mvp_run_id = ?", (run_id,)
        ).fetchone()[0]

    def get_signal_source_text(self, run_id: str, signal_id: str) -> str:
        row = self.connection.execute(
            """
            SELECT sources.title, signals.parent_body, signals.body
            FROM mvp_run_signals
            JOIN signals ON signals.signal_id = mvp_run_signals.signal_id
            LEFT JOIN sources ON sources.source_id = signals.source_id
            WHERE mvp_run_signals.mvp_run_id = ? AND mvp_run_signals.signal_id = ?
            """,
            (run_id, signal_id),
        ).fetchone()
        if row is None:
            raise KeyError(f"unknown signal in mvp run: {signal_id}")
        return "\n".join(value for value in row if value)

    def append_score_failure(
        self,
        *,
        score_run_id: str,
        run_id: str,
        signal_id: str,
        provider: str | None,
        model: str | None,
        prompt_version: str,
        schema_version: str,
        error_code: str,
    ) -> None:
        self._require_open_day14(run_id)
        with self.connection:
            self.connection.execute(
                """
                INSERT INTO score_runs (
                    score_run_id, mvp_run_id, signal_id, provider, model,
                    prompt_version, schema_version, status, error_code, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'FAILED', ?, ?)
                """,
                (
                    score_run_id,
                    run_id,
                    signal_id,
                    provider,
                    model,
                    prompt_version,
                    schema_version,
                    error_code,
                    self._server_timestamp(),
                ),
            )

    def append_score_success(
        self,
        *,
        score_run_id: str,
        run_id: str,
        signal_id: str,
        provider: str,
        model: str,
        prompt_version: str,
        schema_version: str,
        decision: "ScoreDecision",
        token_usage: dict[str, object] | None,
    ) -> None:
        self._require_open_day14(run_id)
        with self.connection:
            self.connection.execute(
                """
                INSERT INTO score_runs (
                    score_run_id, mvp_run_id, signal_id, provider, model,
                    prompt_version, schema_version, dimension_scores_json,
                    total_score, grade, confidence, reason_json, status,
                    token_usage_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'SUCCEEDED', ?, ?)
                """,
                (
                    score_run_id,
                    run_id,
                    signal_id,
                    provider,
                    model,
                    prompt_version,
                    schema_version,
                    json.dumps(
                        decision.dimension_scores.model_dump(),
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                    decision.score,
                    decision.grade,
                    decision.confidence,
                    json.dumps(
                        decision.model_dump(exclude={"dimension_scores"}),
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                    json.dumps(token_usage, sort_keys=True, separators=(",", ":"))
                    if token_usage is not None
                    else None,
                    self._server_timestamp(),
                ),
            )

    def append_draft_failure(
        self,
        *,
        draft_run_id: str,
        run_id: str,
        signal_id: str,
        provider: str | None,
        model: str | None,
        prompt_version: str,
        error_code: str,
    ) -> None:
        self._require_open_day14(run_id)
        with self.connection:
            self.connection.execute(
                """
                INSERT INTO draft_runs (
                    draft_run_id, mvp_run_id, signal_id, provider, model,
                    prompt_version, draft_kind, body, status, error_code, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'GENERATED', NULL, 'FAILED', ?, ?)
                """,
                (
                    draft_run_id,
                    run_id,
                    signal_id,
                    provider,
                    model,
                    prompt_version,
                    error_code,
                    self._server_timestamp(),
                ),
            )

    def append_draft_success(
        self,
        *,
        draft_run_id: str,
        run_id: str,
        signal_id: str,
        provider: str,
        model: str,
        prompt_version: str,
        decision: "DraftDecision",
        token_usage: dict[str, object] | None,
    ) -> None:
        self._require_open_day14(run_id)
        with self.connection:
            self.connection.execute(
                """
                INSERT INTO draft_runs (
                    draft_run_id, mvp_run_id, signal_id, provider, model,
                    prompt_version, draft_kind, body, status, contract_json,
                    token_usage_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'GENERATED', ?, 'SUCCEEDED', ?, ?, ?)
                """,
                (
                    draft_run_id,
                    run_id,
                    signal_id,
                    provider,
                    model,
                    prompt_version,
                    decision.body,
                    json.dumps(
                        decision.model_dump(),
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                    json.dumps(token_usage, sort_keys=True, separators=(",", ":"))
                    if token_usage is not None
                    else None,
                    self._server_timestamp(),
                ),
            )

    def _resolve_source(
        self, item: NormalizedSignal, author_public_id: str
    ) -> str | None:
        if not item.external_source_id:
            return None
        existing = self.connection.execute(
            """
            SELECT source_id, canonical_url, author_public_id
            FROM sources
            WHERE platform = ? AND external_source_id = ?
            """,
            (item.platform, item.external_source_id),
        ).fetchone()
        if existing is not None:
            source_url = item.source_url.strip() if item.source_url else None
            existing_url = existing["canonical_url"]
            existing_author = existing["author_public_id"]
            if item.verifiable and (
                not isinstance(existing_url, str)
                or not existing_url.strip()
                or source_url != existing_url
            ):
                raise ValueError("VERIFIABLE_PROVENANCE_REQUIRED")
            if (
                source_url
                and existing_url
                and source_url != existing_url
                or author_public_id
                and existing_author
                and author_public_id != existing_author
            ):
                raise SignalIdentityConflict("SIGNAL_IDENTITY_CONFLICT")
            return str(existing["source_id"])
        source_id = str(uuid4())
        self.connection.execute(
            """
            INSERT INTO sources (
                source_id, platform, external_source_id, title, canonical_url, author_public_id,
                published_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                source_id,
                item.platform,
                item.external_source_id,
                item.source_title,
                item.source_url,
                author_public_id,
                item.source_published_at,
            ),
        )
        return source_id

    def _resolve_signal(
        self,
        item: NormalizedSignal,
        source_id: str | None,
        external_comment_id: str | None,
        comment_url: str,
        author_public_id: str,
        body_sha256: str,
    ) -> tuple[str, bool]:
        if external_comment_id is not None:
            existing = self.connection.execute(
                """
                SELECT signal_id, source_id, normalized_comment_url,
                       author_public_id, body_sha256
                FROM signals
                WHERE platform = ? AND external_comment_id = ?
                """,
                (item.platform, external_comment_id),
            ).fetchone()
            if existing is not None:
                if (
                    existing["source_id"] != source_id
                    or existing["normalized_comment_url"] != comment_url
                    or existing["author_public_id"] != author_public_id
                    or existing["body_sha256"] != body_sha256
                ):
                    raise SignalIdentityConflict("SIGNAL_IDENTITY_CONFLICT")
                return str(existing["signal_id"]), False
        else:
            existing = self.connection.execute(
                """
                SELECT signal_id FROM signals
                WHERE platform = ? AND normalized_comment_url = ?
                  AND author_public_id = ? AND body_sha256 = ?
                """,
                (item.platform, comment_url, author_public_id, body_sha256),
            ).fetchone()
            if existing is not None:
                return str(existing["signal_id"]), False

        signal_id = str(uuid4())
        self.connection.execute(
            """
            INSERT INTO signals (
                signal_id, source_id, platform, external_comment_id, parent_comment_id,
                parent_body, normalized_comment_url, author_public_id, body, body_sha256,
                published_at, verifiable, normalizer_version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                signal_id,
                source_id,
                item.platform,
                external_comment_id,
                item.parent_comment_id,
                item.parent_body,
                comment_url,
                author_public_id,
                item.body,
                body_sha256,
                item.published_at,
                int(item.verifiable),
                item.normalizer_version,
            ),
        )
        return signal_id, True
