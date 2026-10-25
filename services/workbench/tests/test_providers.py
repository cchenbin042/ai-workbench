"""Provider config versions, keyring secrets, and the DeepSeek client against a stub."""
import asyncio
import json
import logging
import uuid
from urllib.parse import urlparse

import httpx
import pytest

from workbench.contracts import DomainError, ModelRequest
from workbench.providers import config as provider_config
from workbench.providers.deepseek import DeepSeekClient
from workbench.storage import Storage, canonical_json
from workbench.tasks import TaskService
from fixtures.http_provider import ScriptedProvider, completion_body


class FakeKeyring:
    """In-memory stand-in for the Windows system keyring backend."""

    def __init__(self, backend_name="WinVaultKeyring"):
        self._backend_cls = type(backend_name, (), {})
        self.store: dict[tuple[str, str], str] = {}

    def get_keyring(self):
        return self._backend_cls()

    def set_password(self, service: str, username: str, password: str) -> None:
        self.store[(service, username)] = password

    def get_password(self, service: str, username: str) -> str | None:
        return self.store.get((service, username))

    def delete_password(self, service: str, username: str) -> None:
        if (service, username) not in self.store:
            raise KeyError("password not found")
        del self.store[(service, username)]


SECRET = "sk-test-secret-value-not-real"


def model_request(content: str = "Reply with JSON {\"ok\": true} only."):
    return ModelRequest(model_id="deepseek-flash",
                        messages=[{"role": "user", "content": content}], max_tokens=16)


def update_request(endpoint="https://api.deepseek.com/chat/completions",
                   model_id="deepseek-chat", **patch):
    return {"operation_id": str(uuid.uuid4()), "kind": "text", "endpoint": endpoint,
            "model_id": model_id, "parameters": {}, **patch}


@pytest.fixture
async def store(tmp_path):
    storage = await Storage.open(tmp_path / "data" / "workbench.sqlite3")
    try:
        yield storage
    finally:
        await storage.close()


async def complete_with(client: DeepSeekClient, cancel=None):
    return await client.complete(model_request(), cancel or asyncio.Event())


async def test_seeded_providers_and_agents_exist(store):
    listed = (await provider_config.list_providers(store))["items"]
    assert [item["kind"] for item in listed] == ["text"]
    text = listed[0]
    assert text["endpoint"] == "https://api.deepseek.com/chat/completions"
    assert text["model_id"] == "deepseek-flash"
    assert text["version_no"] == 1 and text["has_secret"] is False
    assert text["secret_ref"] is None
    assert await provider_config.get_provider({"kind": "text"}, store) == text
    agents = await store.read("SELECT id,agent_type FROM agent_configs ORDER BY agent_type")
    assert [row["agent_type"] for row in agents] == ["interview", "question_generation"]
    for row in agents:
        versions = await store.read(
            "SELECT flow_type FROM agent_config_versions WHERE agent_id=?", (row["id"],))
        assert len(versions) == 1


async def test_update_provider_creates_new_version_and_replays(store):
    request = update_request()
    first = await provider_config.update_provider(request, store)
    assert first["version_no"] == 2 and first["model_id"] == "deepseek-chat"
    assert await provider_config.update_provider(request, store) == first
    versions = await store.read("SELECT version_no,endpoint FROM provider_config_versions ORDER BY version_no")
    assert [row["version_no"] for row in versions] == [1, 2]
    assert versions[0]["endpoint"] == "https://api.deepseek.com/chat/completions"

    loopback = await provider_config.update_provider(
        update_request("http://127.0.0.1:9/v1/chat/completions", "stub-model"), store)
    assert loopback["version_no"] == 3
    with pytest.raises(DomainError) as error:
        await provider_config.update_provider(update_request("http://example.com/v1"), store)
    assert error.value.code == "ENDPOINT_INVALID"
    assert len(await store.read("SELECT * FROM provider_config_versions")) == 3


