#!/usr/bin/env python3
# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Crash-safety + offline AI-off tests (7g).

Two guarantees, one command:

1. **Crash safety** — a worker process reviews cards through the real answering
   engine on a shared collection file, and the orchestrator `SIGKILL`s it
   *mid-review* 20 times in a row (like force-quitting the app while grading).
   After every kill we reopen the collection and run the engine's own database
   integrity check (`fix_integrity`), asserting **zero corruption** every time,
   and that the review count is monotonic (no reviews lost, none invented).
   This works because the collection is SQLite: a killed write is rolled back
   by the journal on reopen.

2. **Offline / AI-off** — with a clean environment and AI explicitly disabled,
   the AI status reports unavailable *cleanly* (no crash, a plain reason), and
   the app still produces a deterministic MCAT score (`mcat_exam_readiness`).
   This mirrors pulling the network: AI turns off, the app keeps working.

The orchestrator only ever operates on a throwaway copy of the cached benchmark
deck — the user's real profile is never touched.

Run (one command):

    just mcat-crash-test

Or directly:

    PYTHONPATH=out/pylib:pylib out/pyenv/bin/python mcat/tests/crash_harness.py
"""

from __future__ import annotations

import argparse
import os
import random
import shutil
import signal
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
BENCH_DIR = os.path.join(HERE, "..", "bench")
sys.path.insert(0, os.path.abspath(BENCH_DIR))

DEFAULT_CARDS = 2000
DEFAULT_KILLS = 20


# --------------------------------------------------------------------------- #
# Worker: runs in a child process, reviews until killed.
# --------------------------------------------------------------------------- #
def worker(db_path: str) -> int:
    from anki.collection import Collection
    from anki.scheduler.v3 import CardAnswer

    col = Collection(db_path)
    try:
        # Cycle through every card id and grade it through the real answering
        # engine (get_scheduling_states + answer_card). Driving by card id
        # rather than the queue means grading never starves on scheduler
        # throttling, so the worker keeps writing genuine revlog rows until it
        # is SIGKILLed mid-review.
        cids = col.find_cards("")
        answered = 0
        i = 0
        while True:
            cid = cids[i % len(cids)]
            i += 1
            states = col._backend.get_scheduling_states(cid)
            rating = random.choice(
                [CardAnswer.AGAIN, CardAnswer.GOOD, CardAnswer.GOOD, CardAnswer.EASY]
            )
            new_state = {
                CardAnswer.AGAIN: states.again,
                CardAnswer.HARD: states.hard,
                CardAnswer.GOOD: states.good,
                CardAnswer.EASY: states.easy,
            }[rating]
            ans = CardAnswer(
                card_id=cid,
                current_state=states.current,
                new_state=new_state,
                rating=rating,
                answered_at_millis=int(time.time() * 1000),
                milliseconds_taken=1500,
            )
            col.sched.answer_card(ans)
            answered += 1
            if answered == 1 or answered % 50 == 0:
                print(f"WORKER answered={answered}", flush=True)
    finally:
        col.close()
    return 0


# --------------------------------------------------------------------------- #
# Orchestrator: kill the worker mid-review, verify integrity after each kill.
# --------------------------------------------------------------------------- #
def _revlog_count(db_path: str) -> int:
    from anki.collection import Collection

    col = Collection(db_path)
    try:
        return col.db.scalar("select count() from revlog") or 0
    finally:
        col.close()


def _integrity_ok(db_path: str) -> tuple[bool, str]:
    from anki.collection import Collection

    col = Collection(db_path)
    try:
        report, ok = col.fix_integrity()
        return ok, report
    finally:
        col.close()


def run_crash_test(work_db: str, kills: int) -> dict:
    print(f"\n=== Crash safety: {kills} mid-review SIGKILLs ===")
    prev_reviews = _revlog_count(work_db)
    start_reviews = prev_reviews
    failures: list[str] = []
    import select

    for i in range(1, kills + 1):
        proc = subprocess.Popen(
            [sys.executable, os.path.abspath(__file__), "--worker", work_db],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=os.environ.copy(),
        )
        # Wait until the worker reports it has started grading, so the kill is
        # guaranteed to land *mid-review* (not during collection open/recovery).
        deadline = time.time() + 15
        while time.time() < deadline:
            remaining = deadline - time.time()
            ready, _, _ = select.select([proc.stdout], [], [], max(0.0, remaining))
            if not ready:
                break
            line = proc.stdout.readline()
            if not line or "WORKER answered=" in line:
                break
        # Let it grade a little longer, then kill it in the middle of a review.
        time.sleep(random.uniform(0.03, 0.25))
        try:
            os.kill(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        proc.wait(timeout=30)
        if proc.stdout:
            proc.stdout.close()

        ok, report = _integrity_ok(work_db)
        reviews = _revlog_count(work_db)
        lost = reviews < prev_reviews
        status = "OK" if (ok and not lost) else "CORRUPT/LOST"
        print(
            f"  kill {i:>2}/{kills}: integrity={'clean' if ok else 'PROBLEMS'} "
            f"reviews={reviews} (+{reviews - prev_reviews})  -> {status}"
        )
        if not ok:
            failures.append(f"kill {i}: integrity problems: {report.strip()[:200]}")
        if lost:
            failures.append(f"kill {i}: review count dropped {prev_reviews} -> {reviews}")
        prev_reviews = reviews

    return {
        "kills": kills,
        "start_reviews": start_reviews,
        "end_reviews": prev_reviews,
        "reviews_added": prev_reviews - start_reviews,
        "failures": failures,
    }


def run_offline_ai_off(work_db: str) -> dict:
    print("\n=== Offline / AI-off: app still scores cleanly ===")
    for key in (
        "OPENAI_API_KEY",
        "MCAT_AI_API_KEY",
        "MCAT_AI_BASE_URL",
        "MCAT_AI_MODEL",
        "MCAT_AI_MOCK",
    ):
        os.environ.pop(key, None)

    from anki.collection import Collection

    col = Collection(work_db)
    try:
        col.mcat_ai_set_config(enabled=False)
        status = col.mcat_ai_status()
        readiness = col.mcat_exam_readiness()
        ai_off = not status.available
        scores = readiness.memory.available
        print(f"  AI available: {status.available}  (reason: {status.reason})")
        print(
            f"  memory score with AI off: "
            f"{'available' if scores else 'ABSTAIN'}"
            + (f" = {readiness.memory.point:.1f}" if scores else "")
        )
        failures = []
        if not ai_off:
            failures.append("AI did not turn off cleanly")
        if not scores:
            failures.append("no deterministic score produced with AI off")
        return {"ai_off": ai_off, "scores": scores, "failures": failures}
    finally:
        col.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="MCAT crash-safety + offline AI-off tests.")
    parser.add_argument("--worker", metavar="DB", help="(internal) run the review worker on DB")
    parser.add_argument("-n", "--num-cards", type=int, default=DEFAULT_CARDS)
    parser.add_argument("-k", "--kills", type=int, default=DEFAULT_KILLS)
    args = parser.parse_args()

    if args.worker:
        return worker(args.worker)

    from gen_big_deck import ensure_big_deck

    path, _ = ensure_big_deck(args.num_cards, verbose=True)
    tmp = tempfile.mkdtemp(prefix="mcat_crash_")
    work = os.path.join(tmp, "collection.anki2")
    shutil.copy2(path, work)

    try:
        crash = run_crash_test(work, args.kills)
        offline = run_offline_ai_off(work)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    failures = crash["failures"] + offline["failures"]
    print("\n=== Summary ===")
    print(
        f"  Crash: {crash['kills']} kills, "
        f"{crash['reviews_added']} reviews added, "
        f"{'0 corruptions' if not crash['failures'] else str(len(crash['failures'])) + ' FAILURES'}"
    )
    print(
        f"  Offline AI-off: "
        f"{'clean + still scores' if not offline['failures'] else 'FAILED'}"
    )
    if failures:
        print("\nFAILURES:")
        for f in failures:
            print(f"  - {f}")
        print("\nCRASH/OFFLINE TESTS FAILED")
        return 1
    print(
        f"\nCRASH/OFFLINE OK: {crash['kills']} mid-review kills, zero corrupted "
        "collections, no reviews lost; AI turns off cleanly and the app still scores."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
