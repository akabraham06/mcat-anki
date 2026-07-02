#!/usr/bin/env python3
# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""9.4 gold-set evaluation harness for the AI card quality checker.

Runs entirely OFFLINE using the deterministic mock AI provider (via the
``MCAT_AI_MOCK`` environment variable), so it needs no network and no API key
and keeps ``just check`` / CI green. It:

* evaluates 50 known-correct MCAT Q/A pairs (positives, drawn from the real
  starter content) — the checker should accept these;
* evaluates 50 candidate cards "generated from one real source" (source.json +
  generated.json), each with a ground-truth label — a mix of good cards and
  wrong / vague / trivial / duplicate ones the checker should block;
* compares the checker against a naive length/keyword **baseline**;
* writes ``mcat/ai_eval/report.md`` and exits non-zero if the checker does not
  beat the baseline.

Run via ``just mcat-ai-eval`` (which sets PYTHONPATH + MCAT_AI_MOCK).
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

from content import EXAM_MCQ  # noqa: E402

from anki.collection import Collection  # noqa: E402

REPORT_PATH = os.path.join(HERE, "report.md")

# Checker acceptance cutoff is set BEFORE testing and stored in config; the
# default is 0.7 (see rslib/src/mcat/ai/mod.rs DEFAULT_CHECKER_CUTOFF).
CHECKER_CUTOFF = 0.7


def load_json(name: str) -> dict:
    with open(os.path.join(HERE, name), encoding="utf-8") as fh:
        return json.load(fh)


def baseline_accept(question: str, answer: str) -> bool:
    """Naive baseline: accept if the answer is reasonably long and the question
    looks like a question. Ignores facts, source, vagueness and duplicates."""
    return len(answer.strip()) >= 25 and question.strip().endswith("?")


def positives_from_content(n: int = 50) -> list[dict]:
    """50 known-correct MCAT Q/A pairs from the real starter content: the exam
    question stem as the question and its explanation as the answer."""
    out = []
    for tag, question, _options, _correct, explanation in EXAM_MCQ[:n]:
        out.append({"question": question, "answer": explanation, "topic_tag": tag})
    return out


def add_note(col: Collection, deck_id: int, question: str, answer: str, tag: str) -> None:
    basic = col.models.by_name("Basic")
    note = col.new_note(basic)
    note["Front"] = question
    note["Back"] = answer
    note.tags = [tag]
    col.add_note(note, deck_id)


def evaluate() -> dict:
    source = load_json("source.json")
    gen = load_json("generated.json")

    results = {
        "positives": {"checker_correct": 0, "baseline_correct": 0, "total": 0},
        "generated": {
            "checker_correct": 0,
            "baseline_correct": 0,
            "total": 0,
            "accepted": 0,
            "blocked": 0,
            "duplicates": 0,
            "correct_and_useful": 0,
            "wrong_caught": 0,
            "bad_teaching_caught": 0,
        },
    }

    # --- Phase A: positives (no source; the general quality gate) ---
    tmp = tempfile.mkdtemp(prefix="mcat_eval_pos_")
    col = Collection(os.path.join(tmp, "c.anki2"))
    try:
        for card in positives_from_content(50):
            report = col.mcat_check_card(
                question=card["question"],
                answer=card["answer"],
                topic_tag=card["topic_tag"],
            )
            checker_accept = report.passed
            base = baseline_accept(card["question"], card["answer"])
            results["positives"]["total"] += 1
            if checker_accept:  # expected: accept
                results["positives"]["checker_correct"] += 1
            if base:
                results["positives"]["baseline_correct"] += 1
    finally:
        col.close()

    # --- Phase B: generated candidates (grounded in the source) ---
    tmp = tempfile.mkdtemp(prefix="mcat_eval_gen_")
    col = Collection(os.path.join(tmp, "c.anki2"))
    try:
        deck_id = col.decks.id("MCAT::Eval")
        # Seed the "existing notes" corpus so the duplicate check can fire.
        for c in gen.get("corpus", []):
            add_note(col, deck_id, c["question"], c["answer"], c["topic_tag"])
        # Register the single real source used to ground generation.
        col.mcat_register_ai_source(
            source_name=source["source_name"],
            excerpt=source["excerpt"],
            source_section=source.get("source_section", ""),
            source_id=source["source_id"],
        )
        excerpt = source["excerpt"]
        g = results["generated"]
        for card in gen["cards"]:
            report = col.mcat_check_card(
                question=card["question"],
                answer=card["answer"],
                topic_tag=card["topic_tag"],
                source_id=source["source_id"],
                source_excerpt=excerpt,
            )
            checker_accept = report.passed
            base = baseline_accept(card["question"], card["answer"])
            expected_accept = card["label"] == "accept"
            g["total"] += 1
            if checker_accept == expected_accept:
                g["checker_correct"] += 1
            if base == expected_accept:
                g["baseline_correct"] += 1
            if checker_accept:
                g["accepted"] += 1
                if expected_accept:
                    g["correct_and_useful"] += 1
            else:
                g["blocked"] += 1
            if report.duplicate:
                g["duplicates"] += 1
            if not checker_accept and card["flaw"] == "unsupported":
                g["wrong_caught"] += 1
            if not checker_accept and card["flaw"] in ("vague", "trivial"):
                g["bad_teaching_caught"] += 1
    finally:
        col.close()

    return results


