#!/usr/bin/env python3
# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Rubric 7f — gold-set check with a pre-registered cutoff.

Protocol (cutoff fixed BEFORE looking at any result):

1. Gold set: 50 Q&A with known-correct MCAT answers (``gold_set.json``, sourced
   from the curated EXAM_MCQ bank). Used as the known-correct reference and as a
   false-block calibration set.
2. Candidates: 50 cards generated from ONE real source (``generated.json``,
   grounded in ``source.json``), each carrying a human ground-truth quality
   label.
3. Cutoff = 0.70, pre-registered (``DEFAULT_CHECKER_CUTOFF`` /
   ``gold_set.json.cutoff``); set on the collection before any card is scored.
4. Run every candidate through the 9.4 quality checker; BLOCK any card that does
   not pass (overall score < cutoff or a hard failure).
5. Report EXACTLY THREE COUNTS of the 50 candidates by TRUE quality:
     (a) correct + useful           (flaw = none)
     (b) wrong (wrong fact)         (flaw = unsupported)
     (c) correct-but-bad-teaching   (flaw = vague / trivial / duplicate)
   plus how many were blocked, and a per-bucket block breakdown.

Run:
  PYTHONPATH=out/pylib:pylib out/pyenv/bin/python mcat/ai_eval/gold_set_check.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile

os.environ.setdefault("MCAT_AI_MOCK", "1")

HERE = os.path.dirname(os.path.abspath(__file__))
MCAT_DIR = os.path.join(HERE, "..")
sys.path.insert(0, MCAT_DIR)

from anki.collection import Collection  # noqa: E402

# Pre-registered acceptance cutoff — fixed BEFORE inspecting any candidate.
CUTOFF = 0.70

BUCKET_OF_FLAW = {
    "none": "a_correct_useful",
    "unsupported": "b_wrong_fact",
    "vague": "c_bad_teaching",
    "trivial": "c_bad_teaching",
    "duplicate": "c_bad_teaching",
}


def load_json(name: str):
    with open(os.path.join(HERE, name), encoding="utf-8") as fh:
        return json.load(fh)


def add_note(col, deck_id, q, a, tags):
    basic = col.models.by_name("Basic")
    note = col.new_note(basic)
    note["Front"] = q
    note["Back"] = a
    note.tags = tags
    col.add_note(note, deck_id)
    return col.find_cards(f"nid:{note.id}")[0]


