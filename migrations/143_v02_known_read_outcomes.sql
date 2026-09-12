-- Preserve FAILED accounting; only the three exact known READ outcomes carry results.
ALTER TABLE pilot_research_effect_journal DROP CONSTRAINT IF EXISTS pilot_research_effect_journal_check;
ALTER TABLE pilot_research_effect_journal DROP CONSTRAINT IF EXISTS research_effect_final_result;
ALTER TABLE pilot_research_effect_journal ADD CONSTRAINT research_effect_final_result CHECK (
 (status='SUCCEEDED' AND result IS NOT NULL AND output_sha256 IS NOT NULL)
 OR (status<>'SUCCEEDED' AND result IS NULL AND output_sha256 IS NULL)
 OR (status='FAILED' AND kind='READ' AND output_sha256 IS NOT NULL AND result IS NOT NULL
     AND result IN (
      '{"status":"FAILED","code":"not_found","replayed":false}'::jsonb,
      '{"status":"FAILED","code":"unsupported_media_type","replayed":false}'::jsonb,
      '{"status":"FAILED","code":"too_large","replayed":false}'::jsonb))
);

ALTER TABLE pilot_research_resource_events DROP CONSTRAINT IF EXISTS pilot_research_resource_events_check1;
ALTER TABLE pilot_research_resource_events DROP CONSTRAINT IF EXISTS research_resource_final_result;
ALTER TABLE pilot_research_resource_events ADD CONSTRAINT research_resource_final_result CHECK (
 (status='ISSUED' AND output_sha256 IS NULL AND finished_at IS NULL)
 OR (status='SUCCEEDED' AND output_sha256 IS NOT NULL AND finished_at IS NOT NULL)
 OR (status IN ('FAILED','UNKNOWN') AND output_sha256 IS NULL AND finished_at IS NOT NULL)
 OR (status='FAILED' AND resource='SOURCE_READ' AND output_sha256 IS NOT NULL AND finished_at IS NOT NULL)
);

-- Journal.finish updates the resource first: validate the pair at transaction end.
-- Invoker security retains existing tenant/owner RLS and immutable transition guards.
CREATE OR REPLACE FUNCTION pilot_known_read_failure_pair() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NEW.status='FAILED' AND NEW.output_sha256 IS NOT NULL AND NOT EXISTS (
  SELECT 1 FROM pilot_research_effect_journal j
  WHERE j.tenant_id=NEW.tenant_id AND j.owner_user_id=NEW.owner_user_id
   AND j.task_id=NEW.task_id AND j.run_id=NEW.run_id AND j.action_id=NEW.action_id
   AND j.permit_id=NEW.permit_id AND j.input_sha256=NEW.input_sha256
   AND j.status=NEW.status AND j.output_sha256=NEW.output_sha256 AND j.kind='READ'
   AND j.result IN (
    '{"status":"FAILED","code":"not_found","replayed":false}'::jsonb,
    '{"status":"FAILED","code":"unsupported_media_type","replayed":false}'::jsonb,
    '{"status":"FAILED","code":"too_large","replayed":false}'::jsonb)
 ) THEN
  RAISE EXCEPTION USING ERRCODE='YT043', MESSAGE='known_read_failure_unbound';
 END IF;
 RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS pilot_known_read_failure_pair ON pilot_research_resource_events;
CREATE CONSTRAINT TRIGGER pilot_known_read_failure_pair
 AFTER INSERT OR UPDATE ON pilot_research_resource_events
 DEFERRABLE INITIALLY DEFERRED FOR EACH ROW
 WHEN (NEW.status='FAILED' AND NEW.output_sha256 IS NOT NULL)
 EXECUTE FUNCTION pilot_known_read_failure_pair();
