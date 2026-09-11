"""Opt-in real PostgreSQL check; use only an isolated migrated test database.

Can also run with unittest inside the service image (no test dependencies).
"""
import os
from pathlib import Path
import unittest
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

import psycopg
from psycopg import sql

from pilot.db import PilotDatabase
from pilot.store import PilotStore


ROOT = Path(__file__).resolve().parents[1]
ADMIN_URL = os.environ.get("YIKE_EMPTY_DEPLOYMENT_TEST_DATABASE_URL")


@unittest.skipUnless(ADMIN_URL, "requires an isolated migrated PostgreSQL database")
class EmptyDeploymentGrantsTest(unittest.TestCase):
    def setUp(self):
        self.role = "empty_grants_" + uuid4().hex
        self.password = uuid4().hex
        self.admin = psycopg.connect(ADMIN_URL, autocommit=True)
        self.admin.execute(sql.SQL(
            "CREATE ROLE {} LOGIN PASSWORD {} NOSUPERUSER NOBYPASSRLS "
            "NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION"
        ).format(sql.Identifier(self.role), sql.Literal(self.password)))
        self.addCleanup(self.cleanup_role)
        parsed = urlsplit(ADMIN_URL)
        host = parsed.netloc.rsplit("@", 1)[-1]
        self.app = PilotStore(PilotDatabase(urlunsplit(parsed._replace(
            netloc=f"{self.role}:{self.password}@{host}"))))

    def cleanup_role(self):
        # This randomly named role is created by this test and owns no objects.
        self.admin.execute(sql.SQL("DROP OWNED BY {}").format(sql.Identifier(self.role)))
        self.admin.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(self.role)))
        self.admin.close()

    def grant(self):
        with self.admin.transaction():
            self.admin.execute("SELECT set_config('yike.app_role', %s, true)", (self.role,))
            manifest = (ROOT / "deploy/grant_runtime.sql").read_text()
            names = [line.split()[1] for line in manifest.splitlines() if line.startswith("\\ir ")]
            self.assertEqual(len(names), len(set(names)))
            self.assertEqual(set(names), {
                path.name for path in (ROOT / "deploy").glob("grant_*.sql")
                if path.name != "grant_runtime.sql"
            })
            for name in names:
                self.admin.execute((ROOT / "deploy" / name).read_text())

    def test_profile_save_confirm_and_cross_tenant_read(self):
        self.grant()
        admin_store = PilotStore(PilotDatabase(ADMIN_URL))
        tenant = admin_store.provision_tenant("SYNTHETIC EMPTY DB CHECK")
        user = admin_store.provision_user(tenant, "test@example.invalid")
        other = admin_store.provision_user(
            admin_store.provision_tenant("SYNTHETIC OTHER TENANT"), "test@example.invalid")
        self.assertEqual(self.app.list_profiles(user), [])
        profile = self.app.save_profile(user, {"description": "Synthetic deployment check"})
        self.app.confirm_profile(user, profile["version_id"])
        self.assertEqual(len(self.app.list_profiles(user)), 1)
        self.assertEqual(self.app.list_profiles(other), [])
        self.grant()  # Repeatable; does not destroy profile data.
        self.assertEqual(len(self.app.list_profiles(user)), 1)
        for table in ("pilot_users", "business_profiles", "business_profile_versions", "pilot_tasks"):
            for privilege in ("DELETE", "TRUNCATE", "TRIGGER", "REFERENCES"):
                self.assertFalse(self.admin.execute(
                    "SELECT has_table_privilege(%s,%s,%s)", (self.role, table, privilege)).fetchone()[0])
        self.assertFalse(self.admin.execute(
            "SELECT has_any_column_privilege(%s,'pilot_users','INSERT,UPDATE')", (self.role,)).fetchone()[0])
        self.assertFalse(self.admin.execute(
            "SELECT has_column_privilege(%s,'business_profile_versions','payload','UPDATE')", (self.role,)).fetchone()[0])

    def test_rejects_preexisting_excess_column_permissions(self):
        self.admin.execute(sql.SQL(
            "GRANT UPDATE(payload) ON business_profile_versions TO {}"
        ).format(sql.Identifier(self.role)))
        with self.assertRaises(psycopg.Error):
            self.grant()


if __name__ == "__main__":
    unittest.main()
