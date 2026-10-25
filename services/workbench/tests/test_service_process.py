"""Real pipes catch blocked stdin, fragmented reads and protocol pollution."""
import json
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time
import uuid

import pytest


@pytest.fixture
def service(tmp_path):
    processes = []
    def start(helper=False):
        command = [sys.executable, "-u"]
        command += [str(Path(__file__).with_name("process_helper.py"))] if helper else ["-m", "workbench"]
        process = subprocess.Popen(command + ["--data-dir",str(tmp_path / "data space")], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        responses = queue.Queue()
        def read():
            for line in process.stdout:
                responses.put(json.loads(line))
        threading.Thread(target=read,daemon=True).start()
        processes.append(process)
        return process, responses
    yield start
    for process in processes:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=5)
        for stream in [process.stdin,process.stdout,process.stderr]:
            stream.close()


def send(process, method, id=1, **extra):
    process.stdin.write((json.dumps({"jsonrpc":"2.0","method":method,"id":id,**extra})+"\n").encode())
    process.stdin.flush()


def test_initialize_ping_shutdown_with_stdin_still_open(service):
    process, responses = service()
    send(process,"system.initialize")
    result = responses.get(timeout=4)["result"]
    assert result["protocol_version"] == 1 and result["schema_version"] == 4
    uuid.UUID(result["service_instance_id"])
    assert "system.shutdown" in result["capabilities"]
    send(process,"system.initialize",id=2)
    assert responses.get(timeout=3)["result"]["service_instance_id"] == result["service_instance_id"]
    send(process,"system.ping",id=3)
    assert responses.get(timeout=3)["result"]["status"] == "ok"
    send(process,"system.shutdown",id=4)
    assert responses.get(timeout=3) == {"jsonrpc":"2.0","id":4,"result":{"status":"shutting_down"}}
    assert process.wait(timeout=3) == 0
    assert process.stderr.read() == b""


def test_eof_exits_and_flushes_pending_request(service):
    process, responses = service()
    send(process,"system.ping")
    process.stdin.close()
    assert responses.get(timeout=3)["result"]["status"] == "ok"
    assert process.wait(timeout=3) == 0


def test_fragmented_utf8_bad_then_valid_and_multiple_requests(service):
    process, responses = service()
    wire = '{"jsonrpc":"2.0","method":"不存在","id":1}\n'.encode()
    split = wire.index("不".encode())+1
    process.stdin.write(wire[:split]); process.stdin.flush()
    process.stdin.write(wire[split:] + b'bad secret\n' + b'{"jsonrpc":"2.0","method":"system.ping","id":2}\n' + b'[]\n')
    process.stdin.flush()
    results = [responses.get(timeout=3) for _ in range(4)]
    assert sorted(r["error"]["code"] for r in results if "error" in r) == [-32700,-32601,-32600]
    assert next(r for r in results if r["id"] == 2)["result"]["status"] == "ok"
    assert "secret" not in json.dumps(results)
    send(process,"system.shutdown")
    assert process.wait(timeout=3) == 0


def test_slow_request_ping_and_shutdown_share_actual_read_write_lifecycle(service):
    process, responses = service(helper=True)
    send(process, "system.initialize", id=0)
    assert responses.get(timeout=4)["id"] == 0
    send(process,"test.block",id=1)
    send(process,"test.slow",id=2)
    send(process,"system.ping",id=3)
    assert responses.get(timeout=.5)["id"] == 3
    assert responses.get(timeout=2) == {"jsonrpc":"2.0","id":2,"result":"slow"}
    send(process,"system.shutdown",id=4)
    assert responses.get(timeout=2)["id"] == 4
    assert process.wait(timeout=3) == 0


def test_startup_diagnostics_are_stderr_only(service,tmp_path):
    invalid = tmp_path/"a-file"
    invalid.write_text("private")
    process = subprocess.run([sys.executable,"-u","-m","workbench","--data-dir",str(invalid)],input=b"",capture_output=True,timeout=3)
    assert process.returncode != 0 and process.stdout == b""
    assert b"Unable to start backend" in process.stderr
    assert b"private" not in process.stderr


def test_oversize_frame_recovers_before_next_valid_request(service):
    process, responses = service()
    process.stdin.write(b"x" * (8 * 1024 * 1024 + 1) + b"\n")
    process.stdin.flush()
    assert responses.get(timeout=4)["error"]["code"] == -32600
    send(process, "system.ping", id=2)
    assert responses.get(timeout=3)["result"]["ok"] is True
    send(process, "system.shutdown", id=3)
    assert process.wait(timeout=3) == 0


def test_notification_shutdown_exits_without_response(service):
    process, responses = service()
    process.stdin.write(b'{"jsonrpc":"2.0","method":"system.shutdown"}\n')
    process.stdin.flush()
    assert process.wait(timeout=3) == 0
    assert responses.empty()


