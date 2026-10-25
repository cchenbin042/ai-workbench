"""Real SQLite tests for atomicity, replay, isolation and migrations."""
import asyncio
from datetime import datetime
from pathlib import Path
import sqlite3
import threading
import time
import uuid

import pytest

from workbench.contracts import CommandMeta, DomainError
from workbench.storage import Storage, save_draft, get_draft


@pytest.fixture
async def store(tmp_path):
    instance = await Storage.open(tmp_path / "data" / "workbench.sqlite3")
    try:
        yield instance
    finally:
        await instance.close()


def draft(**patch):
    return {"operation_id": str(uuid.uuid4()), "scope_id": "local", "owner_type": "local",
            "owner_id": "79293d59-5845-4544-8b3b-f7ed1b727607", "expected_revision": None,
            "content_json": {"text": "初稿"}, **patch}


def identity(command):
    return {key: command[key] for key in ["scope_id", "owner_type", "owner_id"]}


def operation(**patch):
    return CommandMeta(operation_id="op-1", method="test.write", scope_id="local", **patch)


async def test_open_migrates_and_enables_durable_settings(store):
    assert store.schema_version == 3
    settings = await store.transaction(lambda conn: {
        "wal": conn.execute("PRAGMA journal_mode").fetchone()[0],
        "full": conn.execute("PRAGMA synchronous").fetchone()[0],
        "fk": conn.execute("PRAGMA foreign_keys").fetchone()[0],
        "timeout": conn.execute("PRAGMA busy_timeout").fetchone()[0],
    })
    assert settings == {"wal": "wal", "full": 2, "fk": 1, "timeout": 5000}
    tables = {row["name"] for row in await store.read("SELECT name FROM sqlite_master WHERE type='table'")}
    assert tables == {"schema_migrations", "operations", "drafts", "notes", "tasks", "task_runs",
                      "task_events", "workspaces", "directory_links", "materials", "material_versions"}
    assert (await store.read("PRAGMA integrity_check"))[0]["integrity_check"] == "ok"


async def test_operation_replay_precedes_revision_guard(store):
    command = draft()
    first = await save_draft(command, store)
    await save_draft(draft(expected_revision=first["revision"], content_json={"text": "新稿"}), store)
    assert await save_draft(command, store) == first
    assert (await get_draft(identity(command), store))["content_json"] == {"text": "新稿"}
    meta = operation(expected_revision=1)
    result = await store.write_once(meta, {"value": "first"}, lambda conn: {"revision": 2})
    def must_not_run(conn):
        raise AssertionError("Replay executed the mutation")
    assert await store.write_once(meta, {"value": "first"}, must_not_run) == result


async def test_request_identity_conflicts_do_not_run_mutation(store):
    await store.write_once(operation(), {"one": 1, "two": 2}, lambda conn: {"saved": True})
    assert await store.write_once(operation(), {"two": 2, "one": 1}, lambda conn: {}) == {"saved": True}
    for meta, payload in [
        (operation(), {"one": 9}),
        (CommandMeta(operation_id="op-1", method="other", scope_id="local"), {"one": 1, "two": 2}),
        (CommandMeta(operation_id="op-1", method="test.write", scope_id="other"), {"one": 1, "two": 2}),
        (operation(expected_revision=3), {"one": 1, "two": 2}),
    ]:
        with pytest.raises(DomainError) as error:
            await store.write_once(meta, payload, lambda conn: pytest.fail("Conflict mutated data"))
        assert error.value.code == "OPERATION_CONFLICT"


async def test_result_and_business_change_roll_back_together(store):
    def invalid_result(conn):
        conn.execute("INSERT INTO notes(id,owner_type,owner_id,content_md) VALUES(?,?,?,?)", ("n1", "local", "o1", "private"))
        return {"bad": float("nan")}
    with pytest.raises(DomainError):
        await store.write_once(operation(), {}, invalid_result)
    assert await store.read("SELECT * FROM notes") == []
    assert await store.read("SELECT * FROM operations") == []


async def test_disk_full_rolls_back_operation(store):
    await store.transaction(lambda conn: {"limit": conn.execute("PRAGMA max_page_count=24").fetchone()[0]})
    def fill(conn):
        conn.execute("INSERT INTO notes(id,owner_type,owner_id,content_md) VALUES(?,?,?,?)", ("n1", "local", "o1", "x" * 1024 * 1024))
        return {"saved": True}
    with pytest.raises(DomainError) as error:
        await store.write_once(operation(), {}, fill)
    assert error.value.code == "STORAGE_FULL"
    assert error.value.committed is False
    assert await store.read("SELECT * FROM notes") == []
    assert await store.read("SELECT * FROM operations") == []