def write_report(results: dict) -> tuple[float, float]:
    pos = results["positives"]
    g = results["generated"]
    total = pos["total"] + g["total"]
    checker_correct = pos["checker_correct"] + g["checker_correct"]
    baseline_correct = pos["baseline_correct"] + g["baseline_correct"]
    checker_acc = checker_correct / total if total else 0.0
    baseline_acc = baseline_correct / total if total else 0.0

    lines = [
        "# MCAT AI Card Quality Checker — Gold-set Evaluation",
        "",
        "Deterministic, offline evaluation (mock AI provider, no network/key).",
        "",
        f"- **Checker passing cutoff (set before testing):** {CHECKER_CUTOFF}",
        f"- **Gold set:** {pos['total']} known-correct MCAT Q/A + {g['total']} "
        "generated candidates from one source",
        "",
        "## Accuracy vs. baseline",
        "",
        "| System | Correct | Total | Accuracy |",
        "| --- | --- | --- | --- |",
        f"| Multi-category AI checker | {checker_correct} | {total} | {checker_acc:.1%} |",
        f"| Naive length/keyword baseline | {baseline_correct} | {total} | {baseline_acc:.1%} |",
        "",
        f"**Checker beats baseline: {checker_acc:.1%} vs {baseline_acc:.1%} "
        f"(+{(checker_acc - baseline_acc) * 100:.1f} pts).**",
        "",
        "## Positives (known-correct human cards)",
        "",
        f"- Checker accepted: {pos['checker_correct']}/{pos['total']}",
        f"- Baseline accepted: {pos['baseline_correct']}/{pos['total']}",
        "",
        "## Generated candidates (labelled)",
        "",
        f"- Accepted: {g['accepted']}",
        f"- Blocked: {g['blocked']}",
        f"- Correct & useful (accepted good cards): {g['correct_and_useful']}",
        f"- Wrong / unsupported caught: {g['wrong_caught']}",
        f"- Correct-but-bad-teaching (vague/trivial) caught: {g['bad_teaching_caught']}",
        f"- Duplicates detected: {g['duplicates']}",
        f"- Checker decisions matching label: {g['checker_correct']}/{g['total']}",
        f"- Baseline decisions matching label: {g['baseline_correct']}/{g['total']}",
        "",
    ]
    with open(REPORT_PATH, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    return checker_acc, baseline_acc


def main() -> int:
    results = evaluate()
    checker_acc, baseline_acc = write_report(results)
    print(f"Wrote {REPORT_PATH}")
    print(f"Checker accuracy: {checker_acc:.1%}   Baseline accuracy: {baseline_acc:.1%}")
    if checker_acc <= baseline_acc:
        print("FAIL: checker did not beat the baseline", file=sys.stderr)
        return 1
    print("PASS: checker beats the baseline")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