def test_invalid_shutdown_does_not_stop_service_or_echo_params(service):
    process, responses = service()
    send(process, "system.shutdown", params={"secret": "private-token"})
    assert responses.get(timeout=3)["error"]["code"] == -32602
    send(process, "system.ping", id=2)
    assert responses.get(timeout=3)["result"]["ok"] is True
    send(process, "system.shutdown", id=3)
    assert process.wait(timeout=3) == 0


def test_incomplete_eof_is_rejected_and_logs_never_capture_payload(service, tmp_path):
    process, responses = service()
    process.stdin.write(b'{"secret":"private-token"')
    process.stdin.close()
    assert responses.get(timeout=3)["error"]["code"] == -32700
    assert process.wait(timeout=3) == 0
    logs = list((tmp_path / "data space" / "logs").glob("*.log"))
    assert logs
    assert all("private-token" not in log.read_text(encoding="utf-8") for log in logs)


@pytest.mark.parametrize("method", ["system.ping", "x"])
def test_full_frame_id_response_overflow_does_not_terminate_service(service, method):
    process, responses = service()
    request = {"jsonrpc": "2.0", "method": method, "id": ""}
    size = len(json.dumps(request, separators=(",", ":")).encode())
    request["id"] = "x" * (8 * 1024 * 1024 - size)
    wire = json.dumps(request, separators=(",", ":")).encode()
    assert len(wire) == 8 * 1024 * 1024
    process.stdin.write(wire + bytes([10]))
    process.stdin.flush()
    response = responses.get(timeout=5)
    assert response["id"] is None
    assert response["error"]["code"] in [-32603, -32601]
    send(process, "system.ping", id=2)
    assert responses.get(timeout=3)["result"]["ok"] is True
    send(process, "system.shutdown", id=3)
    assert process.wait(timeout=3) == 0


def test_shutdown_with_queued_input_never_leaks_reader_diagnostics(tmp_path):
    wire = json.dumps({"jsonrpc": "2.0", "method": "system.shutdown", "id": 1}).encode()
    for attempt in range(4):
        result = subprocess.run(
            [sys.executable, "-u", "-m", "workbench", "--data-dir", str(tmp_path / str(attempt))],
            input=wire + bytes([10]) + b"x" * (3 * 1024 * 1024),
            capture_output=True, timeout=6,
        )
        assert result.returncode == 0
        assert json.loads(result.stdout)["result"]["status"] == "shutting_down"
        assert result.stderr == b""


def test_drafts_persist_replay_and_revisions_across_service_restart(service):
    process, responses = service()
    command = {"operation_id": str(uuid.uuid4()), "scope_id": "local",
               "owner_type": "local", "owner_id": "editor-1",
               "content_json": {"text": "草稿正文"}}
    send(process, "drafts.save", params=command)
    first = responses.get(timeout=4)["result"]
    assert first["revision"] == 1
    uuid.UUID(first["draft_id"])
    send(process, "system.shutdown", id=2)
    assert responses.get(timeout=3)["result"]["status"] == "shutting_down"
    assert process.wait(timeout=3) == 0
    process, responses = service()
    send(process, "drafts.save", params=command)
    assert responses.get(timeout=4)["result"] == first
    owner = {key: command[key] for key in ["scope_id", "owner_type", "owner_id"]}
    send(process, "drafts.get", id=2, params=owner)
    loaded = responses.get(timeout=3)["result"]
    assert loaded == {**first, **owner, "content_json": command["content_json"]}
    send(process, "drafts.save", id=3, params={**command, "content_json": {"text": "changed"}})
    assert responses.get(timeout=3)["error"]["data"]["code"] == "OPERATION_CONFLICT"
    send(process, "drafts.save", id=4, params={**command, "operation_id": str(uuid.uuid4())})
    error = responses.get(timeout=3)["error"]["data"]
    assert error["code"] == "REVISION_CONFLICT" and error["committed"] is False
    send(process, "drafts.get", id=5, params={**owner, "scope_id": "private-token"})
    error = responses.get(timeout=3)["error"]
    assert error["code"] == -32602 and "private-token" not in json.dumps(error)
    send(process, "drafts.get", id=6, params={**owner, "owner_id": "missing"})
    assert responses.get(timeout=3)["error"]["data"]["code"] == "DRAFT_NOT_FOUND"
    send(process, "system.shutdown", id=7)
    assert responses.get(timeout=3)["id"] == 7
    assert process.wait(timeout=3) == 0
    assert process.stderr.read() == b""


def test_eof_drains_draft_commit_before_service_exit(service):
    process, responses = service()
    command = {"operation_id": str(uuid.uuid4()), "scope_id": "local",
               "owner_type": "local", "owner_id": "editor-1",
               "content_json": {"text": "durable"}}
    send(process, "drafts.save", params=command)
    process.stdin.close()
    first = responses.get(timeout=4)["result"]
    assert process.wait(timeout=3) == 0
    process, responses = service()
    send(process, "drafts.save", params=command)
    assert responses.get(timeout=4)["result"] == first
    send(process, "system.shutdown", id=2)
    assert responses.get(timeout=3)["id"] == 2
    assert process.wait(timeout=3) == 0


