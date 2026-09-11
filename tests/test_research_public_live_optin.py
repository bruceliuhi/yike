"""One explicitly opted-in public read; synthetic identity is not customer UAT."""
import json
import os
from pathlib import Path
import subprocess
from uuid import uuid4

import pytest

from pilot.research_candidates import ResearchCandidateStore
from tests.test_research_resources_postgres import started, store
from tests.test_candidate_ingestion_http_postgres import http_client
from tests.test_confirmed_strategy_review_postgres import real_strategy_env
from tests.test_candidate_review_postgres import (databases, env, execution_databases,
    execution_env, raw_databases, raw_env)


@pytest.mark.skipif(os.environ.get("YIKE_RESEARCH_PUBLIC_LIVE") != "1",
                    reason="explicit single public read opt-in required")
def test_one_fixed_public_read_persists_original_candidates_and_recovery(real_strategy_env):
    env = real_strategy_env
    execution, _ = started(env)
    resource_store = store(env)
    research = ResearchCandidateStore(resource_store)
    binding = dict(task_id=execution["task_id"], run_id=execution["run_id"],
                   action_id=str(uuid4()))
    first = research.read_public(env.claims, **binding)
    event = resource_store.get(env.claims, **binding)
    assert first["event"] == event
    assert first["replayed"] is False
    # Recovery is history-only. This second call must not make another read.
    def forbid_read(_deadline):
        pytest.fail("recovery attempted a second public request")
    recovered = research.read_public(env.claims, **binding, fetcher=forbid_read)
    assert recovered == dict(event=event, receipt=first["receipt"], replayed=True)
    receipt = first["receipt"]
    client, _ = http_client(env)
    response = client.get('/api/ui/raw-candidates', params={'task_id': binding['task_id'], 'page_size': 100})
    assert response.status_code == 200
    listing = response.json()
    assert receipt is not None and listing["total"] == receipt["accepted_count"]
    evidence = []
    for item in listing["items"]:
        response = client.get('/api/ui/raw-candidates/' + item['candidate_id'])
        assert response.status_code == 200
        detail = response.json()
        assert detail["candidate"]["status"] == "UNVERIFIED"
        assert detail["candidate"]["current_version"]["body"].strip()
        assert detail["candidate"]["current_version"]["public_url"].startswith("https://www.v2ex.com/t/")
        assert detail["observations"]["items"][0]["execution_context"]["action_id"] == binding["action_id"]
        evidence.append(detail)
    # Parse the actual HTTP wire response with the same client boundary used by the page.
    probe = subprocess.run([os.environ.get('YIKE_TEST_NODE', 'node'), '--input-type=module', '-e', '''
import { createServer } from 'vite';
let input = ''; for await (const chunk of process.stdin) input += chunk;
const server = await createServer({ configFile: false, server: { middlewareMode: true } });
try {
  const { parseRawCandidateEvidence } = await server.ssrLoadModule('/src/shared/rawCandidateEvidence.ts');
  const items = JSON.parse(input);
  for (const value of items) {
    const c = value.candidate;
    parseRawCandidateEvidence(value, { candidateId: c.candidate_id, candidateRevision: c.revision,
      sourceVersionId: c.current_version.version_id, profileId: c.profile_version_id,
      strategyVersionId: c.strategy_version_id, platform: c.platform });
  }
  console.log(JSON.stringify({ parsed: items.length }));
} finally { await server.close(); }
'''], input=json.dumps(evidence), text=True, capture_output=True, timeout=30,
        cwd=Path(__file__).parents[1] / 'desktop')
    assert probe.returncode == 0, 'client evidence parser failed; inspect locally without printing source'
    assert json.loads(probe.stdout.strip().splitlines()[-1]) == {'parsed': listing['total']}
    print({"live_read_status": event["status"],
           "persisted_candidate_count": listing["total"],
           "digest_recorded": event["output_sha256"] is not None,
           "http_and_client_parse": True,
           "recovery_without_read": True})
    assert event["status"] == "SUCCEEDED", "public read failed; no automatic retry"
