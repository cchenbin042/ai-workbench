"""Exercise task state transitions and cancellation against real SQLite."""
import asyncio
import sqlite3
import uuid

import pytest

from workbench.contracts import DomainError
from workbench.storage import Storage
from workbench.tasks import TaskService


def command(**patch):
    return {"operation_id": str(uuid.uuid4()), "task_type": "generic",
            "workspace_id": None, "agent_config_version_id": None,
            "material_version_ids": [], "input": {"text": "input"}, **patch}


async def no_flow(service, task_id, run_id):
    await service.commit_run(task_id, run_id, lambda conn: {})


@pytest.fixture
async def service(tmp_path):
    store = await Storage.open(tmp_path / "data" / "workbench.sqlite3")
    events = []
    tasks = TaskService(store, handlers={"generic": no_flow}, on_event=events.append)
    try:
        yield tasks, store, events
    finally:
        await tasks.close()
        await store.close()


async def test_create_replays_original_snapshot_after_task_advances(service):
    tasks, store, events = service
    request = command()
    first = await tasks.create(request)
    assert first["status"] == "queued" and first["revision"] == 1
    uuid.UUID(first["task_id"])
    run = await tasks.start(first["task_id"])
    assert await tasks.create(request) == first
    with pytest.raises(DomainError) as error:
        await tasks.create({**request, "input": {"changed": True}})
    assert error.value.code == "OPERATION_CONFLICT"
    assert len(await store.read("SELECT * FROM tasks")) == 1
    assert (await tasks.get(first["task_id"]))["active_run_id"] == run


async def test_cancel_fences_late_commit(service):
    tasks, store, events = service
    task = await tasks.create(command())
    run = await tasks.start(task["task_id"])
    cancelled = await tasks.cancel(task["task_id"])
    assert cancelled["active_run_id"] is None
    def late(conn):
        conn.execute("INSERT INTO notes(id,owner_type,owner_id,content_md) VALUES('late','local','o1','late')")
        return {}
    with pytest.raises(DomainError) as error:
        await tasks.commit_run(task["task_id"], run, late)
    assert error.value.code == "STALE_RUN"
    assert await store.read("SELECT * FROM notes") == []
    assert (await tasks.get(task["task_id"]))["status"] == "cancelled"


async def test_result_that_commits_before_cancel_is_preserved(service):
    tasks, store, events = service
    task = await tasks.create(command())
    run = await tasks.start(task["task_id"])
    def save(conn):
        conn.execute("INSERT INTO notes(id,owner_type,owner_id,content_md) VALUES('n1','local','o1','saved')")
        return {"note_id": "n1"}
    result = await tasks.commit_run(task["task_id"], run, save)
    assert result["result"] == {"note_id": "n1"}
    assert (await tasks.cancel(task["task_id"]))["status"] == "completed"
    assert (await store.read("SELECT content_md FROM notes"))[0]["content_md"] == "saved"


async def test_fifo_and_waiting_user_release_slot(service):
    tasks, store, events = service
    first = await tasks.create(command())
    second = await tasks.create(command())
    with pytest.raises(DomainError) as error:
        await tasks.start(second["task_id"])
    assert error.value.code == "NOT_NEXT_TASK"
    run = await tasks.start(first["task_id"])
    with pytest.raises(DomainError) as error:
        await tasks.start(second["task_id"])
    assert error.value.code == "EXECUTION_BUSY"
    waiting = await tasks.commit_run(first["task_id"], run, lambda conn: {},
                                   status="waiting_user", waiting_reason="review_artifact",
                                   checkpoint={"artifact_id": "a1"})
    assert waiting["task"]["waiting_reason"] == "review_artifact"
    assert waiting["task"]["active_run_id"] is None
    assert await tasks.start(second["task_id"]) != run


