"""Workspace entities and user-approved directory links."""
import json
import uuid

from .contracts import (CommandMeta, CreateWorkspaceCommand, DirectoryLinkResult, DomainError,
                        LinkDirectoryCommand, ListDirectoryLinksCommand, UnlinkDirectoryCommand,
                        WorkspaceResult)
from .storage import Storage, canonical_json, utc_now, validate_command


def _row_to_workspace(row) -> dict:
    return WorkspaceResult(
        workspace_id=row["id"], name=row["name"], role_tags=json.loads(row["role_tags_json"]),
        revision=row["revision"], archived_at=row["archived_at"],
        created_at=row["created_at"], updated_at=row["updated_at"],
    ).model_dump()


def _workspace_row(conn, workspace_id):
    row = conn.execute("SELECT * FROM workspaces WHERE id=?", (workspace_id,)).fetchone()
    if row is None:
        raise DomainError("WORKSPACE_NOT_FOUND", "Workspace was not found")
    return row


async def create_workspace(command: dict, store: Storage) -> dict:
    parsed = validate_command(CreateWorkspaceCommand, command)
    payload = parsed.model_dump()
    meta = CommandMeta(operation_id=parsed.operation_id, method="workspaces.create", scope_id="local")

    def mutate(conn):
        workspace_id = str(uuid.uuid4())
        now = utc_now()
        conn.execute("INSERT INTO workspaces(id,name,role_tags_json,revision,created_at,updated_at) VALUES(?,?,?,1,?,?)",
                     (workspace_id, parsed.name, canonical_json(parsed.role_tags), now, now))
        return {"workspace_id": workspace_id, "name": parsed.name, "role_tags": parsed.role_tags,
                "revision": 1, "archived_at": None, "created_at": now, "updated_at": now}
    return await store.write_once(meta, payload, mutate)


async def list_workspaces(store: Storage) -> dict:
    rows = await store.read("SELECT * FROM workspaces ORDER BY created_at,id")
    return {"items": [_row_to_workspace(row) for row in rows]}


async def link_directory(command: dict, store: Storage, grants) -> dict:
    parsed = validate_command(LinkDirectoryCommand, command)
    payload = parsed.model_dump()
    grant = grants.get(parsed.grant_id)
    if grant["kind"] != "directory" or grant.get("root") is None:
        raise DomainError("GRANT_INVALID", "Linking a directory needs a directory grant")
    meta = CommandMeta(operation_id=parsed.operation_id, method="workspaces.linkDirectory",
                       scope_id="local")

    def mutate(conn):
        workspace = _workspace_row(conn, parsed.workspace_id)
        if workspace["archived_at"] is not None:
            raise DomainError("INVALID_WORKSPACE_STATE", "Archived workspaces cannot add links")
        duplicate = conn.execute("SELECT id FROM directory_links WHERE workspace_id=? AND root_key=? AND removed_at IS NULL",
                                 (parsed.workspace_id, grant["root_key"])).fetchone()
        if duplicate is not None:
            raise DomainError("DIRECTORY_ALREADY_LINKED", "This directory is already linked")
        link_id = str(uuid.uuid4())
        now = utc_now()
        conn.execute("INSERT INTO directory_links(id,workspace_id,canonical_root,root_key,linked_at,removed_at) VALUES(?,?,?,?,?,NULL)",
                     (link_id, parsed.workspace_id, grant["root"], grant["root_key"], now))
        return DirectoryLinkResult(link_id=link_id, workspace_id=parsed.workspace_id,
                                   canonical_root=grant["root"], linked_at=now,
                                   removed_at=None).model_dump()
    return await store.write_once(meta, payload, mutate)


async def list_directory_links(command: dict, store: Storage) -> dict:
    parsed = validate_command(ListDirectoryLinksCommand, command)
    rows = await store.read("SELECT * FROM directory_links WHERE workspace_id=? ORDER BY linked_at,id",
                            (parsed.workspace_id,))
    return {"items": [DirectoryLinkResult(
        link_id=row["id"], workspace_id=row["workspace_id"], canonical_root=row["canonical_root"],
        linked_at=row["linked_at"], removed_at=row["removed_at"],
    ).model_dump() for row in rows]}


async def unlink_directory(command: dict, store: Storage) -> dict:
    parsed = validate_command(UnlinkDirectoryCommand, command)
    payload = parsed.model_dump()
    meta = CommandMeta(operation_id=parsed.operation_id, method="workspaces.unlinkDirectory",
                       scope_id="local")

    def mutate(conn):
        _workspace_row(conn, parsed.workspace_id)
        row = conn.execute("SELECT canonical_root,linked_at FROM directory_links WHERE id=? AND workspace_id=? AND removed_at IS NULL",
                           (parsed.link_id, parsed.workspace_id)).fetchone()
        if row is None:
            raise DomainError("LINK_NOT_FOUND", "Directory link was not found")
        now = utc_now()
        conn.execute("UPDATE directory_links SET removed_at=? WHERE id=?", (now, parsed.link_id))
        return DirectoryLinkResult(link_id=parsed.link_id, workspace_id=parsed.workspace_id,
                                   canonical_root=row["canonical_root"],
                                   linked_at=row["linked_at"], removed_at=now).model_dump()
    return await store.write_once(meta, payload, mutate)
