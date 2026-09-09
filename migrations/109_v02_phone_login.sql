CREATE TABLE IF NOT EXISTS pilot_phone_bindings (
    phone_hash TEXT PRIMARY KEY CHECK (phone_hash ~ '^[a-f0-9]{64}$'),
    user_id TEXT NOT NULL UNIQUE REFERENCES pilot_users(user_id)
);
CREATE TABLE IF NOT EXISTS pilot_phone_challenges (
    phone_hash TEXT PRIMARY KEY CHECK (phone_hash ~ '^[a-f0-9]{64}$'),
    challenge_id UUID NOT NULL,
    otp_hash TEXT NOT NULL CHECK (otp_hash ~ '^[a-f0-9]{64}$'),
    created_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    state TEXT NOT NULL DEFAULT 'PENDING' CHECK (state IN ('PENDING','ACCEPTED','REJECTED','UNKNOWN')),
    failures INTEGER NOT NULL DEFAULT 0 CHECK (failures BETWEEN 0 AND 5),
    consumed BOOLEAN NOT NULL DEFAULT false
);
CREATE TABLE IF NOT EXISTS pilot_phone_rates (
    kind TEXT NOT NULL CHECK (kind IN ('phone','peer','global')),
    scope_hash TEXT NOT NULL,
    hits TIMESTAMPTZ[] NOT NULL,
    PRIMARY KEY(kind,scope_hash),
    CHECK (cardinality(hits) <= 100),
    CHECK ((kind='global' AND scope_hash='service') OR (kind IN ('phone','peer') AND scope_hash ~ '^[a-f0-9]{64}$'))
);
ALTER TABLE pilot_phone_bindings ENABLE ROW LEVEL SECURITY;
ALTER TABLE pilot_phone_bindings FORCE ROW LEVEL SECURITY;
ALTER TABLE pilot_phone_challenges ENABLE ROW LEVEL SECURITY;
ALTER TABLE pilot_phone_challenges FORCE ROW LEVEL SECURITY;
ALTER TABLE pilot_phone_rates ENABLE ROW LEVEL SECURITY;
ALTER TABLE pilot_phone_rates FORCE ROW LEVEL SECURITY;
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname=current_schema() AND tablename='pilot_phone_bindings' AND policyname='phone_binding_read') THEN
        CREATE POLICY phone_binding_read ON pilot_phone_bindings FOR SELECT USING (phone_hash=current_setting('yike.auth_phone',true) OR user_id=current_setting('yike.user_id',true));
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname=current_schema() AND tablename='pilot_phone_challenges' AND policyname='phone_challenge_scope') THEN
        CREATE POLICY phone_challenge_scope ON pilot_phone_challenges USING (phone_hash=current_setting('yike.auth_phone',true)) WITH CHECK (phone_hash=current_setting('yike.auth_phone',true));
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname=current_schema() AND tablename='pilot_phone_rates' AND policyname='phone_rate_scope') THEN
        CREATE POLICY phone_rate_scope ON pilot_phone_rates USING (
            (kind='phone' AND scope_hash=current_setting('yike.auth_phone',true)) OR
            (kind='peer' AND scope_hash=current_setting('yike.auth_peer',true)) OR
            (kind='global' AND current_setting('yike.auth_phone',true) ~ '^[a-f0-9]{64}$' AND current_setting('yike.auth_peer',true) ~ '^[a-f0-9]{64}$')
        );
    END IF;
END $$;
REVOKE ALL ON pilot_phone_bindings, pilot_phone_challenges, pilot_phone_rates FROM PUBLIC;
