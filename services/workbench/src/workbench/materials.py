"""Material scope, source snapshots, and freshness within approved links.

File contents are read only through a grant (dialog file selection or an
active directory link), always outside storage transactions, and always as
immutable material versions. Unlinked sources are answered from snapshots
without touching the filesystem again.
"""
import asyncio
import hashlib
import json
import os
import stat as stat_module
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import paths
from .contracts import (CheckFreshnessCommand, CommandMeta, DirectoryEntry, DirectoryListingResult,
                        DomainError, FreshnessItem, GetMaterialCommand, GrantResult,
                        ImportFilesCommand, ImportTextCommand, ListDirectoryCommand,
                        ListMaterialsCommand, MaterialDetail, MaterialSummary,
                        MaterialVersionSummary, PreviewFileCommand, PreviewResult,
                        RegisterGrantCommand)
from .paths import MAX_SINGLE_FILE_BYTES, read_selected_file, validate_relative_entry
from .storage import Storage, canonical_json, utc_now, validate_command

MAX_BATCH_BYTES = 1_000_000
MAX_LISTING_ENTRIES = 2_000
MAX_LISTING_DEPTH = 8

EXCLUDED_DIRECTORY_NAMES = {".git", "node_modules", ".venv", "venv", "__pycache__",
                            "target", "build", "dist"}
TEXT_EXTENSIONS = {".md", ".txt", ".json", ".py", ".java"}
CREDENTIAL_EXTENSIONS = {".pem", ".key", ".ppk", ".pfx", ".p12", ".kdbx", ".jks", ".keystore"}
CREDENTIAL_NAMES = {"credentials.json", "credentials.yaml", "secrets.json", "secrets.yaml",
                    ".npmrc", ".netrc", ".pypirc"}


def probe_stat(path: str):
    # Module-level seam so tests can count every filesystem access.
    return os.stat(path)


def _excluded_file_name(name: str) -> bool:
    lowered = name.casefold()
    if lowered.startswith(".env"):
        return True
    if lowered in CREDENTIAL_NAMES or any(lowered.endswith(ext) for ext in CREDENTIAL_EXTENSIONS):
        return True
    return any(lowered.startswith(prefix)
               for prefix in ("id_rsa", "id_ed25519", "id_ecdsa", "id_dsa"))


def _is_reparse(info: os.stat_result) -> bool:
    return bool(getattr(info, "st_file_attributes", 0) & paths._REPARSE_FLAG)


class GrantRegistry:
    """Short-lived in-process selection grants created only by main-process dialogs."""

    def __init__(self, ttl_seconds: float = 900):
        self.ttl_seconds = ttl_seconds
        self._grants: dict[str, dict] = {}

    def get(self, grant_id: str) -> dict:
        grant = self._grants.get(grant_id)
        if grant is None:
            raise DomainError("GRANT_NOT_FOUND", "That selection grant was not found")
        if datetime.now(timezone.utc) > datetime.fromisoformat(grant["expires_at"]):
            del self._grants[grant_id]
            raise DomainError("GRANT_EXPIRED", "The selection grant expired; choose again")
        return grant


