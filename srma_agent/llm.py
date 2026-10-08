"""Structured JSON calls to the clinical model.

Small quantized models are good at judgement and bad at formatting. Asked
for JSON they routinely wrap it in markdown fences, prepend "Here is the
JSON:", emit trailing commas, or use single quotes.

Rather than scatter defensive parsing across the screening and extraction
modules, all of it lives here. Callers get a validated pydantic object or a
clear error.

WHY THIS TALKS TO OLLAMA DIRECTLY INSTEAD OF THROUGH LITELLM

LiteLLM was the original transport. It reported
`APIConnectionError: [Errno 111] Connection refused` against an Ollama
daemon that a plain `requests.post` reached successfully from the same
process, in the same second. Debugging someone else's HTTP abstraction is
not a good use of a project whose correctness matters, and the Ollama API
is a single POST. LiteLLM is retained only for non-Ollama providers.

The direct path also unlocks Ollama's schema-constrained decoding: passing
the JSON Schema in `format` makes the sampler physically unable to emit
invalid JSON, which is strictly better than generating freely and repairing
afterwards. The repair code below is kept as a fallback for providers that
have no such feature.

WHY THIS BYPASSES ADK AGENTS

Screening iterates over hundreds of abstracts with an identical prompt,
which is a loop, not a conversation. Running it as a plain loop makes it
testable, resumable and free of agent overhead.
"""

from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import sys
import threading
import time
from urllib.parse import urlparse
from typing import Any, TypeVar

import requests
from pydantic import BaseModel, ValidationError

from . import config

T = TypeVar("T", bound=BaseModel)

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)
_TRAILING_COMMA_RE = re.compile(r",\s*([}\]])")

# Ollama loads the model on the first call and keeps it resident. A 4B
# model on CPU answers a screening prompt in roughly 10-40s, so the timeout
# has to be generous or correct answers get thrown away as failures.
_OLLAMA_TIMEOUT = 300

# The Vertex chatCompletions format requires an explicit max_tokens, and it
# is a hard cut-off: generation stops mid-string when it is reached. The
# hosted MedGemma spends 400-1200 tokens on a "<unused94>thought" preamble
# before the answer, and the StudyExtraction JSON (RoB 2 rationales,
# evidence quotes) is another 800-1500. At 2048 roughly half of all
# extractions were truncated inside the JSON (run-20261007-093214: 129/241
# failed with "Unterminated string"). 8192 is a ceiling, not a target - the
# model still stops at the closing brace - so it costs nothing on short
# replies and only matters on the long ones that used to be cut.
_VERTEX_DEFAULT_MAX_TOKENS = 8192


class LlmCallError(RuntimeError):
    """Raised when the model could not produce usable structured output."""


def _extract_json(text: str) -> str:
    """Pull a JSON object out of whatever the model actually returned."""
    if not text:
        raise LlmCallError("Model returned empty output")

    # Markdown code fence is the most common wrapper.
    fenced = _FENCE_RE.search(text)
    if fenced:
        text = fenced.group(1)

    # Otherwise take the outermost balanced braces, skipping any prose.
    start = text.find("{")
    if start == -1:
        raise LlmCallError(f"No JSON object in output: {text[:200]}")

    depth, in_string, escaped = 0, False, False
    for i, ch in enumerate(text[start:], start):
        if escaped:
            escaped = False
            continue
        if ch == "\\":
            escaped = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]

    # Unbalanced: return the remainder and let the repair pass try.
    return text[start:]


def _repair(raw: str) -> str:
    """Fix the malformations small models produce most often."""
    fixed = _TRAILING_COMMA_RE.sub(r"\1", raw)
    # Python literals leaking into JSON.
    fixed = re.sub(r"\bNone\b", "null", fixed)
    fixed = re.sub(r"\bTrue\b", "true", fixed)
    fixed = re.sub(r"\bFalse\b", "false", fixed)
    return fixed


# --------------------------------------------------------------------------
# Transport
# --------------------------------------------------------------------------


