#!/usr/bin/env python
"""Run a systematic review from the command line.

Useful when a review is long enough that you would rather leave it in a
terminal than hold a browser tab open, and for scripting repeated runs.

    ./.venv/bin/python scripts/run_review.py \
        "Does aspirin reduce mortality after myocardial infarction?"

    ./.venv/bin/python scripts/run_review.py --check
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from srma_agent import config, llm, pipeline      # noqa: E402
from srma_agent.tools import search as search_mod  # noqa: E402


def check_gemini() -> None:
    """Make one real Gemini call so we learn now whether the key works.

    Reporting only that a key string exists is close to useless: an expired
    key, a key with the API disabled, or an OAuth token pasted in by mistake
    all look identical to a presence check, and each one fails later inside
    `adk web` with an error that gives no hint about the cause.

    This never returns False. The pipeline itself does not call Gemini - only
    the ADK tool-calling front end does - so a broken key is a warning, not a
    reason to refuse to run a review.
    """
    if not config.GOOGLE_API_KEY:
        print("\n  gemini         : no key set")
        print("      The pipeline still runs; the local model does everything.")
        print("      A key is needed for `adk web`, where Gemini picks tools.")
        print("      Free key: https://aistudio.google.com/apikey")
        return


    try:
        from google import genai
        client = genai.Client(api_key=config.GOOGLE_API_KEY)
        client.models.generate_content(
            model=config.ORCHESTRATOR_MODEL, contents="Reply with: OK")
        print(f"\n  gemini         : OK ({config.ORCHESTRATOR_MODEL}, live call "
              f"succeeded)")
    except Exception as exc:  # noqa: BLE001 - surface whatever Google said
        text = str(exc)
        print(f"\n  gemini         : FAILED\n      {text[:400]}")
        # Map the three errors people actually hit onto their fixes.
        if "API_KEY_INVALID" in text or "API key not valid" in text:
            print("      The key was rejected. Make a new one at "
                  "https://aistudio.google.com/apikey")
        elif "PERMISSION_DENIED" in text or "SERVICE_DISABLED" in text:
            print("      The key is real but the Generative Language API is "
                  "off for its project.")
            print("      Easiest fix: create a key with 'Create API key in "
                  "new project'.")
        elif "RESOURCE_EXHAUSTED" in text or "429" in text:
            print("      Rate limited, not broken. Wait a minute and retry.")
        elif "NOT_FOUND" in text or "404" in text:
            # The key authenticated; the model id is simply gone. Google
            # retires ids on its own schedule and names the replacement in
            # the error text, so quote it rather than guessing.
            print(f"      Your key works - the model id "
                  f"'{config.ORCHESTRATOR_MODEL}' no longer exists.")
            print("      Google usually names the replacement in the message "
                  "above. Put it in .env as:")
            print("          SRMA_ORCHESTRATOR_MODEL=<that name>")
            print("      Or see everything your key can reach:")
            print("          ./.venv/bin/python scripts/run_review.py "
                  "--list-models")
        hint = config.google_api_key_hint()
        if hint:
            print(f"      {hint}")


def list_models() -> int:
    """Print every Gemini model this key may call, for pasting into .env.

    Hardcoded model ids rot: Google retires them and the code 404s through no
    fault of the user. Asking the API what exists right now turns that from a
    research task into a copy-paste, and it also reveals which models a
    particular account tier is actually entitled to - which differs between
    consumer, Workspace and Vertex keys.
    """
    if not config.GOOGLE_API_KEY:
        print("No GOOGLE_API_KEY set. Add one to .env first.")
        return 1
    try:
        from google import genai
        client = genai.Client(api_key=config.GOOGLE_API_KEY)
        names = []
        for m in client.models.list():
            actions = getattr(m, "supported_actions", None) or []
            # Only generateContent models can back an ADK agent; embedding
            # models would be a confusing thing to offer here.
            if actions and "generateContent" not in actions:
                continue
            names.append(m.name.removeprefix("models/"))
    except Exception as exc:  # noqa: BLE001
        print(f"Could not list models: {exc}")
        return 1

    print(f"Models available to this key ({len(names)}):\n")
    for name in sorted(names):
        marker = "  <- currently configured" if name == config.ORCHESTRATOR_MODEL else ""
        print(f"  {name}{marker}")
    print("\nTo use one, add this line to .env:")
    print("  SRMA_ORCHESTRATOR_MODEL=<name from the list above>")
    print("\nPrefer a 'flash' model: the orchestrator only routes tool calls,")
    print("so paying for 'pro' reasoning here buys nothing.")
    return 0


def preflight() -> bool:
    """Check both models and the databases before committing to a long run."""
    print(config.summary())
    print()

    health = llm.health_check()
    if health["status"] == "ok":
        print(f"  clinical model : OK ({config.CLINICAL_MODEL})")
    else:
        print(f"  clinical model : FAILED\n      {health.get('error')}")
        print("\n  Start it with:  ollama serve")
        return False

    sources = search_mod.available_sources()
    print(f"  databases      : {len(sources['available'])} available")
    for name in sources["available"]:
        print(f"      + {name}")
    for name, err in sources["unavailable"].items():
        print(f"      ! {name}: {err}")

    check_gemini()
    return True


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run a systematic review and meta-analysis.")
    parser.add_argument("question", nargs="?",
                        help="The clinical question, in plain English.")
    parser.add_argument("--check", action="store_true",
                        help="Run the preflight check and exit.")
    parser.add_argument("--list-models", action="store_true",
                        help="List Gemini models this API key can use, and exit.")
    parser.add_argument("--screen", type=int, default=None, metavar="N",
                        help="Abstracts to screen. Each costs ~20s.")
    parser.add_argument("--extract", type=int, default=10, metavar="N",
                        help="Studies to extract. Each costs ~40s.")
    parser.add_argument("--per-source", type=int, default=None, metavar="N",
                        help="Records to retrieve from each database.")
    parser.add_argument("--measure", default="auto",
                        help="auto, RR, OR, RD, MD or SMD.")
    parser.add_argument("--model", default="random",
                        help="fixed, random, random_reml, random_hksj, "
                             "random_reml_hksj.")
    parser.add_argument("--no-plots", action="store_true",
                        help="Skip figure rendering.")
    args = parser.parse_args()

    if args.list_models:
        return list_models()

    if not preflight():
        return 1
    if args.check:
        return 0
    if not args.question:
        parser.error("a question is required unless --check is given")

    print("\n" + "=" * 74)
    print(f"QUESTION: {args.question}")
    print("=" * 74 + "\n")

    def on_phase(phase: str, message: str) -> None:
        print(f"  [{phase:<14}] {message}", flush=True)

    result = pipeline.run_review(
        args.question,
        max_records_per_source=args.per_source,
        max_abstracts_to_screen=args.screen,
        max_studies_to_extract=args.extract,
        effect_measure=args.measure,
        model=args.model,
        make_plots=not args.no_plots,
        on_phase=on_phase,
    )

    print("\n" + pipeline.render_summary(result))
    print(f"\nFull output: {result.get('run_dir')}")
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