def test_corrupt_database_startup_never_emits_protocol_or_private_data(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "workbench.sqlite3").write_bytes(b"private-token invalid database")
    process = subprocess.run(
        [sys.executable, "-u", "-m", "workbench", "--data-dir", str(tmp_path)],
        input=b"", capture_output=True, timeout=4,
    )
    assert process.returncode != 0
    assert process.stdout == b""
    assert process.stderr and b"private-token" not in process.stderr


def test_task_reads_are_public_but_placeholder_execution_is_not(service):
    process, responses = service()
    send(process, "tasks.list")
    assert responses.get(timeout=4)["result"] == []
    send(process, "tasks.create", id=2, params={"operation_id": "o1", "task_type": "generic", "input": {}})
    assert responses.get(timeout=3)["error"]["code"] == -32601
    send(process, "tasks.get", id=3, params={"task_id": "missing"})
    assert responses.get(timeout=3)["error"]["data"]["code"] == "TASK_NOT_FOUND"
    send(process, "tasks.cancel", id=4, params={"task_id": "missing", "operation_id": "o1", "expected_revision": True})
    assert responses.get(timeout=3)["error"]["code"] == -32602
    send(process, "events.list", id=5, params={"task_id": "missing", "after_seq": -1})
    assert responses.get(timeout=3)["error"]["code"] == -32602
    send(process, "system.shutdown", id=6)
    assert responses.get(timeout=3)["id"] == 6
    assert process.wait(timeout=3) == 0


def test_real_process_startup_recovers_tasks_without_replaying_work(service, tmp_path):
    import asyncio
    from workbench.storage import Storage
    from workbench.tasks import TaskService
    from test_tasks import command, no_flow
    async def seed():
        store = await Storage.open(tmp_path / "data space" / "data" / "workbench.sqlite3")
        tasks = TaskService(store, handlers={"generic": no_flow})
        waiting = await tasks.create(command())
        run = await tasks.start(waiting["task_id"])
        await tasks.commit_run(waiting["task_id"], run, lambda conn: {}, status="waiting_user",
                               waiting_reason="review_artifact", checkpoint={"artifact_id": "a1"})
        running = await tasks.create(command())
        await tasks.start(running["task_id"])
        queued = await tasks.create(command())
        await store.close()
        return waiting, running, queued
    waiting, running, queued = asyncio.run(seed())
    process, responses = service()
    send(process, "system.initialize")
    first_instance = responses.get(timeout=4)["result"]["service_instance_id"]
    send(process, "tasks.get", id=2, params={"task_id": waiting["task_id"]})
    snapshot = responses.get(timeout=3)["result"]
    assert snapshot["status"] == "waiting_user"
    assert snapshot["checkpoint"] == {"artifact_id": "a1"}
    for index, task in enumerate([running, queued], 3):
        send(process, "tasks.get", id=index, params={"task_id": task["task_id"]})
        assert responses.get(timeout=3)["result"]["status"] == "interrupted"
    send(process, "events.list", id=5, params={"task_id": running["task_id"], "after_seq": 2})
    event = responses.get(timeout=3)["result"][0]
    assert event["seq"] == 3 and event["payload"]["status"] == "interrupted"
    assert event["service_instance_id"] == first_instance
    # The generic flow is registered for the provider connection test, so the
    # resume succeeds; the worker then rejects this unknown generic action.
    # Successful state changes push events, so reads must filter by RPC id.
    def wait_response(request_id: int, timeout: float = 3):
        while True:
            message = responses.get(timeout=timeout)
            if message.get("id") == request_id:
                return message

    send(process, "tasks.resume", id=6, params={"task_id": running["task_id"], "operation_id": str(uuid.uuid4()), "expected_revision": 3})
    assert wait_response(6)["result"]["status"] == "queued"
    status = None
    for index in range(50):
        send(process, "tasks.get", id=100 + index, params={"task_id": running["task_id"]})
        status = wait_response(100 + index)["result"]["status"]
        if status == "failed":
            break
        time.sleep(0.05)
    assert status == "failed"
    # Kill the actual service, then verify a second instance keeps the snapshot.
    process.kill()
    assert process.wait(timeout=3) != 0
    process, responses = service()
    send(process, "system.initialize")
    second_instance = responses.get(timeout=4)["result"]["service_instance_id"]
    assert second_instance != first_instance
    send(process, "tasks.get", id=2, params={"task_id": running["task_id"]})
    # The first instance already ran the resumed task to a terminal failure;
    # recovery keeps terminal states, so the snapshot survives unchanged.
    assert responses.get(timeout=3)["result"]["status"] == "failed"
    send(process, "events.list", id=3, params={"task_id": running["task_id"], "after_seq": 2})
    historical = wait_response(3)["result"]
    assert [event["seq"] for event in historical] == [3, 4, 5, 6]
    assert [event["type"] for event in historical] == ["task.status_changed", "task.status_changed",
                                                       "step.started", "step.failed"]
    assert all(event["service_instance_id"] == first_instance for event in historical)
    send(process, "system.shutdown", id=4)
    assert responses.get(timeout=3)["id"] == 4
    assert process.wait(timeout=3) == 0
