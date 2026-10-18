"""Content images of HTML pages: find them, fetch them, OCR them, and record which ones become documents.

Some pages carry text only as a picture (a poster, an infographic, a table screenshot). Nothing here runs as part of
`extract` or `clean.build`: fetching and OCR are explicit, and an image only enters the corpus when
`data/image_decisions.csv` says `keep` for it (the review notebook `notebooks/image_review.py` writes that file).

Input : data/pages.jsonl, data/raw/<page id>.html (the `col-main` block), data/clean/documents.jsonl (overlap check)
Output: data/image_index.csv       (image_id, page_id, url, file, width, height, alt, bytes), rewritten on every run
        data/raw/img/<file>        the downloaded images (not in git)
        data/raw/ocr/<image_id>/   Typhoon OCR output, same cache as the PDFs
        data/image_decisions.csv   (image_id, decision keep|drop, title, note, decided_at, source ocr|manual, verified), by hand or notebook
        data/text/image/<id>.md    text of every image decided `keep` (in git, so clean.build needs no OCR cache): the OCR text,
                                   or for `source = manual` a hand-corrected file that export never overwrites

Some images (infographics, tables without ruled lines) defeat OCR in ways no setting fixes. For those the text is corrected
by hand: write data/text/image/<id>.md, set `source` to `manual`, and set `verified` to the date a person compared the text
with the image. `verified` empty on a kept image means nobody has done that comparison yet.
Run   : uv run python -m crawler.images                 list the images and fetch the missing ones
        uv run python -m crawler.images --ocr [ID ...]  OCR these images (default: every image not decided `drop`)
`image_id` is the file stem: `<page id>_<position among the page's images>_<name in the URL>`.
"""

import argparse
import csv
import json
import re
import sys
import urllib.parse
from pathlib import Path

import urllib3
from lxml import html as lh

from crawler.clean.text import normalize
from crawler.extract import OCR_RAW, OCR_URL, ocr, ocr_up
from crawler.legal import DATA, RAW as RAW_LEGAL

RAW = RAW_LEGAL.parent  # data/raw
IMG = RAW / "img"
TEXT = DATA / "text" / "image"
INDEX = DATA / "image_index.csv"
DECISIONS = DATA / "image_decisions.csv"
INDEX_FIELDS = ["image_id", "page_id", "url", "file", "width", "height", "alt", "bytes"]
DECISION_FIELDS = ["image_id", "decision", "title", "note", "decided_at", "source", "verified"]
SKIP = ("counter.php", "hits.php")  # visit counters, not content
MIN_BYTES = 1000


def discover() -> list[dict]:
    """The `<img>` elements inside `col-main` of every page in pages.jsonl, minus visit counters."""
    rows = []
    for line in (DATA / "pages.jsonl").open(encoding="utf-8"):
        page = json.loads(line)
        page_id = page["url"].rsplit("/", 1)[-1].removesuffix(".html")
        raw = RAW / f"{page_id}.html"
        if not raw.exists():
            continue
        main = lh.fromstring(raw.read_bytes()).xpath('//div[contains(@class,"col-main")]')
        for i, img in enumerate(main[0].xpath(".//img") if main else []):
            src = img.get("src") or ""
            if not src or any(s in src for s in SKIP):
                continue
            url = urllib.parse.urljoin(page["url"], src)
            name = Path(urllib.parse.urlparse(url).path).name
            rows.append(dict(
                image_id=Path(f"{page_id}_{i}_{name}").stem, page_id=page_id, url=url, file=f"{page_id}_{i}_{name}",
                width=img.get("width") or "", height=img.get("height") or "", alt=(img.get("alt") or "").strip(), bytes="",
            ))
    return rows


def fetch(rows: list[dict]) -> None:
    """Download the images that are not on disk yet; fill in `bytes`. A failed download leaves `bytes` empty."""
    IMG.mkdir(parents=True, exist_ok=True)
    http = urllib3.PoolManager()
    for r in rows:
        path = IMG / r["file"]
        if not path.exists():
            resp = http.request("GET", r["url"], timeout=20)
            if resp.status != 200 or len(resp.data) < MIN_BYTES:
                print(f"skip {resp.status} {r['url']} ({len(resp.data)} bytes)", file=sys.stderr)
                continue
            path.write_bytes(resp.data)
        r["bytes"] = path.stat().st_size


def load_index() -> list[dict]:
    return list(csv.DictReader(INDEX.open(encoding="utf-8"))) if INDEX.exists() else []


def save_index(rows: list[dict]) -> None:
    with INDEX.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=INDEX_FIELDS)
        w.writeheader()
        w.writerows(rows)


def load_decisions() -> dict[str, dict]:
    if not DECISIONS.exists():
        return {}
    return {r["image_id"]: {"source": "ocr", "verified": "", **r} for r in csv.DictReader(DECISIONS.open(encoding="utf-8"))}


def save_decisions(decisions: dict[str, dict]) -> None:
    """Rewrite the decisions file. Written to a temporary file first, so a failure leaves the old file as it was
    (a long-running notebook can hold an older version of this module, and a half-written file lost two rows once)."""
    rows = sorted(({"source": "ocr", "verified": "", **r} for r in decisions.values()), key=lambda r: r["image_id"])
    tmp = DECISIONS.with_suffix(".csv.tmp")
    try:
        with tmp.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=DECISION_FIELDS)
            w.writeheader()
            w.writerows(rows)
        tmp.replace(DECISIONS)
    finally:
        tmp.unlink(missing_ok=True)


