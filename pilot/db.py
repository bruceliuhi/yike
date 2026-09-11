from __future__ import annotations

import os
import hashlib
from pathlib import Path

import psycopg


class MissingDatabaseConfiguration(RuntimeError):
    """Raised when the customer pilot is not pointed at an explicit Postgres DB."""


class PilotDatabase:
    migration_path = Path(__file__).resolve().parents[1] / "migrations" / "101_customer_pilot.sql"
    migration_paths = (
        ("customer-pilot-v1", migration_path),
        ("customer-pilot-v2", migration_path.with_name("102_customer_pilot_evidence.sql")),
        ("customer-pilot-v3", migration_path.with_name("103_customer_pilot_tenant_rls.sql")),
        ("v02-identity-execution", migration_path.with_name("104_v02_identity_execution.sql")),
        ("v02-session-revocation", migration_path.with_name("105_v02_session_revocation.sql")),
        ("v02-device-credentials", migration_path.with_name("106_v02_device_credentials.sql")),
        ("v02-connection-versions", migration_path.with_name("107_v02_connection_versions.sql")),
        ("v02-phone-login", migration_path.with_name("109_v02_phone_login.sql")),
        ("v02-search-suggestions", migration_path.with_name("110_v02_search_suggestions.sql")),
        ("v02-execution-runtime", migration_path.with_name("111_v02_execution_runtime.sql")),
        ("v02-candidate-ingestion", migration_path.with_name("112_v02_candidate_ingestion.sql")),
        ("v02-candidate-review", migration_path.with_name("113_v02_candidate_review.sql")),
        ("v02-research-strategies", migration_path.with_name("114_v02_research_strategies.sql")),
        ("v02-opportunity-evidence", migration_path.with_name("115_v02_opportunity_evidence.sql")),
        ("v02-device-registration", migration_path.with_name("116_v02_device_registration.sql")),
        ("v02-reply-events", migration_path.with_name("118_v02_reply_events.sql")),
        ("v02-outreach-contract", migration_path.with_name("117_v02_outreach_contract.sql")),
        ("v02-connection-verification", migration_path.with_name("119_v02_connection_verification.sql")),
        ("v02-execution-finish", migration_path.with_name("120_v02_execution_finish.sql")),
        ("v02-contact-drafts", migration_path.with_name("121_v02_contact_drafts.sql")),
        ("v02-outreach-queue", migration_path.with_name("122_v02_outreach_queue.sql")),
        ("v02-outreach-dispatch", migration_path.with_name("123_v02_outreach_dispatch.sql")),
        ("v02-reply-attestation", migration_path.with_name("124_v02_reply_attestation.sql")),
        ("v02-materials", migration_path.with_name("125_v02_materials.sql")),
        ("v02-monitor-plans", migration_path.with_name("126_v02_monitor_plans.sql")),
        ("v02-monitor-runtime", migration_path.with_name("127_v02_monitor_runtime.sql")),
        ("v02-search-suggestion-consent", migration_path.with_name("128_v02_search_suggestion_consent.sql")),
        ("v02-search-suggestion-rejections", migration_path.with_name("129_v02_search_suggestion_rejections.sql")),
        ("v02-short-coach", migration_path.with_name("130_v02_short_coach.sql")),
        ("v02-structured-followups", migration_path.with_name("131_v02_structured_followups.sql")),
        ("v02-material-profile-references", migration_path.with_name("132_v02_material_profile_references.sql")),
        ("v02-research-execution", migration_path.with_name("133_v02_research_execution.sql")),
        ("v02-research-resources", migration_path.with_name("134_v02_research_resources.sql")),
        ("v02-research-candidate-binding", migration_path.with_name("135_v02_research_candidate_binding.sql")),
        ("v02-ops-trials", migration_path.with_name("136_v02_ops_trials.sql")),
        ("v02-research-runtime", migration_path.with_name("137_v02_research_runtime.sql")),
        ("v02-temporary-access", migration_path.with_name("138_v02_temporary_access.sql")),
    )

    def __init__(self, url: str):
        if not url.startswith(("postgresql://", "postgres://")):
            raise MissingDatabaseConfiguration("YIKE_PILOT_DATABASE_URL must be a PostgreSQL URL")
        self.url = url

    @classmethod
    def from_environment(cls) -> "PilotDatabase":
        url = os.environ.get("YIKE_PILOT_DATABASE_URL", "").strip()
        if not url:
            raise MissingDatabaseConfiguration("YIKE_PILOT_DATABASE_URL is required")
        return cls(url)

    @classmethod
    def from_admin_environment(cls) -> "PilotDatabase":
        """Build the trusted migration/provisioning connection explicitly."""
        url = os.environ.get("YIKE_PILOT_ADMIN_DATABASE_URL", "").strip()
        if not url:
            raise MissingDatabaseConfiguration("YIKE_PILOT_ADMIN_DATABASE_URL is required")
        return cls(url)

    def connect(self):
        return psycopg.connect(self.url, connect_timeout=5, application_name="yike-customer-pilot")

    def migrate(self) -> None:
        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_xact_lock(hashtext('yike-customer-pilot-schema'))")
                for version, path in self.migration_paths:
                    sql = path.read_text(encoding="utf-8")
                    checksum = hashlib.sha256(sql.encode("utf-8")).hexdigest()
                    cursor.execute(sql)
                    cursor.execute("SELECT checksum FROM pilot_schema_meta WHERE version=%s", (version,))
                    existing = cursor.fetchone()
                    if existing is None:
                        cursor.execute("INSERT INTO pilot_schema_meta(version, checksum) VALUES (%s, %s)", (version, checksum))
                    elif existing[0] != checksum:
                        raise RuntimeError(f"customer-pilot migration checksum mismatch: {version}")
