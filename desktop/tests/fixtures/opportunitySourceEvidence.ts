export function capturedEvidenceFixture(
  overrides: {
    opportunityId?: string;
    profileVersionId?: string;
  } = {},
): Record<string, unknown> {
  const opportunityId = overrides.opportunityId ?? "TEST-o";
  const profileVersionId = overrides.profileVersionId ?? "TEST-p";
  return {
    status: "CAPTURED",
    snapshot_sha256: "a".repeat(64),
    snapshot: {
      schema_version: "opportunity-source-evidence-v1",
      opportunity_id: opportunityId,
      captured_at: "2026-09-10T09:10:11.123456+08:00",
      source: {
        platform: "XIAOHONGSHU",
        kind: "COMMENT",
        external_source_id: "TEST-source-1",
        external_comment_id: "TEST-comment-1",
        public_url:
          "https://example.test/posts/TEST-source-1?comment=TEST-comment-1",
        version_id: "TEST-source-version-1",
        content_sha256: "b".repeat(64),
        title: null,
        container_title: "TEST 原帖标题：门店视频需求",
        body: "TEST 评论正文：我们需要批量制作\n  保留 空白",
        author_public_id: "TEST-public-author",
        published_at: "2026-09-09T01:02:03.654321Z",
        parent: {
          external_comment_id: "TEST-parent-comment-1",
          body: "TEST 父评论正文：请说明交付时间",
          author_public_id: "TEST-parent-author",
          published_at: "2026-09-09T00:02:03.000001+00:00",
          public_url:
            "https://example.test/posts/TEST-source-1?comment=TEST-parent-comment-1",
        },
      },
      observation: {
        id: "TEST-observation-1",
        observed_at: "2026-09-10T00:59:58.000001+00:00",
        received_at: "2026-09-10T01:00:00+00:00",
      },
      assessment: {
        id: "TEST-assessment-1",
        assessed_at: "2026-09-10T01:05:00.999999+00:00",
        profile_version_id: profileVersionId,
        profile_version: 7,
        strategy_version_id: "TEST-strategy-version-1",
        provider: "TEST-provider",
        model: "TEST-model",
        rule_version: "TEST-rule-v1",
        rule_sha256: "c".repeat(64),
        citations: [
          {
            dimension: "businessMatch",
            field: "source.container_title",
            quote: "门店视频需求",
          },
          {
            dimension: "intent",
            field: "source.body",
            quote: "需要批量制作",
          },
          {
            dimension: "urgency",
            field: "source.parent.body",
            quote: "交付时间",
          },
          {
            dimension: "actionability",
            field: "source.body",
            quote: "\n  保留 空白",
          },
        ],
        omitted_profile_citations: 1,
      },
      verification: {
        method: "HUMAN_REOPENED",
        status_at_capture: "OPEN",
        checked_at: "2026-09-10T01:07:00.123456+00:00",
        opening_method: "DIRECT",
        contact_method: "COMMENT",
      },
    },
  };
}
