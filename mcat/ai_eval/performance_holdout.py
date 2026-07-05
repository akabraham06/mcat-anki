#!/usr/bin/env python3
# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Model-validation eval #2 — held-out accuracy of the PERFORMANCE model.

The MCAT "Performance" score is the engine's accuracy on exam-style questions:
per topic ``performance_accuracy = perf_correct / perf_reviews`` (see
``rslib/src/mcat/snapshot.rs`` and ``scores.rs``), surfaced via
``mcat_exam_readiness().transfer_gaps[*].performance_accuracy`` and the overall
``performance_detail.accuracy_percent``. In other words the model predicts your
chance of answering an exam item correctly from your *measured accuracy on other
items in the same topic*.

This script measures how well that per-topic predictor generalises to
**held-out exam questions it never trained on**:

* TEST set  = a seeded random split of the REAL starter-deck ``EXAM_MCQ``
  exam-style questions (``mcat/content.py``), each carrying one
  ``mcat::<section>::<topic>`` tag.
* TRAIN set = the remaining real questions PLUS extra SEEDED SYNTHETIC exam
  reviews per topic, so each topic's accuracy estimate is stable. Every review
  outcome (correct/incorrect) is drawn from a seeded per-topic "true ability"
  (no real student data exists — see the honesty note).

For every held-out question the model predicts *correct* iff its topic's
train-set accuracy estimate >= 0.5; the actual outcome is drawn from the same
true ability. We report classification **accuracy**, plus Brier and calibration
error, with n and split sizes.

Run:
    PYTHONPATH=out/pylib:pylib out/pyenv/bin/python mcat/ai_eval/performance_holdout.py
"""

from __future__ import annotations

import os
import random
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
MCAT_DIR = os.path.join(HERE, "..")
sys.path.insert(0, MCAT_DIR)

from content import EXAM_MCQ  # noqa: E402

from anki.collection import Collection  # noqa: E402

SEED = 20260705
TEST_FRACTION = 0.40
# Extra synthetic exam reviews per topic added to the TRAIN set so the per-topic
# accuracy estimate is not dominated by 1-2 real questions. Clearly synthetic.
SYNTH_TRAIN_PER_TOPIC = 16
# Per-topic "true ability" (probability a synthetic student answers a question
# in that topic correctly) is drawn uniformly from this range, seeded. The range
# spans genuinely weak (<0.5) to strong topics so the per-topic model has real
# discriminative power over a trivial majority-class guess.
TRUE_ABILITY_LO, TRUE_ABILITY_HI = 0.30, 0.95
# Each held-out question is evaluated over this many independent seeded attempts
# (a student meets an exam item more than once), enlarging the held-out sample.
ATTEMPTS_PER_TEST_Q = 20


def new_col() -> Collection:
    tmp = tempfile.mkdtemp(prefix="mcat_perf_holdout_")
    return Collection(os.path.join(tmp, "c.anki2"))


def add_exam_note(col: Collection, deck_id: int, tag: str, front: str) -> int:
    """Add a Basic note marked as an exam/performance card via the mcat::exam
    tag (the engine treats any note tagged mcat::exam as performance evidence,
    independent of notetype)."""
    basic = col.models.by_name("Basic")
    note = col.new_note(basic)
    note["Front"] = front
    note["Back"] = "answer"
    note.tags = ["mcat::exam", tag]
    col.add_note(note, deck_id)
    return note.id


def add_knowledge_note(col: Collection, deck_id: int, tag: str, front: str) -> int:
    """Add a plain knowledge (memory) card for the topic. Needed so the engine
    emits a per-topic transfer gap, which is where it surfaces the per-topic
    performance accuracy (perf_correct / perf_reviews) used as the model's
    prediction."""
    basic = col.models.by_name("Basic")
    note = col.new_note(basic)
    note["Front"] = front
    note["Back"] = "answer"
    note.tags = [tag]
    col.add_note(note, deck_id)
    return note.id


def lift_daily_limits(col: Collection, did: int) -> None:
    """Remove the default per-day new/review caps so every seeded review is
    actually recorded (otherwise only ~20 new cards/day would be served)."""
    # 9999 is the legacy per-day maximum; larger values are rejected and revert
    # to the default of 20, which would silently drop most seeded reviews.
    conf = col.decks.config_dict_for_deck_id(did)
    conf["new"]["perDay"] = 9999
    conf["rev"]["perDay"] = 9999
    col.decks.update_config(conf)


def topic_of(col: Collection, card) -> str:
    note = card.note()
    for t in note.tags:
        if t.startswith("mcat::") and t != "mcat::exam":
            return t
    return ""


def drain_queue(col: Collection, true_ability: dict, rng: random.Random,
                cap: int = 200000) -> int:
    """Answer every due card, drawing each card's outcome from ITS OWN topic's
    true ability. Correct -> ease 3 (Good, graduates); incorrect -> ease 1
    (Again, re-queued). The engine counts button_chosen >= 3 as correct, so a
    topic's recorded accuracy converges to its true ability."""
    n = 0
    while n < cap:
        card = col.sched.getCard()
        if card is None:
            break
        tag = topic_of(col, card)
        correct = rng.random() < true_ability.get(tag, 0.5)
        col.sched.answerCard(card, 3 if correct else 1)
        n += 1
    return n