async def test_snapshot_then_events_has_no_gap(service):
    tasks, store, events = service
    task = await tasks.create(command())
    snapshot = await tasks.get(task["task_id"])
    assert snapshot["last_seq"] == 1
    run = await tasks.start(task["task_id"])
    await tasks.commit_run(task["task_id"], run, lambda conn: {})
    delta = await tasks.list_events(task["task_id"], snapshot["last_seq"])
    assert [event["seq"] for event in delta] == [2, 3]
    assert [event["type"] for event in delta] == ["step.started", "step.completed"]
    assert (await tasks.get(task["task_id"]))["last_seq"] == 3
    assert [event["seq"] for event in events] == [1, 2, 3]
    assert len({event["service_instance_id"] for event in events}) == 1


async def test_business_failure_rolls_back_status_and_events(service):
    tasks, store, events = service
    task = await tasks.create(command())
    run = await tasks.start(task["task_id"])
    def fail(conn):
        conn.execute("INSERT INTO notes(id,owner_type,owner_id,content_md) VALUES('n1','local','o1','discard')")
        raise ValueError("private-token")
    with pytest.raises(DomainError) as error:
        await tasks.commit_run(task["task_id"], run, fail)
    assert "private-token" not in str(error.value)
    current = await tasks.get(task["task_id"])
    assert current["status"] == "running" and current["last_seq"] == 2
    assert await store.read("SELECT * FROM notes") == []
    assert [event["seq"] for event in events] == [1, 2]


async def test_commands_replay_before_revision_checks(service):
    tasks, store, events = service
    task = await tasks.create(command())
    operation_id = str(uuid.uuid4())
    first = await tasks.cancel(task["task_id"], operation_id=operation_id, expected_revision=1)
    assert first["status"] == "cancelled"
    assert await tasks.cancel(task["task_id"], operation_id=operation_id, expected_revision=1) == first
    with pytest.raises(DomainError) as error:
        await tasks.cancel(task["task_id"], operation_id=str(uuid.uuid4()), expected_revision=1)
    assert error.value.code == "REVISION_CONFLICT"


async def test_continue_requires_matching_reason_and_immutable_input(service):
    tasks, store, events = service
    task = await tasks.create(command())
    run = await tasks.start(task["task_id"])
    await tasks.commit_run(task["task_id"], run, lambda conn: {}, status="waiting_user",
                           waiting_reason="review_artifact", checkpoint={"artifact_id": "a1"})
    with pytest.raises(DomainError) as error:
        await tasks.continue_task(task["task_id"], action="answer_question", input={})
    assert error.value.code == "INVALID_TASK_ACTION"
    queued = await tasks.continue_task(task["task_id"], action="review_artifact", input={"approved": True})
    assert queued["status"] == "queued"
    assert queued["input"] == {"text": "input"}
    assert queued["checkpoint"]["continuation"] == {"action": "review_artifact", "input": {"approved": True}}
    assert await tasks.start(task["task_id"]) != run


async def test_worker_runs_one_flow_at_a_time_in_fifo_order(service):
    tasks, store, events = service
    started = asyncio.Queue()
    release = asyncio.Event()
    active = 0
    maximum = 0
    async def flow(service, task_id, run_id):
        nonlocal active, maximum
        active += 1
        maximum = max(maximum, active)
        await started.put(task_id)
        await release.wait()
        active -= 1
        await service.commit_run(task_id, run_id, lambda conn: {})
    tasks.handlers["generic"] = flow
    one, two = await tasks.create(command()), await tasks.create(command())
    tasks.start_worker()
    assert await asyncio.wait_for(started.get(), 2) == one["task_id"]
    assert started.empty()
    release.set()
    assert await asyncio.wait_for(started.get(), 2) == two["task_id"]
    async with asyncio.timeout(2):
        while (await tasks.get(two["task_id"]))["status"] != "completed":
            await asyncio.sleep(.01)
    assert maximum == 1


async def test_waiting_user_releases_slot(service):
    tasks, store, events = service
    started = asyncio.Queue()
    async def flow(service, task_id, run_id):
        await service.commit_run(task_id, run_id, lambda conn: {}, status="waiting_user",
                                 waiting_reason="review_artifact", checkpoint={"saved": True})
        await started.put(task_id)
    tasks.handlers["generic"] = flow
    one, two = await tasks.create(command()), await tasks.create(command())
    tasks.start_worker()
    assert await asyncio.wait_for(started.get(), 2) == one["task_id"]
    assert await asyncio.wait_for(started.get(), 2) == two["task_id"]
    assert (await tasks.get(one["task_id"]))["status"] == "waiting_user"