def _is_ollama(model: str) -> bool:
    return model.startswith("ollama")


def _is_vertex(model: str) -> bool:
    return model.startswith("vertex")


def _ollama_model_name(model: str) -> str:
    """Strip the LiteLLM-style provider prefix Ollama does not use."""
    return model.split("/", 1)[1] if "/" in model else model


def _call_ollama(
    model: str,
    messages: list[dict[str, str]],
    *,
    temperature: float,
    max_tokens: int | None = None,
    schema: dict[str, Any] | None = None,
) -> str:
    """POST to Ollama's /api/chat and return the assistant's text.

    Args:
        schema: A JSON Schema. When supplied, Ollama constrains decoding to
            it, so the output cannot be malformed JSON. This is a sampler
            constraint, not a prompt instruction, so the model cannot
            ignore it.
    """
    options: dict[str, Any] = {"temperature": temperature}
    if max_tokens:
        options["num_predict"] = max_tokens

    payload: dict[str, Any] = {
        "model": _ollama_model_name(model),
        "messages": messages,
        "stream": False,
        "options": options,
    }
    if schema is not None:
        payload["format"] = schema

    url = f"{config.OLLAMA_API_BASE.rstrip('/')}/api/chat"
    try:
        response = requests.post(url, json=payload, timeout=_OLLAMA_TIMEOUT)
    except requests.RequestException as exc:
        raise LlmCallError(
            f"Could not reach Ollama at {url}: {exc}. "
            f"Start it with `ollama serve`, and check the model is present "
            f"with `ollama list`."
        ) from exc

    if response.status_code == 404:
        raise LlmCallError(
            f"Ollama does not have a model named "
            f"'{_ollama_model_name(model)}'. Run `ollama list` to see what "
            f"is installed."
        )
    if response.status_code >= 400:
        raise LlmCallError(
            f"Ollama returned HTTP {response.status_code}: "
            f"{response.text[:300]}"
        )

    return (response.json().get("message") or {}).get("content", "")


# --------------------------------------------------------------------------
# Vertex AI dedicated endpoint (MedGemma)
# --------------------------------------------------------------------------
# The endpoint accepts the OpenAI-style "chatCompletions" request format
# wrapped in a Vertex `instances` envelope:
#
#   {"instances": [{"@requestFormat": "chatCompletions",
#                   "messages": [{"role": "...", "content": [{"type":"text","text":"..."}]}],
#                   "max_tokens": N}]}
#
# Authentication is a bearer token from Application Default Credentials.
# `gcloud auth application-default login` or a service account on Cloud Run
# both satisfy google-auth; if that library is missing we shell out to
# `gcloud auth print-access-token`, which is what the curl example does.

_VERTEX_TOKEN_LOCK = threading.Lock()
_VERTEX_TOKEN: dict[str, Any] = {"value": None, "expires": 0.0}


def _vertex_access_token() -> str:
    """Return a cached OAuth2 bearer token, refreshing a few minutes early."""
    now = time.time()
    with _VERTEX_TOKEN_LOCK:
        if _VERTEX_TOKEN["value"] and now < _VERTEX_TOKEN["expires"] - 300:
            return _VERTEX_TOKEN["value"]

        token: str | None = None
        expires_at: float = now + 3300  # gcloud tokens live ~1h

        try:
            import google.auth
            import google.auth.transport.requests

            creds, _ = google.auth.default(
                scopes=["https://www.googleapis.com/auth/cloud-platform"])
            creds.refresh(google.auth.transport.requests.Request())
            token = creds.token
            if getattr(creds, "expiry", None):
                expires_at = creds.expiry.timestamp()
        except Exception:  # noqa: BLE001 - fall through to gcloud
            token = None

        if not token:
            try:
                proc = subprocess.run(
                    ["gcloud", "auth", "print-access-token"],
                    capture_output=True, text=True, timeout=30, check=True,
                )
                token = proc.stdout.strip()
            except Exception as exc:  # noqa: BLE001
                raise LlmCallError(
                    "Could not obtain a Google Cloud access token for the "
                    "Vertex MedGemma endpoint. Run `gcloud auth "
                    "application-default login` (or `gcloud auth login`) "
                    f"and retry. Underlying error: {exc}"
                ) from exc

        _VERTEX_TOKEN["value"] = token
        _VERTEX_TOKEN["expires"] = expires_at
        return token


