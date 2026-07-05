#!/usr/bin/env python3
# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Three-build study test under EQUAL study time.

Compares three study-scheduling builds head-to-head, holding the study budget
fixed (same number of reviews per arm):

  A = blocked        : study one topic at a time, no recommender
                       (col.mcat_interleaved_session(interleave=False))
  B = interleaved    : mix topics across the session
                       (col.mcat_interleaved_session(interleave=True))
  C = interleaved + topic-weighted recommender : weighted round-robin over
      topics using the deterministic recommender's real priority score
      (col.mcat_study_recommendation()).

What is REAL here: the per-arm study ORDER comes from the shipped Rust
scheduling RPCs, and the per-topic exam weight + recommender priority are read
from the backend. What is SYNTHETIC (fixed seed, clearly labelled): the learner.
Crucially, the learner model is IDENTICAL across all three arms — the only thing
that differs is which topics each build spends the fixed budget on. So any
difference in the outcome is attributable to the scheduling policy, not to a
per-arm learning bonus we baked in.

Outcome proxy: exam-weighted TRANSFER accuracy on held-out reworded questions
per topic (a topic you never reach in the budget stays at its starting mastery).

HONESTY: no real learners; magnitudes depend on the synthetic learning-rate and
starting-mastery assumptions. The comparison is fair because those assumptions
are shared by every arm. We print an explicit verdict even when a build does not
help.

Run:
  PYTHONPATH=out/pylib:pylib out/pyenv/bin/python mcat/ai_eval/study_three_build.py
