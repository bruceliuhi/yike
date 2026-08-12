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
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(_MIGRATION.read_text(encoding="utf-8"))