def _to_chat_completions_messages(messages: list[dict[str, str]]) -> list[dict[str, Any]]:
    """Convert plain {role, content:str} into the endpoint's content-parts form."""
    out: list[dict[str, Any]] = []
    for m in messages:
        content = m.get("content", "")
        if isinstance(content, str):
            content = [{"type": "text", "text": content}]
        out.append({"role": m.get("role", "user"), "content": content})
    return out


# Dedicated Vertex endpoints get a hostname of the form
#   <endpoint-id>.<region>-<NUMBER>.prediction.vertexai.goog
# and that NUMBER changes every time the model is (re)deployed - observed
# 2026-10-08: 781612439219 -> 893481880555 after an undeploy/redeploy of the
# same endpoint id. Hard-coding it in .env therefore breaks on every
# redeploy. Instead we ask the Vertex control plane for the endpoint's
# current `dedicatedEndpointDns` and cache it; a connection failure clears
# the cache so the next call re-resolves without a restart.
_PREDICT_URL: dict[str, str | None] = {"value": None}
_PREDICT_URL_LOCK = threading.Lock()


def _lookup_dedicated_dns() -> str | None:
    """GET the endpoint resource and return its dedicatedEndpointDns, or None."""
    url = (f"https://{config.VERTEX_LOCATION}-aiplatform.googleapis.com/v1/"
           f"projects/{config.VERTEX_PROJECT_ID}/locations/{config.VERTEX_LOCATION}"
           f"/endpoints/{config.VERTEX_MEDGEMMA_ENDPOINT_ID}")
    try:
        resp = requests.get(url, headers={"Authorization": f"Bearer {_vertex_access_token()}"},
                            timeout=15)
        if resp.status_code != 200:
            print(f"[llm] endpoint lookup HTTP {resp.status_code}: {resp.text[:160]}",
                  file=sys.stderr)
            return None
        return (resp.json().get("dedicatedEndpointDns") or "").strip() or None
    except Exception as exc:  # noqa: BLE001
        print(f"[llm] endpoint lookup failed: {type(exc).__name__}: {str(exc)[:160]}",
              file=sys.stderr)
        return None


def _resolve_predict_url(force: bool = False) -> str:
    """Return the :predict URL for the MedGemma endpoint.

    Priority: explicit SRMA_VERTEX_MEDGEMMA_URL override > live lookup of
    the endpoint's dedicated DNS > the static URL assembled in config.
    """
    if os.getenv("SRMA_VERTEX_MEDGEMMA_URL", "").strip():
        return config.VERTEX_MEDGEMMA_PREDICT_URL
    with _PREDICT_URL_LOCK:
        if _PREDICT_URL["value"] and not force:
            return _PREDICT_URL["value"]
        dns = _lookup_dedicated_dns()
        if dns:
            url = (f"https://{dns}/v1/projects/{config.VERTEX_PROJECT_ID}"
                   f"/locations/{config.VERTEX_LOCATION}"
                   f"/endpoints/{config.VERTEX_MEDGEMMA_ENDPOINT_ID}:predict")
        else:
            url = config.VERTEX_MEDGEMMA_PREDICT_URL
        _PREDICT_URL["value"] = url
        return url


def _invalidate_predict_url() -> None:
    with _PREDICT_URL_LOCK:
        _PREDICT_URL["value"] = None


