"""One client for every LLM backend that speaks the OpenAI chat API (OpenAI, OpenRouter, Typhoon, ThaiLLM, iApp,
Ollama). Backends and named model profiles live in rag/models.toml; API keys in .env (see .env.example).

Every call is cached on disk, keyed by base URL, model, messages and parameters, so re-running a step or re-scoring
answers costs nothing and returns the same text. The cache file also keeps the model id the backend reports and the
token usage.

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
import time
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
MODELS = Path(__file__).parent / "models.toml"
CACHE = ROOT / "rag" / "out" / "llm_cache"

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
    rpm: int | None = None


@dataclass
class Reply:
    text: str
    model: str  # as reported by the backend
    usage: dict
    cached: bool
    seconds: float


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
                   params=dict(m.get("params", {})), json_mode=b.get("json_mode", False), rpm=b.get("rpm"))


def cache_key(p: Profile, messages: list[dict], params: dict, json_out: bool) -> str:
    """Identity of a request. The key and the profile name are left out: the same request through another key or
    profile name is the same request."""
    req = dict(base_url=p.base_url, model=p.model, messages=messages, params=params, json=json_out)
    return hashlib.sha256(json.dumps(req, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


_clients: dict[tuple[str, str], object] = {}
_last_call: dict[str, float] = {}


def _complete(p: Profile, messages: list[dict], params: dict, json_out: bool) -> tuple[str, str, dict]:
    from openai import OpenAI

    client = _clients.get((p.base_url, p.api_key))
    if client is None:
        client = _clients[(p.base_url, p.api_key)] = OpenAI(base_url=p.base_url, api_key=p.api_key, max_retries=5, timeout=180)
    if p.rpm:  # simple spacing for rate-limited free APIs
        wait = _last_call.get(p.backend, 0) + 60 / p.rpm - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        _last_call[p.backend] = time.monotonic()
    extra = {"response_format": {"type": "json_object"}} if json_out and p.json_mode else {}
    r = client.chat.completions.create(model=p.model, messages=messages, **params, **extra)
    usage = r.usage.model_dump() if r.usage else {}
    return r.choices[0].message.content or "", r.model, usage


def chat(p: Profile | str, messages: list[dict], *, json_out: bool = False, use_cache: bool = True, **params) -> Reply:
    """Send a chat request. `params` override the profile's parameters for this call."""
    p = profile(p) if isinstance(p, str) else p
    params = p.params | params
    key = cache_key(p, messages, params, json_out)
    path = CACHE / key[:2] / f"{key}.json"
    if use_cache and path.exists():
        c = json.loads(path.read_text(encoding="utf-8"))
        return Reply(c["text"], c["served_model"], c["usage"], cached=True, seconds=c["seconds"])
    t = time.monotonic()
    text, served, usage = _complete(p, messages, params, json_out)
    seconds = round(time.monotonic() - t, 2)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(dict(
        profile=p.name, backend=p.backend, base_url=p.base_url, model=p.model, served_model=served, params=params,
        json=json_out, messages=messages, text=text, usage=usage, seconds=seconds, at=time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    ), ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)
    return Reply(text, served, usage, cached=False, seconds=seconds)


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
    from openai import OpenAI

    url, key = backend_endpoint(backend, config["backends"][backend])
    for m in sorted(x.id for x in OpenAI(base_url=url, api_key=key).models.list()):
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
