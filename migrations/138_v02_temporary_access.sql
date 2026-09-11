-- An SMS trial invitation is never a standalone authentication credential.
ALTER TABLE pilot_trial_accounts ADD COLUMN IF NOT EXISTS credential_kind TEXT NOT NULL DEFAULT 'SMS_TRIAL'
    CHECK (credential_kind IN ('SMS_TRIAL','TEMPORARY_ACCESS'));
ALTER TABLE pilot_trial_accounts ADD COLUMN IF NOT EXISTS access_code_hash TEXT UNIQUE
    CHECK (access_code_hash ~ '^[a-f0-9]{64}$');
ALTER TABLE pilot_trial_accounts ADD COLUMN IF NOT EXISTS access_issued_at TIMESTAMPTZ;
ALTER TABLE pilot_trial_accounts ADD COLUMN IF NOT EXISTS activation_source TEXT
    CHECK (activation_source IN ('SMS','TEMPORARY_ACCESS'));
-- Do not infer historical phone verification from trial activation.
ALTER TABLE pilot_phone_bindings ADD COLUMN IF NOT EXISTS phone_verified_at TIMESTAMPTZ;

CREATE TABLE IF NOT EXISTS pilot_access_rates (
    kind TEXT NOT NULL CHECK (kind IN ('peer','global')),
    scope_hash TEXT NOT NULL,
    hits TIMESTAMPTZ[] NOT NULL CHECK (cardinality(hits) <= 100),
    PRIMARY KEY(kind,scope_hash),
    CHECK ((kind='global' AND scope_hash='service') OR (kind='peer' AND scope_hash ~ '^[a-f0-9]{64}$'))
);
ALTER TABLE pilot_access_rates ENABLE ROW LEVEL SECURITY;
ALTER TABLE pilot_access_rates FORCE ROW LEVEL SECURITY;
REVOKE ALL ON pilot_access_rates FROM PUBLIC;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname='public' AND tablename='pilot_trial_accounts' AND policyname='temporary_access_lookup') THEN
        CREATE POLICY temporary_access_lookup ON pilot_trial_accounts
            USING (credential_kind='TEMPORARY_ACCESS' AND access_code_hash=current_setting('yike.access_hash',true))
            WITH CHECK (credential_kind='TEMPORARY_ACCESS' AND access_code_hash=current_setting('yike.access_hash',true));
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname='public' AND tablename='pilot_access_rates' AND policyname='access_rate_scope') THEN
        CREATE POLICY access_rate_scope ON pilot_access_rates USING (
            current_setting('yike.access_peer',true) ~ '^[a-f0-9]{64}$' AND
            ((kind='peer' AND scope_hash=current_setting('yike.access_peer',true)) OR (kind='global' AND scope_hash='service'))
        );
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname='public' AND tablename='pilot_phone_bindings' AND policyname='phone_verified_update') THEN
        CREATE POLICY phone_verified_update ON pilot_phone_bindings FOR UPDATE
            USING (phone_hash=current_setting('yike.auth_phone',true))
            WITH CHECK (phone_hash=current_setting('yike.auth_phone',true));
    END IF;
END $$;
