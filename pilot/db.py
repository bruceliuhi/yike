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