def main() -> int:
    source = load_json("source.json")
    gen = load_json("generated.json")
    gold = load_json("gold_set.json")
    candidates = gen["cards"]

    print("=== Rubric 7f — gold-set check ===")
    print(f"Pre-registered cutoff (set before looking): {CUTOFF:.2f}")
    print(
        f"Gold set: {len(gold['items'])} known-correct MCAT Q&A  |  "
        f"Candidates: {len(candidates)} cards from one real source "
        f"('{source['source_name']}')"
    )

    # --- Three ground-truth counts of the 50 candidates ---
    counts = {"a_correct_useful": 0, "b_wrong_fact": 0, "c_bad_teaching": 0}
    for c in candidates:
        counts[BUCKET_OF_FLAW[c["flaw"]]] += 1

    # --- Run candidates through the checker at the pre-registered cutoff ---
    col = Collection(os.path.join(tempfile.mkdtemp(prefix="gold_cand_"), "c.anki2"))
    observed_cutoff = CUTOFF
    blocked_total = 0
    blocked_by_bucket = {"a_correct_useful": 0, "b_wrong_fact": 0, "c_bad_teaching": 0}
    passed_by_bucket = {"a_correct_useful": 0, "b_wrong_fact": 0, "c_bad_teaching": 0}
    try:
        col.mcat_ai_set_config(checker_cutoff=CUTOFF, enabled=True)
        deck_id = col.decks.id("MCAT::Gold")
        for c in gen.get("corpus", []):
            add_note(col, deck_id, c["question"], c["answer"], [c["topic_tag"]])
        col.mcat_register_ai_source(
            source_name=source["source_name"],
            excerpt=source["excerpt"],
            source_section=source.get("source_section", ""),
            source_id=source["source_id"],
        )
        for c in candidates:
            report = col.mcat_check_card(
                question=c["question"],
                answer=c["answer"],
                topic_tag=c["topic_tag"],
                source_id=source["source_id"],
                source_excerpt=source["excerpt"],
            )
            observed_cutoff = report.cutoff
            bucket = BUCKET_OF_FLAW[c["flaw"]]
            if report.passed:
                passed_by_bucket[bucket] += 1
            else:
                blocked_total += 1
                blocked_by_bucket[bucket] += 1
    finally:
        col.close()

    # --- Gold calibration: false-block rate on known-correct Q&A ---
    col = Collection(os.path.join(tempfile.mkdtemp(prefix="gold_cal_"), "c.anki2"))
    gold_blocked = 0
    try:
        col.mcat_ai_set_config(checker_cutoff=CUTOFF, enabled=True)
        for item in gold["items"]:
            report = col.mcat_check_card(
                question=item["question"],
                answer=f"{item['answer']}. {item['explanation']}",
                topic_tag=item["topic"],
            )
            if not report.passed:
                gold_blocked += 1
    finally:
        col.close()

    print(f"\nChecker cutoff confirmed from report objects: {observed_cutoff:.2f}")

    print("\n-- THREE COUNTS (ground truth quality of the 50 candidates) --")
    print(f"  (a) correct + useful          : {counts['a_correct_useful']}")
    print(f"  (b) wrong (wrong fact)        : {counts['b_wrong_fact']}")
    print(f"  (c) correct-but-bad-teaching  : {counts['c_bad_teaching']}")
    print(
        f"      (bad-teaching = vague/trivial/duplicate) "
        f"total = {sum(counts.values())}"
    )

    print(f"\n-- Blocked by the checker at cutoff {observed_cutoff:.2f} --")
    print(f"  Blocked total: {blocked_total} / {len(candidates)}")
    print(f"  {'Bucket':<30} {'blocked':>8} {'passed':>8}")
    labels = {
        "a_correct_useful": "(a) correct + useful",
        "b_wrong_fact": "(b) wrong fact",
        "c_bad_teaching": "(c) bad teaching",
    }
    for key in ("a_correct_useful", "b_wrong_fact", "c_bad_teaching"):
        print(
            f"  {labels[key]:<30} {blocked_by_bucket[key]:>8} "
            f"{passed_by_bucket[key]:>8}"
        )

    good_shown = passed_by_bucket["a_correct_useful"]
    bad_shown = passed_by_bucket["b_wrong_fact"] + passed_by_bucket["c_bad_teaching"]
    print(
        f"\n  Of the {good_shown + bad_shown} cards the checker would SHOW a "
        f"student, {bad_shown} are actually bad "
        f"(wrong or bad-teaching) — the wrong-answer leak-through."
    )
    print(
        f"  Wrong-fact cards caught: {blocked_by_bucket['b_wrong_fact']}/"
        f"{counts['b_wrong_fact']}; "
        f"bad-teaching caught: {blocked_by_bucket['c_bad_teaching']}/"
        f"{counts['c_bad_teaching']}; "
        f"good cards wrongly blocked: {blocked_by_bucket['a_correct_useful']}/"
        f"{counts['a_correct_useful']}."
    )

    print(
        f"\n-- Gold-set calibration (false-block on known-correct Q&A) --\n"
        f"  {gold_blocked}/{len(gold['items'])} known-correct gold cards were "
        f"blocked at cutoff {CUTOFF:.2f}\n"
        f"  (these gold items are ungrounded broad-MCAT Q&A; the number bounds "
        f"the checker's\n  false-block rate when no registered source is "
        f"attached)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