def register_grant(registry: GrantRegistry, **command) -> dict:
    parsed = validate_command(RegisterGrantCommand, command)
    expires_at = (datetime.now(timezone.utc)
                  + timedelta(seconds=registry.ttl_seconds)).isoformat()
    grant_id = str(uuid.uuid4())
    if parsed.kind == "directory":
        if parsed.path is None:
            raise DomainError("PATH_INVALID", "A directory grant needs one path")
        root = paths.normalize_absolute_path(parsed.path)
        try:
            info = os.lstat(root)
        except OSError:
            raise DomainError("PATH_INVALID", "The selected directory is not available") from None
        if _is_reparse(info) or not stat_module.S_ISDIR(info.st_mode):
            raise DomainError("PATH_INVALID", "The grant must point at a real local directory")
        grant = {"grant_id": grant_id, "kind": "directory", "expires_at": expires_at,
                 "root": str(root), "root_key": str(root).casefold(), "files": {}}
    else:
        files: dict[str, str] = {}
        for raw in parsed.paths:
            resolved = paths.normalize_absolute_path(raw)
            try:
                info = os.lstat(resolved)
            except OSError:
                raise DomainError("PATH_INVALID", "A selected file is not available") from None
            if _is_reparse(info) or not stat_module.S_ISREG(info.st_mode):
                raise DomainError("PATH_INVALID", "A file grant must point at real files")
            files[str(resolved)] = resolved.name
        if not files:
            raise DomainError("PATH_INVALID", "A file grant needs at least one file")
        grant = {"grant_id": grant_id, "kind": "files", "expires_at": expires_at,
                 "root": None, "root_key": None, "files": files}
    registry._grants[grant_id] = grant
    return GrantResult(grant_id=grant_id, kind=parsed.kind, expires_at=expires_at,
                       root=grant["root"], files=list(grant["files"])).model_dump()


async def _resolve_link(store: Storage, workspace_id: str, link_id: str) -> dict:
    rows = await store.read("SELECT id,canonical_root,root_key FROM directory_links WHERE id=? AND workspace_id=? AND removed_at IS NULL",
                            (link_id, workspace_id))
    if not rows:
        raise DomainError("SOURCE_OUT_OF_SCOPE", "Directory link was not found in this workspace")
    return rows[0]


def _walk_listing(root: Path) -> tuple[list[dict], bool]:
    collected: list[dict] = []
    truncated = False

    def visit(directory: Path, prefix: str, depth: int) -> None:
        nonlocal truncated
        if depth > MAX_LISTING_DEPTH:
            return
        try:
            children = sorted(os.scandir(directory), key=lambda entry: entry.name.casefold())
        except OSError:
            return
        for child in children:
            if len(collected) >= MAX_LISTING_ENTRIES:
                truncated = True
                return
            try:
                info = child.stat(follow_symlinks=False)
            except OSError:
                continue
            if _is_reparse(info):
                continue
            if stat_module.S_ISDIR(info.st_mode):
                if child.name.casefold() not in EXCLUDED_DIRECTORY_NAMES:
                    visit(Path(child.path), f"{prefix}{child.name}/", depth + 1)
                continue
            if not stat_module.S_ISREG(info.st_mode):
                continue
            name = child.name
            if Path(name).suffix.casefold() not in TEXT_EXTENSIONS or _excluded_file_name(name):
                continue
            if len(collected) >= MAX_LISTING_ENTRIES:
                truncated = True
                return
            modified = datetime.fromtimestamp(info.st_mtime, tz=timezone.utc).isoformat()
            collected.append({"relative_path": f"{prefix}{name}",
                              "size_bytes": info.st_size, "modified_at": modified})

    visit(root, "", 0)
    return collected[:MAX_LISTING_ENTRIES], truncated


async def list_directory_files(command: dict, store: Storage) -> dict:
    parsed = validate_command(ListDirectoryCommand, command)
    link = await _resolve_link(store, parsed.workspace_id, parsed.link_id)
    root = Path(link["canonical_root"])
    entries, truncated = await asyncio.to_thread(_walk_listing, root)
    listing = DirectoryListingResult(link_id=parsed.link_id, canonical_root=str(root),
                                     entries=[DirectoryEntry(**entry) for entry in entries],
                                     truncated=truncated)
    return listing.model_dump()


