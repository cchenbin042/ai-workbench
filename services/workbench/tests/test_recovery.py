"""Crash recovery preserves durable checkpoints and never restarts work."""
import asyncio
import pytest
from workbench.storage import Storage
from workbench.tasks import TaskService
from test_tasks import command, no_flow


async def test_restart_never_replays_queued(tmp_path):
    path = tmp_path / "data" / "workbench.sqlite3"
    store = await Storage.open(path)
    service = TaskService(store, handlers={"generic": no_flow})
    request = command()
    first = await service.create(request)
    # Closing only the database models process loss before service cleanup.
    await store.close()
    store = await Storage.open(path)
    called = []
    async def unexpected(*args):
        called.append(args)
    recovered = TaskService(store, handlers={"generic": unexpected})
    try:
        changes = await recovered.recover_startup()
        assert [task["task_id"] for task in changes] == [first["task_id"]]
        assert changes[0]["status"] == "interrupted"
        assert await recovered.create(request) == first
        recovered.start_worker()
        await asyncio.sleep(.03)
        assert called == []
        queued = await recovered.resume(first["task_id"])
        assert queued["status"] == "queued"
    finally:
        await recovered.close()
        await store.close()


async def test_recovery_invalidates_old_run_but_preserves_waiting_user(tmp_path):
    from workbench.contracts import DomainError
    path = tmp_path / "data" / "workbench.sqlite3"
    store = await Storage.open(path)
    service = TaskService(store, handlers={"generic": no_flow})
    waiting = await service.create(command())
    run = await service.start(waiting["task_id"])
    await service.commit_run(waiting["task_id"], run, lambda conn: {}, status="waiting_user",
                             waiting_reason="review_artifact", checkpoint={"artifact_id": "a1"})
    running = await service.create(command())
    old_run = await service.start(running["task_id"])
    await store.close()
    store = await Storage.open(path)
    recovered = TaskService(store, handlers={"generic": no_flow})
    try:
        assert len(await recovered.recover_startup()) == 1
        snapshot = await recovered.get(waiting["task_id"])
        assert snapshot["status"] == "waiting_user"
        assert snapshot["checkpoint"] == {"artifact_id": "a1"}
        assert snapshot["waiting_reason"] == "review_artifact"
        with pytest.raises(DomainError) as error:
            await recovered.commit_run(running["task_id"], old_run, lambda conn: {})
        assert error.value.code == "STALE_RUN"
        assert await recovered.recover_startup() == []
        assert (await store.read("SELECT state FROM task_runs WHERE id=?", (old_run,)))[0]["state"] == "interrupted"
    finally:
        await recovered.close()
        await store.close()


async def test_recovery_preserves_cancelling_run_history(tmp_path):
    path = tmp_path / "data" / "workbench.sqlite3"
    store = await Storage.open(path)
    service = TaskService(store, handlers={"generic": no_flow})
    task = await service.create(command())
    run = await service.start(task["task_id"])
    def revoke(conn):
        conn.execute("UPDATE tasks SET status='cancelling',active_run_id=NULL,revision=revision+1 WHERE id=?", (task["task_id"],))
        conn.execute("UPDATE task_runs SET state='revoked' WHERE id=?", (run,))
        return {}
    await store.transaction(revoke)
    await store.close()
    store = await Storage.open(path)
    recovered = TaskService(store)
    try:
        assert (await recovered.recover_startup())[0]["status"] == "interrupted"
        assert (await store.read("SELECT state,ended_at FROM task_runs WHERE id=?", (run,)))[0]["state"] == "interrupted"
        assert (await recovered.get(task["task_id"]))["active_run_id"] is None
    finally:
        await recovered.close()
        await store.close()
