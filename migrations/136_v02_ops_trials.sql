CREATE TABLE IF NOT EXISTS pilot_trial_accounts (
    trial_id UUID PRIMARY KEY,
    user_id TEXT NOT NULL UNIQUE REFERENCES pilot_users(user_id),
    phone_hash TEXT NOT NULL UNIQUE REFERENCES pilot_phone_bindings(phone_hash),
    phone_ciphertext BYTEA NOT NULL,
    code_hash TEXT NOT NULL UNIQUE CHECK (code_hash ~ '^[a-f0-9]{64}$'),
    days INTEGER NOT NULL DEFAULT 3 CHECK (days BETWEEN 1 AND 30),
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    redeem_before TIMESTAMPTZ NOT NULL DEFAULT (clock_timestamp() + interval '30 days'),
    activated_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ,
    revoked_at TIMESTAMPTZ,
    CHECK ((activated_at IS NULL) = (expires_at IS NULL))
);
ALTER TABLE pilot_trial_accounts ENABLE ROW LEVEL SECURITY;
-- Trusted migration owner can read through the narrow SECURITY DEFINER check;
-- customer/ops roles must not own this table or reach its owner.
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname='public' AND tablename='pilot_trial_accounts' AND policyname='trial_self') THEN
        CREATE POLICY trial_self ON pilot_trial_accounts
            USING (user_id=current_setting('yike.user_id',true))
            WITH CHECK (user_id=current_setting('yike.user_id',true));
    END IF;
END $$;
REVOKE ALL ON pilot_trial_accounts FROM PUBLIC;

CREATE TABLE IF NOT EXISTS pilot_ops_sessions (
    token_hash TEXT PRIMARY KEY CHECK (token_hash ~ '^[a-f0-9]{64}$'),
    expires_at TIMESTAMPTZ NOT NULL
);
ALTER TABLE pilot_ops_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE pilot_ops_sessions FORCE ROW LEVEL SECURITY;
REVOKE ALL ON pilot_ops_sessions FROM PUBLIC;

CREATE OR REPLACE FUNCTION public.pilot_trial_allowed() RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $$
    SELECT NOT EXISTS (
        SELECT 1 FROM public.pilot_trial_accounts
        WHERE user_id=current_setting('yike.user_id',true)
          AND (activated_at IS NULL OR revoked_at IS NOT NULL OR expires_at<=clock_timestamp())
    )
$$;
-- Boolean access gate only: no phone, code or row is returned. Legacy roles
-- also evaluate it so already-issued sessions cannot bypass trial expiry.
REVOKE ALL ON FUNCTION public.pilot_trial_allowed() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.pilot_trial_allowed() TO PUBLIC;
