-- Historical devices deliberately keep NULL ownership: never first-claim wins.
ALTER TABLE pilot_devices ADD COLUMN IF NOT EXISTS owner_user_id TEXT;
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid='pilot_devices'::regclass AND conname='pilot_device_owner_fk') THEN
        ALTER TABLE pilot_devices ADD CONSTRAINT pilot_device_owner_fk
            FOREIGN KEY (tenant_id, owner_user_id) REFERENCES pilot_users(tenant_id, user_id);
    END IF;
END $$;
CREATE UNIQUE INDEX IF NOT EXISTS pilot_devices_tenant_owner_device_key
    ON pilot_devices(tenant_id, owner_user_id, device_id);

CREATE TABLE IF NOT EXISTS pilot_device_credentials (
    tenant_id TEXT NOT NULL,
    owner_user_id TEXT NOT NULL,
    device_id TEXT NOT NULL,
    public_key TEXT NOT NULL CHECK (public_key ~ '^[A-Za-z0-9_-]{43}$'),
    credential_version INTEGER NOT NULL CHECK (credential_version BETWEEN 1 AND 2147483647),
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (tenant_id, device_id),
    FOREIGN KEY (tenant_id, owner_user_id, device_id)
        REFERENCES pilot_devices(tenant_id, owner_user_id, device_id)
);

CREATE TABLE IF NOT EXISTS pilot_device_key_requests (
    tenant_id TEXT NOT NULL,
    owner_user_id TEXT NOT NULL,
    request_id TEXT NOT NULL CHECK (request_id ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'),
    challenge_id TEXT NOT NULL CHECK (challenge_id ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'),
    device_id TEXT NOT NULL,
    session_digest TEXT NOT NULL CHECK (session_digest ~ '^[0-9a-f]{64}$'),
    request_sha256 TEXT NOT NULL CHECK (request_sha256 ~ '^[0-9a-f]{64}$'),
    operation TEXT NOT NULL CHECK (operation IN ('BIND','PROVE','ROTATE')),
    expected_credential_version INTEGER NOT NULL CHECK (expected_credential_version BETWEEN 0 AND 2147483646),
    target_public_key TEXT NOT NULL CHECK (target_public_key ~ '^[A-Za-z0-9_-]{43}$'),
    signing_payload TEXT NOT NULL CHECK (length(signing_payload) BETWEEN 1 AND 4096),
    expires_at TIMESTAMPTZ NOT NULL,
    state TEXT NOT NULL DEFAULT 'PENDING' CHECK (state IN ('PENDING','SUCCEEDED','REJECTED','EXPIRED')),
    result_version INTEGER CHECK (result_version BETWEEN 1 AND 2147483647),
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    completed_at TIMESTAMPTZ,
    PRIMARY KEY (tenant_id, owner_user_id, request_id),
    UNIQUE (tenant_id, owner_user_id, challenge_id),
    FOREIGN KEY (tenant_id, owner_user_id, device_id)
        REFERENCES pilot_devices(tenant_id, owner_user_id, device_id),
    CHECK ((state='SUCCEEDED') = (result_version IS NOT NULL)),
    CHECK ((operation='BIND') = (expected_credential_version=0))
);
CREATE INDEX IF NOT EXISTS pilot_device_pending_keys
    ON pilot_device_key_requests(tenant_id, device_id, expires_at) WHERE state='PENDING';

ALTER TABLE pilot_device_credentials ENABLE ROW LEVEL SECURITY;
ALTER TABLE pilot_device_credentials FORCE ROW LEVEL SECURITY;
ALTER TABLE pilot_device_key_requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE pilot_device_key_requests FORCE ROW LEVEL SECURITY;
DO $$
DECLARE table_name TEXT; action TEXT;
BEGIN
    FOREACH table_name IN ARRAY ARRAY['pilot_device_credentials','pilot_device_key_requests'] LOOP
        FOREACH action IN ARRAY ARRAY['SELECT','INSERT','UPDATE'] LOOP
            IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname=current_schema()
                AND tablename=table_name AND policyname='device_owner_' || lower(action)) THEN
                IF action='INSERT' THEN
                    EXECUTE format('CREATE POLICY %I ON %I FOR INSERT WITH CHECK (tenant_id=current_setting(''yike.tenant_id'',true) AND owner_user_id=current_setting(''yike.user_id'',true))', 'device_owner_insert', table_name);
                ELSE
                    EXECUTE format('CREATE POLICY %I ON %I FOR %s USING (tenant_id=current_setting(''yike.tenant_id'',true) AND owner_user_id=current_setting(''yike.user_id'',true))', 'device_owner_' || lower(action), table_name, action);
                END IF;
            END IF;
        END LOOP;
    END LOOP;
END $$;
-- No DELETE policy and no runtime grants. See grant_device_credentials.sql.
