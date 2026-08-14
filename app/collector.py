from dataclasses import dataclass, replace
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time
from typing import Callable, Literal

from app.collectors import normalize_bilibili, normalize_douyin
from app.normalizer import PlatformResponseChanged
from app.repository import (
    CollectionDailyLimitError,
    Repository,
    SignalIdentityConflict,
)


MEDIACRAWLER_COMMIT = "439509782cc2991c8ef7648e178d5847b0545798"
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_LOCK_PATH = _PROJECT_ROOT / "vendor" / "mediacrawler.lock"
_PATCH_ROOT = _PROJECT_ROOT / "vendor" / "patches" / "mediacrawler"
_STATUS_SCHEMA = "YIKE_MEDIACRAWLER_STATUS_V1"
_RUNTIME_SCHEMA = "YIKE_MEDIACRAWLER_RUNTIME_V1"
_BROWSER_CONTRACT = {
    "engine": "playwright-bundled-chromium",
    "launch_channel": None,
    "user_agent_mode": "playwright-default",
}
_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")


@dataclass(frozen=True)
class CollectionRequest:
    mvp_run_id: str
    collection_run_id: str
    platform: Literal["bili", "dy"]
    query_cluster: str
    query_text: str
    started_by: str
    max_contents: int = 5
    max_comments_per_content: int = 20


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


@dataclass(frozen=True)
class SupervisedProcessResult:
    returncode: int
    stdout: str
    stderr: str
    cancelled: bool = False
    timed_out: bool = False


@dataclass(frozen=True)
class _CollectionOutcome:
    status: str
    raw_count: int
    unique_count: int
    error_code: str | None
    manifest_sha256: str | None = None


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


def _stop_process_group(
    process: subprocess.Popen[str], *, terminate_grace_seconds: float
) -> tuple[str, str]:
    process_group_id = process.pid
    deadline = time.monotonic() + terminate_grace_seconds
    try:
        os.killpg(process_group_id, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        stdout, stderr = process.communicate(timeout=terminate_grace_seconds)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process_group_id, signal.SIGKILL)
        except ProcessLookupError:
            pass
        return process.communicate()
    while time.monotonic() < deadline:
        try:
            os.killpg(process_group_id, 0)
        except ProcessLookupError:
            return stdout, stderr
        time.sleep(min(0.01, max(0, deadline - time.monotonic())))
    try:
        os.killpg(process_group_id, signal.SIGKILL)
    except ProcessLookupError:
        pass
    return stdout, stderr


