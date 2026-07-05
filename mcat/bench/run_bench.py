#!/usr/bin/env python3
# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""One-command performance benchmark on the shared 50,000-card MCAT deck (7h).

Loads (generating on first run) the big benchmark collection from
``gen_big_deck.ensure_big_deck`` and times the core engine actions that the
desktop and phone perform, reporting the **median (p50)**, **95th percentile
(p95)** and **worst case** for each — never a single hand-picked number.

Actions covered:

* ``search_all``        – ``find_cards`` across the whole 50k deck
* ``search_tag``        – a tag-scoped search
* ``next_card``         – fetch the next due card from the v3 scheduler
* ``answer_card``       – grade a card through the real answering engine
* ``undo``              – undo that grade (proves undo stays fast at scale)
* ``topic_mastery``     – the per-topic mastery query (7a: powers the dashboard)
* ``exam_readiness``    – the full dashboard payload (three scores + coverage)
* ``study_recommendation`` – best-next-topic recommender

The cache is opened via a throwaway copy, so the benchmark never mutates the
cached deck and never touches the user's real profile. Results are written to
``mcat/bench/results/bench_<n>.{json,md}``.

Run (one command):

    just mcat-bench            # 50k deck, default iterations

Or directly:

    PYTHONPATH=out/pylib:pylib out/pyenv/bin/python mcat/bench/run_bench.py
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import statistics
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from gen_big_deck import DEFAULT_NUM_CARDS, ensure_big_deck  # noqa: E402

RESULTS_DIR = os.path.join(HERE, "results")


def _percentile(sorted_vals: list[float], pct: float) -> float:
    """Nearest-rank percentile on an already-sorted list (ms)."""
    if not sorted_vals:
        return 0.0
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    idx = int(round((pct / 100.0) * (len(sorted_vals) - 1)))
    idx = max(0, min(len(sorted_vals) - 1, idx))
    return sorted_vals[idx]


def _summary(name: str, samples_ms: list[float]) -> dict:
    s = sorted(samples_ms)
    return {
        "action": name,
        "n": len(s),
        "p50_ms": round(_percentile(s, 50), 3),
        "p95_ms": round(_percentile(s, 95), 3),
        "worst_ms": round(s[-1], 3) if s else 0.0,
        "mean_ms": round(statistics.fmean(s), 3) if s else 0.0,
    }


def _time_readonly(fn, iterations: int) -> list[float]:
    """Time a side-effect-free callable ``iterations`` times (+1 warmup)."""
    fn()  # warmup (JIT/cache)
    out = []
    for _ in range(iterations):
        t0 = time.perf_counter()
        fn()
        out.append((time.perf_counter() - t0) * 1000.0)
    return out


def _time_answer_undo(col, deck_id: int, iterations: int):
    """Time answer + immediate undo as paired ops so the deck stays stable and
    the undo stack always holds exactly the grade we just made."""
    col.decks.select(deck_id)
    answer_ms: list[float] = []
    undo_ms: list[float] = []
    misses = 0
    for _ in range(iterations):
        card = col.sched.getCard()
        if card is None:
            misses += 1
            break
        t0 = time.perf_counter()
        col.sched.answerCard(card, 3)  # Good
        answer_ms.append((time.perf_counter() - t0) * 1000.0)

        t0 = time.perf_counter()
        col.undo()
        undo_ms.append((time.perf_counter() - t0) * 1000.0)
    return answer_ms, undo_ms, misses


