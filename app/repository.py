from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import hashlib
import json
import sqlite3
from typing import TYPE_CHECKING
from uuid import uuid4

if TYPE_CHECKING:
    from app.config import Settings


_PLATFORMS = frozenset(("bili", "dy"))
_FINAL_DECISIONS = frozenset(
    ("STOP_DISCOVERY", "BLOCKED_INPUT", "PROCEED_TO_V03_REVIEW", "REVISE_MVP")
)


class ActiveRunError(RuntimeError):
    pass


class FinalizedRunError(RuntimeError):
    pass


class SignalIdentityConflict(ValueError):
    pass


class RunRevisionError(ValueError):
    pass


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
    published_at: str | None = None
    collected_at: str | None = None
    raw_sha256: str | None = None
    body_sha256: str | None = None
    envelope_sha256: str | None = None
    query_cluster: str | None = None
    query_text: str | None = None
    collection_run_id: str | None = None
    normalizer_version: str | None = None
    verifiable: bool = True


@dataclass(frozen=True)
class ImportResult:
    signal_id: str
    created: bool
    observation_id: str


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class Repository:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

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
        started_at = _utc_now()
        due_at = (datetime.now(UTC) + timedelta(days=14)).isoformat(timespec="seconds").replace(
            "+00:00", "Z"
        )
        try:
            with self.connection:
                self.connection.execute(
                    """
                    INSERT INTO mvp_runs (
                        mvp_run_id, revision_of_run_id, state, authorization_basis,
                        platform_scope_json, started_at, day14_due_at
                    ) VALUES (?, ?, 'ACTIVE', ?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        revision_of_run_id,
                        "USER_ATTESTED_PLATFORM_AUTHORIZATION",
                        json.dumps(platforms, separators=(",", ":")),
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

    def import_signal(self, run_id: str, item: NormalizedSignal) -> ImportResult:
        return self.import_signals(run_id, [item])[0]

    def import_signals(
        self, run_id: str, items: list[NormalizedSignal]
    ) -> list[ImportResult]:
        prepared = [self._prepare_signal(run_id, item) for item in items]
        results: list[ImportResult] = []
        try:
            with self.connection:
                for item, values in zip(items, prepared, strict=True):
                    results.append(self._import_prepared_signal(run_id, item, *values))
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
    ) -> str:
        if platform not in _PLATFORMS:
            raise ValueError("platform must be one of: bili, dy")
        if not 1 <= max_contents <= 10 or not 1 <= max_comments_per_content <= 50:
            raise ValueError("collection limit is outside the allowed range")
        run = self.connection.execute(
            "SELECT state, platform_scope_json FROM mvp_runs WHERE mvp_run_id = ?",
            (run_id,),
        ).fetchone()
        if run is None or run["state"] != "ACTIVE":
            raise ValueError("collection requires an ACTIVE mvp run")
        if platform not in json.loads(run["platform_scope_json"]):
            raise ValueError("collection platform is outside the run scope")
        campaign_id = str(uuid4())
        now = _utc_now()
        with self.connection:
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
                    attempt, backend, state, started_at
                ) VALUES (?, ?, ?, ?, 1, 'MEDIACRAWLER_AUTHORIZED', 'RUNNING', ?)
                """,
                (collection_run_id, run_id, campaign_id, platform, now),
            )
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
        with self.connection:
            result = self.connection.execute(
                """
                UPDATE collection_runs
                SET state = ?, finished_at = ?, raw_count = ?, unique_count = ?,
                    error_code = ?, output_manifest_sha256 = ?
                WHERE collection_run_id = ?
                """,
                (
                    state,
                    _utc_now(),
                    raw_count,
                    unique_count,
                    error_code,
                    output_manifest_sha256,
                    collection_run_id,
                ),
            )
        if result.rowcount != 1:
            raise KeyError(f"unknown collection run: {collection_run_id}")

    def _prepare_signal(
        self, run_id: str, item: NormalizedSignal
    ) -> tuple[str | None, str, str, str, str, str]:
        if item.platform not in _PLATFORMS:
            raise ValueError("platform must be one of: bili, dy")
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
        observed_at = item.collected_at or _utc_now()
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
            (run_id, signal_id, observed_at),
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

    def finalize_run(self, run_id: str, decision: str, facts: dict[str, object]) -> None:
        if decision not in _FINAL_DECISIONS:
            raise ValueError("decision is not a final discovery conclusion")
        facts_json = json.dumps(facts, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        with self.connection:
            result = self.connection.execute(
                """
                UPDATE mvp_runs
                SET state = 'FINALIZED', finalized_at = ?, conclusion = ?,
                    conclusion_facts_json = ?, conclusion_facts_sha256 = ?
                WHERE mvp_run_id = ? AND state = 'ACTIVE'
                """,
                (_utc_now(), decision, facts_json, _sha256(facts_json), run_id),
            )
        if result.rowcount != 1:
            raise FinalizedRunError("mvp run is already finalized or not active")

    def count_signals(self, run_id: str) -> int:
        return self.connection.execute(
            "SELECT COUNT(*) FROM mvp_run_signals WHERE mvp_run_id = ?", (run_id,)
        ).fetchone()[0]

    def count_observations(self, run_id: str) -> int:
        return self.connection.execute(
            "SELECT COUNT(*) FROM signal_observations WHERE mvp_run_id = ?", (run_id,)
        ).fetchone()[0]

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
                item.published_at,
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
