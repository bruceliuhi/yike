"""MCP-to-host search client: accepts only a temporary literal-loopback route."""
import json
import threading
from urllib.parse import urlsplit

import httpx

from pilot.public_search import normalize_query, valid_search_result

_MAX_RESPONSE_BYTES = 1024 * 1024


class SearchToolClient:
    def __init__(self, *, url: str, token: str):
        try:
            parts = urlsplit(url)
            if (type(url) is not str or parts.scheme != 'http' or parts.hostname != '127.0.0.1'
                    or parts.port is None or not 1 <= parts.port <= 65535
                    or parts.netloc != f'127.0.0.1:{parts.port}'
                    or parts.path != '/v1/public-search' or parts.query or parts.fragment
                    or type(token) is not str or not 1 <= len(token) <= 256
                    or any(c.isspace() for c in token)):
                raise ValueError()
        except (ValueError, TypeError, AttributeError):
            raise ValueError('invalid_search_configuration') from None
        self._url, self._token = url, token

    def search(self, query: str) -> dict:
        failure = dict(status='FAILED', code='unavailable', replayed=False)
        try:
            query = normalize_query(query)
        except ValueError:
            return failure | {'code':'invalid_query'}
        with httpx.Client(timeout=21, trust_env=False, follow_redirects=False) as client:
            timer = threading.Timer(21, client.close)
            timer.daemon = True
            timer.start()
            try:
                with client.stream('POST', self._url, headers={'Authorization':'Bearer '+self._token},
                                   json={'query':query}) as response:
                    if response.status_code != 200:
                        return failure
                    chunks, size = [], 0
                    for chunk in response.iter_bytes():
                        size += len(chunk)
                        if size > _MAX_RESPONSE_BYTES:
                            return failure | {'code':'invalid_search_result'}
                        chunks.append(chunk)
                result = json.loads(b''.join(chunks))
                if not valid_search_result(result, query):
                    return failure | {'code':'invalid_search_result'}
                return result
            except Exception:
                return failure
            finally:
                timer.cancel()
