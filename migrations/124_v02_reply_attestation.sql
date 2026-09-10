-- Preserve all historical event bytes/digests and existing immutable-row guard.
ALTER TABLE pilot_reply_events ADD COLUMN IF NOT EXISTS device_attestation JSONB;
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid='pilot_reply_events'::regclass AND conname='reply_attestation_binding') THEN
        ALTER TABLE pilot_reply_events ADD CONSTRAINT reply_attestation_binding CHECK (
            device_attestation IS NULL OR ((jsonb_typeof(device_attestation)='object'
                AND kind='PLATFORM_REPLY'
                AND device_attestation->>'schemaVersion'='device-reply-attestation-v1'
                AND device_attestation->>'authority'='DEVICE_ATTESTED_PLATFORM_REPLY'
                AND device_attestation->>'replyEventSha256'=payload_sha256
                AND length(device_attestation->>'deviceId')=36
                AND length(device_attestation->>'claimId')=36
                AND device_attestation->>'contextSha256' ~ '^[a-f0-9]{64}$'
                AND device_attestation->>'requestSha256' ~ '^[a-f0-9]{64}$') IS TRUE));
    END IF;
END $$;
