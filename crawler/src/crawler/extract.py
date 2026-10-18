"""Full-text extraction for the core legal set: one clean text file per kept document.

Input : data/legal_core.csv (decision = keep), data/raw/legal/*
Output: data/text/legal/<stem>.md, data/legal_text.csv (url, file, method, quality, chars, status, note);
        back-fills empty `year` in data/legal_core.csv from the extracted text.

Order : HTML -> col-main text.  PDF -> Typhoon OCR (local vLLM). pdftotext is not used: its Thai text loses sara am
        and misorders tone marks, and OCR was clearly better on all 17 documents compared (docs/plans/cleaning-open-items.md).
Pages : OCR output carries "<!-- page N -->" anchors; they are kept in the text so clean/ can record page spans.
OCR   : runs $OCR_HOME/typhoon_ocr_file.py (default ~/san/ocr) in its own venv; start the server with
        ~/san/vllm/serve_typhoon.sh start. If it is down, rows are marked needs-ocr and the run continues.
Run   : uv run python -m crawler.extract [--force] [--only STEM ...]
"""

import argparse
import csv
import os
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

import urllib3
from lxml import html as lh

from crawler.legal import DATA, RAW, TH_DIGITS, download, norm
from crawler.legal_core import MIN_QUALITY, quality, year

OUT = DATA / "text" / "legal"
OCR_RAW = RAW.parent / "ocr"  # Typhoon's per-page output, kept out of git
OCR_HOME = Path(os.environ.get("OCR_HOME", Path.home() / "san" / "ocr"))
OCR_URL = "http://127.0.0.1:8101/v1"

# Royal Gazette running header, one item per line: "หน้า 33", "เล่ม 134 ตอนที่ 12 ก", "ราชกิจจานุเบกษา".
# A volume line that also carries the publication date ("… ราชกิจจานุเบกษา 8 สิงหาคม 2559", OCR) is left for clean/gazette.py.
HEADER = re.compile(r"^\s*(หน้า\s*\d+|เล่ม\s*\d+\s*ตอน(?:(?!ราชกิจจานุเบกษา\s*\d).)*|ราชกิจจานุเบกษา)\s*$")
THAI_GAP = re.compile(r"(?<=[฀-๿]) (?=[฀-๿])")


def html_text(path: Path) -> str:
    doc = lh.fromstring(path.read_bytes())
    for bad in doc.xpath("//script|//style|//noscript"):
        bad.drop_tree()
    main = (doc.xpath('//div[contains(@class,"col-main")]') or [doc])[0]
    return "\n".join(line.strip() for line in main.text_content().splitlines())


def unspace(line: str) -> str:
    """Rejoin letter-spaced Thai ("ซึ่ ง แก้ ไ ข") only on lines where most Thai tokens are fragments."""
    tokens = [t for t in line.split(" ") if re.match(r"[฀-๿]", t)]
    if len(tokens) >= 4 and sum(len(t) <= 3 for t in tokens) / len(tokens) >= 0.5:
        return THAI_GAP.sub("", line)
    return line


def normalise(text: str) -> str:
    text = unicodedata.normalize("NFC", text)
    text = text.translate(TH_DIGITS).replace("\xa0", " ").replace("\f", "\n")
    text = re.sub(r"<!-- page \d+: OCR FAILED -->|<figure>.*?</figure>", "", text, flags=re.S)  # failed-page marks, image captions (page anchors stay)
    lines = [unspace(re.sub(r"[ \t]+", " ", l).strip()) for l in text.splitlines()]
    lines = [l for l in lines if not HEADER.match(l)]
    text = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip() + "\n"
    # pdftotext splits sara am into nikhahit + sara aa (and letter-spacing puts a gap between them): ํ + า -> ำ, after unspace
    return text.replace("ํา", "ำ")


def ocr_up() -> bool:
    try:
        return urllib3.request("GET", OCR_URL + "/models", timeout=3).status == 200
    except Exception:
        return False


