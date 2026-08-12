from dataclasses import dataclass, replace
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Literal

from app.collectors import normalize_bilibili, normalize_douyin
from app.normalizer import PlatformResponseChanged
from app.repository import Repository, SignalIdentityConflict


MEDIACRAWLER_COMMIT = "439509782cc2991c8ef7648e178d5847b0545798"
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_LOCK_PATH = _PROJECT_ROOT / "vendor" / "mediacrawler.lock"


@dataclass(frozen=True)
class CollectionRequest:
    mvp_run_id: str
    collection_run_id: str
    platform: Literal["bili", "dy"]
    query_cluster: str
    query_text: str
    max_contents: int = 5
    max_comments_per_content: int = 20
    started_by: str | None = None


@dataclass(frozen=True)
class CollectionResult:
    mvp_run_id: str
    collection_run_id: str
    platform: str
    status: str
    raw_count: int
    unique_count: int
    error_code: str | None
    output_dir: str


_EXIT_RESULTS: dict[int, tuple[str, str]] = {
    40: ("BLOCKED_INPUT", "PLATFORM_AUTH_REQUIRED"),
    41: ("BLOCKED_INPUT", "PLATFORM_PERMISSION_DENIED"),
    42: ("BLOCKED_INPUT", "PLATFORM_VERIFICATION_REQUIRED"),
    43: ("BLOCKED_INPUT", "PLATFORM_RATE_LIMITED"),
    44: ("FAILED", "PLATFORM_RESPONSE_CHANGED"),
    45: ("FAILED", "COLLECTION_NETWORK_FAILED"),
    46: ("FAILED", "COLLECTION_PARSE_FAILED"),
    47: ("CANCELLED", "COLLECTION_CANCELLED"),
}