@pytest.mark.parametrize("patch", [{"workspace_id": "forged"}, {"agent_config_version_id": "forged"},
                                   {"material_version_ids": ["forged"]}, {"extra": "private-token"},
                                   {"input": {"number": float("nan")}}])
async def test_unavailable_references_and_invalid_input_never_create_tasks(service, patch):
    tasks, store, events = service
    with pytest.raises(DomainError) as error:
        await tasks.create(command(**patch))
    assert error.value.code == -32602
    assert await store.read("SELECT * FROM tasks") == []
    assert await store.read("SELECT * FROM operations") == []


async def test_missing_flow_is_not_exposed_as_a_fake_agent(service):
    tasks, store, events = service
    with pytest.raises(DomainError) as error:
        await tasks.create(command(task_type="question_generation"))
    assert error.value.code == "FLOW_UNAVAILABLE"
    assert await store.read("SELECT * FROM tasks") == []


async def test_task_events_are_committed_before_publish(service):
    tasks, store, events = service
    def published(event):
        with sqlite3.connect(store.path) as conn:
            assert conn.execute("SELECT seq FROM task_events WHERE event_id=?", (event["event_id"],)).fetchone()[0] == event["seq"]
        events.append(event)
    tasks.on_event = published
    task = await tasks.create(command())
    assert events[0]["task_id"] == task["task_id"]


async def test_cancel_rejects_late_result_before_releasing_execution_slot(service):
    tasks, store, events = service
    started, cancelled, release, next_started = (asyncio.Event() for _ in range(4))
    late_errors = []
    first_id = None
    async def flow(service, task_id, run_id):
        if task_id != first_id:
            next_started.set()
            await service.commit_run(task_id, run_id, lambda conn: {})
            return
        started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.set()
            await release.wait()
            try:
                await service.commit_run(task_id, run_id, lambda conn: {"late": True})
            except DomainError as error:
                late_errors.append(error.code)
    tasks.handlers["generic"] = flow
    one = await tasks.create(command())
    first_id = one["task_id"]
    two = await tasks.create(command())
    tasks.start_worker()
    await asyncio.wait_for(started.wait(), 2)
    result = await tasks.cancel(first_id)
    assert result["active_run_id"] is None
    await asyncio.wait_for(cancelled.wait(), 2)
    assert not next_started.is_set()
    assert (await tasks.get(first_id))["status"] == "cancelling"
    release.set()
    await asyncio.wait_for(next_started.wait(), 2)
    assert late_errors == ["STALE_RUN"]
    assert (await tasks.get(first_id))["status"] == "cancelled"


async def test_handler_failure_is_sanitized_and_next_task_runs(service):
    tasks, store, events = service
    first_id = None
    async def fail_first(service, task_id, run_id):
        if task_id == first_id:
            raise RuntimeError("private-token")
        await service.commit_run(task_id, run_id, lambda conn: {})
    tasks.handlers["generic"] = fail_first
    first = await tasks.create(command())
    first_id = first["task_id"]
    second = await tasks.create(command())
    tasks.start_worker()
    async with asyncio.timeout(2):
        while (await tasks.get(second["task_id"]))["status"] != "completed":
            await asyncio.sleep(.01)
    assert (await tasks.get(first_id))["status"] == "failed"
    assert "private-token" not in str(await tasks.list_events(first_id))
    assert "private-token" not in str(await store.read("SELECT error_json FROM task_runs"))
    retried = await tasks.resume(first_id)
    assert retried["status"] == "queued"


async def test_event_delivery_failure_keeps_committed_operation_replayable(service):
    tasks, store, events = service
    def unavailable(event):
        raise RuntimeError("private-token")
    tasks.on_event = unavailable
    request = command()
    result = await tasks.create(request)
    assert await tasks.create(request) == result
    assert [event["seq"] for event in await tasks.list_events(result["task_id"])] == [1]
    operation = await tasks.get_operation(operation_id=request["operation_id"])
    assert operation["committed"] is True and operation["result"] == result


