"""One client for every LLM backend that speaks the OpenAI chat API (OpenAI, OpenRouter, Typhoon, ThaiLLM, iApp,
Ollama). Backends and named model profiles live in rag/models.toml; API keys in .env (see .env.example).

Every call is cached on disk, keyed by base URL, model, messages and parameters, so re-running a step or re-scoring
answers costs nothing and returns the same text. The cache file also keeps the model id the backend reports, the
token usage and why the reply ended (`finish_reason`). A reply cut off by `max_tokens` is asked again once with twice
the cap (the answer is cached under the original request, so a re-run does not pay for the cut-off call); a reply
still cut off raises `Truncated` and is not cached.

Run: uv run python -m rag.llm check                # which backends have a key and base URL
     uv run python -m rag.llm models openai        # model ids the key can see
     uv run python -m rag.llm ping judge gpt-mini  # one short Thai round trip per profile
"""

import argparse
import hashlib
import json
import os
import re
import sys
import threading
import time
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
MODELS = Path(__file__).parent / "models.toml"
CACHE = ROOT / "rag" / "out" / "llm_cache"
CAP_PARAMS = ("max_tokens", "max_completion_tokens")  # the parameter that caps a reply, whichever the backend takes
TOTALS = ("prompt_tokens", "completion_tokens", "total_tokens")
CAP_GROWTH = 2  # a cut-off reply is asked again with this many times the cap

load_dotenv(ROOT / ".env")


@dataclass(frozen=True)
class Profile:
    name: str
    backend: str
    model: str
    base_url: str
    api_key: str
    params: dict = field(default_factory=dict)
    json_mode: bool = False
    rpm: int | None = None  # this model's own limit, throttled per model
    backend_rpm: int | None = None  # the backend's limit, shared by every model on the same key


@dataclass
class Reply:
    text: str
    model: str  # as reported by the backend
    usage: dict
    cached: bool
    seconds: float
    finish: str | None = None  # finish_reason of the call; None for a cache file written before it was kept


class Truncated(ValueError):
    """The reply hit the token cap, also after asking again with a larger one. Not cached; callers that skip a bad
    reply (`except ValueError`) skip this too. `usage` is what the calls were paid for, since no cache file keeps it."""

    def __init__(self, message: str, usage: dict | None = None):
        super().__init__(message)
        self.usage = usage or {}


def read_config(path: Path = MODELS) -> dict:
    return tomllib.loads(path.read_text(encoding="utf-8"))


def backend_endpoint(name: str, b: dict) -> tuple[str, str]:
    """(base_url, api_key) of a backend; raises with the variable to set when either is missing."""
    base_url = b.get("base_url") or os.environ.get(b.get("base_url_env", ""), "")
    key = b.get("key") or os.environ.get(b.get("key_env", ""), "")
    if not base_url:
        raise SystemExit(f"backend {name}: set {b.get('base_url_env')} in .env")
    if not key:
        raise SystemExit(f"backend {name}: set {b.get('key_env')} in .env")
    return base_url.rstrip("/"), key


def profile(name: str, config: dict | None = None) -> Profile:
    config = config or read_config()
    if name not in config.get("models", {}):
        raise SystemExit(f"no profile {name!r} in models.toml; known: {', '.join(config.get('models', {}))}")
    m = config["models"][name]
    b = config["backends"][m["backend"]]
    if not m.get("model"):
        raise SystemExit(f"profile {name}: model id is empty in models.toml (list ids with `python -m rag.llm models {m['backend']}`)")
    base_url, key = backend_endpoint(m["backend"], b)
    return Profile(name=name, backend=m["backend"], model=m["model"], base_url=base_url, api_key=key,
                   params=dict(m.get("params", {})), json_mode=b.get("json_mode", False), rpm=m.get("rpm"), backend_rpm=b.get("rpm"))


