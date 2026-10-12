import argparse
from pathlib import Path

from .fetch import fetch_all, raw_path, read_links
from .parse import parse_all

DATA = Path("data")


def main() -> None:
    ap = argparse.ArgumentParser(prog="crawler")
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch", help="download raw HTML for links.txt")
    f.add_argument("--links", type=Path, default=Path("links.txt"))
    f.add_argument("--delay", type=float, default=1.0)
    f.add_argument("--force", action="store_true")
    p = sub.add_parser("parse", help="parse raw HTML into data/pages.jsonl")
    p.add_argument("--links", type=Path, default=Path("links.txt"))
    args = ap.parse_args()

    if args.cmd == "fetch":
        fetch_all(args.links, DATA / "raw", args.delay, args.force)
    else:
        recs = parse_all(read_links(args.links), DATA / "raw", DATA / "pages.jsonl", raw_path)
        print(f"wrote {len(recs)} records -> {DATA / 'pages.jsonl'}")
