"""Legal-source catalogue: PIT-relevance tiering of rd.go.th statutes/instruments.

Input : data/legal_catalog.csv  (url, kind, tier, title, hub) built from the rd.go.th listing hubs
Output: data/legal_catalog.csv  (re-tiered, + reason/cited/tier_v1)  and  data/legal_scan.csv (full-text scan)

Tiers:  A = explicit personal-income-tax signal, B = generic income-tax / needs review, C = other.
Run:    uv run python -m crawler.legal
"""

import csv
import hashlib
import json
import re
import subprocess
import time
from collections import Counter
from pathlib import Path

import urllib3

DATA = Path("data")
RAW = DATA / "raw" / "legal"
CITING = ("5937", "5938", "2597")  # Code pages for ม.38–64 + rate table: what they cite is PIT by definition
INCOME_TAX_HUBS = {"19956", "26876", "49231"}  # ประกาศอธิบดี listings that are about ภาษีเงินได้ by definition
HUB_LINKS = ("6160.html",)  # listing pages that show up as "ดู…" links

STRONG = (
    r"บุคคลธรรมดา|ลดหย่อน|มาตรา\s*(40|41|42|44|45|46|47|48|49|50|51|52|53|54|55|56|57|58|59|60|61|62|63|64)\b"
    r"|ภ\.?ง\.?ด\.?\s*(90|91|94|1|2|3|1ก)|เงินได้พึงประเมิน|ผู้มีเงินได้|หัก\s*ณ\s*ที่จ่าย|เงินเดือน|ค่าจ้าง|ค่าชดเชย|เกษียณ"
    r"|กองทุนสำรองเลี้ยงชีพ|กบข|RMF|SSF|กองทุนรวม|ประกันชีวิต|เบี้ยประกัน|ดอกเบี้ย|ที่อยู่อาศัย|บริจาค|พรรคการเมือง|คนพิการ"
    r"|บิดา|มารดา|บุตร|ผู้สูงอายุ|เงินปันผล|ค่าเช่า|ให้เช่า|ค่าลิขสิทธิ์|ต่างประเทศ|รับให้|มรดก|ค่านายหน้า|ค่าทำของ"
    r"|วิชาชีพอิสระ|e-?Receipt|ช้อป|ท่องเที่ยว|สินทรัพย์ดิจิทัล|โทเคน"
)
# Added after the Code-citation check: generic procedural terms that still mean "worth a look".
GENERIC = r"ภาษีเงินได้|ยกเว้นรัษฎากร|ณ\s*ที่จ่าย|ยื่นแบบ|มาตรา\s*17|หนังสือรับรอง"
NEG = (
    r"ภาษีมูลค่าเพิ่ม|ภาษีธุรกิจเฉพาะ|อากรแสตมป์|ปิโตรเลียม|นิติบุคคล|บริษัท|มอบอำนาจ|มอบหมาย|ระบบสำหรับการปฏิบัติ"
    r"|ใบกำกับภาษี|แท่นขุดเจาะ|ส่งเสริมการลงทุน"
)
PIT = re.compile(
    r"บุคคลธรรมดา|ผู้มีเงินได้|เงินได้พึงประเมิน|ภ\.?ง\.?ด\.?\s*(90|91|94|1|3|2)\b|ลดหย่อน"
    r"|มาตรา\s*(40|41|42|44|45|46|47|48|50|51|52|56|57|59|60|61|62|63|64)\b"
)
CORP = re.compile(r"นิติบุคคล|กำไรสุทธิ|ภาษีมูลค่าเพิ่ม|ภาษีธุรกิจเฉพาะ|อากรแสตมป์")
TH_DIGITS = str.maketrans("๐๑๒๓๔๕๖๗๘๙", "0123456789")


def norm(url: str) -> str:
    return url.replace("http://", "https://").replace("://rd.go.th", "://www.rd.go.th").replace("://cmsinteradmin.rd.go.th", "://www.rd.go.th").strip()


def key(url: str) -> str:
    """Identity of a document: `…/30829`, `…/30829.html` and `…/30829.html#x` are the same."""
    return re.sub(r"\.html?$", "", norm(url).split("#")[0].rstrip("/")).lower()


def ext(url: str) -> str:
    return "pdf" if url.lower().split("?")[0].endswith(".pdf") else "html"


