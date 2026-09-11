CREATE TABLE IF NOT EXISTS pilot_short_coach_requests (
 tenant_id TEXT NOT NULL, owner_user_id TEXT NOT NULL, request_id TEXT NOT NULL,
 opportunity_id TEXT NOT NULL, request_hash TEXT NOT NULL CHECK(request_hash ~ '^[0-9a-f]{64}$'),
 model_provider TEXT NOT NULL, model_name TEXT NOT NULL,
 state TEXT NOT NULL CHECK(state IN ('PROCESSING','SUCCEEDED','FAILED')),
 result JSONB, error_code TEXT, created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
 updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(), PRIMARY KEY(tenant_id,owner_user_id,request_id),
 FOREIGN KEY(tenant_id,owner_user_id) REFERENCES pilot_users(tenant_id,user_id),
 FOREIGN KEY(tenant_id,opportunity_id) REFERENCES pilot_opportunities(tenant_id,opportunity_id),
 CHECK((state='PROCESSING' AND result IS NULL AND error_code IS NULL) OR
       (state='SUCCEEDED' AND jsonb_typeof(result)='object' AND error_code IS NULL) OR
       (state='FAILED' AND result IS NULL AND error_code='short_coach_failed')));
CREATE UNIQUE INDEX IF NOT EXISTS pilot_short_coach_one_processing_per_tenant
 ON pilot_short_coach_requests(tenant_id) WHERE state='PROCESSING';
ALTER TABLE pilot_short_coach_requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE pilot_short_coach_requests FORCE ROW LEVEL SECURITY;
DO $$ BEGIN IF NOT EXISTS(SELECT 1 FROM pg_policies WHERE tablename='pilot_short_coach_requests' AND policyname='short_coach_owner') THEN
 CREATE POLICY short_coach_owner ON pilot_short_coach_requests USING(tenant_id=current_setting('yike.tenant_id',true) AND owner_user_id=current_setting('yike.user_id',true))
 WITH CHECK(tenant_id=current_setting('yike.tenant_id',true) AND owner_user_id=current_setting('yike.user_id',true)); END IF; END $$;
CREATE OR REPLACE FUNCTION pilot_short_coach_transition_guard() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
 IF TG_OP='INSERT' AND NEW.state<>'PROCESSING' THEN RAISE EXCEPTION USING ERRCODE='YC001'; END IF;
 IF TG_OP='UPDATE' AND (OLD.state<>'PROCESSING' OR NEW.state='PROCESSING' OR ROW(NEW.tenant_id,NEW.owner_user_id,NEW.request_id,NEW.opportunity_id,NEW.request_hash,NEW.model_provider,NEW.model_name,NEW.created_at) IS DISTINCT FROM ROW(OLD.tenant_id,OLD.owner_user_id,OLD.request_id,OLD.opportunity_id,OLD.request_hash,OLD.model_provider,OLD.model_name,OLD.created_at)) THEN RAISE EXCEPTION USING ERRCODE='YC001'; END IF;
 NEW.updated_at=clock_timestamp(); RETURN NEW; END $$;
DROP TRIGGER IF EXISTS pilot_short_coach_transition_guard ON pilot_short_coach_requests;
CREATE TRIGGER pilot_short_coach_transition_guard BEFORE INSERT OR UPDATE ON pilot_short_coach_requests FOR EACH ROW EXECUTE FUNCTION pilot_short_coach_transition_guard();