async def test_provider_errors_preserve_input_and_redact_secrets(store, caplog, monkeypatch):
    import workbench.providers.deepseek as deepseek_module

    async def instant(_seconds):
        return None
    monkeypatch.setattr(deepseek_module, "_sleep", instant)
    caplog.set_level(logging.INFO, logger="workbench")

    fake = FakeKeyring()
    await provider_config.set_secret({"operation_id": str(uuid.uuid4()), "kind": "text",
                                "secret": SECRET}, store, keyring_module=fake)

    stub = ScriptedProvider([(401, {"error": {"message": "invalid api key"}})])
    client = DeepSeekClient("https://stub.test/chat/completions", SECRET,
                            transport=stub.transport())
    with pytest.raises(DomainError) as error:
        await complete_with(client)
    assert error.value.code == "AUTH_FAILED"
    assert stub.calls == 1 and stub.auth_present() == [True]
    assert "invalid api key" not in str(error.value)
    assert SECRET not in caplog.text

    for row in await store.read("SELECT * FROM provider_config_versions"):
        assert SECRET not in canonical_json(dict(row))
    listed = (await provider_config.list_providers(store))["items"]
    assert SECRET not in canonical_json(listed)
    assert listed[0]["has_secret"] is True


async def test_retry_only_explicit_no_content_error(store, monkeypatch):
    import workbench.providers.deepseek as deepseek_module
    sleeps: list[float] = []

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    monkeypatch.setattr(deepseek_module, "_sleep", fake_sleep)
    error_body = {"error": {"message": "slow down"}}

    stub = ScriptedProvider([(429, error_body), (200, completion_body("hi"))])
    result = await complete_with(DeepSeekClient("https://stub.test/chat/completions", SECRET,
                                                transport=stub.transport()))
    assert stub.calls == 2 and result.content == "hi" and len(sleeps) == 1

    stub = ScriptedProvider([(429, error_body), (429, error_body)])
    with pytest.raises(DomainError) as error:
        await complete_with(DeepSeekClient("https://stub.test/chat/completions", SECRET,
                                           transport=stub.transport()))
    assert error.value.code == "RATE_LIMITED" and stub.calls == 2

    stub = ScriptedProvider([(500, error_body), (200, completion_body("recovered"))])
    result = await complete_with(DeepSeekClient("https://stub.test/chat/completions", SECRET,
                                                transport=stub.transport()))
    assert stub.calls == 2 and result.content == "recovered"

    stub = ScriptedProvider([httpx.ReadError("connection lost")])
    with pytest.raises(DomainError) as error:
        await complete_with(DeepSeekClient("https://stub.test/chat/completions", SECRET,
                                           transport=stub.transport()))
    assert error.value.code == "PROVIDER_NETWORK" and stub.calls == 1
    assert SECRET not in str(error.value)


async def test_empty_and_truncated_content_fail(store):
    stub = ScriptedProvider([(200, completion_body("", finish_reason="stop"))])
    with pytest.raises(DomainError) as error:
        await complete_with(DeepSeekClient("https://stub.test/chat/completions", SECRET,
                                           transport=stub.transport()))
    assert error.value.code == "MODEL_EMPTY"

    stub = ScriptedProvider([(200, completion_body("part", finish_reason="length"))])
    with pytest.raises(DomainError) as error:
        await complete_with(DeepSeekClient("https://stub.test/chat/completions", SECRET,
                                           transport=stub.transport()))
    assert error.value.code == "MODEL_TRUNCATED"


