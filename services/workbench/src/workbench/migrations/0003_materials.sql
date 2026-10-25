CREATE TABLE workspaces (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    role_tags_json TEXT NOT NULL CHECK (json_valid(role_tags_json)),
    revision INTEGER NOT NULL CHECK (revision > 0),
    archived_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
) STRICT;

CREATE TABLE directory_links (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE RESTRICT,
    canonical_root TEXT NOT NULL,
    root_key TEXT NOT NULL,
    linked_at TEXT NOT NULL,
    removed_at TEXT
) STRICT;

CREATE TABLE materials (
    id TEXT PRIMARY KEY,
    workspace_id TEXT REFERENCES workspaces(id) ON DELETE RESTRICT,
    kind TEXT NOT NULL CHECK (kind IN ('file','text')),
    display_name TEXT NOT NULL,
    source_key TEXT,
    current_version_id TEXT REFERENCES material_versions(id) ON DELETE RESTRICT,
    archived_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (workspace_id, source_key)
) STRICT;

CREATE TABLE material_versions (
    id TEXT PRIMARY KEY,
    material_id TEXT NOT NULL REFERENCES materials(id) ON DELETE RESTRICT,
    version_no INTEGER NOT NULL CHECK (version_no > 0),
    content_text TEXT NOT NULL,
    sha256 TEXT NOT NULL CHECK (length(sha256) = 64),
    byte_size INTEGER NOT NULL CHECK (byte_size >= 0),
    encoding TEXT NOT NULL,
    line_count INTEGER NOT NULL CHECK (line_count >= 0),
    source_json TEXT NOT NULL CHECK (json_valid(source_json)),
    read_at TEXT NOT NULL,
    UNIQUE (material_id, version_no)
) STRICT;

CREATE INDEX directory_links_workspace ON directory_links(workspace_id, removed_at);
CREATE UNIQUE INDEX directory_links_active ON directory_links(workspace_id, root_key) WHERE removed_at IS NULL;
CREATE INDEX materials_workspace ON materials(workspace_id, archived_at);
CREATE INDEX material_versions_material ON material_versions(material_id, version_no);
