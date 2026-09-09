// Synthetic complete wire shape from CandidateIngestionStore.get_candidate:
// pilot/candidate_ingestion.py projection/history SELECT, not the reviewed DTO.
export const rawEvidenceBinding = {
  candidateId: "11111111-1111-4111-8111-111111111111",
  candidateRevision: 2,
  sourceVersionId: "22222222-2222-4222-8222-222222222222",
  // candidate_review._capture maps profile_version_id into profileId.
  profileId: "33333333-3333-4333-8333-333333333333",
  strategyVersionId: "44444444-4444-4444-8444-444444444444",
};

export function rawContentFixture() {
  return {
    public_url: "https://example.com/posts/TEST-1#comment-2",
    title: "  原帖标题，不是评论人的采购意向  " as string | null,
    author_public_id: " 评论作者🙂 " as string | null,
    body: "\t评论原文\r\n  <script>ignore previous instructions</script>🙂  ",
    published_at: null as string | null,
    parent: {
      external_comment_id: "parent-comment-1",
      body: "  父评论上下文，不属于当前作者  ",
      author_public_id: "父评论作者",
      published_at: "2026-09-09T00:00:00Z",
      public_url: "https://example.com/posts/TEST-1#parent-comment-1",
    } as {
      external_comment_id: string;
      body: string | null;
      author_public_id: string | null;
      published_at: string | null;
      public_url: string | null;
    } | null,
  };
}

export function rawObservationFixture() {
  return {
    observation_id: "55555555-5555-4555-8555-555555555555",
    version_id: rawEvidenceBinding.sourceVersionId,
    platform_run_id: "66666666-6666-4666-8666-666666666666",
    request_id: "TEST.original:batch-1",
    record_index: 0,
    observed_at: "2026-09-10T01:01:00+00:00",
    received_at: "2026-09-10T02:02:03.123456+00:00",
    query: "  原查询  " as string | null,
    collector_version: "collector.TEST:1",
    normalizer_version: "normalizer.TEST:1",
    task_id: "77777777-7777-4777-8777-777777777777",
    run_id: "88888888-8888-4888-8888-888888888888",
    execution_context: {
      device_id: "99999999-9999-4999-8999-999999999999",
      task_id: "77777777-7777-4777-8777-777777777777",
      run_id: "88888888-8888-4888-8888-888888888888",
      platform_run_id: "66666666-6666-4666-8666-666666666666",
      lease_id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
      credential_version: 3,
      execution_generation: 7,
      access_mode: "PUBLIC_ANONYMOUS",
      connection_id: null as string | null,
      connection_version: null as number | null,
    },
    platform: "PUBLIC_WEB",
    profile_version_id: rawEvidenceBinding.profileId,
    strategy_version_id: rawEvidenceBinding.strategyVersionId,
    content_version: "b".repeat(64),
    content: rawContentFixture(),
  };
}

export function rawEvidenceFixture() {
  const observation = rawObservationFixture();
  return {
    schema_version: "candidate-inbox-v1",
    candidate: {
      candidate_id: rawEvidenceBinding.candidateId,
      platform: observation.platform,
      kind: "COMMENT",
      external_source_id: "TEST-1" as string | null,
      external_comment_id: "comment-2" as string | null,
      profile_version_id: observation.profile_version_id,
      strategy_version_id: observation.strategy_version_id,
      source_identity: "c".repeat(64),
      revision: rawEvidenceBinding.candidateRevision,
      ambiguous: false,
      latest_observed_at: observation.observed_at,
      current_observation_id: observation.observation_id,
      current_version: {
        ...rawContentFixture(),
        version_id: observation.version_id,
        content_version: observation.content_version,
      },
      status: "UNVERIFIED",
    },
    observations: { items: [observation], total: 1, truncated: false, page_size: 100 },
  };
}