async def import_files(command: dict, store: Storage, grants: GrantRegistry | None = None) -> dict:
    parsed = validate_command(ImportFilesCommand, command)
    if parsed.grant_id is not None:
        if grants is None:
            raise DomainError("GRANT_NOT_FOUND", "That selection grant was not found")
        grant = grants.get(parsed.grant_id)
        if grant["kind"] != "files":
            raise DomainError("GRANT_INVALID", "Importing files needs a file selection grant")
        if parsed.entries:
            raise DomainError("GRANT_INVALID",
                              "A file selection grant already fixes the files to import")
        root = None
        root_key = None
        plan = [(Path(path), display, None) for path, display in grant["files"].items()]
    else:
        link = await _resolve_link(store, parsed.workspace_id, parsed.link_id)
        root = Path(link["canonical_root"])
        root_key = link["root_key"]
        if not parsed.entries:
            raise DomainError(-32602, "Select at least one file to import")
        plan = []
        for entry in parsed.entries:
            relative = validate_relative_entry(entry.relative_path)
            plan.append((Path(root, *relative.parts), relative.name, entry.encoding))

    read_results = []
    total_bytes = 0
    for target, display_name, encoding in plan:
        if root is not None:
            authorization = {"canonical_root": str(root), "encoding": encoding}
        else:
            authorization = {"canonical_root": None, "files": grant["files"],
                             "encoding": encoding}
        result = await asyncio.to_thread(read_selected_file, target, authorization)
        if total_bytes + result["byte_size"] > MAX_BATCH_BYTES:
            raise DomainError("CONTEXT_TOO_LARGE",
                              "This batch exceeds the 1000000-byte total text limit")
        total_bytes += result["byte_size"]
        read_results.append((result, display_name))

    payload = parsed.model_dump()
    meta = CommandMeta(operation_id=parsed.operation_id, method="materials.importFiles",
                       scope_id="local")

    def mutate(conn):
        workspace = conn.execute("SELECT id FROM workspaces WHERE id=?",
                                 (parsed.workspace_id,)).fetchone()
        if workspace is None:
            raise DomainError("WORKSPACE_NOT_FOUND", "Workspace was not found")
        materials = []
        for result, display_name in read_results:
            materials.append(_store_version(conn, parsed.workspace_id, "file", display_name,
                                            result, root_key).model_dump())
        return {"materials": materials, "total_bytes": total_bytes}
    return await store.write_once(meta, payload, mutate)


def _store_version(conn, workspace_id: str | None, kind: str, display_name: str,
                   result: dict, root_key: str | None) -> MaterialDetail:
    now = utc_now()
    source_key = result["path"].casefold() if kind == "file" else None
    existing = None
    if source_key is not None:
        existing = conn.execute("SELECT id FROM materials WHERE workspace_id=? AND source_key=?",
                                (workspace_id, source_key)).fetchone()
    source = {"origin": "file" if kind == "file" else "pasted_text", "path": result["path"],
              "root_key": root_key, "size": result["byte_size"],
              "mtime_ns": result.get("mtime_ns"), "encoding": result["encoding"],
              "line_count": result["line_count"]}
    if existing is not None:
        material_id = existing["id"]
        current = conn.execute("SELECT mv.sha256 FROM materials m JOIN material_versions mv ON mv.id=m.current_version_id WHERE m.id=?",
                               (material_id,)).fetchone()
        if current is not None and current["sha256"] == result["sha256"]:
            row = conn.execute("SELECT version_no,sha256,byte_size,encoding,line_count,read_at,content_text,source_json FROM material_versions WHERE id=(SELECT current_version_id FROM materials WHERE id=?)",
                               (material_id,)).fetchone()
            return _detail(conn, material_id, kind, display_name, workspace_id, row)
        version_no = conn.execute("SELECT coalesce(max(version_no),0)+1 FROM material_versions WHERE material_id=?",
                                  (material_id,)).fetchone()[0]
    else:
        material_id = str(uuid.uuid4())
        version_no = 1
        conn.execute("INSERT INTO materials(id,workspace_id,kind,display_name,source_key,current_version_id,created_at,updated_at) VALUES(?,?,?,?,?,NULL,?,?)",
                     (material_id, workspace_id, kind, display_name, source_key, now, now))
    version_id = str(uuid.uuid4())
    conn.execute("INSERT INTO material_versions(id,material_id,version_no,content_text,sha256,byte_size,encoding,line_count,source_json,read_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                 (version_id, material_id, version_no, result["content_text"], result["sha256"],
                  result["byte_size"], result["encoding"], result["line_count"],
                  canonical_json(source), now))
    conn.execute("UPDATE materials SET current_version_id=?,updated_at=? WHERE id=?",
                 (version_id, now, material_id))
    row = conn.execute("SELECT version_no,sha256,byte_size,encoding,line_count,read_at,content_text,source_json FROM material_versions WHERE id=?",
                       (version_id,)).fetchone()
    return _detail(conn, material_id, kind, display_name, workspace_id, row)


