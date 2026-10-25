"""Provider configuration versions and system keyring secret storage.

Secrets only ever live in the system keyring; the database stores a reference
and the RPC results only say whether a key exists. Connection tests run as
generic tasks through the single execution slot.
"""
import asyncio
import json
import time
import uuid
from urllib.parse import urlparse

import keyring as system_keyring

from ..contracts import (CommandMeta, DeleteProviderSecretCommand, DomainError,
                         GetProviderCommand, ModelRequest, ProviderVersionResult,
                         SetProviderSecretCommand, TestProviderCommand, UpdateProviderCommand)
from ..storage import Storage, canonical_json, utc_now, validate_command
from .deepseek import DeepSeekClient

logger = __import__("logging").getLogger("workbench")

KEYRING_SERVICE = "ZhixuWorkbench"
ALLOWED_KEYRING_BACKENDS = {"WinVaultKeyring"}
PROVIDER_IDS = {"text": "builtin-text-provider"}
CONNECTION_TEST_ACTION = "provider_connection_test"
CONNECTION_TEST_PROMPT = 'Reply with the JSON object {"ok": true} and no other text.'
CONNECTION_TEST_MAX_TOKENS = 16


def _secret_username(kind: str) -> str:
    return f"provider/{kind}/api-key"


def secret_ref_for(kind: str) -> str:
    return f"keyring:{KEYRING_SERVICE}:{_secret_username(kind)}"


def _keyring_module(keyring_module=None):
    module = keyring_module or system_keyring
    backend_name = type(module.get_keyring()).__name__
    if backend_name not in ALLOWED_KEYRING_BACKENDS:
        raise DomainError("KEYRING_UNAVAILABLE",
                          "The system key storage backend is not allowed; check the Windows Credential Manager")
    return module


def read_secret(secret_ref: str | None, *, keyring_module=None) -> str | None:
    if not secret_ref or not secret_ref.startswith("keyring:"):
        return None
    parts = secret_ref.split(":", 2)
    if len(parts) != 3:
        return None
    module = keyring_module or system_keyring
    try:
        return module.get_password(parts[1], parts[2])
    except Exception as error:
        raise DomainError("KEYRING_UNAVAILABLE",
                          "The system key storage is unavailable") from error


def _result(row) -> dict:
    return ProviderVersionResult(
        provider_id=row["provider_id"], kind=row["kind"], version_no=row["version_no"],
        endpoint=row["endpoint"], model_id=row["model_id"],
        parameters=row["parameters"], secret_ref=row["secret_ref"],
        has_secret=row["secret_ref"] is not None, created_at=row["created_at"],
    ).model_dump()


_VERSION_QUERY = """SELECT p.id AS provider_id, p.kind, v.version_no, v.endpoint, v.model_id,
    v.parameters_json, v.secret_ref, v.created_at
    FROM provider_configs p JOIN provider_config_versions v ON v.id = p.current_version_id"""


def _row_result(row) -> dict:
    row = dict(row)
    row["parameters"] = json.loads(row.pop("parameters_json"))
    return _result(row)


async def get_provider(command: dict, store: Storage) -> dict:
    parsed = validate_command(GetProviderCommand, command)
    rows = await store.read(f"{_VERSION_QUERY} WHERE p.kind=?", (parsed.kind,))
    if not rows:
        raise DomainError("PROVIDER_NOT_CONFIGURED", "This provider has no configuration yet")
    return _row_result(rows[0])


async def list_providers(store: Storage) -> dict:
    rows = await store.read(f"{_VERSION_QUERY} ORDER BY p.kind")
    return {"items": [_row_result(row) for row in rows]}


def _validate_endpoint(endpoint: str) -> None:
    parsed = urlparse(endpoint)
    if parsed.scheme == "https" and parsed.hostname:
        return
    if parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost", "::1"}:
        # Plain HTTP stays limited to loopback stubs for tests and development.
        return
    raise DomainError("ENDPOINT_INVALID",
                      "The endpoint must use HTTPS; plain HTTP is only allowed for loopback")


async def update_provider(command: dict, store: Storage) -> dict:
    parsed = validate_command(UpdateProviderCommand, command)
    _validate_endpoint(parsed.endpoint)
    payload = parsed.model_dump()
    meta = CommandMeta(operation_id=parsed.operation_id, method="providers.update", scope_id="local")

    def mutate(conn):
        config_row = conn.execute("SELECT id FROM provider_configs WHERE kind=?",
                                  (parsed.kind,)).fetchone()
        if config_row is None:
            raise DomainError("PROVIDER_NOT_CONFIGURED", "This provider has no configuration yet")
        version_no = conn.execute("SELECT coalesce(max(version_no),0)+1 FROM provider_config_versions WHERE provider_id=?",
                                  (config_row["id"],)).fetchone()[0]
        previous = conn.execute("SELECT secret_ref FROM provider_config_versions WHERE id=(SELECT current_version_id FROM provider_configs WHERE id=?)",
                                (config_row["id"],)).fetchone()
        now = utc_now()
        version_id = str(uuid.uuid4())
        conn.execute("INSERT INTO provider_config_versions(id,provider_id,version_no,endpoint,model_id,parameters_json,secret_ref,created_at) VALUES(?,?,?,?,?,?,?,?)",
                     (version_id, config_row["id"], version_no, parsed.endpoint, parsed.model_id,
                      canonical_json(parsed.parameters), previous["secret_ref"] if previous else None, now))
        conn.execute("UPDATE provider_configs SET current_version_id=?,revision=revision+1,updated_at=? WHERE id=?",
                     (version_id, now, config_row["id"]))
        row = conn.execute(f"{_VERSION_QUERY} WHERE p.id=?", (config_row["id"],)).fetchone()
        return _row_result(row)
    return await store.write_once(meta, payload, mutate)


