from pathlib import Path
import sqlite3


_MIGRATION = Path(__file__).resolve().parents[1] / "migrations" / "001_discovery.sql"


def connect(database_path: Path) -> sqlite3.Connection:
    """Open the local fact store with the required SQLite safety settings."""
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    connection.execute("PRAGMA busy_timeout = 5000")
    return connection


def migrate(connection: sqlite3.Connection) -> None:
    """Apply the idempotent discovery schema to an empty or existing database."""
    if connection.in_transaction:
        raise RuntimeError("cannot migrate while connection has an active transaction")
    connection.execute("PRAGMA foreign_keys = ON")
    if connection.execute("PRAGMA foreign_keys").fetchone()[0] != 1:
        raise RuntimeError("SQLite foreign key enforcement could not be enabled")
    connection.executescript(_MIGRATION.read_text(encoding="utf-8"))