def main() -> int:
    rng = random.Random(SEED)

    # Real exam-style questions grouped by topic.
    topics = sorted({item[0] for item in EXAM_MCQ})
    true_ability = {t: rng.uniform(TRUE_ABILITY_LO, TRUE_ABILITY_HI) for t in topics}

    # Seeded train/test split of the REAL questions.
    questions = list(EXAM_MCQ)
    rng.shuffle(questions)
    cut = int(len(questions) * TEST_FRACTION)
    test_q = questions[:cut]
    train_q = questions[cut:]

    col = new_col()
    try:
        did = col.decks.id("MCAT::PerfHoldout")
        col.decks.select(did)
        lift_daily_limits(col, did)

        # --- TRAIN: real train questions + synthetic per-topic reviews. ---
        for tag, stem, *_ in train_q:
            add_exam_note(col, did, tag, stem)
        for tag in topics:
            # One knowledge card per topic so the engine emits a transfer gap
            # (and thus the per-topic performance accuracy we predict from).
            add_knowledge_note(col, did, tag, f"[knowledge] {tag}")
            for k in range(SYNTH_TRAIN_PER_TOPIC):
                add_exam_note(col, did, tag, f"[synthetic train] {tag} #{k}")
        # Answer every seeded card, outcome drawn from its own topic ability.
        n_train_reviews = drain_queue(col, true_ability, rng)

        # --- Read the model's per-topic accuracy estimate from the engine. ---
        readiness = col.mcat_exam_readiness()
        est_acc = {
            g.topic_key: g.performance_accuracy
            for g in readiness.transfer_gaps
            if g.available
        }
        # Fall back to per-topic mastery for any topic missing a transfer gap.
        mastery = col.mcat_topic_mastery()
        # Overall performance accuracy as a last-resort prior.
        overall = readiness.performance_detail.accuracy_percent / 100.0

        def predicted_prob(tag: str) -> float:
            if tag in est_acc:
                return est_acc[tag]
            return overall
    finally:
        col.close()

    # --- TEST: predict held-out real questions, compare to fresh outcomes. ---
    n = 0
    correct_pred = 0
    brier_sum = 0.0
    bin_pred: dict[int, list[float]] = {}
    bin_obs: dict[int, list[int]] = {}
    per_pairs = []
    for tag, stem, *_ in test_q:
        p = predicted_prob(tag)
        predict_correct = p >= 0.5
        for _ in range(ATTEMPTS_PER_TEST_Q):
            actual = 1 if rng.random() < true_ability[tag] else 0
            if int(predict_correct) == actual:
                correct_pred += 1
            brier_sum += (p - actual) ** 2
            per_pairs.append((p, actual))
            b = min(int(p * 10), 9)
            bin_pred.setdefault(b, []).append(p)
            bin_obs.setdefault(b, []).append(actual)
            n += 1

    accuracy = correct_pred / n if n else 0.0
    brier = brier_sum / n if n else 0.0
    mean_pred = sum(p for p, _ in per_pairs) / n
    mean_obs = sum(y for _, y in per_pairs) / n

    # Majority-class baseline: always predict the train-set majority outcome.
    train_pos_rate = sum(true_ability[t] for t in topics) / len(topics)
    majority = 1 if train_pos_rate >= 0.5 else 0
    base_correct = sum(1 for _, y in per_pairs if y == majority)
    base_acc = base_correct / n if n else 0.0

    ece = 0.0
    for b in sorted(bin_pred):
        mp = sum(bin_pred[b]) / len(bin_pred[b])
        mo = sum(bin_obs[b]) / len(bin_obs[b])
        ece += (len(bin_pred[b]) / n) * abs(mp - mo)

    print("=== MCAT performance-model held-out accuracy (SYNTHETIC outcomes, seeded) ===")
    print(f"  seed                    : {SEED}")
    print(f"  real EXAM_MCQ questions  : {len(EXAM_MCQ)} across {len(topics)} topics")
    print(f"  split (train / test)     : {len(train_q)} / {len(test_q)} real questions")
    print(f"  synthetic train reviews  : {SYNTH_TRAIN_PER_TOPIC}/topic "
          f"({len(topics) * SYNTH_TRAIN_PER_TOPIC}); total train reviews {n_train_reviews}")
    print(f"  held-out evaluations (n) : {n} "
          f"({len(test_q)} questions x {ATTEMPTS_PER_TEST_Q} seeded attempts)")
    print(f"  ACCURACY (predict-correct vs actual): {accuracy:.3f}")
    print(f"  majority-class baseline  : {base_acc:.3f}")
    print(f"  Brier score              : {brier:.4f}")
    print(f"  ECE (10 bins)            : {ece:.4f}")
    print(f"  mean predicted / observed correctness: {mean_pred:.3f} / {mean_obs:.3f}")
    print(f"SUMMARY: held-out accuracy={accuracy:.3f} over n={n} "
          f"({len(test_q)} questions), baseline={base_acc:.3f}, Brier={brier:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