def _call_vertex_medgemma(
    model: str,
    messages: list[dict[str, str]],
    *,
    temperature: float,
    max_tokens: int | None = None,
    schema: dict[str, Any] | None = None,
) -> str:
    """POST a chatCompletions instance to the Vertex dedicated endpoint.

    The vLLM-backed endpoint has no sampler-level schema constraint like
    Ollama's `format`, so `schema` is intentionally ignored here: the JSON
    schema is already spelled out in the system prompt by `call_json`, and
    the extract/repair/retry loop handles the rest.
    """
    instance: dict[str, Any] = {
        "@requestFormat": "chatCompletions",
        "messages": _to_chat_completions_messages(messages),
        "max_tokens": int(max_tokens or _VERTEX_DEFAULT_MAX_TOKENS),
        "temperature": float(temperature),
    }
    payload = {"instances": [instance]}
    url = _resolve_predict_url()

    last_exc: Exception | None = None
    for attempt in range(2):
        headers = {
            "Authorization": f"Bearer {_vertex_access_token()}",
            "Content-Type": "application/json",
        }
        try:
            response = requests.post(url, json=payload, headers=headers,
                                     timeout=config.VERTEX_TIMEOUT)
        except requests.ConnectionError as exc:
            # Hostname gone / changed (e.g. model redeployed under a new
            # dedicated DNS). Re-resolve once, then give up.
            if attempt == 0:
                _invalidate_predict_url()
                new_url = _resolve_predict_url()
                if new_url != url:
                    url = new_url
                    continue
            raise LlmCallError(
                f"Could not reach the Vertex MedGemma endpoint at {url}: {exc}"
            ) from exc
        except requests.RequestException as exc:
            raise LlmCallError(
                f"Could not reach the Vertex MedGemma endpoint at {url}: {exc}"
            ) from exc

        if response.status_code == 401 and attempt == 0:
            # Token may have been revoked/expired early; force refresh once.
            with _VERTEX_TOKEN_LOCK:
                _VERTEX_TOKEN["value"] = None
            continue
        if response.status_code >= 400:
            raise LlmCallError(
                f"Vertex MedGemma endpoint returned HTTP "
                f"{response.status_code}: {response.text[:400]}"
            )
        break
    else:  # pragma: no cover - only if both attempts hit 401
        raise LlmCallError(f"Vertex MedGemma auth failed twice: {last_exc}")

    body = response.json()
    return _strip_thinking(_extract_vertex_text(body))


def clinical_model_reachable(timeout: float = 8.0) -> tuple[bool, str]:
    """Cheap liveness probe for the clinical model, used before a run starts.

    For the Vertex dedicated endpoint: while the model is undeployed the
    endpoint hostname does not resolve at all, so a DNS lookup answers in
    milliseconds. If DNS succeeds we send a 1-token request to confirm the
    deployment is actually serving (a freshly deploying replica resolves
    but returns 5xx for several minutes).

    Returns (ok, detail). Never raises.
    """
    model = config.CLINICAL_MODEL
    if not _is_vertex(model):
        return True, "non-vertex clinical model; no probe"

    # Force a fresh lookup: this runs once per review, which is exactly when
    # a redeploy under a new dedicated DNS must be noticed.
    url = _resolve_predict_url(force=True)
    host = urlparse(url).hostname or ""
    try:
        socket.getaddrinfo(host, 443)
    except socket.gaierror as exc:
        return False, f"endpoint hostname does not resolve ({host}): {exc}"

    payload = {"instances": [{
        "@requestFormat": "chatCompletions",
        "messages": [{"role": "user", "content": [{"type": "text", "text": "OK"}]}],
        "max_tokens": 1,
        "temperature": 0.0,
    }]}
    try:
        headers = {"Authorization": f"Bearer {_vertex_access_token()}",
                   "Content-Type": "application/json"}
        resp = requests.post(url, json=payload, headers=headers, timeout=timeout)
    except Exception as exc:  # noqa: BLE001
        return False, f"probe failed: {type(exc).__name__}: {str(exc)[:160]}"
    if resp.status_code >= 400:
        return False, f"endpoint returned HTTP {resp.status_code}: {resp.text[:160]}"
    return True, "ok"

