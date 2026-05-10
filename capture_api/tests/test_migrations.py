from __future__ import annotations

from pathlib import Path

from app.db import connect, run_migrations


def test_creates_schema_on_empty_db(tmp_path: Path) -> None:
    db = tmp_path / "queue.db"
    conn = connect(db)
    applied = run_migrations(conn)
    assert applied == ["001_initial.sql"]
    tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }
    assert {"queue", "_migrations"} <= tables
    conn.close()


def test_idempotent_on_already_migrated(tmp_path: Path) -> None:
    db = tmp_path / "queue.db"
    conn = connect(db)
    run_migrations(conn)
    second = run_migrations(conn)
    assert second == []
    conn.close()


def test_new_migration_runs_exactly_once(tmp_path: Path) -> None:
    db = tmp_path / "queue.db"
    migrations = tmp_path / "migrations"
    migrations.mkdir()

    (migrations / "001_initial.sql").write_text(
        "CREATE TABLE foo (id INTEGER PRIMARY KEY);"
    )

    conn = connect(db)
    assert run_migrations(conn, migrations) == ["001_initial.sql"]

    (migrations / "002_extra.sql").write_text(
        "CREATE TABLE bar (id INTEGER PRIMARY KEY);"
    )
    assert run_migrations(conn, migrations) == ["002_extra.sql"]

    # Third call: nothing applied.
    assert run_migrations(conn, migrations) == []

    rows = list(conn.execute("SELECT filename FROM _migrations ORDER BY filename"))
    assert [r[0] for r in rows] == ["001_initial.sql", "002_extra.sql"]
    conn.close()