async def test_read_cannot_write_even_if_query_only_is_disabled(store):
    with pytest.raises(DomainError):
        await store.read("DELETE FROM notes")
    assert await store.read("SELECT * FROM notes") == []


async def test_drafts_revision_ack_and_concurrent_writes(store):
    command = draft()
    started = time.monotonic()
    first = await save_draft(command, store)
    assert time.monotonic() - started < .8
    uuid.UUID(first["draft_id"])
    assert first["revision"] == 1
    datetime.fromisoformat(first["saved_at"])
    results = await asyncio.gather(*[
        save_draft(draft(expected_revision=1, content_json={"text": text}), store)
        for text in ["A", "B"]
    ], return_exceptions=True)
    assert sum(isinstance(result, dict) for result in results) == 1
    assert [result.code for result in results if isinstance(result, DomainError)] == ["REVISION_CONFLICT"]
    assert len(await store.read("SELECT * FROM operations")) == 2
    assert (await get_draft(identity(command), store))["revision"] == 2


@pytest.mark.parametrize("patch", [
    {"scope_id": "other"}, {"owner_type": "task"}, {"owner_id": ""},
    {"expected_revision": True}, {"content_json": {"number": float("nan")}},
    {"content_json": {"text": "x" * 200001}}, {"secret_ref": "ignored"},
])
async def test_drafts_reject_invalid_or_unowned_scope_before_replay(store, patch):
    command = draft()
    await save_draft(command, store)
    with pytest.raises(DomainError) as error:
        await save_draft(command | patch, store)
    assert error.value.code == -32602
    assert len(await store.read("SELECT * FROM operations")) == 1


async def test_draft_replay_survives_database_reopen(tmp_path):
    path = tmp_path / "data" / "workbench.sqlite3"
    command = draft()
    store = await Storage.open(path)
    first = await save_draft(command, store)
    await store.close()
    store = await Storage.open(path)
    try:
        assert await save_draft(command, store) == first
        assert (await get_draft(identity(command), store))["content_json"] == {"text": "初稿"}
    finally:
        await store.close()