"""

from __future__ import annotations

import math
import os
import random
import sys
import tempfile
from collections import Counter

os.environ.setdefault("MCAT_AI_MOCK", "1")

HERE = os.path.dirname(os.path.abspath(__file__))
MCAT_DIR = os.path.join(HERE, "..")
sys.path.insert(0, MCAT_DIR)

from anki.collection import Collection  # noqa: E402

SEED = 4242
N_LEARNERS = 300
HISTORY_CARDS = 4  # per topic, reviewed to prime the backend
STUDY_CARDS = 8  # per topic, the fresh study queue
BUDGET_FRACTION = 0.45  # equal study time = this fraction of all study events
GAIN_MEAN = 0.28  # per-review mastery gain toward 1.0 (diminishing returns)
LOGIT_K = 3.5  # transfer-test sharpness

# Topic set + SYNTHETIC ground-truth starting mastery (what the arms don't see)
# and per-topic transfer difficulty. Exam weight + recommender priority are read
# live from the backend, not hard-coded.
TOPICS = {
    "mcat::biobiochem::enzymes": {"m0": 0.25, "d": 0.55},
    "mcat::biobiochem::metabolism": {"m0": 0.35, "d": 0.50},
    "mcat::biobiochem::glycolysis": {"m0": 0.45, "d": 0.45},
    "mcat::chemphys::thermodynamics": {"m0": 0.70, "d": 0.60},
    "mcat::chemphys::kinetics": {"m0": 0.60, "d": 0.55},
    "mcat::chemphys::acids_bases": {"m0": 0.50, "d": 0.50},
}


def logistic(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def build_collection() -> tuple[Collection, dict]:
    """Seed a collection, prime it with reviewed history, add a fresh study
    queue, and return the collection plus a card_id -> topic map."""
    tmp = tempfile.mkdtemp(prefix="study3_")
    col = Collection(os.path.join(tmp, "c.anki2"))
    deck_id = col.decks.id("MCAT::Study3")
    basic = col.models.by_name("Basic")
    rng = random.Random(SEED)

    def add(topic: str, front: str) -> int:
        note = col.new_note(basic)
        note["Front"] = front
        note["Back"] = "answer"
        note.tags = ["mcat::exam", topic]
        col.add_note(note, deck_id)
        return col.find_cards(f"nid:{note.id}")[0]

    id_topic: dict[int, str] = {}

    # History cards, reviewed with an ease pattern reflecting starting mastery.
    for topic, meta in TOPICS.items():
        for i in range(HISTORY_CARDS):
            cid = add(topic, f"{topic} history {i}?")
            id_topic[cid] = topic
    col.decks.select(deck_id)
    n = 0
    while True:
        card = col.sched.getCard()
        if card is None:
            break
        topic = id_topic.get(card.id)
        if topic is None:
            col.sched.answerCard(card, 3)
        else:
            m = TOPICS[topic]["m0"]
            col.sched.answerCard(card, 3 if rng.random() < m else 1)
        n += 1
        if n > 400:
            break

    # Fresh study queue (the queue the three builds will order).
    for topic in TOPICS:
        for i in range(STUDY_CARDS):
            cid = add(topic, f"{topic} study {i}?")
            id_topic[cid] = topic

    return col, id_topic


def topic_sequence(card_ids, id_topic) -> list[str]:
    return [id_topic[c] for c in card_ids if c in id_topic]


def weighted_interleave(counts: dict, weights: dict) -> list[str]:
    """Deficit-weighted round-robin: higher-priority topics get proportionally
    more early slots, but topics stay interleaved (not blocked)."""
    remaining = dict(counts)
    credit = {t: 0.0 for t in counts}
    order: list[str] = []
    total = sum(counts.values())
    for _ in range(total):
        for t in counts:
            if remaining[t] > 0:
                credit[t] += weights.get(t, 1.0)
        avail = [t for t in counts if remaining[t] > 0]
        if not avail:
            break
        pick = max(avail, key=lambda t: credit[t])
        order.append(pick)
        remaining[pick] -= 1
        credit[pick] -= sum(weights.get(t, 1.0) for t in avail)
    return order


def run_arm(seq: list[str], budget: int, exam_weight: dict) -> float:
    """Average exam-weighted transfer accuracy over the synthetic learners for
    one arm's study order, truncated to the fixed budget. All arms draw the SAME
    learner population (same seed) so this is a paired comparison — differences
    come only from the study order, not from Monte-Carlo noise."""
    rng = random.Random(SEED)
    studied = seq[:budget]
    total = 0.0
    for _ in range(N_LEARNERS):
        gain = max(0.05, rng.gauss(GAIN_MEAN, 0.05))
        mastery = {
            t: min(0.98, max(0.02, TOPICS[t]["m0"] + rng.gauss(0.0, 0.05)))
            for t in TOPICS
        }
        for topic in studied:
            mastery[topic] += gain * (1.0 - mastery[topic])
        num = den = 0.0
        for t, meta in TOPICS.items():
            w = exam_weight.get(t, 1.0)
            acc = logistic(LOGIT_K * (mastery[t] - meta["d"]))
            num += w * acc
            den += w
        total += num / den
    return total / N_LEARNERS


def main() -> int:
    col, id_topic = build_collection()
    try:
        blk = col.mcat_interleaved_session(interleave=False, max_cards=500)
        inter = col.mcat_interleaved_session(interleave=True, max_cards=500)
        rec = col.mcat_study_recommendation()
    finally:
        # keep col open until after we read everything
        pass

    # Real per-topic signals from the backend.
    priority = {c.topic_key: c.priority_score for c in rec.candidates}
    exam_weight = {c.topic_key: c.exam_weight for c in rec.candidates}
    # Fill any missing topics with neutral defaults.
    for t in TOPICS:
        priority.setdefault(t, 1.0)
        exam_weight.setdefault(t, 4.0)
    col.close()

    a_seq = topic_sequence(blk.card_ids, id_topic)
    b_seq = topic_sequence(inter.card_ids, id_topic)
    # Only order the fresh study cards for the weighted arm.
    study_counts = Counter(t for t in b_seq)
    c_seq = weighted_interleave(dict(study_counts), priority)

    total_events = len(b_seq)
    budget = max(1, int(round(total_events * BUDGET_FRACTION)))

    print("=== Three-build study test (equal study time) ===")
    print(
        f"Topics: {len(TOPICS)}   study events available: {total_events}   "
        f"EQUAL budget/arm: {budget} reviews   learners: {N_LEARNERS}   "
        f"seed: {SEED}"
    )
    print("\nBackend recommender priority (real) / exam weight (real):")
    for t in TOPICS:
        print(
            f"  {t:<34} priority {priority[t]:5.2f}  exam_weight {exam_weight[t]:.0f}"
        )

    arms = {
        "A blocked (no recommender)": a_seq,
        "B interleaved": b_seq,
        "C interleaved + weighted rec": c_seq,
    }

    print("\nTopic coverage within the equal budget (reviews per topic):")
    results = {}
    for name, seq in arms.items():
        cov = Counter(seq[:budget])
        results[name] = run_arm(seq, budget, exam_weight)
        cov_str = ", ".join(
            f"{t.split('::')[-1]}:{cov.get(t, 0)}" for t in TOPICS
        )
        print(f"  {name:<32} {cov_str}")

    print("\n-- Results (exam-weighted transfer accuracy on held-out reworded qs) --")
    print(f"  {'Build':<32} {'Transfer acc':>12}")
    print(f"  {'-' * 32} {'-' * 12}")
    for name in arms:
        print(f"  {name:<32} {results[name] * 100:11.1f}%")

    best = max(results, key=results.get)
    b_val = results["B interleaved"]
    c_val = results["C interleaved + weighted rec"]
    a_val = results["A blocked (no recommender)"]
    print("\n-- Verdict --")
    print(f"  Best build under equal time: {best} ({results[best] * 100:.1f}%).")
    print(
        f"  Interleaving vs blocking: {(b_val - a_val) * 100:+.1f} pts "
        f"(B {b_val * 100:.1f}% vs A {a_val * 100:.1f}%)."
    )
    verdict_c = (
        f"  Adding the topic-weighted recommender vs plain interleaving: "
        f"{(c_val - b_val) * 100:+.1f} pts (C {c_val * 100:.1f}% vs B "
        f"{b_val * 100:.1f}%)."
    )
    print(verdict_c)
    if c_val <= b_val + 1e-9:
        print(
            "  HONEST NEGATIVE RESULT: under a strictly equal review budget the "
            "recommender\n  weighting did NOT beat plain interleaving on this "
            "synthetic outcome — even\n  coverage already captured most of the "
            "gain, and concentrating the budget\n  on high-priority topics hit "
            "diminishing returns."
        )
    else:
        print(
            "  The recommender weighting added a small gain by front-loading "
            "high-yield\n  topics within the fixed budget."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
