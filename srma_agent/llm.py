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
import re
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
    """Route to the right transport for the model string."""
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