# The vLLM-served MedGemma emits an internal reasoning block before the real
# answer, delimited by Gemma's reserved thinking tokens:
#   "<unused94>thought\n...reasoning...<unused95>final answer"
# Observed live: health_check() returned "<unused94>thought\nThe user wants
# me to act as...". The structured-JSON path survives because it searches
# for the first "{", but free-text callers would leak the reasoning into
# reports, and a thought block that itself contains a "{" would mislead the
# JSON extractor. Strip it at the transport boundary.
_THINK_BLOCK_RE = re.compile(r"<unused94>.*?(?:<unused95>|$)", re.DOTALL)
_THINK_PREFIX_RE = re.compile(r"^\s*(?:<unused9[45]>)?\s*thought\s*\n", re.IGNORECASE)


def _strip_thinking(text: str) -> str:
    if not text or "<unused9" not in text and not text.lstrip().lower().startswith("thought"):
        return text
    cleaned = _THINK_BLOCK_RE.sub("", text)
    cleaned = _THINK_PREFIX_RE.sub("", cleaned)
    cleaned = cleaned.replace("<unused95>", "").replace("<unused94>", "")
    # If stripping removed everything (model put the answer inside the
    # thought block), fall back to the original minus the marker tokens so
    # the JSON extractor still has something to search.
    if not cleaned.strip():
        cleaned = text.replace("<unused94>", "").replace("<unused95>", "")
        cleaned = _THINK_PREFIX_RE.sub("", cleaned)
    return cleaned.strip()


def _extract_vertex_text(body: dict[str, Any]) -> str:
    """Pull the assistant text out of the several shapes Vertex may return.

    Dedicated endpoints return `{"predictions": <openai-chat-completion>}`
    for a single instance, or `{"predictions": [<completion>, ...]}`. Some
    deployments return the completion at the top level. All are handled.
    """
    pred = body.get("predictions", body)
    if isinstance(pred, list):
        pred = pred[0] if pred else {}
    if isinstance(pred, str):
        return pred

    choices = pred.get("choices") if isinstance(pred, dict) else None
    if choices:
        msg = choices[0].get("message") or {}
        content = msg.get("content", "")
        if isinstance(content, list):
            content = "".join(
                part.get("text", "") for part in content
                if isinstance(part, dict) and part.get("type", "text") == "text"
            )
        if content:
            return content
        # Some servers put plain completions under "text".
        if choices[0].get("text"):
            return choices[0]["text"]

    # Last resort: common alternative keys.
    for key in ("content", "text", "output", "generated_text"):
        if isinstance(pred, dict) and isinstance(pred.get(key), str):
            return pred[key]

    raise LlmCallError(
        f"Unrecognised Vertex response shape: {json.dumps(body)[:400]}")