async def set_secret(command: dict, store: Storage, *, keyring_module=None) -> dict:
    parsed = validate_command(SetProviderSecretCommand, command)
    module = _keyring_module(keyring_module)
    ref = secret_ref_for(parsed.kind)
    # Keyring write comes first: replaying the same operation rewrites the same
    # value, so a crash between the two steps cannot lose the secret.
    await asyncio.to_thread(module.set_password, KEYRING_SERVICE, _secret_username(parsed.kind),
                            parsed.secret)
    payload = {"kind": parsed.kind}
    meta = CommandMeta(operation_id=parsed.operation_id, method="providers.setSecret",
                       scope_id="local")

    def mutate(conn):
        row = conn.execute("SELECT id FROM provider_configs WHERE kind=?", (parsed.kind,)).fetchone()
        if row is None:
            raise DomainError("PROVIDER_NOT_CONFIGURED", "This provider has no configuration yet")
        now = utc_now()
        conn.execute("UPDATE provider_config_versions SET secret_ref=? WHERE id=(SELECT current_version_id FROM provider_configs WHERE kind=?)",
                     (ref, parsed.kind))
        conn.execute("UPDATE provider_configs SET revision=revision+1,updated_at=? WHERE kind=?",
                     (now, parsed.kind))
        return {"provider_id": row["id"], "kind": parsed.kind, "secret_ref": ref,
                "has_secret": True}
    return await store.write_once(meta, payload, mutate)


async def delete_secret(command: dict, store: Storage, *, keyring_module=None) -> dict:
    parsed = validate_command(DeleteProviderSecretCommand, command)
    module = _keyring_module(keyring_module)
    rows = await store.read("SELECT secret_ref FROM provider_config_versions WHERE id=(SELECT current_version_id FROM provider_configs WHERE kind=?)",
                            (parsed.kind,))
    ref = rows[0]["secret_ref"] if rows else None
    if ref is None:
        raise DomainError("SECRET_NOT_FOUND", "No API key is stored for this provider")
    try:
        await asyncio.to_thread(module.delete_password, KEYRING_SERVICE,
                                _secret_username(parsed.kind))
    except Exception:
        # A missing keyring entry is already the desired state.
        pass
    payload = {"kind": parsed.kind}
    meta = CommandMeta(operation_id=parsed.operation_id, method="providers.deleteSecret",
                       scope_id="local")

    def mutate(conn):
        row = conn.execute("SELECT id FROM provider_configs WHERE kind=?", (parsed.kind,)).fetchone()
        if row is None:
            raise DomainError("PROVIDER_NOT_CONFIGURED", "This provider has no configuration yet")
        now = utc_now()
        conn.execute("UPDATE provider_config_versions SET secret_ref=NULL WHERE id=(SELECT current_version_id FROM provider_configs WHERE kind=?)",
                     (parsed.kind,))
        conn.execute("UPDATE provider_configs SET revision=revision+1,updated_at=? WHERE kind=?",
                     (now, parsed.kind))
        return {"provider_id": row["id"], "kind": parsed.kind, "secret_ref": None,
                "has_secret": False}
    return await store.write_once(meta, payload, mutate)


async def test_provider(command: dict, store: Storage, tasks) -> dict:
    parsed = validate_command(TestProviderCommand, command)
    return await tasks.create({"operation_id": parsed.operation_id, "task_type": "generic",
                               "input": {"action": CONNECTION_TEST_ACTION, "kind": parsed.kind}})


async def run_connection_test(service, task_id: str, run_id: str, *, transport=None,
                              keyring_module=None) -> dict:
    snapshot = await service.get(task_id)
    kind = snapshot["input"].get("kind", "text")
    store: Storage = service.store
    started = time.monotonic()

    def failure(error: DomainError) -> dict:
        return {"ok": False, "error_code": error.code, "latency_ms": None, "model_id": None,
                "request_id": None, "usage": {}}

    try:
        config = await get_provider({"kind": kind}, store)
        secret = read_secret(config["secret_ref"], keyring_module=keyring_module)
        if not secret:
            raise DomainError("PROVIDER_NOT_CONFIGURED", "No API key is stored for this provider")
        parameters = config["parameters"]
        client = DeepSeekClient(config["endpoint"], secret,
                                connect_timeout=parameters.get("timeout_connect_seconds", 10.0),
                                idle_timeout=parameters.get("timeout_idle_seconds", 60.0),
                                total_timeout=parameters.get("timeout_total_seconds", 180.0),
                                transport=transport)
        model_result = await client.complete(
            ModelRequest(model_id=config["model_id"],
                         messages=[{"role": "user", "content": CONNECTION_TEST_PROMPT}],
                         max_tokens=CONNECTION_TEST_MAX_TOKENS),
            asyncio.Event())
        result = {"ok": True, "error_code": None,
                  "latency_ms": int((time.monotonic() - started) * 1000),
                  "model_id": model_result.model, "request_id": model_result.request_id,
                  "usage": model_result.usage}
        logger.info("provider connection test succeeded: request_id=%s latency_ms=%s",
                    model_result.request_id, result["latency_ms"])
    except DomainError as error:
        logger.warning("provider connection test failed: error_code=%s", error.code)
        result = failure(error)

    def commit(conn):
        return dict(result)

    await service.commit_run(task_id, run_id, commit, checkpoint=dict(result))
    return result
