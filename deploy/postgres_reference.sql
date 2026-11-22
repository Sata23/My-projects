-- Target schema only; current Python runtime uses SQLite.
-- Run DDL as migration owner, then use a separate non-owner non-BYPASSRLS application role.
CREATE EXTENSION IF NOT EXISTS vector;
CREATE SCHEMA IF NOT EXISTS telecom;
CREATE TABLE telecom.approved_chunks (
  tenant_id text NOT NULL,
  chunk_id text NOT NULL,
  zone text NOT NULL,
  required_role text NOT NULL,
  passage text NOT NULL,
  approved boolean NOT NULL DEFAULT false,
  valid_until date NOT NULL,
  embedding vector(384) NOT NULL,
  model_revision text NOT NULL,
  PRIMARY KEY(tenant_id,chunk_id)
);
ALTER TABLE telecom.approved_chunks ENABLE ROW LEVEL SECURITY;
ALTER TABLE telecom.approved_chunks FORCE ROW LEVEL SECURITY;
CREATE POLICY scoped_chunk_read ON telecom.approved_chunks FOR SELECT USING (
  tenant_id=current_setting('app.tenant',true)
  AND approved AND valid_until>=CURRENT_DATE
  AND (zone='All' OR zone=ANY(string_to_array(current_setting('app.zones',true),',')))
  AND (required_role='All' OR required_role=ANY(string_to_array(current_setting('app.roles',true),',')))
);
-- Populate app.tenant/zones/roles only from verified server identity, using set_config(...,true)
-- in a transaction. Never accept these attributes as arbitrary request-body data.
-- ACL-filtered subset first, cosine ORDER BY embedding <=> query next. Evaluate plans at scale;
-- approximate ANN + post-filtering can lose recall and must not widen authorization.
-- No INSERT/UPDATE policy is granted here; ingestion needs an independently privileged review path.
