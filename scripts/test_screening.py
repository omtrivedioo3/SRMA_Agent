#!/usr/bin/env python
"""Smoke test for dual-reviewer screening.

Three cases, chosen so that rubber-stamping cannot pass:

  POSITIVE  ISIS-2, an aspirin RCT in acute MI. Must be INCLUDED. This is
            the case the single-call version got wrong: it excluded on a
            wording mismatch between "suspected acute MI" and the
            protocol's "established coronary disease".
  NEGATIVE  A randomised aspirin trial in HEALTHY physicians with no
            cardiovascular disease. Must be EXCLUDED, "Wrong population".
  NEGATIVE  A narrative review. Must be EXCLUDED, "Not primary research".

It also checks that the two reviewers are not producing identical text,
which is the specific failure the two-call design was built to fix.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from srma_agent import config, llm, screening           # noqa: E402
from srma_agent.schemas import StudyRecord              # noqa: E402

PROTOCOL = """
  Population   : Adults with established coronary heart disease, including
                 acute or prior myocardial infarction (secondary prevention).
  Intervention : Aspirin (acetylsalicylic acid), any dose, oral.
  Comparator   : Placebo or no antiplatelet therapy.
  Primary outcome : All-cause or vascular mortality, or recurrent
                 myocardial infarction.
  Eligible designs: Randomized Controlled Trials only.
  Exclusions   : animal studies, in-vitro work, narrative reviews,
                 editorials, case reports; primary-prevention populations
                 with no established cardiovascular disease.
""".strip()

CASES = [
    (
        "POSITIVE - ISIS-2, aspirin RCT in acute MI",
        "Include", "",
        StudyRecord(
            pmid="2899772",
            title=("Randomised trial of intravenous streptokinase, oral "
                   "aspirin, both, or neither among 17,187 cases of "
                   "suspected acute myocardial infarction: ISIS-2."),
            publication_types=["Randomized Controlled Trial"],
            abstract=(
                "17,187 patients entering 417 hospitals up to 24 hours after "
                "the onset of suspected acute myocardial infarction were "
                "randomised, with placebo control, between one hour "
                "intravenous infusion of 1.5 MU streptokinase and one month "
                "of 160 mg/day enteric-coated aspirin. Aspirin alone "
                "produced a highly significant reduction in vascular "
                "mortality (804/8587 aspirin-allocated vascular deaths "
                "versus 1016/8600 placebo-allocated; 23% odds reduction, "
                "2p < 0.00001). Aspirin also halved the risk of non-fatal "
                "reinfarction."
            ),
        ),
    ),
    (
        "NEGATIVE - healthy physicians, primary prevention",
        "Exclude", "Wrong population",
        StudyRecord(
            pmid="2664509",
            title=("Final report on the aspirin component of the ongoing "
                   "Physicians' Health Study."),
            publication_types=["Randomized Controlled Trial"],
            abstract=(
                "We conducted a randomised, double-blind, placebo-controlled "
                "trial of aspirin among 22,071 HEALTHY male physicians aged "
                "40 to 84 years with NO history of myocardial infarction, "
                "stroke, or transient ischaemic attack at entry. "
                "Participants received 325 mg aspirin every other day. There "
                "was a 44% reduction in the risk of a FIRST myocardial "
                "infarction in the aspirin group. This primary-prevention "
                "finding does not address patients with established "
                "coronary disease."
            ),
        ),
    ),
    (
        "NEGATIVE - narrative review, not primary research",
        "Exclude", "Not primary research",
        StudyRecord(
            pmid="9999999",
            title="Aspirin in cardiovascular disease: a narrative review.",
            publication_types=["Review"],
            abstract=(
                "In this narrative review we summarise the history of "
                "aspirin in cardiovascular medicine. We discuss its "
                "mechanism of action on cyclooxygenase, and we describe the "
                "findings of several landmark trials. No new patients were "
                "enrolled and no original data are reported. This article "
                "is intended as an educational overview for trainees."
            ),
        ),
    ),
]


def main() -> int:
    print(config.summary())

    print("\nHealth check ...")
    health = llm.health_check()
    print(f"  {health}")
    if health["status"] != "ok":
        print("\nModel endpoint unreachable. Start Ollama with: ollama serve")
        return 1

    passes = 0
    identical_count = 0

    for label, expect, expect_cat, record in CASES:
        print(f"\n{'=' * 72}\n{label}\n  expecting: {expect}"
              f"{f' / {expect_cat}' if expect_cat else ''}\n{'=' * 72}")
        start = time.time()
        try:
            result = screening.screen_record(record, PROTOCOL)
        except Exception as exc:  # noqa: BLE001
            print(f"  FAILED: {type(exc).__name__}: {exc}")
            continue

        elapsed = time.time() - start
        print(f"  Reviewer 1 (recall-oriented)   : {result.reviewer_1.decision.value}")
        print(f"      {result.reviewer_1.reason[:160]}")
        print(f"  Reviewer 2 (precision-oriented): {result.reviewer_2.decision.value}")
        print(f"      {result.reviewer_2.reason[:160]}")
        print(f"  CONSENSUS : {result.consensus.value}")
        if result.exclusion_category:
            print(f"  Category  : {result.exclusion_category}")
        if result.conflict_resolution:
            print(f"  Resolved  : {result.conflict_resolution[:150]}")
        print(f"  ({elapsed:.1f}s)")

        identical = result.reviewer_1.reason.strip() == result.reviewer_2.reason.strip()
        if identical:
            identical_count += 1
            print("  NOTE: reviewers produced identical text on this record.")

        ok = result.consensus.value == expect
        if ok and expect_cat:
            ok = result.exclusion_category == expect_cat
            if not ok:
                print(f"  category mismatch: got {result.exclusion_category!r}")
        passes += ok
        print(f"  --> {'PASS' if ok else 'FAIL'}")

    print(f"\n{'=' * 72}")
    print(f"RESULT: {passes}/{len(CASES)} passed")
    print(f"Records where both reviewers wrote identical text: "
          f"{identical_count}/{len(CASES)}")
    if identical_count == len(CASES):
        print("WARNING: the two reviewer personas are not diverging at all. "
              "The dual-review safeguard is not doing any work.")
    return 0 if passes == len(CASES) else 1


if __name__ == "__main__":
    raise SystemExit(main())