def ocr(path: Path) -> str | None:
    out = OCR_RAW / path.stem / f"{path.stem}.md"
    if not out.exists():
        r = subprocess.run([str(OCR_HOME / ".venv/bin/python"), str(OCR_HOME / "typhoon_ocr_file.py"), str(path.resolve()), "-o", str(OCR_RAW.resolve())])
        if r.returncode != 0 or not out.exists():
            return None
    return out.read_text(encoding="utf-8")


def extract(row: dict, ocr_ok: bool) -> tuple[str, str, str, str]:
    """-> (text, method, status, note)"""
    path = RAW / row["file"] if row["file"] else None
    if path is None or not path.exists():
        download([row["url"]])
        from crawler.legal import raw_file

        path = raw_file(row["url"])
        if not path.exists() or not path.stat().st_size:
            return "", "", "failed", "not downloadable (rd.go.th returns HTTP 500)"
    if path.suffix == ".html":
        text = normalise(html_text(path))
        return text, "html", "ok" if quality(text) >= MIN_QUALITY else "failed", ""
    if not ocr_ok and not (OCR_RAW / path.stem / f"{path.stem}.md").exists():
        return "", "", "needs-ocr", "OCR server not running"
    md = ocr(path)
    if md is None:
        return "", "ocr", "failed", "OCR failed on some page (see data/raw/ocr)"
    text = normalise(md)
    return text, "ocr", "ok" if quality(text) >= MIN_QUALITY else "failed", ""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="re-extract rows that already have cached text")
    ap.add_argument("--only", nargs="+", metavar="STEM", help="limit --force to these file stems")
    a = ap.parse_args()

    core_path = DATA / "legal_core.csv"
    core = list(csv.DictReader(core_path.open(encoding="utf-8")))
    index_path = DATA / "legal_text.csv"
    index = {r["url"]: r for r in csv.DictReader(index_path.open(encoding="utf-8"))} if index_path.exists() else {}
    OUT.mkdir(parents=True, exist_ok=True)
    ocr_ok = ocr_up()
    if not ocr_ok:
        print(f"OCR server not reachable at {OCR_URL}: PDFs without cached OCR will be marked needs-ocr (start: ~/san/vllm/serve_typhoon.sh start)")

    for r in core:
        if r["decision"] != "keep":
            index.pop(r["url"], None)
            continue
        stem = Path(r["file"]).stem if r["file"] else norm(r["url"]).rsplit("/", 1)[-1]
        out = OUT / f"{stem}.md"
        prev = index.get(r["url"])
        if prev and prev["status"] == "ok" and out.exists() and not (a.force and (not a.only or stem in a.only)):
            text = out.read_text(encoding="utf-8")
        else:
            text, method, status, note = extract(r, ocr_ok)
            if status == "ok":
                out.write_text(text, encoding="utf-8")
            index[r["url"]] = dict(url=r["url"], file=out.name if status == "ok" else "", method=method,
                                   quality=f"{quality(text):.1f}" if text else "", chars=len(text), status=status, note=note)
            print(f"{status:9} {method:9} {len(text):7} {r['title'][:60]}", flush=True)
        if text and not r["year"]:
            r["year"] = year(r, text)

    with index_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["url", "file", "method", "quality", "chars", "status", "note"])
        w.writeheader()
        w.writerows(index[r["url"]] for r in core if r["url"] in index)
    with core_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(core[0]))
        w.writeheader()
        w.writerows(core)

    rows = list(index.values())
    from collections import Counter

    print("status:", dict(Counter(r["status"] for r in rows)), "| method:", dict(Counter(r["method"] for r in rows if r["status"] == "ok")),
          "| chars:", sum(int(r["chars"]) for r in rows if r["status"] == "ok"))
    sys.exit(0)


if __name__ == "__main__":
    main()
