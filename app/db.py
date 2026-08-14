from pathlib import Path
import hashlib
import json
import sqlite3


_MIGRATION = Path(__file__).resolve().parents[1] / "migrations" / "001_discovery.sql"
_SCHEMA_VERSION = "DISCOVERY_FACT_STORE_V15"
_SCHEMA_SIGNATURE = "b53b01c2acc2f0b0818a5b60a390c7d26c13042c807a3f8eb31277bf85f43ec0"


class UnsupportedSchemaError(RuntimeError):
    pass


def _sha256_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _nonblank_text(value: object) -> int:
    return int(isinstance(value, str) and bool(value.strip()))


def _register_functions(connection: sqlite3.Connection) -> None:
    connection.create_function(
        "yike_sha256_text", 1, _sha256_text, deterministic=True
    )
    connection.create_function(
        "yike_nonblank_text", 1, _nonblank_text, deterministic=True
    )


def _schema_signature(connection: sqlite3.Connection) -> str:
    objects = [
        tuple(row)
        for row in connection.execute(
            """
            SELECT type, name, tbl_name, sql
            FROM sqlite_master
            WHERE name NOT LIKE 'sqlite_%' AND sql IS NOT NULL
            ORDER BY type, name
            """
        )
    ]
    encoded = json.dumps(objects, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _validate_current_schema(connection: sqlite3.Connection) -> None:
    try:
        marker = connection.execute(
            """
            SELECT version, signature FROM schema_meta
            WHERE schema_key = 'discovery'
            """
        ).fetchone()
    except sqlite3.Error as error:
        raise UnsupportedSchemaError(
            "UNSUPPORTED_SCHEMA: database has no current schema marker"
        ) from error
    if marker is None or tuple(marker) != (_SCHEMA_VERSION, _SCHEMA_SIGNATURE):
        raise UnsupportedSchemaError(
            "UNSUPPORTED_SCHEMA: database schema marker is not current"
        )
    if _schema_signature(connection) != _SCHEMA_SIGNATURE:
        raise UnsupportedSchemaError(
            "UNSUPPORTED_SCHEMA: database schema signature does not match"
        )


def connect(database_path: Path) -> sqlite3.Connection:
    """Open the local fact store with the required SQLite safety settings."""
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database_path)
    _register_functions(connection)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    connection.execute("PRAGMA busy_timeout = 5000")
    return connection


def migrate(connection: sqlite3.Connection) -> None:
    """Apply the idempotent discovery schema to an empty or existing database."""
    if connection.in_transaction:
        raise RuntimeError("cannot migrate while connection has an active transaction")
    _register_functions(connection)
    connection.execute("PRAGMA foreign_keys = ON")
    if connection.execute("PRAGMA foreign_keys").fetchone()[0] != 1:
        raise RuntimeError("SQLite foreign key enforcement could not be enabled")
    has_schema = connection.execute(
        """
        SELECT 1 FROM sqlite_master
        WHERE name NOT LIKE 'sqlite_%'
        LIMIT 1
        """
    ).fetchone()
    if has_schema:
        _validate_current_schema(connection)
        return

    connection.executescript(_MIGRATION.read_text(encoding="utf-8"))
    signature = _schema_signature(connection)
    if signature != _SCHEMA_SIGNATURE:
        raise UnsupportedSchemaError(
            "UNSUPPORTED_SCHEMA: installed schema signature does not match"
        )
    with connection:
        connection.execute(
            """
            INSERT INTO schema_meta (schema_key, version, signature)
            VALUES ('discovery', ?, ?)
            """,
            (_SCHEMA_VERSION, _SCHEMA_SIGNATURE),
        )