def run(num_cards: int, iterations: int, verbose: bool = True) -> dict:
    from anki.collection import Collection

    path, gen_stats = ensure_big_deck(num_cards, verbose=verbose)

    # Work on a copy so the cached deck is never mutated by answering.
    tmp = tempfile.mkdtemp(prefix="mcat_bench_run_")
    work = os.path.join(tmp, "collection.anki2")
    shutil.copy2(path, work)

    col = Collection(work)
    try:
        deck_id = col.decks.id("MCAT")
        card_count = len(col.find_cards(""))
        if verbose:
            print(f"\nBenchmarking {card_count:,} cards ({iterations} iters/action) ...\n")

        results: list[dict] = []

        def bench(name: str, fn):
            samples = _time_readonly(fn, iterations)
            summ = _summary(name, samples)
            results.append(summ)
            if verbose:
                print(
                    f"  {name:<22} p50={summ['p50_ms']:>9.3f}ms  "
                    f"p95={summ['p95_ms']:>9.3f}ms  worst={summ['worst_ms']:>9.3f}ms"
                )

        bench("search_all", lambda: col.find_cards("deck:MCAT::*"))
        bench("search_tag", lambda: col.find_cards("tag:mcat::*"))
        bench("next_card", lambda: (col.decks.select(deck_id), col.sched.getCard()))
        bench("topic_mastery", lambda: col.mcat_topic_mastery())
        bench("exam_readiness", lambda: col.mcat_exam_readiness())
        bench("study_recommendation", lambda: col.mcat_study_recommendation())

        # Mutating actions (answer + undo), timed as pairs.
        answer_ms, undo_ms, misses = _time_answer_undo(col, deck_id, iterations)
        for name, samples in (("answer_card", answer_ms), ("undo", undo_ms)):
            summ = _summary(name, samples)
            results.append(summ)
            if verbose:
                print(
                    f"  {name:<22} p50={summ['p50_ms']:>9.3f}ms  "
                    f"p95={summ['p95_ms']:>9.3f}ms  worst={summ['worst_ms']:>9.3f}ms"
                )

        report = {
            "num_cards": num_cards,
            "cards_in_collection": card_count,
            "iterations": iterations,
            "deck_gen": {
                k: gen_stats.get(k)
                for k in (
                    "graded_reviews",
                    "coverage_percent",
                    "perf_cards",
                    "knowledge_cards",
                    "size_bytes",
                )
            },
            "actions": results,
        }
    finally:
        col.close()
        shutil.rmtree(tmp, ignore_errors=True)

    _write_report(report)
    return report


def _write_report(report: dict) -> None:
    os.makedirs(RESULTS_DIR, exist_ok=True)
    n = report["num_cards"]
    json_path = os.path.join(RESULTS_DIR, f"bench_{n}.json")
    md_path = os.path.join(RESULTS_DIR, f"bench_{n}.md")
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)

    lines = [
        f"# MCAT engine benchmark — {report['cards_in_collection']:,}-card deck",
        "",
        f"- Collection: **{report['cards_in_collection']:,} cards**, "
        f"{report['deck_gen'].get('graded_reviews') or 0:,} graded reviews, "
        f"coverage {report['deck_gen'].get('coverage_percent') or 0:.0f}%",
        f"- Iterations per action: **{report['iterations']}** (plus 1 warm-up, not counted)",
        "- All times in milliseconds. `worst` is the single slowest observed call.",
        "",
        "| Action | p50 (ms) | p95 (ms) | worst (ms) | mean (ms) | n |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for a in report["actions"]:
        lines.append(
            f"| `{a['action']}` | {a['p50_ms']:.3f} | {a['p95_ms']:.3f} | "
            f"{a['worst_ms']:.3f} | {a['mean_ms']:.3f} | {a['n']} |"
        )
    lines.append("")
    with open(md_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    print(f"\nWrote {md_path}\n     {json_path}")


def main() -> int:
    parser = argparse.ArgumentParser(description="MCAT 50k-deck engine benchmark (p50/p95/worst).")
    parser.add_argument("-n", "--num-cards", type=int, default=DEFAULT_NUM_CARDS)
    parser.add_argument("-i", "--iterations", type=int, default=40)
    args = parser.parse_args()

    t0 = time.time()
    run(args.num_cards, args.iterations)
    print(f"Benchmark complete in {time.time() - t0:.1f}s total.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
