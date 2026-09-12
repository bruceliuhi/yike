"""Bounded owner-visible candidate history; never infer contact from a draft."""
from pilot.open_web_reader import PublicReadError, normalize_public_url


def load_research_history(cursor, *, tenant, owner, profile_id):
    cursor.execute("""
      WITH scoped AS (
       SELECT p.candidate_id,p.source_id,s.source_identity,p.latest_observed_at,
        v.content->>'public_url' AS url,LEFT(COALESCE(NULLIF(v.content->>'title',''),
          v.content->>'body','已记录需求'),500) AS description
       FROM pilot_candidate_projections p
       JOIN business_profile_versions b ON b.tenant_id=p.tenant_id AND b.profile_version_id=p.profile_version_id
       JOIN pilot_candidate_sources s ON s.tenant_id=p.tenant_id AND s.owner_user_id=p.owner_user_id
        AND s.source_id=p.source_id
       JOIN pilot_candidate_versions v ON v.tenant_id=p.tenant_id AND v.owner_user_id=p.owner_user_id
        AND v.source_id=p.source_id AND v.version_id=p.version_id
       WHERE p.tenant_id=%s AND p.owner_user_id=%s AND b.profile_id=%s
      ), latest AS (
       SELECT DISTINCT ON(source_identity) * FROM scoped
       ORDER BY source_identity,latest_observed_at DESC,candidate_id
      ), decisions AS (
       SELECT DISTINCT ON(r.candidate_id) r.candidate_id,r.action,r.created_at
       FROM pilot_candidate_review_requests r JOIN scoped s USING(candidate_id)
       WHERE r.tenant_id=%s AND r.owner_user_id=%s AND r.status='SUCCEEDED'
        AND r.action IN('INCLUDE','EXCLUDE')
       ORDER BY r.candidate_id,r.created_at DESC,r.request_id
      ), manual AS (
       SELECT DISTINCT ON(record_id) opportunity_id,status,state,occurred_at,recorded_at
       FROM pilot_structured_followup_revisions WHERE tenant_id=%s AND owner_user_id=%s
       ORDER BY record_id,revision DESC
      ), facts AS (
       SELECT source_identity,'KNOWN' AS state,0 AS priority,latest_observed_at AS happened FROM latest
       UNION ALL
       SELECT s.source_identity,'EXCLUDED',1,d.created_at FROM scoped s JOIN decisions d USING(candidate_id)
        WHERE d.action='EXCLUDE'
       UNION ALL
       SELECT s.source_identity,CASE WHEN m.status IN('LOST','WON') THEN 'CLOSED' ELSE 'CONTACTED' END,
        CASE WHEN m.status IN('LOST','WON') THEN 3 ELSE 2 END,COALESCE(m.occurred_at,m.recorded_at)
       FROM manual m JOIN pilot_candidate_reviews r ON r.opportunity_id=m.opportunity_id
        AND r.tenant_id=%s AND r.owner_user_id=%s
       JOIN pilot_candidate_review_requests rr ON rr.tenant_id=r.tenant_id
        AND rr.owner_user_id=r.owner_user_id AND rr.request_id=r.request_id
       JOIN scoped s ON s.candidate_id=rr.candidate_id WHERE m.state='ACTIVE'
       UNION ALL
       SELECT s.source_identity,'CONTACTED',2,o.recorded_at FROM pilot_outreach_results o
       JOIN pilot_outreach_queue q USING(tenant_id,owner_user_id,request_id)
       JOIN pilot_candidate_reviews r ON r.tenant_id=q.tenant_id AND r.owner_user_id=q.owner_user_id
        AND r.opportunity_id=q.opportunity_id
       JOIN pilot_candidate_review_requests rr ON rr.tenant_id=r.tenant_id
        AND rr.owner_user_id=r.owner_user_id AND rr.request_id=r.request_id
       JOIN scoped s ON s.candidate_id=rr.candidate_id
       WHERE o.tenant_id=%s AND o.owner_user_id=%s AND o.payload#>>'{outcome,status}'='SENT'
      ), chosen AS (
       SELECT DISTINCT ON(source_identity) * FROM facts ORDER BY source_identity,priority DESC,happened DESC
      ) SELECT c.source_identity,c.state,l.url,l.description
       FROM chosen c JOIN latest l USING(source_identity)
       ORDER BY c.priority DESC,c.happened DESC,c.source_identity LIMIT 31
      """,(tenant,owner,profile_id,tenant,owner,tenant,owner,tenant,owner,tenant,owner))
    result=[]
    for key,state,url,description in cursor.fetchall()[:30]:
        try:
            urls=[normalize_public_url(url)]
        except PublicReadError:
            urls=[]
        result.append(dict(project_key=key,state=state,source_urls=urls,
            description=' '.join(description.split())[:500] or '已记录需求'))
    # Legacy/shared imports and externally contacted buyers are not fully covered.
    return ('PARTIAL' if result else 'NONE'),result
