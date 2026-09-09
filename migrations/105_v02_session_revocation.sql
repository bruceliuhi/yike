CREATE UNIQUE INDEX IF NOT EXISTS pilot_users_tenant_user_key
    ON pilot_users(tenant_id, user_id);

-- This is not a credential vault. No usable tokens, cookies or signing secrets.
CREATE TABLE IF NOT EXISTS pilot_session_revocations (
    tenant_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    revocation_key TEXT NOT NULL CHECK (revocation_key ~ '^[0-9a-f]{64}$'),
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, revocation_key),
    -- A revoked user cannot be reparented and thereby hide their tombstones.
    FOREIGN KEY (tenant_id, user_id) REFERENCES pilot_users(tenant_id, user_id)
);

ALTER TABLE pilot_session_revocations ENABLE ROW LEVEL SECURITY;
ALTER TABLE pilot_session_revocations FORCE ROW LEVEL SECURITY;
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname = current_schema() AND tablename = 'pilot_session_revocations' AND policyname = 'session_revocations_read') THEN
        CREATE POLICY session_revocations_read ON pilot_session_revocations FOR SELECT
            USING (tenant_id = current_setting('yike.tenant_id', true)
                AND user_id = current_setting('yike.user_id', true));
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname = current_schema() AND tablename = 'pilot_session_revocations' AND policyname = 'session_revocations_insert') THEN
        CREATE POLICY session_revocations_insert ON pilot_session_revocations FOR INSERT
            WITH CHECK (tenant_id = current_setting('yike.tenant_id', true)
                AND user_id = current_setting('yike.user_id', true));
    END IF;
END $$;
-- No application UPDATE/DELETE policy: a retry cannot un-revoke a credential.
-- No cleanup job yet. Expired records must not be deleted before token expiry.