def _detail(conn, material_id: str, kind: str, display_name: str, workspace_id: str | None,
            version_row) -> MaterialDetail:
    summary = MaterialVersionSummary(version_no=version_row["version_no"],
                                     sha256=version_row["sha256"],
                                     byte_size=version_row["byte_size"],
                                     encoding=version_row["encoding"],
                                     line_count=version_row["line_count"],
                                     read_at=version_row["read_at"])
    return MaterialDetail(
        material_id=material_id, workspace_id=workspace_id, kind=kind, display_name=display_name,
        current_version=summary, source_path=json.loads(version_row["source_json"])["path"],
        content_text=version_row["content_text"], sha256=version_row["sha256"],
        byte_size=version_row["byte_size"], encoding=version_row["encoding"],
        line_count=version_row["line_count"], version_no=version_row["version_no"],
        read_at=version_row["read_at"], source=json.loads(version_row["source_json"]),
    )


async def import_text(command: dict, store: Storage) -> dict:
    parsed = validate_command(ImportTextCommand, command)
    if len(parsed.content_text.encode("utf-8")) > MAX_SINGLE_FILE_BYTES:
        raise DomainError("CONTEXT_TOO_LARGE", "Text materials are limited to 200000 bytes")
    payload = parsed.model_dump()
    meta = CommandMeta(operation_id=parsed.operation_id, method="materials.importText",
                       scope_id="local")

    def mutate(conn):
        if parsed.workspace_id is not None:
            workspace = conn.execute("SELECT id FROM workspaces WHERE id=?",
                                     (parsed.workspace_id,)).fetchone()
            if workspace is None:
                raise DomainError("WORKSPACE_NOT_FOUND", "Workspace was not found")
        data = parsed.content_text.encode("utf-8")
        result = {"path": None, "content_text": parsed.content_text,
                  "sha256": hashlib.sha256(data).hexdigest(), "encoding": "utf-8",
                  "byte_size": len(data), "line_count": paths.line_count(data), "mtime_ns": None}
        detail = _store_version(conn, parsed.workspace_id, "text", parsed.display_name,
                                result, None)
        return {"materials": [detail.model_dump()], "total_bytes": result["byte_size"]}
    return await store.write_once(meta, payload, mutate)


async def list_materials(command: dict, store: Storage) -> dict:
    parsed = validate_command(ListMaterialsCommand, command)
    rows = await store.read("""SELECT m.id AS material_id, m.workspace_id, m.kind, m.display_name,
        mv.version_no, mv.sha256, mv.byte_size, mv.encoding, mv.line_count, mv.read_at, mv.source_json
        FROM materials m JOIN material_versions mv ON mv.id=m.current_version_id
        WHERE m.workspace_id=? AND m.archived_at IS NULL ORDER BY m.created_at, m.id""",
                            (parsed.workspace_id,))
    items = []
    for row in rows:
        items.append(MaterialSummary(
            material_id=row["material_id"], workspace_id=row["workspace_id"], kind=row["kind"],
            display_name=row["display_name"],
            current_version=MaterialVersionSummary(
                version_no=row["version_no"], sha256=row["sha256"], byte_size=row["byte_size"],
                encoding=row["encoding"], line_count=row["line_count"], read_at=row["read_at"]),
            source_path=json.loads(row["source_json"])["path"],
        ).model_dump())
    return {"items": items}


