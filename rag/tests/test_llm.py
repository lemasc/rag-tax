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
        return "ตอบ", "m-large-2026", {"prompt_tokens": 3, "completion_tokens": 1}, "stop"

    monkeypatch.setattr(llm, "_complete", fake)
    p = llm.profile("judge", CONFIG)
    msg = [{"role": "user", "content": "ถาม"}]
    first, second = llm.chat(p, msg), llm.chat(p, msg)
    assert calls == [{"temperature": 0}]
    assert (first.cached, second.cached) == (False, True)
    assert second.text == "ตอบ" and second.model == "m-large-2026" and second.usage["prompt_tokens"] == 3
    llm.chat(p, msg, temperature=0.7)  # a per-call override is a different request
    assert calls[-1] == {"temperature": 0.7}


def _scripted(monkeypatch, tmp_path, replies):
    """chat() with `_complete` replaying (text, finish) pairs; returns the params of each call."""
    monkeypatch.setenv("A_KEY", "secret")
    monkeypatch.setattr(llm, "CACHE", tmp_path)
    seen = []

    def fake(p, messages, params, json_out):
        seen.append(params)
        text, finish = replies[len(seen) - 1]
        return text, "m", {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}, finish

    monkeypatch.setattr(llm, "_complete", fake)
    return seen


CAPPED = {"temperature": 0, "max_tokens": 100}


def test_cut_off_reply_is_asked_again_with_a_larger_cap_and_cached_under_the_original_request(monkeypatch, tmp_path):
    seen = _scripted(monkeypatch, tmp_path, [('{"a":', "length"), ('{"a": 1}', "stop")])
    p = llm.profile("judge", CONFIG)
    msg = [{"role": "user", "content": "ถาม"}]
    first = llm.chat(p, msg, max_tokens=100)
    assert [s["max_tokens"] for s in seen] == [100, 200] and first.text == '{"a": 1}' and first.finish == "stop"
    assert first.usage["prompt_tokens"] == 20 and first.usage["completion_tokens"] == 10  # both calls were paid
    again = llm.chat(p, msg, max_tokens=100)
    assert again.cached and again.text == '{"a": 1}' and len(seen) == 2


def test_reply_cut_off_twice_raises_and_is_not_cached(monkeypatch, tmp_path):
    seen = _scripted(monkeypatch, tmp_path, [("", "length"), ("{", "length"), ("", "length"), ("{", "length")])
    p = llm.profile("judge", CONFIG)
    msg = [{"role": "user", "content": "ถาม"}]
    with pytest.raises(llm.Truncated, match="cut off at 200") as e:
        llm.chat(p, msg, max_tokens=100)
    assert e.value.usage["completion_tokens"] == 10  # both calls were paid, and nothing else records them
    with pytest.raises(ValueError):  # nothing was cached, so the next call goes out again
        llm.chat(p, msg, max_tokens=100)
    assert len(seen) == 4


def test_cut_off_without_a_cap_raises_at_once(monkeypatch, tmp_path):
    seen = _scripted(monkeypatch, tmp_path, [("{", "length")])
    with pytest.raises(llm.Truncated):
        llm.chat(llm.profile("judge", CONFIG), [{"role": "user", "content": "ถาม"}])
    assert len(seen) == 1


@pytest.mark.parametrize("text", ['{"score": 4}', 'ผลคือ\n```json\n{"score": 4}\n```', 'Here: {"score": 4} done'])
def test_parse_json_finds_the_object(text):
    assert llm.parse_json(text) == {"score": 4}


def test_parse_json_fails_loudly_without_an_object():
    with pytest.raises(ValueError, match="no JSON object"):
        llm.parse_json("คะแนน 4")


def test_backend_rpm_is_shared_by_its_models_and_a_profile_rpm_is_its_own(monkeypatch):
    config = {
        "backends": {"t": {"base_url": "https://t.example/v1", "key": "k", "rpm": 190}},
        "models": {"x": {"backend": "t", "model": "m-x"}, "y": {"backend": "t", "model": "m-y", "rpm": 18}},
    }
    x, y = llm.profile("x", config), llm.profile("y", config)
    assert (x.backend_rpm, x.rpm, y.backend_rpm, y.rpm) == (190, None, 190, 18)
    spaced = []
    monkeypatch.setattr(llm, "_space", lambda key, rpm: spaced.append((key, rpm)))

    class Client:  # stands in for OpenAI(); only the throttle is under test
        def __init__(self, **kw):
            self.chat = self

        @property
        def completions(self):
            return self

        def create(self, **kw):
            raise RuntimeError("sent")

    monkeypatch.setattr("openai.OpenAI", Client)
    for p in (x, y):
        with pytest.raises(RuntimeError):
            llm._complete(p, [], {}, False)
    assert spaced == [(("t", "k"), 190), (("t", "k"), 190), (("m-y",), 18)]
