"""Stage 2: turn raw HTML into structured records (content + related links)."""

import json
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urldefrag, urljoin

import trafilatura
from lxml import html as lh

BASE = "https://www.rd.go.th/"


def _links(root, base: str) -> list[dict]:
    out, seen = [], set()
    for a in root.iter("a"):
        href = (a.get("href") or "").strip()
        if not href or href.startswith(("javascript:", "mailto:", "tel:", "#")):
            continue
        url = urldefrag(urljoin(base, href))[0]
        if url in seen:
            continue
        seen.add(url)
        title = " ".join((a.get("title") or a.text_content()).split())
        out.append({"url": url, "title": title})
    return out


def parse_page(url: str, raw: bytes) -> dict:
    doc = lh.fromstring(raw)
    first = lambda xp: (doc.xpath(xp) or [None])[0]

    side = first('//div[contains(@class,"col-side")]')
    main = first('//div[contains(@class,"col-main")]')
    crumbs = first('//div[contains(@class,"content-breadcrumb")]')
    updated = first('//div[contains(@class,"page-lastupdate")]')

    # Content: run trafilatura on the main column only (sidebar/nav excluded).
    # Trafilatura returns nothing for a bare <div> fragment, so wrap it as a document.
    text = None
    if main is not None:
        wrapped = f"<html><body><article>{lh.tostring(main, encoding='unicode')}</article></body></html>"
        text = trafilatura.extract(
            wrapped, url=url, favor_recall=True, include_tables=True,
            include_links=False, output_format="txt",
        )

    title = " ".join(doc.xpath("string(//title)").split()).split("|")[0].strip()
    heading = " ".join(main.xpath("string(.//h1|.//h2|.//h3)").split()) if main is not None else ""
    heading = heading or title  # some pages have no <h*>; the <title> is the same text
    last_update = None
    if updated is not None:
        m = re.search(r"\d{2}-\d{2}-\d{4}", updated.text_content())
        last_update = m.group(0) if m else None

    content_links = _links(main, url) if main is not None else []
    return {
        "url": url,
        "title": title,
        "heading": heading,
        "breadcrumb": [l["title"] for l in _links(crumbs, url)[1:]] if crumbs is not None else [],
        "last_update": last_update,  # dd-mm-yyyy (Buddhist/Gregorian as published)
        "text": text,
        "content_links": content_links,  # links inside the article body (e.g. index pages)
        "related_links": _links(side, url) if side is not None else [],  # sidebar; NOT crawled yet
    }


def parse_all(links: list[str], raw_dir: Path, out: Path, raw_path) -> list[dict]:
    records = []
    for url in links:
        p = raw_path(raw_dir, url)
        if not p.exists():
            print("missing raw", url)
            continue
        rec = parse_page(url, p.read_bytes())
        # Download time = raw file mtime (fetch writes it once; --force refreshes it).
        rec["fetched_at"] = datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec="seconds")
        records.append(rec)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return records
