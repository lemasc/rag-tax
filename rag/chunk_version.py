"""Which chunk table a saved run was made with, and what a tool does when it is not the one in rag/out.

Rebuilding chunks.jsonl changes chunk ids and text, so a run, a judgment pool or a label made with one version is read
wrongly against another, often without an error: an id that still exists can hold other text. Every run records the
version it retrieved from (`retrieval.chunks_sha` in its config.json, by rag.answer). Tools that compute from a run
(scoring, judging) stop on a mismatch; viewers open the run read-only with a warning and save nothing. To work with an
older run, check out the codebase at a commit that has its chunks: rag/chunks_freeze.json lists the versions.
"""

import hashlib
import json
from pathlib import Path

from rag.chunk import OUT

FREEZE = Path(__file__).parent / "chunks_freeze.json"
SHA_CHARS = 12  # as rag.answer.file_sha records it


def current() -> str:
    return hashlib.sha256((OUT / "chunks.jsonl").read_bytes()).hexdigest()[:SHA_CHARS]


def run_sha(run_dir: Path) -> str | None:
    """The chunk version a run in rag/out/runs/ retrieved from, None if its config does not say."""
    config = json.loads((run_dir / "config.json").read_text(encoding="utf-8"))
    return config.get("retrieval", {}).get("chunks_sha")


def commit_for(sha: str) -> str | None:
    """A commit whose checkout has that chunk version, from the `earlier` list of rag/chunks_freeze.json (the frozen
    version itself is the one checked in; it moves to `earlier`, with its commit, when the chunks are frozen again)."""
    freeze = json.loads(FREEZE.read_text(encoding="utf-8"))
    return next((v["commit"] for v in freeze.get("earlier", []) if v["chunks_sha"] == sha), None)


def problem(sha: str | None, what: str) -> str | None:
    """None when `what` was made with the current chunks, else a message saying what differs and what to check out."""
    now = current()
    if sha == now:
        return None
    if sha is None:
        return f"{what} does not record which chunks it was made with; rag/out/chunks.jsonl is {now}."
    where = commit_for(sha)
    return (f"{what} was made with chunks {sha}, but rag/out/chunks.jsonl is {now}: chunk ids and text differ, so it "
            f"would be read wrongly. "
            + (f"Check out commit {where} (the whole codebase), then run `python -m rag.index`, to work with it."
               if where else "No commit is recorded for that version in rag/chunks_freeze.json."))


def require(sha: str | None, what: str) -> None:
    """For tools that compute from a run: stop on a mismatch."""
    if msg := problem(sha, what):
        raise SystemExit(msg)


def placeholder(chunk_id: str) -> dict:
    """What a viewer shows for a chunk the current table does not have."""
    return dict(chunk_id=chunk_id, header=f"({chunk_id}: not in the current chunks.jsonl)", text="", kind="", title="",
                url="", doc_id="", source="", tax_year=None, year=None, flags=[])