async def test_cancelled_request_does_not_cancel_committed_write_or_close(store):
    started, release = threading.Event(), threading.Event()
    def delayed(conn):
        started.set()
        assert release.wait(timeout=3)
        conn.execute("INSERT INTO notes(id,owner_type,owner_id,content_md) VALUES(?,?,?,?)", ("n1", "local", "o1", "saved"))
        return {"saved": True}
    task = asyncio.create_task(store.write_once(operation(), {}, delayed))
    assert await asyncio.to_thread(started.wait, 2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    release.set()
    await store.close()
    with sqlite3.connect(store.path) as conn:
        assert conn.execute("SELECT content_md FROM notes").fetchone()[0] == "saved"
        assert conn.execute("SELECT count(*) FROM operations").fetchone()[0] == 1


async def test_migration_failure_preserves_backup(tmp_path, monkeypatch):
    import workbench.storage as storage_module
    path = tmp_path / "data" / "workbench.sqlite3"
    migrations = tmp_path / "migrations"
    migrations.mkdir()
    source = Path(storage_module.MIGRATIONS_DIR)
    (migrations / "0001_core.sql").write_bytes((source / "0001_core.sql").read_bytes())
    (migrations / "0002_tasks.sql").write_bytes((source / "0002_tasks.sql").read_bytes())
    monkeypatch.setattr(storage_module, "MIGRATIONS_DIR", migrations)
    store = await Storage.open(path)
    await save_draft(draft(), store)
    await store.close()
    (migrations / "0003_broken.sql").write_text("CREATE TABLE must_rollback(id TEXT);\nINVALID private-token;", encoding="utf-8")
    with pytest.raises(DomainError) as error:
        await Storage.open(path)
    assert error.value.code == "MIGRATION_FAILED"
    assert "private-token" not in str(error.value)
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT max(version) FROM schema_migrations").fetchone()[0] == 2
        assert conn.execute("SELECT name FROM sqlite_master WHERE name='must_rollback'").fetchone() is None
    backups = list((tmp_path / "backups").glob("migration-*/workbench.sqlite3"))
    assert len(backups) == 1
    with sqlite3.connect(backups[0]) as backup:
        assert backup.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert backup.execute("SELECT count(*) FROM drafts").fetchone()[0] == 1


async def test_changed_migration_checksum_refuses_to_write(tmp_path, monkeypatch):
    import workbench.storage as storage_module
    path = tmp_path / "data" / "workbench.sqlite3"
    store = await Storage.open(path)
    await store.close()
    migrations = tmp_path / "migrations"
    migrations.mkdir()
    source = Path(storage_module.MIGRATIONS_DIR)
    (migrations / "0001_core.sql").write_bytes((source / "0001_core.sql").read_bytes() + b"\n-- changed")
    monkeypatch.setattr(storage_module, "MIGRATIONS_DIR", migrations)
    with pytest.raises(DomainError) as error:
        await Storage.open(path)
    assert error.value.code == "MIGRATION_FAILED"


async def test_closed_store_refuses_new_work(store):
    await store.close()
    await store.close()
    with pytest.raises(DomainError) as error:
        await store.transaction(lambda conn: {})
    assert error.value.code == "STORAGE_UNAVAILABLE"


async def test_read_rejects_attached_database_and_mutating_pragmas(store, tmp_path):
    target = tmp_path / "should-not-exist.sqlite3"
    for sql, params in [("ATTACH DATABASE ? AS external", (str(target),)),
                        ("PRAGMA query_only=OFF", ())]:
        with pytest.raises(DomainError) as error:
            await store.read(sql, params)
        assert error.value.code == "STORAGE_UNAVAILABLE"
    assert not target.exists()


async def test_locked_database_rolls_back_and_keeps_event_loop_responsive(store):
    with sqlite3.connect(store.path, isolation_level=None) as blocker:
        blocker.execute("BEGIN IMMEDIATE")
        # Shorten this test's wait without changing the production 5000 ms setting.
        await store._submit(lambda: store._connection.execute("PRAGMA busy_timeout=100").close())
        pending = asyncio.create_task(save_draft(draft(), store))
        await asyncio.sleep(.02)
        assert not pending.done()
        with pytest.raises(DomainError) as error:
            await pending
        assert error.value.code == "STORAGE_UNAVAILABLE"
        assert error.value.committed is False
        blocker.execute("ROLLBACK")
    assert await store.read("SELECT * FROM drafts") == []
    assert await store.read("SELECT * FROM operations") == []
    assert (await save_draft(draft(), store))["revision"] == 1


async def test_writes_share_one_owner_thread_and_async_callbacks_are_rejected(store):
    caller = threading.get_ident()
    identities = await asyncio.gather(*[
        store.transaction(lambda conn: {"thread": threading.get_ident()}) for _ in range(5)
    ])
    assert len({item["thread"] for item in identities}) == 1
    assert identities[0]["thread"] != caller
    async def wrong(conn):
        return {}
    with pytest.raises(DomainError):
        await store.transaction(wrong)
    assert (await save_draft(draft(), store))["revision"] == 1


async def test_successful_upgrade_backs_up_wal_and_retains_five_snapshots(tmp_path, monkeypatch):
    import hashlib
    import json
    import workbench.storage as storage_module
    path = tmp_path / "data" / "workbench.sqlite3"
    backups = tmp_path / "backups"
    for index in range(6):
        directory = backups / f"migration-20000101-{index}"
        directory.mkdir(parents=True)
        (directory / "manifest.json").write_text("{}")
        (directory / "workbench.sqlite3").write_bytes(b"old")
    manual = backups / "manual-kept"
    manual.mkdir()
    (manual / "workbench.sqlite3").write_bytes(b"manual")
    migrations = tmp_path / "migrations"
    migrations.mkdir()
    (migrations / "0001_core.sql").write_bytes((storage_module.MIGRATIONS_DIR / "0001_core.sql").read_bytes())
    (migrations / "0002_tasks.sql").write_bytes((storage_module.MIGRATIONS_DIR / "0002_tasks.sql").read_bytes())
    monkeypatch.setattr(storage_module, "MIGRATIONS_DIR", migrations)
    store = await Storage.open(path)
    assert store.schema_version == 2
    await store.close()
    with sqlite3.connect(path, isolation_level=None) as writer:
        writer.execute("PRAGMA journal_mode=WAL")
        writer.execute("PRAGMA wal_autocheckpoint=0")
        writer.execute("INSERT INTO notes(id,owner_type,owner_id,content_md) VALUES('n1','local','o1','wal content')")
        assert Path(str(path) + "-wal").stat().st_size > 0
    (migrations / "0003_next.sql").write_text("CREATE TABLE upgrade_probe(id TEXT PRIMARY KEY) STRICT;")
    store = await Storage.open(path)
    assert store.schema_version == 3
    await store.close()
    snapshots = sorted(backups.glob("migration-*"))
    assert len(snapshots) == 5
    assert manual.is_dir()
    latest = snapshots[-1]
    with sqlite3.connect(latest / "workbench.sqlite3") as conn:
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert conn.execute("SELECT content_md FROM notes").fetchone()[0] == "wal content"
        assert conn.execute("SELECT max(version) FROM schema_migrations").fetchone()[0] == 2
    manifest = json.loads((latest / "manifest.json").read_text())
    from importlib.metadata import version
    assert manifest["schema_version"] == 2
    assert manifest["app_version"] == version("zhixu-workbench")
    assert manifest["protocol_version"] == 1
    assert manifest["kind"] == "migration"
    assert manifest["attachment_ids"] == []
    assert manifest["includes_attachments"] is False
    assert manifest["sha256"] == hashlib.sha256((latest / "workbench.sqlite3").read_bytes()).hexdigest()


async def test_backup_cleanup_failure_does_not_reverse_successful_migration(tmp_path, monkeypatch):
    import workbench.storage as storage_module
    path = tmp_path / "data" / "workbench.sqlite3"
    migrations = tmp_path / "migrations"
    migrations.mkdir()
    (migrations / "0001_core.sql").write_bytes((storage_module.MIGRATIONS_DIR / "0001_core.sql").read_bytes())
    (migrations / "0002_tasks.sql").write_bytes((storage_module.MIGRATIONS_DIR / "0002_tasks.sql").read_bytes())
    monkeypatch.setattr(storage_module, "MIGRATIONS_DIR", migrations)
    store = await Storage.open(path)
    await store.close()
    (migrations / "0003_next.sql").write_text("CREATE TABLE upgrade_probe(id TEXT PRIMARY KEY) STRICT;")
    def fail_cleanup(self):
        raise OSError("private-token")
    monkeypatch.setattr(Storage, "_prune_backups", fail_cleanup)
    store = await Storage.open(path)
    assert store.schema_version == 3
    assert await store.read("SELECT * FROM upgrade_probe") == []
    await store.close()


async def test_readonly_writer_cannot_leave_successful_operations(store):
    def reopen_readonly():
        store._connection.close()
        store._connection = sqlite3.connect(store.path.as_uri() + "?mode=ro", uri=True, isolation_level=None)
        store._connection.row_factory = sqlite3.Row
    await store._submit(reopen_readonly)
    with pytest.raises(DomainError) as error:
        await save_draft(draft(), store)
    assert error.value.code == "STORAGE_UNAVAILABLE"
    assert error.value.committed is False
    assert await store.read("SELECT * FROM operations") == []
    assert await store.read("SELECT * FROM drafts") == []


async def test_newer_database_refuses_downgrade_without_modifying_data(tmp_path):
    path = tmp_path / "data" / "workbench.sqlite3"
    store = await Storage.open(path)
    await save_draft(draft(), store)
    await store.close()
    with sqlite3.connect(path) as conn:
        conn.execute("INSERT INTO schema_migrations(version,checksum,applied_at) VALUES(4,?,?)",
                     ("a" * 64, "2026-10-18T00:00:00+00:00"))
    with pytest.raises(DomainError) as error:
        await Storage.open(path)
    assert error.value.code == "MIGRATION_FAILED"
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT max(version) FROM schema_migrations").fetchone()[0] == 4
        assert conn.execute("SELECT count(*) FROM drafts").fetchone()[0] == 1


async def test_cancelled_callback_rolls_back_before_next_transaction(store):
    def cancelled(conn):
        conn.execute("INSERT INTO notes(id,owner_type,owner_id,content_md) VALUES('n1','local','o1','discard')")
        raise asyncio.CancelledError
    with pytest.raises(asyncio.CancelledError):
        await store.transaction(cancelled)
    assert (await save_draft(draft(), store))["revision"] == 1
    assert await store.read("SELECT * FROM notes") == []
