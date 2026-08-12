import argparse
import json
from pathlib import Path
import sys


RESULT_BY_KEYWORD = {
    "__auth__": (40, "BLOCKED_INPUT", "PLATFORM_AUTH_REQUIRED"),
    "__permission__": (41, "BLOCKED_INPUT", "PLATFORM_PERMISSION_DENIED"),
    "__verification__": (42, "BLOCKED_INPUT", "PLATFORM_VERIFICATION_REQUIRED"),
    "__rate_limit__": (43, "BLOCKED_INPUT", "PLATFORM_RATE_LIMITED"),
    "__response_changed__": (44, "FAILED", "PLATFORM_RESPONSE_CHANGED"),
    "__network__": (45, "FAILED", "COLLECTION_NETWORK_FAILED"),
    "__parse__": (46, "FAILED", "COLLECTION_PARSE_FAILED"),
    "__cancelled__": (47, "CANCELLED", "COLLECTION_CANCELLED"),
}

STATUS_SCHEMA = "YIKE_MEDIACRAWLER_STATUS_V1"


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--platform", required=True)
    parser.add_argument("--lt", required=True)
    parser.add_argument("--type", required=True)
    parser.add_argument("--keywords", required=True)
    parser.add_argument("--get_comment", required=True)
    parser.add_argument("--get_sub_comment", required=True)
    parser.add_argument("--headless", required=True)
    parser.add_argument("--save_data_option", required=True)
    parser.add_argument("--save_data_path", required=True)
    parser.add_argument("--crawler_max_notes_count", required=True)
    parser.add_argument("--max_comments_count_singlenotes", required=True)
    parser.add_argument("--max_concurrency_num", required=True)
    parser.add_argument("--enable_ip_proxy", required=True)
    return parser.parse_args()


def write_jsonl(path, records):
    with path.open("w", encoding="utf-8") as target:
        for record in records:
            target.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")))
            target.write("\n")


def write_status(output, platform, status, error_code):
    target = output / ".yike-collection-status.json"
    temporary = target.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(
            {
                "schema_version": STATUS_SCHEMA,
                "platform": platform,
                "status": status,
                "error_code": error_code,
            },
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )
    temporary.replace(target)


def main():
    args = parse_args()
    output = Path(args.save_data_path)
    output.mkdir(parents=True, exist_ok=True)
    (output / "invocation.json").write_text(
        json.dumps({"count": 1, "argv": sys.argv[1:]}, ensure_ascii=False),
        encoding="utf-8",
    )
    if args.keywords == "__exit_only_verification__":
        return 42
    if args.keywords in RESULT_BY_KEYWORD:
        exit_code, status, error_code = RESULT_BY_KEYWORD[args.keywords]
        write_status(output, args.platform, status, error_code)
        return exit_code
    if args.keywords == "__empty__":
        write_status(output, args.platform, "SUCCEEDED_NO_DATA", None)
        return 0

    fixture_path = Path(__file__).resolve().parent.parent / args.platform / "comments.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    comments = list(fixture["comments"])
    if args.keywords == "__partial_invalid__":
        invalid = dict(comments[0])
        invalid["comment_id"] = "invalid-comment"
        invalid["content"] = ""
        comments.append(invalid)
    data_dir = output / ("bili" if args.platform == "bili" else "douyin") / "jsonl"
    data_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(data_dir / "search_contents_fixture.jsonl", fixture["contents"])
    write_jsonl(data_dir / "search_comments_fixture.jsonl", comments)
    if args.keywords != "__missing_status__":
        write_status(output, args.platform, "SUCCEEDED", None)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
