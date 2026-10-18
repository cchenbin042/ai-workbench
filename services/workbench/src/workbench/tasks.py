"""One durable FIFO execution slot with transactional events and run fencing."""
import asyncio
import inspect
import json
import logging
import uuid

from .contracts import (ChangeTaskCommand, CommandMeta, CreateTaskCommand, DomainError,
                        GetOperationCommand, GetTaskCommand, ListEventsCommand,
                        ListTasksCommand, TaskSnapshot, WaitingReason)
from .storage import canonical_json, utc_now, validate_command

logger = logging.getLogger("workbench")


class TaskService:
    def __init__(self, store, *, handlers=None, on_event=None, instance_id=None):
        self.store = store
        self.handlers = dict(handlers or {})
        self.on_event = on_event
        self.instance_id = instance_id or str(uuid.uuid4())
        self._wake = asyncio.Event()
        self._dispatch_lock = asyncio.Lock()
        self._worker = None
        self._execution = None
        self._active_task_id = None
        self._jobs = set()
        self._closing = False
        self._close_task = None

    @staticmethod
    def _row(conn, task_id):
        row = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        if row is None:
            raise DomainError("TASK_NOT_FOUND", "Task was not found")
        scope = json.loads(row["scope_snapshot_json"])
        if row["workspace_id"] is not None or scope.get("scope_id") != "local":
            raise DomainError("SOURCE_OUT_OF_SCOPE", "Task is outside the selected scope")
        return row

    @staticmethod
    def _snapshot(row):
        return TaskSnapshot(
            task_id=row["id"], task_type=row["type"], workspace_id=row["workspace_id"],
            agent_config_version_id=row["agent_version_id"], input=json.loads(row["input_snapshot_json"]),
            scope=json.loads(row["scope_snapshot_json"]), checkpoint=json.loads(row["checkpoint_json"]),
            status=row["status"], waiting_reason=row["waiting_reason"], active_run_id=row["active_run_id"],
            revision=row["revision"], last_seq=row["last_seq"], created_at=row["created_at"],
            updated_at=row["updated_at"],
        ).model_dump()

    def _event(self, conn, task_id, kind, payload, *, run_id=None):
        conn.execute("UPDATE tasks SET last_seq=last_seq+1 WHERE id=?", (task_id,))
        row = self._row(conn, task_id)
        event = {"event_id": str(uuid.uuid4()), "task_id": task_id, "seq": row["last_seq"],
                 "run_id": run_id, "service_instance_id": self.instance_id,
                 "task_revision": row["revision"], "type": kind, "payload": payload, "created_at": utc_now()}
        conn.execute("INSERT INTO task_events(event_id,task_id,seq,run_id,service_instance_id,task_revision,type,payload_json,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                     (event["event_id"], task_id, event["seq"], run_id, self.instance_id, row["revision"], kind, canonical_json(payload), event["created_at"]))
        return event

    def _publish(self, events):
        for event in events:
            if self.on_event is not None:
                try:
                    self.on_event(event)
                except Exception:
                    # Delivery is best effort; events.list is the durable source.
                    logger.warning("Task event delivery deferred")
        self._wake.set()

    async def _accepted(self, operation):
        if self._closing:
            operation.close()
            raise DomainError("SERVICE_STOPPING", "Task service is stopping")
        job = asyncio.create_task(operation)
        self._jobs.add(job)
        def done(task):
            self._jobs.discard(task)
            if not task.cancelled():
                task.exception()
        job.add_done_callback(done)
        # Commit and follow-up cancellation/delivery survive a lost RPC waiter.
        return await asyncio.shield(job)

    async def _write(self, mutate, events):
        result = await self.store.transaction(mutate)
        self._publish(events)
        return result

    async def _command(self, task_id, method, mutate, *, operation_id=None, expected_revision=None, extra=None):
        parsed = validate_command(ChangeTaskCommand, {"task_id": task_id, "operation_id": operation_id or str(uuid.uuid4()),
                                                      "expected_revision": expected_revision})
        await self.get(parsed.task_id)  # Access checks always precede operation replay.
        meta = CommandMeta(operation_id=parsed.operation_id, method=method, scope_id="local",
                           expected_revision=parsed.expected_revision)
        payload = parsed.model_dump() | (extra or {})
        events = []
        def apply(conn):
            row = self._row(conn, parsed.task_id)
            if parsed.expected_revision is not None and row["revision"] != parsed.expected_revision:
                raise DomainError("REVISION_CONFLICT", "Task changed; reload before retrying")
            mutate(conn, row, events)
            return self._snapshot(self._row(conn, task_id))
        async def persist():
            result = await self.store.write_once(meta, payload, apply)
            self._publish(events)
            if method == "tasks.cancel" and any(event["payload"].get("status") == "cancelling" for event in events):
                # Side effects belong to this newly committed request, never to
                # an old operation replayed after recovery started a newer run.
                current = await self.get(task_id)
                if current["status"] == "cancelling":
                    if self._active_task_id == task_id and self._execution is not None:
                        self._execution.cancel()
                    else:
                        await self._finish_cancel(task_id)
            return result
        return await self._accepted(persist())

    async def create(self, command):
        parsed = validate_command(CreateTaskCommand, command)
        task_id = str(uuid.uuid4())
        events = []
        def create(conn):
            if parsed.task_type not in self.handlers:
                raise DomainError("FLOW_UNAVAILABLE", "This task flow is not available")
            now = utc_now()
            order = conn.execute("SELECT coalesce(max(queue_order),0)+1 FROM tasks").fetchone()[0]
            scope = {"scope_id": "local", "material_version_ids": parsed.material_version_ids}
            conn.execute("INSERT INTO tasks(id,type,status,workspace_id,agent_version_id,input_snapshot_json,scope_snapshot_json,checkpoint_json,queue_order,revision,created_at,updated_at) VALUES(?,?,'queued',?,?,?,?,'{}',?,1,?,?)",
                         (task_id, parsed.task_type, parsed.workspace_id, parsed.agent_config_version_id, canonical_json(parsed.input), canonical_json(scope), order, now, now))
            events.append(self._event(conn, task_id, "task.status_changed", {"status": "queued"}))
            return self._snapshot(self._row(conn, task_id))
        async def persist():
            meta = CommandMeta(operation_id=parsed.operation_id, method="tasks.create", scope_id="local")
            result = await self.store.write_once(meta, parsed.model_dump(), create)
            self._publish(events)
            return result
        return await self._accepted(persist())

    async def get(self, task_id):
        parsed = validate_command(GetTaskCommand, {"task_id": task_id})
        rows = await self.store.read("SELECT * FROM tasks WHERE id=?", (parsed.task_id,))
        if not rows:
            raise DomainError("TASK_NOT_FOUND", "Task was not found")
        row = rows[0]
        if row["workspace_id"] is not None or json.loads(row["scope_snapshot_json"]).get("scope_id") != "local":
            raise DomainError("SOURCE_OUT_OF_SCOPE", "Task is outside the selected scope")
        return self._snapshot(row)

    async def list(self, **command):
        parsed = validate_command(ListTasksCommand, command)
        rows = await self.store.read("SELECT * FROM tasks WHERE workspace_id IS NULL AND json_extract(scope_snapshot_json,'$.scope_id')='local' AND (? IS NULL OR status=?) ORDER BY created_at DESC,id LIMIT ? OFFSET ?",
                                     (parsed.status, parsed.status, parsed.limit, parsed.offset))
        return [self._snapshot(row) for row in rows]

    async def list_events(self, task_id, after_seq=0, limit=50):
        parsed = validate_command(ListEventsCommand, {"task_id": task_id, "after_seq": after_seq, "limit": limit})
        await self.get(parsed.task_id)
        rows = await self.store.read("SELECT * FROM task_events WHERE task_id=? AND seq>? ORDER BY seq LIMIT ?",
                                     (parsed.task_id, parsed.after_seq, parsed.limit))
        return [{**{key: value for key, value in row.items() if key != "payload_json"},
                 "payload": json.loads(row["payload_json"])} for row in rows]

    async def get_operation(self, **command):
        parsed = validate_command(GetOperationCommand, command)
        rows = await self.store.read("SELECT method,result_json FROM operations WHERE operation_id=? AND scope_id=?",
                                     (parsed.operation_id, parsed.scope_id))
        if not rows:
            raise DomainError("OPERATION_NOT_FOUND", "Operation was not found")
        result = json.loads(rows[0]["result_json"])
        if "task_id" in result:
            await self.get(result["task_id"])
        return {"operation_id": parsed.operation_id, "method": rows[0]["method"],
                "status": "completed", "committed": True, "result": result}

    async def start(self, task_id):
        validate_command(GetTaskCommand, {"task_id": task_id})
        run_id = str(uuid.uuid4())
        events = []
        def start(conn):
            row = self._row(conn, task_id)
            if row["status"] != "queued":
                raise DomainError("INVALID_TASK_STATE", "Task is not queued")
            if conn.execute("SELECT 1 FROM tasks WHERE status IN ('running','cancelling')").fetchone():
                raise DomainError("EXECUTION_BUSY", "Another task owns the execution slot")
            first = conn.execute("SELECT id FROM tasks WHERE status='queued' ORDER BY queue_order,id LIMIT 1").fetchone()
            if first[0] != task_id:
                raise DomainError("NOT_NEXT_TASK", "An earlier task is queued")
            attempt = conn.execute("SELECT coalesce(max(attempt_no),0)+1 FROM task_runs WHERE task_id=?", (task_id,)).fetchone()[0]
            revision, now = row["revision"] + 1, utc_now()
            conn.execute("INSERT INTO task_runs(id,task_id,attempt_no,task_revision,state,started_at) VALUES(?,?,?,?,'running',?)",
                         (run_id, task_id, attempt, revision, now))
            conn.execute("UPDATE tasks SET status='running',waiting_reason=NULL,active_run_id=?,revision=?,updated_at=? WHERE id=?",
                         (run_id, revision, now, task_id))
            events.append(self._event(conn, task_id, "step.started", {"status": "running", "attempt_no": attempt}, run_id=run_id))
            return {"run_id": run_id}
        result = await self._accepted(self._write(start, events))
        return result["run_id"]

    async def commit_run(self, task_id, run_id, mutate, *, status="completed", waiting_reason=None, checkpoint=None):
        validate_command(GetTaskCommand, {"task_id": task_id})
        if status not in {"completed", "waiting_user"} or (status == "waiting_user") != (waiting_reason is not None):
            raise DomainError(-32602, "Invalid params")
        if waiting_reason is not None and waiting_reason not in WaitingReason.__args__:
            raise DomainError(-32602, "Invalid params")
        checkpoint = validate_command(CreateTaskCommand, {"operation_id": "checkpoint", "task_type": "generic", "input": checkpoint or {}}).input
        events = []
        def commit(conn):
            row = self._row(conn, task_id)
            run = conn.execute("SELECT state,task_revision FROM task_runs WHERE id=? AND task_id=?", (run_id, task_id)).fetchone()
            if (row["status"] != "running" or row["active_run_id"] != run_id or run is None
                    or run["state"] != "running" or run["task_revision"] != row["revision"]):
                raise DomainError("STALE_RUN", "This execution is no longer active")
            result = mutate(conn)
            if inspect.isawaitable(result):
                if inspect.iscoroutine(result):
                    result.close()
                raise ValueError("Task mutations must be synchronous")
            if not isinstance(result, dict):
                raise ValueError("Task result must be an object")
            canonical_json(result)
            now = utc_now()
            conn.execute("UPDATE task_runs SET state=?,ended_at=? WHERE id=?", (status, now, run_id))
            conn.execute("UPDATE tasks SET status=?,waiting_reason=?,active_run_id=NULL,checkpoint_json=?,revision=revision+1,updated_at=? WHERE id=?",
                         (status, waiting_reason, canonical_json(checkpoint), now, task_id))
            kind = "task.waiting_user" if status == "waiting_user" else "step.completed"
            events.append(self._event(conn, task_id, kind, {"status": status, "reason": waiting_reason}, run_id=run_id))
            return {"task": self._snapshot(self._row(conn, task_id)), "result": result}
        return await self._accepted(self._write(commit, events))

    async def cancel(self, task_id, *, operation_id=None, expected_revision=None):
        def cancel(conn, row, events):
            if row["status"] in {"completed", "cancelled", "cancelling"}:
                return
            run_id = row["active_run_id"]
            status = "cancelling" if run_id is not None else "cancelled"
            now = utc_now()
            conn.execute("UPDATE tasks SET status=?,waiting_reason=NULL,active_run_id=NULL,revision=revision+1,updated_at=? WHERE id=?", (status, now, task_id))
            if run_id is not None:
                conn.execute("UPDATE task_runs SET state='revoked' WHERE id=?", (run_id,))
            events.append(self._event(conn, task_id, "task.cancel_requested", {"status": status}, run_id=run_id))
        async def cancel_registered_run():
            # Registering an execution and revoking it share one coordinator lock.
            # Cancel ACK cannot precede a later start of the cancelled handler.
            async with self._dispatch_lock:
                return await self._command(task_id, "tasks.cancel", cancel, operation_id=operation_id,
                                           expected_revision=expected_revision)
        return await self._accepted(cancel_registered_run())

    async def _finish_cancel(self, task_id):
        events = []
        def finish(conn):
            row = self._row(conn, task_id)
            if row["status"] == "cancelling":
                now = utc_now()
                conn.execute("UPDATE tasks SET status='cancelled',revision=revision+1,updated_at=? WHERE id=?", (now, task_id))
                conn.execute("UPDATE task_runs SET state='cancelled',ended_at=? WHERE task_id=? AND state='revoked'", (now, task_id))
                events.append(self._event(conn, task_id, "task.status_changed", {"status": "cancelled"}))
            return {}
        await self._write(finish, events)

    async def resume(self, task_id, *, operation_id=None, expected_revision=None):
        return await self._requeue(task_id, "tasks.resume", operation_id, expected_revision)

    async def continue_task(self, task_id, *, action, input, operation_id=None, expected_revision=None):
        parsed = validate_command(CreateTaskCommand, {"operation_id": "continue", "task_type": "generic", "input": input})
        if action not in WaitingReason.__args__:
            raise DomainError(-32602, "Invalid params")
        return await self._requeue(task_id, "tasks.continue", operation_id, expected_revision, {"action": action, "input": parsed.input})

    async def _requeue(self, task_id, method, operation_id, expected_revision, continuation=None):
        def queue(conn, row, events):
            allowed = {"waiting_user"} if continuation is not None else {"failed", "interrupted"}
            if row["status"] not in allowed:
                raise DomainError("INVALID_TASK_STATE", "Task cannot continue from its current state")
            if continuation is not None and continuation["action"] != row["waiting_reason"]:
                raise DomainError("INVALID_TASK_ACTION", "Action does not match the task's current waiting reason")
            if row["type"] not in self.handlers:
                raise DomainError("FLOW_UNAVAILABLE", "This task flow is not available")
            checkpoint = json.loads(row["checkpoint_json"])
            if continuation is not None:
                checkpoint["continuation"] = continuation
            order = conn.execute("SELECT coalesce(max(queue_order),0)+1 FROM tasks").fetchone()[0]
            conn.execute("UPDATE tasks SET status='queued',waiting_reason=NULL,active_run_id=NULL,checkpoint_json=?,queue_order=?,revision=revision+1,updated_at=? WHERE id=?",
                         (canonical_json(checkpoint), order, utc_now(), task_id))
            events.append(self._event(conn, task_id, "task.status_changed", {"status": "queued"}))
        return await self._command(task_id, method, queue, operation_id=operation_id,
                                   expected_revision=expected_revision, extra=continuation)

    async def recover_startup(self):
        events = []
        def recover(conn):
            rows = list(conn.execute("SELECT * FROM tasks WHERE status IN ('running','cancelling','queued') ORDER BY queue_order,id"))
            result = []
            for row in rows:
                self._row(conn, row["id"])
                now = utc_now()
                conn.execute("UPDATE tasks SET status='interrupted',waiting_reason=NULL,active_run_id=NULL,revision=revision+1,updated_at=? WHERE id=?", (now, row["id"]))
                conn.execute("UPDATE task_runs SET state='interrupted',ended_at=? WHERE task_id=? AND state IN ('running','revoked')", (now, row["id"]))
                events.append(self._event(conn, row["id"], "task.status_changed", {"status": "interrupted"}, run_id=row["active_run_id"]))
                result.append(self._snapshot(self._row(conn, row["id"])))
            return {"tasks": result}
        result = await self._write(recover, events)
        return result["tasks"]

    def start_worker(self):
        if self._closing:
            raise DomainError("SERVICE_STOPPING", "Task service is stopping")
        if self._worker is None or self._worker.done():
            if self._worker is not None and not self._worker.cancelled():
                self._worker.exception()
            self._worker = asyncio.create_task(self._run_queue())
            self._wake.set()

    async def _failed(self, task_id, run_id):
        events = []
        def fail(conn):
            row = self._row(conn, task_id)
            if row["status"] == "running" and row["active_run_id"] == run_id:
                now = utc_now()
                error = {"code": "TASK_FAILED", "user_message": "Task failed; inspect the saved checkpoint before retrying"}
                conn.execute("UPDATE tasks SET status='failed',active_run_id=NULL,revision=revision+1,updated_at=? WHERE id=?", (now, task_id))
                conn.execute("UPDATE task_runs SET state='failed',ended_at=?,error_json=? WHERE id=?", (now, canonical_json(error), run_id))
                events.append(self._event(conn, task_id, "step.failed", error, run_id=run_id))
            return {}
        await self._write(fail, events)

    async def _execute(self, kind, task_id, run_id):
        handler = self.handlers.get(kind)
        if handler is None:
            raise DomainError("FLOW_UNAVAILABLE", "This task flow is not available")
        await handler(self, task_id, run_id)

    async def _settle_execution(self, task_id, run_id):
        # Retry only local finalization after the handler has stopped. Repeating
        # a provider/tool call here would have unknown external side effects.
        while True:
            try:
                await self._failed(task_id, run_id)
                await self._finish_cancel(task_id)
                return
            except DomainError as error:
                if self._closing or error.code not in {"STORAGE_UNAVAILABLE", "STORAGE_FULL"}:
                    raise
                logger.warning("Task finalization waiting for storage")
                await asyncio.sleep(.25)

    async def _run_queue(self):
        while not self._closing:
            await self._wake.wait()
            self._wake.clear()
            while not self._closing:
                try:
                    async with self._dispatch_lock:
                        if self._closing:
                            return
                        queued = await self.store.read("SELECT id,type FROM tasks WHERE status='queued' ORDER BY queue_order,id LIMIT 1")
                        if not queued:
                            break
                        task_id, kind = queued[0]["id"], queued[0]["type"]
                        run_id = await self.start(task_id)
                        self._active_task_id = task_id
                        self._execution = asyncio.create_task(self._execute(kind, task_id, run_id))
                except DomainError as error:
                    if error.code in {"EXECUTION_BUSY", "INVALID_TASK_STATE", "NOT_NEXT_TASK"}:
                        break
                    if error.code in {"STORAGE_UNAVAILABLE", "STORAGE_FULL"}:
                        # No flow has started: retry only this local, atomic slot
                        # acquisition after storage recovers, never a provider call.
                        logger.warning("Task queue waiting for storage")
                        await asyncio.sleep(.25)
                        continue
                    raise
                try:
                    await self._execution
                except asyncio.CancelledError:
                    if self._closing:
                        return
                except Exception:
                    logger.warning("Task flow failed")
                finally:
                    if not self._closing:
                        await self._settle_execution(task_id, run_id)
                    self._execution = None
                    self._active_task_id = None

    async def close(self):
        if self._close_task is None:
            self._closing = True
            async def finish():
                while self._jobs:
                    await asyncio.gather(*list(self._jobs), return_exceptions=True)
                if self._worker is not None:
                    self._worker.cancel()
                    await asyncio.gather(self._worker, return_exceptions=True)
                await self.recover_startup()
            self._close_task = asyncio.create_task(finish())
        await asyncio.shield(self._close_task)
