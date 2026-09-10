-- Human-confirmed queue only. No dispatch lease or platform result is implied.
CREATE TABLE IF NOT EXISTS pilot_outreach_queue (
    tenant_id TEXT NOT NULL,
    owner_user_id TEXT NOT NULL,
    request_id TEXT NOT NULL,
    opportunity_id TEXT NOT NULL,
    channel TEXT NOT NULL CHECK (channel IN ('comment','dm')),
    state TEXT NOT NULL DEFAULT 'QUEUED' CHECK (state IN ('QUEUED','CANCELLED')),
    request_sha256 TEXT NOT NULL CHECK (request_sha256 ~ '^[a-f0-9]{64}$'),
    request_payload JSONB NOT NULL,
    context_payload JSONB NOT NULL,
    confirmed_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (tenant_id,owner_user_id,request_id),
    FOREIGN KEY (tenant_id,opportunity_id) REFERENCES pilot_opportunities(tenant_id,opportunity_id),
    CHECK ((jsonb_typeof(request_payload)='object' AND jsonb_typeof(context_payload)='object'
        AND request_payload->>'requestId'=request_id
        AND request_payload->'humanConfirmed'='true'::jsonb
        AND request_payload#>>'{channelCheck,status}'='AVAILABLE'
        AND request_payload#>>'{context,binding,opportunityId}'=opportunity_id
        AND request_payload#>>'{context,binding,channel}'=channel
        AND request_payload->>'contextSha256'=context_payload->>'contextSha256'
        AND request_payload#>'{context,binding}'=context_payload->'binding'
        AND context_payload->>'ownerUserId'=owner_user_id
        AND context_payload#>>'{accountScope,id}'=tenant_id
    ) IS TRUE)
);
CREATE UNIQUE INDEX IF NOT EXISTS pilot_outreach_one_pending
    ON pilot_outreach_queue(tenant_id,owner_user_id,opportunity_id,channel) WHERE state='QUEUED';
ALTER TABLE pilot_outreach_queue ENABLE ROW LEVEL SECURITY;
ALTER TABLE pilot_outreach_queue FORCE ROW LEVEL SECURITY;
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname=current_schema() AND tablename='pilot_outreach_queue' AND policyname='outreach_queue_owner') THEN
        CREATE POLICY outreach_queue_owner ON pilot_outreach_queue
            USING (tenant_id=current_setting('yike.tenant_id',true) AND owner_user_id=current_setting('yike.user_id',true))
            WITH CHECK (tenant_id=current_setting('yike.tenant_id',true) AND owner_user_id=current_setting('yike.user_id',true));
    END IF;
END $$;
CREATE OR REPLACE FUNCTION pilot_outreach_queue_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP='UPDATE' AND OLD.state='QUEUED' AND NEW.state='CANCELLED'
        AND to_jsonb(NEW)-'state'=to_jsonb(OLD)-'state' THEN RETURN NEW; END IF;
    RAISE EXCEPTION 'outreach confirmation is immutable; only queued cancellation allowed';
END $$;
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgrelid='pilot_outreach_queue'::regclass AND tgname='outreach_queue_guard') THEN
        CREATE TRIGGER outreach_queue_guard BEFORE UPDATE OR DELETE ON pilot_outreach_queue
            FOR EACH ROW EXECUTE FUNCTION pilot_outreach_queue_guard();
    END IF;
END $$;