def _call_litellm(
    model: str,
    messages: list[dict[str, str]],
    *,
    temperature: float,
    max_tokens: int | None = None,
) -> str:
    """Fallback transport for hosted providers such as Gemini."""
    import litellm

    response = litellm.completion(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return response.choices[0].message.content or ""


def _complete(
    model: str,
    messages: list[dict[str, str]],
    *,
    temperature: float,
    max_tokens: int | None = None,
    schema: dict[str, Any] | None = None,
) -> str:
    """Route to the right transport for the model string.

    For the Vertex MedGemma path, a transport-level failure (network, auth,
    5xx, unparseable response) is retried once against the local Ollama
    MedGemma when `config.VERTEX_FALLBACK_TO_LOCAL` is on. The fallback is
    logged to stderr so a run that silently degraded is still auditable.
    """
    if _is_vertex(model):
        try:
            return _call_vertex_medgemma(model, messages, temperature=temperature,
                                         max_tokens=max_tokens, schema=schema)
        except LlmCallError as exc:
            if not config.VERTEX_FALLBACK_TO_LOCAL:
                raise
            print(f"[llm] Vertex MedGemma failed ({str(exc)[:160]}); "
                  f"falling back to {config.LOCAL_CLINICAL_MODEL}",
                  file=sys.stderr)
            return _call_ollama(config.LOCAL_CLINICAL_MODEL, messages,
                                temperature=temperature, max_tokens=max_tokens,
                                schema=schema)
    if _is_ollama(model):
        return _call_ollama(model, messages, temperature=temperature,
                            max_tokens=max_tokens, schema=schema)
    return _call_litellm(model, messages, temperature=temperature,
                         max_tokens=max_tokens)



def call_json(
    system_prompt: str,
    user_prompt: str,
    schema: type[T],
    *,
    model: str | None = None,
    temperature: float = 0.1,
    max_attempts: int = 3,
) -> T:
    """Call the model and return a validated instance of `schema`.

    On Ollama the schema is enforced by the sampler, so attempt one is
    normally already valid JSON. The retry loop exists for two remaining
    failure modes: providers without constrained decoding, and output that
    is syntactically valid JSON but semantically wrong, such as an enum
    value outside the permitted set.

    Args:
        system_prompt: Role and methodology. Must contain the grounding
            facts; never rely on the model's own recall.
        user_prompt: The specific text to judge.
        schema: Pydantic model the reply must satisfy.
        model: Model string. Defaults to the clinical model.
        temperature: Low by default; this is classification, not writing.
        max_attempts: Retries, each with escalating corrective feedback.

    Raises:
        LlmCallError: if no attempt produced schema-valid JSON.
    """
    model = model or config.CLINICAL_MODEL
    json_schema = schema.model_json_schema()

    # Providers without constrained decoding need the schema spelled out in
    # the prompt. Ollama does not, but including it costs little and makes
    # field semantics clearer to the model either way.
    messages = [
        {"role": "system", "content":
            f"{system_prompt}\n\n"
            f"Reply with a single JSON object and nothing else. "
            f"It must conform to this JSON Schema:\n"
            f"{json.dumps(json_schema, indent=2)}"},
        {"role": "user", "content": user_prompt},
    ]

    errors: list[str] = []
    for attempt in range(max_attempts):
        try:
            text = _complete(model, messages, temperature=temperature,
                             schema=json_schema)
        except LlmCallError as exc:
            # A transport failure will not be fixed by rephrasing, so stop
            # rather than burn two more timeouts on the same dead socket.
            raise
        except Exception as exc:  # noqa: BLE001 - surface any provider error
            errors.append(f"attempt {attempt + 1}: API error: {exc}")
            continue

        try:
            raw = _extract_json(text)
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                data = json.loads(_repair(raw))
            return schema.model_validate(data)
        except (LlmCallError, json.JSONDecodeError, ValidationError) as exc:
            errors.append(f"attempt {attempt + 1}: {type(exc).__name__}: "
                          f"{str(exc)[:300]}")
            # Feed the failure back so the retry is informed, not identical.
            messages.append({"role": "assistant", "content": text[:1000]})
            messages.append({"role": "user", "content":
                f"That was not valid. Error: {str(exc)[:300]}\n"
                f"Reply with ONLY the JSON object, no prose, no code fences."})

    raise LlmCallError(
        f"Failed after {max_attempts} attempts.\n" + "\n".join(errors))


def call_text(
    system_prompt: str,
    user_prompt: str,
    *,
    model: str | None = None,
    temperature: float = 0.2,
    max_tokens: int = 2048,
) -> str:
    """Free-text call, for narrative sections where no schema applies."""
    model = model or config.CLINICAL_MODEL
    try:
        return _complete(
            model,
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )
    except LlmCallError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise LlmCallError(f"Model call failed: {exc}") from exc



def health_check(model: str | None = None) -> dict[str, Any]:
    """Verify the model endpoint is reachable. Used by the CLI preflight."""
    model = model or config.CLINICAL_MODEL
    try:
        reply = call_text(
            "You are a test harness.",
            "Reply with exactly: OK",
            model=model, max_tokens=10,
        )
        return {"status": "ok", "model": model, "reply": reply.strip()[:50]}
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "model": model, "error": str(exc)[:300]}
