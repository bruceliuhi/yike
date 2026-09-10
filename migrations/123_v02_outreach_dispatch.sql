-- One immutable dispatch grant, append-only results; no automatic retries.
CREATE TABLE IF NOT EXISTS pilot_outreach_claims (
    tenant_id TEXT NOT NULL,
    owner_user_id TEXT NOT NULL,
    request_id TEXT NOT NULL,
    claim_id TEXT NOT NULL,
    request_sha256 TEXT NOT NULL CHECK (request_sha256 ~ '^[a-f0-9]{64}$'),
    payload JSONB NOT NULL,
    claimed_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    dispatch_before TIMESTAMPTZ NOT NULL,
    PRIMARY KEY(tenant_id,owner_user_id,request_id),
    UNIQUE(tenant_id,owner_user_id,claim_id),
    UNIQUE(tenant_id,owner_user_id,request_id,claim_id),
    FOREIGN KEY(tenant_id,owner_user_id,request_id) REFERENCES pilot_outreach_queue(tenant_id,owner_user_id,request_id),
    CHECK ((payload->>'action'='CLAIM' AND payload->>'requestId'=request_id AND payload->>'claimId'=claim_id) IS TRUE)
);
CREATE TABLE IF NOT EXISTS pilot_outreach_results (
    tenant_id TEXT NOT NULL,
    owner_user_id TEXT NOT NULL,
    result_id TEXT NOT NULL,
    request_id TEXT NOT NULL,
    claim_id TEXT NOT NULL,
    request_sha256 TEXT NOT NULL CHECK (request_sha256 ~ '^[a-f0-9]{64}$'),
    payload JSONB NOT NULL,
    receipt JSONB NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY(tenant_id,owner_user_id,result_id),
    FOREIGN KEY(tenant_id,owner_user_id,request_id,claim_id) REFERENCES pilot_outreach_claims(tenant_id,owner_user_id,request_id,claim_id),
    CHECK ((payload->>'action'='RESULT' AND payload->>'requestId'=request_id
        AND payload->>'claimId'=claim_id AND payload->>'resultId'=result_id
        AND payload#>>'{outcome,status}' IN ('UNKNOWN','SENT','FAILED')
        AND receipt->>'state'=payload#>>'{outcome,status}'
        AND receipt->>'requestId'=request_id AND receipt->>'claimId'=claim_id
        AND receipt->>'resultId'=result_id AND receipt->'dispatchAllowed'='false'::jsonb) IS TRUE)
);
ALTER TABLE pilot_outreach_queue DROP CONSTRAINT IF EXISTS pilot_outreach_queue_state_check;
ALTER TABLE pilot_outreach_queue ADD CONSTRAINT pilot_outreach_queue_state_check
    CHECK (state IN ('QUEUED','UNKNOWN','SENT','FAILED','CANCELLED'));
DROP INDEX IF EXISTS pilot_outreach_one_pending;
CREATE UNIQUE INDEX pilot_outreach_one_pending ON pilot_outreach_queue(tenant_id,owner_user_id,opportunity_id,channel)
    WHERE state NOT IN ('CANCELLED','FAILED');
CREATE OR REPLACE FUNCTION pilot_outreach_queue_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP='UPDATE' AND to_jsonb(NEW)-'state'=to_jsonb(OLD)-'state' THEN
        IF OLD.state='QUEUED' AND NEW.state='CANCELLED' AND NOT EXISTS
            (SELECT 1 FROM pilot_outreach_claims WHERE tenant_id=OLD.tenant_id AND owner_user_id=OLD.owner_user_id AND request_id=OLD.request_id)
            THEN RETURN NEW; END IF;
        IF OLD.state='QUEUED' AND NEW.state='UNKNOWN' AND EXISTS
            (SELECT 1 FROM pilot_outreach_claims WHERE tenant_id=OLD.tenant_id AND owner_user_id=OLD.owner_user_id AND request_id=OLD.request_id)
            THEN RETURN NEW; END IF;
        IF OLD.state='UNKNOWN' AND NEW.state IN ('SENT','FAILED') AND EXISTS
            (SELECT 1 FROM pilot_outreach_results WHERE tenant_id=OLD.tenant_id AND owner_user_id=OLD.owner_user_id AND request_id=OLD.request_id AND receipt->>'state'=NEW.state)
            THEN RETURN NEW; END IF;
    END IF;
    RAISE EXCEPTION 'invalid outreach transition or immutable confirmation change';
END $$;
CREATE OR REPLACE FUNCTION pilot_outreach_dispatch_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'outreach dispatch history is immutable'; END $$;
DO $$ DECLARE table_name TEXT;
BEGIN
    FOREACH table_name IN ARRAY ARRAY['pilot_outreach_claims','pilot_outreach_results'] LOOP
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY',table_name);
        EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY',table_name);
        IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname=current_schema() AND tablename=table_name AND policyname='outreach_dispatch_owner') THEN
            EXECUTE format('CREATE POLICY outreach_dispatch_owner ON %I USING (tenant_id=current_setting(''yike.tenant_id'',true) AND owner_user_id=current_setting(''yike.user_id'',true)) WITH CHECK (tenant_id=current_setting(''yike.tenant_id'',true) AND owner_user_id=current_setting(''yike.user_id'',true))',table_name);
        END IF;
        IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgrelid=table_name::regclass AND tgname='outreach_dispatch_immutable') THEN
            EXECUTE format('CREATE TRIGGER outreach_dispatch_immutable BEFORE UPDATE OR DELETE ON %I FOR EACH ROW EXECUTE FUNCTION pilot_outreach_dispatch_immutable()',table_name);
        END IF;
    END LOOP;
END $$;
