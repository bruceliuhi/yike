-- The reader can prove TCP connect failure before sending an HTTP request.
-- Keep 143 immutable; extend both exact-result gates together for existing DBs.
ALTER TABLE pilot_research_effect_journal DROP CONSTRAINT research_effect_final_result;
ALTER TABLE pilot_research_effect_journal ADD CONSTRAINT research_effect_final_result CHECK (
 (status='SUCCEEDED' AND result IS NOT NULL AND output_sha256 IS NOT NULL)
 OR (status<>'SUCCEEDED' AND result IS NULL AND output_sha256 IS NULL)
 OR (status='FAILED' AND kind='READ' AND output_sha256 IS NOT NULL AND result IS NOT NULL
     AND result IN (
      '{"status":"FAILED","code":"not_found","replayed":false}'::jsonb,
      '{"status":"FAILED","code":"unsupported_media_type","replayed":false}'::jsonb,
      '{"status":"FAILED","code":"too_large","replayed":false}'::jsonb,
      '{"status":"FAILED","code":"connection_unavailable","replayed":false}'::jsonb))
);

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
    '{"status":"FAILED","code":"too_large","replayed":false}'::jsonb,
    '{"status":"FAILED","code":"connection_unavailable","replayed":false}'::jsonb)
 ) THEN
  RAISE EXCEPTION USING ERRCODE='YT043', MESSAGE='known_read_failure_unbound';
 END IF;
 RETURN NEW;
END $$;