def cache_key(p: Profile, messages: list[dict], params: dict, json_out: bool, attempt: int = 0) -> str:
    """Identity of a request. The key and the profile name are left out: the same request through another key or
    profile name is the same request. `attempt` > 0 is a deliberate new try of the same request (not sent to the
    backend); attempt 0 keeps the key every earlier call was cached under."""
    req = dict(base_url=p.base_url, model=p.model, messages=messages, params=params, json=json_out)
    if attempt:
        req["attempt"] = attempt
    return hashlib.sha256(json.dumps(req, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


_clients: dict[tuple[str, str], object] = {}
_last_call: dict[tuple, float] = {}
_throttle = threading.Lock()


def _space(key: tuple, rpm: int) -> None:
    """Simple spacing for rate-limited free APIs: at most `rpm` calls a minute under `key`, evenly spaced (so a
    per-second limit above rpm/60 holds too). The lock keeps parallel callers in line."""
    with _throttle:
        wait = _last_call.get(key, 0) + 60 / rpm - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        _last_call[key] = time.monotonic()


def _complete(p: Profile, messages: list[dict], params: dict, json_out: bool) -> tuple[str, str, dict, str | None]:
    from openai import OpenAI

    client = _clients.get((p.base_url, p.api_key))
    if client is None:
        client = _clients[(p.base_url, p.api_key)] = OpenAI(base_url=p.base_url, api_key=p.api_key, max_retries=5, timeout=300)  # ThaiLLM reasoning replies have taken 166 s
    if p.backend_rpm:
        _space((p.backend, p.api_key), p.backend_rpm)
    if p.rpm:
        _space((p.model,), p.rpm)
    extra = {"response_format": {"type": "json_object"}} if json_out and p.json_mode else {}
    r = client.chat.completions.create(model=p.model, messages=messages, **params, **extra)
    usage = r.usage.model_dump() if r.usage else {}
    return r.choices[0].message.content or "", r.model, usage, r.choices[0].finish_reason


def chat(p: Profile | str, messages: list[dict], *, json_out: bool = False, use_cache: bool = True, attempt: int = 0,
         **params) -> Reply:
    """Send a chat request. `params` override the profile's parameters for this call. A caller that rejects a reply
    asks again with the next `attempt`, which is cached on its own."""
    p = profile(p) if isinstance(p, str) else p
    params = p.params | params
    key = cache_key(p, messages, params, json_out, attempt)
    path = CACHE / key[:2] / f"{key}.json"
    if use_cache and path.exists():
        c = json.loads(path.read_text(encoding="utf-8"))
        return Reply(c["text"], c["served_model"], c["usage"], cached=True, seconds=c["seconds"], finish=c.get("finish_reason"))
    t = time.monotonic()
    used = params
    text, served, usage, finish = _complete(p, messages, used, json_out)
    cap_name = next((k for k in CAP_PARAMS if k in params), None)
    if finish == "length" and cap_name:
        used = params | {cap_name: params[cap_name] * CAP_GROWTH}
        print(f"llm: {p.name} cut off at {params[cap_name]} tokens, asking again with {used[cap_name]}", file=sys.stderr)
        first = usage
        text, served, usage, finish = _complete(p, messages, used, json_out)
        usage = usage | {k: first.get(k, 0) + usage.get(k, 0) for k in TOTALS}  # both calls were paid
    seconds = round(time.monotonic() - t, 2)
    if finish == "length":
        raise Truncated(f"{p.name} reply cut off at {used.get(cap_name, 'its own limit')} tokens "
                        f"(paid {usage.get('prompt_tokens', 0)} in, {usage.get('completion_tokens', 0)} out): {text[:200]!r}", usage)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(dict(
        profile=p.name, backend=p.backend, base_url=p.base_url, model=p.model, served_model=served, params=params,
        params_used=used, finish_reason=finish, json=json_out, attempt=attempt, messages=messages, text=text, usage=usage, seconds=seconds,
        at=time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    ), ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)
    return Reply(text, served, usage, cached=False, seconds=seconds, finish=finish)


JSON_BLOCK = re.compile(r"\{.*\}", re.S)


def parse_json(text: str) -> dict:
    """The JSON object in a reply. Backends without JSON mode often wrap it in prose or a ``` fence."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = JSON_BLOCK.search(text)
        if not m:
            raise ValueError(f"no JSON object in reply: {text[:200]!r}") from None
        return json.loads(m.group(0))


def chat_json(p: Profile | str, messages: list[dict], **kw) -> tuple[dict, Reply]:
    r = chat(p, messages, json_out=True, **kw)
    return parse_json(r.text), r


# ---------------------------------------------------------------- CLI


def _check(config: dict) -> None:
    for name, b in config["backends"].items():
        try:
            url, _ = backend_endpoint(name, b)
            print(f"  ok       {name:10s} {url}")
        except SystemExit as e:
            print(f"  missing  {name:10s} {e}")
    for name, m in config["models"].items():
        print(f"  profile  {name:10s} {m['backend']}/{m.get('model') or '(model id not set)'}")


def _models(config: dict, backend: str) -> None:
    import httpx

    url, key = backend_endpoint(backend, config["backends"][backend])
    r = httpx.get(f"{url}/models", headers={"Authorization": f"Bearer {key}"}, timeout=60)
    r.raise_for_status()
    body = r.json()  # OpenAI wraps the list in {"data": [...]}; Typhoon returns the bare list
    for m in sorted(x["id"] for x in (body["data"] if isinstance(body, dict) else body)):
        print(m)


def _ping(names: list[str]) -> None:
    msg = [{"role": "user", "content": "ตอบเป็นภาษาไทยสั้น ๆ หนึ่งประโยค: ภาษีเงินได้บุคคลธรรมดาคืออะไร"}]
    for name in names:
        try:
            r = chat(name, msg, use_cache=False)
            print(f"{name}: {r.model}, {r.seconds}s, {r.usage.get('prompt_tokens')}+{r.usage.get('completion_tokens')} tokens\n  {r.text.strip()[:200]}")
        except Exception as e:  # report every profile, not only the first failure
            print(f"{name}: FAILED {type(e).__name__}: {e}", file=sys.stderr)


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check")
    sub.add_parser("models").add_argument("backend")
    sub.add_parser("ping").add_argument("profiles", nargs="+")
    a = ap.parse_args()
    config = read_config()
    if a.cmd == "check":
        _check(config)
    elif a.cmd == "models":
        _models(config, a.backend)
    else:
        _ping(a.profiles)


if __name__ == "__main__":
    main()
