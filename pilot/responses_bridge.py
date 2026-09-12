"""A per-task, loopback-only adapter for the Responses protocol."""

from __future__ import annotations

import copy
import hashlib
import json
import math
import re
import secrets
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import httpx

from pilot.public_search import normalize_query, valid_search_result


_UPSTREAM = "https://ark.cn-beijing.volces.com/api/v3/responses"
_MAX_BYTES = 2 * 1024 * 1024
_SAFE_NAME = re.compile(r"[^A-Za-z0-9_-]+")


class BridgeError(Exception):
    """Bridge configuration error whose message is always a fixed safe code."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _alias(namespace: str, name: str) -> str:
    stem = _SAFE_NAME.sub("_", f"{namespace}__{name}").strip("_") or "tool"
    digest = hashlib.sha256(f"{namespace}\0{name}".encode()).hexdigest()[:12]
    return f"{stem[:50]}_{digest}"


class _Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False


class ResponsesBridge:
    def __init__(self, *, api_key: str, model: str, max_requests: int,
                 deadline: float, allowed_tools: tuple[tuple[str, str], ...],
                 transport=None, search_service=None):
        if not isinstance(api_key, str) or not api_key or not isinstance(model, str) or not model:
            raise BridgeError("invalid_config")
        if type(max_requests) is not int or not 1 <= max_requests <= 20:
            raise BridgeError("invalid_config")
        if (isinstance(deadline, bool) or not isinstance(deadline, (int, float))
                or not math.isfinite(deadline) or deadline > time.monotonic() + 1800):
            raise BridgeError("invalid_config")
        if not isinstance(allowed_tools, tuple):
            raise BridgeError("invalid_config")
        if search_service is not None and not all(callable(getattr(search_service, name, None))
                                                  for name in ("search", "close")):
            raise BridgeError("invalid_config")
        self._search_service = search_service
        self._api_key = api_key
        self._model = model
        self._max_requests = max_requests
        self._deadline = float(deadline)
        self._transport = transport
        self._by_pair: dict[tuple[str, str], str] = {}
        self._by_alias: dict[str, tuple[str, str]] = {}
        for pair in allowed_tools:
            if (not isinstance(pair, tuple) or len(pair) != 2
                    or not all(isinstance(value, str) and value for value in pair)
                    or pair in self._by_pair):
                raise BridgeError("invalid_tools")
            alias = _alias(*pair)
            if alias in self._by_alias:
                raise BridgeError("tool_alias_collision")
            self._by_pair[pair] = alias
            self._by_alias[alias] = pair
        self._gate = threading.Lock()
        self._state_lock = threading.Lock()
        self._count = 0
        self._records: list[dict] = []
        self._connections: set[socket.socket] = set()
        self._closed = True
        self._server = None
        self._thread = None
        self._client = None

    @property
    def records(self) -> list[dict]:
        with self._state_lock:
            return copy.deepcopy(self._records)

    def __enter__(self):
        if not self._closed:
            raise BridgeError("already_started")
        self.token = secrets.token_urlsafe(32)
        transport = self._transport if self._transport is not None else httpx.HTTPTransport(retries=0)
        self._client = httpx.Client(transport=transport, trust_env=False, follow_redirects=False)
        bridge = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def setup(self):
                self.request.settimeout(max(0.001, min(20.0, bridge._deadline - time.monotonic())))
                super().setup()
                with bridge._state_lock:
                    bridge._connections.add(self.connection)

            def finish(self):
                try:
                    super().finish()
                finally:
                    with bridge._state_lock:
                        bridge._connections.discard(self.connection)

            def do_POST(self):
                bridge._handle(self)

            def do_GET(self):
                bridge._send(self, 405, {"error": {"code": "method_not_allowed"}})

            def do_PUT(self):
                bridge._send(self, 405, {"error": {"code": "method_not_allowed"}})

            do_DELETE = do_PATCH = do_OPTIONS = do_GET

            def log_message(self, *_):
                return

        self._server = _Server(("127.0.0.1", 0), Handler)
        port = self._server.server_address[1]
        self.base_url = f"http://127.0.0.1:{port}/v1"
        self.search_url = self.base_url + "/public-search" if self._search_service is not None else None
        self._closed = False
        self._thread = threading.Thread(target=self._server.serve_forever, name="responses-bridge", daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *_exc):
        with self._state_lock:
            self._closed = True
            connections = tuple(self._connections)
        for connection in connections:
            try:
                connection.shutdown(socket.SHUT_RDWR)
                connection.close()
            except OSError:
                pass
        if self._search_service is not None:
            self._search_service.close()
        if self._client is not None:
            self._client.close()
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=2)
        self._api_key = ""
        self.token = ""

    @staticmethod
    def _send(handler, status: int, value: dict):
        body = json.dumps(value, separators=(",", ":")).encode()
        try:
            handler.send_response(status)
            handler.send_header("content-type", "application/json")
            handler.send_header("content-length", str(len(body)))
            handler.send_header("connection", "close")
            handler.end_headers()
            handler.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _handle(self, handler):
        is_search = handler.path == "/v1/public-search" and self._search_service is not None
        if handler.path != "/v1/responses" and not is_search:
            self._send(handler, 404, {"error": {"code": "not_found"}})
            return
        if handler.headers.get("Authorization") != "Bearer " + self.token:
            self._send(handler, 401, {"error": {"code": "unauthorized"}})
            return
        if not handler.headers.get("content-type", "").lower().startswith("application/json"):
            self._send(handler, 400, {"error": {"code": "invalid_request"}})
            return
        try:
            length = int(handler.headers.get("content-length", "-1"))
        except ValueError:
            length = -1
        if length < 0:
            self._send(handler, 400, {"error": {"code": "invalid_request"}})
            return
        if length > _MAX_BYTES:
            self._send(handler, 413, {"error": {"code": "request_too_large"}})
            return
        try:
            raw = handler.rfile.read(length)
        except (OSError, TimeoutError):
            self._send(handler, 408, {"error": {"code": "deadline_exceeded"}})
            return
        if len(raw) != length:
            self._send(handler, 400, {"error": {"code": "invalid_request"}})
            return
        try:
            payload = json.loads(raw)
            if is_search:
                self._search(handler, payload)
                return
            outbound = self._outbound(payload)
        except (ValueError, TypeError, KeyError, RecursionError, BridgeError):
            self._send(handler, 400, {"error": {"code": "invalid_request"}})
            return
        now = time.monotonic()
        with self._state_lock:
            if self._closed or now >= self._deadline:
                self._send(handler, 408, {"error": {"code": "deadline_exceeded"}})
                return
            if self._count >= self._max_requests:
                self._send(handler, 429, {"error": {"code": "request_limit"}})
                return
            self._count += 1
            ordinal = self._count
            self._records.append({"ordinal": ordinal, "status": "unknown", "code": "in_flight",
                                  "usage": None, "elapsed_seconds": 0.0})
        started = time.monotonic()
        status, code, body, usage = self._forward(outbound)
        record = {"ordinal": ordinal, "status": "ok" if status == 200 else "error",
                  "code": code, "usage": usage,
                  "elapsed_seconds": round(time.monotonic() - started, 6)}
        with self._state_lock:
            if not self._closed:
                self._records[ordinal - 1] = record
        if status != 200:
            self._send(handler, status, {"error": {"code": code}})
            return
        try:
            handler.send_response(200)
            handler.send_header("content-type", "text/event-stream")
            handler.send_header("content-length", str(len(body)))
            handler.send_header("connection", "close")
            handler.end_headers()
            handler.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _search(self, handler, payload):
        if type(payload) is not dict or set(payload) != {"query"}:
            raise BridgeError("invalid_request")
        query = normalize_query(payload["query"])
        with self._state_lock:
            unavailable = self._closed or time.monotonic() >= self._deadline
        if unavailable:
            self._send(handler, 408, {"error": {"code": "deadline_exceeded"}})
            return
        try:
            value = self._search_service.search(query)
            if not valid_search_result(value, query):
                value = {"status":"FAILED", "code":"invalid_search_result", "replayed":False}
            if self._closed or time.monotonic() >= self._deadline:
                value = {"status":"FAILED", "code":"deadline_exceeded", "replayed":False}
        except Exception:
            value = {"status":"FAILED", "code":"unavailable", "replayed":False}
        self._send(handler, 200, value)

    def _outbound(self, payload: Any) -> dict:
        if not isinstance(payload, dict) or not isinstance(payload.get("tools", []), list) or not isinstance(payload.get("input", []), list):
            raise BridgeError("invalid_request")
        result = dict(payload)
        result["model"] = self._model
        reasoning = result.get("reasoning")
        if reasoning is not None:
            if not isinstance(reasoning, dict):
                raise BridgeError("invalid_request")
            reasoning = dict(reasoning)
            reasoning.pop("summary", None)
            result["reasoning"] = reasoning
        tools = []
        for namespace in result.get("tools", []):
            if not isinstance(namespace, dict):
                raise BridgeError("invalid_request")
            if namespace.get("type") != "namespace":
                continue
            namespace_name = namespace.get("name")
            declared = namespace.get("tools")
            if not isinstance(namespace_name, str) or not isinstance(declared, list):
                raise BridgeError("invalid_request")
            for tool in declared:
                if not isinstance(tool, dict) or tool.get("type") != "function" or not isinstance(tool.get("name"), str):
                    raise BridgeError("invalid_request")
                pair = (namespace_name, tool["name"])
                alias = self._by_pair.get(pair)
                if alias is None:
                    continue
                item = dict(tool); item["name"] = alias
                tools.append(item)
        result["tools"] = tools
        inputs = []
        for source in result.get("input", []):
            if not isinstance(source, dict):
                inputs.append(source)
                continue
            item = dict(source)
            item_type = item.get("type")
            if isinstance(item_type, str) and item_type.endswith("_call") and item_type != "function_call":
                raise BridgeError("invalid_request")
            if item.get("type") == "function_call":
                pair = (item.get("namespace"), item.get("name"))
                alias = self._by_pair.get(pair)
                if alias is None:
                    raise BridgeError("invalid_request")
                item["name"] = alias; item.pop("namespace", None)
            inputs.append(item)
        result["input"] = inputs
        return result

    def _forward(self, payload: dict):
        with self._gate:
            remaining = self._deadline - time.monotonic()
            with self._state_lock:
                closed = self._closed
            if closed or remaining <= 0:
                return 408, "deadline_exceeded", b"", None
            cutoff = threading.Event()
            def abort_upstream():
                cutoff.set()
                self._client.close()
            timer = threading.Timer(remaining, abort_upstream)
            timer.daemon = True
            timer.start()
            try:
                with self._client.stream("POST", _UPSTREAM,
                                         headers={"authorization": "Bearer " + self._api_key,
                                                  "content-type": "application/json"},
                                         json=payload, timeout=min(20.0, remaining)) as response:
                    if response.status_code != 200:
                        return 502, "provider_error", b"", None
                    if "text/event-stream" not in response.headers.get("content-type", "").lower():
                        return 502, "provider_error", b"", None
                    chunks = []
                    size = 0
                    for chunk in response.iter_bytes():
                        if cutoff.is_set() or time.monotonic() >= self._deadline:
                            return 408, "deadline_exceeded", b"", None
                        size += len(chunk)
                        if size > _MAX_BYTES:
                            return 502, "provider_error", b"", None
                        chunks.append(chunk)
                body, usage = self._inbound(b"".join(chunks))
                with self._state_lock:
                    closed = self._closed
                if closed or time.monotonic() >= self._deadline:
                    return 408, "deadline_exceeded", b"", None
                return 200, "ok", body, usage
            except Exception:
                if cutoff.is_set() or time.monotonic() >= self._deadline:
                    return 408, "deadline_exceeded", b"", None
                return 502, "provider_error", b"", None
            finally:
                timer.cancel()

    def _restore_item(self, source: Any):
        if not isinstance(source, dict):
            raise BridgeError("provider_error")
        item = dict(source)
        item_type = item.get("type")
        if isinstance(item_type, str) and item_type.endswith("_call") and item_type != "function_call":
            raise BridgeError("provider_error")
        if item.get("type") == "function_call":
            pair = self._by_alias.get(item.get("name"))
            if pair is None:
                raise BridgeError("provider_error")
            item["namespace"], item["name"] = pair
        return item

    def _inbound(self, raw: bytes):
        text = raw.decode("utf-8")
        blocks = text.replace("\r\n", "\n").split("\n\n")
        output = []
        completed = False
        sentinel = False
        usage = None
        for block in blocks:
            if not block:
                continue
            lines = block.splitlines()
            data_lines = [line[5:].lstrip() for line in lines if line.startswith("data:")]
            if not data_lines:
                raise BridgeError("provider_error")
            data = "\n".join(data_lines)
            if data == "[DONE]":
                if not completed or sentinel:
                    raise BridgeError("provider_error")
                sentinel = True
                output.append("data: [DONE]\n\n")
                continue
            if completed or sentinel:
                raise BridgeError("provider_error")
            event = json.loads(data)
            if not isinstance(event, dict) or not isinstance(event.get("type"), str):
                raise BridgeError("provider_error")
            if event["type"] in {"response.failed", "response.incomplete"}:
                raise BridgeError("provider_error")
            if "item" in event:
                event = dict(event); event["item"] = self._restore_item(event["item"])
            if event["type"] == "response.completed":
                response = event.get("response")
                if not isinstance(response, dict) or response.get("status") != "completed" or not isinstance(response.get("output", []), list):
                    raise BridgeError("provider_error")
                response = dict(response)
                response["output"] = [self._restore_item(item) for item in response.get("output", [])]
                usage = copy.deepcopy(response.get("usage")) if isinstance(response.get("usage"), dict) else None
                event = dict(event); event["response"] = response
                completed = True
            event_name = next((line[6:].strip() for line in lines if line.startswith("event:")), event["type"])
            output.append(f"event: {event_name}\ndata: {json.dumps(event, separators=(',', ':'))}\n\n")
        if not completed:
            raise BridgeError("provider_error")
        body = "".join(output).encode()
        if len(body) > _MAX_BYTES:
            raise BridgeError("provider_error")
        return body, usage
