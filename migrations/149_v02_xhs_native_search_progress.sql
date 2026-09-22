-- Extend the committed native search head table for the governed XHS adapter.
-- The adapter and platform remain part of the primary key, so Bilibili heads
-- are never mixed with Xiaohongshu heads.
ALTER TABLE pilot_native_search_progress
    DROP CONSTRAINT IF EXISTS pilot_native_search_progress_platform_check,
    DROP CONSTRAINT IF EXISTS pilot_native_search_progress_adapter_version_check;

ALTER TABLE pilot_native_search_progress
    ADD CONSTRAINT pilot_native_search_progress_platform_check
        CHECK (platform IN ('BILIBILI', 'XIAOHONGSHU')),
    ADD CONSTRAINT pilot_native_search_progress_adapter_version_check
        CHECK (adapter_version IN ('bili-search-items-v1', 'xhs-search-items-v1'));