async def test_cancelled_rpc_waiter_does_not_lose_durable_task_creation(service):
    tasks, store, events = service
    import threading
    entered, release = threading.Event(), threading.Event()
    def hold(conn):
        entered.set()
        assert release.wait(2)
        return {}
    blocker = asyncio.create_task(store.transaction(hold))
    assert await asyncio.to_thread(entered.wait, 1)
    request = command()
    pending = asyncio.create_task(tasks.create(request))
    await asyncio.sleep(.02)
    pending.cancel()
    with pytest.raises(asyncio.CancelledError):
        await pending
    release.set()
    await blocker
    await tasks.close()
    rows = await store.read("SELECT status FROM tasks")
    assert rows == [{"status": "interrupted"}]
    assert len(await store.read("SELECT * FROM operations WHERE operation_id=?", (request["operation_id"],))) == 1


async def test_event_pagination_and_invalid_limits(service):
    tasks, store, events = service
    task = await tasks.create(command())
    run = await tasks.start(task["task_id"])
    await tasks.commit_run(task["task_id"], run, lambda conn: {})
    page = await tasks.list_events(task["task_id"], 0, limit=2)
    assert [event["seq"] for event in page] == [1, 2]
    assert [event["seq"] for event in await tasks.list_events(task["task_id"], 2)] == [3]
    for patch in [{"limit": 201}, {"limit": True}, {"after_seq": -1}]:
        with pytest.raises(DomainError) as error:
            await tasks.list_events(task["task_id"], **patch)
        assert error.value.code == -32602


async def test_out_of_scope_task_cannot_replay_previous_command(service):
    tasks, store, events = service
    task = await tasks.create(command())
    operation_id = str(uuid.uuid4())
    await tasks.cancel(task["task_id"], operation_id=operation_id, expected_revision=1)
    await store.transaction(lambda conn: {"updated": conn.execute("UPDATE tasks SET scope_snapshot_json=? WHERE id=?",
                                    ('{"scope_id":"other"}', task["task_id"])).rowcount})
    with pytest.raises(DomainError) as error:
        await tasks.cancel(task["task_id"], operation_id=operation_id, expected_revision=1)
    assert error.value.code == "SOURCE_OUT_OF_SCOPE"
    # Teardown only scans transient states, so this deliberately altered terminal
    # row does not require access to a different workspace.


async def test_close_interrupts_running_and_queued_but_preserves_checkpoint(service):
    tasks, store, events = service
    entered = asyncio.Event()
    async def wait(service, task_id, run_id):
        entered.set()
        await asyncio.Event().wait()
    tasks.handlers["generic"] = wait
    first = await tasks.create(command())
    second = await tasks.create(command())
    tasks.start_worker()
    await asyncio.wait_for(entered.wait(), 2)
    await tasks.close()
    assert (await tasks.get(first["task_id"]))["status"] == "interrupted"
    assert (await tasks.get(second["task_id"]))["status"] == "interrupted"
    await tasks.close()
    with pytest.raises(DomainError) as error:
        await tasks.create(command())
    assert error.value.code == "SERVICE_STOPPING"


async def test_replayed_cancel_after_recovery_never_cancels_new_run(service, monkeypatch):
    tasks, store, events = service
    task = await tasks.create(command())
    await tasks.start(task["task_id"])
    original_finish = tasks._finish_cancel
    async def lost_cleanup(task_id):
        pass  # Model process loss after committing the cancel operation.
    monkeypatch.setattr(tasks, "_finish_cancel", lost_cleanup)
    cancel_id = str(uuid.uuid4())
    original = await tasks.cancel(task["task_id"], operation_id=cancel_id, expected_revision=2)
    assert original["status"] == "cancelling"
    monkeypatch.setattr(tasks, "_finish_cancel", original_finish)
    await tasks.recover_startup()
    queued = await tasks.resume(task["task_id"])
    entered, release, interrupted = asyncio.Event(), asyncio.Event(), asyncio.Event()
    async def resumed(service, task_id, run_id):
        entered.set()
        try:
            await release.wait()
        except asyncio.CancelledError:
            interrupted.set()
            raise
        await service.commit_run(task_id, run_id, lambda conn: {})
    tasks.handlers["generic"] = resumed
    tasks.start_worker()
    await asyncio.wait_for(entered.wait(), 2)
    current = await tasks.get(task["task_id"])
    assert await tasks.cancel(task["task_id"], operation_id=cancel_id, expected_revision=2) == original
    await asyncio.sleep(.02)
    assert not interrupted.is_set()
    assert (await tasks.get(task["task_id"]))["active_run_id"] == current["active_run_id"]
    release.set()


