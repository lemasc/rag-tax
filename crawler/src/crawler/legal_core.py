"""Core legal set: the documents the Code (ม.38–64) cites, with a keep/drop decision, year and text status.

Input : data/legal_catalog.csv, data/legal_scan.csv, data/raw/legal/*  (from crawler.legal)
Output: data/legal_core.csv  (url, decision, reason, text, year, kind, title, chars, file)

text  : ok | garbled (PDF text layer with broken font encoding: needs OCR) | missing (not downloaded)
Run   : uv run python -m crawler.legal_core
"""

import csv
import re
from collections import Counter

from crawler.legal import DATA, RAW, doc_text

# Common words of Thai tax/legal prose. Real text has >=8 per 1k chars; broken-font PDFs have 0.
COMMON = re.compile(r"ภาษี|เงินได้|ประมวลรัษฎากร|มาตรา|กรมสรรพากร|ให้|และ|ของ")
MIN_QUALITY = 5

# Content decisions that rules can't make. Keyed by URL; everything else cited is kept.
OVERRIDES = {
    "https://www.rd.go.th/2644.html": ("drop", "list of ม.47(7)(ข) charity names (122K chars): would flood retrieval, answers nothing"),
}


def quality(text: str) -> float:
    return len(COMMON.findall(text)) / max(1, len(text) / 1000)


def year(row: dict, text: str) -> str:
    """Buddhist-era year of issue: signing date in the body, else title, else the number suffix (ป.119/2545)."""
    m = re.search(r"(?:ประกาศ|ให้ไว้|สั่ง)\s*ณ\s*วันที่\s*\d{1,2}\s*\S+\s*(?:พ\.ศ\.)?\s*(2[45]\d\d)", text)
    if m:
        return m.group(1)
    title = row["title"].translate(str.maketrans("๐๑๒๓๔๕๖๗๘๙", "0123456789"))
    m = re.match(r".{0,60}?พ\.ศ\.\s*(2[45]\d\d)", title) or re.search(r"\d+\s*/\s*(2[45]\d\d)\b", title)
    return m.group(1) if m else ""


def main() -> None:
    catalog = [r for r in csv.DictReader((DATA / "legal_catalog.csv").open(encoding="utf-8")) if r["cited"] == "1"]
    scan = {r["url"]: r for r in csv.DictReader((DATA / "legal_scan.csv").open(encoding="utf-8"))}
    rows = []
    for r in catalog:
        s = scan.get(r["url"])
        text = doc_text(RAW / s["file"]) if s else ""
        status = "missing" if not s else "ok" if quality(text) >= MIN_QUALITY else "garbled"
        decision, reason = OVERRIDES.get(r["url"], ("keep", "cited by Code ม.38–64"))
        rows.append(dict(url=r["url"], decision=decision, reason=reason, text=status, year=year(r, text if status == "ok" else ""),
                         kind=r["kind"], title=r["title"], chars=len(text) if status == "ok" else "", file=s["file"] if s else ""))

    rows.sort(key=lambda r: (r["kind"], r["year"] or "9999", r["title"]))
    fields = ["url", "decision", "reason", "text", "year", "kind", "title", "chars", "file"]
    with (DATA / "legal_core.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    keep = [r for r in rows if r["decision"] == "keep"]
    print(f"{len(rows)} cited documents -> {len(keep)} keep")
    print("text  :", dict(Counter(r["text"] for r in keep)))
    print("year  :", sum(bool(r["year"]) for r in keep), "of", len(keep), "dated")
    print("chars :", sum(int(r["chars"] or 0) for r in keep), "(text=ok only)")


if __name__ == "__main__":
    main()
