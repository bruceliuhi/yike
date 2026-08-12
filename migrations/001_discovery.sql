CREATE TABLE IF NOT EXISTS schema_meta (
    schema_key TEXT PRIMARY KEY CHECK (schema_key = 'discovery'),
    version TEXT NOT NULL,
    signature TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS mvp_runs (
    mvp_run_id TEXT PRIMARY KEY,
    revision_of_run_id TEXT UNIQUE REFERENCES mvp_runs(mvp_run_id),
    state TEXT NOT NULL CHECK (state IN ('DRAFT', 'ACTIVE', 'FINALIZED', 'CANCELLED')),
    timezone TEXT NOT NULL DEFAULT 'Asia/Shanghai',
    authorization_basis TEXT NOT NULL,
    platform_scope_json TEXT NOT NULL,
    query_set_sha256 TEXT NOT NULL CHECK (length(query_set_sha256) = 64),
    prompt_version TEXT NOT NULL CHECK (length(trim(prompt_version)) > 0),
    schema_version TEXT NOT NULL CHECK (length(trim(schema_version)) > 0),
    thresholds_sha256 TEXT NOT NULL CHECK (length(thresholds_sha256) = 64),
    started_at TEXT NOT NULL,
    day14_due_at TEXT NOT NULL,
    finalized_at TEXT,
    conclusion TEXT,
    conclusion_facts_json TEXT,
    conclusion_facts_sha256 TEXT,
    final_report_sha256 TEXT,
    CHECK (revision_of_run_id IS NULL OR revision_of_run_id <> mvp_run_id),
    CHECK (platform_scope_json = '["bili","dy"]'),
    CHECK (
        (
            state = 'FINALIZED'
            AND finalized_at IS NOT NULL
            AND conclusion IS NOT NULL
            AND conclusion_facts_json IS NOT NULL
            AND conclusion_facts_sha256 IS NOT NULL
            AND final_report_sha256 IS NOT NULL
        )
        OR
        (
            state <> 'FINALIZED'
            AND finalized_at IS NULL
            AND conclusion IS NULL
            AND conclusion_facts_json IS NULL
            AND conclusion_facts_sha256 IS NULL
            AND final_report_sha256 IS NULL
        )
    )
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
    UNIQUE (campaign_id, mvp_run_id),
    UNIQUE (campaign_id, mvp_run_id, platform)
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
    FOREIGN KEY (campaign_id, mvp_run_id, platform)
        REFERENCES campaigns(campaign_id, mvp_run_id, platform)
);

CREATE UNIQUE INDEX IF NOT EXISTS one_running_collection
    ON collection_runs(state) WHERE state = 'RUNNING';

CREATE TABLE IF NOT EXISTS sources (
    source_id TEXT PRIMARY KEY,
    platform TEXT NOT NULL CHECK (platform IN ('bili', 'dy')),
    external_source_id TEXT NOT NULL,
    title TEXT,
    canonical_url TEXT,
    author_public_id TEXT,
    published_at TEXT,
    UNIQUE (platform, external_source_id),
    UNIQUE (source_id, platform)
);

CREATE TABLE IF NOT EXISTS signals (
    signal_id TEXT PRIMARY KEY,
    source_id TEXT,
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
    UNIQUE (platform, external_comment_id),
    FOREIGN KEY (source_id, platform) REFERENCES sources(source_id, platform)
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
    status TEXT NOT NULL CHECK (status IN ('SUCCEEDED', 'FAILED')),
    error_code TEXT,
    token_usage_json TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    FOREIGN KEY (mvp_run_id, signal_id)
        REFERENCES mvp_run_signals(mvp_run_id, signal_id),
    CHECK (strftime('%Y-%m-%dT%H:%M:%SZ', created_at) IS created_at),
    CHECK (prompt_version IS NOT NULL AND length(trim(prompt_version)) > 0),
    CHECK (schema_version IS NOT NULL AND length(trim(schema_version)) > 0),
    CHECK (
        (
            status = 'SUCCEEDED'
            AND provider IS NOT NULL AND length(trim(provider)) > 0
            AND model IS NOT NULL AND length(trim(model)) > 0
            AND dimension_scores_json IS NOT NULL
            AND json_valid(dimension_scores_json)
            AND total_score IS NOT NULL AND total_score BETWEEN 0 AND 12
            AND typeof(total_score) = 'integer'
            AND grade IS NOT NULL AND grade IN ('A', 'B', 'C', 'D')
            AND confidence IS NOT NULL AND confidence BETWEEN 0.0 AND 1.0
            AND reason_json IS NOT NULL AND json_valid(reason_json)
            AND error_code IS NULL
            AND (token_usage_json IS NULL OR json_valid(token_usage_json))
        )
        OR (
            status = 'FAILED'
            AND dimension_scores_json IS NULL
            AND total_score IS NULL
            AND grade IS NULL
            AND confidence IS NULL
            AND reason_json IS NULL
            AND token_usage_json IS NULL
            AND error_code IS NOT NULL
            AND error_code IN (
                'MODEL_NOT_CONFIGURED',
                'MODEL_UNAVAILABLE',
                'MODEL_OUTPUT_INVALID'
            )
        )
    ),
    UNIQUE (score_run_id, mvp_run_id, signal_id)
);

CREATE TABLE IF NOT EXISTS score_presentations (
    presentation_id TEXT PRIMARY KEY,
    mvp_run_id TEXT NOT NULL,
    signal_id TEXT NOT NULL,
    score_run_id TEXT NOT NULL,
    presented_at TEXT NOT NULL,
    FOREIGN KEY (mvp_run_id, signal_id)
        REFERENCES mvp_run_signals(mvp_run_id, signal_id),
    FOREIGN KEY (score_run_id, mvp_run_id, signal_id)
        REFERENCES score_runs(score_run_id, mvp_run_id, signal_id),
    UNIQUE (mvp_run_id, signal_id),
    UNIQUE (mvp_run_id, signal_id, score_run_id)
);

CREATE TABLE IF NOT EXISTS activity_sessions (
    activity_session_id TEXT PRIMARY KEY,
    mvp_run_id TEXT NOT NULL,
    signal_id TEXT NOT NULL,
    activity_kind TEXT NOT NULL CHECK (activity_kind IN ('REVIEW', 'DRAFT')),
    state TEXT NOT NULL CHECK (state IN ('OPEN', 'PAUSED', 'COMPLETED', 'CANCELLED')),
    started_at TEXT NOT NULL,
    completed_at TEXT,
    active_seconds INTEGER,
    FOREIGN KEY (mvp_run_id, signal_id)
        REFERENCES mvp_run_signals(mvp_run_id, signal_id),
    CHECK (strftime('%Y-%m-%dT%H:%M:%SZ', started_at) IS started_at),
    CHECK (
        (state IN ('OPEN', 'PAUSED') AND completed_at IS NULL AND active_seconds IS NULL)
        OR
        (state IN ('COMPLETED', 'CANCELLED')
         AND completed_at IS NOT NULL
         AND typeof(active_seconds) = 'integer'
         AND active_seconds >= 0)
    ),
    UNIQUE (activity_session_id, mvp_run_id, signal_id),
    UNIQUE (activity_session_id, mvp_run_id, signal_id, activity_kind)
);

CREATE UNIQUE INDEX IF NOT EXISTS one_open_activity_per_subject
    ON activity_sessions(mvp_run_id, signal_id, activity_kind)
    WHERE state IN ('OPEN', 'PAUSED');

CREATE TRIGGER IF NOT EXISTS activity_sessions_must_start_open
BEFORE INSERT ON activity_sessions
WHEN NEW.state <> 'OPEN'
     OR NEW.completed_at IS NOT NULL
     OR NEW.active_seconds IS NOT NULL
BEGIN SELECT RAISE(ABORT, 'ACTIVITY_MUST_START_OPEN'); END;

CREATE TABLE IF NOT EXISTS activity_events (
    activity_event_id TEXT PRIMARY KEY,
    activity_session_id TEXT NOT NULL,
    mvp_run_id TEXT NOT NULL,
    signal_id TEXT NOT NULL,
    activity_kind TEXT NOT NULL CHECK (activity_kind IN ('REVIEW', 'DRAFT')),
    sequence_no INTEGER NOT NULL CHECK (typeof(sequence_no) = 'integer' AND sequence_no > 0),
    event_kind TEXT NOT NULL CHECK (
        event_kind IN (
            'START', 'PAUSE_HIDDEN', 'PAUSE_IDLE', 'RESUME', 'COMPLETE', 'CANCEL'
        )
    ),
    received_at TEXT NOT NULL CHECK (
        strftime('%Y-%m-%dT%H:%M:%SZ', received_at) IS received_at
    ),
    FOREIGN KEY (activity_session_id, mvp_run_id, signal_id, activity_kind)
        REFERENCES activity_sessions(
            activity_session_id, mvp_run_id, signal_id, activity_kind
        ),
    UNIQUE (activity_session_id, sequence_no)
);

CREATE TRIGGER IF NOT EXISTS activity_event_sequence_guard
BEFORE INSERT ON activity_events
WHEN strftime('%Y-%m-%dT%H:%M:%SZ', NEW.received_at) IS NOT NEW.received_at
  OR (
      NEW.event_kind = 'START'
      AND (
          NEW.sequence_no <> 1
          OR EXISTS (
              SELECT 1 FROM activity_events event
              WHERE event.activity_session_id = NEW.activity_session_id
          )
          OR NOT EXISTS (
              SELECT 1 FROM activity_sessions session
              WHERE session.activity_session_id = NEW.activity_session_id
                AND session.state = 'OPEN'
                AND session.started_at = NEW.received_at
          )
      )
  )
  OR (
      NEW.event_kind <> 'START'
      AND (
          NEW.sequence_no <> coalesce((
              SELECT max(event.sequence_no) + 1
              FROM activity_events event
              WHERE event.activity_session_id = NEW.activity_session_id
          ), 0)
          OR julianday(NEW.received_at) < julianday((
              SELECT event.received_at
              FROM activity_events event
              WHERE event.activity_session_id = NEW.activity_session_id
              ORDER BY event.sequence_no DESC LIMIT 1
          ))
          OR NOT EXISTS (
              SELECT 1
              FROM activity_events prior
              JOIN activity_sessions session
                ON session.activity_session_id = prior.activity_session_id
              WHERE prior.activity_session_id = NEW.activity_session_id
                AND prior.sequence_no = NEW.sequence_no - 1
                AND (
                    (session.state = 'OPEN'
                     AND prior.event_kind IN ('START', 'RESUME')
                     AND NEW.event_kind IN (
                         'PAUSE_HIDDEN', 'PAUSE_IDLE', 'COMPLETE', 'CANCEL'
                     ))
                    OR
                    (session.state = 'PAUSED'
                     AND prior.event_kind IN ('PAUSE_HIDDEN', 'PAUSE_IDLE')
                     AND NEW.event_kind IN ('RESUME', 'CANCEL'))
                )
          )
      )
  )
  OR (
      NEW.event_kind = 'START'
      AND NOT EXISTS (
          SELECT 1 FROM activity_sessions session
          WHERE session.activity_session_id = NEW.activity_session_id
            AND session.state = 'OPEN'
      )
  )
BEGIN SELECT RAISE(ABORT, 'ACTIVITY_EVENT_INVALID_TRANSITION'); END;

CREATE TABLE IF NOT EXISTS human_reviews (
    review_id TEXT PRIMARY KEY,
    mvp_run_id TEXT NOT NULL,
    signal_id TEXT NOT NULL,
    presented_score_run_id TEXT NOT NULL,
    label TEXT NOT NULL CHECK (label IN ('HIGH_INTENT', 'POSSIBLE', 'NOT_LEAD', 'UNVERIFIABLE')),
    reason TEXT,
    note TEXT,
    activity_session_id TEXT NOT NULL UNIQUE,
    started_at TEXT NOT NULL,
    completed_at TEXT NOT NULL,
    active_seconds INTEGER NOT NULL CHECK (
        typeof(active_seconds) = 'integer' AND active_seconds >= 0
    ),
    supersedes_review_id TEXT UNIQUE,
    FOREIGN KEY (mvp_run_id, signal_id)
        REFERENCES mvp_run_signals(mvp_run_id, signal_id),
    FOREIGN KEY (presented_score_run_id, mvp_run_id, signal_id)
        REFERENCES score_runs(score_run_id, mvp_run_id, signal_id),
    FOREIGN KEY (mvp_run_id, signal_id, presented_score_run_id)
        REFERENCES score_presentations(mvp_run_id, signal_id, score_run_id),
    FOREIGN KEY (supersedes_review_id, mvp_run_id, signal_id)
        REFERENCES human_reviews(review_id, mvp_run_id, signal_id),
    FOREIGN KEY (activity_session_id, mvp_run_id, signal_id)
        REFERENCES activity_sessions(activity_session_id, mvp_run_id, signal_id),
    CHECK (supersedes_review_id IS NULL OR supersedes_review_id <> review_id),
    UNIQUE (review_id, mvp_run_id, signal_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS one_root_review_per_signal
    ON human_reviews(mvp_run_id, signal_id)
    WHERE supersedes_review_id IS NULL;

CREATE TABLE IF NOT EXISTS draft_runs (
    draft_run_id TEXT PRIMARY KEY,
    mvp_run_id TEXT NOT NULL,
    signal_id TEXT NOT NULL,
    provider TEXT,
    model TEXT,
    prompt_version TEXT NOT NULL,
    draft_kind TEXT NOT NULL CHECK (draft_kind IN ('GENERATED', 'HUMAN_EDITED')),
    body TEXT,
    status TEXT NOT NULL CHECK (status IN ('SUCCEEDED', 'FAILED')),
    activity_session_id TEXT UNIQUE,
    contract_json TEXT,
    token_usage_json TEXT,
    error_code TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (mvp_run_id, signal_id)
        REFERENCES mvp_run_signals(mvp_run_id, signal_id),
    FOREIGN KEY (activity_session_id, mvp_run_id, signal_id)
        REFERENCES activity_sessions(activity_session_id, mvp_run_id, signal_id),
    CHECK (strftime('%Y-%m-%dT%H:%M:%SZ', created_at) IS created_at),
    CHECK (
        (
            draft_kind = 'GENERATED'
            AND activity_session_id IS NULL
            AND (
                (
                    status = 'SUCCEEDED'
                    AND provider IS NOT NULL AND length(trim(provider)) > 0
                    AND model IS NOT NULL AND length(trim(model)) > 0
                    AND body IS NOT NULL AND length(trim(body)) > 0 AND length(body) <= 180
                    AND contract_json IS NOT NULL AND json_valid(contract_json)
                    AND error_code IS NULL
                    AND (token_usage_json IS NULL OR json_valid(token_usage_json))
                )
                OR
                (
                    status = 'FAILED'
                    AND body IS NULL
                    AND contract_json IS NULL
                    AND token_usage_json IS NULL
                    AND error_code IN (
                        'MODEL_NOT_CONFIGURED', 'MODEL_UNAVAILABLE', 'MODEL_OUTPUT_INVALID'
                    )
                )
            )
        )
        OR
        (
            draft_kind = 'HUMAN_EDITED'
            AND status = 'SUCCEEDED'
            AND provider = 'human'
            AND model IS NULL
            AND activity_session_id IS NOT NULL
            AND body IS NOT NULL AND length(trim(body)) > 0 AND length(body) <= 180
            AND contract_json IS NULL
            AND token_usage_json IS NULL
            AND error_code IS NULL
        )
    ),
    UNIQUE (draft_run_id, mvp_run_id, signal_id)
);

CREATE TABLE IF NOT EXISTS outreach_actions (
    outreach_action_id TEXT PRIMARY KEY,
    mvp_run_id TEXT NOT NULL,
    signal_id TEXT NOT NULL,
    review_id TEXT NOT NULL,
    score_run_id TEXT NOT NULL,
    draft_run_id TEXT NOT NULL,
    platform TEXT NOT NULL CHECK (platform IN ('bili', 'dy')),
    subject_key TEXT NOT NULL,
    approved_text TEXT,
    sent_at TEXT,
    source_url TEXT,
    context_evidence TEXT,
    evidence_summary TEXT,
    source_link_opened INTEGER NOT NULL DEFAULT 0
        CHECK (source_link_opened IN (0, 1)),
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
    CHECK (
        sent_at IS NULL OR strftime('%Y-%m-%dT%H:%M:%SZ', sent_at) IS sent_at
    ),
    CHECK (strftime('%Y-%m-%dT%H:%M:%SZ', created_at) IS created_at),
    CHECK (
        status <> 'SENT_VERIFIED'
        OR (
            source_link_opened = 1
            AND approved_text IS NOT NULL
            AND length(trim(approved_text, char(9) || char(10) || char(13) || ' ')) > 0
            AND sent_at IS NOT NULL
            AND length(trim(sent_at, char(9) || char(10) || char(13) || ' ')) > 0
            AND source_url IS NOT NULL
            AND length(trim(source_url, char(9) || char(10) || char(13) || ' ')) > 0
            AND context_evidence IS NOT NULL
            AND length(trim(context_evidence, char(9) || char(10) || char(13) || ' ')) > 0
            AND evidence_summary = context_evidence
        )
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
    response_type TEXT NOT NULL CHECK (response_type IN ('VALID', 'INVALID')),
    summary TEXT,
    occurred_at TEXT,
    verified_at TEXT,
    evidence_summary TEXT,
    recorded_at TEXT NOT NULL CHECK (
        strftime('%Y-%m-%dT%H:%M:%SZ', recorded_at) IS recorded_at
    ),
    FOREIGN KEY (outreach_action_id, mvp_run_id)
        REFERENCES outreach_actions(outreach_action_id, mvp_run_id),
    CHECK (
        occurred_at IS NULL
        OR strftime('%Y-%m-%dT%H:%M:%SZ', occurred_at) IS occurred_at
    ),
    CHECK (
        verified_at IS NULL
        OR strftime('%Y-%m-%dT%H:%M:%SZ', verified_at) IS verified_at
    ),
    CHECK (
        response_type <> 'VALID'
        OR (
            occurred_at IS NOT NULL AND length(trim(occurred_at)) > 0
            AND
            verified_at IS NOT NULL AND length(trim(verified_at)) > 0
            AND evidence_summary IS NOT NULL AND length(trim(evidence_summary)) > 0
            AND occurred_at <= verified_at
        )
    ),
    UNIQUE (response_event_id, mvp_run_id)
);

CREATE TABLE IF NOT EXISTS interviews (
    interview_id TEXT PRIMARY KEY,
    mvp_run_id TEXT NOT NULL,
    response_event_id TEXT NOT NULL,
    scheduled_at TEXT,
    completed_at TEXT,
    summary_json TEXT,
    solution_fit TEXT NOT NULL CHECK (
        solution_fit IN ('SOLVABLE', 'UNSOLVABLE', 'UNKNOWN')
    ),
    next_step TEXT,
    recorded_at TEXT NOT NULL CHECK (
        strftime('%Y-%m-%dT%H:%M:%SZ', recorded_at) IS recorded_at
    ),
    FOREIGN KEY (response_event_id, mvp_run_id)
        REFERENCES response_events(response_event_id, mvp_run_id),
    CHECK (
        scheduled_at IS NULL
        OR strftime('%Y-%m-%dT%H:%M:%SZ', scheduled_at) IS scheduled_at
    ),
    CHECK (
        completed_at IS NULL
        OR strftime('%Y-%m-%dT%H:%M:%SZ', completed_at) IS completed_at
    ),
    CHECK (
        completed_at IS NULL
        OR (
            summary_json IS NOT NULL
            AND json_valid(summary_json)
            AND json_type(summary_json) = 'object'
            AND json_type(summary_json, '$.customer_source_and_sales_process') = 'text'
            AND length(trim(json_extract(summary_json, '$.customer_source_and_sales_process'))) > 0
            AND json_type(summary_json, '$.weekly_lead_volume_and_loss_point') = 'text'
            AND length(trim(json_extract(summary_json, '$.weekly_lead_volume_and_loss_point'))) > 0
            AND json_type(summary_json, '$.most_manual_step') = 'text'
            AND length(trim(json_extract(summary_json, '$.most_manual_step'))) > 0
            AND json_type(summary_json, '$.current_tools') = 'text'
            AND length(trim(json_extract(summary_json, '$.current_tools'))) > 0
            AND json_type(summary_json, '$.minimum_agent_scenario_and_decision_process') = 'text'
            AND length(trim(json_extract(summary_json, '$.minimum_agent_scenario_and_decision_process'))) > 0
        )
    ),
    UNIQUE (interview_id, mvp_run_id)
);

CREATE TABLE IF NOT EXISTS quote_opportunities (
    quote_opportunity_id TEXT PRIMARY KEY,
    mvp_run_id TEXT NOT NULL,
    response_event_id TEXT,
    interview_id TEXT,
    scope_summary TEXT NOT NULL CHECK (length(trim(scope_summary)) > 0),
    agreed_to_receive_pricing_at TEXT NOT NULL CHECK (
        strftime('%Y-%m-%dT%H:%M:%SZ', agreed_to_receive_pricing_at)
            IS agreed_to_receive_pricing_at
    ),
    verified_at TEXT NOT NULL CHECK (
        strftime('%Y-%m-%dT%H:%M:%SZ', verified_at) IS verified_at
    ),
    recorded_at TEXT NOT NULL CHECK (
        strftime('%Y-%m-%dT%H:%M:%SZ', recorded_at) IS recorded_at
    ),
    CHECK (response_event_id IS NOT NULL OR interview_id IS NOT NULL),
    CHECK (agreed_to_receive_pricing_at <= verified_at),
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
    event_type TEXT NOT NULL CHECK (event_type IN (
        'PLATFORM_PENALTY', 'UNAUTHORIZED_COLLECTION', 'MIS_SEND',
        'DUPLICATE_HARASSMENT', 'SENSITIVE_LEAK', 'UNAUTHORIZED_DATA', 'BYPASS'
    )),
    severity TEXT NOT NULL CHECK (severity = 'CONFIRMED'),
    platform TEXT CHECK (platform IS NULL OR platform IN ('bili', 'dy')),
    summary TEXT NOT NULL CHECK (length(trim(summary)) > 0),
    verified_at TEXT NOT NULL CHECK (
        strftime('%Y-%m-%dT%H:%M:%SZ', verified_at) IS verified_at
    ),
    forces_stop INTEGER NOT NULL DEFAULT 1 CHECK (forces_stop = 1)
);

CREATE TABLE IF NOT EXISTS model_availability_events (
    event_sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    mvp_run_id TEXT NOT NULL REFERENCES mvp_runs(mvp_run_id),
    fact_kind TEXT NOT NULL CHECK (fact_kind IN ('SCORE', 'DRAFT')),
    fact_id TEXT NOT NULL,
    availability_state TEXT NOT NULL CHECK (
        availability_state IN ('AVAILABLE', 'BLOCKED')
    ),
    recorded_at TEXT NOT NULL CHECK (
        strftime('%Y-%m-%dT%H:%M:%SZ', recorded_at) IS recorded_at
    ),
    UNIQUE (fact_kind, fact_id)
);

CREATE TRIGGER IF NOT EXISTS model_availability_event_fact_guard
BEFORE INSERT ON model_availability_events
WHEN NOT EXISTS (
    SELECT 1 FROM score_runs score
    WHERE NEW.fact_kind = 'SCORE'
      AND score.score_run_id = NEW.fact_id
      AND score.mvp_run_id = NEW.mvp_run_id
      AND (
          (NEW.availability_state = 'AVAILABLE' AND score.status = 'SUCCEEDED')
          OR
          (NEW.availability_state = 'BLOCKED' AND score.status = 'FAILED'
           AND score.error_code IN ('MODEL_NOT_CONFIGURED', 'MODEL_UNAVAILABLE'))
      )
)
AND NOT EXISTS (
    SELECT 1 FROM draft_runs draft
    WHERE NEW.fact_kind = 'DRAFT'
      AND draft.draft_run_id = NEW.fact_id
      AND draft.mvp_run_id = NEW.mvp_run_id
      AND draft.draft_kind = 'GENERATED'
      AND (
          (NEW.availability_state = 'AVAILABLE' AND draft.status = 'SUCCEEDED')
          OR
          (NEW.availability_state = 'BLOCKED' AND draft.status = 'FAILED'
           AND draft.error_code IN ('MODEL_NOT_CONFIGURED', 'MODEL_UNAVAILABLE'))
      )
)
BEGIN SELECT RAISE(ABORT, 'MODEL_AVAILABILITY_FACT_INVALID'); END;

CREATE TRIGGER IF NOT EXISTS finalized_model_availability_events_insert
BEFORE INSERT ON model_availability_events
WHEN EXISTS (
    SELECT 1 FROM mvp_runs
    WHERE mvp_run_id = NEW.mvp_run_id AND state = 'FINALIZED'
)
BEGIN SELECT RAISE(ABORT, 'FINALIZED_RUN_IMMUTABLE'); END;

CREATE TRIGGER IF NOT EXISTS score_model_availability_event
AFTER INSERT ON score_runs
WHEN NEW.status = 'SUCCEEDED'
  OR NEW.error_code IN ('MODEL_NOT_CONFIGURED', 'MODEL_UNAVAILABLE')
BEGIN
    INSERT INTO model_availability_events (
        mvp_run_id, fact_kind, fact_id, availability_state, recorded_at
    ) VALUES (
        NEW.mvp_run_id, 'SCORE', NEW.score_run_id,
        CASE WHEN NEW.status = 'SUCCEEDED' THEN 'AVAILABLE' ELSE 'BLOCKED' END,
        NEW.created_at
    );
END;

CREATE TRIGGER IF NOT EXISTS draft_model_availability_event
AFTER INSERT ON draft_runs
WHEN NEW.draft_kind = 'GENERATED'
 AND (
    NEW.status = 'SUCCEEDED'
    OR NEW.error_code IN ('MODEL_NOT_CONFIGURED', 'MODEL_UNAVAILABLE')
 )
BEGIN
    INSERT INTO model_availability_events (
        mvp_run_id, fact_kind, fact_id, availability_state, recorded_at
    ) VALUES (
        NEW.mvp_run_id, 'DRAFT', NEW.draft_run_id,
        CASE WHEN NEW.status = 'SUCCEEDED' THEN 'AVAILABLE' ELSE 'BLOCKED' END,
        NEW.created_at
    );
END;

CREATE TRIGGER IF NOT EXISTS model_availability_events_append_only_update
BEFORE UPDATE ON model_availability_events
BEGIN SELECT RAISE(ABORT, 'APPEND_ONLY_FACT'); END;

CREATE TRIGGER IF NOT EXISTS model_availability_events_append_only_delete
BEFORE DELETE ON model_availability_events
BEGIN SELECT RAISE(ABORT, 'APPEND_ONLY_FACT'); END;

CREATE TRIGGER IF NOT EXISTS mvp_runs_finalized_immutable
BEFORE UPDATE ON mvp_runs
WHEN OLD.state = 'FINALIZED'
BEGIN
    SELECT RAISE(ABORT, 'FINALIZED_RUN_IMMUTABLE');
END;

CREATE TRIGGER IF NOT EXISTS mvp_runs_initial_state_guard
BEFORE INSERT ON mvp_runs
WHEN NEW.state NOT IN ('DRAFT', 'ACTIVE')
BEGIN SELECT RAISE(ABORT, 'RUN_INITIAL_STATE_INVALID'); END;

CREATE TRIGGER IF NOT EXISTS mvp_runs_day0_config_immutable
BEFORE UPDATE ON mvp_runs
WHEN NEW.revision_of_run_id IS NOT OLD.revision_of_run_id
  OR NEW.timezone IS NOT OLD.timezone
  OR NEW.authorization_basis IS NOT OLD.authorization_basis
  OR NEW.platform_scope_json IS NOT OLD.platform_scope_json
  OR NEW.query_set_sha256 IS NOT OLD.query_set_sha256
  OR NEW.prompt_version IS NOT OLD.prompt_version
  OR NEW.schema_version IS NOT OLD.schema_version
  OR NEW.thresholds_sha256 IS NOT OLD.thresholds_sha256
  OR NEW.started_at IS NOT OLD.started_at
  OR NEW.day14_due_at IS NOT OLD.day14_due_at
BEGIN SELECT RAISE(ABORT, 'DAY0_CONFIG_IMMUTABLE'); END;

CREATE TRIGGER IF NOT EXISTS mvp_runs_state_transition_guard
BEFORE UPDATE OF state ON mvp_runs
WHEN NOT (
    (OLD.state = 'DRAFT' AND NEW.state = 'ACTIVE')
    OR (OLD.state = 'ACTIVE' AND NEW.state IN ('CANCELLED', 'FINALIZED'))
    OR (OLD.state = 'CANCELLED' AND NEW.state = 'FINALIZED')
)
BEGIN SELECT RAISE(ABORT, 'RUN_STATE_INVALID_TRANSITION'); END;

CREATE TRIGGER IF NOT EXISTS mvp_runs_conclusion_only_when_finalized
BEFORE UPDATE ON mvp_runs
WHEN NEW.state <> 'FINALIZED'
     AND (
         NEW.finalized_at IS NOT NULL
         OR NEW.conclusion IS NOT NULL
         OR NEW.conclusion_facts_json IS NOT NULL
         OR NEW.conclusion_facts_sha256 IS NOT NULL
         OR NEW.final_report_sha256 IS NOT NULL
     )
BEGIN SELECT RAISE(ABORT, 'RUN_CONCLUSION_BEFORE_FINALIZATION'); END;

CREATE TRIGGER IF NOT EXISTS mvp_runs_finalization_requires_snapshot
BEFORE UPDATE OF state ON mvp_runs
WHEN NEW.state = 'FINALIZED'
     AND (
         NEW.finalized_at IS NULL
         OR NEW.conclusion NOT IN (
             'STOP_DISCOVERY', 'BLOCKED_INPUT',
             'PROCEED_TO_V03_REVIEW', 'REVISE_MVP'
         )
         OR NEW.conclusion_facts_json IS NULL
         OR json_valid(NEW.conclusion_facts_json) = 0
         OR NEW.conclusion_facts_sha256 IS NULL
         OR length(NEW.conclusion_facts_sha256) <> 64
         OR NEW.final_report_sha256 IS NULL
         OR length(NEW.final_report_sha256) <> 64
     )
BEGIN SELECT RAISE(ABORT, 'FINALIZATION_SNAPSHOT_REQUIRED'); END;

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

CREATE TRIGGER IF NOT EXISTS finalized_score_presentations_insert
BEFORE INSERT ON score_presentations
WHEN EXISTS (SELECT 1 FROM mvp_runs WHERE mvp_run_id = NEW.mvp_run_id AND state = 'FINALIZED')
BEGIN SELECT RAISE(ABORT, 'FINALIZED_RUN_IMMUTABLE'); END;
CREATE TRIGGER IF NOT EXISTS finalized_score_presentations_update
BEFORE UPDATE ON score_presentations
WHEN EXISTS (SELECT 1 FROM mvp_runs WHERE mvp_run_id = OLD.mvp_run_id AND state = 'FINALIZED')
BEGIN SELECT RAISE(ABORT, 'FINALIZED_RUN_IMMUTABLE'); END;
CREATE TRIGGER IF NOT EXISTS finalized_score_presentations_delete
BEFORE DELETE ON score_presentations
WHEN EXISTS (SELECT 1 FROM mvp_runs WHERE mvp_run_id = OLD.mvp_run_id AND state = 'FINALIZED')
BEGIN SELECT RAISE(ABORT, 'FINALIZED_RUN_IMMUTABLE'); END;

CREATE TRIGGER IF NOT EXISTS finalized_activity_sessions_insert
BEFORE INSERT ON activity_sessions
WHEN EXISTS (SELECT 1 FROM mvp_runs WHERE mvp_run_id = NEW.mvp_run_id AND state = 'FINALIZED')
BEGIN SELECT RAISE(ABORT, 'FINALIZED_RUN_IMMUTABLE'); END;
CREATE TRIGGER IF NOT EXISTS finalized_activity_sessions_update
BEFORE UPDATE ON activity_sessions
WHEN EXISTS (SELECT 1 FROM mvp_runs WHERE mvp_run_id = OLD.mvp_run_id AND state = 'FINALIZED')
BEGIN SELECT RAISE(ABORT, 'FINALIZED_RUN_IMMUTABLE'); END;
CREATE TRIGGER IF NOT EXISTS finalized_activity_sessions_delete
BEFORE DELETE ON activity_sessions
WHEN EXISTS (SELECT 1 FROM mvp_runs WHERE mvp_run_id = OLD.mvp_run_id AND state = 'FINALIZED')
BEGIN SELECT RAISE(ABORT, 'FINALIZED_RUN_IMMUTABLE'); END;

CREATE TRIGGER IF NOT EXISTS finalized_activity_events_insert
BEFORE INSERT ON activity_events
WHEN EXISTS (SELECT 1 FROM mvp_runs WHERE mvp_run_id = NEW.mvp_run_id AND state = 'FINALIZED')
BEGIN SELECT RAISE(ABORT, 'FINALIZED_RUN_IMMUTABLE'); END;
CREATE TRIGGER IF NOT EXISTS finalized_activity_events_update
BEFORE UPDATE ON activity_events
WHEN EXISTS (SELECT 1 FROM mvp_runs WHERE mvp_run_id = OLD.mvp_run_id AND state = 'FINALIZED')
BEGIN SELECT RAISE(ABORT, 'FINALIZED_RUN_IMMUTABLE'); END;
CREATE TRIGGER IF NOT EXISTS finalized_activity_events_delete
BEFORE DELETE ON activity_events
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
        WHEN NEW.mvp_run_id IS NOT OLD.mvp_run_id
            THEN RAISE(ABORT, 'RUN_SCOPE_IMMUTABLE')
        WHEN NEW.campaign_id IS NOT OLD.campaign_id
          OR NEW.platform IS NOT OLD.platform
          OR NEW.query_cluster IS NOT OLD.query_cluster
          OR NEW.query_text IS NOT OLD.query_text
          OR NEW.max_contents IS NOT OLD.max_contents
          OR NEW.max_comments_per_content IS NOT OLD.max_comments_per_content
          OR NEW.created_at IS NOT OLD.created_at
            THEN RAISE(ABORT, 'FACT_IDENTITY_IMMUTABLE')
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
        WHEN NEW.mvp_run_id IS NOT OLD.mvp_run_id
            THEN RAISE(ABORT, 'RUN_SCOPE_IMMUTABLE')
        WHEN NEW.collection_run_id IS NOT OLD.collection_run_id
          OR NEW.campaign_id IS NOT OLD.campaign_id
          OR NEW.platform IS NOT OLD.platform
          OR NEW.attempt IS NOT OLD.attempt
          OR NEW.backend IS NOT OLD.backend
            THEN RAISE(ABORT, 'FACT_IDENTITY_IMMUTABLE')
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

CREATE TRIGGER IF NOT EXISTS score_presentations_append_only_update
BEFORE UPDATE ON score_presentations
BEGIN SELECT RAISE(ABORT, 'APPEND_ONLY_FACT'); END;
CREATE TRIGGER IF NOT EXISTS score_presentations_append_only_delete
BEFORE DELETE ON score_presentations
BEGIN SELECT RAISE(ABORT, 'APPEND_ONLY_FACT'); END;

CREATE TRIGGER IF NOT EXISTS successful_score_required_for_presentation
BEFORE INSERT ON score_presentations
WHEN NOT EXISTS (
    SELECT 1 FROM score_runs
    WHERE score_run_id = NEW.score_run_id
      AND mvp_run_id = NEW.mvp_run_id
      AND signal_id = NEW.signal_id
      AND status = 'SUCCEEDED'
)
BEGIN SELECT RAISE(ABORT, 'PRESENTED_SCORE_NOT_SUCCEEDED'); END;

CREATE TRIGGER IF NOT EXISTS activity_session_transition_guard
BEFORE UPDATE ON activity_sessions
BEGIN
    SELECT CASE
        WHEN NEW.activity_session_id IS NOT OLD.activity_session_id
          OR NEW.mvp_run_id IS NOT OLD.mvp_run_id
          OR NEW.signal_id IS NOT OLD.signal_id
          OR NEW.activity_kind IS NOT OLD.activity_kind
          OR NEW.started_at IS NOT OLD.started_at
            THEN RAISE(ABORT, 'ACTIVITY_IDENTITY_IMMUTABLE')
        WHEN OLD.state = 'OPEN' AND NEW.state NOT IN ('PAUSED', 'COMPLETED', 'CANCELLED')
            THEN RAISE(ABORT, 'ACTIVITY_INVALID_TRANSITION')
        WHEN OLD.state = 'PAUSED' AND NEW.state NOT IN ('OPEN', 'CANCELLED')
            THEN RAISE(ABORT, 'ACTIVITY_INVALID_TRANSITION')
        WHEN OLD.state IN ('COMPLETED', 'CANCELLED')
            THEN RAISE(ABORT, 'APPEND_ONLY_FACT')
        WHEN NEW.state = 'PAUSED'
          AND NOT EXISTS (
              SELECT 1 FROM activity_events event
              WHERE event.activity_session_id = OLD.activity_session_id
                AND event.sequence_no = (
                    SELECT max(last.sequence_no) FROM activity_events last
                    WHERE last.activity_session_id = OLD.activity_session_id
                )
                AND event.event_kind IN ('PAUSE_HIDDEN', 'PAUSE_IDLE')
                AND NEW.completed_at IS NULL
                AND NEW.active_seconds IS NULL
          )
            THEN RAISE(ABORT, 'ACTIVITY_STATE_EVENT_REQUIRED')
        WHEN OLD.state = 'PAUSED' AND NEW.state = 'OPEN'
          AND NOT EXISTS (
              SELECT 1 FROM activity_events event
              WHERE event.activity_session_id = OLD.activity_session_id
                AND event.sequence_no = (
                    SELECT max(last.sequence_no) FROM activity_events last
                    WHERE last.activity_session_id = OLD.activity_session_id
                )
                AND event.event_kind = 'RESUME'
                AND NEW.completed_at IS NULL
                AND NEW.active_seconds IS NULL
          )
            THEN RAISE(ABORT, 'ACTIVITY_STATE_EVENT_REQUIRED')
        WHEN NEW.state IN ('COMPLETED', 'CANCELLED')
          AND NOT EXISTS (
              SELECT 1 FROM activity_events event
              WHERE event.activity_session_id = OLD.activity_session_id
                AND event.sequence_no = (
                    SELECT max(last.sequence_no) FROM activity_events last
                    WHERE last.activity_session_id = OLD.activity_session_id
                )
                AND event.event_kind = CASE NEW.state
                    WHEN 'COMPLETED' THEN 'COMPLETE' ELSE 'CANCEL' END
                AND event.received_at = NEW.completed_at
          )
            THEN RAISE(ABORT, 'ACTIVITY_TERMINAL_EVENT_REQUIRED')
    END;
END;
CREATE TRIGGER IF NOT EXISTS activity_summary_matches_events
BEFORE UPDATE ON activity_sessions
WHEN NEW.state IN ('COMPLETED', 'CANCELLED')
     AND NEW.active_seconds <> (
         SELECT coalesce(sum(
             CASE
               WHEN terminal.event_kind = 'PAUSE_IDLE' THEN max(
                   0,
                   cast(strftime('%s', terminal.received_at) as integer)
                   - cast(strftime('%s', prior.received_at) as integer)
                   - 60
               )
               ELSE max(
                   0,
                   cast(strftime('%s', terminal.received_at) as integer)
                   - cast(strftime('%s', prior.received_at) as integer)
               )
             END
         ), 0)
         FROM activity_events terminal
         JOIN activity_events prior
           ON prior.activity_session_id = terminal.activity_session_id
          AND prior.sequence_no = terminal.sequence_no - 1
          AND prior.event_kind IN ('START', 'RESUME')
         WHERE terminal.activity_session_id = OLD.activity_session_id
           AND terminal.event_kind IN (
               'PAUSE_HIDDEN', 'PAUSE_IDLE', 'COMPLETE', 'CANCEL'
           )
     )
BEGIN SELECT RAISE(ABORT, 'ACTIVITY_SUMMARY_MISMATCH'); END;
CREATE TRIGGER IF NOT EXISTS activity_sessions_append_only_delete
BEFORE DELETE ON activity_sessions
BEGIN SELECT RAISE(ABORT, 'APPEND_ONLY_FACT'); END;
CREATE TRIGGER IF NOT EXISTS activity_events_append_only_update
BEFORE UPDATE ON activity_events
BEGIN SELECT RAISE(ABORT, 'APPEND_ONLY_FACT'); END;
CREATE TRIGGER IF NOT EXISTS activity_events_append_only_delete
BEFORE DELETE ON activity_events
BEGIN SELECT RAISE(ABORT, 'APPEND_ONLY_FACT'); END;

CREATE TRIGGER IF NOT EXISTS review_requires_completed_activity
BEFORE INSERT ON human_reviews
WHEN NOT EXISTS (
    SELECT 1 FROM activity_sessions session
    WHERE session.activity_session_id = NEW.activity_session_id
      AND session.mvp_run_id = NEW.mvp_run_id
      AND session.signal_id = NEW.signal_id
      AND session.activity_kind = 'REVIEW'
      AND session.state = 'COMPLETED'
      AND session.started_at = NEW.started_at
      AND session.completed_at = NEW.completed_at
      AND session.active_seconds = NEW.active_seconds
)
BEGIN SELECT RAISE(ABORT, 'REVIEW_ACTIVITY_NOT_COMPLETED'); END;

CREATE TRIGGER IF NOT EXISTS human_reviews_append_only_update
BEFORE UPDATE ON human_reviews
BEGIN SELECT RAISE(ABORT, 'APPEND_ONLY_FACT'); END;
CREATE TRIGGER IF NOT EXISTS human_reviews_append_only_delete
BEFORE DELETE ON human_reviews
BEGIN SELECT RAISE(ABORT, 'APPEND_ONLY_FACT'); END;

CREATE TRIGGER IF NOT EXISTS successful_presented_score_required
BEFORE INSERT ON human_reviews
WHEN NOT EXISTS (
    SELECT 1 FROM score_presentations
    WHERE score_run_id = NEW.presented_score_run_id
      AND mvp_run_id = NEW.mvp_run_id
      AND signal_id = NEW.signal_id
)
BEGIN SELECT RAISE(ABORT, 'PRESENTED_SCORE_NOT_SUCCEEDED'); END;

CREATE TRIGGER IF NOT EXISTS review_revision_must_follow_current_leaf
BEFORE INSERT ON human_reviews
WHEN EXISTS (
        SELECT 1 FROM human_reviews
        WHERE mvp_run_id = NEW.mvp_run_id AND signal_id = NEW.signal_id
    )
    AND (
        NEW.supersedes_review_id IS NULL
        OR NOT EXISTS (
            SELECT 1 FROM human_reviews AS parent
            WHERE parent.review_id = NEW.supersedes_review_id
              AND parent.mvp_run_id = NEW.mvp_run_id
              AND parent.signal_id = NEW.signal_id
              AND NOT EXISTS (
                  SELECT 1 FROM human_reviews AS child
                  WHERE child.supersedes_review_id = parent.review_id
              )
        )
    )
BEGIN SELECT RAISE(ABORT, 'REVIEW_SUPERSEDES_NOT_CURRENT'); END;

CREATE TRIGGER IF NOT EXISTS draft_requires_governed_activity
BEFORE INSERT ON draft_runs
WHEN NEW.draft_kind = 'HUMAN_EDITED'
     AND NOT EXISTS (
         SELECT 1 FROM activity_sessions session
         WHERE session.activity_session_id = NEW.activity_session_id
           AND session.mvp_run_id = NEW.mvp_run_id
           AND session.signal_id = NEW.signal_id
           AND session.activity_kind = 'DRAFT'
           AND session.state = 'COMPLETED'
     )
BEGIN SELECT RAISE(ABORT, 'DRAFT_ACTIVITY_NOT_COMPLETED'); END;

CREATE TRIGGER IF NOT EXISTS follow_up_parent_must_be_root
BEFORE INSERT ON outreach_actions
WHEN NEW.parent_outreach_action_id IS NOT NULL
    AND NOT EXISTS (
        SELECT 1 FROM outreach_actions AS parent
        WHERE parent.outreach_action_id = NEW.parent_outreach_action_id
          AND parent.mvp_run_id = NEW.mvp_run_id
          AND parent.signal_id = NEW.signal_id
          AND parent.platform = NEW.platform
          AND parent.subject_key = NEW.subject_key
          AND parent.parent_outreach_action_id IS NULL
    )
BEGIN SELECT RAISE(ABORT, 'FOLLOW_UP_PARENT_NOT_ROOT'); END;

CREATE TRIGGER IF NOT EXISTS outreach_bindings_must_be_ready
BEFORE INSERT ON outreach_actions
WHEN NOT EXISTS (
        SELECT 1 FROM human_reviews
        WHERE review_id = NEW.review_id
          AND mvp_run_id = NEW.mvp_run_id
          AND signal_id = NEW.signal_id
          AND completed_at IS NOT NULL
          AND presented_score_run_id = NEW.score_run_id
          AND NOT EXISTS (
              SELECT 1 FROM human_reviews child
              WHERE child.supersedes_review_id = human_reviews.review_id
          )
    )
    OR NOT EXISTS (
        SELECT 1 FROM score_runs
        WHERE score_run_id = NEW.score_run_id
          AND mvp_run_id = NEW.mvp_run_id
          AND signal_id = NEW.signal_id
          AND status = 'SUCCEEDED'
    )
    OR NOT EXISTS (
        SELECT 1 FROM draft_runs
        WHERE draft_run_id = NEW.draft_run_id
          AND mvp_run_id = NEW.mvp_run_id
          AND signal_id = NEW.signal_id
          AND status = 'SUCCEEDED'
          AND draft_kind = 'HUMAN_EDITED'
    )
BEGIN SELECT RAISE(ABORT, 'OUTREACH_BINDING_NOT_READY'); END;

CREATE TRIGGER IF NOT EXISTS outreach_time_follows_review_and_draft
BEFORE INSERT ON outreach_actions
WHEN NEW.status = 'SENT_VERIFIED'
     AND NOT EXISTS (
         SELECT 1 FROM human_reviews review
         JOIN draft_runs draft
           ON draft.draft_run_id = NEW.draft_run_id
          AND draft.mvp_run_id = NEW.mvp_run_id
          AND draft.signal_id = NEW.signal_id
         LEFT JOIN outreach_actions parent
           ON parent.outreach_action_id = NEW.parent_outreach_action_id
          AND parent.mvp_run_id = NEW.mvp_run_id
         WHERE review.review_id = NEW.review_id
           AND review.mvp_run_id = NEW.mvp_run_id
           AND review.signal_id = NEW.signal_id
           AND NEW.sent_at >= review.completed_at
           AND NEW.sent_at >= draft.created_at
           AND (
               NEW.parent_outreach_action_id IS NULL
               OR NEW.sent_at >= parent.sent_at
           )
     )
BEGIN SELECT RAISE(ABORT, 'OUTREACH_TIME_CAUSALITY'); END;

CREATE TRIGGER IF NOT EXISTS outreach_score_matches_review
BEFORE INSERT ON outreach_actions
WHEN EXISTS (
    SELECT 1 FROM human_reviews
    WHERE review_id = NEW.review_id
      AND presented_score_run_id <> NEW.score_run_id
)
BEGIN SELECT RAISE(ABORT, 'OUTREACH_SCORE_REVIEW_MISMATCH'); END;

CREATE TRIGGER IF NOT EXISTS outreach_context_is_verbatim
BEFORE INSERT ON outreach_actions
WHEN NEW.status = 'SENT_VERIFIED'
     AND (
         instr(NEW.approved_text, NEW.context_evidence) = 0
         OR NOT EXISTS (
             SELECT 1 FROM signals signal
             LEFT JOIN sources source ON source.source_id = signal.source_id
             WHERE signal.signal_id = NEW.signal_id
               AND instr(
                   coalesce(source.title, '') || '\n'
                   || coalesce(signal.parent_body, '') || '\n'
                   || signal.body,
                   NEW.context_evidence
               ) > 0
         )
     )
BEGIN SELECT RAISE(ABORT, 'OUTREACH_CONTEXT_NOT_VERBATIM'); END;

CREATE TRIGGER IF NOT EXISTS outreach_subject_is_signal_author
BEFORE INSERT ON outreach_actions
WHEN NOT EXISTS (
    SELECT 1 FROM signals signal
    WHERE signal.signal_id = NEW.signal_id
      AND signal.platform = NEW.platform
      AND NEW.subject_key = signal.platform || ':' || signal.author_public_id
)
BEGIN SELECT RAISE(ABORT, 'OUTREACH_SUBJECT_NOT_SIGNAL_AUTHOR'); END;

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

CREATE TRIGGER IF NOT EXISTS response_subject_matches_outreach
BEFORE INSERT ON response_events
WHEN NOT EXISTS (
    SELECT 1 FROM outreach_actions outreach
    WHERE outreach.outreach_action_id = NEW.outreach_action_id
      AND outreach.mvp_run_id = NEW.mvp_run_id
      AND outreach.subject_key = NEW.responder_subject_key
)
BEGIN SELECT RAISE(ABORT, 'RESPONSE_SUBJECT_MISMATCH'); END;

CREATE TRIGGER IF NOT EXISTS valid_response_requires_verified_outreach
BEFORE INSERT ON response_events
WHEN NEW.response_type = 'VALID'
     AND NOT EXISTS (
         SELECT 1 FROM outreach_actions outreach
         WHERE outreach.outreach_action_id = NEW.outreach_action_id
           AND outreach.mvp_run_id = NEW.mvp_run_id
           AND outreach.status = 'SENT_VERIFIED'
           AND outreach.sent_at IS NOT NULL
     )
BEGIN SELECT RAISE(ABORT, 'VALID_RESPONSE_OUTREACH_NOT_SENT'); END;

CREATE TRIGGER IF NOT EXISTS response_time_follows_outreach
BEFORE INSERT ON response_events
WHEN NOT EXISTS (
    SELECT 1 FROM outreach_actions outreach
    WHERE outreach.outreach_action_id = NEW.outreach_action_id
      AND outreach.mvp_run_id = NEW.mvp_run_id
      AND NEW.occurred_at >= outreach.sent_at
      AND NEW.verified_at >= NEW.occurred_at
)
BEGIN SELECT RAISE(ABORT, 'RESPONSE_TIME_CAUSALITY'); END;

CREATE TRIGGER IF NOT EXISTS interviews_append_only_update
BEFORE UPDATE ON interviews
BEGIN SELECT RAISE(ABORT, 'APPEND_ONLY_FACT'); END;
CREATE TRIGGER IF NOT EXISTS interviews_append_only_delete
BEFORE DELETE ON interviews
BEGIN SELECT RAISE(ABORT, 'APPEND_ONLY_FACT'); END;

CREATE TRIGGER IF NOT EXISTS interview_requires_valid_response
BEFORE INSERT ON interviews
WHEN NOT EXISTS (
    SELECT 1 FROM response_events response
    WHERE response.response_event_id = NEW.response_event_id
      AND response.mvp_run_id = NEW.mvp_run_id
      AND response.response_type = 'VALID'
)
BEGIN SELECT RAISE(ABORT, 'INTERVIEW_RESPONSE_NOT_VALID'); END;

CREATE TRIGGER IF NOT EXISTS interview_time_follows_response
BEFORE INSERT ON interviews
WHEN NEW.completed_at IS NOT NULL
     AND NOT EXISTS (
         SELECT 1 FROM response_events response
         WHERE response.response_event_id = NEW.response_event_id
           AND response.mvp_run_id = NEW.mvp_run_id
           AND NEW.scheduled_at <= NEW.completed_at
           AND NEW.completed_at >= response.verified_at
     )
BEGIN SELECT RAISE(ABORT, 'INTERVIEW_TIME_CAUSALITY'); END;

CREATE TRIGGER IF NOT EXISTS interview_summary_exactly_five
BEFORE INSERT ON interviews
WHEN NEW.completed_at IS NOT NULL
     AND (
         (SELECT COUNT(*) FROM json_each(NEW.summary_json)) <> 5
         OR EXISTS (
             SELECT 1 FROM json_each(NEW.summary_json)
             WHERE key NOT IN (
                 'customer_source_and_sales_process',
                 'weekly_lead_volume_and_loss_point',
                 'most_manual_step',
                 'current_tools',
                 'minimum_agent_scenario_and_decision_process'
             )
         )
     )
BEGIN SELECT RAISE(ABORT, 'INTERVIEW_SUMMARY_NOT_EXACT'); END;

CREATE TRIGGER IF NOT EXISTS quote_opportunities_append_only_update
BEFORE UPDATE ON quote_opportunities
BEGIN SELECT RAISE(ABORT, 'APPEND_ONLY_FACT'); END;
CREATE TRIGGER IF NOT EXISTS quote_opportunities_append_only_delete
BEFORE DELETE ON quote_opportunities
BEGIN SELECT RAISE(ABORT, 'APPEND_ONLY_FACT'); END;

CREATE TRIGGER IF NOT EXISTS quote_requires_valid_response
BEFORE INSERT ON quote_opportunities
WHEN NOT EXISTS (
    SELECT 1 FROM response_events response
    LEFT JOIN interviews interview
      ON interview.interview_id = NEW.interview_id
     AND interview.mvp_run_id = NEW.mvp_run_id
    WHERE response.mvp_run_id = NEW.mvp_run_id
      AND response.response_event_id = coalesce(
          NEW.response_event_id, interview.response_event_id
      )
      AND response.response_type = 'VALID'
      AND (
          NEW.response_event_id IS NULL
          OR NEW.interview_id IS NULL
          OR interview.response_event_id = NEW.response_event_id
      )
)
BEGIN SELECT RAISE(ABORT, 'QUOTE_RESPONSE_NOT_VALID'); END;

CREATE TRIGGER IF NOT EXISTS quote_time_follows_business_chain
BEFORE INSERT ON quote_opportunities
WHEN NOT EXISTS (
    SELECT 1 FROM response_events response
    LEFT JOIN interviews interview
      ON interview.interview_id = NEW.interview_id
     AND interview.mvp_run_id = NEW.mvp_run_id
    WHERE response.mvp_run_id = NEW.mvp_run_id
      AND response.response_event_id = coalesce(
          NEW.response_event_id, interview.response_event_id
      )
      AND NEW.agreed_to_receive_pricing_at >= response.verified_at
      AND (
          NEW.interview_id IS NULL
          OR NEW.agreed_to_receive_pricing_at >= interview.completed_at
      )
      AND NEW.verified_at >= NEW.agreed_to_receive_pricing_at
)
BEGIN SELECT RAISE(ABORT, 'QUOTE_TIME_CAUSALITY'); END;

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
