"""Command configuration only: no Codex process, provider call or network."""
import json
from types import SimpleNamespace

import pytest

from pilot.codex_research_worker import _command


@pytest.mark.parametrize('controlled,search_enabled,compiled,expected', [
    (True, True, True, 'low'),
    (False, True, True, 'minimal'),
    (True, True, False, 'minimal'),
    (True, False, True, 'minimal'),
])
def test_reasoning_only_for_controlled_compiled_discovery(tmp_path, controlled, search_enabled, compiled, expected):
    bridge = SimpleNamespace(base_url='http://127.0.0.1:1/v1',
                             search_url='http://127.0.0.1:1/v1/public-search',
                             read_url='http://127.0.0.1:1/v1/public-read', token='test-only')
    command = _command(tmp_path, codex_binary='codex', python_binary='python',
                       model='test-model', bridge=bridge, max_reads=4, max_seconds=60,
                       max_requests=6, max_searches=3, search_enabled=search_enabled,
                       research_instructions='Confirmed research scope' if compiled else None,
                       controlled=controlled)
    config = dict((value.split('=', 1)[0], json.loads(value.split('=', 1)[1]))
                  for index, value in enumerate(command) if index and command[index-1] == '-c')
    assert config['model_reasoning_effort'] == expected
    assert config['model'] == 'test-model'
    assert config['model_providers.yike_domestic.request_max_retries'] == 0
    assert config['model_providers.yike_domestic.stream_max_retries'] == 0
    assert config['features.shell_tool'] is False
    assert config['features.unbounded_connection_retries'] is False
    assert command[command.index('--sandbox') + 1] == 'read-only'
    assert ('--output-schema' in command) == compiled
