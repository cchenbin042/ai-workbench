"""Single-owner SQLite writes, atomic replay, and verified migration backups."""
import asyncio
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import inspect
from importlib.metadata import version
import json
import logging
from pathlib import Path
import shutil
import sqlite3
import uuid

from pydantic import ValidationError

from .contracts import CommandMeta, DomainError, GetDraftCommand, InitializeResult, SaveDraftCommand

logger = logging.getLogger("workbench")

MIGRATIONS_DIR = Path(__file__).with_name("migrations")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_json(value) -> str:
    # Serializing is part of validation: no non-finite numbers or lone surrogates.
    result = json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False,
                        separators=(",", ":"))
    result.encode("utf-8")
    return result


def storage_error(error: Exception) -> DomainError:
    if isinstance(error, DomainError):
        return error
    if isinstance(error, sqlite3.Error) and getattr(error, "sqlite_errorcode", 0) & 0xff == sqlite3.SQLITE_FULL:
        return DomainError("STORAGE_FULL", "Storage is full; keep your unsaved edits")
    return DomainError("STORAGE_UNAVAILABLE", "Storage is unavailable; keep your unsaved edits")


class Storage:
    def __init__(self, path: Path):
        self.path = path.resolve()
        self.schema_version = 0
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="workbench-db")
        self._connection = None
        self._closing = False
        self._close_task = None

    @classmethod
    async def open(cls, path: Path) -> "Storage":
        store = cls(Path(path))
        try:
            await store._submit(store._open)
            return store
        except BaseException:
            await store.close()
            raise

    async def _submit(self, function: Callable, *args):
        if self._closing:
            raise DomainError("STORAGE_UNAVAILABLE", "Storage is closed")
        # Shield the underlying job: cancellation of an RPC must not cancel a
        # queued/active commit. Its persisted operation can be queried on retry.
        job = self._executor.submit(function, *args)
        future = asyncio.wrap_future(job)
        try:
            return await asyncio.shield(future)
        except asyncio.CancelledError:
            # Retrieve a later failure even when the caller has already gone away.
            future.add_done_callback(lambda done: None if done.cancelled() else done.exception())
            raise

    def _open(self):
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._connection = sqlite3.connect(self.path, isolation_level=None, timeout=5)
            self._connection.row_factory = sqlite3.Row
            self._connection.execute("PRAGMA foreign_keys=ON")
            self._connection.execute("PRAGMA busy_timeout=5000")
            self._connection.execute("PRAGMA journal_mode=WAL")
            self._connection.execute("PRAGMA synchronous=FULL")
            self._migrate()
        except DomainError:
            raise
        except (sqlite3.Error, OSError, ValueError) as error:
            raise storage_error(error) from None

    def _migrate(self):
        conn = self._connection
        try:
            if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("Invalid database integrity")
            scripts = sorted(MIGRATIONS_DIR.glob("[0-9][0-9][0-9][0-9]_*.sql"))
            versions = [int(script.name[:4]) for script in scripts]
            if not versions or versions != list(range(1, len(versions) + 1)):
                raise ValueError("Invalid migration sequence")
            contents = [script.read_bytes() for script in scripts]
            checksums = [hashlib.sha256(content).hexdigest() for content in contents]
            tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            applied = list(conn.execute("SELECT version,checksum FROM schema_migrations ORDER BY version")) if "schema_migrations" in tables else []
            if tables and not applied:
                raise ValueError("Unrecognized database schema")
            if [row[0] for row in applied] != list(range(1, len(applied) + 1)):
                raise ValueError("Invalid applied migration sequence")
            if len(applied) > len(scripts) or any(row[1] != checksums[index] for index, row in enumerate(applied)):
                raise ValueError("Migration checksum mismatch or database is newer")
            self.schema_version = len(applied)
            if self.schema_version == len(scripts):
                return
            if tables:
                self._backup()
            conn.execute("BEGIN IMMEDIATE")
            try:
                for index in range(self.schema_version, len(scripts)):
                    statement = ""
                    for character in contents[index].decode("utf-8"):
                        statement += character
                        if character == ";" and sqlite3.complete_statement(statement):
                            conn.execute(statement)
                            statement = ""
                    if statement.strip():
                        # SQL files end in a complete statement, never a partial one.
                        conn.execute(statement)
                    conn.execute("INSERT INTO schema_migrations(version,checksum,applied_at) VALUES(?,?,?)",
                                 (index + 1, checksums[index], utc_now()))
                if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise ValueError("Migration integrity check failed")
                if conn.execute("PRAGMA foreign_key_check").fetchone() is not None:
                    raise ValueError("Migration foreign key check failed")
                conn.execute("COMMIT")
                self.schema_version = len(scripts)
            except BaseException:
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
                raise
            try:
                self._prune_backups()
            except OSError:
                # Cleanup follows COMMIT; failure must never report rollback.
                logger.warning("Migration backup cleanup deferred")
        except (sqlite3.Error, OSError, ValueError, UnicodeError):
            raise DomainError("MIGRATION_FAILED", "Database migration failed; existing backups were preserved") from None

    def _backup(self):
        backups = self.path.parent.parent / "backups"
        directory = backups / ("migration-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + "-" + uuid.uuid4().hex)
        directory.mkdir(parents=True)
        target = directory / "workbench.sqlite3"
        # SQLite backup includes committed WAL pages; never copy just the main file.
        with closing(sqlite3.connect(target, isolation_level=None)) as destination:
            self._connection.backup(destination)
            if destination.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("Invalid migration backup")
        manifest = {"schema_version": self.schema_version, "created_at": utc_now(),
                    "app_version": version("zhixu-workbench"),
                    "protocol_version": InitializeResult.model_fields["protocol_version"].default,
                    "kind": "migration", "attachment_ids": [], "includes_attachments": False,
                    "sha256": hashlib.sha256(target.read_bytes()).hexdigest()}
        (directory / "manifest.json").write_text(canonical_json(manifest), encoding="utf-8")

    def _prune_backups(self):
        backups = self.path.parent.parent / "backups"
        # Only complete, automatically created migration snapshots are eligible.
        candidates = sorted(path for path in backups.glob("migration-*")
                            if (path / "manifest.json").is_file() and (path / "workbench.sqlite3").is_file())
        for directory in candidates[:-5]:
            shutil.rmtree(directory)

    async def read(self, sql: str, params: tuple = ()) -> list[dict]:
        if self._closing:
            raise DomainError("STORAGE_UNAVAILABLE", "Storage is closed")
        def query():
            try:
                uri = self.path.as_uri() + "?mode=ro"
                with closing(sqlite3.connect(uri, uri=True, isolation_level=None, timeout=5)) as conn:
                    conn.row_factory = sqlite3.Row
                    conn.execute("PRAGMA foreign_keys=ON")
                    conn.execute("PRAGMA busy_timeout=5000")
                    conn.execute("PRAGMA query_only=ON")
                    def authorize(action, first, second, database, trigger):
                        if action in (sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ,
                                      sqlite3.SQLITE_FUNCTION, sqlite3.SQLITE_RECURSIVE):
                            return sqlite3.SQLITE_OK
                        if action == sqlite3.SQLITE_PRAGMA:
                            # Table/index introspection takes an argument without
                            # writing; other pragma assignments are forbidden.
                            introspection = {"table_info", "table_xinfo", "index_info",
                                             "index_xinfo", "index_list", "foreign_key_list"}
                            if second is None or first.lower() in introspection:
                                return sqlite3.SQLITE_OK
                        return sqlite3.SQLITE_DENY
                    conn.set_authorizer(authorize)
                    return [dict(row) for row in conn.execute(sql, params)]
            except (sqlite3.Error, OSError) as error:
                raise storage_error(error) from None
        return await asyncio.to_thread(query)

    def _transaction(self, mutate: Callable[[sqlite3.Connection], dict]) -> dict:
        conn = self._connection
        try:
            conn.execute("BEGIN IMMEDIATE")
            result = mutate(conn)
            if inspect.isawaitable(result):
                if inspect.iscoroutine(result):
                    result.close()
                raise ValueError("Transaction callbacks must be synchronous")
            if not isinstance(result, dict):
                raise ValueError("Transaction result must be an object")
            # Validate/copy before COMMIT, so an unencodable result cannot create a
            # committed operation that the caller will never be able to receive.
            result = json.loads(canonical_json(result))
            conn.execute("COMMIT")
            return result
        except BaseException as error:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            if not isinstance(error, Exception):
                raise
            raise storage_error(error) from None

    async def transaction(self, mutate: Callable[[sqlite3.Connection], dict]) -> dict:
        return await self._submit(self._transaction, mutate)

    async def write_once(self, meta: CommandMeta, payload: dict, mutate: Callable[[sqlite3.Connection], dict]) -> dict:
        try:
            meta = CommandMeta.model_validate(meta)
            request_hash = hashlib.sha256(canonical_json({"meta": meta.model_dump(), "payload": payload}).encode("utf-8")).hexdigest()
        except (ValidationError, TypeError, ValueError, UnicodeError):
            raise DomainError(-32602, "Invalid params") from None

        def apply(conn):
            existing = conn.execute("SELECT method,scope_id,request_hash,result_json FROM operations WHERE operation_id=?",
                                    (meta.operation_id,)).fetchone()
            if existing is not None:
                if (existing["method"], existing["scope_id"], existing["request_hash"]) != (meta.method, meta.scope_id, request_hash):
                    raise DomainError("OPERATION_CONFLICT", "Operation ID was already used with a different request")
                return json.loads(existing["result_json"])
            result = mutate(conn)
            serialized = canonical_json(result)
            conn.execute("INSERT INTO operations(operation_id,method,scope_id,request_hash,status,result_json,created_at) VALUES(?,?,?,?,?,?,?)",
                         (meta.operation_id, meta.method, meta.scope_id, request_hash, "completed", serialized, utc_now()))
            return result
        return await self.transaction(apply)

    async def close(self) -> None:
        if self._close_task is None:
            self._closing = True
            async def finish():
                def disconnect():
                    if self._connection is not None:
                        self._connection.close()
                        self._connection = None
                try:
                    # Enqueued after all accepted writes, including cancelled RPCs.
                    await asyncio.wrap_future(self._executor.submit(disconnect))
                finally:
                    self._executor.shutdown(wait=False)
            self._close_task = asyncio.create_task(finish())
        await asyncio.shield(self._close_task)


def validate_command(model, command):
    try:
        parsed = model.model_validate(command)
        canonical_json(parsed.model_dump())
        return parsed
    except (ValidationError, TypeError, ValueError, UnicodeError):
        raise DomainError(-32602, "Invalid params") from None


async def save_draft(command: dict, store: Storage) -> dict:
    parsed = validate_command(SaveDraftCommand, command)
    payload = parsed.model_dump()
    meta = CommandMeta(operation_id=parsed.operation_id, method="drafts.save", scope_id=parsed.scope_id,
                       expected_revision=parsed.expected_revision)
    def mutate(conn):
        existing = conn.execute("SELECT id,revision,scope_id FROM drafts WHERE owner_type=? AND owner_id=?",
                                (parsed.owner_type, parsed.owner_id)).fetchone()
        saved_at = utc_now()
        content = canonical_json(parsed.content_json)
        if existing is None:
            if parsed.expected_revision is not None:
                raise DomainError("REVISION_CONFLICT", "Draft changed; reload before saving")
            draft_id = str(uuid.uuid4())
            conn.execute("INSERT INTO drafts(id,scope_id,owner_type,owner_id,content_json,saved_at,created_at,updated_at,revision) VALUES(?,?,?,?,?,?,?,?,1)",
                         (draft_id, parsed.scope_id, parsed.owner_type, parsed.owner_id, content, saved_at, saved_at, saved_at))
            revision = 1
        else:
            if existing["scope_id"] != parsed.scope_id:
                raise DomainError("SOURCE_OUT_OF_SCOPE", "Draft is outside the selected scope")
            cursor = conn.execute("UPDATE drafts SET content_json=?,saved_at=?,updated_at=?,revision=revision+1 WHERE id=? AND revision=?",
                                  (content, saved_at, saved_at, existing["id"], parsed.expected_revision))
            if cursor.rowcount != 1:
                raise DomainError("REVISION_CONFLICT", "Draft changed; reload before saving")
            draft_id, revision = existing["id"], existing["revision"] + 1
        return {"draft_id": draft_id, "revision": revision, "saved_at": saved_at}
    return await store.write_once(meta, payload, mutate)


async def get_draft(command: dict, store: Storage) -> dict:
    parsed = validate_command(GetDraftCommand, command)
    rows = await store.read("SELECT id AS draft_id,scope_id,owner_type,owner_id,content_json,revision,saved_at FROM drafts WHERE owner_type=? AND owner_id=? AND scope_id=?",
                            (parsed.owner_type, parsed.owner_id, parsed.scope_id))
    if not rows:
        raise DomainError("DRAFT_NOT_FOUND", "Draft was not found")
    result = rows[0]
    result["content_json"] = json.loads(result["content_json"])
    return result
