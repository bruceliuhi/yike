from dataclasses import dataclass


@dataclass(frozen=True)
class NormalizedSignal:
    platform: str
    body: str
    external_source_id: str | None = None
    source_title: str | None = None
    source_url: str | None = None
    source_author_public_id: str | None = None
    external_comment_id: str | None = None
    parent_comment_id: str | None = None
    parent_body: str | None = None
    comment_url: str | None = None
    normalized_comment_url: str | None = None
    author_public_id: str | None = None
    source_published_at: str | None = None
    published_at: str | None = None
    collected_at: str | None = None
    raw_sha256: str | None = None
    body_sha256: str | None = None
    envelope_sha256: str | None = None
    query_cluster: str | None = None
    query_text: str | None = None
    collection_run_id: str | None = None
    normalizer_version: str | None = None
    verifiable: bool = False