def ocr_path(image_id: str) -> Path:
    return OCR_RAW / image_id / f"{image_id}.md"


def ocr_text(image_id: str) -> str | None:
    """Cleaned OCR text for the image, or None when it has not been OCR'd. Page anchors and figure captions are dropped."""
    path = ocr_path(image_id)
    if not path.exists():
        return None
    text = re.sub(r"<!-- page \d+(: OCR FAILED)? -->|<figure>.*?</figure>", "", path.read_text(encoding="utf-8"), flags=re.S)
    return normalize(text)


def export_kept() -> list[str]:
    """Write the OCR text of every image decided `keep` to data/text/image/. Returns the ids written.

    Images with `source = manual` are skipped: their file is the hand-corrected text and must not be overwritten.
    """
    TEXT.mkdir(parents=True, exist_ok=True)
    done = []
    for image_id, d in load_decisions().items():
        text = ocr_text(image_id) if d["decision"] == "keep" and d["source"] != "manual" else None
        if text:
            (TEXT / f"{image_id}.md").write_text(text + "\n", encoding="utf-8")
            done.append(image_id)
    return done


# --- overlap with the text we already have --------------------------------------------------------------------------

K = 6  # characters per shingle


def squash(text: str) -> str:
    """Thai letters, Latin letters and digits only: markup, punctuation and whitespace differ between OCR and source."""
    return re.sub(r"[^ก-๙a-zA-Z0-9]", "", re.sub(r"<[^>]+>", "", normalize(text)))


def shingles(text: str, k: int = K) -> set[str]:
    s = squash(text)
    return {s[i : i + k] for i in range(len(s) - k + 1)}


def corpus_shingles() -> dict[str, set[str]]:
    """Shingle set per document of the clean corpus (image documents excluded), keyed by doc_id."""
    path = DATA / "clean" / "documents.jsonl"
    docs = (json.loads(line) for line in path.open(encoding="utf-8"))
    return {d["doc_id"]: shingles(d["text"]) for d in docs if d["source"] != "image"}


def overlap(text: str, corpus: dict[str, set[str]], page_id: str | None = None) -> dict:
    """How much of `text` is already in the corpus.

    `page` is the share of the text's shingles found in its own page, `corpus` the share found anywhere, `best` the five
    documents covering most of it. Exact-shingle matching survives OCR's punctuation and spacing but not its misreadings,
    so read a low number as "probably new or misread", not as proof.
    """
    own = shingles(text)
    if not own:
        return dict(n=0, page=0.0, corpus=0.0, best=[])
    union = set().union(*corpus.values())
    per_doc = sorted(((len(own & s) / len(own), d) for d, s in corpus.items()), reverse=True)[:5]
    return dict(
        n=len(own), page=len(own & corpus.get(page_id, set())) / len(own) if page_id else 0.0,
        corpus=len(own & union) / len(own), best=[(d, round(f, 3)) for f, d in per_doc],
    )


def unmatched_lines(text: str, corpus: dict[str, set[str]], threshold: float = 0.5) -> list[str]:
    """Lines of `text` (length >= 2 shingles) whose shingles are mostly absent from the corpus: the likely new content."""
    union = set().union(*corpus.values())
    out = []
    for line in text.split("\n"):
        sh = shingles(line)
        if len(sh) >= 2 and len(sh & union) / len(sh) < threshold:
            out.append(line.strip())
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ocr", nargs="*", metavar="ID", help="OCR these image ids; no ids = every image not decided `drop`")
    a = ap.parse_args()

    rows = discover()
    fetch(rows)
    save_index(rows)
    decisions = load_decisions()
    if a.ocr is not None:
        if not ocr_up():
            sys.exit(f"OCR server not reachable at {OCR_URL} (start: ~/san/vllm/serve_typhoon.sh start)")
        ids = a.ocr or [r["image_id"] for r in rows if decisions.get(r["image_id"], {}).get("decision") != "drop"]
        files = {r["image_id"]: IMG / r["file"] for r in rows}
        for image_id in ids:
            if image_id not in files or not files[image_id].exists():
                print(f"unknown or missing image: {image_id}", file=sys.stderr)
            elif ocr_path(image_id).exists():
                print(f"cached  {image_id}")
            else:
                print(f"{'ok' if ocr(files[image_id]) is not None else 'FAILED':7} {image_id}", flush=True)
    exported = export_kept()
    kept = [i for i, d in decisions.items() if d["decision"] == "keep" and d["source"] != "manual"]
    if set(kept) - set(exported):
        print(f"kept but not OCR'd yet, so no text exported: {sorted(set(kept) - set(exported))} (run with --ocr)", file=sys.stderr)
    print(f"{'image_id':58} {'size':>9} {'decision':8} ocr")
    for r in rows:
        print(f"{r['image_id'][:58]:58} {r['width'] or '?':>4}x{r['height'] or '?':<4} {decisions.get(r['image_id'], {}).get('decision', '-'):8} "
              f"{'yes' if ocr_path(r['image_id']).exists() else '-'}")
    print(f"{len(rows)} images on {len({r['page_id'] for r in rows})} pages; {sum(1 for r in rows if r['bytes'])} on disk; "
          f"{sum(1 for d in decisions.values() if d['decision'] == 'keep')} kept "
          f"({sum(1 for d in decisions.values() if d['decision'] == 'keep' and not d['verified'])} not verified), "
          f"{sum(1 for d in decisions.values() if d['decision'] == 'drop')} dropped")


if __name__ == "__main__":
    main()
