from dataclasses import dataclass
from datetime import UTC, datetime
import sqlite3
from threading import RLock

import pytest


@dataclass
class DiscoveryClock:
    value: datetime = datetime(2026, 8, 12, 8, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.value


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "native_clock: retain real Python and native SQLite clocks"
    )


@pytest.fixture
def discovery_clock(monkeypatch, request):
    """Align legacy August fixtures without altering production time gates.

    Opt in at the test/module level; native_clock counterexamples opt out.
    Explicit clocks passed by individual tests still control their timelines.
    Only SQLite's current-time input is replaced: its native implementation
    remains responsible for parsing, formatting, modifiers and invalid dates.
    """
    if request.node.get_closest_marker("native_clock"):
        yield None
        return

    from app import db, metrics, repository, web, workflow

    clock = DiscoveryClock()

    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            instant = clock()
            if tz is None:
                return instant.astimezone().replace(tzinfo=None)
            return instant.astimezone(tz)

    # HTTP handlers and race tests open connections on worker threads. Keep the
    # native date evaluator separate from application connections and serialize
    # its use, so the shim neither recurses nor shares an application transaction.
    native = sqlite3.connect(":memory:", check_same_thread=False)
    native_lock = RLock()
    register_functions = db._register_functions

    def strftime(*arguments):
        if len(arguments) == 1:
            arguments += (clock().isoformat(),)
        elif len(arguments) > 1 and isinstance(arguments[1], str):
            if arguments[1].lower() == "now":
                arguments = (arguments[0], clock().isoformat(), *arguments[2:])
        placeholders = ",".join("?" for _ in arguments)
        with native_lock:
            return native.execute(
                f"SELECT strftime({placeholders})", arguments
            ).fetchone()[0]

    def register_clock(connection):
        register_functions(connection)
        connection.create_function("strftime", -1, strftime)

    monkeypatch.setattr(db, "_register_functions", register_clock)
    for module in (repository, metrics, web):
        monkeypatch.setattr(module, "datetime", FrozenDateTime)
    monkeypatch.setattr(workflow, "_system_now", clock)
    try:
        yield clock
    finally:
        native.close()
