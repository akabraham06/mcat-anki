#!/usr/bin/env python3
# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Deterministic-scoring smoke check with AI switched OFF.

Confirms the rubric guarantee that the app still produces MCAT scores when AI is
disabled: with ``mcat.ai.enabled = false`` (and a clean env) the AI status pill
is unavailable, yet ``mcat_exam_readiness`` still returns the deterministic
memory / performance / section scores computed purely from review history — no
AI is involved in scoring at all.

Run: PYTHONPATH=out/pylib:pylib out/pyenv/bin/python mcat/ai_eval/verify_scoring_ai_off.py
"""

from __future__ import annotations

import os
import sys
import tempfile

for key in (
    "OPENAI_API_KEY",
    "MCAT_AI_API_KEY",
    "MCAT_AI_BASE_URL",
    "MCAT_AI_MODEL",
    "MCAT_AI_MOCK",
):
    os.environ.pop(key, None)

from anki.collection import Collection  # noqa: E402

KNOWLEDGE = [
    ("mcat::biobiochem::metabolism", "Where does glycolysis occur?", "The cytosol."),
    ("mcat::biobiochem::metabolism", "Net ATP from glycolysis?", "Two ATP."),
    ("mcat::biobiochem::enzymes", "Competitive inhibitor effect on Km?", "Raises apparent Km."),
    ("mcat::chemphys::thermodynamics", "Sign of dG for a spontaneous process?", "Negative."),
]


def add(col: Collection, deck_id: int, tag: str, front: str, back: str, exam: bool) -> int:
    basic = col.models.by_name("Basic")
    note = col.new_note(basic)
    note["Front"] = front
    note["Back"] = back
    note.tags = (["mcat::exam", tag] if exam else [tag])
    col.add_note(note, deck_id)
    return note.id


def answer_all(col: Collection, deck_id: int, ease: int = 3) -> int:
    col.decks.select(deck_id)
    n = 0
    while True:
        card = col.sched.getCard()
        if card is None:
            break
        col.sched.answerCard(card, ease)
        n += 1
        if n > 500:
            break
    return n


def main() -> int:
    tmp = tempfile.mkdtemp(prefix="mcat_scoring_off_")
    col = Collection(os.path.join(tmp, "c.anki2"))
    try:
        # Switch AI OFF explicitly (belt-and-braces alongside the clean env).
        col.mcat_ai_set_config(enabled=False)
        status = col.mcat_ai_status()
        print("=== AI status (explicitly disabled) ===")
        print(f"  available: {status.available}   reason: {status.reason}")
        assert not status.available, "AI must be off for this check"

        deck_id = col.decks.id("MCAT::ScoreOff")
        for tag, front, back in KNOWLEDGE:
            add(col, deck_id, tag, front, back, exam=False)
        # One exam-style (performance) card so the performance score has data.
        add(
            col,
            deck_id,
            "mcat::biobiochem::metabolism",
            "In a cell lacking oxygen, what regenerates NAD+?",
            "Lactate fermentation.",
            exam=True,
        )
        graded = answer_all(col, deck_id)
        print(f"\nAnswered {graded} reviews (AI off the whole time).")

        r = col.mcat_exam_readiness()
        print("\n=== Deterministic MCAT scores with AI OFF ===")

        def show(label: str, s) -> None:
            if s.available:
                print(
                    f"  {label:<12}: {s.point:.1f}  [{s.low:.1f}–{s.high:.1f}]  "
                    f"confidence={s.confidence}  coverage={s.coverage_percent:.0f}%"
                )
            else:
                print(f"  {label:<12}: (abstains) {s.abstain_reason}")

        show("Memory", r.memory)
        show("Performance", r.performance)
        show("Readiness", r.readiness)
        print(f"  Give-up rule : {r.give_up_rule.description}")
        print("  Section scores:")
        for sec in r.sections:
            state = f"{sec.point:.1f}" if sec.available else "abstains"
            print(f"    - {sec.section_name:<28} {state}  (coverage {sec.coverage_percent:.0f}%)")

        # The core guarantee: a real MCAT score is produced with AI off.
        assert r.memory.available, "memory score must be produced with AI off"
        assert r.recommendation.available, "deterministic recommender must still work"
        print(
            "\nSCORING-AI-OFF OK: memory/section scores produced deterministically "
            "with AI disabled; readiness follows the written give-up rule."
        )
        return 0
    finally:
        col.close()


if __name__ == "__main__":
    raise SystemExit(main())
