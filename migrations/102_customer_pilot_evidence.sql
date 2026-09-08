ALTER TABLE pilot_opportunities ADD COLUMN IF NOT EXISTS match_reason TEXT NOT NULL DEFAULT '';
ALTER TABLE pilot_opportunities ADD COLUMN IF NOT EXISTS action_signal TEXT NOT NULL DEFAULT '';
ALTER TABLE pilot_opportunities ADD COLUMN IF NOT EXISTS value_judgment TEXT NOT NULL DEFAULT '';
ALTER TABLE pilot_opportunities ADD COLUMN IF NOT EXISTS risk TEXT NOT NULL DEFAULT '';
ALTER TABLE pilot_opportunities ADD COLUMN IF NOT EXISTS reviewed_by TEXT NOT NULL DEFAULT '';
ALTER TABLE pilot_opportunities ADD COLUMN IF NOT EXISTS reviewed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE pilot_opportunities ALTER COLUMN source_status SET DEFAULT 'UNVERIFIED';

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pilot_opportunities
        GROUP BY tenant_id, source_id, profile_version_id
        HAVING COUNT(*) > 1
    ) THEN
        RAISE EXCEPTION 'cannot add opportunity source/profile uniqueness: duplicate rows require manual merge';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'pilot_opportunities_tenant_source_profile_key'
    ) THEN
        ALTER TABLE pilot_opportunities
            ADD CONSTRAINT pilot_opportunities_tenant_source_profile_key
            UNIQUE (tenant_id, source_id, profile_version_id);
    END IF;
END $$;
