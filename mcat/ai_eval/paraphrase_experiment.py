#!/usr/bin/env python3
# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Rubric 7d — recall-vs-transfer (paraphrase) experiment.

Question: does strong *recall* on a flashcard actually mean the student
understands the idea, or are they just matching the card's surface wording?

Method (fully offline, deterministic):

1. Take 30 MCAT knowledge cards (``paraphrase_items.json``). Each card comes
   with 2 hand-authored, exam-style REWORDED questions that test the SAME idea
   with a different surface form. (We also try the shipped 9.8 perf-question
   generator ``col.mcat_generate_perf_questions`` and report what it returns;
   see the honesty note below for why authored items drive the measurement.)
2. Simulate a clearly-labelled SYNTHETIC learner population (fixed seed): each
   student has a latent ability; each card has a latent concept difficulty and a
   "surface-memorisation" propensity (the fraction of retention that is rote
   wording rather than understanding).
3. Measure mean RECALL on the ORIGINAL card vs mean ACCURACY on the 2 REWORDED
   questions, and report the GAP = mean_recall - mean_reworded_accuracy.

Interpretation: a near-zero gap would mean the performance signal just copies
the memory signal (students who "know" the card can't answer it reworded ⇒ they
only memorised surface). A positive gap quantifies how much apparent recall is
surface-bound and does not transfer.

HONESTY: there are NO real students here. The learner is synthetic with a fixed
seed, so the gap's *magnitude* reflects our modelling assumptions (surface-
memorisation propensity ``phi`` and concept-transfer success ``tau``), not a
measured human effect. What is real and reusable is (a) the authored
same-idea reworded item set, (b) the measurement harness, and (c) the control
showing the gap collapses to ~0 when surface-memorisation is removed. Real
magnitudes need real learners; plug them into ``simulate()`` unchanged.

Run:
  PYTHONPATH=out/pylib:pylib out/pyenv/bin/python mcat/ai_eval/paraphrase_experiment.py
