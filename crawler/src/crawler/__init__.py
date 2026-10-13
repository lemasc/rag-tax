import argparse
from pathlib import Path

from .fetch import collect_links, fetch_all, raw_path
from .parse import parse_all

DATA = Path("data")


def main() -> None:
    ap = argparse.ArgumentParser(prog="crawler")
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch", help="download raw HTML for links.txt + reviewed decisions")
    p = sub.add_parser("parse", help="parse raw HTML into data/pages.jsonl")
    for sp in (f, p):
        sp.add_argument("--links", type=Path, default=Path("links.txt"))
        sp.add_argument(
            "--decisions", type=Path, default=DATA / "link_decisions.csv",
            help="review CSV; rows marked `crawl` are added to the link list (missing file = ignored)",
        )
        sp.add_argument(
            "--tier", action="append", default=[], metavar="NAME",
            help="also include `defer` rows with this tier (repeatable)",
        )
    f.add_argument("--delay", type=float, default=1.0)
    f.add_argument("--force", action="store_true")
    args = ap.parse_args()
    urls = collect_links(args.links, args.decisions, args.tier)
    print(f"{len(urls)} urls ({args.links} + {args.decisions})")

    if args.cmd == "fetch":
        fetch_all(urls, DATA / "raw", args.delay, args.force)
    else:
        recs = parse_all(urls, DATA / "raw", DATA / "pages.jsonl", raw_path)
        print(f"wrote {len(recs)} records -> {DATA / 'pages.jsonl'}")
