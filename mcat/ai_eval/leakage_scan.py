#!/usr/bin/env python3
# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Rubric 7e — train/test leakage scanner.

Standalone script that scans the TRAINING corpus (source-grounded generated
cards, the shipped EXAM_MCQ bank, and the authored gold set) against the
HELD-OUT TEST items we score on (the 7d reworded transfer questions and the 9.8
perf-question generator output). It flags any test item that is an exact match
or a near-duplicate (token-set Jaccard >= threshold) of a training item — i.e.
an evaluation item that leaked in from something the pipeline already saw, which
would inflate scores.

A clean result (0 leaked) means the transfer/held-out numbers are measured on
genuinely novel surface. To prove the scanner is not simply blind, it also runs
a SANITY CHECK that plants a known training item into the test set and confirms
it is caught.

Run:
  PYTHONPATH=out/pylib:pylib out/pyenv/bin/python mcat/ai_eval/leakage_scan.py
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

# Pre-registered near-duplicate threshold (token-set Jaccard). Set before scan.
NEAR_DUP_THRESHOLD = 0.70


def load_json(name: str):
    with open(os.path.join(HERE, name), encoding="utf-8") as fh:
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


def normalise(text: str) -> str:
    return " ".join("".join(c if c.isalnum() else " " for c in text.lower()).split())


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def build_training_corpus() -> list[dict]:
    """Everything the generation pipeline could have seen: the generated card
    set (+ seeded corpus), the shipped EXAM_MCQ bank, and the authored gold
    set."""
    corpus: list[dict] = []

    gen = load_json("generated.json")
    for c in gen.get("corpus", []):
        corpus.append({"src": "generated.corpus", "text": c["question"]})
    for c in gen.get("cards", []):
        corpus.append({"src": "generated.cards", "text": c["question"]})

    try:
        from content import EXAM_MCQ  # noqa: E402

        for _tag, question, _opts, _correct, _expl in EXAM_MCQ:
            corpus.append({"src": "EXAM_MCQ", "text": question})
    except Exception as exc:  # pragma: no cover
        print(f"  (warning: could not import EXAM_MCQ: {exc})")

    if os.path.exists(os.path.join(HERE, "gold_set.json")):
        gold = load_json("gold_set.json")
        for item in gold.get("items", []):
            corpus.append({"src": "gold_set", "text": item["question"]})

    for entry in corpus:
        entry["tokens"] = tokens(entry["text"])
        entry["norm"] = normalise(entry["text"])
    return corpus


def build_test_items() -> list[dict]:
    """The held-out items we actually score on: 7d reworded transfer questions
    and the 9.8 perf-question generator output."""
    tests: list[dict] = []

    para = load_json("paraphrase_items.json")
    for it in para["items"]:
        for rw in it["reworded"]:
            tests.append({"src": "paraphrase.reworded", "text": rw["question"]})

    # Perf-question generator output (real RPC), grounded in the same source.
    try:
        from anki.collection import Collection  # noqa: E402

        source = load_json("source.json")
        tmp = tempfile.mkdtemp(prefix="leak_perf_")
        col = Collection(os.path.join(tmp, "c.anki2"))
        try:
            col.mcat_register_ai_source(
                source_name=source["source_name"],
                excerpt=source["excerpt"],
                source_section=source.get("source_section", ""),
                source_id=source["source_id"],
            )
            deck_id = col.decks.id("MCAT::Leak")
            basic = col.models.by_name("Basic")
            seeds = [
                ("What does a competitive inhibitor do to Km and Vmax?",
                 "Raises apparent Km; Vmax unchanged."),
                ("Where does glycolysis occur?", "In the cytosol."),
                ("What regenerates NAD+ anaerobically?", "Lactate fermentation."),
            ]
            for q, a in seeds:
                note = col.new_note(basic)
                note["Front"] = q
                note["Back"] = a
                note.tags = ["mcat::biobiochem::metabolism"]
                col.add_note(note, deck_id)
                cid = col.find_cards(f"nid:{note.id}")[0]
                gen = col.mcat_generate_perf_questions(
                    card_id=cid, source_id=source["source_id"]
                )
                for pq in gen.questions:
                    tests.append({"src": "perfgen", "text": pq.question})
        finally:
            col.close()
    except Exception as exc:  # pragma: no cover
        print(f"  (warning: could not exercise perf-gen: {exc})")

    for t in tests:
        t["tokens"] = tokens(t["text"])
        t["norm"] = normalise(t["text"])
    return tests


