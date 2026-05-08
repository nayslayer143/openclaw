-- openbrain schema-init.sql
--
-- Applied at first postgres boot via /docker-entrypoint-initdb.d/.
-- Base `thoughts` table extracted from upstream
-- integrations/kubernetes-deployment/k8s/openbrain.yml ConfigMap, with
-- embedding dim patched 1536 -> 768 to match Ollama's nomic-embed-text.
--
-- Idempotent (CREATE … IF NOT EXISTS, CREATE OR REPLACE FUNCTION).
-- Pinned upstream SHA: see ../UPSTREAM_SHA.
--
-- NOTE on agent-memory sidecars:
-- The upstream sidecar schema (schemas/agent-memory/schema.sql) is designed
-- against the Supabase OB1 variant where thoughts.id is UUID. Velo's K8s
-- deployment uses BIGSERIAL, which is incompatible with the sidecar foreign
-- keys. Sidecars are deferred along with agent-memory-api (path A — see
-- SPIKE-NOTES.md) and will land in a focused follow-up plan that ports the
-- API service to direct Postgres.

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS thoughts (
    id BIGSERIAL PRIMARY KEY,
    content TEXT NOT NULL,
    embedding vector(768),
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_thoughts_created_at ON thoughts (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_thoughts_metadata ON thoughts USING GIN (metadata);

CREATE OR REPLACE FUNCTION match_thoughts(
    query_embedding vector(768),
    match_threshold FLOAT DEFAULT 0.5,
    match_count INT DEFAULT 10,
    filter JSONB DEFAULT '{}'::jsonb
)
RETURNS TABLE (
    id BIGINT,
    content TEXT,
    metadata JSONB,
    similarity FLOAT,
    created_at TIMESTAMP WITH TIME ZONE
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT
        t.id,
        t.content,
        t.metadata,
        (1 - (t.embedding <=> query_embedding))::FLOAT AS similarity,
        t.created_at
    FROM thoughts t
    WHERE 1 - (t.embedding <=> query_embedding) >= match_threshold
    ORDER BY t.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;

-- end of schema-init.sql --
