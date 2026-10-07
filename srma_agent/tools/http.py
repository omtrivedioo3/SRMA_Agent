"""Shared HTTP client for all literature sources.

Implements three things the SRMA specification demands of every query:

  Reproducibility - every request is logged with an exact UTC timestamp and
                    the full parameter set, so any search can be replayed.
  Traceability    - responses carry the source name and the query that
                    produced them, so a record can always be traced back.
  Politeness      - retries with exponential backoff, per-host rate limiting,
                    and an identifying User-Agent. Public research APIs are
                    free; hammering them is how you get blocked.
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlencode

import requests

from .. import config

# --------------------------------------------------------------------------
# Audit log
# --------------------------------------------------------------------------


@dataclass
class QueryRecord:
    """One API call, recorded for the reproducibility appendix."""

    source: str
    url: str
    params: dict[str, Any]
    timestamp_utc: str
    status_code: int | None
    n_results: int | None
    duration_ms: int
    error: str | None = None


class AuditLog:
    """Thread-safe, append-only record of every outbound query."""

    def __init__(self) -> None:
        self._records: list[QueryRecord] = []
        self._lock = threading.Lock()

    def add(self, record: QueryRecord) -> None:
        with self._lock:
            self._records.append(record)

    @property
    def records(self) -> list[QueryRecord]:
        with self._lock:
            return list(self._records)

    def as_dicts(self) -> list[dict[str, Any]]:
        return [asdict(r) for r in self.records]

    def clear(self) -> None:
        with self._lock:
            self._records.clear()

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.as_dicts(), indent=indent)

    def summary(self) -> dict[str, Any]:
        recs = self.records
        by_source: dict[str, int] = {}
        for r in recs:
            by_source[r.source] = by_source.get(r.source, 0) + 1
        return {
            "total_queries": len(recs),
            "queries_by_source": by_source,
            "failures": sum(1 for r in recs if r.error),
        }


# Module-level log. The pipeline snapshots and clears this per run.
AUDIT = AuditLog()


# --------------------------------------------------------------------------
# Rate limiting
# --------------------------------------------------------------------------


class _RateLimiter:
    """Simple per-host minimum-interval limiter."""

    def __init__(self) -> None:
        self._last_call: dict[str, float] = {}
        self._lock = threading.Lock()

    def wait(self, host: str, min_interval: float) -> None:
        with self._lock:
            last = self._last_call.get(host, 0.0)
            elapsed = time.monotonic() - last
            if elapsed < min_interval:
                time.sleep(min_interval - elapsed)
            self._last_call[host] = time.monotonic()


_LIMITER = _RateLimiter()

# Per-host minimum seconds between requests.
# NCBI allows 3/sec without a key and 10/sec with one.
_RATE_LIMITS: dict[str, float] = {
    "eutils.ncbi.nlm.nih.gov": 0.11 if config.NCBI_API_KEY else 0.34,
    "www.ebi.ac.uk": 0.10,
    "clinicaltrials.gov": 0.10,
    "api.openalex.org": 0.10,
    "api.crossref.org": 0.10,
    "api.semanticscholar.org": 1.10,  # aggressive limits without a key
    "api.biorxiv.org": 0.05,
    "api.fda.gov": 0.30,
    "api.unpaywall.org": 0.10,
}
_DEFAULT_RATE_LIMIT = 0.25


# --------------------------------------------------------------------------
# Request helper
# --------------------------------------------------------------------------

_SESSION = requests.Session()
_SESSION.headers.update({
    "User-Agent": config.USER_AGENT,
    "Accept": "application/json",
})


class SourceError(RuntimeError):
    """Raised when a source cannot be queried after all retries."""


def request_json(
    source: str,
    url: str,
    params: dict[str, Any] | None = None,
    *,
    headers: dict[str, str] | None = None,
    timeout: int | None = None,
    max_retries: int | None = None,
    expect_json: bool = True,
) -> Any:
    """GET a URL, with retries, rate limiting, and audit logging.

    Args:
        source: Short source name for the audit log, e.g. "pubmed".
        url: Full request URL.
        params: Query parameters.
        headers: Extra headers merged over the session defaults.
        timeout: Per-attempt timeout in seconds.
        max_retries: Attempts before giving up.
        expect_json: If False, returns response text instead of parsed JSON.

    Returns:
        Parsed JSON (or raw text when expect_json is False).

    Raises:
        SourceError: if all attempts fail.
    """
    params = dict(params or {})
    timeout = timeout or config.HTTP_TIMEOUT
    max_retries = max_retries or config.HTTP_MAX_RETRIES

    host = url.split("/")[2] if "//" in url else url
    min_interval = _RATE_LIMITS.get(host, _DEFAULT_RATE_LIMIT)

    started = time.monotonic()
    last_error: str | None = None
    status: int | None = None

    for attempt in range(max_retries):
        _LIMITER.wait(host, min_interval)
        try:
            resp = _SESSION.get(
                url, params=params, headers=headers, timeout=timeout
            )
            status = resp.status_code

            # Back off on rate limiting / transient server errors.
            if status in (429, 500, 502, 503, 504):
                last_error = f"HTTP {status}"
                time.sleep(min(2 ** attempt, 8))
                continue

            resp.raise_for_status()
            payload = resp.json() if expect_json else resp.text

            AUDIT.add(QueryRecord(
                source=source,
                url=url,
                params=_redact(params),
                timestamp_utc=datetime.now(timezone.utc).isoformat(),
                status_code=status,
                n_results=_guess_count(payload),
                duration_ms=int((time.monotonic() - started) * 1000),
            ))
            return payload

        except requests.RequestException as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            time.sleep(min(2 ** attempt, 8))
        except ValueError as exc:  # JSON decode failure
            last_error = f"Invalid JSON: {exc}"
            break

    AUDIT.add(QueryRecord(
        source=source,
        url=url,
        params=_redact(params),
        timestamp_utc=datetime.now(timezone.utc).isoformat(),
        status_code=status,
        n_results=None,
        duration_ms=int((time.monotonic() - started) * 1000),
        error=last_error,
    ))
    raise SourceError(f"{source}: {last_error} (url={url}?{urlencode(params)[:200]})")


def _redact(params: dict[str, Any]) -> dict[str, Any]:
    """Strip credentials from anything written to the audit log."""
    out = {}
    for k, v in params.items():
        if k.lower() in {"api_key", "apikey", "key", "token"}:
            out[k] = "<redacted>"
        else:
            out[k] = v
    return out


def _guess_count(payload: Any) -> int | None:
    """Best-effort result count, for the audit log only."""
    if isinstance(payload, dict):
        for key in ("hitCount", "totalResults", "total_count", "count", "meta"):
            val = payload.get(key)
            if isinstance(val, int):
                return val
            if isinstance(val, dict) and isinstance(val.get("count"), int):
                return val["count"]
        esr = payload.get("esearchresult")
        if isinstance(esr, dict) and "count" in esr:
            try:
                return int(esr["count"])
            except (TypeError, ValueError):
                return None
    if isinstance(payload, list):
        return len(payload)
    return None


def safe_call(source: str, fn, *args, **kwargs) -> dict[str, Any]:
    """Run a source function, converting failures into a structured result.

    One dead source must never abort a systematic review; the PRISMA report
    simply records that the source failed.
    """
    try:
        records = fn(*args, **kwargs)
        return {"source": source, "status": "success",
                "count": len(records), "records": records}
    except Exception as exc:  # noqa: BLE001 - deliberate catch-all per source
        return {"source": source, "status": "error",
                "count": 0, "records": [], "error": f"{type(exc).__name__}: {exc}"}
