import json
from pathlib import Path

import pytest

from crawler.clean.text import normalize

DATA = Path(__file__).parent.parent / "data"


@pytest.fixture(scope="session")
def pages() -> dict[str, dict]:
    """First-pass pages keyed by page id ("5937"); text is the raw trafilatura output."""
    path = DATA / "pages.jsonl"
    if not path.exists():
        pytest.skip("data/pages.jsonl not available")
    recs = (json.loads(line) for line in path.open(encoding="utf-8"))
    return {r["url"].rsplit("/", 1)[-1].removesuffix(".html"): r for r in recs}


@pytest.fixture(scope="session")
def page_text(pages):
    """Normalised text of a page by id."""
    return lambda pid: normalize(pages[pid]["text"])
