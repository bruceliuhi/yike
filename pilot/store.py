from __future__ import annotations

import hashlib
import json
from contextlib import contextmanager
from datetime import UTC, datetime
from uuid import uuid4

import psycopg

from pilot.auth import InvalidPilotToken, TokenClaims
from pilot.connection_versions import ConnectionOperationError, MAX_VERSION
from pilot.db import PilotDatabase
from pilot.identity import validate_connection_input, validate_execution_event
from pilot.opportunity_evidence import evidence_view
from pilot.sessions import PilotSessionRegistry


class PilotStore:
    def __init__(self, database: PilotDatabase):
        self.database = database
        self.sessions = PilotSessionRegistry(database)

    def _fetchone(self, tenant_id: str, query: str, params=()):
        with self.database.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT set_config('yike.tenant_id', %s, false)", (tenant_id,))
                cursor.execute(query, params)
                row = cursor.fetchone()
                if row is None:
                    raise KeyError("record not found in tenant")
                columns = [d.name for d in cursor.description]
                return dict(zip(columns, row))

    def provision_tenant(self, name: str) -> str:
        """Provisioning-only operation; never expose through a customer request."""
        tenant_id = str(uuid4())
        with self.database.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT set_config('yike.tenant_id', %s, false)", (tenant_id,))
                cursor.execute("INSERT INTO pilot_tenants(tenant_id, name) VALUES (%s, %s)", (tenant_id, name))
        return tenant_id

    def provision_user(self, tenant_id: str, email: str) -> str:
        """Provisioning-only operation; tenant comes from trusted admin tooling."""
        user_id = str(uuid4())
        with self.database.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT set_config('yike.tenant_id', %s, false)", (tenant_id,))
                cursor.execute("SELECT set_config('yike.user_id', %s, false)", (user_id,))
                cursor.execute("INSERT INTO pilot_users(user_id, tenant_id, email) VALUES (%s, %s, %s)", (user_id, tenant_id, email))
        return user_id

    def _tenant_for_user(self, user_id: str) -> str:
        with self.database.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT set_config('yike.user_id', %s, false)", (user_id,))
                cursor.execute("SELECT tenant_id FROM pilot_users WHERE user_id=%s", (user_id,))
                row = cursor.fetchone()
                if row is None:
                    raise PermissionError("authenticated pilot user is not mapped to a tenant")
                return row[0]

    def save_profile(self, user_id: str, payload: dict) -> dict:
        if not isinstance(payload, dict) or not any(isinstance(value, str) and value.strip() for value in payload.values()):
            raise ValueError("profile description is required")
        tenant_id = self._tenant_for_user(user_id)
        profile_id = self._profile_id(tenant_id)
        content = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(content.encode()).hexdigest()
        with self.database.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT set_config('yike.tenant_id', %s, false)", (tenant_id,))
                cursor.execute("INSERT INTO business_profiles(profile_id, tenant_id) VALUES (%s, %s) ON CONFLICT DO NOTHING", (profile_id, tenant_id))
                cursor.execute("SELECT profile_id FROM business_profiles WHERE tenant_id=%s AND profile_id=%s FOR UPDATE", (tenant_id, profile_id))
                cursor.execute("SELECT profile_version_id, version, status FROM business_profile_versions WHERE tenant_id=%s AND profile_id=%s AND content_sha256=%s", (tenant_id, profile_id, digest))
                existing = cursor.fetchone()
                if existing is not None:
                    return {"profile_id": profile_id, "version_id": existing[0], "version": existing[1], "status": existing[2]}
                cursor.execute("SELECT COALESCE(MAX(version), 0) + 1 FROM business_profile_versions WHERE tenant_id=%s AND profile_id=%s", (tenant_id, profile_id))
                version = cursor.fetchone()[0]
                version_id = str(uuid4())
                cursor.execute(
                    "INSERT INTO business_profile_versions(profile_version_id, tenant_id, profile_id, version, payload, content_sha256) VALUES (%s,%s,%s,%s,%s::jsonb,%s)",
                    (version_id, tenant_id, profile_id, version, content, digest),
                )
        return {"profile_id": profile_id, "version_id": version_id, "version": version, "status": "DRAFT"}

    def confirm_profile(self, user_id: str, version_id: str) -> None:
        tenant_id = self._tenant_for_user(user_id)
        with self.database.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT set_config('yike.tenant_id', %s, false)", (tenant_id,))
                cursor.execute("SELECT profile_id FROM business_profile_versions WHERE tenant_id=%s AND profile_version_id=%s", (tenant_id, version_id))
                profile = cursor.fetchone()
                if profile is None:
                    raise KeyError("draft profile version not found in tenant")
                profile_id = profile[0]
                cursor.execute("SELECT profile_id FROM business_profiles WHERE tenant_id=%s AND profile_id=%s FOR UPDATE", (tenant_id, profile_id))
                cursor.execute("SELECT status FROM business_profile_versions WHERE tenant_id=%s AND profile_version_id=%s FOR UPDATE", (tenant_id, version_id))
                current = cursor.fetchone()
                if current is None:
                    raise KeyError("draft profile version not found in tenant")
                status = current[0]
                if status == "CONFIRMED":
                    return
                if status != "DRAFT":
                    raise ValueError("profile version is not confirmable")
                cursor.execute("UPDATE business_profile_versions SET status='REVOKED' WHERE tenant_id=%s AND profile_id=%s AND status='CONFIRMED'", (tenant_id, profile_id))
                cursor.execute("UPDATE business_profile_versions SET status='CONFIRMED', approved_at=CURRENT_TIMESTAMP WHERE tenant_id=%s AND profile_version_id=%s", (tenant_id, version_id))
                cursor.execute(
                    "INSERT INTO pilot_tasks(task_id, tenant_id, task_key) VALUES (%s,%s,%s) ON CONFLICT (tenant_id, task_key) DO NOTHING",
                    (str(uuid4()), tenant_id, f"research:{version_id}"),
                )

    def get_profile_version(self, user_id: str, version_id: str) -> dict:
        tenant_id = self._tenant_for_user(user_id)
        row = self._fetchone(tenant_id, "SELECT profile_version_id, version, payload, status FROM business_profile_versions WHERE tenant_id=%s AND profile_version_id=%s", (tenant_id, version_id))
        return {"version_id": row["profile_version_id"], "version": row["version"], "payload": row["payload"], "status": row["status"]}

    def import_opportunity(self, user_id: str, profile_version_id: str, import_key: str, data: dict) -> dict:
        tenant_id = self._tenant_for_user(user_id)
        with self.database.connect() as connection:
            return self._import_opportunity(connection, tenant_id, profile_version_id, import_key, data)

    def import_opportunities(self, user_id: str, profile_version_id: str, entries: list[tuple[str, dict]]) -> list[dict]:
        """Persist a reviewed bundle atomically, including source observations."""
        tenant_id = self._tenant_for_user(user_id)
        with self.database.connect() as connection:
            return [
                self._import_opportunity(connection, tenant_id, profile_version_id, key, data)
                for key, data in entries
            ]

    def _import_opportunity(self, connection, tenant_id: str, profile_version_id: str, import_key: str, data: dict) -> dict:
        source_id = str(uuid4())
        opportunity_id = str(uuid4())
        with connection.cursor() as cursor:
            cursor.execute("SELECT set_config('yike.tenant_id', %s, false)", (tenant_id,))
            cursor.execute("SELECT profile_id FROM business_profile_versions WHERE tenant_id=%s AND profile_version_id=%s", (tenant_id, profile_version_id))
            profile_row = cursor.fetchone()
            if profile_row is None:
                raise ValueError("opportunity import requires a confirmed profile version")
            cursor.execute("SELECT profile_id FROM business_profiles WHERE tenant_id=%s AND profile_id=%s FOR UPDATE", (tenant_id, profile_row[0]))
            cursor.execute("SELECT 1 FROM business_profile_versions WHERE tenant_id=%s AND profile_version_id=%s AND status='CONFIRMED'", (tenant_id, profile_version_id))
            if cursor.fetchone() is None:
                raise ValueError("opportunity import requires a confirmed profile version")
            cursor.execute(
                "SELECT o.opportunity_id, o.profile_version_id, s.platform, s.external_id, s.public_url FROM pilot_opportunities o "
                "JOIN pilot_sources s ON s.tenant_id=o.tenant_id AND s.source_id=o.source_id "
                "WHERE o.tenant_id=%s AND o.import_key=%s FOR UPDATE",
                (tenant_id, import_key),
            )
            existing_import = cursor.fetchone()
            if existing_import is not None:
                if existing_import[1] != profile_version_id:
                    raise ValueError("import key conflicts with existing profile")
                if (existing_import[2], existing_import[3]) != (data["source_platform"], data["source_external_id"]):
                    raise ValueError("import key conflicts with existing source")
                if existing_import[4] != data["public_url"]:
                    raise ValueError("source identity conflicts with existing public URL")
                return {"opportunity_id": existing_import[0], "created": False}
            cursor.execute("INSERT INTO pilot_sources(source_id, tenant_id, platform, external_id, public_url, published_at) VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT (tenant_id, platform, external_id) DO NOTHING RETURNING source_id", (source_id, tenant_id, data["source_platform"], data["source_external_id"], data["public_url"], data.get("source_published_at")))
            source = cursor.fetchone()
            if source:
                source_id = source[0]
            else:
                cursor.execute("SELECT source_id, public_url, published_at FROM pilot_sources WHERE tenant_id=%s AND platform=%s AND external_id=%s FOR UPDATE", (tenant_id, data["source_platform"], data["source_external_id"]))
                existing_source = cursor.fetchone()
                source_id = existing_source[0]
                if existing_source[1] != data["public_url"]:
                    raise ValueError("source identity conflicts with existing public URL")
            source_text = json.dumps({"title": data["title"], "excerpt": data.get("public_excerpt", "")}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            source_hash = hashlib.sha256(source_text.encode()).hexdigest()
            source_version_id = str(uuid4())
            cursor.execute("INSERT INTO pilot_source_versions(source_version_id, tenant_id, source_id, content_sha256, title, excerpt) VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT (tenant_id, source_id, content_sha256) DO NOTHING RETURNING source_version_id", (source_version_id, tenant_id, source_id, source_hash, data["title"], data.get("public_excerpt", "")))
            version_row = cursor.fetchone()
            if version_row is not None:
                source_version_id = version_row[0]
            else:
                cursor.execute("SELECT source_version_id FROM pilot_source_versions WHERE tenant_id=%s AND source_id=%s AND content_sha256=%s FOR UPDATE", (tenant_id, source_id, source_hash))
                source_version_id = cursor.fetchone()[0]
            cursor.execute("INSERT INTO pilot_source_observations(observation_id, tenant_id, source_id, source_version_id) VALUES (%s,%s,%s,%s)", (str(uuid4()), tenant_id, source_id, source_version_id))
            cursor.execute(
                "INSERT INTO pilot_opportunities(opportunity_id, tenant_id, profile_version_id, source_id, import_key, title, buyer, summary, contact_path, public_excerpt, match_reason, action_signal, value_judgment, risk, reviewed_by, reviewed_at, draft_comment, draft_dm) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                "ON CONFLICT DO NOTHING RETURNING opportunity_id",
                (
                    opportunity_id, tenant_id, profile_version_id, source_id, import_key,
                    data["title"], data["buyer"], data["summary"], data["contact_path"],
                    data.get("public_excerpt"), data.get("match_reason", ""),
                    data.get("action_signal", ""), data.get("value_judgment", ""),
                    data.get("risk", ""), data.get("reviewed_by", ""), data.get("reviewed_at") or datetime.now(UTC),
                    data["draft_comment"], data["draft_dm"],
                ),
            )
            inserted = cursor.fetchone()
            if inserted is not None:
                return {"opportunity_id": inserted[0], "created": True}
            cursor.execute("SELECT opportunity_id FROM pilot_opportunities WHERE tenant_id=%s AND import_key=%s", (tenant_id, import_key))
            existing = cursor.fetchone()
            if existing is not None:
                return {"opportunity_id": existing[0], "created": False}
            cursor.execute(
                "SELECT opportunity_id FROM pilot_opportunities WHERE tenant_id=%s AND source_id=%s AND profile_version_id=%s",
                (tenant_id, source_id, profile_version_id),
            )
            existing_source = cursor.fetchone()
            if existing_source is not None:
                return {"opportunity_id": existing_source[0], "created": False}
            raise RuntimeError("opportunity insert conflict could not be resolved")

    def list_opportunities(self, user_id: str) -> list[dict]:
        tenant_id = self._tenant_for_user(user_id)
        with self.database.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT set_config('yike.tenant_id', %s, false)", (tenant_id,))
                cursor.execute(
                    "SELECT o.opportunity_id, o.title, o.buyer, o.intent_status, o.source_status, o.summary, o.updated_at, o.public_excerpt, o.match_reason, o.action_signal, o.value_judgment, o.risk, p.status AS profile_status, "
                    "s.platform AS source_platform, s.public_url, s.published_at, "
                    "(SELECT f.status FROM pilot_followups f WHERE f.tenant_id=o.tenant_id AND f.opportunity_id=o.opportunity_id "
                    "ORDER BY f.created_at DESC, f.followup_id DESC LIMIT 1) AS latest_followup_status "
                    "FROM pilot_opportunities o JOIN business_profile_versions p ON p.tenant_id=o.tenant_id AND p.profile_version_id=o.profile_version_id "
                    "JOIN pilot_sources s ON s.tenant_id=o.tenant_id AND s.source_id=o.source_id "
                    "WHERE o.tenant_id=%s ORDER BY o.created_at DESC",
                    (tenant_id,),
                )
                columns = [d.name for d in cursor.description]
                return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def get_opportunity(self, user_id: str, opportunity_id: str) -> dict:
        tenant_id = self._tenant_for_user(user_id)
        row = self._fetchone(
            tenant_id,
            "SELECT o.opportunity_id, o.title, o.buyer, o.summary, o.contact_path, o.public_excerpt, o.match_reason, o.action_signal, o.value_judgment, o.risk, o.reviewed_by, o.reviewed_at, o.profile_version_id, p.status AS profile_status, "
            "o.draft_comment, o.draft_dm, o.source_status, o.intent_status, o.updated_at, s.platform AS source_platform, "
            "s.public_url, s.published_at, e.payload AS source_evidence_payload, e.payload_sha256 AS source_evidence_sha256 FROM pilot_opportunities o "
            "JOIN pilot_sources s ON s.tenant_id=o.tenant_id AND s.source_id=o.source_id "
            "JOIN business_profile_versions p ON p.tenant_id=o.tenant_id AND p.profile_version_id=o.profile_version_id "
            "LEFT JOIN pilot_opportunity_evidence e ON e.tenant_id=o.tenant_id AND e.opportunity_id=o.opportunity_id "
            "WHERE o.tenant_id=%s AND o.opportunity_id=%s",
            (tenant_id, opportunity_id),
        )
        payload = row.pop("source_evidence_payload")
        digest = row.pop("source_evidence_sha256")
        row["source_evidence"] = evidence_view(
            payload, digest, opportunity_id=opportunity_id,
            profile_version_id=row["profile_version_id"],
        )
        return row

    def set_source_status(self, user_id: str, opportunity_id: str, status: str) -> None:
        if status not in {"OPEN", "EXPIRED", "BLOCKED", "UNVERIFIED"}:
            raise ValueError("unsupported source status")
        tenant_id = self._tenant_for_user(user_id)
        with self.database.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT set_config('yike.tenant_id', %s, false)", (tenant_id,))
                cursor.execute(
                    "UPDATE pilot_opportunities SET source_status=%s, updated_at=CURRENT_TIMESTAMP "
                    "WHERE tenant_id=%s AND opportunity_id=%s RETURNING source_id",
                    (status, tenant_id, opportunity_id),
                )
                if cursor.rowcount != 1:
                    raise KeyError("opportunity not found in tenant")
                source_id = cursor.fetchone()[0]
                cursor.execute("UPDATE pilot_sources SET health=%s WHERE tenant_id=%s AND source_id=%s", (status, tenant_id, source_id))
                cursor.execute(
                    "UPDATE pilot_opportunities SET source_status=%s, updated_at=CURRENT_TIMESTAMP "
                    "WHERE tenant_id=%s AND source_id=%s",
                    (status, tenant_id, source_id),
                )

    def record_followup(self, user_id: str, opportunity_id: str, status: str, note: str) -> dict:
        tenant_id = self._tenant_for_user(user_id)
        if status not in {"CONTACTED", "REPLIED", "MEETING", "QUOTED", "LOST", "WON"}:
            raise ValueError("unsupported follow-up status")
        if not note.strip():
            raise ValueError("follow-up note is required")
        followup_id = str(uuid4())
        with self.database.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT set_config('yike.tenant_id', %s, false)", (tenant_id,))
                cursor.execute("SELECT 1 FROM pilot_opportunities WHERE tenant_id=%s AND opportunity_id=%s", (tenant_id, opportunity_id))
                if cursor.fetchone() is None:
                    raise KeyError("opportunity not found in tenant")
                cursor.execute("INSERT INTO pilot_followups(followup_id, tenant_id, opportunity_id, status, note) VALUES (%s,%s,%s,%s,%s)", (followup_id, tenant_id, opportunity_id, status, note))
                intent_status = "CLOSED" if status in {"LOST", "WON"} else "CONTACTED"
                cursor.execute("UPDATE pilot_opportunities SET intent_status=%s, updated_at=CURRENT_TIMESTAMP WHERE tenant_id=%s AND opportunity_id=%s", (intent_status, tenant_id, opportunity_id))
        return {"followup_id": followup_id}

    def list_followups(self, user_id: str, opportunity_id: str) -> list[dict]:
        tenant_id = self._tenant_for_user(user_id)
        with self.database.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT set_config('yike.tenant_id', %s, false)", (tenant_id,))
                cursor.execute("SELECT followup_id, status, note, created_at FROM pilot_followups WHERE tenant_id=%s AND opportunity_id=%s ORDER BY created_at DESC", (tenant_id, opportunity_id))
                columns = [d.name for d in cursor.description]
                return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def list_all_followups(self, user_id: str) -> list[dict]:
        tenant_id = self._tenant_for_user(user_id)
        with self.database.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT set_config('yike.tenant_id', %s, false)", (tenant_id,))
                cursor.execute(
                    "SELECT f.followup_id, f.opportunity_id, o.title, f.status, f.note, f.created_at "
                    "FROM pilot_followups f JOIN pilot_opportunities o ON o.tenant_id=f.tenant_id AND o.opportunity_id=f.opportunity_id "
                    "WHERE f.tenant_id=%s ORDER BY f.created_at DESC",
                    (tenant_id,),
                )
                columns = [d.name for d in cursor.description]
                return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def claim_task(self, user_id: str, task_key: str, lease_owner: str, lease_seconds: int = 300) -> dict | None:
        """Atomically claim a tenant task, returning None when it is unavailable or done."""
        if not task_key.strip() or not lease_owner.strip():
            raise ValueError("task_key and lease_owner are required")
        if not isinstance(lease_seconds, int) or isinstance(lease_seconds, bool) or not 1 <= lease_seconds <= 86_400:
            raise ValueError("lease_seconds must be an integer from 1 to 86400")
        tenant_id = self._tenant_for_user(user_id)
        task_id = str(uuid4())
        with self.database.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT set_config('yike.tenant_id', %s, false)", (tenant_id,))
                cursor.execute(
                    "INSERT INTO pilot_tasks(task_id, tenant_id, task_key) VALUES (%s,%s,%s) "
                    "ON CONFLICT (tenant_id, task_key) DO NOTHING",
                    (task_id, tenant_id, task_key),
                )
                cursor.execute(
                    "UPDATE pilot_tasks SET status='RUNNING', lease_owner=%s, "
                    "lease_until=CURRENT_TIMESTAMP + (%s * INTERVAL '1 second') "
                    "WHERE tenant_id=%s AND task_key=%s AND ("
                    "status IN ('PENDING','FAILED') OR "
                    "(status='RUNNING' AND (lease_until <= CURRENT_TIMESTAMP OR lease_owner=%s))"
                    ") RETURNING task_id, task_key, status, lease_owner, lease_until",
                    (lease_owner, lease_seconds, tenant_id, task_key, lease_owner),
                )
                row = cursor.fetchone()
                if row is None:
                    return None
                columns = [d.name for d in cursor.description]
                return dict(zip(columns, row))

    def complete_task(self, user_id: str, task_key: str, lease_owner: str) -> bool:
        """Mark a currently-held task done; repeated completion is idempotent."""
        if not task_key.strip() or not lease_owner.strip():
            raise ValueError("task_key and lease_owner are required")
        tenant_id = self._tenant_for_user(user_id)
        with self.database.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT set_config('yike.tenant_id', %s, false)", (tenant_id,))
                cursor.execute(
                    "UPDATE pilot_tasks SET status='DONE', lease_until=NULL "
                    "WHERE tenant_id=%s AND task_key=%s AND ((status='DONE' AND lease_owner=%s) OR "
                    "(status='RUNNING' AND lease_owner=%s AND lease_until > CURRENT_TIMESTAMP))",
                    (tenant_id, task_key, lease_owner, lease_owner),
                )
                return cursor.rowcount == 1

    def fail_task(self, user_id: str, task_key: str, lease_owner: str) -> bool:
        """Mark a currently-held task failed; repeated failure is idempotent."""
        if not task_key.strip() or not lease_owner.strip():
            raise ValueError("task_key and lease_owner are required")
        tenant_id = self._tenant_for_user(user_id)
        with self.database.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT set_config('yike.tenant_id', %s, false)", (tenant_id,))
                cursor.execute(
                    "UPDATE pilot_tasks SET status='FAILED', lease_until=NULL "
                    "WHERE tenant_id=%s AND task_key=%s AND ((status='FAILED' AND lease_owner=%s) OR "
                    "(status='RUNNING' AND lease_owner=%s AND lease_until > CURRENT_TIMESTAMP))",
                    (tenant_id, task_key, lease_owner, lease_owner),
                )
                return cursor.rowcount == 1

    def get_task(self, user_id: str, task_key: str) -> dict:
        tenant_id = self._tenant_for_user(user_id)
        return self._fetchone(
            tenant_id,
            "SELECT task_id, task_key, status, lease_owner, lease_until FROM pilot_tasks WHERE tenant_id=%s AND task_key=%s",
            (tenant_id, task_key),
        )

    def list_failed_tasks(self, user_id: str) -> list[dict]:
        tenant_id = self._tenant_for_user(user_id)
        with self.database.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT set_config('yike.tenant_id', %s, false)", (tenant_id,))
                cursor.execute("SELECT task_id, task_key, status FROM pilot_tasks WHERE tenant_id=%s AND status='FAILED' ORDER BY task_id", (tenant_id,))
                columns = [d.name for d in cursor.description]
                return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def register_device(self, user_id: str, device_label: str) -> dict:
        if not isinstance(device_label, str) or not 1 <= len(device_label.strip()) <= 128:
            raise ValueError("device_label is required")
        tenant_id = self._tenant_for_user(user_id)
        device_id = str(uuid4())
        with self.database.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT set_config('yike.tenant_id', %s, false)", (tenant_id,))
                cursor.execute(
                    "INSERT INTO pilot_devices(device_id, tenant_id, device_label, owner_user_id) VALUES (%s,%s,%s,%s)",
                    (device_id, tenant_id, device_label.strip(), user_id),
                )
        return {"device_id": device_id, "device_label": device_label.strip(), "status": "ACTIVE"}

    def list_devices(self, user_id: str) -> list[dict]:
        tenant_id = self._tenant_for_user(user_id)
        with self.database.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT set_config('yike.tenant_id', %s, false)", (tenant_id,))
                cursor.execute(
                    "SELECT device_id, device_label, status, created_at, revoked_at "
                    "FROM pilot_devices WHERE tenant_id=%s ORDER BY created_at DESC, device_id DESC",
                    (tenant_id,),
                )
                columns = [column.name for column in cursor.description]
                return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def _check_mutation_session(self, cursor, user_id, claims):
        if claims is not None:
            if claims.user_id != user_id:
                raise InvalidPilotToken("invalid pilot token")
            self.sessions.require_active(cursor, claims)

    @contextmanager
    def _connection_mutation(self, user_id, claims):
        try:
            with self.database.connect() as connection, connection.cursor() as cursor:
                self._check_mutation_session(cursor, user_id, claims)
                yield cursor
                self._check_mutation_session(cursor, user_id, claims)
        except psycopg.Error as error:
            if error.sqlstate in ("YC001", "YC002"):
                code = "connection_version_exhausted" if error.sqlstate == "YC001" else "connection_version_conflict"
                raise ConnectionOperationError(code) from None
            raise

    def revoke_device(self, user_id: str, device_id: str, *, claims: TokenClaims | None = None) -> bool:
        if not isinstance(device_id, str) or not device_id.strip():
            raise ValueError("device_id is required")
        tenant_id = self._tenant_for_user(user_id)
        with self._connection_mutation(user_id, claims) as cursor:
            cursor.execute("SELECT set_config('yike.tenant_id', %s, false)", (tenant_id,))
            cursor.execute(
                "UPDATE pilot_devices SET status='REVOKED', revoked_at=COALESCE(revoked_at, CURRENT_TIMESTAMP) "
                "WHERE tenant_id=%s AND device_id=%s AND status <> 'REVOKED' RETURNING device_id",
                (tenant_id, device_id.strip()),
            )
            if cursor.fetchone() is None:
                return False
            self._check_mutation_session(cursor, user_id, claims)
            cursor.execute(
                "UPDATE pilot_platform_connections SET status='DISCONNECTED', disconnected_at=COALESCE(disconnected_at, CURRENT_TIMESTAMP) "
                "WHERE tenant_id=%s AND device_id=%s AND status<>'DISCONNECTED'",
                (tenant_id, device_id.strip()),
            )
        return True

    def connect_platform(self, user_id: str, platform: str, device_id: str, account_public_id: str, session_ref: str, *, claims: TokenClaims | None = None) -> dict:
        values = validate_connection_input(platform, device_id, account_public_id, session_ref)
        tenant_id = self._tenant_for_user(user_id)
        connection_id = str(uuid4())
        with self._connection_mutation(user_id, claims) as cursor:
            cursor.execute("SELECT set_config('yike.tenant_id', %s, false)", (tenant_id,))
            cursor.execute(
                "SELECT status FROM pilot_devices WHERE tenant_id=%s AND device_id=%s FOR UPDATE",
                (tenant_id, values["device_id"]),
            )
            device = cursor.fetchone()
            self._check_mutation_session(cursor, user_id, claims)
            if device is None:
                raise KeyError("device not found in tenant")
            if device[0] != "ACTIVE":
                raise ValueError("device is revoked")
            cursor.execute("SELECT connection_version FROM pilot_platform_connections "
                "WHERE tenant_id=%s AND device_id=%s AND platform=%s AND account_public_id=%s FOR UPDATE",
                (tenant_id, values["device_id"], values["platform"], values["account_public_id"]))
            existing = cursor.fetchone()
            self._check_mutation_session(cursor, user_id, claims)
            if existing and existing[0] == MAX_VERSION:
                raise ConnectionOperationError("connection_version_exhausted")
            cursor.execute(
                "INSERT INTO pilot_platform_connections(connection_id, tenant_id, device_id, platform, account_public_id, session_ref) "
                "VALUES (%s,%s,%s,%s,%s,%s) "
                "ON CONFLICT (tenant_id, device_id, platform, account_public_id) DO UPDATE SET "
                "session_ref=EXCLUDED.session_ref, status='UNVERIFIED', disconnected_at=NULL, "
                "connection_version=pilot_platform_connections.connection_version+1 "
                "RETURNING connection_id, platform, account_public_id, status, connection_version",
                (connection_id, tenant_id, values["device_id"], values["platform"], values["account_public_id"], values["session_ref"]),
            )
            row = cursor.fetchone()
            if row is None:
                raise RuntimeError("platform connection upsert failed")
        return {"connection_id": row[0], "platform": row[1], "account_public_id": row[2], "status": row[3], "connection_version": row[4]}

    def list_connections(self, user_id: str) -> list[dict]:
        tenant_id = self._tenant_for_user(user_id)
        with self.database.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT set_config('yike.tenant_id', %s, false)", (tenant_id,))
                cursor.execute(
                    "SELECT connection_id, device_id, platform, account_public_id, status, connected_at, disconnected_at, connection_version "
                    "FROM pilot_platform_connections WHERE tenant_id=%s ORDER BY connected_at DESC, connection_id DESC",
                    (tenant_id,),
                )
                columns = [column.name for column in cursor.description]
                return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def disconnect_platform(self, user_id: str, connection_id: str, *, claims: TokenClaims | None = None) -> bool:
        if not isinstance(connection_id, str) or not connection_id.strip():
            raise ValueError("connection_id is required")
        tenant_id = self._tenant_for_user(user_id)
        with self._connection_mutation(user_id, claims) as cursor:
            cursor.execute("SELECT set_config('yike.tenant_id', %s, false)", (tenant_id,))
            # Read identity without locking connection, then device→connection.
            cursor.execute("SELECT device_id FROM pilot_platform_connections WHERE tenant_id=%s AND connection_id=%s",
                           (tenant_id, connection_id.strip()))
            target = cursor.fetchone()
            if target is None:
                return False
            cursor.execute("SELECT device_id FROM pilot_devices WHERE tenant_id=%s AND device_id=%s FOR UPDATE",
                           (tenant_id, target[0]))
            self._check_mutation_session(cursor, user_id, claims)
            cursor.execute(
                "UPDATE pilot_platform_connections SET status='DISCONNECTED', disconnected_at=COALESCE(disconnected_at, CURRENT_TIMESTAMP) "
                "WHERE tenant_id=%s AND device_id=%s AND connection_id=%s AND status<>'DISCONNECTED' RETURNING connection_id",
                (tenant_id, target[0], connection_id.strip()),
            )
            return cursor.fetchone() is not None

    def append_execution_event(self, user_id: str, device_id: str, connection_id: str, execution_generation: int, event_type: str, payload: dict, task_id: str | None = None) -> dict:
        """Append reported telemetry only; never advance tasks, cursors or metrics."""
        event = validate_execution_event(event_type, execution_generation, payload)
        tenant_id = self._tenant_for_user(user_id)
        event_id = str(uuid4())
        body = json.dumps(event["payload"], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        with self.database.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT set_config('yike.tenant_id', %s, false)", (tenant_id,))
                cursor.execute(
                    "SELECT status FROM pilot_devices WHERE tenant_id=%s AND device_id=%s FOR UPDATE",
                    (tenant_id, device_id),
                )
                device = cursor.fetchone()
                if device is None:
                    raise KeyError("device not found in tenant")
                if device[0] != "ACTIVE":
                    raise ValueError("device is not active")
                # Fixed lock order: device, then connection, same as revoke.
                cursor.execute(
                    "SELECT status FROM pilot_platform_connections WHERE tenant_id=%s AND device_id=%s AND connection_id=%s FOR UPDATE",
                    (tenant_id, device_id, connection_id),
                )
                connected = cursor.fetchone()
                if connected is None:
                    raise KeyError("device or connection not found in tenant")
                if connected[0] != "CONNECTED":
                    raise ValueError("connection is not active")
                if task_id is not None:
                    cursor.execute("SELECT task_id FROM pilot_tasks WHERE tenant_id=%s AND task_id=%s FOR KEY SHARE", (tenant_id, task_id))
                    if cursor.fetchone() is None:
                        raise KeyError("task not found in tenant")
                cursor.execute(
                    "INSERT INTO pilot_execution_events(event_id, tenant_id, device_id, connection_id, task_id, execution_generation, event_type, payload) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb)",
                    (event_id, tenant_id, device_id, connection_id, task_id, event["execution_generation"], event["event_type"], body),
                )
        return {"event_id": event_id, "execution_generation": event["execution_generation"], "event_type": event["event_type"]}

    @staticmethod
    def _profile_id(tenant_id: str) -> str:
        return hashlib.sha256((tenant_id + ":default-profile").encode()).hexdigest()[:32]