def scan(tests: list[dict], corpus: list[dict], threshold: float) -> list[dict]:
    flags = []
    for t in tests:
        best_score = 0.0
        best_train = None
        exact = False
        for c in corpus:
            if t["norm"] == c["norm"]:
                exact = True
                best_score = 1.0
                best_train = c
                break
            s = jaccard(t["tokens"], c["tokens"])
            if s > best_score:
                best_score = s
                best_train = c
        if exact or best_score >= threshold:
            flags.append(
                {
                    "test": t,
                    "score": best_score,
                    "exact": exact,
                    "train": best_train,
                }
            )
    return flags


def main() -> int:
    print("=== Rubric 7e — train/test leakage scan ===")
    print(f"Pre-registered near-duplicate threshold (Jaccard): {NEAR_DUP_THRESHOLD}")

    corpus = build_training_corpus()
    tests = build_test_items()

    from collections import Counter

    csrc = Counter(c["src"] for c in corpus)
    tsrc = Counter(t["src"] for t in tests)
    print(
        f"\nTraining corpus: {len(corpus)} items "
        + "(" + ", ".join(f"{k}:{v}" for k, v in csrc.items()) + ")"
    )
    print(
        f"Held-out test items: {len(tests)} items "
        + "(" + ", ".join(f"{k}:{v}" for k, v in tsrc.items()) + ")"
    )

    flags = scan(tests, corpus, NEAR_DUP_THRESHOLD)
    exact = sum(1 for f in flags if f["exact"])
    near = len(flags) - exact

    # Distribution of the best match score, to show how far test items sit from
    # the nearest training item even when nothing is flagged.
    max_scores = []
    for t in tests:
        best = 0.0
        for c in corpus:
            if t["norm"] == c["norm"]:
                best = 1.0
                break
            s = jaccard(t["tokens"], c["tokens"])
            best = max(best, s)
        max_scores.append(best)
    max_scores.sort(reverse=True)

    print("\n-- Result --")
    print(f"  Exact-duplicate leaks : {exact}")
    print(f"  Near-duplicate leaks  : {near} (Jaccard >= {NEAR_DUP_THRESHOLD})")
    print(f"  Total leaked          : {len(flags)} / {len(tests)}")
    print(
        f"  Highest test↔train similarity observed: "
        f"{max_scores[0]:.2f} (next: "
        f"{', '.join(f'{s:.2f}' for s in max_scores[1:4])})"
    )
    if flags:
        print("\n  Flagged items:")
        for f in flags[:20]:
            kind = "EXACT" if f["exact"] else f"near({f['score']:.2f})"
            print(f"    [{kind}] {f['test']['src']}: {f['test']['text'][:70]}")
            print(f"        ~ {f['train']['src']}: {f['train']['text'][:70]}")
        verdict = f"{len(flags)} leaked — NOT clean"
    else:
        verdict = "0 leaked — CLEAN"
    print(f"\n  VERDICT: {verdict}")

    # Sanity check: plant a known training item as a fake test item and confirm
    # the scanner catches it (guards against a silently-blind scan).
    planted = dict(corpus[0])
    planted["src"] = "PLANTED(sanity)"
    sanity_flags = scan([planted], corpus, NEAR_DUP_THRESHOLD)
    ok = len(sanity_flags) == 1 and sanity_flags[0]["exact"]
    print(
        f"\n  Sanity check (plant a training item into the test set): "
        f"{'caught' if ok else 'MISSED'} "
        f"(scanner is {'working' if ok else 'BROKEN'})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
