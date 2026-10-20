"""rag.llm without network: profile resolution, cache identity, cache hits, JSON extraction."""

import pytest

from rag import llm

CONFIG = {
    "backends": {
        "a": {"base_url": "https://a.example/v1/", "key_env": "A_KEY", "json_mode": True},
        "b": {"base_url_env": "B_URL", "key": "fixed"},
    },
    "models": {
        "judge": {"backend": "a", "model": "m-large", "params": {"temperature": 0}},
        "nomodel": {"backend": "a", "model": ""},
        "local": {"backend": "b", "model": "m-small"},
    },
}


def test_profile_reads_key_and_url_from_the_environment(monkeypatch):
    monkeypatch.setenv("A_KEY", "secret")
    p = llm.profile("judge", CONFIG)
    assert (p.base_url, p.api_key, p.model, p.params, p.json_mode) == ("https://a.example/v1", "secret", "m-large", {"temperature": 0}, True)


def test_missing_settings_name_what_to_set(monkeypatch):
    monkeypatch.delenv("A_KEY", raising=False)
    monkeypatch.delenv("B_URL", raising=False)
    with pytest.raises(SystemExit, match="A_KEY"):
        llm.profile("judge", CONFIG)
    with pytest.raises(SystemExit, match="B_URL"):
        llm.profile("local", CONFIG)
    monkeypatch.setenv("A_KEY", "secret")
    with pytest.raises(SystemExit, match="model id is empty"):
        llm.profile("nomodel", CONFIG)
    with pytest.raises(SystemExit, match="no profile"):
        llm.profile("nope", CONFIG)


def test_cache_key_ignores_the_api_key_but_not_the_request(monkeypatch):
    monkeypatch.setenv("A_KEY", "one")
    p1 = llm.profile("judge", CONFIG)
    monkeypatch.setenv("A_KEY", "two")
    p2 = llm.profile("judge", CONFIG)
    msg = [{"role": "user", "content": "ภาษี"}]
    assert llm.cache_key(p1, msg, {}, False) == llm.cache_key(p2, msg, {}, False)
    assert llm.cache_key(p1, msg, {}, False) != llm.cache_key(p1, msg, {"temperature": 0}, False)
    assert llm.cache_key(p1, msg, {}, False) != llm.cache_key(p1, msg, {}, True)


def test_second_identical_call_is_served_from_the_cache(monkeypatch, tmp_path):
    monkeypatch.setenv("A_KEY", "secret")
    monkeypatch.setattr(llm, "CACHE", tmp_path)
    calls = []

    def fake(p, messages, params, json_out):
        calls.append(params)
        return "ตอบ", "m-large-2026", {"prompt_tokens": 3, "completion_tokens": 1}

    monkeypatch.setattr(llm, "_complete", fake)
    p = llm.profile("judge", CONFIG)
    msg = [{"role": "user", "content": "ถาม"}]
    first, second = llm.chat(p, msg), llm.chat(p, msg)
    assert calls == [{"temperature": 0}]
    assert (first.cached, second.cached) == (False, True)
    assert second.text == "ตอบ" and second.model == "m-large-2026" and second.usage["prompt_tokens"] == 3
    llm.chat(p, msg, temperature=0.7)  # a per-call override is a different request
    assert calls[-1] == {"temperature": 0.7}


@pytest.mark.parametrize("text", ['{"score": 4}', 'ผลคือ\n```json\n{"score": 4}\n```', 'Here: {"score": 4} done'])
def test_parse_json_finds_the_object(text):
    assert llm.parse_json(text) == {"score": 4}


def test_parse_json_fails_loudly_without_an_object():
    with pytest.raises(ValueError, match="no JSON object"):
        llm.parse_json("คะแนน 4")
