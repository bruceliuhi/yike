from dataclasses import dataclass, replace
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Literal

from app.collectors import normalize_bilibili, normalize_douyin
from app.normalizer import PlatformResponseChanged
from app.repository import Repository, SignalIdentityConflict


MEDIACRAWLER_COMMIT = "439509782cc2991c8ef7648e178d5847b0545798"
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_LOCK_PATH = _PROJECT_ROOT / "vendor" / "mediacrawler.lock"
_PATCH_ROOT = _PROJECT_ROOT / "vendor" / "patches" / "mediacrawler"
_STATUS_SCHEMA = "YIKE_MEDIACRAWLER_STATUS_V1"
_RUNTIME_SCHEMA = "YIKE_MEDIACRAWLER_RUNTIME_V1"
_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")


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
    48: ("FAILED", "COLLECTION_PROCESS_FAILED"),
}


class Collector:
    def __init__(
        self,
        *,
        repository: Repository,
        runtime_path: Path,
        work_root: Path,
        python_executable: str | None = None,
        timeout_seconds: int = 900,
    ):
        self.repository = repository
        self.runtime_path = runtime_path.resolve()
        self.work_root = work_root.resolve()
        fixture_runtime = (_PROJECT_ROOT / "tests/fixtures/fake_mediacrawler").resolve()
        self.python_executable = python_executable or (
            sys.executable
            if self.runtime_path == fixture_runtime
            else str(self.runtime_path / ".venv" / "bin" / "python")
        )
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
        run_dir = self.work_root / request.mvp_run_id
        output_path = run_dir / request.collection_run_id
        if run_dir.is_symlink() or output_path.is_symlink():
            raise ValueError("collection output has a symlinked ancestor")
        output_dir = output_path.resolve()
        if not output_dir.is_relative_to(self.work_root):
            raise ValueError("collection identifiers escape the output root")
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
        try:
            output_dir.mkdir(parents=True)
        except OSError:
            return self._finish(
                request, "FAILED", 0, 0, "COLLECTION_OUTPUT_FAILED"
            )

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
                env={
                    **os.environ,
                    "PLAYWRIGHT_BROWSERS_PATH": str(
                        self.runtime_path / ".venv" / "playwright-browsers"
                    ),
                },
            )
        except subprocess.TimeoutExpired:
            return self._finish(
                request, "FAILED", 0, 0, "COLLECTION_PROCESS_FAILED"
            )
        except KeyboardInterrupt:
            return self._finish(request, "CANCELLED", 0, 0, "COLLECTION_CANCELLED")
        except OSError:
            return self._finish(
                request, "FAILED", 0, 0, "COLLECTION_PROCESS_FAILED"
            )

        terminal = self._runtime_terminal(output_dir, request, process.returncode)
        if terminal is None:
            return self._finish(
                request, "FAILED", 0, 0, "COLLECTION_PROCESS_FAILED"
            )
        status, error_code = terminal
        if process.returncode != 0:
            return self._finish(request, status, 0, 0, error_code)

        try:
            data_dir = self._data_dir(request, output_dir)
            contents = self._read_jsonl(data_dir, "search_contents_*.jsonl")
            comments = self._read_jsonl(data_dir, "search_comments_*.jsonl")
            self._verify_output_limits(request, contents, comments)
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
        if not main.is_file() or not _LOCK_PATH.is_file():
            return "COLLECTION_RUNTIME_MISSING"
        try:
            lock = json.loads(_LOCK_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, TypeError):
            return "COLLECTION_RUNTIME_MISMATCH"
        if (
            lock.get("schema_version") != "YIKE_MEDIACRAWLER_LOCK_V2"
            or lock.get("commit") != MEDIACRAWLER_COMMIT
            or lock.get("status_contract") != _STATUS_SCHEMA
        ):
            return "COLLECTION_RUNTIME_MISMATCH"
        fixture = lock.get("test_fixture")
        if not isinstance(fixture, dict):
            return "COLLECTION_RUNTIME_MISMATCH"
        expected_fixture = (_PROJECT_ROOT / str(fixture.get("path", ""))).resolve()
        if self.runtime_path == expected_fixture:
            if self._tree_sha256(self.runtime_path) != fixture.get("tree_sha256"):
                return "COLLECTION_RUNTIME_MISMATCH"
            return None
        if not self._verified_patched_checkout(lock):
            return "COLLECTION_RUNTIME_MISMATCH"
        return None

    def _verified_patched_checkout(self, lock: dict[str, object]) -> bool:
        marker = self.runtime_path / ".yike-runtime.json"
        if not marker.is_file() or marker.is_symlink():
            return False
        try:
            root = self._git("rev-parse", "--show-toplevel")
            head = self._git("rev-parse", "HEAD")
            changed = set(self._git("diff", "HEAD", "--name-only", "--").splitlines())
            untracked = set(
                self._git("ls-files", "--others", "--exclude-standard").splitlines()
            )
            patched_files = lock["patched_files"]
            if not isinstance(patched_files, dict):
                return False
            expected_paths = set(patched_files)
            if (
                Path(root).resolve() != self.runtime_path
                or head != MEDIACRAWLER_COMMIT
                or changed != expected_paths
                or untracked != {".yike-runtime.json"}
            ):
                return False
            actual_files = []
            for relative, expected_sha in sorted(patched_files.items()):
                unresolved_path = self.runtime_path / relative
                path = unresolved_path.resolve()
                if (
                    unresolved_path.is_symlink()
                    or not path.is_relative_to(self.runtime_path)
                    or not path.is_file()
                ):
                    return False
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
                if digest != expected_sha:
                    return False
                actual_files.append((relative, digest))
            patched_tree_sha256 = self._signature(actual_files)
            if patched_tree_sha256 != lock.get("patched_tree_sha256"):
                return False
            patches = lock["patches"]
            if not isinstance(patches, list):
                return False
            patch_entries = []
            for patch in patches:
                if not isinstance(patch, dict):
                    return False
                relative = str(patch.get("path", ""))
                unresolved_patch_path = _PROJECT_ROOT / relative
                patch_path = unresolved_patch_path.resolve()
                if (
                    unresolved_patch_path.is_symlink()
                    or not patch_path.is_relative_to(_PATCH_ROOT)
                    or not patch_path.is_file()
                ):
                    return False
                digest = hashlib.sha256(patch_path.read_bytes()).hexdigest()
                if digest != patch.get("sha256"):
                    return False
                patch_entries.append((relative, digest))
            patchset_sha256 = self._signature(patch_entries)
            if patchset_sha256 != lock.get("patchset_sha256"):
                return False
            runtime_environment = lock["runtime_environment"]
            if not isinstance(runtime_environment, dict) or not self._verified_environment(
                runtime_environment
            ):
                return False
            runtime_marker = json.loads(marker.read_text(encoding="utf-8"))
        except (OSError, KeyError, TypeError, json.JSONDecodeError, subprocess.SubprocessError):
            return False
        return runtime_marker == {
            "schema_version": _RUNTIME_SCHEMA,
            "commit": MEDIACRAWLER_COMMIT,
            "patchset_sha256": lock.get("patchset_sha256"),
            "patched_tree_sha256": patched_tree_sha256,
            "runtime_environment": runtime_environment,
        }

    def _verified_environment(self, expected: dict[str, object]) -> bool:
        required = {
            "uv_version",
            "lock_path",
            "lock_sha256",
            "manifest_path",
            "manifest_sha256",
            "python_path",
            "playwright_path",
            "browser_path",
        }
        if set(expected) != required:
            return False
        try:
            for path_key, sha_key in (
                ("lock_path", "lock_sha256"),
                ("manifest_path", "manifest_sha256"),
            ):
                unresolved = self.runtime_path / str(expected[path_key])
                resolved = unresolved.resolve()
                if (
                    unresolved.is_symlink()
                    or not resolved.is_relative_to(self.runtime_path)
                    or not resolved.is_file()
                    or hashlib.sha256(resolved.read_bytes()).hexdigest()
                    != expected[sha_key]
                ):
                    return False
            environment_root = self.runtime_path / ".venv"
            python_path = self.runtime_path / str(expected["python_path"])
            playwright_path = self.runtime_path / str(expected["playwright_path"])
            browser_path = self.runtime_path / str(expected["browser_path"])
            if (
                environment_root.is_symlink()
                or not python_path.is_file()
                or not os.access(python_path, os.X_OK)
                or not playwright_path.is_file()
                or not os.access(playwright_path, os.X_OK)
                or browser_path.is_symlink()
                or not browser_path.is_dir()
            ):
                return False
            uv_version = subprocess.run(
                ["uv", "--version"],
                check=True,
                capture_output=True,
                text=True,
                timeout=10,
            ).stdout.split()[1]
            if uv_version != expected["uv_version"]:
                return False
            subprocess.run(
                [
                    "uv",
                    "sync",
                    "--frozen",
                    "--no-dev",
                    "--no-install-project",
                    "--check",
                    "--project",
                    str(self.runtime_path),
                ],
                check=True,
                capture_output=True,
                text=True,
                timeout=60,
            )
            probe = subprocess.run(
                [
                    str(python_path),
                    "-c",
                    (
                        "from pathlib import Path; "
                        "from playwright.sync_api import sync_playwright; "
                        "p=sync_playwright().start(); "
                        "assert Path(p.chromium.executable_path).is_file(); "
                        "p.stop(); print('YIKE_RUNTIME_OK')"
                    ),
                ],
                check=True,
                capture_output=True,
                text=True,
                timeout=30,
                env={
                    **os.environ,
                    "PLAYWRIGHT_BROWSERS_PATH": str(browser_path),
                },
            )
        except (OSError, KeyError, IndexError, subprocess.SubprocessError):
            return False
        return probe.stdout.strip() == "YIKE_RUNTIME_OK"

    def _git(self, *arguments: str) -> str:
        process = subprocess.run(
            ["git", "-C", str(self.runtime_path), *arguments],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
        return process.stdout.strip()

    @staticmethod
    def _signature(entries: list[tuple[str, str]]) -> str:
        payload = json.dumps(entries, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @classmethod
    def _tree_sha256(cls, root: Path) -> str:
        entries = []
        for path in sorted(root.rglob("*")):
            if (
                not path.is_file()
                or "__pycache__" in path.parts
                or path.suffix == ".pyc"
                or path.name == ".DS_Store"
            ):
                continue
            entries.append(
                (
                    str(path.relative_to(root)),
                    hashlib.sha256(path.read_bytes()).hexdigest(),
                )
            )
        return cls._signature(entries)

    @staticmethod
    def _runtime_terminal(
        output_dir: Path, request: CollectionRequest, returncode: int
    ) -> tuple[str, str | None] | None:
        marker = output_dir / ".yike-collection-status.json"
        try:
            if marker.is_symlink() or not marker.is_file() or marker.stat().st_size > 4096:
                return None
            payload = json.loads(marker.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if set(payload) != {"schema_version", "platform", "status", "error_code"}:
            return None
        terminal = (payload["status"], payload["error_code"])
        if payload["schema_version"] != _STATUS_SCHEMA or payload["platform"] != request.platform:
            return None
        if returncode == 0:
            return terminal if terminal in {("SUCCEEDED", None), ("SUCCEEDED_NO_DATA", None)} else None
        return terminal if _EXIT_RESULTS.get(returncode) == terminal else None

    @staticmethod
    def _verify_output_limits(
        request: CollectionRequest,
        contents: list[dict[str, object]],
        comments: list[dict[str, object]],
    ) -> None:
        if len(contents) > request.max_contents:
            raise ValueError("runtime exceeded the content limit")
        source_key = "video_id" if request.platform == "bili" else "aweme_id"
        counts: dict[str, int] = {}
        for comment in comments:
            source_id = str(comment.get(source_key, ""))
            counts[source_id] = counts.get(source_id, 0) + 1
        if any(
            count > request.max_comments_per_content for count in counts.values()
        ):
            raise ValueError("runtime exceeded the comment limit")

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
        if not _SAFE_IDENTIFIER.fullmatch(request.mvp_run_id) or not _SAFE_IDENTIFIER.fullmatch(
            request.collection_run_id
        ):
            raise ValueError("collection identifier is not a safe token")
        if request.platform not in ("bili", "dy"):
            raise ValueError("platform must be bili or dy")
        if not request.query_cluster.strip() or not request.query_text.strip():
            raise ValueError("query cluster and text are required")
        if not 1 <= request.max_contents <= 10:
            raise ValueError("max contents limit must be between 1 and 10")
        if not 1 <= request.max_comments_per_content <= 50:
            raise ValueError("max comments limit must be between 1 and 50")
