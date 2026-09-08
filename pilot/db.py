from __future__ import annotations

import os
import hashlib
from pathlib import Path

import psycopg


class MissingDatabaseConfiguration(RuntimeError):
    """Raised when the customer pilot is not pointed at an explicit Postgres DB."""


class PilotDatabase:
    migration_path = Path(__file__).resolve().parents[1] / "migrations" / "101_customer_pilot.sql"

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
        sql = self.migration_path.read_text(encoding="utf-8")
        checksum = hashlib.sha256(sql.encode("utf-8")).hexdigest()
        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_xact_lock(hashtext('yike-customer-pilot-schema'))")
                cursor.execute(sql)
                cursor.execute("SELECT checksum FROM pilot_schema_meta WHERE version='customer-pilot-v1'")
                existing = cursor.fetchone()
                if existing is None:
                    cursor.execute("INSERT INTO pilot_schema_meta(version, checksum) VALUES (%s, %s)", ("customer-pilot-v1", checksum))
                elif existing[0] != checksum:
                    raise RuntimeError("customer-pilot migration checksum mismatch")
