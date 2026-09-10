-- Owner-private append-only material revisions, immutable receipts and one-use impact tokens.
CREATE TABLE IF NOT EXISTS pilot_material_revisions (
    tenant_id TEXT NOT NULL,
    owner_user_id TEXT NOT NULL,
    profile_version_id TEXT NOT NULL,
    material_id TEXT NOT NULL,
    material_version INTEGER NOT NULL CHECK (material_version > 0),
    record JSONB NOT NULL CHECK (jsonb_typeof(record)='object'),
    removed BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (tenant_id,owner_user_id,profile_version_id,material_id,material_version),
    FOREIGN KEY (tenant_id,owner_user_id) REFERENCES pilot_users(tenant_id,user_id),
    FOREIGN KEY (tenant_id,profile_version_id) REFERENCES business_profile_versions(tenant_id,profile_version_id)
);
CREATE TABLE IF NOT EXISTS pilot_material_operations (
    tenant_id TEXT NOT NULL,
    owner_user_id TEXT NOT NULL,
    profile_version_id TEXT NOT NULL,
    request_id TEXT NOT NULL,
    material_id TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('save','parse','confirm','remove','revoke')),
    request_sha256 TEXT NOT NULL CHECK (request_sha256 ~ '^[a-f0-9]{64}$'),
    receipt JSONB NOT NULL CHECK (jsonb_typeof(receipt)='object'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (tenant_id,owner_user_id,request_id),
    FOREIGN KEY (tenant_id,owner_user_id) REFERENCES pilot_users(tenant_id,user_id),
    FOREIGN KEY (tenant_id,profile_version_id) REFERENCES business_profile_versions(tenant_id,profile_version_id)
);
CREATE TABLE IF NOT EXISTS pilot_material_impact_tokens (
    tenant_id TEXT NOT NULL,
    owner_user_id TEXT NOT NULL,
    profile_version_id TEXT NOT NULL,
    material_id TEXT NOT NULL,
    material_version INTEGER NOT NULL,
    action TEXT NOT NULL CHECK (action IN ('remove','revoke')),
    token_sha256 TEXT NOT NULL CHECK (token_sha256 ~ '^[a-f0-9]{64}$'),
    expires_at TIMESTAMPTZ NOT NULL,
    consumed_at TIMESTAMPTZ,
    PRIMARY KEY (tenant_id,owner_user_id,token_sha256),
    FOREIGN KEY (tenant_id,owner_user_id) REFERENCES pilot_users(tenant_id,user_id)
);
ALTER TABLE pilot_material_revisions ENABLE ROW LEVEL SECURITY; ALTER TABLE pilot_material_revisions FORCE ROW LEVEL SECURITY;
ALTER TABLE pilot_material_operations ENABLE ROW LEVEL SECURITY; ALTER TABLE pilot_material_operations FORCE ROW LEVEL SECURITY;
ALTER TABLE pilot_material_impact_tokens ENABLE ROW LEVEL SECURITY; ALTER TABLE pilot_material_impact_tokens FORCE ROW LEVEL SECURITY;
DO $$ DECLARE item TEXT; BEGIN
  FOREACH item IN ARRAY ARRAY['pilot_material_revisions','pilot_material_operations','pilot_material_impact_tokens'] LOOP
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname=current_schema() AND tablename=item AND policyname=item||'_owner_all') THEN
      EXECUTE format('CREATE POLICY %I ON %I FOR ALL USING (tenant_id=current_setting(''yike.tenant_id'',true) AND owner_user_id=current_setting(''yike.user_id'',true)) WITH CHECK (tenant_id=current_setting(''yike.tenant_id'',true) AND owner_user_id=current_setting(''yike.user_id'',true))',item||'_owner_all',item);
    END IF;
  END LOOP;
END $$;
CREATE OR REPLACE FUNCTION pilot_material_history_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'material history is immutable'; END $$;
DO $$ DECLARE item TEXT; BEGIN
  FOREACH item IN ARRAY ARRAY['pilot_material_revisions','pilot_material_operations'] LOOP
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgrelid=to_regclass('public.'||item) AND tgname=item||'_immutable') THEN
      EXECUTE format('CREATE TRIGGER %I BEFORE UPDATE OR DELETE ON %I FOR EACH ROW EXECUTE FUNCTION pilot_material_history_immutable()',item||'_immutable',item);
    END IF;
  END LOOP;
END $$;