"""

from __future__ import annotations

import json
import math
import os
import random
import sys
import tempfile

os.environ.setdefault("MCAT_AI_MOCK", "1")

HERE = os.path.dirname(os.path.abspath(__file__))
MCAT_DIR = os.path.join(HERE, "..")
sys.path.insert(0, MCAT_DIR)

from anki.collection import Collection  # noqa: E402

N_STUDENTS = 400
# Latent-model parameters (documented, synthetic).
CONCEPT_DIFF_SD = 0.9  # spread of per-card concept difficulty
PHI_LOW, PHI_HIGH = 0.15, 0.45  # per-card surface-memorisation propensity
ABILITY_MEAN, ABILITY_SD = 0.3, 1.0  # student ability distribution
TAU = 0.85  # P(a student who KNOWS the concept transfers to a reworded stem)
SURFACE_RECOG = 0.6  # how strongly rote memory fires on a reworded stem,
#                      scaled by word overlap with the original


def load_items() -> dict:
    with open(os.path.join(HERE, "paraphrase_items.json"), encoding="utf-8") as fh:
        return json.load(fh)


def tokens(text: str) -> set[str]:
    out, word = set(), ""
    for ch in text.lower():
        if ch.isalnum():
            word += ch
        elif word:
            if len(word) > 2:
                out.add(word)
            word = ""
    if len(word) > 2:
        out.add(word)
    return out


def jaccard(a: str, b: str) -> float:
    ta, tb = tokens(a), tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def logistic(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def simulate(items: list[dict], phi_scale: float = 1.0, tau: float = TAU) -> dict:
    """Monte-Carlo the synthetic learner population over the item set.

    ``phi_scale`` scales the surface-memorisation propensity (0.0 = a pure-
    understanding control where recall cannot be surface-bound)."""
    rng = random.Random(SEED)

    # Per-card latent parameters (fixed across students).
    card_params = []
    for it in items:
        b = rng.gauss(0.0, CONCEPT_DIFF_SD)  # concept difficulty
        phi = rng.uniform(PHI_LOW, PHI_HIGH) * phi_scale  # surface propensity
        overlaps = [
            jaccard(rw["question"], it["original_question"]) for rw in it["reworded"]
        ]
        card_params.append((b, phi, overlaps))

    orig_hits = 0
    orig_n = 0
    rew_hits = 0
    rew_n = 0
    per_card = []

    for b, phi, overlaps in card_params:
        c_orig = c_orig_n = c_rew = c_rew_n = 0
        for _ in range(N_STUDENTS):
            ability = rng.gauss(ABILITY_MEAN, ABILITY_SD)
            p_know = logistic(ability - b)
            knows = rng.random() < p_know
            memorised = rng.random() < phi  # rote surface memory of this card

            # Original card: correct if the concept is known OR the exact
            # wording was rote-memorised.
            correct_orig = knows or memorised
            c_orig += int(correct_orig)
            c_orig_n += 1

            # Reworded questions: understanding transfers with prob tau; rote
            # memory only fires to the extent the reworded stem still overlaps
            # the original wording.
            for ov in overlaps:
                transfer = knows and (rng.random() < tau)
                surface = memorised and (rng.random() < SURFACE_RECOG * ov)
                correct_rew = transfer or surface
                c_rew += int(correct_rew)
                c_rew_n += 1

        orig_hits += c_orig
        orig_n += c_orig_n
        rew_hits += c_rew
        rew_n += c_rew_n
        per_card.append(
            (c_orig / c_orig_n, c_rew / c_rew_n)
        )

    recall = orig_hits / orig_n
    reworded = rew_hits / rew_n
    return {
        "recall": recall,
        "reworded": reworded,
        "gap": recall - reworded,
        "per_card": per_card,
    }


def probe_perfgen(items: list[dict], k: int = 3) -> list[dict]:
    """Show what the shipped 9.8 perf-question generator returns for the first
    ``k`` cards, so the reader can compare it against the authored items."""
    src = {
        "source_id": "paraphrase-probe-src",
        "source_name": "MCAT Biochem Primer (probe)",
        "excerpt": (
            "Competitive inhibitors bind the active site and raise the apparent "
            "Km of an enzyme while leaving Vmax unchanged. Glycolysis occurs in "
            "the cytosol and nets two ATP and two NADH per glucose."
        ),
    }
    out = []
    tmp = tempfile.mkdtemp(prefix="paraphrase_perf_")
    col = Collection(os.path.join(tmp, "c.anki2"))
    try:
        col.mcat_register_ai_source(
            source_name=src["source_name"],
            excerpt=src["excerpt"],
            source_id=src["source_id"],
        )
        deck_id = col.decks.id("MCAT::Paraphrase")
        basic = col.models.by_name("Basic")
        for it in items[:k]:
            note = col.new_note(basic)
            note["Front"] = it["original_question"]
            note["Back"] = it["original_answer"]
            note.tags = [it["topic"]]
            col.add_note(note, deck_id)
            cid = col.find_cards(f"nid:{note.id}")[0]
            gen = col.mcat_generate_perf_questions(
                card_id=cid, source_id=src["source_id"]
            )
            out.append(
                {
                    "card": it["id"],
                    "ai_available": gen.ai_available,
                    "n": len(gen.questions),
                    "questions": [q.question for q in gen.questions],
                }
            )
    finally:
        col.close()
    return out


def main() -> int:
    data = load_items()
    global SEED
    SEED = int(data.get("seed", 1729))
    items = data["items"]
    n_cards = len(items)
    n_reworded = sum(len(it["reworded"]) for it in items)

    print("=== Rubric 7d — recall vs transfer (paraphrase) ===")
    print(
        f"Cards: {n_cards}   reworded questions: {n_reworded} "
        f"({n_reworded / n_cards:.1f} per card)   "
        f"synthetic students: {N_STUDENTS}   seed: {SEED}"
    )

    main_run = simulate(items, phi_scale=1.0, tau=TAU)
    print("\n-- Main synthetic learner --")
    print(f"  mean recall on ORIGINAL cards : {main_run['recall'] * 100:5.1f}%")
    print(f"  mean accuracy on REWORDED qs  : {main_run['reworded'] * 100:5.1f}%")
    print(
        f"  TRANSFER GAP (recall - reworded): "
        f"{main_run['gap'] * 100:5.1f} pts"
    )

    # Control: remove surface memorisation (phi=0) and assume perfect concept
    # transfer (tau=1). If recall were pure understanding, the gap vanishes.
    control = simulate(items, phi_scale=0.0, tau=1.0)
    print("\n-- Control (no surface memorisation, perfect transfer) --")
    print(f"  mean recall on ORIGINAL cards : {control['recall'] * 100:5.1f}%")
    print(f"  mean accuracy on REWORDED qs  : {control['reworded'] * 100:5.1f}%")
    print(f"  TRANSFER GAP                   : {control['gap'] * 100:5.1f} pts")
    print(
        "  (Interpretation: the gap collapses to ~0, confirming that in this "
        "model\n   a non-trivial gap comes specifically from surface-bound "
        "memorisation.)"
    )

    # Worst-transfer cards (largest per-card recall - reworded gap).
    ranked = sorted(
        zip(items, main_run["per_card"]),
        key=lambda t: t[1][0] - t[1][1],
        reverse=True,
    )
    print("\n-- Largest per-card recall→transfer drops (main run) --")
    for it, (o, r) in ranked[:5]:
        print(
            f"  {it['id']:<28} recall {o * 100:4.0f}%  reworded {r * 100:4.0f}%  "
            f"gap {(o - r) * 100:4.0f} pts"
        )

    print("\n-- Shipped 9.8 perf-question generator (first 3 cards) --")
    for row in probe_perfgen(items, k=3):
        print(f"  [{row['card']}] ai_available={row['ai_available']} n={row['n']}")
        for q in row["questions"]:
            print(f"      · {q}")
    print(
        "  NOTE: offline the mock perf-generator returns generic templated stems "
        "with\n  the source excerpt as the answer, so it can't drive a per-idea "
        "accuracy\n  measurement; the authored same-idea items above do. The "
        "generator path is\n  exercised here to show it is wired and available."
    )
    print(
        f"\nRESULT: transfer gap = {main_run['gap'] * 100:.1f} pts "
        f"(recall {main_run['recall'] * 100:.1f}% vs reworded "
        f"{main_run['reworded'] * 100:.1f}%), SYNTHETIC learner, seed {SEED}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