async def test_set_and_delete_secret_store_reference_only(store):
    fake = FakeKeyring()
    result = await provider_config.set_secret({"operation_id": str(uuid.uuid4()), "kind": "text",
                                         "secret": SECRET}, store, keyring_module=fake)
    assert result["has_secret"] is True
    assert SECRET not in result["secret_ref"]
    assert list(fake.store.values()) == [SECRET]
    assert provider_config.read_secret(result["secret_ref"], keyring_module=fake) == SECRET

    with pytest.raises(DomainError) as error:
        await provider_config.set_secret({"operation_id": str(uuid.uuid4()), "kind": "text",
                                    "secret": SECRET}, store,
                                   keyring_module=FakeKeyring("FailKeyring"))
    assert error.value.code == "KEYRING_UNAVAILABLE"

    updated = await provider_config.update_provider(update_request(), store)
    assert updated["has_secret"] is True and updated["secret_ref"] == result["secret_ref"]

    removed = await provider_config.delete_secret({"operation_id": str(uuid.uuid4()), "kind": "text"},
                                            store, keyring_module=fake)
    assert removed["has_secret"] is False and fake.store == {}
    assert provider_config.read_secret(result["secret_ref"], keyring_module=fake) is None
    with pytest.raises(DomainError) as error:
        await provider_config.delete_secret({"operation_id": str(uuid.uuid4()), "kind": "text"},
                                            store, keyring_module=fake)
    assert error.value.code == "SECRET_NOT_FOUND"


async def test_connection_test_runs_in_task_slot(store):
    stub: ScriptedProvider | None = None
    fake = FakeKeyring()

    async def dispatch(service, task_id, run_id):
        return await provider_config.run_connection_test(
            service, task_id, run_id,
            transport=stub.transport() if stub else None, keyring_module=fake)

    tasks = TaskService(store, handlers={"generic": dispatch}, instance_id="test-instance")
    try:
        tasks.start_worker()
        created = await provider_config.test_provider(
            {"operation_id": str(uuid.uuid4()), "kind": "text"}, store, tasks)
        assert created["task_type"] == "generic"
        for _ in range(2000):
            snapshot = await tasks.get(created["task_id"])
            if snapshot["status"] == "completed":
                break
            await asyncio.sleep(0.01)
        assert snapshot["status"] == "completed"
        assert snapshot["checkpoint"]["ok"] is False
        assert snapshot["checkpoint"]["error_code"] == "PROVIDER_NOT_CONFIGURED"

        await provider_config.set_secret({"operation_id": str(uuid.uuid4()), "kind": "text",
                                    "secret": SECRET}, store, keyring_module=fake)
        stub = ScriptedProvider([(200, completion_body('{"ok": true}'))])
        created = await provider_config.test_provider(
            {"operation_id": str(uuid.uuid4()), "kind": "text"}, store, tasks)
        for _ in range(2000):
            snapshot = await tasks.get(created["task_id"])
            if snapshot["status"] == "completed":
                break
            await asyncio.sleep(0.01)
        checkpoint = snapshot["checkpoint"]
        assert snapshot["status"] == "completed"
        assert checkpoint["ok"] is True
        assert checkpoint["model_id"] == "stub-model"
        assert checkpoint["request_id"] == "stub-req-1"
        assert checkpoint["usage"]["total_tokens"] == 12
        assert checkpoint["latency_ms"] >= 0
        assert SECRET not in canonical_json(checkpoint)

        stub = ScriptedProvider([(401, {"error": {"message": "denied"}})])
        created = await provider_config.test_provider(
            {"operation_id": str(uuid.uuid4()), "kind": "text"}, store, tasks)
        for _ in range(2000):
            snapshot = await tasks.get(created["task_id"])
            if snapshot["status"] == "completed":
                break
            await asyncio.sleep(0.01)
        assert snapshot["checkpoint"]["ok"] is False
        assert snapshot["checkpoint"]["error_code"] == "AUTH_FAILED"
    finally:
        await tasks.close()


async def test_provider_operations_replay_idempotently(store):
    fake = FakeKeyring()
    secret_request = {"operation_id": str(uuid.uuid4()), "kind": "text", "secret": SECRET}
    first = await provider_config.set_secret(secret_request, store, keyring_module=fake)
    assert await provider_config.set_secret(secret_request, store, keyring_module=fake) == first
    assert len(fake.store) == 1
    update = update_request()
    assert await provider_config.update_provider(update, store) == \
        await provider_config.update_provider(update, store)
    versions = await store.read("SELECT version_no FROM provider_config_versions ORDER BY version_no")
    assert [row["version_no"] for row in versions] == [1, 2]