def run_supervised_process(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    timeout_seconds: float,
    cancel_requested: Callable[[], bool] | None = None,
    poll_interval_seconds: float = 0.1,
    terminate_grace_seconds: float = 2.0,
) -> SupervisedProcessResult:
    """Run one command in an isolated session and own its full process group."""
    process = subprocess.Popen(
        command,
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        shell=False,
        start_new_session=True,
    )
    deadline = time.monotonic() + timeout_seconds
    try:
        while True:
            if cancel_requested is not None and cancel_requested():
                stdout, stderr = _stop_process_group(
                    process, terminate_grace_seconds=terminate_grace_seconds
                )
                return SupervisedProcessResult(
                    process.returncode, stdout, stderr, cancelled=True
                )
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                stdout, stderr = _stop_process_group(
                    process, terminate_grace_seconds=terminate_grace_seconds
                )
                return SupervisedProcessResult(
                    process.returncode, stdout, stderr, timed_out=True
                )
            try:
                stdout, stderr = process.communicate(
                    timeout=min(poll_interval_seconds, remaining)
                )
            except subprocess.TimeoutExpired:
                continue
            return SupervisedProcessResult(process.returncode, stdout, stderr)
    except BaseException:
        _stop_process_group(
            process, terminate_grace_seconds=terminate_grace_seconds
        )
        raise


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
        self.work_root = work_root.absolute()
        fixture_runtime = (_PROJECT_ROOT / "tests/fixtures/fake_mediacrawler").resolve()
        self.backend = (
            "SIMULATION_ONLY"
            if self.runtime_path == fixture_runtime
            else "MEDIACRAWLER_AUTHORIZED"
        )
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
            str(output_dir.absolute()),
            "--crawler_max_notes_count",
            str(request.max_contents),
            "--max_comments_count_singlenotes",
            str(request.max_comments_per_content),
            "--max_concurrency_num",
            "1",
            "--enable_ip_proxy",
            "no",
        ]

    def collect(
        self,
        request: CollectionRequest,
        *,
        cancel_event: object | None = None,
    ) -> CollectionResult:
        self._validate_request(request)
        run_dir = self.work_root / request.mvp_run_id
        output_path = run_dir / request.collection_run_id
        self._require_contained_without_symlinks(run_dir, self.work_root)
        self._require_contained_without_symlinks(output_path, self.work_root)
        output_dir = output_path.absolute()
        if output_dir.exists():
            raise ValueError("collection output directory already exists")

        try:
            self.repository.begin_collection(
                run_id=request.mvp_run_id,
                collection_run_id=request.collection_run_id,
                platform=request.platform,
                query_cluster=request.query_cluster,
                query_text=request.query_text,
                max_contents=request.max_contents,
                max_comments_per_content=request.max_comments_per_content,
                started_by=request.started_by,
                runtime_lock_sha256=hashlib.sha256(_LOCK_PATH.read_bytes()).hexdigest(),
                backend=self.backend,
            )
        except CollectionDailyLimitError as error:
            return CollectionResult(
                mvp_run_id=request.mvp_run_id,
                collection_run_id=request.collection_run_id,
                platform=request.platform,
                status="BLOCKED_INPUT",
                raw_count=0,
                unique_count=0,
                error_code=error.code,
                output_dir=str(output_dir),
            )
        try:
            outcome = self._collect_started(
                request,
                output_dir,
                cancel_requested=(
                    getattr(cancel_event, "is_set")
                    if cancel_event is not None
                    else None
                ),
            )
        except KeyboardInterrupt:
            outcome = _CollectionOutcome(
                "CANCELLED", 0, 0, "COLLECTION_CANCELLED"
            )
        except Exception:
            outcome = _CollectionOutcome(
                "FAILED", 0, 0, "COLLECTION_PROCESS_FAILED"
            )
        return self._finish(
            request,
            outcome.status,
            outcome.raw_count,
            outcome.unique_count,
            outcome.error_code,
            outcome.manifest_sha256,
        )

    def _collect_started(
        self,
        request: CollectionRequest,
        output_dir: Path,
        *,
        cancel_requested: Callable[[], bool] | None,
    ) -> _CollectionOutcome:
        try:
            output_dir.mkdir(parents=True)
            self._require_contained_without_symlinks(output_dir, self.work_root)
        except OSError:
            return _CollectionOutcome(
                "FAILED", 0, 0, "COLLECTION_OUTPUT_FAILED"
            )

        runtime_error = self._runtime_error()
        if runtime_error:
            return _CollectionOutcome("BLOCKED_INPUT", 0, 0, runtime_error)

        try:
            self._require_contained_without_symlinks(output_dir, self.work_root)
            process = run_supervised_process(
                self.command_for(request, output_dir),
                cwd=self.runtime_path,
                env={
                    **os.environ,
                    "PLAYWRIGHT_BROWSERS_PATH": str(
                        self.runtime_path / ".venv" / "playwright-browsers"
                    ),
                },
                timeout_seconds=self.timeout_seconds,
                cancel_requested=cancel_requested,
            )
        except OSError:
            return _CollectionOutcome(
                "FAILED", 0, 0, "COLLECTION_PROCESS_FAILED"
            )
        if process.cancelled:
            return _CollectionOutcome(
                "CANCELLED", 0, 0, "COLLECTION_CANCELLED"
            )
        if process.timed_out:
            return _CollectionOutcome(
                "FAILED", 0, 0, "COLLECTION_PROCESS_FAILED"
            )

        self._require_contained_without_symlinks(output_dir, self.work_root)
        terminal = self._runtime_terminal(output_dir, request, process.returncode)
        if terminal is None:
            return _CollectionOutcome(
                "FAILED", 0, 0, "COLLECTION_PROCESS_FAILED"
            )
        status, error_code = terminal
        if process.returncode != 0:
            return _CollectionOutcome(status, 0, 0, error_code)

        try:
            data_dir = self._data_dir(request, output_dir)
            manifest_sha256 = self._manifest_sha256(output_dir)
            contents = self._read_jsonl(
                data_dir, "search_contents_*.jsonl", output_dir
            )
            comments = self._read_jsonl(
                data_dir, "search_comments_*.jsonl", output_dir
            )
            self._verify_output_limits(request, contents, comments)
            if self._manifest_sha256(output_dir) != manifest_sha256:
                raise ValueError("collector output changed while being verified")
        except (OSError, json.JSONDecodeError, ValueError):
            return _CollectionOutcome(
                "FAILED", 0, 0, "COLLECTION_PARSE_FAILED"
            )

        raw_count = len(comments)
        if not comments:
            return _CollectionOutcome(
                "SUCCEEDED_NO_DATA", 0, 0, None, manifest_sha256
            )

        try:
            normalized = self._normalize_batch(request, contents, comments)
            import_results = self.repository.import_signals(
                request.mvp_run_id, normalized
            )
            unique_count = sum(result.created for result in import_results)
        except PlatformResponseChanged:
            return _CollectionOutcome(
                "FAILED", raw_count, 0, "PLATFORM_RESPONSE_CHANGED"
            )
        except SignalIdentityConflict:
            return _CollectionOutcome(
                "FAILED", raw_count, 0, "SIGNAL_IDENTITY_CONFLICT"
            )
        except (ValueError, KeyError):
            return _CollectionOutcome(
                "FAILED", raw_count, 0, "PLATFORM_RESPONSE_CHANGED"
            )
        return _CollectionOutcome(
            "SUCCEEDED", raw_count, unique_count, None, manifest_sha256
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
                    collected_at=None,
                    envelope_sha256=hashlib.sha256(
                        json.dumps(
                            {"content": by_source[str(comment_source)], "comment": comment},
                            ensure_ascii=False,
                            sort_keys=True,
                            separators=(",", ":"),
                        ).encode("utf-8")
                    ).hexdigest(),
                    verifiable=True,
                )
            )
        return normalized

    def _read_jsonl(
        self, data_dir: Path, pattern: str, output_dir: Path
    ) -> list[dict[str, object]]:
        self._require_contained_without_symlinks(data_dir, output_dir)
        records: list[dict[str, object]] = []
        for path in sorted(data_dir.glob(pattern)):
            self._require_contained_without_symlinks(path, output_dir)
            if not path.is_file():
                raise ValueError("collector output is not a regular file")
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
            or lock.get("browser_contract") != _BROWSER_CONTRACT
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
            "browser_contract": _BROWSER_CONTRACT,
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
                        "import os; from pathlib import Path; "
                        "from playwright.sync_api import sync_playwright; "
                        "p=sync_playwright().start(); "
                        "browser_path=Path(os.environ['YIKE_BROWSER_PATH']).resolve(); "
                        "executable=Path(p.chromium.executable_path).resolve(); "
                        "assert executable.is_file() and executable.is_relative_to(browser_path.resolve()); "
                        "browser=p.chromium.launch(headless=True); "
                        "assert browser.browser_type.name == 'chromium'; "
                        "context=browser.new_context(); page=context.new_page(); "
                        "assert page.evaluate('navigator.userAgent'); "
                        "browser.close(); p.stop(); print('YIKE_RUNTIME_OK')"
                    ),
                ],
                check=True,
                capture_output=True,
                text=True,
                timeout=30,
                env={
                    **os.environ,
                    "PLAYWRIGHT_BROWSERS_PATH": str(browser_path),
                    "YIKE_BROWSER_PATH": str(browser_path),
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
        self._require_contained_without_symlinks(output_dir, self.work_root)
        manifest = []
        for path in sorted(output_dir.glob("*/jsonl/search_*.jsonl")):
            self._require_contained_without_symlinks(path, output_dir)
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
                (self.work_root / request.mvp_run_id / request.collection_run_id).absolute()
            ),
        )

    def _data_dir(self, request: CollectionRequest, output_dir: Path) -> Path:
        platform_dir = "bili" if request.platform == "bili" else "douyin"
        data_dir = output_dir / platform_dir / "jsonl"
        self._require_contained_without_symlinks(data_dir, output_dir)
        return data_dir

    @staticmethod
    def _require_contained_without_symlinks(path: Path, boundary: Path) -> None:
        candidate = path.absolute()
        root = boundary.absolute()
        if not candidate.is_relative_to(root):
            raise ValueError("collector output escaped its run directory")
        current = Path(candidate.anchor)
        for part in candidate.parts[1:]:
            current /= part
            if current.is_symlink():
                raise ValueError("collection output has a symlinked ancestor")
        if not candidate.resolve(strict=False).is_relative_to(
            root.resolve(strict=False)
        ):
            raise ValueError("collector output escaped its run directory")

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
        if not isinstance(request.started_by, str) or not request.started_by.strip():
            raise ValueError("collection started by is required")
        if not 1 <= request.max_contents <= 10:
            raise ValueError("max contents limit must be between 1 and 10")
        if not 1 <= request.max_comments_per_content <= 50:
            raise ValueError("max comments limit must be between 1 and 50")
