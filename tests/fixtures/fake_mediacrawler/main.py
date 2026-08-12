import argparse
import json
from pathlib import Path
import sys


EXIT_BY_KEYWORD = {
    "__auth__": 40,
    "__permission__": 41,
    "__verification__": 42,
    "__rate_limit__": 43,
    "__response_changed__": 44,
    "__network__": 45,
    "__parse__": 46,
    "__cancelled__": 47,
}


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


def main():
    args = parse_args()
    output = Path(args.save_data_path)
    output.mkdir(parents=True, exist_ok=True)
    (output / "invocation.json").write_text(
        json.dumps({"count": 1, "argv": sys.argv[1:]}, ensure_ascii=False),
        encoding="utf-8",
    )
    if args.keywords in EXIT_BY_KEYWORD:
        return EXIT_BY_KEYWORD[args.keywords]
    if args.keywords == "__empty__":
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
