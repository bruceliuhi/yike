from dataclasses import replace
from uuid import uuid4

from app.repository import NormalizedSignal, Repository


def collect_verified_signal(
    repository: Repository,
    run_id: str,
    item: NormalizedSignal,
    *,
    query_cluster: str = "sales-agent",
    query_text: str = "销售线索",
) -> str:
    """Create one synthetic, provenance-complete test Signal.

    This is a code fixture only. It does not represent a real platform request.
    """
    collection_run_id = f"test-collection-{uuid4()}"
    repository.begin_collection(
        run_id=run_id,
        collection_run_id=collection_run_id,
        platform=item.platform,
        query_cluster=query_cluster,
        query_text=query_text,
        max_contents=5,
        max_comments_per_content=20,
        started_by="test-operator",
        runtime_lock_sha256="a" * 64,
        backend="MEDIACRAWLER_AUTHORIZED",
    )
    repository.advance_collection_state(collection_run_id, "RUNNING")
    repository.advance_collection_state(collection_run_id, "IMPORTING")
    prepared = replace(
        item,
        source_author_public_id=(
            item.source_author_public_id or f"source-{item.author_public_id}"
        ),
        raw_sha256=item.raw_sha256 or "b" * 64,
        envelope_sha256=item.envelope_sha256 or "c" * 64,
        query_cluster=query_cluster,
        query_text=query_text,
        collection_run_id=collection_run_id,
        normalizer_version=item.normalizer_version or "test-normalizer-v1",
        verifiable=True,
    )
    return repository.complete_collection_success(
        collection_run_id=collection_run_id,
        run_id=run_id,
        platform=item.platform,
        backend="MEDIACRAWLER_AUTHORIZED",
        query_cluster=query_cluster,
        query_text=query_text,
        max_contents=5,
        max_comments_per_content=20,
        items=[prepared],
        raw_count=1,
        output_manifest_sha256="d" * 64,
    )[0].signal_id
