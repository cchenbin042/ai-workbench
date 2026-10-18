"""Real pipes catch blocked stdin, fragmented reads and protocol pollution."""
import json
from pathlib import Path
import queue
import subprocess
import sys
import threading
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
    assert result["protocol_version"] == 1 and result["schema_version"] == 1
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
