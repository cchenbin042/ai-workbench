CREATE TABLE provider_configs (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL CHECK (kind IN ('text','asr')),
    current_version_id TEXT REFERENCES provider_config_versions(id) ON DELETE RESTRICT,
    revision INTEGER NOT NULL CHECK (revision > 0),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
) STRICT;

CREATE TABLE provider_config_versions (
    id TEXT PRIMARY KEY,
    provider_id TEXT NOT NULL REFERENCES provider_configs(id) ON DELETE RESTRICT,
    version_no INTEGER NOT NULL CHECK (version_no > 0),
    endpoint TEXT NOT NULL,
    model_id TEXT NOT NULL,
    parameters_json TEXT NOT NULL CHECK (json_valid(parameters_json)),
    secret_ref TEXT,
    created_at TEXT NOT NULL,
    UNIQUE (provider_id, version_no)
) STRICT;

CREATE TABLE agent_configs (
    id TEXT PRIMARY KEY,
    agent_type TEXT NOT NULL CHECK (agent_type IN ('question_generation','interview')),
    current_version_id TEXT REFERENCES agent_config_versions(id) ON DELETE RESTRICT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
) STRICT;

CREATE TABLE agent_config_versions (
    id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL REFERENCES agent_configs(id) ON DELETE RESTRICT,
    version_no INTEGER NOT NULL CHECK (version_no > 0),
    flow_type TEXT NOT NULL CHECK (flow_type IN ('question_generation','interview')),
    instructions TEXT NOT NULL,
    provider_version_id TEXT REFERENCES provider_config_versions(id) ON DELETE RESTRICT,
    allowed_tools_json TEXT NOT NULL CHECK (json_valid(allowed_tools_json)),
    created_at TEXT NOT NULL,
    UNIQUE (agent_id, version_no)
) STRICT;

CREATE INDEX provider_config_versions_provider ON provider_config_versions(provider_id, version_no);
CREATE INDEX agent_config_versions_agent ON agent_config_versions(agent_id, version_no);

INSERT INTO provider_configs(id,kind,current_version_id,revision,created_at,updated_at) VALUES
    ('builtin-text-provider','text',NULL,1,
     strftime('%Y-%m-%dT%H:%M:%fZ','now'), strftime('%Y-%m-%dT%H:%M:%fZ','now'));

INSERT INTO provider_config_versions(id,provider_id,version_no,endpoint,model_id,parameters_json,secret_ref,created_at) VALUES
    ('builtin-text-provider-v1','builtin-text-provider',1,'https://api.deepseek.com/chat/completions','deepseek-flash',
     '{"timeout_connect_seconds":10,"timeout_idle_seconds":60,"timeout_total_seconds":180,"max_tokens":8000}',
     NULL, strftime('%Y-%m-%dT%H:%M:%fZ','now'));

UPDATE provider_configs SET current_version_id='builtin-text-provider-v1' WHERE id='builtin-text-provider';

INSERT INTO agent_configs(id,agent_type,current_version_id,created_at,updated_at) VALUES
    ('agent-question-generation','question_generation',NULL,
     strftime('%Y-%m-%dT%H:%M:%fZ','now'), strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    ('agent-interview','interview',NULL,
     strftime('%Y-%m-%dT%H:%M:%fZ','now'), strftime('%Y-%m-%dT%H:%M:%fZ','now'));

INSERT INTO agent_config_versions(id,agent_id,version_no,flow_type,instructions,provider_version_id,allowed_tools_json,created_at) VALUES
    ('agent-question-generation-v1','agent-question-generation',1,'question_generation','',NULL,'[]',
     strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    ('agent-interview-v1','agent-interview',1,'interview','',NULL,'[]',
     strftime('%Y-%m-%dT%H:%M:%fZ','now'));

UPDATE agent_configs SET current_version_id='agent-question-generation-v1' WHERE id='agent-question-generation';
UPDATE agent_configs SET current_version_id='agent-interview-v1' WHERE id='agent-interview';
