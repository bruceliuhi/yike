-- Immutable operator action history.  This table deliberately stores only
-- opaque identifiers and a one-way session fingerprint; never phone numbers,
-- trial codes, cookies, IP addresses, or submitted form values.
CREATE TABLE IF NOT EXISTS pilot_ops_audit_events (
    event_id UUID PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    action TEXT NOT NULL CHECK (action IN ('ISSUE','REISSUE','REVOKE','ISSUE_ACCESS')),
    result TEXT NOT NULL CHECK (result IN ('SUCCEEDED','REJECTED','FAILED')),
    actor_hash TEXT NOT NULL CHECK (actor_hash ~ '^[a-f0-9]{64}$'),
    trial_id UUID,
    user_id TEXT,
    error_code TEXT CHECK (error_code IS NULL OR error_code ~ '^[a-z0-9_]{1,64}$'),
    CHECK (result = 'SUCCEEDED' OR error_code IS NOT NULL)
);
ALTER TABLE pilot_ops_audit_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE pilot_ops_audit_events FORCE ROW LEVEL SECURITY;
REVOKE ALL ON pilot_ops_audit_events FROM PUBLIC;
CREATE INDEX IF NOT EXISTS pilot_ops_audit_events_created_idx
    ON pilot_ops_audit_events (created_at DESC, event_id DESC);
CREATE INDEX IF NOT EXISTS pilot_ops_audit_events_action_result_idx
    ON pilot_ops_audit_events (action, result, created_at DESC, event_id DESC);

CREATE OR REPLACE FUNCTION public.pilot_ops_audit_immutable() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog AS $$
BEGIN
    RAISE EXCEPTION 'pilot operator audit events are append-only';
END;
$$;
REVOKE ALL ON FUNCTION public.pilot_ops_audit_immutable() FROM PUBLIC;
DROP TRIGGER IF EXISTS pilot_ops_audit_append_only ON pilot_ops_audit_events;
CREATE TRIGGER pilot_ops_audit_append_only
    BEFORE UPDATE OR DELETE ON pilot_ops_audit_events
    FOR EACH ROW EXECUTE FUNCTION public.pilot_ops_audit_immutable();