def raw_file(url: str) -> Path:
    return RAW / (hashlib.sha1(norm(url).encode()).hexdigest()[:12] + "." + ext(url))


def doc_text(path: Path) -> str:
    """Plain text of a downloaded PDF/HTML: Thai digits -> ASCII, justified-text letter spacing removed."""
    if path.suffix == ".pdf":
        t = subprocess.run(["pdftotext", "-layout", str(path), "-"], capture_output=True, text=True).stdout
    else:
        from lxml import html as lh

        try:
            doc = lh.fromstring(path.read_bytes())
            main = (doc.xpath('//div[contains(@class,"col-main")]') or [doc])[0]
            t = main.text_content()
        except Exception:
            t = ""
    t = t.translate(TH_DIGITS)
    return re.sub(r"(?<=[฀-๿]) (?=[฀-๿])", "", t)


def subject(text: str) -> str:
    m = re.search(r"เรื่อง\s*([^\n]{5,150})", text[:2500])
    return " ".join(m.group(1).split()) if m else ""


def title_tier(title: str) -> tuple[str, str]:
    strong = re.search(STRONG, title)
    generic = re.search(GENERIC, title)
    neg = re.search(NEG, title)
    if strong and not neg:
        return "A", f"title: {strong.group(0)}"
    if strong:
        return "B", f"title: {strong.group(0)} (+{neg.group(0)})"
    if generic:
        return "B", f"title: {generic.group(0)}"
    return "C", ""


def classify(row: dict, scan: dict | None, use_cited: bool = True) -> tuple[str, str]:
    """Final tier + reason. Order: Code citation > title signal > hub/kind floor > body-text promotion."""
    if use_cited and row.get("cited") == "1":
        return "A", "cited by Code ม.38–64"
    title = row["title"] + " " + (scan["subject"] if scan else "")
    tier, reason = title_tier(title)
    if tier != "A":
        if row["hub"] in INCOME_TAX_HUBS:
            tier, reason = "B", f"hub {row['hub']} (ภาษีเงินได้)" + (f"; {reason}" if reason else "")
        elif row["kind"] == "คำวินิจฉัย":
            tier, reason = "B", "kind: คำวินิจฉัย"
    if tier == "C" and scan and int(scan["chars"]) >= 150 and int(scan["pit"]) >= 3 and int(scan["corp"]) <= int(scan["pit"]):
        tier, reason = "B", f"body: {scan['pit']} PIT vs {scan['corp']} corp terms"
    return tier, reason


def kind_from_title(title: str) -> str:
    title = title.replace("กฤษฏีกา", "กฤษฎีกา")
    for k in ("กฎกระทรวง", "พระราชกฤษฎีกา", "คำสั่งกรมสรรพากร", "ประกาศอธิบดี", "ประกาศกระทรวงการคลัง", "ประกาศกรมสรรพากร", "คำวินิจฉัย"):
        if k in title:
            return k
    return "other"


def cited_links() -> list[dict]:
    out = []
    for line in (DATA / "pages.jsonl").read_text(encoding="utf-8").splitlines():
        d = json.loads(line)
        if d["url"].rsplit("/", 1)[-1].removesuffix(".html") in CITING:
            out += d["content_links"]
    skip = re.compile(r"^\s*(มาตรา|หมวด|บัญชี|บทบัญญัติ)")  # Code sections, not subordinate instruments
    return [l for l in out if not l["url"].endswith(HUB_LINKS) and l["title"].strip() and not skip.match(l["title"])]


def download(urls: list[str], delay: float = 0.5) -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    http = urllib3.PoolManager(headers={"User-Agent": "Mozilla/5.0 (compatible; rag-tax-crawler/0.1)"}, timeout=40, retries=urllib3.Retry(3, backoff_factor=1))
    for u in urls:
        f = raw_file(u)
        if f.exists() and f.stat().st_size:
            continue
        try:
            r = http.request("GET", norm(u))
            if r.status == 200:
                f.write_bytes(r.data)
            print(r.status, u)
        except Exception as e:
            print("error", u, e)
        time.sleep(delay)


