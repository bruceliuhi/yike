CREATE TABLE IF NOT EXISTS mvp_runs (
    mvp_run_id TEXT PRIMARY KEY,
    revision_of_run_id TEXT UNIQUE REFERENCES mvp_runs(mvp_run_id),
    state TEXT NOT NULL CHECK (state IN ('DRAFT', 'ACTIVE', 'FINALIZED', 'CANCELLED')),
    timezone TEXT NOT NULL DEFAULT 'Asia/Shanghai',
    authorization_basis TEXT NOT NULL,
    platform_scope_json TEXT NOT NULL,
    query_set_sha256 TEXT,
    prompt_version TEXT,
    schema_version TEXT,
    thresholds_sha256 TEXT,
    started_at TEXT NOT NULL,
    day14_due_at TEXT NOT NULL,
    finalized_at TEXT,
    conclusion TEXT,
    conclusion_facts_json TEXT,
    conclusion_facts_sha256 TEXT,
    final_report_sha256 TEXT,
    CHECK (revision_of_run_id IS NULL OR revision_of_run_id <> mvp_run_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS one_active_mvp_run
    ON mvp_runs(state) WHERE state = 'ACTIVE';

CREATE TABLE IF NOT EXISTS keyword_versions (
    keyword_version_id TEXT PRIMARY KEY,
    mvp_run_id TEXT NOT NULL REFERENCES mvp_runs(mvp_run_id),
    version TEXT NOT NULL,
    query_cluster TEXT NOT NULL,
    query_text TEXT NOT NULL,
    rationale TEXT,
    content_sha256 TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS campaigns (
    campaign_id TEXT PRIMARY KEY,
    mvp_run_id TEXT NOT NULL REFERENCES mvp_runs(mvp_run_id),
    platform TEXT NOT NULL CHECK (platform IN ('bili', 'dy')),
    query_cluster TEXT NOT NULL,
    query_text TEXT NOT NULL,
    max_contents INTEGER,
    max_comments_per_content INTEGER,
    state TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (campaign_id, mvp_run_id)
);

CREATE TABLE IF NOT EXISTS collection_runs (
    collection_run_id TEXT PRIMARY KEY,
    mvp_run_id TEXT NOT NULL REFERENCES mvp_runs(mvp_run_id),
    campaign_id TEXT,
    platform TEXT NOT NULL CHECK (platform IN ('bili', 'dy')),
    attempt INTEGER NOT NULL,
    backend TEXT NOT NULL,
    state TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    raw_count INTEGER NOT NULL DEFAULT 0,
    unique_count INTEGER NOT NULL DEFAULT 0,
    error_code TEXT,
    output_manifest_sha256 TEXT,
    UNIQUE (collection_run_id, mvp_run_id),
    FOREIGN KEY (campaign_id, mvp_run_id)
        REFERENCES campaigns(campaign_id, mvp_run_id)
);

CREATE TABLE IF NOT EXISTS sources (
    source_id TEXT PRIMARY KEY,
    platform TEXT NOT NULL CHECK (platform IN ('bili', 'dy')),
    external_source_id TEXT NOT NULL,
    title TEXT,
    canonical_url TEXT,
    author_public_id TEXT,
    published_at TEXT,
    UNIQUE (platform, external_source_id)
);

CREATE TABLE IF NOT EXISTS signals (
    signal_id TEXT PRIMARY KEY,
    source_id TEXT REFERENCES sources(source_id),
    platform TEXT NOT NULL CHECK (platform IN ('bili', 'dy')),
    external_comment_id TEXT,
    parent_comment_id TEXT,
    parent_body TEXT,
    normalized_comment_url TEXT NOT NULL,
    author_public_id TEXT NOT NULL,
    body TEXT NOT NULL,
    body_sha256 TEXT NOT NULL,
    published_at TEXT,
    verifiable INTEGER NOT NULL DEFAULT 1 CHECK (verifiable IN (0, 1)),
    normalizer_version TEXT,
    UNIQUE (platform, external_comment_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS fallback_signal_identity
    ON signals(platform, normalized_comment_url, author_public_id, body_sha256)
    WHERE external_comment_id IS NULL;

CREATE TABLE IF NOT EXISTS mvp_run_signals (
    mvp_run_id TEXT NOT NULL REFERENCES mvp_runs(mvp_run_id),
    signal_id TEXT NOT NULL REFERENCES signals(signal_id),
    added_at TEXT NOT NULL,
    PRIMARY KEY (mvp_run_id, signal_id)
);

CREATE TABLE IF NOT EXISTS signal_observations (
    observation_id TEXT PRIMARY KEY,
    mvp_run_id TEXT NOT NULL REFERENCES mvp_runs(mvp_run_id),
    collection_run_id TEXT,
    signal_id TEXT NOT NULL,
    query_cluster TEXT,
    query_text TEXT,
    observed_at TEXT NOT NULL,
    raw_sha256 TEXT NOT NULL,
    envelope_sha256 TEXT,
    FOREIGN KEY (mvp_run_id, signal_id)
        REFERENCES mvp_run_signals(mvp_run_id, signal_id),
    FOREIGN KEY (collection_run_id, mvp_run_id)
        REFERENCES collection_runs(collection_run_id, mvp_run_id)
);

CREATE TABLE IF NOT EXISTS score_runs (
    score_run_id TEXT PRIMARY KEY,
    mvp_run_id TEXT NOT NULL,
    signal_id TEXT NOT NULL,
    provider TEXT,
    model TEXT,
    prompt_version TEXT,
    schema_version TEXT,
    dimension_scores_json TEXT,
    total_score INTEGER,
    grade TEXT,
    confidence REAL,
    reason_json TEXT,
    status TEXT NOT NULL,
    error_code TEXT,
    token_usage_json TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    FOREIGN KEY (mvp_run_id, signal_id)
        REFERENCES mvp_run_signals(mvp_run_id, signal_id),
    UNIQUE (score_run_id, mvp_run_id, signal_id)
);

CREATE TABLE IF NOT EXISTS human_reviews (
    review_id TEXT PRIMARY KEY,
    mvp_run_id TEXT NOT NULL,
    signal_id TEXT NOT NULL,
    presented_score_run_id TEXT NOT NULL,
    label TEXT NOT NULL CHECK (label IN ('HIGH_INTENT', 'POSSIBLE', 'NOT_LEAD', 'UNVERIFIABLE')),
    reason TEXT,
    note TEXT,
    started_at TEXT,
    completed_at TEXT,
    active_seconds INTEGER,
    supersedes_review_id TEXT,
    FOREIGN KEY (mvp_run_id, signal_id)
        REFERENCES mvp_run_signals(mvp_run_id, signal_id),
    FOREIGN KEY (presented_score_run_id, mvp_run_id, signal_id)
        REFERENCES score_runs(score_run_id, mvp_run_id, signal_id),
    FOREIGN KEY (supersedes_review_id, mvp_run_id, signal_id)
        REFERENCES human_reviews(review_id, mvp_run_id, signal_id),
    CHECK (supersedes_review_id IS NULL OR supersedes_review_id <> review_id),
    UNIQUE (review_id, mvp_run_id, signal_id)
);

CREATE TABLE IF NOT EXISTS draft_runs (
    draft_run_id TEXT PRIMARY KEY,
    mvp_run_id TEXT NOT NULL,
    signal_id TEXT NOT NULL,
    provider TEXT,
    model TEXT,
    prompt_version TEXT,
    body TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (mvp_run_id, signal_id)
        REFERENCES mvp_run_signals(mvp_run_id, signal_id),
    UNIQUE (draft_run_id, mvp_run_id, signal_id)
);

CREATE TABLE IF NOT EXISTS outreach_actions (
    outreach_action_id TEXT PRIMARY KEY,
    mvp_run_id TEXT NOT NULL,
    signal_id TEXT NOT NULL,
    review_id TEXT,
    score_run_id TEXT,
    draft_run_id TEXT,
    platform TEXT NOT NULL CHECK (platform IN ('bili', 'dy')),
    subject_key TEXT NOT NULL,
    approved_text TEXT,
    sent_at TEXT,
    source_url TEXT,
    evidence_summary TEXT,
    status TEXT NOT NULL,
    parent_outreach_action_id TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (mvp_run_id, signal_id)
        REFERENCES mvp_run_signals(mvp_run_id, signal_id),
    FOREIGN KEY (review_id, mvp_run_id, signal_id)
        REFERENCES human_reviews(review_id, mvp_run_id, signal_id),
    FOREIGN KEY (score_run_id, mvp_run_id, signal_id)
        REFERENCES score_runs(score_run_id, mvp_run_id, signal_id),
    FOREIGN KEY (draft_run_id, mvp_run_id, signal_id)
        REFERENCES draft_runs(draft_run_id, mvp_run_id, signal_id),
    FOREIGN KEY (
        parent_outreach_action_id, mvp_run_id, signal_id, platform, subject_key
    ) REFERENCES outreach_actions(
        outreach_action_id, mvp_run_id, signal_id, platform, subject_key
    ),
    CHECK (
        parent_outreach_action_id IS NULL
        OR parent_outreach_action_id <> outreach_action_id
    ),
    UNIQUE (outreach_action_id, mvp_run_id),
    UNIQUE (outreach_action_id, mvp_run_id, signal_id, platform, subject_key)
);

CREATE UNIQUE INDEX IF NOT EXISTS first_outreach_per_subject
    ON outreach_actions(mvp_run_id, platform, subject_key)
    WHERE parent_outreach_action_id IS NULL;

CREATE TABLE IF NOT EXISTS response_events (
    response_event_id TEXT PRIMARY KEY,
    mvp_run_id TEXT NOT NULL,
    outreach_action_id TEXT NOT NULL,
    responder_subject_key TEXT NOT NULL,
    response_type TEXT NOT NULL,
    summary TEXT,
    occurred_at TEXT,
    verified_at TEXT,
    evidence_summary TEXT,
    FOREIGN KEY (outreach_action_id, mvp_run_id)
        REFERENCES outreach_actions(outreach_action_id, mvp_run_id),
    UNIQUE (response_event_id, mvp_run_id)
);

CREATE TABLE IF NOT EXISTS interviews (
    interview_id TEXT PRIMARY KEY,
    mvp_run_id TEXT NOT NULL,
    response_event_id TEXT NOT NULL,
    scheduled_at TEXT,
    completed_at TEXT,
    summary_json TEXT,
    next_step TEXT,
    FOREIGN KEY (response_event_id, mvp_run_id)
        REFERENCES response_events(response_event_id, mvp_run_id),
    UNIQUE (interview_id, mvp_run_id)
);

CREATE TABLE IF NOT EXISTS quote_opportunities (
    quote_opportunity_id TEXT PRIMARY KEY,
    mvp_run_id TEXT NOT NULL,
    response_event_id TEXT,
    interview_id TEXT,
    scope_summary TEXT,
    agreed_to_receive_pricing_at TEXT,
    verified_at TEXT,
    CHECK (response_event_id IS NOT NULL OR interview_id IS NOT NULL),
    FOREIGN KEY (response_event_id, mvp_run_id)
        REFERENCES response_events(response_event_id, mvp_run_id),
    FOREIGN KEY (interview_id, mvp_run_id)
        REFERENCES interviews(interview_id, mvp_run_id)
);

CREATE TABLE IF NOT EXISTS daily_snapshots (
    daily_snapshot_id TEXT PRIMARY KEY,
    mvp_run_id TEXT NOT NULL REFERENCES mvp_runs(mvp_run_id),
    local_date TEXT NOT NULL,
    fact_counts_json TEXT NOT NULL,
    human_minutes INTEGER,
    risk_summary TEXT,
    created_at TEXT NOT NULL,
    UNIQUE (mvp_run_id, local_date)
);

CREATE TABLE IF NOT EXISTS risk_events (
    risk_event_id TEXT PRIMARY KEY,
    mvp_run_id TEXT NOT NULL REFERENCES mvp_runs(mvp_run_id),
    event_type TEXT NOT NULL,
    severity TEXT NOT NULL,
    platform TEXT CHECK (platform IS NULL OR platform IN ('bili', 'dy')),
    summary TEXT NOT NULL,
    verified_at TEXT NOT NULL,
    forces_stop INTEGER NOT NULL DEFAULT 0 CHECK (forces_stop IN (0, 1))
);

CREATE TRIGGER IF NOT EXISTS mvp_runs_finalized_immutable
BEFORE UPDATE ON mvp_runs
WHEN OLD.state = 'FINALIZED'
BEGIN
    SELECT RAISE(ABORT, 'FINALIZED_RUN_IMMUTABLE');
END;

CREATE TRIGGER IF NOT EXISTS mvp_runs_finalized_not_deleted
BEFORE DELETE ON mvp_runs
WHEN OLD.state = 'FINALIZED'
BEGIN
    SELECT RAISE(ABORT, 'FINALIZED_RUN_IMMUTABLE');
END;

CREATE TRIGGER IF NOT EXISTS signals_append_only_update
BEFORE UPDATE ON signals
BEGIN
    SELECT RAISE(ABORT, 'APPEND_ONLY_FACT');
END;

CREATE TRIGGER IF NOT EXISTS signals_append_only_delete
BEFORE DELETE ON signals
BEGIN
    SELECT RAISE(ABORT, 'APPEND_ONLY_FACT');
END;

CREATE TRIGGER IF NOT EXISTS sources_append_only_update
BEFORE UPDATE ON sources
BEGIN
    SELECT RAISE(ABORT, 'APPEND_ONLY_FACT');
END;

CREATE TRIGGER IF NOT EXISTS sources_append_only_delete
BEFORE DELETE ON sources
BEGIN
    SELECT RAISE(ABORT, 'APPEND_ONLY_FACT');
END;

CREATE TRIGGER IF NOT EXISTS finalized_keyword_versions_insert
BEFORE INSERT ON keyword_versions
WHEN EXISTS (SELECT 1 FROM mvp_runs WHERE mvp_run_id = NEW.mvp_run_id AND state = 'FINALIZED')
BEGIN SELECT RAISE(ABORT, 'FINALIZED_RUN_IMMUTABLE'); END;
CREATE TRIGGER IF NOT EXISTS finalized_keyword_versions_update
BEFORE UPDATE ON keyword_versions
WHEN EXISTS (SELECT 1 FROM mvp_runs WHERE mvp_run_id = OLD.mvp_run_id AND state = 'FINALIZED')
BEGIN SELECT RAISE(ABORT, 'FINALIZED_RUN_IMMUTABLE'); END;
CREATE TRIGGER IF NOT EXISTS finalized_keyword_versions_delete
BEFORE DELETE ON keyword_versions
WHEN EXISTS (SELECT 1 FROM mvp_runs WHERE mvp_run_id = OLD.mvp_run_id AND state = 'FINALIZED')
BEGIN SELECT RAISE(ABORT, 'FINALIZED_RUN_IMMUTABLE'); END;

CREATE TRIGGER IF NOT EXISTS finalized_campaigns_insert
BEFORE INSERT ON campaigns
WHEN EXISTS (SELECT 1 FROM mvp_runs WHERE mvp_run_id = NEW.mvp_run_id AND state = 'FINALIZED')
BEGIN SELECT RAISE(ABORT, 'FINALIZED_RUN_IMMUTABLE'); END;
CREATE TRIGGER IF NOT EXISTS finalized_campaigns_update
BEFORE UPDATE ON campaigns
WHEN EXISTS (SELECT 1 FROM mvp_runs WHERE mvp_run_id = OLD.mvp_run_id AND state = 'FINALIZED')
BEGIN SELECT RAISE(ABORT, 'FINALIZED_RUN_IMMUTABLE'); END;
CREATE TRIGGER IF NOT EXISTS finalized_campaigns_delete
BEFORE DELETE ON campaigns
WHEN EXISTS (SELECT 1 FROM mvp_runs WHERE mvp_run_id = OLD.mvp_run_id AND state = 'FINALIZED')
BEGIN SELECT RAISE(ABORT, 'FINALIZED_RUN_IMMUTABLE'); END;

CREATE TRIGGER IF NOT EXISTS finalized_collection_runs_insert
BEFORE INSERT ON collection_runs
WHEN EXISTS (SELECT 1 FROM mvp_runs WHERE mvp_run_id = NEW.mvp_run_id AND state = 'FINALIZED')
BEGIN SELECT RAISE(ABORT, 'FINALIZED_RUN_IMMUTABLE'); END;
CREATE TRIGGER IF NOT EXISTS finalized_collection_runs_update
BEFORE UPDATE ON collection_runs
WHEN EXISTS (SELECT 1 FROM mvp_runs WHERE mvp_run_id = OLD.mvp_run_id AND state = 'FINALIZED')
BEGIN SELECT RAISE(ABORT, 'FINALIZED_RUN_IMMUTABLE'); END;
CREATE TRIGGER IF NOT EXISTS finalized_collection_runs_delete
BEFORE DELETE ON collection_runs
WHEN EXISTS (SELECT 1 FROM mvp_runs WHERE mvp_run_id = OLD.mvp_run_id AND state = 'FINALIZED')
BEGIN SELECT RAISE(ABORT, 'FINALIZED_RUN_IMMUTABLE'); END;

CREATE TRIGGER IF NOT EXISTS finalized_mvp_run_signals_insert
BEFORE INSERT ON mvp_run_signals
WHEN EXISTS (SELECT 1 FROM mvp_runs WHERE mvp_run_id = NEW.mvp_run_id AND state = 'FINALIZED')
BEGIN SELECT RAISE(ABORT, 'FINALIZED_RUN_IMMUTABLE'); END;
CREATE TRIGGER IF NOT EXISTS finalized_mvp_run_signals_update
BEFORE UPDATE ON mvp_run_signals
WHEN EXISTS (SELECT 1 FROM mvp_runs WHERE mvp_run_id = OLD.mvp_run_id AND state = 'FINALIZED')
BEGIN SELECT RAISE(ABORT, 'FINALIZED_RUN_IMMUTABLE'); END;
CREATE TRIGGER IF NOT EXISTS finalized_mvp_run_signals_delete
BEFORE DELETE ON mvp_run_signals
WHEN EXISTS (SELECT 1 FROM mvp_runs WHERE mvp_run_id = OLD.mvp_run_id AND state = 'FINALIZED')
BEGIN SELECT RAISE(ABORT, 'FINALIZED_RUN_IMMUTABLE'); END;

CREATE TRIGGER IF NOT EXISTS finalized_signal_observations_insert
BEFORE INSERT ON signal_observations
WHEN EXISTS (SELECT 1 FROM mvp_runs WHERE mvp_run_id = NEW.mvp_run_id AND state = 'FINALIZED')
BEGIN SELECT RAISE(ABORT, 'FINALIZED_RUN_IMMUTABLE'); END;
CREATE TRIGGER IF NOT EXISTS finalized_signal_observations_update
BEFORE UPDATE ON signal_observations
WHEN EXISTS (SELECT 1 FROM mvp_runs WHERE mvp_run_id = OLD.mvp_run_id AND state = 'FINALIZED')
BEGIN SELECT RAISE(ABORT, 'FINALIZED_RUN_IMMUTABLE'); END;
CREATE TRIGGER IF NOT EXISTS finalized_signal_observations_delete
BEFORE DELETE ON signal_observations
WHEN EXISTS (SELECT 1 FROM mvp_runs WHERE mvp_run_id = OLD.mvp_run_id AND state = 'FINALIZED')
BEGIN SELECT RAISE(ABORT, 'FINALIZED_RUN_IMMUTABLE'); END;

CREATE TRIGGER IF NOT EXISTS finalized_score_runs_insert
BEFORE INSERT ON score_runs
WHEN EXISTS (SELECT 1 FROM mvp_runs WHERE mvp_run_id = NEW.mvp_run_id AND state = 'FINALIZED')
BEGIN SELECT RAISE(ABORT, 'FINALIZED_RUN_IMMUTABLE'); END;
CREATE TRIGGER IF NOT EXISTS finalized_score_runs_update
BEFORE UPDATE ON score_runs
WHEN EXISTS (SELECT 1 FROM mvp_runs WHERE mvp_run_id = OLD.mvp_run_id AND state = 'FINALIZED')
BEGIN SELECT RAISE(ABORT, 'FINALIZED_RUN_IMMUTABLE'); END;
CREATE TRIGGER IF NOT EXISTS finalized_score_runs_delete
BEFORE DELETE ON score_runs
WHEN EXISTS (SELECT 1 FROM mvp_runs WHERE mvp_run_id = OLD.mvp_run_id AND state = 'FINALIZED')
BEGIN SELECT RAISE(ABORT, 'FINALIZED_RUN_IMMUTABLE'); END;

CREATE TRIGGER IF NOT EXISTS finalized_human_reviews_insert
BEFORE INSERT ON human_reviews
WHEN EXISTS (SELECT 1 FROM mvp_runs WHERE mvp_run_id = NEW.mvp_run_id AND state = 'FINALIZED')
BEGIN SELECT RAISE(ABORT, 'FINALIZED_RUN_IMMUTABLE'); END;
CREATE TRIGGER IF NOT EXISTS finalized_human_reviews_update
BEFORE UPDATE ON human_reviews
WHEN EXISTS (SELECT 1 FROM mvp_runs WHERE mvp_run_id = OLD.mvp_run_id AND state = 'FINALIZED')
BEGIN SELECT RAISE(ABORT, 'FINALIZED_RUN_IMMUTABLE'); END;
CREATE TRIGGER IF NOT EXISTS finalized_human_reviews_delete
BEFORE DELETE ON human_reviews
WHEN EXISTS (SELECT 1 FROM mvp_runs WHERE mvp_run_id = OLD.mvp_run_id AND state = 'FINALIZED')
BEGIN SELECT RAISE(ABORT, 'FINALIZED_RUN_IMMUTABLE'); END;

CREATE TRIGGER IF NOT EXISTS finalized_draft_runs_insert
BEFORE INSERT ON draft_runs
WHEN EXISTS (SELECT 1 FROM mvp_runs WHERE mvp_run_id = NEW.mvp_run_id AND state = 'FINALIZED')
BEGIN SELECT RAISE(ABORT, 'FINALIZED_RUN_IMMUTABLE'); END;
CREATE TRIGGER IF NOT EXISTS finalized_draft_runs_update
BEFORE UPDATE ON draft_runs
WHEN EXISTS (SELECT 1 FROM mvp_runs WHERE mvp_run_id = OLD.mvp_run_id AND state = 'FINALIZED')
BEGIN SELECT RAISE(ABORT, 'FINALIZED_RUN_IMMUTABLE'); END;
CREATE TRIGGER IF NOT EXISTS finalized_draft_runs_delete
BEFORE DELETE ON draft_runs
WHEN EXISTS (SELECT 1 FROM mvp_runs WHERE mvp_run_id = OLD.mvp_run_id AND state = 'FINALIZED')
BEGIN SELECT RAISE(ABORT, 'FINALIZED_RUN_IMMUTABLE'); END;

CREATE TRIGGER IF NOT EXISTS finalized_outreach_actions_insert
BEFORE INSERT ON outreach_actions
WHEN EXISTS (SELECT 1 FROM mvp_runs WHERE mvp_run_id = NEW.mvp_run_id AND state = 'FINALIZED')
BEGIN SELECT RAISE(ABORT, 'FINALIZED_RUN_IMMUTABLE'); END;
CREATE TRIGGER IF NOT EXISTS finalized_outreach_actions_update
BEFORE UPDATE ON outreach_actions
WHEN EXISTS (SELECT 1 FROM mvp_runs WHERE mvp_run_id = OLD.mvp_run_id AND state = 'FINALIZED')
BEGIN SELECT RAISE(ABORT, 'FINALIZED_RUN_IMMUTABLE'); END;
CREATE TRIGGER IF NOT EXISTS finalized_outreach_actions_delete
BEFORE DELETE ON outreach_actions
WHEN EXISTS (SELECT 1 FROM mvp_runs WHERE mvp_run_id = OLD.mvp_run_id AND state = 'FINALIZED')
BEGIN SELECT RAISE(ABORT, 'FINALIZED_RUN_IMMUTABLE'); END;

CREATE TRIGGER IF NOT EXISTS finalized_response_events_insert
BEFORE INSERT ON response_events
WHEN EXISTS (SELECT 1 FROM mvp_runs WHERE mvp_run_id = NEW.mvp_run_id AND state = 'FINALIZED')
BEGIN SELECT RAISE(ABORT, 'FINALIZED_RUN_IMMUTABLE'); END;
CREATE TRIGGER IF NOT EXISTS finalized_response_events_update
BEFORE UPDATE ON response_events
WHEN EXISTS (SELECT 1 FROM mvp_runs WHERE mvp_run_id = OLD.mvp_run_id AND state = 'FINALIZED')
BEGIN SELECT RAISE(ABORT, 'FINALIZED_RUN_IMMUTABLE'); END;
CREATE TRIGGER IF NOT EXISTS finalized_response_events_delete
BEFORE DELETE ON response_events
WHEN EXISTS (SELECT 1 FROM mvp_runs WHERE mvp_run_id = OLD.mvp_run_id AND state = 'FINALIZED')
BEGIN SELECT RAISE(ABORT, 'FINALIZED_RUN_IMMUTABLE'); END;

CREATE TRIGGER IF NOT EXISTS finalized_interviews_insert
BEFORE INSERT ON interviews
WHEN EXISTS (SELECT 1 FROM mvp_runs WHERE mvp_run_id = NEW.mvp_run_id AND state = 'FINALIZED')
BEGIN SELECT RAISE(ABORT, 'FINALIZED_RUN_IMMUTABLE'); END;
CREATE TRIGGER IF NOT EXISTS finalized_interviews_update
BEFORE UPDATE ON interviews
WHEN EXISTS (SELECT 1 FROM mvp_runs WHERE mvp_run_id = OLD.mvp_run_id AND state = 'FINALIZED')
BEGIN SELECT RAISE(ABORT, 'FINALIZED_RUN_IMMUTABLE'); END;
CREATE TRIGGER IF NOT EXISTS finalized_interviews_delete
BEFORE DELETE ON interviews
WHEN EXISTS (SELECT 1 FROM mvp_runs WHERE mvp_run_id = OLD.mvp_run_id AND state = 'FINALIZED')
BEGIN SELECT RAISE(ABORT, 'FINALIZED_RUN_IMMUTABLE'); END;

CREATE TRIGGER IF NOT EXISTS finalized_quote_opportunities_insert
BEFORE INSERT ON quote_opportunities
WHEN EXISTS (SELECT 1 FROM mvp_runs WHERE mvp_run_id = NEW.mvp_run_id AND state = 'FINALIZED')
BEGIN SELECT RAISE(ABORT, 'FINALIZED_RUN_IMMUTABLE'); END;
CREATE TRIGGER IF NOT EXISTS finalized_quote_opportunities_update
BEFORE UPDATE ON quote_opportunities
WHEN EXISTS (SELECT 1 FROM mvp_runs WHERE mvp_run_id = OLD.mvp_run_id AND state = 'FINALIZED')
BEGIN SELECT RAISE(ABORT, 'FINALIZED_RUN_IMMUTABLE'); END;
CREATE TRIGGER IF NOT EXISTS finalized_quote_opportunities_delete
BEFORE DELETE ON quote_opportunities
WHEN EXISTS (SELECT 1 FROM mvp_runs WHERE mvp_run_id = OLD.mvp_run_id AND state = 'FINALIZED')
BEGIN SELECT RAISE(ABORT, 'FINALIZED_RUN_IMMUTABLE'); END;

CREATE TRIGGER IF NOT EXISTS finalized_daily_snapshots_insert
BEFORE INSERT ON daily_snapshots
WHEN EXISTS (SELECT 1 FROM mvp_runs WHERE mvp_run_id = NEW.mvp_run_id AND state = 'FINALIZED')
BEGIN SELECT RAISE(ABORT, 'FINALIZED_RUN_IMMUTABLE'); END;
CREATE TRIGGER IF NOT EXISTS finalized_daily_snapshots_update
BEFORE UPDATE ON daily_snapshots
WHEN EXISTS (SELECT 1 FROM mvp_runs WHERE mvp_run_id = OLD.mvp_run_id AND state = 'FINALIZED')
BEGIN SELECT RAISE(ABORT, 'FINALIZED_RUN_IMMUTABLE'); END;
CREATE TRIGGER IF NOT EXISTS finalized_daily_snapshots_delete
BEFORE DELETE ON daily_snapshots
WHEN EXISTS (SELECT 1 FROM mvp_runs WHERE mvp_run_id = OLD.mvp_run_id AND state = 'FINALIZED')
BEGIN SELECT RAISE(ABORT, 'FINALIZED_RUN_IMMUTABLE'); END;

-- A revision is a single child of a finalized base run. A revision cannot
-- become the parent of another revision, and run identity never changes.
CREATE TRIGGER IF NOT EXISTS revision_parent_must_be_finalized
BEFORE INSERT ON mvp_runs
WHEN NEW.revision_of_run_id IS NOT NULL
     AND NOT EXISTS (
         SELECT 1 FROM mvp_runs
         WHERE mvp_run_id = NEW.revision_of_run_id AND state = 'FINALIZED'
     )
BEGIN SELECT RAISE(ABORT, 'RUN_REVISION_PARENT_NOT_FINALIZED'); END;

CREATE TRIGGER IF NOT EXISTS revision_chain_not_allowed
BEFORE INSERT ON mvp_runs
WHEN NEW.revision_of_run_id IS NOT NULL
     AND EXISTS (
         SELECT 1 FROM mvp_runs
         WHERE mvp_run_id = NEW.revision_of_run_id
           AND revision_of_run_id IS NOT NULL
     )
BEGIN SELECT RAISE(ABORT, 'RUN_REVISION_CHAIN_NOT_ALLOWED'); END;

CREATE TRIGGER IF NOT EXISTS revision_self_not_allowed
BEFORE INSERT ON mvp_runs
WHEN NEW.revision_of_run_id = NEW.mvp_run_id
BEGIN SELECT RAISE(ABORT, 'RUN_REVISION_SELF'); END;

CREATE TRIGGER IF NOT EXISTS mvp_run_identity_immutable
BEFORE UPDATE OF mvp_run_id, revision_of_run_id ON mvp_runs
WHEN NEW.mvp_run_id <> OLD.mvp_run_id
     OR NEW.revision_of_run_id IS NOT OLD.revision_of_run_id
BEGIN SELECT RAISE(ABORT, 'RUN_IDENTITY_IMMUTABLE'); END;

-- Collection lifecycle records may advance state, but never move between
-- runs or disappear. Both sides are checked so an UPDATE cannot move a row
-- into a finalized run.
CREATE TRIGGER IF NOT EXISTS campaigns_update_guard
BEFORE UPDATE ON campaigns
BEGIN
    SELECT CASE
        WHEN NEW.mvp_run_id <> OLD.mvp_run_id
            THEN RAISE(ABORT, 'RUN_SCOPE_IMMUTABLE')
        WHEN EXISTS (
            SELECT 1 FROM mvp_runs
            WHERE mvp_run_id IN (OLD.mvp_run_id, NEW.mvp_run_id)
              AND state = 'FINALIZED'
        ) THEN RAISE(ABORT, 'FINALIZED_RUN_IMMUTABLE')
    END;
END;

CREATE TRIGGER IF NOT EXISTS campaigns_append_only_delete
BEFORE DELETE ON campaigns
BEGIN SELECT RAISE(ABORT, 'APPEND_ONLY_FACT'); END;

CREATE TRIGGER IF NOT EXISTS collection_runs_update_guard
BEFORE UPDATE ON collection_runs
BEGIN
    SELECT CASE
        WHEN NEW.mvp_run_id <> OLD.mvp_run_id
            THEN RAISE(ABORT, 'RUN_SCOPE_IMMUTABLE')
        WHEN EXISTS (
            SELECT 1 FROM mvp_runs
            WHERE mvp_run_id IN (OLD.mvp_run_id, NEW.mvp_run_id)
              AND state = 'FINALIZED'
        ) THEN RAISE(ABORT, 'FINALIZED_RUN_IMMUTABLE')
    END;
END;

CREATE TRIGGER IF NOT EXISTS collection_runs_append_only_delete
BEFORE DELETE ON collection_runs
BEGIN SELECT RAISE(ABORT, 'APPEND_ONLY_FACT'); END;

-- All remaining facts are immutable from insertion, including while their
-- run is ACTIVE. Corrections are represented by new superseding rows.
CREATE TRIGGER IF NOT EXISTS keyword_versions_append_only_update
BEFORE UPDATE ON keyword_versions
BEGIN SELECT RAISE(ABORT, 'APPEND_ONLY_FACT'); END;
CREATE TRIGGER IF NOT EXISTS keyword_versions_append_only_delete
BEFORE DELETE ON keyword_versions
BEGIN SELECT RAISE(ABORT, 'APPEND_ONLY_FACT'); END;

CREATE TRIGGER IF NOT EXISTS mvp_run_signals_append_only_update
BEFORE UPDATE ON mvp_run_signals
BEGIN SELECT RAISE(ABORT, 'APPEND_ONLY_FACT'); END;
CREATE TRIGGER IF NOT EXISTS mvp_run_signals_append_only_delete
BEFORE DELETE ON mvp_run_signals
BEGIN SELECT RAISE(ABORT, 'APPEND_ONLY_FACT'); END;

CREATE TRIGGER IF NOT EXISTS signal_observations_append_only_update
BEFORE UPDATE ON signal_observations
WHEN NOT EXISTS (
    SELECT 1 FROM mvp_runs
    WHERE mvp_run_id = OLD.mvp_run_id AND state = 'FINALIZED'
)
BEGIN SELECT RAISE(ABORT, 'APPEND_ONLY_FACT'); END;
CREATE TRIGGER IF NOT EXISTS signal_observations_append_only_delete
BEFORE DELETE ON signal_observations
WHEN NOT EXISTS (
    SELECT 1 FROM mvp_runs
    WHERE mvp_run_id = OLD.mvp_run_id AND state = 'FINALIZED'
)
BEGIN SELECT RAISE(ABORT, 'APPEND_ONLY_FACT'); END;

CREATE TRIGGER IF NOT EXISTS score_runs_append_only_update
BEFORE UPDATE ON score_runs
BEGIN SELECT RAISE(ABORT, 'APPEND_ONLY_FACT'); END;
CREATE TRIGGER IF NOT EXISTS score_runs_append_only_delete
BEFORE DELETE ON score_runs
BEGIN SELECT RAISE(ABORT, 'APPEND_ONLY_FACT'); END;

CREATE TRIGGER IF NOT EXISTS human_reviews_append_only_update
BEFORE UPDATE ON human_reviews
BEGIN SELECT RAISE(ABORT, 'APPEND_ONLY_FACT'); END;
CREATE TRIGGER IF NOT EXISTS human_reviews_append_only_delete
BEFORE DELETE ON human_reviews
BEGIN SELECT RAISE(ABORT, 'APPEND_ONLY_FACT'); END;

CREATE TRIGGER IF NOT EXISTS successful_presented_score_required
BEFORE INSERT ON human_reviews
WHEN NOT EXISTS (
    SELECT 1 FROM score_runs
    WHERE score_run_id = NEW.presented_score_run_id
      AND mvp_run_id = NEW.mvp_run_id
      AND signal_id = NEW.signal_id
      AND status = 'SUCCEEDED'
)
BEGIN SELECT RAISE(ABORT, 'PRESENTED_SCORE_NOT_SUCCEEDED'); END;

CREATE TRIGGER IF NOT EXISTS draft_runs_append_only_update
BEFORE UPDATE ON draft_runs
BEGIN SELECT RAISE(ABORT, 'APPEND_ONLY_FACT'); END;
CREATE TRIGGER IF NOT EXISTS draft_runs_append_only_delete
BEFORE DELETE ON draft_runs
BEGIN SELECT RAISE(ABORT, 'APPEND_ONLY_FACT'); END;

CREATE TRIGGER IF NOT EXISTS outreach_actions_append_only_update
BEFORE UPDATE ON outreach_actions
BEGIN SELECT RAISE(ABORT, 'APPEND_ONLY_FACT'); END;
CREATE TRIGGER IF NOT EXISTS outreach_actions_append_only_delete
BEFORE DELETE ON outreach_actions
BEGIN SELECT RAISE(ABORT, 'APPEND_ONLY_FACT'); END;

CREATE TRIGGER IF NOT EXISTS response_events_append_only_update
BEFORE UPDATE ON response_events
BEGIN SELECT RAISE(ABORT, 'APPEND_ONLY_FACT'); END;
CREATE TRIGGER IF NOT EXISTS response_events_append_only_delete
BEFORE DELETE ON response_events
BEGIN SELECT RAISE(ABORT, 'APPEND_ONLY_FACT'); END;

CREATE TRIGGER IF NOT EXISTS interviews_append_only_update
BEFORE UPDATE ON interviews
BEGIN SELECT RAISE(ABORT, 'APPEND_ONLY_FACT'); END;
CREATE TRIGGER IF NOT EXISTS interviews_append_only_delete
BEFORE DELETE ON interviews
BEGIN SELECT RAISE(ABORT, 'APPEND_ONLY_FACT'); END;

CREATE TRIGGER IF NOT EXISTS quote_opportunities_append_only_update
BEFORE UPDATE ON quote_opportunities
BEGIN SELECT RAISE(ABORT, 'APPEND_ONLY_FACT'); END;
CREATE TRIGGER IF NOT EXISTS quote_opportunities_append_only_delete
BEFORE DELETE ON quote_opportunities
BEGIN SELECT RAISE(ABORT, 'APPEND_ONLY_FACT'); END;

CREATE TRIGGER IF NOT EXISTS daily_snapshots_append_only_update
BEFORE UPDATE ON daily_snapshots
BEGIN SELECT RAISE(ABORT, 'APPEND_ONLY_FACT'); END;
CREATE TRIGGER IF NOT EXISTS daily_snapshots_append_only_delete
BEFORE DELETE ON daily_snapshots
BEGIN SELECT RAISE(ABORT, 'APPEND_ONLY_FACT'); END;

CREATE TRIGGER IF NOT EXISTS finalized_risk_events_insert
BEFORE INSERT ON risk_events
WHEN EXISTS (
    SELECT 1 FROM mvp_runs
    WHERE mvp_run_id = NEW.mvp_run_id AND state = 'FINALIZED'
)
BEGIN SELECT RAISE(ABORT, 'FINALIZED_RUN_IMMUTABLE'); END;

CREATE TRIGGER IF NOT EXISTS risk_events_append_only_update
BEFORE UPDATE ON risk_events
BEGIN SELECT RAISE(ABORT, 'APPEND_ONLY_FACT'); END;
CREATE TRIGGER IF NOT EXISTS risk_events_append_only_delete
BEFORE DELETE ON risk_events
BEGIN SELECT RAISE(ABORT, 'APPEND_ONLY_FACT'); END;
