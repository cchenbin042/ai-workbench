"""Real filesystem and SQLite tests for scoped workspaces and source snapshots."""
import codecs
import hashlib
import shutil
import sys
import uuid
from pathlib import Path

import pytest

from workbench import paths
from workbench.contracts import DomainError
from workbench.materials import (GrantRegistry, check_freshness, get_material, import_files,
                                 import_text, list_directory_files, list_materials,
                                 preview_file, register_grant)
from workbench.storage import Storage
from workbench.workspaces import (create_workspace, link_directory, list_workspaces,
                                  unlink_directory)


@pytest.fixture
async def store(tmp_path):
    storage = await Storage.open(tmp_path / "data" / "workbench.sqlite3")
    try:
        yield storage
    finally:
        await storage.close()


@pytest.fixture
def grants():
    return GrantRegistry()


@pytest.fixture
def project_dir(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    (root / "notes.md").write_text("# 计划\n内容行", encoding="utf-8")
    (root / "docs").mkdir()
    (root / "docs" / "Main.java").write_text("class Main {}", encoding="utf-8")
    (root / ".env").write_text("SECRET=1", encoding="utf-8")
    (root / ".env.example").write_text("TEMPLATE=1", encoding="utf-8")
    (root / "node_modules").mkdir()
    (root / "node_modules" / "lib.js").write_text("x", encoding="utf-8")
    (root / ".git").mkdir()
    (root / ".git" / "HEAD").write_text("ref: main", encoding="utf-8")
    (root / "app.exe").write_bytes(b"MZ\x00\x00binary")
    (root / "logo.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    return root


async def make_workspace(store, name="开发空间"):
    return await create_workspace({"operation_id": str(uuid.uuid4()), "name": name}, store)


async def link_workspace(store, grants, workspace_id, root):
    grant = register_grant(grants, kind="directory", path=str(root))
    return await link_directory({"operation_id": str(uuid.uuid4()), "workspace_id": workspace_id,
                                 "grant_id": grant["grant_id"]}, store, grants)


def import_request(workspace_id, link_id, entries):
    return {"operation_id": str(uuid.uuid4()), "workspace_id": workspace_id,
            "link_id": link_id, "entries": entries}


async def test_workspace_create_list_and_replay(store):
    request = {"operation_id": str(uuid.uuid4()), "name": "面试准备", "role_tags": ["dev"]}
    first = await create_workspace(request, store)
    assert first["name"] == "面试准备" and first["revision"] == 1 and first["archived_at"] is None
    uuid.UUID(first["workspace_id"])
    assert await create_workspace(request, store) == first
    listed = await list_workspaces(store)
    assert [item["workspace_id"] for item in listed["items"]] == [first["workspace_id"]]


async def test_scope_rejects_prefix_junction_and_replaced_file(store, grants, tmp_path, monkeypatch):
    root = tmp_path / "proj"
    root.mkdir()
    outside = tmp_path / "project2"
    outside.mkdir()
    (outside / "outside.txt").write_text("outside", encoding="utf-8")
    (root / "notes.md").write_text("first", encoding="utf-8")
    workspace = await make_workspace(store)
    link_row = await link_workspace(store, grants, workspace["workspace_id"], root)

    # Containment compares path segments case-insensitively, never string prefixes.
    with pytest.raises(DomainError) as error:
        paths.ensure_within_root(root, outside / "outside.txt")
    assert error.value.code == "SOURCE_OUT_OF_SCOPE"
    paths.ensure_within_root(root, root / "notes.md")

    def request(entries):
        return import_request(workspace["workspace_id"], link_row["link_id"], entries)

    for entry in ("../project2/outside.txt", str(outside / "outside.txt")):
        with pytest.raises(DomainError) as error:
            await import_files(request([{"relative_path": entry}]), store)
        assert error.value.code == "SOURCE_OUT_OF_SCOPE"
    assert await store.read("SELECT * FROM materials") == []

    if sys.platform == "win32":
        import _winapi
        junction = root / "jump"
        _winapi.CreateJunction(str(outside), str(junction))
        with pytest.raises(DomainError) as error:
            await import_files(request([{"relative_path": "jump/outside.txt"}]), store)
        assert error.value.code == "SOURCE_OUT_OF_SCOPE"
        assert await store.read("SELECT * FROM materials") == []

    import workbench.paths as paths_module
    original_read = paths_module.read_all
    target = root / "notes.md"

    def replace_while_reading(handle):
        data = original_read(handle)
        with open(target, "ab") as patch:
            patch.write(b"appended-later")
        return data

    monkeypatch.setattr(paths_module, "read_all", replace_while_reading)
    with pytest.raises(DomainError) as error:
        await import_files(request([{"relative_path": "notes.md"}]), store)
    assert error.value.code == "SOURCE_CHANGED"
    assert await store.read("SELECT * FROM materials") == []
    assert await store.read("SELECT * FROM material_versions") == []


async def test_text_limits_and_encoding(store, grants, tmp_path):
    workspace = await make_workspace(store)
    exact = "字" * 66666 + "ab"
    assert len(exact.encode("utf-8")) == 200000
    result = await import_text({"operation_id": str(uuid.uuid4()),
                                "workspace_id": workspace["workspace_id"],
                                "display_name": "粘贴资料", "content_text": exact}, store)
    assert result["materials"][0]["byte_size"] == 200000
    assert result["total_bytes"] == 200000
    with pytest.raises(DomainError) as error:
        await import_text({"operation_id": str(uuid.uuid4()),
                           "workspace_id": workspace["workspace_id"],
                           "display_name": "超限", "content_text": exact + "a"}, store)
    assert error.value.code == "CONTEXT_TOO_LARGE"

    root = tmp_path / "batch"
    root.mkdir()
    for index in range(5):
        (root / f"part{index}.txt").write_bytes(b"a" * 180000)
    (root / "tail.txt").write_bytes(b"b" * 100001)
    link_row = await link_workspace(store, grants, workspace["workspace_id"], root)
    versions_before = len(await store.read("SELECT * FROM material_versions"))
    entries = [{"relative_path": f"part{index}.txt"} for index in range(5)]
    entries.append({"relative_path": "tail.txt"})
    with pytest.raises(DomainError) as error:
        await import_files(import_request(workspace["workspace_id"], link_row["link_id"], entries),
                           store)
    assert error.value.code == "CONTEXT_TOO_LARGE"
    assert len(await store.read("SELECT * FROM material_versions")) == versions_before

    (root / "big.txt").write_bytes(b"x" * 200001)
    with pytest.raises(DomainError) as error:
        await import_files(import_request(workspace["workspace_id"], link_row["link_id"],
                                          [{"relative_path": "big.txt"}]), store)
    assert error.value.code == "CONTEXT_TOO_LARGE"
    assert len(await store.read("SELECT * FROM material_versions")) == versions_before

    gbk = root / "gbk.txt"
    gbk.write_bytes("中文内容".encode("gb18030"))
    with pytest.raises(DomainError) as error:
        await import_files(import_request(workspace["workspace_id"], link_row["link_id"],
                                          [{"relative_path": "gbk.txt"}]), store)
    assert error.value.code == "SOURCE_DECODE_FAILED"
    assert len(await store.read("SELECT * FROM material_versions")) == versions_before
    decoded = await import_files(import_request(workspace["workspace_id"], link_row["link_id"],
                                                [{"relative_path": "gbk.txt", "encoding": "gb18030"}]),
                                 store)
    assert decoded["materials"][0]["content_text"] == "中文内容"
    assert decoded["materials"][0]["encoding"] == "gb18030"

    (root / "bom.txt").write_bytes(codecs.BOM_UTF8 + "带BOM内容".encode("utf-8"))
    bom = await import_files(import_request(workspace["workspace_id"], link_row["link_id"],
                                            [{"relative_path": "bom.txt"}]), store)
    assert bom["materials"][0]["encoding"] == "utf-8-sig"
    assert bom["materials"][0]["content_text"] == "带BOM内容"


async def test_unlinked_source_uses_snapshot_without_reading_path(store, grants, tmp_path,
                                                                  monkeypatch):
    root = tmp_path / "proj"
    root.mkdir()
    (root / "notes.md").write_text("# 计划", encoding="utf-8")
    workspace = await make_workspace(store)
    link_row = await link_workspace(store, grants, workspace["workspace_id"], root)
    imported = await import_files(import_request(workspace["workspace_id"], link_row["link_id"],
                                                 [{"relative_path": "notes.md"}]), store)
    material_id = imported["materials"][0]["material_id"]

    before = await check_freshness({"workspace_id": workspace["workspace_id"]}, store)
    assert before["items"][0]["status"] == "current"

    await unlink_directory({"operation_id": str(uuid.uuid4()),
                            "workspace_id": workspace["workspace_id"],
                            "link_id": link_row["link_id"]}, store)
    shutil.rmtree(root)

    import workbench.materials as materials_module
    probes = []
    original_probe = materials_module.probe_stat

    def counting_probe(path):
        probes.append(str(path))
        return original_probe(path)

    monkeypatch.setattr(materials_module, "probe_stat", counting_probe)
    report = await check_freshness({"workspace_id": workspace["workspace_id"]}, store)
    assert probes == []
    item = report["items"][0]
    assert item["status"] == "snapshot_only"
    assert item["link_removed"] is True
    assert item["material_id"] == material_id

    detail = await get_material({"workspace_id": workspace["workspace_id"],
                                 "material_id": material_id}, store)
    assert detail["content_text"] == "# 计划"
    assert detail["sha256"] == hashlib.sha256("# 计划".encode("utf-8")).hexdigest()
    assert detail["current_version"]["version_no"] == 1


async def test_cross_workspace_access_is_rejected(store, grants, tmp_path):
    first = await make_workspace(store, "空间一")
    second = await make_workspace(store, "空间二")
    root = tmp_path / "proj"
    root.mkdir()
    (root / "a.md").write_text("A", encoding="utf-8")
    grant = register_grant(grants, kind="directory", path=str(root))
    link_row = await link_directory({"operation_id": str(uuid.uuid4()),
                                     "workspace_id": first["workspace_id"],
                                     "grant_id": grant["grant_id"]}, store, grants)
    imported = await import_files(import_request(first["workspace_id"], link_row["link_id"],
                                                 [{"relative_path": "a.md"}]), store)
    material_id = imported["materials"][0]["material_id"]

    with pytest.raises(DomainError) as error:
        await get_material({"workspace_id": second["workspace_id"], "material_id": material_id},
                           store)
    assert error.value.code == "SOURCE_OUT_OF_SCOPE"
    with pytest.raises(DomainError) as error:
        await import_files(import_request(second["workspace_id"], link_row["link_id"],
                                          [{"relative_path": "a.md"}]), store)
    assert error.value.code == "SOURCE_OUT_OF_SCOPE"
    with pytest.raises(DomainError) as error:
        await preview_file({"workspace_id": second["workspace_id"],
                            "link_id": link_row["link_id"],
                            "relative_path": "a.md"}, store)
    assert error.value.code == "SOURCE_OUT_OF_SCOPE"
    assert (await list_materials({"workspace_id": second["workspace_id"]}, store))["items"] == []
    assert (await check_freshness({"workspace_id": second["workspace_id"]}, store))["items"] == []


async def test_reread_creates_new_version_and_keeps_old_snapshot(store, grants, tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    notes = root / "notes.md"
    notes.write_text("第一版", encoding="utf-8")
    workspace = await make_workspace(store)
    link_row = await link_workspace(store, grants, workspace["workspace_id"], root)
    first = await import_files(import_request(workspace["workspace_id"], link_row["link_id"],
                                              [{"relative_path": "notes.md"}]), store)
    original_hash = first["materials"][0]["sha256"]

    notes.write_text("第二版内容", encoding="utf-8")
    changed = await check_freshness({"workspace_id": workspace["workspace_id"]}, store)
    assert changed["items"][0]["status"] == "changed"

    second = await import_files(import_request(workspace["workspace_id"], link_row["link_id"],
                                               [{"relative_path": "notes.md"}]), store)
    assert second["materials"][0]["current_version"]["version_no"] == 2
    assert second["materials"][0]["sha256"] != original_hash
    rows = await store.read("SELECT version_no,sha256,content_text FROM material_versions ORDER BY version_no")
    assert len(rows) == 2
    assert rows[0]["sha256"] == original_hash
    assert rows[0]["content_text"] == "第一版"

    again = await import_files(import_request(workspace["workspace_id"], link_row["link_id"],
                                              [{"relative_path": "notes.md"}]), store)
    assert again["materials"][0]["current_version"]["version_no"] == 2
    assert len(await store.read("SELECT * FROM material_versions")) == 2


async def test_listing_excludes_sensitive_and_binary_files(store, grants, project_dir):
    workspace = await make_workspace(store)
    link_row = await link_workspace(store, grants, workspace["workspace_id"], project_dir)
    listing = await list_directory_files({"workspace_id": workspace["workspace_id"],
                                          "link_id": link_row["link_id"]}, store)
    sent = {entry["relative_path"] for entry in listing["entries"]}
    assert sent == {"notes.md", "docs/Main.java"}
    for excluded in (".env", ".env.example", "node_modules/lib.js", ".git/HEAD",
                     "app.exe", "logo.png"):
        assert excluded not in sent
    assert listing["truncated"] is False
    assert listing["canonical_root"].casefold() == str(project_dir).casefold()


async def test_preview_reads_content_without_creating_versions(store, grants, project_dir):
    workspace = await make_workspace(store)
    link_row = await link_workspace(store, grants, workspace["workspace_id"], project_dir)
    preview = await preview_file({"workspace_id": workspace["workspace_id"],
                                  "link_id": link_row["link_id"],
                                  "relative_path": "docs/Main.java"}, store)
    assert preview["content_text"] == "class Main {}"
    assert preview["encoding"] == "utf-8"
    assert preview["line_count"] == 1
    assert await store.read("SELECT * FROM materials") == []
    assert await store.read("SELECT * FROM material_versions") == []


async def test_grants_bind_paths_and_expire(grants, tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    (root / "notes.md").write_text("x", encoding="utf-8")
    grant = register_grant(grants, kind="directory", path=str(root))
    assert grant["kind"] == "directory" and grant["root"].casefold() == str(root).casefold()
    assert Path(grant["root"]).is_absolute()

    with pytest.raises(DomainError) as error:
        register_grant(grants, kind="directory", path=str(root / "notes.md"))
    assert error.value.code == "PATH_INVALID"
    with pytest.raises(DomainError) as error:
        register_grant(grants, kind="directory", path="\\\\server\\share\\docs")
    assert error.value.code == "PATH_INVALID"
    with pytest.raises(DomainError) as error:
        register_grant(grants, kind="directory", path=str(tmp_path / "missing"))
    assert error.value.code == "PATH_INVALID"
    with pytest.raises(DomainError) as error:
        register_grant(grants, kind="files", paths=[str(tmp_path / "missing.txt")])
    assert error.value.code == "PATH_INVALID"

    files = register_grant(grants, kind="files", paths=[str(root / "notes.md")])
    assert files["files"] == [str(root / "notes.md")]

    with pytest.raises(DomainError) as error:
        grants.get(str(uuid.uuid4()))
    assert error.value.code == "GRANT_NOT_FOUND"

    expiring = GrantRegistry(ttl_seconds=0.05)
    short = register_grant(expiring, kind="directory", path=str(root))
    import asyncio
    await asyncio.sleep(0.1)
    with pytest.raises(DomainError) as error:
        expiring.get(short["grant_id"])
    assert error.value.code == "GRANT_EXPIRED"


async def test_link_directory_rejects_wrong_grant_and_duplicates(store, grants, tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    (root / "notes.md").write_text("x", encoding="utf-8")
    workspace = await make_workspace(store)
    files_grant = register_grant(grants, kind="files", paths=[str(root / "notes.md")])
    with pytest.raises(DomainError) as error:
        await link_directory({"operation_id": str(uuid.uuid4()),
                              "workspace_id": workspace["workspace_id"],
                              "grant_id": files_grant["grant_id"]}, store, grants)
    assert error.value.code == "GRANT_INVALID"

    first = await link_workspace(store, grants, workspace["workspace_id"], root)
    assert first["removed_at"] is None
    with pytest.raises(DomainError) as error:
        await link_workspace(store, grants, workspace["workspace_id"], root)
    assert error.value.code == "DIRECTORY_ALREADY_LINKED"

    removed = await unlink_directory({"operation_id": str(uuid.uuid4()),
                                      "workspace_id": workspace["workspace_id"],
                                      "link_id": first["link_id"]}, store)
    assert removed["removed_at"] is not None
    assert (root / "notes.md").read_text(encoding="utf-8") == "x"
    with pytest.raises(DomainError) as error:
        await unlink_directory({"operation_id": str(uuid.uuid4()),
                                "workspace_id": workspace["workspace_id"],
                                "link_id": first["link_id"]}, store)
    assert error.value.code == "LINK_NOT_FOUND"

    relinked = await link_workspace(store, grants, workspace["workspace_id"], root)
    assert relinked["link_id"] != first["link_id"]


async def test_files_grant_imports_exactly_the_selected_files(store, grants, project_dir):
    workspace = await make_workspace(store)
    grant = register_grant(grants, kind="files", paths=[str(project_dir / "notes.md")])
    result = await import_files({"operation_id": str(uuid.uuid4()),
                                 "workspace_id": workspace["workspace_id"],
                                 "grant_id": grant["grant_id"]}, store, grants)
    assert [item["display_name"] for item in result["materials"]] == ["notes.md"]
    assert (project_dir / ".env").read_text(encoding="utf-8") == "SECRET=1"
    with pytest.raises(DomainError) as error:
        await import_files({"operation_id": str(uuid.uuid4()),
                            "workspace_id": workspace["workspace_id"],
                            "grant_id": grant["grant_id"],
                            "entries": [{"relative_path": ".env"}]}, store, grants)
    assert error.value.code == "GRANT_INVALID"


async def test_import_replays_same_operation_without_new_materials(store, grants, tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    (root / "notes.md").write_text("内容", encoding="utf-8")
    workspace = await make_workspace(store)
    link_row = await link_workspace(store, grants, workspace["workspace_id"], root)
    request = import_request(workspace["workspace_id"], link_row["link_id"],
                             [{"relative_path": "notes.md"}])
    first = await import_files(request, store)
    assert await import_files(request, store) == first
    assert len(await store.read("SELECT * FROM materials")) == 1
    assert len(await store.read("SELECT * FROM material_versions")) == 1