def scan_all(rows: list[dict]) -> dict[str, dict]:
    scans = {}
    for r in rows:
        f = raw_file(r["url"])
        if not f.exists() or not f.stat().st_size:
            continue
        t = doc_text(f)
        scans[r["url"]] = dict(url=r["url"], chars=len(t), pit=len(PIT.findall(t)), corp=len(CORP.findall(t)), subject=subject(t), file=f.name)
    return scans


def main() -> None:
    path = DATA / "legal_catalog.csv"
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    nav = {"27995", "26247", "26876", "49231", "19956", "28331", "17014", "42940"}  # hub pages that leaked in as rows
    rows = [r for r in rows if r["hub"] != "cited" and key(r["url"]).rsplit("/", 1)[-1] not in nav]  # rebuilt below / not documents
    for r in rows:
        r.setdefault("tier_v1", r["tier"])  # first title-only tiering, kept for the before/after check
        r["url"] = norm(r["url"])
    known = {key(r["url"]): r for r in rows}

    # 1. Documents the Code cites for ม.38–64: flag existing rows, add the ones the hubs don't list (old HTML pages).
    cited_keys, added = set(), []
    for l in cited_links():
        k = key(l["url"])
        cited_keys.add(k)
        if k in known:
            known[k]["cited"] = "1"
        else:
            row = dict(url=norm(l["url"]), kind=kind_from_title(l["title"]), tier="C", tier_v1="", title=re.sub(r"^[\s(]*ดู|[\s)]+$", "", l["title"]).strip(), hub="cited", cited="1")
            rows.append(row)
            known[k] = row
            added.append(row)
    for r in rows:
        r.setdefault("cited", "")
    print(f"{len(cited_keys)} cited documents; {len(added)} not in the hub catalogue -> added")

    # 2. Fetch what we don't have, full-text scan everything.
    download([r["url"] for r in rows if r["cited"] == "1"])
    scans = scan_all(rows)
    # tiers depend on the scan, so fetch what newly-promoted rows are missing, then rescan
    need = [r["url"] for r in rows if r["url"] not in scans and classify(r, None)[0] != "C"]
    if need:
        download(need)
        scans = scan_all(rows)

    # 3. Re-tier. Title for empty-title คำสั่ง ("......") comes from the document's เรื่อง line.
    for r in rows:
        s = scans.get(r["url"])
        if s and s["subject"] and (len(re.sub(r"[.\s]", "", r["title"].split("|")[-1])) < 5):
            r["title"] = (r["title"] + " | " + s["subject"])[:300]
        r["tier"], r["reason"] = classify(r, s)
        r["tier_nocite"], _ = classify(r, s, use_cited=False)

    fields = ["url", "kind", "tier", "tier_v1", "reason", "cited", "title", "hub"]
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    with (DATA / "legal_scan.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["url", "chars", "pit", "corp", "subject", "file"])
        w.writeheader()
        w.writerows(scans.values())

    # 4. Check: recall of A+B on the Code-cited documents (rules only, so the citation flag doesn't make it circular).
    cited_rows = [r for r in rows if r["cited"] == "1"]
    in_hubs = [r for r in cited_rows if r["tier_v1"]]
    ab = lambda t: t in ("A", "B")
    print("\n== recall of A+B on documents cited by the Code (ม.38–64)")
    print(f"before (title rules v1), cited docs listed in hubs : {sum(ab(r['tier_v1']) for r in in_hubs)}/{len(in_hubs)}")
    print(f"after  (new rules, no citation flag), same docs    : {sum(ab(r['tier_nocite']) for r in in_hubs)}/{len(in_hubs)}")
    print(f"after  incl. old HTML pages not in hubs (rules only): {sum(ab(r['tier_nocite']) for r in cited_rows)}/{len(cited_rows)}")
    print(f"final  (with citation flag; by construction)        : {sum(ab(r['tier']) for r in cited_rows)}/{len(cited_rows)}")
    missed = [r for r in cited_rows if not ab(r["tier_nocite"])]
    for r in missed[:15]:
        print("  still missed by rules:", r["kind"], "|", r["title"][:80])
    print("\n== tier counts v1 -> now:", dict(Counter(r["tier_v1"] or "(new)" for r in rows)), "->", dict(Counter(r["tier"] for r in rows)))
    print("== reasons:", dict(Counter(r["reason"].split(":")[0].split(" (")[0] for r in rows if r["tier"] != "C")))


if __name__ == "__main__":
    main()