async def test_temporary_database_lock_does_not_kill_queue_worker(service):
    tasks, store, events = service
    entered = asyncio.Event()
    async def flow(service, task_id, run_id):
        entered.set()
        await service.commit_run(task_id, run_id, lambda conn: {})
    tasks.handlers["generic"] = flow
    first = await tasks.create(command())
    await store._submit(lambda: store._connection.execute("PRAGMA busy_timeout=20").close())
    with sqlite3.connect(store.path, isolation_level=None) as blocker:
        blocker.execute("BEGIN IMMEDIATE")
        tasks.start_worker()
        await asyncio.sleep(.1)
        assert not entered.is_set()
        blocker.execute("ROLLBACK")
    await asyncio.wait_for(entered.wait(), 2)
    async with asyncio.timeout(2):
        while (await tasks.get(first["task_id"]))["status"] != "completed":
            await asyncio.sleep(.01)
    assert tasks._worker is not None and not tasks._worker.done()


async def test_cancel_during_run_start_never_starts_handler_after_cancel_ack(service, monkeypatch):
    tasks, store, events = service
    committed, release, handler_started = asyncio.Event(), asyncio.Event(), asyncio.Event()
    task = await tasks.create(command())
    original = tasks.start
    async def delayed_start(task_id):
        run_id = await original(task_id)
        committed.set()
        await release.wait()
        return run_id
    monkeypatch.setattr(tasks, "start", delayed_start)
    cancelled_ack = False
    called_after_ack = []
    async def flow(service, task_id, run_id):
        called_after_ack.append(cancelled_ack)
        handler_started.set()
        await asyncio.Event().wait()
    tasks.handlers["generic"] = flow
    tasks.start_worker()
    await asyncio.wait_for(committed.wait(), 2)
    pending = asyncio.create_task(tasks.cancel(task["task_id"]))
    # Allow either ordering: cancellation may wait for slot registration, or it
    # may fence the new run immediately and prevent handler startup entirely.
    await asyncio.sleep(.03)
    if pending.done():
        await pending
        cancelled_ack = True
    release.set()
    await asyncio.wait_for(pending, 2)
    cancelled_ack = True
    await asyncio.sleep(.03)
    assert True not in called_after_ack
    assert (await tasks.get(task["task_id"]))["status"] == "cancelled"


async def test_storage_lock_during_flow_failure_does_not_replay_flow_or_stall_queue(service):
    tasks, store, events = service
    entered, fail_now, next_started = asyncio.Event(), asyncio.Event(), asyncio.Event()
    first_id = None
    attempts = []
    async def flow(service, task_id, run_id):
        attempts.append(task_id)
        if task_id == first_id:
            entered.set()
            await fail_now.wait()
            raise RuntimeError("private-token")
        next_started.set()
        await service.commit_run(task_id, run_id, lambda conn: {})
    tasks.handlers["generic"] = flow
    first = await tasks.create(command())
    first_id = first["task_id"]
    second = await tasks.create(command())
    await store._submit(lambda: store._connection.execute("PRAGMA busy_timeout=20").close())
    tasks.start_worker()
    await asyncio.wait_for(entered.wait(), 2)
    with sqlite3.connect(store.path, isolation_level=None) as blocker:
        blocker.execute("BEGIN IMMEDIATE")
        fail_now.set()
        await asyncio.sleep(.1)
        assert not next_started.is_set()
        blocker.execute("ROLLBACK")
    await asyncio.wait_for(next_started.wait(), 2)
    assert (await tasks.get(first_id))["status"] == "failed"
    assert attempts == [first_id, second["task_id"]]
