-- Append-only provider usage evidence for ordinary candidate ASSESS invocations.
CREATE TABLE IF NOT EXISTS pilot_candidate_model_usage_events (
 tenant_id TEXT NOT NULL,
 owner_user_id TEXT NOT NULL,
 request_id TEXT NOT NULL,
 snapshot_key TEXT NOT NULL CHECK(snapshot_key ~ '^[0-9a-f]{64}$'),
 phase TEXT NOT NULL CHECK(phase IN ('DISPATCH','FINISH')),
 outcome TEXT CHECK(outcome IN ('SUCCEEDED','FAILED','UNKNOWN')),
 usage JSONB,
 recorded_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(tenant_id,owner_user_id,request_id,phase),
 FOREIGN KEY(tenant_id,owner_user_id,request_id)
  REFERENCES pilot_candidate_review_requests(tenant_id,owner_user_id,request_id),
 CHECK ((phase='DISPATCH' AND outcome IS NULL AND usage IS NULL)
     OR (phase='FINISH' AND outcome IS NOT NULL)),
 CHECK (usage IS NULL OR (
     jsonb_typeof(usage)='object'
     AND usage ?& ARRAY['prompt_tokens','completion_tokens','total_tokens']
     AND usage-ARRAY['prompt_tokens','completion_tokens','total_tokens']='{}'::jsonb
     AND jsonb_typeof(usage->'prompt_tokens')='number'
     AND jsonb_typeof(usage->'completion_tokens')='number'
     AND jsonb_typeof(usage->'total_tokens')='number'
     AND usage->>'prompt_tokens' ~ '^(0|[1-9][0-9]*)$'
     AND usage->>'completion_tokens' ~ '^(0|[1-9][0-9]*)$'
     AND usage->>'total_tokens' ~ '^(0|[1-9][0-9]*)$'
     AND (usage->>'prompt_tokens')::numeric < 2147483648
     AND (usage->>'completion_tokens')::numeric < 2147483648
     AND (usage->>'total_tokens')::numeric < 2147483648
     AND (usage->>'prompt_tokens')::numeric + (usage->>'completion_tokens')::numeric
         = (usage->>'total_tokens')::numeric
  )),
 CHECK (phase='FINISH' OR usage IS NULL)
);

ALTER TABLE pilot_candidate_model_usage_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE pilot_candidate_model_usage_events FORCE ROW LEVEL SECURITY;
DO $$ BEGIN
 IF NOT EXISTS(SELECT 1 FROM pg_policies WHERE schemaname=current_schema()
    AND tablename='pilot_candidate_model_usage_events'
    AND policyname='candidate_model_usage_owner') THEN
  CREATE POLICY candidate_model_usage_owner ON pilot_candidate_model_usage_events
   USING(tenant_id=current_setting('yike.tenant_id',true)
     AND owner_user_id=current_setting('yike.user_id',true))
   WITH CHECK(tenant_id=current_setting('yike.tenant_id',true)
     AND owner_user_id=current_setting('yike.user_id',true));
 END IF;
END $$;

CREATE OR REPLACE FUNCTION pilot_candidate_model_usage_insert_guard() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE original RECORD;
BEGIN
 NEW.recorded_at := clock_timestamp();
 SELECT action,attempt,invocation_id,snapshot_key,snapshot INTO original
 FROM pilot_candidate_review_requests
 WHERE tenant_id=NEW.tenant_id AND owner_user_id=NEW.owner_user_id
   AND request_id=NEW.request_id;
 IF NOT FOUND THEN
  RETURN NEW; -- Let the composite FK report the missing request.
 END IF;
 IF original.action<>'ASSESS' OR original.attempt<=0 OR original.invocation_id IS NOT NULL
    OR original.snapshot_key IS DISTINCT FROM NEW.snapshot_key
    OR original.snapshot ? 'research' THEN
  RAISE EXCEPTION 'invalid candidate model usage event';
 END IF;
 IF NEW.phase='FINISH' AND NOT EXISTS(
    SELECT 1 FROM pilot_candidate_model_usage_events event
    WHERE event.tenant_id=NEW.tenant_id AND event.owner_user_id=NEW.owner_user_id
      AND event.request_id=NEW.request_id AND event.phase='DISPATCH'
      AND event.snapshot_key=NEW.snapshot_key) THEN
  RAISE EXCEPTION 'invalid candidate model usage event';
 END IF;
 RETURN NEW;
END $$;

CREATE OR REPLACE FUNCTION pilot_candidate_model_usage_immutable() RETURNS trigger
LANGUAGE plpgsql AS $$ BEGIN
 RAISE EXCEPTION 'candidate model usage evidence is immutable';
END $$;

DROP TRIGGER IF EXISTS candidate_model_usage_insert_guard ON pilot_candidate_model_usage_events;
CREATE TRIGGER candidate_model_usage_insert_guard
 BEFORE INSERT ON pilot_candidate_model_usage_events FOR EACH ROW
 EXECUTE FUNCTION pilot_candidate_model_usage_insert_guard();
DROP TRIGGER IF EXISTS candidate_model_usage_immutable ON pilot_candidate_model_usage_events;
CREATE TRIGGER candidate_model_usage_immutable
 BEFORE UPDATE ON pilot_candidate_model_usage_events FOR EACH ROW
 EXECUTE FUNCTION pilot_candidate_model_usage_immutable();