async def get_material(command: dict, store: Storage) -> dict:
    parsed = validate_command(GetMaterialCommand, command)
    rows = await store.read("""SELECT m.workspace_id, m.kind, m.display_name,
        mv.version_no, mv.sha256, mv.byte_size, mv.encoding, mv.line_count, mv.read_at,
        mv.content_text, mv.source_json
        FROM materials m JOIN material_versions mv ON mv.id=m.current_version_id WHERE m.id=?""",
                            (parsed.material_id,))
    if not rows:
        raise DomainError("MATERIAL_NOT_FOUND", "Material was not found")
    row = rows[0]
    if row["workspace_id"] != parsed.workspace_id:
        raise DomainError("SOURCE_OUT_OF_SCOPE", "Material is outside the selected workspace")
    summary = MaterialVersionSummary(version_no=row["version_no"], sha256=row["sha256"],
                                     byte_size=row["byte_size"], encoding=row["encoding"],
                                     line_count=row["line_count"], read_at=row["read_at"])
    detail = MaterialDetail(
        material_id=parsed.material_id, workspace_id=row["workspace_id"], kind=row["kind"],
        display_name=row["display_name"], current_version=summary,
        source_path=json.loads(row["source_json"])["path"], content_text=row["content_text"],
        sha256=row["sha256"], byte_size=row["byte_size"], encoding=row["encoding"],
        line_count=row["line_count"], version_no=row["version_no"], read_at=row["read_at"],
        source=json.loads(row["source_json"]),
    )
    return detail.model_dump()


async def preview_file(command: dict, store: Storage) -> dict:
    parsed = validate_command(PreviewFileCommand, command)
    link = await _resolve_link(store, parsed.workspace_id, parsed.link_id)
    relative = validate_relative_entry(parsed.relative_path)
    target = Path(link["canonical_root"], *relative.parts)
    result = await asyncio.to_thread(read_selected_file, target,
                                     {"canonical_root": link["canonical_root"], "encoding": None})
    return PreviewResult(content_text=result["content_text"], sha256=result["sha256"],
                         encoding=result["encoding"], byte_size=result["byte_size"],
                         line_count=result["line_count"]).model_dump()


async def check_freshness(command: dict, store: Storage) -> dict:
    parsed = validate_command(CheckFreshnessCommand, command)
    workspaces = await store.read("SELECT id FROM workspaces WHERE id=?", (parsed.workspace_id,))
    if not workspaces:
        raise DomainError("WORKSPACE_NOT_FOUND", "Workspace was not found")
    rows = await store.read("""SELECT m.id AS material_id, mv.byte_size AS stored_size, mv.source_json
        FROM materials m JOIN material_versions mv ON mv.id=m.current_version_id
        WHERE m.workspace_id=? AND m.kind='file' AND m.archived_at IS NULL ORDER BY m.created_at, m.id""",
                            (parsed.workspace_id,))
    links = await store.read("SELECT id,root_key FROM directory_links WHERE workspace_id=? AND removed_at IS NULL",
                             (parsed.workspace_id,))
    active = {row["root_key"]: row["id"] for row in links}
    items = []
    for row in rows:
        source = json.loads(row["source_json"])
        root_key = source.get("root_key")
        link_id = active.get(root_key)
        if link_id is None:
            items.append(FreshnessItem(
                material_id=row["material_id"], status="snapshot_only",
                source_path=source.get("path"), link_id=None,
                link_removed=root_key is not None, stored_size=row["stored_size"],
                observed_size=None).model_dump())
            continue
        try:
            observed = await asyncio.to_thread(probe_stat, source["path"])
        except OSError:
            status, observed_size = "missing", None
        else:
            observed_size = observed.st_size
            unchanged = (observed.st_size, observed.st_mtime_ns) == \
                        (source.get("size"), source.get("mtime_ns"))
            status = "current" if unchanged else "changed"
        items.append(FreshnessItem(
            material_id=row["material_id"], status=status, source_path=source.get("path"),
            link_id=link_id, link_removed=False, stored_size=row["stored_size"],
            observed_size=observed_size).model_dump())
    return {"items": items}
