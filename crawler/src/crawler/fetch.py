"""Stage 1: download raw HTML for each URL in links.txt into data/raw/."""

import hashlib
import time
from pathlib import Path

import urllib3

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; rag-tax-crawler/0.1)"}


def raw_path(raw_dir: Path, url: str) -> Path:
    """Stable file name from the URL: `548.html` -> `548.html`, else a hash."""
    name = url.rstrip("/").rsplit("/", 1)[-1]
    if name.endswith(".html") and name[:-5].isdigit():
        return raw_dir / name
    return raw_dir / f"{hashlib.sha1(url.encode()).hexdigest()[:12]}.html"


def read_links(path: Path) -> list[str]:
    seen: dict[str, None] = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            seen.setdefault(line)
    return list(seen)


def fetch_all(links: Path, raw_dir: Path, delay: float = 1.0, force: bool = False) -> list[dict]:
    raw_dir.mkdir(parents=True, exist_ok=True)
    http = urllib3.PoolManager(headers=HEADERS, timeout=30, retries=urllib3.Retry(3, backoff_factor=1))
    results = []
    for url in read_links(links):
        dest = raw_path(raw_dir, url)
        if dest.exists() and not force:
            results.append({"url": url, "status": "cached", "file": dest.name})
            continue
        try:
            resp = http.request("GET", url)
            if resp.status == 200:
                dest.write_bytes(resp.data)
            results.append({"url": url, "status": resp.status, "file": dest.name})
        except Exception as e:  # keep going; report at the end
            results.append({"url": url, "status": f"error: {e}", "file": dest.name})
        print(results[-1]["status"], url)
        time.sleep(delay)
    return results
