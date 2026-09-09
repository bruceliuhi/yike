"""Synthetic registration recovery against a real restricted PostgreSQL role."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import replace
import hashlib
from pathlib import Path
from types import SimpleNamespace
import time
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

import psycopg
from psycopg import sql
import pytest
from nacl.signing import SigningKey

from pilot.auth import issue_token, verify_token_claims
from pilot.db import PilotDatabase
from pilot.device_credentials import DeviceCredentialStore
from pilot.device_keys import DeviceKeyError
from pilot.device_registration import DeviceRegistrationStore
from pilot.store import PilotStore
from tests.test_device_credentials_postgres import (
    RoleDatabase,
    bind,
    challenge,
    complete,
    databases,
    wait_for_lock,
)


SECRET = "synthetic-registration-test-secret"
ROOT = Path(__file__).parents[1]


@pytest.fixture(scope="module")
def registration_databases(databases):
    admin, app = databases
    admin.migrate()
    admin.migrate()
    with app.connect() as connection:
        role = connection.execute("SELECT current_user").fetchone()[0]
    grant = (ROOT / "deploy/grant_device_registration.sql").read_text()
    with admin.connect() as connection:
        connection.execute("SELECT set_config('yike.app_role',%s,true)", (role,))
        connection.execute(grant)
        connection.execute(grant)
    return admin, app


@pytest.fixture
def env(registration_databases):
    admin, database = registration_databases
    provisioner = PilotStore(admin)
    tenants = [provisioner.provision_tenant("synthetic-registration") for _ in range(2)]
    users = [
        provisioner.provision_user(tenant, f"{uuid4()}@example.invalid")
        for tenant in (tenants[0], tenants[0], tenants[1])
    ]
    claims = [verify_token_claims(issue_token(user, SECRET), SECRET) for user in users]
    yield SimpleNamespace(
        admin=admin,
        database=database,
        tenants=tenants,
        users=users,
        claims=claims,
        service=DeviceRegistrationStore(database),
        store=PilotStore(database),
    )
    with admin.connect() as connection:
        for table in (
            "pilot_device_registrations",
            "pilot_device_key_requests",
            "pilot_device_credentials",
            "pilot_devices",
            "pilot_session_revocations",
            "pilot_users",
            "pilot_tenants",
        ):
            connection.execute(f"DELETE FROM {table} WHERE tenant_id=ANY(%s)", (tenants,))


def payload(label="客户的电脑", request_id=None):
    return {"request_id": request_id or str(uuid4()), "device_label": label}


def test_register_normalizes_replays_recovers_and_conflicts_without_extra_device(env):
    body = payload("  客户的电脑  ")
    first = env.service.register(env.claims[0], body)
    assert set(first) == {"request_id", "device_id", "device_label", "registered_at", "state"}
    assert first["request_id"] == body["request_id"]
    assert first["device_label"] == "客户的电脑"
    assert first["state"] == "SUCCEEDED"
    assert first["registered_at"].endswith(("+00:00", "Z"))
    assert env.service.register(env.claims[0], body) == first
    env.service = DeviceRegistrationStore(env.database)
    assert env.service.get_receipt(env.claims[0], body["request_id"]) == first
    assert env.service.get_identity(env.claims[0], first["device_id"]) == {
        "device_id": first["device_id"],
        "device_status": "ACTIVE",
        "credential_version": 0,
        "public_key": None,
    }
    with pytest.raises(DeviceKeyError, match="request_conflict"):
        env.service.register(env.claims[0], body | {"device_label": "另一名称"})
    with env.admin.connect() as connection:
        assert connection.execute(
            "SELECT count(*) FROM pilot_devices WHERE tenant_id=%s AND owner_user_id=%s AND device_label IN (%s,%s)",
            (env.tenants[0], env.users[0], "客户的电脑", "另一名称"),
        ).fetchone()[0] == 1


def test_same_owner_concurrent_same_request_creates_one_device_and_receipt(env):
    body = payload("并发设备")
    with ThreadPoolExecutor(2) as pool:
        futures = [pool.submit(env.service.register, env.claims[0], body) for _ in range(2)]
    results = [future.result(timeout=5) for future in futures]
    assert results[0] == results[1]
    with env.admin.connect() as connection:
        assert connection.execute(
            "SELECT count(*) FROM pilot_device_registrations WHERE tenant_id=%s AND owner_user_id=%s AND request_id=%s",
            (env.tenants[0], env.users[0], body["request_id"]),
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT count(*) FROM pilot_devices WHERE tenant_id=%s AND owner_user_id=%s AND device_id=%s",
            (env.tenants[0], env.users[0], results[0]["device_id"]),
        ).fetchone()[0] == 1


def test_owner_tenant_request_isolation_and_null_owner_is_never_claimed(env):
    request_id = str(uuid4())
    first = env.service.register(env.claims[0], payload("first owner", request_id))
    second = env.service.register(env.claims[1], payload("second owner", request_id))
    third = env.service.register(env.claims[2], payload("other tenant", request_id))
    assert len({first["device_id"], second["device_id"], third["device_id"]}) == 3
    for index, own in enumerate((first, second, third)):
        assert env.service.get_receipt(env.claims[index], request_id) == own
        for other in ({first["device_id"], second["device_id"], third["device_id"]} - {own["device_id"]}):
            with pytest.raises(DeviceKeyError, match="device_unavailable"):
                env.service.get_identity(env.claims[index], other)

    legacy = env.store.register_device(env.users[0], "legacy matching label")
    with env.admin.connect() as connection:
        connection.execute("UPDATE pilot_devices SET owner_user_id=NULL WHERE device_id=%s", (legacy["device_id"],))
    registered = env.service.register(env.claims[0], payload("legacy matching label"))
    assert registered["device_id"] != legacy["device_id"]
    with pytest.raises(DeviceKeyError, match="device_unavailable"):
        env.service.get_identity(env.claims[0], legacy["device_id"])


def test_identity_tracks_bind_prove_rotate_and_revoke_while_receipt_is_historical(env):
    receipt = env.service.register(env.claims[0], payload("credential lifecycle"))
    original = dict(receipt)
    key_env = SimpleNamespace(
        service=DeviceCredentialStore(env.database),
        store=env.store,
        claims=env.claims[0],
        device=receipt["device_id"],
    )
    old, new = SigningKey.generate(), SigningKey.generate()
    bind(key_env, old)
    assert env.service.get_identity(env.claims[0], receipt["device_id"])["credential_version"] == 1
    complete(key_env, challenge(key_env, "PROVE", 1), old)
    rotation = challenge(key_env, "ROTATE", 1, new)
    complete(key_env, rotation, new, old)
    current = env.service.get_identity(env.claims[0], receipt["device_id"])
    assert current["credential_version"] == 2
    assert current["public_key"] != None
    assert env.service.get_receipt(env.claims[0], receipt["request_id"]) == original
    assert env.store.revoke_device(env.users[0], receipt["device_id"], claims=env.claims[0])
    assert env.service.get_identity(env.claims[0], receipt["device_id"]) == current | {"device_status": "REVOKED"}
    assert env.service.get_receipt(env.claims[0], receipt["request_id"]) == original


def _registration_lock(tenant, user, request_id):
    raw = (tenant + "\0" + user + "\0" + request_id).encode("utf-8")
    return int.from_bytes(hashlib.sha256(raw).digest()[:4], "big", signed=True)


def test_session_expiry_after_request_lock_wait_rolls_back_all_rows(env):
    body = payload("expires while waiting")
    deadline = int(time.time()) + 2
    expiring = replace(env.claims[0], expires_at=deadline)
    lock_key = _registration_lock(env.tenants[0], env.users[0], body["request_id"])
    with ThreadPoolExecutor(1) as pool:
        with env.admin.connect() as blocker:
            blocker.execute("SELECT pg_advisory_xact_lock(11601,%s)", (lock_key,))
            future = pool.submit(env.service.register, expiring, body)
            wait_for_lock(env.admin, "pg_advisory_xact_lock(11601")
            while time.time() <= deadline:
                time.sleep(0.01)
        with pytest.raises(DeviceKeyError, match="invalid_session"):
            future.result(timeout=5)
    with env.admin.connect() as connection:
        assert connection.execute(
            "SELECT count(*) FROM pilot_device_registrations WHERE request_id=%s", (body["request_id"],)
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT count(*) FROM pilot_devices WHERE tenant_id=%s AND owner_user_id=%s AND device_label=%s",
            (env.tenants[0], env.users[0], body["device_label"]),
        ).fetchone()[0] == 0


class _CursorProxy:
    def __init__(self, cursor, *, fail_receipt_insert=False):
        self._cursor = cursor
        self._fail_receipt_insert = fail_receipt_insert

    def __enter__(self):
        self._cursor.__enter__()
        return self

    def __exit__(self, *args):
        return self._cursor.__exit__(*args)

    def execute(self, query, params=None):
        if self._fail_receipt_insert and str(query).lstrip().startswith("INSERT INTO pilot_device_registrations"):
            raise psycopg.OperationalError("synthetic receipt insert failure")
        return self._cursor.execute(query, params)

    def __getattr__(self, name):
        return getattr(self._cursor, name)


class _ConnectionProxy:
    def __init__(self, connection, *, fail_receipt_insert=False):
        self._connection = connection
        self._fail_receipt_insert = fail_receipt_insert

    def cursor(self):
        return _CursorProxy(self._connection.cursor(), fail_receipt_insert=self._fail_receipt_insert)

    def __getattr__(self, name):
        return getattr(self._connection, name)


class _FaultDatabase:
    def __init__(self, database, *, fail_receipt_insert=False, fail_after_commit=False):
        self._database = database
        self._fail_receipt_insert = fail_receipt_insert
        self._fail_after_commit = fail_after_commit

    @contextmanager
    def connect(self):
        with self._database.connect() as connection:
            yield _ConnectionProxy(connection, fail_receipt_insert=self._fail_receipt_insert)
        if self._fail_after_commit:
            raise psycopg.OperationalError("synthetic unknown commit acknowledgement")


def test_receipt_insert_failure_rolls_back_device_and_unknown_commit_recovers(env):
    failed = payload("must roll back")
    service = DeviceRegistrationStore(_FaultDatabase(env.database, fail_receipt_insert=True))
    with pytest.raises(DeviceKeyError, match="registration_outcome_unknown"):
        service.register(env.claims[0], failed)
    with env.admin.connect() as connection:
        assert connection.execute(
            "SELECT count(*) FROM pilot_devices WHERE tenant_id=%s AND owner_user_id=%s AND device_label=%s",
            (env.tenants[0], env.users[0], failed["device_label"]),
        ).fetchone()[0] == 0

    unknown = payload("commit acknowledged late")
    service = DeviceRegistrationStore(_FaultDatabase(env.database, fail_after_commit=True))
    with pytest.raises(DeviceKeyError, match="registration_outcome_unknown"):
        service.register(env.claims[0], unknown)
    recovered = env.service.get_receipt(env.claims[0], unknown["request_id"])
    assert recovered["device_label"] == unknown["device_label"]


def test_fresh_115_to_116_twice_and_restricted_registration_grant(registration_databases):
    admin, _ = registration_databases
    database_name = "registration_upgrade_" + uuid4().hex
    role = "registration_role_" + uuid4().hex
    parts = urlsplit(admin.url)
    fresh = PilotDatabase(urlunsplit(parts._replace(path="/" + database_name)))
    created = False
    try:
        with admin.connect() as connection:
            connection.autocommit = True
            connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database_name)))
            created = True
        legacy_end = next(
            index for index, item in enumerate(PilotDatabase.migration_paths)
            if item[0] == "v02-opportunity-evidence"
        ) + 1
        fresh.migration_paths = PilotDatabase.migration_paths[:legacy_end]
        fresh.migrate()
        with fresh.connect() as connection:
            checksum = connection.execute(
                "SELECT checksum FROM pilot_schema_meta WHERE version='v02-opportunity-evidence'"
            ).fetchone()[0]
            assert connection.execute("SELECT to_regclass('pilot_device_registrations')").fetchone()[0] is None
            connection.execute(
                sql.SQL("CREATE ROLE {} NOLOGIN NOSUPERUSER NOBYPASSRLS NOCREATEROLE").format(sql.Identifier(role))
            )
            connection.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
            connection.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(sql.Identifier(role)))
            connection.execute(sql.SQL("GRANT SELECT ON pilot_users TO {}").format(sql.Identifier(role)))
            connection.execute("SELECT set_config('yike.app_role',%s,true)", (role,))
            connection.execute((ROOT / "deploy/grant_session_revocations.sql").read_text())

        fresh.migration_paths = PilotDatabase.migration_paths
        fresh.migrate()
        fresh.migrate()
        with fresh.connect() as connection:
            assert connection.execute(
                "SELECT checksum FROM pilot_schema_meta WHERE version='v02-opportunity-evidence'"
            ).fetchone()[0] == checksum
            registration_checksum = connection.execute(
                "SELECT checksum FROM pilot_schema_meta WHERE version='v02-device-registration'"
            ).fetchone()[0]
            connection.execute("SELECT set_config('yike.app_role',%s,true)", (role,))
            grant = (ROOT / "deploy/grant_device_registration.sql").read_text()
            connection.execute(grant)
            connection.execute(grant)
            assert connection.execute(
                "SELECT checksum FROM pilot_schema_meta WHERE version='v02-device-registration'"
            ).fetchone()[0] == registration_checksum

        restricted = RoleDatabase(fresh, role)
        provisioner = PilotStore(fresh)
        tenant = provisioner.provision_tenant("synthetic-registration-upgrade")
        users = [provisioner.provision_user(tenant, f"{uuid4()}@example.invalid") for _ in range(2)]
        service = DeviceRegistrationStore(restricted)
        shared_request = str(uuid4())
        receipts = [
            service.register(verify_token_claims(issue_token(user, SECRET), SECRET), payload(str(index), shared_request))
            for index, user in enumerate(users)
        ]
        assert receipts[0]["device_id"] != receipts[1]["device_id"]
        with restricted.connect() as connection:
            assert connection.execute(
                "SELECT rolsuper,rolbypassrls,rolcreaterole FROM pg_roles WHERE rolname=current_user"
            ).fetchone() == (False, False, False)
            assert connection.execute(
                "SELECT has_table_privilege(current_user,'pilot_device_registrations','SELECT')"
            ).fetchone()[0]
            assert connection.execute(
                "SELECT has_table_privilege(current_user,'pilot_device_registrations','INSERT')"
            ).fetchone()[0]
            assert not connection.execute(
                "SELECT has_table_privilege(current_user,'pilot_device_registrations','UPDATE')"
            ).fetchone()[0]
            assert not connection.execute(
                "SELECT has_table_privilege(current_user,'pilot_device_registrations','DELETE')"
            ).fetchone()[0]
            assert not connection.execute("SELECT has_schema_privilege(current_user,'public','CREATE')").fetchone()[0]
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                connection.execute("UPDATE pilot_device_registrations SET device_label=device_label")
        for user in users:
            with restricted.connect() as connection:
                connection.execute("SELECT set_config('yike.tenant_id',%s,true)", (tenant,))
                connection.execute("SELECT set_config('yike.user_id',%s,true)", (user,))
                assert connection.execute("SELECT count(*) FROM pilot_device_registrations").fetchone()[0] == 1
    finally:
        if created:
            with admin.connect() as connection:
                connection.autocommit = True
                connection.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(database_name)))
                if connection.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (role,)).fetchone():
                    connection.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(role)))
