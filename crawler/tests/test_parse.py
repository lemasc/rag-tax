"""parse_page(): extraction regressions, each tied to the page that exposed it. Needs data/raw (not committed)."""

import json

import pytest

from crawler.parse import parse_page
from conftest import DATA

RAW = DATA / "raw"


def need_raw(name: str):
    if not (RAW / name).exists():
        pytest.skip("data/raw not available")


def test_60061_last_paragraph_of_item_4_is_extracted():
    # The paragraph is a bare <strong> directly inside the <div>, after the </p> that closes the answer;
    # trafilatura drops text like that unless it is wrapped in a <p> (parse._wrap_bare_inline).
    need_raw("60061.html")
    text = parse_page("https://www.rd.go.th/60061.html", (RAW / "60061.html").read_bytes())["text"]
    assert text.rstrip().endswith("ตามมาตรา 47(1)(ฌ) แห่งประมวลรัษฎากร")
    assert "ให้ผู้มีเงินได้หักลดหย่อนได้ด้วยสำหรับเงินสมทบของสามีหรือภริยา" in text


@pytest.mark.parametrize("name", ["6052.html", "61081.html", "40339.html"])
def test_page_chrome_stays_out(name):
    # 6052 ends with a bare "<< กลับ" <strong>; 61081 and 40339 carry a visitor counter. None of it is content.
    need_raw(name)
    text = parse_page(f"https://www.rd.go.th/{name}", (RAW / name).read_bytes())["text"]
    assert "<< กลับ" not in text and "ผู้เยี่ยมชม" not in text and "ผู้เข้าชม" not in text


def test_reparsing_every_raw_page_reproduces_pages_jsonl():
    need_raw("60061.html")
    stale = []
    for line in (DATA / "pages.jsonl").open(encoding="utf-8"):
        p = json.loads(line)
        name = p["url"].rsplit("/", 1)[-1]
        if parse_page(p["url"], (RAW / name).read_bytes())["text"] != p["text"]:
            stale.append(name)
    assert not stale, f"pages.jsonl is out of date for {stale}: run `uv run crawler parse`"
