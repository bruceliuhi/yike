"""Private one-shot worker. No shell, plugin, database, or child-process hooks."""
from pathlib import Path
import json
import sys

# `-I` ignores ambient PYTHONPATH; load the package beside this exact worker,
# including in source checkouts with an older wheel in site-packages.
if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pilot.search_suggestion_model import (OpenAICompatibleSearchSuggestionModel,
                                           SearchSuggestionError, serialize_suggestion)


def main() -> None:
    reply = {"error": "suggestion_result_unknown"}
    try:
        raw = sys.stdin.buffer.read(65537)
        if len(raw) > 65536:
            raise ValueError("input too large")
        body = json.loads(raw.decode("utf-8"))
        if type(body) is not dict or set(body) != {"configuration", "description"}:
            raise ValueError("invalid input")
        configuration = body["configuration"]
        if type(configuration) is not dict or set(configuration) != {"base_url", "api_key", "model", "timeout_seconds"}:
            raise ValueError("invalid configuration")
        result, usage = OpenAICompatibleSearchSuggestionModel(**configuration).generate(description=body["description"])
        reply = {"content": serialize_suggestion(result), "usage": usage}
    except SearchSuggestionError as error:
        reply = {"error": error.code}
    except Exception:
        pass
    encoded = json.dumps(reply, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(encoded) > 65536:
        encoded = b'{"error":"invalid_suggestion_result"}'
    sys.stdout.buffer.write(encoded)
    sys.stdout.buffer.flush()


if __name__ == "__main__":
    main()
