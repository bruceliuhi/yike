import csv
import io
import sqlite3


SIGNAL_EXPORT_FIELDS = (
    "mvp_run_id",
    "signal_id",
    "platform",
    "external_source_id",
    "source_title",
    "source_url",
    "external_comment_id",
    "parent_comment_id",
    "parent_body",
    "comment_url",
    "author_public_id",
    "body",
    "published_at",
    "query_cluster",
    "query_text",
    "observed_at",
    "grade",
    "total_score",
    "human_label",
    "review_reason",
    "outreach_status",
    "sent_at",
)


def export_signals_csv(connection: sqlite3.Connection, run_id: str) -> str:
    """Export visible evidence/workflow facts without model or secret configuration."""
    rows = connection.execute(
        """
        SELECT
            m.mvp_run_id,
            s.signal_id,
            s.platform,
            src.external_source_id,
            src.title AS source_title,
            src.canonical_url AS source_url,
            s.external_comment_id,
            s.parent_comment_id,
            s.parent_body,
            s.normalized_comment_url AS comment_url,
            s.author_public_id,
            s.body,
            s.published_at,
            (SELECT so.query_cluster FROM signal_observations so
             WHERE so.mvp_run_id = m.mvp_run_id AND so.signal_id = s.signal_id
             ORDER BY so.observed_at DESC, so.observation_id DESC LIMIT 1) AS query_cluster,
            (SELECT so.query_text FROM signal_observations so
             WHERE so.mvp_run_id = m.mvp_run_id AND so.signal_id = s.signal_id
             ORDER BY so.observed_at DESC, so.observation_id DESC LIMIT 1) AS query_text,
            (SELECT so.observed_at FROM signal_observations so
             WHERE so.mvp_run_id = m.mvp_run_id AND so.signal_id = s.signal_id
             ORDER BY so.observed_at DESC, so.observation_id DESC LIMIT 1) AS observed_at,
            (SELECT sr.grade FROM score_runs sr
             WHERE sr.mvp_run_id = m.mvp_run_id AND sr.signal_id = s.signal_id
               AND sr.status = 'SUCCEEDED'
             ORDER BY sr.created_at DESC, sr.score_run_id DESC LIMIT 1) AS grade,
            (SELECT sr.total_score FROM score_runs sr
             WHERE sr.mvp_run_id = m.mvp_run_id AND sr.signal_id = s.signal_id
               AND sr.status = 'SUCCEEDED'
             ORDER BY sr.created_at DESC, sr.score_run_id DESC LIMIT 1) AS total_score,
            (SELECT hr.label FROM human_reviews hr
             WHERE hr.mvp_run_id = m.mvp_run_id AND hr.signal_id = s.signal_id
               AND NOT EXISTS (
                 SELECT 1 FROM human_reviews newer
                 WHERE newer.supersedes_review_id = hr.review_id
                   AND newer.mvp_run_id = hr.mvp_run_id
                   AND newer.signal_id = hr.signal_id
               )
             ORDER BY hr.completed_at DESC, hr.review_id DESC LIMIT 1) AS human_label,
            (SELECT hr.reason FROM human_reviews hr
             WHERE hr.mvp_run_id = m.mvp_run_id AND hr.signal_id = s.signal_id
               AND NOT EXISTS (
                 SELECT 1 FROM human_reviews newer
                 WHERE newer.supersedes_review_id = hr.review_id
                   AND newer.mvp_run_id = hr.mvp_run_id
                   AND newer.signal_id = hr.signal_id
               )
             ORDER BY hr.completed_at DESC, hr.review_id DESC LIMIT 1) AS review_reason,
            (SELECT oa.status FROM outreach_actions oa
             WHERE oa.mvp_run_id = m.mvp_run_id AND oa.signal_id = s.signal_id
             ORDER BY oa.created_at DESC, oa.outreach_action_id DESC LIMIT 1) AS outreach_status,
            (SELECT oa.sent_at FROM outreach_actions oa
             WHERE oa.mvp_run_id = m.mvp_run_id AND oa.signal_id = s.signal_id
             ORDER BY oa.created_at DESC, oa.outreach_action_id DESC LIMIT 1) AS sent_at
        FROM mvp_run_signals m
        JOIN signals s ON s.signal_id = m.signal_id
        LEFT JOIN sources src ON src.source_id = s.source_id
        WHERE m.mvp_run_id = ?
        ORDER BY
          CASE COALESCE((SELECT sr.grade FROM score_runs sr
                         WHERE sr.mvp_run_id = m.mvp_run_id
                           AND sr.signal_id = s.signal_id
                           AND sr.status = 'SUCCEEDED'
                         ORDER BY sr.created_at DESC, sr.score_run_id DESC LIMIT 1), '')
            WHEN 'A' THEN 0 WHEN 'B' THEN 1 WHEN 'C' THEN 2 WHEN 'D' THEN 3 ELSE 4
          END,
          m.added_at,
          s.signal_id
        """,
        (run_id,),
    ).fetchall()
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=SIGNAL_EXPORT_FIELDS, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow(
            {field: _spreadsheet_safe(row[field]) for field in SIGNAL_EXPORT_FIELDS}
        )
    return output.getvalue()


def _spreadsheet_safe(value: object | None) -> object:
    if not isinstance(value, str):
        return "" if value is None else value
    if value.startswith(("=", "+", "-", "@")):
        return f"'{value}"
    return value