class Collector:
    def __init__(
        self,
        *,
        repository: Repository,
        runtime_path: Path,
        work_root: Path,
        python_executable: str = sys.executable,
        timeout_seconds: int = 900,
    ):
        self.repository = repository
        self.runtime_path = runtime_path.resolve()
        self.work_root = work_root.resolve()
        self.python_executable = python_executable
        self.timeout_seconds = timeout_seconds

    def command_for(self, request: CollectionRequest, output_dir: Path) -> list[str]:
        return [
            self.python_executable,
            str((self.runtime_path / "main.py").resolve()),
            "--platform",
            request.platform,
            "--lt",
            "qrcode",
            "--type",
            "search",
            "--keywords",
            request.query_text,
            "--get_comment",
            "yes",
            "--get_sub_comment",
            "yes",
            "--headless",
            "no",
            "--save_data_option",
            "jsonl",
            "--save_data_path",
            str(output_dir.resolve()),
            "--crawler_max_notes_count",
            str(request.max_contents),
            "--max_comments_count_singlenotes",
            str(request.max_comments_per_content),
            "--max_concurrency_num",
            "1",
            "--enable_ip_proxy",
            "no",
        ]

    def collect(self, request: CollectionRequest) -> CollectionResult:
        self._validate_request(request)
        output_dir = self.work_root / request.mvp_run_id / request.collection_run_id
        if output_dir.exists():
            raise ValueError("collection output directory already exists")

        self.repository.begin_collection(
            run_id=request.mvp_run_id,
            collection_run_id=request.collection_run_id,
            platform=request.platform,
            query_cluster=request.query_cluster,
            query_text=request.query_text,
            max_contents=request.max_contents,
            max_comments_per_content=request.max_comments_per_content,
        )
        output_dir.mkdir(parents=True)

        runtime_error = self._runtime_error()
        if runtime_error:
            return self._finish(request, "BLOCKED_INPUT", 0, 0, runtime_error)

        try:
            process = subprocess.run(
                self.command_for(request, output_dir),
                cwd=self.runtime_path,
                check=False,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                shell=False,
                env=os.environ.copy(),
            )
        except subprocess.TimeoutExpired:
            return self._finish(
                request, "FAILED", 0, 0, "COLLECTION_PROCESS_FAILED"
            )
        except KeyboardInterrupt:
            return self._finish(request, "CANCELLED", 0, 0, "COLLECTION_CANCELLED")
        except OSError:
            return self._finish(
                request, "BLOCKED_INPUT", 0, 0, "COLLECTION_RUNTIME_MISSING"
            )

        if process.returncode != 0:
            status, error_code = _EXIT_RESULTS.get(
                process.returncode, ("FAILED", "COLLECTION_PROCESS_FAILED")
            )
            return self._finish(request, status, 0, 0, error_code)

        try:
            data_dir = self._data_dir(request, output_dir)
            contents = self._read_jsonl(data_dir, "search_contents_*.jsonl")
            comments = self._read_jsonl(data_dir, "search_comments_*.jsonl")
        except (OSError, json.JSONDecodeError, ValueError):
            return self._finish(request, "FAILED", 0, 0, "COLLECTION_PARSE_FAILED")

        raw_count = len(comments)
        if not comments:
            return self._finish(
                request,
                "SUCCEEDED_NO_DATA",
                0,
                0,
                None,
                self._manifest_sha256(output_dir),
            )

        try:
            normalized = self._normalize_batch(request, contents, comments)
            before_count = self.repository.count_signals(request.mvp_run_id)
            self.repository.import_signals(request.mvp_run_id, normalized)
            unique_count = (
                self.repository.count_signals(request.mvp_run_id) - before_count
            )
        except PlatformResponseChanged:
            return self._finish(
                request, "FAILED", raw_count, 0, "PLATFORM_RESPONSE_CHANGED"
            )
        except SignalIdentityConflict:
            return self._finish(
                request, "FAILED", raw_count, 0, "SIGNAL_IDENTITY_CONFLICT"
            )
        except (ValueError, KeyError):
            return self._finish(
                request, "FAILED", raw_count, 0, "PLATFORM_RESPONSE_CHANGED"
            )

        return self._finish(
            request,
            "SUCCEEDED",
            raw_count,
            unique_count,
            None,
            self._manifest_sha256(output_dir),
        )

    def _normalize_batch(
        self,
        request: CollectionRequest,
        contents: list[dict[str, object]],
        comments: list[dict[str, object]],
    ):
        source_key = "video_id" if request.platform == "bili" else "aweme_id"
        by_source = {
            str(content[source_key]): content
            for content in contents
            if content.get(source_key) is not None
        }
        comment_id_keys = ("comment_id", "rpid", "cid")
        by_comment = {}
        for comment in comments:
            comment_id = next(
                (comment.get(key) for key in comment_id_keys if comment.get(key)),
                None,
            )
            if comment_id is not None:
                by_comment[str(comment_id)] = comment
        normalizer = normalize_bilibili if request.platform == "bili" else normalize_douyin
        normalized = []
        for original_comment in comments:
            comment = dict(original_comment)
            comment_source = comment.get(source_key)
            if comment_source is None or str(comment_source) not in by_source:
                raise PlatformResponseChanged(
                    "PLATFORM_RESPONSE_CHANGED: comment has no matching content"
                )
            parent_id = comment.get("parent_comment_id") or comment.get("parent_id")
            if parent_id and not (comment.get("parent_content") or comment.get("parent_body")):
                parent = by_comment.get(str(parent_id))
                if parent:
                    parent_body = parent.get("content") or parent.get("body")
                    if parent_body:
                        comment["parent_content"] = parent_body
            item = normalizer(
                {"content": by_source[str(comment_source)], "comment": comment}
            )
            normalized.append(
                replace(
                    item,
                    collection_run_id=request.collection_run_id,
                    query_cluster=request.query_cluster,
                    query_text=request.query_text,
                )
            )
        return normalized

    def _read_jsonl(self, data_dir: Path, pattern: str) -> list[dict[str, object]]:
        root = data_dir.resolve()
        records: list[dict[str, object]] = []
        for path in sorted(data_dir.glob(pattern)):
            resolved = path.resolve()
            if path.is_symlink() or not resolved.is_relative_to(root) or not path.is_file():
                raise ValueError("collector output escaped its run directory")
            with path.open(encoding="utf-8") as source:
                for line in source:
                    if not line.strip():
                        continue
                    record = json.loads(line)
                    if not isinstance(record, dict):
                        raise ValueError("JSONL record must be an object")
                    record["_raw_sha256"] = hashlib.sha256(
                        line.rstrip("\r\n").encode("utf-8")
                    ).hexdigest()
                    records.append(record)
        return records

    def _runtime_error(self) -> str | None:
        main = self.runtime_path / "main.py"
        marker = self.runtime_path / ".mediacrawler-commit"
        if not main.is_file() or not marker.is_file() or not _LOCK_PATH.is_file():
            return "COLLECTION_RUNTIME_MISSING"
        try:
            lock = json.loads(_LOCK_PATH.read_text(encoding="utf-8"))
            runtime_commit = marker.read_text(encoding="utf-8").strip()
        except (OSError, json.JSONDecodeError):
            return "COLLECTION_RUNTIME_MISMATCH"
        if lock.get("commit") != MEDIACRAWLER_COMMIT or runtime_commit != MEDIACRAWLER_COMMIT:
            return "COLLECTION_RUNTIME_MISMATCH"
        return None

    def _manifest_sha256(self, output_dir: Path) -> str:
        manifest = []
        for path in sorted(output_dir.glob("*/jsonl/search_*.jsonl")):
            if path.is_symlink() or not path.resolve().is_relative_to(output_dir.resolve()):
                raise ValueError("collector output escaped its run directory")
            if path.name.startswith(("search_contents_", "search_comments_")):
                manifest.append(
                    (
                        str(path.relative_to(output_dir)),
                        hashlib.sha256(path.read_bytes()).hexdigest(),
                    )
                )
        payload = json.dumps(manifest, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _finish(
        self,
        request: CollectionRequest,
        status: str,
        raw_count: int,
        unique_count: int,
        error_code: str | None,
        manifest_sha256: str | None = None,
    ) -> CollectionResult:
        self.repository.finish_collection(
            request.collection_run_id,
            state=status,
            raw_count=raw_count,
            unique_count=unique_count,
            error_code=error_code,
            output_manifest_sha256=manifest_sha256,
        )
        return CollectionResult(
            mvp_run_id=request.mvp_run_id,
            collection_run_id=request.collection_run_id,
            platform=request.platform,
            status=status,
            raw_count=raw_count,
            unique_count=unique_count,
            error_code=error_code,
            output_dir=str(
                (self.work_root / request.mvp_run_id / request.collection_run_id).resolve()
            ),
        )

    @staticmethod
    def _data_dir(request: CollectionRequest, output_dir: Path) -> Path:
        platform_dir = "bili" if request.platform == "bili" else "douyin"
        return output_dir / platform_dir / "jsonl"

    @staticmethod
    def _validate_request(request: CollectionRequest) -> None:
        if request.platform not in ("bili", "dy"):
            raise ValueError("platform must be bili or dy")
        if not request.query_cluster.strip() or not request.query_text.strip():
            raise ValueError("query cluster and text are required")
        if not 1 <= request.max_contents <= 10:
            raise ValueError("max contents limit must be between 1 and 10")
        if not 1 <= request.max_comments_per_content <= 50:
            raise ValueError("max comments limit must be between 1 and 50")
