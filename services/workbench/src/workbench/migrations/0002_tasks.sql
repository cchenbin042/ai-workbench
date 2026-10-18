CREATE TABLE tasks (
    id TEXT PRIMARY KEY,
    workspace_id TEXT,
    type TEXT NOT NULL CHECK (type IN ('generic','question_generation','interview')),
    status TEXT NOT NULL CHECK (status IN ('draft','queued','running','waiting_user','cancelling','completed','failed','interrupted','cancelled')),
    waiting_reason TEXT CHECK (waiting_reason IN ('review_candidates','answer_question','verify_transcript','approve_tool','review_artifact')),
    agent_version_id TEXT,
    input_snapshot_json TEXT NOT NULL CHECK (json_valid(input_snapshot_json)),
    scope_snapshot_json TEXT NOT NULL CHECK (json_valid(scope_snapshot_json)),
    checkpoint_json TEXT NOT NULL CHECK (json_valid(checkpoint_json)),
    active_run_id TEXT REFERENCES task_runs(id) ON DELETE RESTRICT,
    queue_order INTEGER NOT NULL CHECK (queue_order > 0),
    revision INTEGER NOT NULL CHECK (revision > 0),
    last_seq INTEGER NOT NULL DEFAULT 0 CHECK (last_seq >= 0),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    CHECK ((status = 'waiting_user') = (waiting_reason IS NOT NULL)),
    CHECK ((status = 'running') = (active_run_id IS NOT NULL))
) STRICT;

CREATE TABLE task_runs (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE RESTRICT,
    attempt_no INTEGER NOT NULL CHECK (attempt_no > 0),
    task_revision INTEGER NOT NULL CHECK (task_revision > 0),
    state TEXT NOT NULL CHECK (state IN ('running','completed','waiting_user','failed','revoked','cancelled','interrupted')),
    started_at TEXT NOT NULL,
    ended_at TEXT,
    error_json TEXT CHECK (error_json IS NULL OR json_valid(error_json)),
    UNIQUE (task_id, attempt_no)
) STRICT;

CREATE TABLE task_events (
    event_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE RESTRICT,
    seq INTEGER NOT NULL CHECK (seq > 0),
    run_id TEXT REFERENCES task_runs(id) ON DELETE RESTRICT,
    service_instance_id TEXT NOT NULL,
    task_revision INTEGER NOT NULL CHECK (task_revision > 0),
    type TEXT NOT NULL,
    payload_json TEXT NOT NULL CHECK (json_valid(payload_json)),
    created_at TEXT NOT NULL,
    UNIQUE (task_id, seq)
) STRICT;

CREATE INDEX tasks_queue ON tasks(status, queue_order);
CREATE INDEX tasks_status_created ON tasks(status, created_at);
CREATE UNIQUE INDEX tasks_single_active ON tasks((1)) WHERE status IN ('running','cancelling');
