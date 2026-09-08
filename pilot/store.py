from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from uuid import uuid4

from pilot.db import PilotDatabase


class PilotStore:
    def __init__(self, database: PilotDatabase):
        self.database = database

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
        tenant_id = self._tenant_for_user(user_id)
        profile_id = self._profile_id(tenant_id)
        content = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(content.encode()).hexdigest()
        with self.database.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT set_config('yike.tenant_id', %s, false)", (tenant_id,))
                cursor.execute("INSERT INTO business_profiles(profile_id, tenant_id) VALUES (%s, %s) ON CONFLICT DO NOTHING", (profile_id, tenant_id))
                cursor.execute("SELECT profile_id FROM business_profiles WHERE tenant_id=%s AND profile_id=%s FOR UPDATE", (tenant_id, profile_id))
                cursor.execute("SELECT COALESCE(MAX(version), 0) + 1 FROM business_profile_versions WHERE tenant_id=%s AND profile_id=%s", (tenant_id, profile_id))
                version = cursor.fetchone()[0]
                version_id = str(uuid4())
                cursor.execute(
                    "INSERT INTO business_profile_versions(profile_version_id, tenant_id, profile_id, version, payload, content_sha256) VALUES (%s,%s,%s,%s,%s::jsonb,%s)",
                    (version_id, tenant_id, profile_id, version, content, digest),
                )
        return {"profile_id": profile_id, "version_id": version_id, "version": version}

    def confirm_profile(self, user_id: str, version_id: str) -> None:
        tenant_id = self._tenant_for_user(user_id)
        with self.database.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT set_config('yike.tenant_id', %s, false)", (tenant_id,))
                cursor.execute("UPDATE business_profile_versions SET status='CONFIRMED', approved_at=CURRENT_TIMESTAMP WHERE tenant_id=%s AND profile_version_id=%s AND status='DRAFT'", (tenant_id, version_id))
                if cursor.rowcount != 1:
                    raise KeyError("draft profile version not found in tenant")

    def get_profile_version(self, user_id: str, version_id: str) -> dict:
        tenant_id = self._tenant_for_user(user_id)
        row = self._fetchone(tenant_id, "SELECT profile_version_id, version, payload, status FROM business_profile_versions WHERE tenant_id=%s AND profile_version_id=%s", (tenant_id, version_id))
        return {"version_id": row["profile_version_id"], "version": row["version"], "payload": row["payload"], "status": row["status"]}

    def import_opportunity(self, user_id: str, profile_version_id: str, import_key: str, data: dict) -> dict:
        tenant_id = self._tenant_for_user(user_id)
        source_id = str(uuid4())
        opportunity_id = str(uuid4())
        with self.database.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT set_config('yike.tenant_id', %s, false)", (tenant_id,))
                cursor.execute("SELECT 1 FROM business_profile_versions WHERE tenant_id=%s AND profile_version_id=%s AND status='CONFIRMED'", (tenant_id, profile_version_id))
                if cursor.fetchone() is None:
                    raise ValueError("opportunity import requires a confirmed profile version")
                cursor.execute("INSERT INTO pilot_sources(source_id, tenant_id, platform, external_id, public_url, published_at) VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT (tenant_id, platform, external_id) DO NOTHING RETURNING source_id", (source_id, tenant_id, data["source_platform"], data["source_external_id"], data["public_url"], data.get("source_published_at")))
                source = cursor.fetchone()
                if source:
                    source_id = source[0]
                else:
                    cursor.execute("SELECT source_id FROM pilot_sources WHERE tenant_id=%s AND platform=%s AND external_id=%s FOR UPDATE", (tenant_id, data["source_platform"], data["source_external_id"]))
                    source_id = cursor.fetchone()[0]
                source_text = json.dumps({"title": data["title"], "summary": data["summary"], "excerpt": data.get("public_excerpt", "")}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
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
                cursor.execute("INSERT INTO pilot_opportunities(opportunity_id, tenant_id, profile_version_id, source_id, import_key, title, buyer, summary, contact_path, public_excerpt, draft_comment, draft_dm) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (tenant_id, import_key) DO NOTHING RETURNING opportunity_id", (opportunity_id, tenant_id, profile_version_id, source_id, import_key, data["title"], data["buyer"], data["summary"], data["contact_path"], data.get("public_excerpt"), data["draft_comment"], data["draft_dm"]))
                inserted = cursor.fetchone()
                if inserted is not None:
                    return {"opportunity_id": inserted[0], "created": True}
                cursor.execute("SELECT opportunity_id FROM pilot_opportunities WHERE tenant_id=%s AND import_key=%s", (tenant_id, import_key))
                existing = cursor.fetchone()
                return {"opportunity_id": existing[0], "created": False}

    def list_opportunities(self, user_id: str) -> list[dict]:
        tenant_id = self._tenant_for_user(user_id)
        with self.database.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT set_config('yike.tenant_id', %s, false)", (tenant_id,))
                cursor.execute("SELECT opportunity_id, title, buyer, intent_status, source_status, public_excerpt FROM pilot_opportunities WHERE tenant_id=%s ORDER BY created_at DESC", (tenant_id,))
                columns = [d.name for d in cursor.description]
                return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def get_opportunity(self, user_id: str, opportunity_id: str) -> dict:
        tenant_id = self._tenant_for_user(user_id)
        return self._fetchone(tenant_id, "SELECT opportunity_id, title, buyer, summary, contact_path, draft_comment, draft_dm, source_status FROM pilot_opportunities WHERE tenant_id=%s AND opportunity_id=%s", (tenant_id, opportunity_id))

    def record_followup(self, user_id: str, opportunity_id: str, status: str, note: str) -> dict:
        tenant_id = self._tenant_for_user(user_id)
        followup_id = str(uuid4())
        with self.database.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT set_config('yike.tenant_id', %s, false)", (tenant_id,))
                cursor.execute("SELECT 1 FROM pilot_opportunities WHERE tenant_id=%s AND opportunity_id=%s", (tenant_id, opportunity_id))
                if cursor.fetchone() is None:
                    raise KeyError("opportunity not found in tenant")
                cursor.execute("INSERT INTO pilot_followups(followup_id, tenant_id, opportunity_id, status, note) VALUES (%s,%s,%s,%s,%s)", (followup_id, tenant_id, opportunity_id, status, note))
        return {"followup_id": followup_id}

    def list_followups(self, user_id: str, opportunity_id: str) -> list[dict]:
        tenant_id = self._tenant_for_user(user_id)
        with self.database.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT set_config('yike.tenant_id', %s, false)", (tenant_id,))
                cursor.execute("SELECT followup_id, status, note, created_at FROM pilot_followups WHERE tenant_id=%s AND opportunity_id=%s ORDER BY created_at DESC", (tenant_id, opportunity_id))
                columns = [d.name for d in cursor.description]
                return [dict(zip(columns, row)) for row in cursor.fetchall()]

    @staticmethod
    def _profile_id(tenant_id: str) -> str:
        return hashlib.sha256((tenant_id + ":default-profile").encode()).hexdigest()[:32]
