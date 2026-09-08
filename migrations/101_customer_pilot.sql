CREATE TABLE IF NOT EXISTS pilot_schema_meta (
    version TEXT PRIMARY KEY,
    checksum TEXT NOT NULL,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
ALTER TABLE pilot_schema_meta ADD COLUMN IF NOT EXISTS checksum TEXT NOT NULL DEFAULT 'legacy-unknown';

CREATE TABLE IF NOT EXISTS pilot_tenants (
    tenant_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS pilot_users (
    user_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES pilot_tenants(tenant_id),
    email TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (tenant_id, email)
);

CREATE TABLE IF NOT EXISTS business_profiles (
    profile_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES pilot_tenants(tenant_id),
    name TEXT NOT NULL DEFAULT '默认业务画像',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (tenant_id, profile_id)
);

CREATE TABLE IF NOT EXISTS business_profile_versions (
    profile_version_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    profile_id TEXT NOT NULL,
    version INTEGER NOT NULL CHECK (version > 0),
    payload JSONB NOT NULL,
    content_sha256 TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'DRAFT' CHECK (status IN ('DRAFT', 'CONFIRMED', 'REVOKED')),
    approved_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (tenant_id, profile_id, version),
    UNIQUE (tenant_id, profile_version_id),
    UNIQUE (tenant_id, profile_id, content_sha256),
    FOREIGN KEY (tenant_id, profile_id) REFERENCES business_profiles(tenant_id, profile_id)
);

ALTER TABLE business_profile_versions ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'DRAFT';
ALTER TABLE business_profile_versions DROP CONSTRAINT IF EXISTS business_profile_versions_status_check;
ALTER TABLE business_profile_versions ADD CONSTRAINT business_profile_versions_status_check CHECK (status IN ('DRAFT', 'CONFIRMED', 'REVOKED'));

CREATE TABLE IF NOT EXISTS pilot_sources (
    source_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES pilot_tenants(tenant_id),
    platform TEXT NOT NULL,
    external_id TEXT NOT NULL,
    public_url TEXT NOT NULL,
    published_at TIMESTAMPTZ,
    health TEXT NOT NULL DEFAULT 'UNVERIFIED',
    UNIQUE (tenant_id, platform, external_id),
    UNIQUE (tenant_id, source_id)
);

CREATE TABLE IF NOT EXISTS pilot_opportunities (
    opportunity_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    profile_version_id TEXT NOT NULL,
    source_id TEXT NOT NULL,
    import_key TEXT NOT NULL,
    title TEXT NOT NULL,
    buyer TEXT NOT NULL,
    summary TEXT NOT NULL,
    contact_path TEXT NOT NULL,
    public_excerpt TEXT,
    draft_comment TEXT NOT NULL,
    draft_dm TEXT NOT NULL,
    intent_status TEXT NOT NULL DEFAULT 'NEW' CHECK (intent_status IN ('NEW', 'REVIEW', 'READY', 'CONTACTED', 'CLOSED')),
    source_status TEXT NOT NULL DEFAULT 'OPEN' CHECK (source_status IN ('OPEN', 'EXPIRED', 'BLOCKED', 'UNVERIFIED')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (tenant_id, import_key),
    UNIQUE (tenant_id, opportunity_id),
    FOREIGN KEY (tenant_id, profile_version_id) REFERENCES business_profile_versions(tenant_id, profile_version_id),
    FOREIGN KEY (tenant_id, source_id) REFERENCES pilot_sources(tenant_id, source_id)
);

CREATE TABLE IF NOT EXISTS pilot_followups (
    followup_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    opportunity_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('NOT_CONTACTED', 'CONTACTED', 'REPLIED', 'MEETING', 'QUOTED', 'LOST', 'WON')),
    note TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (tenant_id, opportunity_id) REFERENCES pilot_opportunities(tenant_id, opportunity_id)
);

CREATE TABLE IF NOT EXISTS pilot_tasks (
    task_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES pilot_tenants(tenant_id),
    task_key TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING', 'RUNNING', 'DONE', 'FAILED')),
    lease_owner TEXT,
    lease_until TIMESTAMPTZ,
    UNIQUE (tenant_id, task_key)
);

ALTER TABLE pilot_users ENABLE ROW LEVEL SECURITY;
ALTER TABLE business_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE business_profile_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE pilot_sources ENABLE ROW LEVEL SECURITY;
ALTER TABLE pilot_opportunities ENABLE ROW LEVEL SECURITY;
ALTER TABLE pilot_followups ENABLE ROW LEVEL SECURITY;
ALTER TABLE pilot_tasks ENABLE ROW LEVEL SECURITY;
ALTER TABLE pilot_users FORCE ROW LEVEL SECURITY;
ALTER TABLE business_profiles FORCE ROW LEVEL SECURITY;
ALTER TABLE business_profile_versions FORCE ROW LEVEL SECURITY;
ALTER TABLE pilot_sources FORCE ROW LEVEL SECURITY;
ALTER TABLE pilot_opportunities FORCE ROW LEVEL SECURITY;
ALTER TABLE pilot_followups FORCE ROW LEVEL SECURITY;
ALTER TABLE pilot_tasks FORCE ROW LEVEL SECURITY;

DO $$
DECLARE table_name TEXT;
BEGIN
    FOREACH table_name IN ARRAY ARRAY[
        'business_profiles', 'business_profile_versions',
        'pilot_sources', 'pilot_opportunities', 'pilot_followups', 'pilot_tasks'
    ] LOOP
        IF NOT EXISTS (
            SELECT 1 FROM pg_policies
            WHERE schemaname = current_schema() AND tablename = table_name
              AND policyname = 'pilot_tenant_scope'
        ) THEN
            EXECUTE format(
                'CREATE POLICY pilot_tenant_scope ON %I USING (tenant_id = current_setting(''yike.tenant_id'', true)) WITH CHECK (tenant_id = current_setting(''yike.tenant_id'', true))',
                table_name
            );
        END IF;
    END LOOP;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname = current_schema() AND tablename = 'pilot_users' AND policyname = 'pilot_user_identity') THEN
        CREATE POLICY pilot_user_identity ON pilot_users
            USING (user_id = current_setting('yike.user_id', true))
            WITH CHECK (tenant_id = current_setting('yike.tenant_id', true));
    END IF;
END $$;
