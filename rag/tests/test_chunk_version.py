"""rag.chunk_version: a run made with other chunks is refused for computing and named with the commit to check out."""

import json

import pytest

from rag import chunk_version


@pytest.fixture
def versions(tmp_path, monkeypatch):
    (tmp_path / "chunks.jsonl").write_text('{"chunk_id": "a#001"}\n', encoding="utf-8")
    freeze = tmp_path / "chunks_freeze.json"
    freeze.write_text(json.dumps(dict(sha256="f" * 64, corpus_commit="c0ffee0", earlier=[dict(chunks_sha="95bba22006ba", commit="482191b")])))
    monkeypatch.setattr(chunk_version, "OUT", tmp_path)
    monkeypatch.setattr(chunk_version, "FREEZE", freeze)
    return chunk_version.current()


def run(tmp_path, sha):
    d = tmp_path / "run"
    d.mkdir(exist_ok=True)
    (d / "config.json").write_text(json.dumps(dict(retrieval=dict(chunks_sha=sha))))
    return d


def test_the_current_chunks_pass(versions, tmp_path):
    assert chunk_version.problem(chunk_version.run_sha(run(tmp_path, versions)), "run x") is None
    chunk_version.require(versions, "run x")


def test_an_earlier_version_names_the_commit_to_check_out(versions):
    msg = chunk_version.problem("95bba22006ba", "run x")
    assert "95bba22006ba" in msg and versions in msg and "482191b" in msg
    with pytest.raises(SystemExit, match="482191b"):
        chunk_version.require("95bba22006ba", "run x")


def test_an_unknown_or_missing_version_says_so(versions):
    assert "No commit is recorded" in chunk_version.problem("0123456789ab", "run x")
    assert "does not record" in chunk_version.problem(None, "run x")


def test_the_checked_in_runs_resolve_to_a_commit():
    """Every run in rag/out/runs is either on the current chunks or on a version rag/chunks_freeze.json can find."""
    runs = sorted((chunk_version.OUT / "runs").glob("*/config.json"))
    if not runs or not (chunk_version.OUT / "chunks.jsonl").exists():
        pytest.skip("no runs or chunks built")
    for c in runs:
        sha = chunk_version.run_sha(c.parent)
        assert sha == chunk_version.current() or chunk_version.commit_for(sha), c.parent.name
