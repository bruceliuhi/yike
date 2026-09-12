-- Bounded original effects, atomically bound to their existing resource permits.
CREATE TABLE IF NOT EXISTS pilot_research_effect_journal (
 tenant_id TEXT NOT NULL, owner_user_id TEXT NOT NULL,
 task_id TEXT NOT NULL, run_id TEXT NOT NULL,
 sequence INTEGER NOT NULL CHECK(sequence BETWEEN 1 AND 1000),
 generation INTEGER NOT NULL CHECK(generation BETWEEN 1 AND 2147483647),
 coordinator_owner TEXT NOT NULL,
 action_id TEXT NOT NULL, permit_id TEXT NOT NULL,
 kind TEXT NOT NULL CHECK(kind IN ('MODEL','SEARCH','READ')),
 context_binding JSONB NOT NULL CHECK(jsonb_typeof(context_binding)='object' AND octet_length(context_binding::text)<=4096),
 -- Canonical application caps are 2 MiB; JSONB may add rendering whitespace.
 payload JSONB NOT NULL CHECK(jsonb_typeof(payload)='object' AND octet_length(payload::text)<=4194304),
 input_sha256 TEXT NOT NULL CHECK(input_sha256 ~ '^[a-f0-9]{64}$'),
 deadline_at TIMESTAMPTZ NOT NULL,
 status TEXT NOT NULL DEFAULT 'ISSUED' CHECK(status IN ('ISSUED','SUCCEEDED','FAILED','UNKNOWN')),
 result JSONB CHECK(jsonb_typeof(result)='object' AND octet_length(result::text)<=4194304),
 output_sha256 TEXT CHECK(output_sha256 ~ '^[a-f0-9]{64}$'),
 PRIMARY KEY(tenant_id,owner_user_id,task_id,run_id,sequence),
 UNIQUE(tenant_id,owner_user_id,action_id),
 UNIQUE(tenant_id,owner_user_id,permit_id),
 FOREIGN KEY(tenant_id,owner_user_id,task_id,run_id)
  REFERENCES pilot_customer_research_contexts(tenant_id,owner_user_id,task_id,run_id) ON DELETE CASCADE,
 FOREIGN KEY(tenant_id,owner_user_id,permit_id)
  REFERENCES pilot_research_resource_events(tenant_id,owner_user_id,permit_id) ON DELETE CASCADE,
 FOREIGN KEY(tenant_id,owner_user_id,task_id,run_id)
  REFERENCES pilot_research_runtime(tenant_id,owner_user_id,task_id,run_id),
 CHECK((status='SUCCEEDED' AND result IS NOT NULL AND output_sha256 IS NOT NULL)
    OR (status<>'SUCCEEDED' AND result IS NULL AND output_sha256 IS NULL))
);
ALTER TABLE pilot_research_effect_journal ENABLE ROW LEVEL SECURITY;
ALTER TABLE pilot_research_effect_journal FORCE ROW LEVEL SECURITY;
DO $$ BEGIN
 IF NOT EXISTS(SELECT 1 FROM pg_policies WHERE schemaname=current_schema()
  AND tablename='pilot_research_effect_journal' AND policyname='research_effect_owner') THEN
  CREATE POLICY research_effect_owner ON pilot_research_effect_journal
   USING(tenant_id=current_setting('yike.tenant_id',true) AND owner_user_id=current_setting('yike.user_id',true))
   WITH CHECK(tenant_id=current_setting('yike.tenant_id',true) AND owner_user_id=current_setting('yike.user_id',true));
 END IF;
END $$;
CREATE OR REPLACE FUNCTION pilot_research_effect_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF TG_OP='UPDATE' THEN
  IF OLD.status<>'ISSUED' OR NEW.status NOT IN ('SUCCEEDED','FAILED','UNKNOWN')
   OR (to_jsonb(OLD)-ARRAY['status','result','output_sha256'])
      IS DISTINCT FROM (to_jsonb(NEW)-ARRAY['status','result','output_sha256']) THEN
   RAISE EXCEPTION USING ERRCODE='YT042', MESSAGE='research_effect_immutable';
  END IF;
  IF NOT EXISTS(SELECT 1 FROM pilot_research_resource_events e
   WHERE e.tenant_id=NEW.tenant_id AND e.owner_user_id=NEW.owner_user_id
    AND e.permit_id=NEW.permit_id AND e.status=NEW.status
    AND e.output_sha256 IS NOT DISTINCT FROM NEW.output_sha256) THEN
   RAISE EXCEPTION USING ERRCODE='YT042', MESSAGE='research_effect_result_unbound';
  END IF;
 ELSE
  IF NEW.status<>'ISSUED' OR NOT EXISTS(
   SELECT 1 FROM pilot_customer_research_contexts c
   JOIN pilot_research_resource_events e ON e.tenant_id=c.tenant_id AND e.owner_user_id=c.owner_user_id
    AND e.task_id=c.task_id AND e.run_id=c.run_id
   JOIN pilot_research_runtime r ON r.tenant_id=c.tenant_id AND r.owner_user_id=c.owner_user_id
    AND r.task_id=c.task_id AND r.run_id=c.run_id
   WHERE c.tenant_id=NEW.tenant_id AND c.owner_user_id=NEW.owner_user_id
    AND c.task_id=NEW.task_id AND c.run_id=NEW.run_id AND c.binding=NEW.context_binding
    AND e.action_id=NEW.action_id AND e.permit_id=NEW.permit_id
    AND e.input_sha256=NEW.input_sha256 AND e.status='ISSUED'
    AND e.resource=CASE WHEN NEW.kind='MODEL' THEN 'MODEL_CALL' ELSE 'SOURCE_READ' END
    AND r.generation=NEW.generation AND r.current_owner=NEW.coordinator_owner AND r.phase='RUNNING'
    AND NEW.deadline_at<=e.deadline_at AND NEW.deadline_at<=r.lease_expires_at
    AND NEW.deadline_at>clock_timestamp()) THEN
   RAISE EXCEPTION USING ERRCODE='YT042', MESSAGE='research_effect_input_unbound';
  END IF;
 END IF;
 RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS pilot_research_effect_guard ON pilot_research_effect_journal;
CREATE TRIGGER pilot_research_effect_guard BEFORE INSERT OR UPDATE ON pilot_research_effect_journal
 FOR EACH ROW EXECUTE FUNCTION pilot_research_effect_guard();
