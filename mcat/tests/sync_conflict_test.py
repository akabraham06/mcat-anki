#!/usr/bin/env python3
# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Sync same-card conflict test (7b) — deterministic merge simulation.

This exercises the exact rule documented in ``docs/sync-conflict-rule.md`` and
implemented in ``rslib/src/sync/collection/chunks.rs``:

* reviews (``revlog``) are **append-only** — ``merge_revlog`` (chunks.rs:168)
  copies every incoming row, each keyed by a globally-unique millisecond id, so
  a sync can never drop or duplicate a review;
* cards use **last-writer-wins by modification time** —
  ``add_or_update_card_if_newer`` (chunks.rs:182) takes an incoming card iff
  ``!existing.usn.is_pending_sync(pending_usn) || existing.mtime < incoming.mtime``.

WHAT THIS TEST DOES / DOES NOT COVER
------------------------------------
A full AnkiWeb (or self-hosted) round-trip is not available in this offline
harness, so this test does **not** run the real network sync client. Instead it
drives the **real Rust engine** to produce genuine ``revlog`` rows and genuine
card-state transitions (via ``get_scheduling_states`` + ``answer_card``), then
reconciles the two devices with a Python function that mirrors
``add_or_update_card_if_newer`` **line for line**. What is real: the collections,
the reviews, the card mtimes and FSRS memory states. What is simulated: the
transport that would carry those rows between the two collections. The merge
*decision* is the engine's documented rule, applied verbatim.

Two scenarios are asserted:

1. **Disjoint reviews ("10 + 10 on two devices").** Two collections branch from
   one shared base; each reviews a distinct set of cards without syncing. The
   union of their revlog rows must contain **every** review **exactly once** (no
   loss, no duplicate id), and each reviewed card's merged state must equal the
   state produced by the device that reviewed it.

2. **Same card reviewed on both devices.** Both devices review the SAME card
   differently while offline. Both reviews survive in the revlog union (two real,
   distinct reviews), and the card's *live* state resolves to the review with the
   **later modification timestamp** — verified to be the strict winner by the
   documented rule.

Run (one command):

    just mcat-sync-conflict

Or directly:

    PYTHONPATH=out/pylib:pylib out/pyenv/bin/python mcat/tests/sync_conflict_test.py
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import time

N_BASE_CARDS = 30
DISJOINT_PER_DEVICE = 10


# --------------------------------------------------------------------------- #
# The merge rule, mirrored verbatim from chunks.rs:182.
# --------------------------------------------------------------------------- #
def incoming_card_wins(existing_mtime: int, existing_pending: bool, incoming_mtime: int) -> bool:
    """Return True iff an incoming card entry should overwrite the existing one.

    Exactly ``add_or_update_card_if_newer`` (rslib/src/sync/collection/chunks.rs:182):

        !existing_card.usn.is_pending_sync(pending_usn) || existing_card.mtime < entry.mtime

    i.e. take the incoming card when the local card has no pending changes, OR the
    incoming card is strictly newer than the local (pending) one.
    """
    return (not existing_pending) or (existing_mtime < incoming_mtime)


# --------------------------------------------------------------------------- #
# Engine helpers (real reviews / real card state).
# --------------------------------------------------------------------------- #
def _review_card(col, cid: int, rating) -> None:
    """Grade a single card by id through the real answering engine, producing a
    genuine revlog row and a card-state transition (mirrors the app). ``rating``
    is a ``CardAnswer`` rating member (AGAIN / HARD / GOOD / EASY)."""
    from anki.scheduler.v3 import CardAnswer

    states = col._backend.get_scheduling_states(cid)
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


def _card_state(col, cid: int) -> dict:
    """A snapshot of the fields sync reconciles for a card."""
    c = col.get_card(cid)
    stability = None
    if c.memory_state is not None:
        stability = round(c.memory_state.stability, 4)
    return {
        "mtime": c.mod,
        "due": c.due,
        "ivl": c.ivl,
        "reps": c.reps,
        "lapses": c.lapses,
        "type": int(c.type),
        "queue": int(c.queue),
        "factor": c.factor,
        "stability": stability,
    }


def _revlog_ids(col) -> set[int]:
    rows = col.db.list("select id from revlog")
    return set(rows)


def _build_base() -> str:
    """Create a shared base collection (FSRS on, no reviews yet) and return its
    path. Both devices are byte-for-byte copies of this file."""
    from anki.collection import Collection

    tmp = tempfile.mkdtemp(prefix="mcat_sync_base_")
    path = os.path.join(tmp, "base.anki2")
    col = Collection(path)
    try:
        col.set_config("fsrs", True)
        basic = col.models.by_name("Basic")
        did = col.decks.id("MCAT::Sync")
        col.decks.select(did)
        conf = col.decks.config_dict_for_deck_id(did)
        conf["new"]["perDay"] = 9999
        conf["rev"]["perDay"] = 9999
        col.decks.update_config(conf)
        for i in range(N_BASE_CARDS):
            note = col.new_note(basic)
            note["Front"] = f"sync base card {i}"
            note["Back"] = "answer"
            note.tags = ["mcat::biobiochem::enzymes"]
            col.add_note(note, did)
    finally:
        col.close()
    return path


def _open(path: str):
    from anki.collection import Collection

    return Collection(path)


def _copy(base_path: str, name: str) -> str:
    tmp = tempfile.mkdtemp(prefix=f"mcat_sync_{name}_")
    dst = os.path.join(tmp, f"{name}.anki2")
    shutil.copy2(base_path, dst)
    return dst


# --------------------------------------------------------------------------- #
# Scenario 1 — disjoint reviews on two devices.
# --------------------------------------------------------------------------- #
def run_disjoint(base_path: str, base_cids: list[int]) -> list[str]:
    failures: list[str] = []
    base_ids = _base_revlog_ids

    a_path = _copy(base_path, "devA")
    b_path = _copy(base_path, "devB")

    a_cids = base_cids[:DISJOINT_PER_DEVICE]
    b_cids = base_cids[DISJOINT_PER_DEVICE : 2 * DISJOINT_PER_DEVICE]

    from anki.scheduler.v3 import CardAnswer

    col_a = _open(a_path)
    try:
        for cid in a_cids:
            _review_card(col_a, cid, CardAnswer.GOOD)
        a_ids = _revlog_ids(col_a) - base_ids
        a_states = {cid: _card_state(col_a, cid) for cid in a_cids}
    finally:
        col_a.close()

    col_b = _open(b_path)
    try:
        for cid in b_cids:
            _review_card(col_b, cid, CardAnswer.HARD)  # a different outcome
        b_ids = _revlog_ids(col_b) - base_ids
        b_states = {cid: _card_state(col_b, cid) for cid in b_cids}
    finally:
        col_b.close()

    # --- Revlog union (append-only merge_revlog) ---
    overlap = a_ids & b_ids
    merged = base_ids | a_ids | b_ids
    expected = len(base_ids) + len(a_ids) + len(b_ids)
    print("\n=== Scenario 1: disjoint reviews (10 + 10 on two devices) ===")
    print(f"  device A reviewed {len(a_cids)} cards -> {len(a_ids)} new revlog rows")
    print(f"  device B reviewed {len(b_cids)} cards -> {len(b_ids)} new revlog rows")
    print(f"  revlog id overlap between devices : {len(overlap)} (must be 0)")
    print(f"  merged unique revlog rows         : {len(merged)} "
          f"(base {len(base_ids)} + {len(a_ids)} + {len(b_ids)} = {expected})")

    if overlap:
        failures.append(f"disjoint: {len(overlap)} revlog ids collided across devices")
    if len(merged) != expected:
        failures.append(
            f"disjoint: merged revlog {len(merged)} != expected {expected} (review lost/dupe)"
        )
    if len(a_ids) != len(a_cids) or len(b_ids) != len(b_cids):
        failures.append("disjoint: a device did not record one revlog row per review")

    # --- Card merge (add_or_update_card_if_newer), disjoint => union ---
    # Merge onto the base: A's changed cards apply (base not pending), then B's.
    merged_cards: dict[int, dict] = {}
    for cid, st in a_states.items():
        # base card is not pending on the receiving side -> incoming (A) wins
        if incoming_card_wins(_base_states[cid]["mtime"], False, st["mtime"]):
            merged_cards[cid] = st
    for cid, st in b_states.items():
        if incoming_card_wins(_base_states[cid]["mtime"], False, st["mtime"]):
            merged_cards[cid] = st

    mism = 0
    for cid, st in a_states.items():
        if merged_cards.get(cid) != st:
            mism += 1
    for cid, st in b_states.items():
        if merged_cards.get(cid) != st:
            mism += 1
    if mism:
        failures.append(f"disjoint: {mism} merged card states did not match their device")
    print(f"  merged card states matched their reviewing device: "
          f"{len(a_states) + len(b_states) - mism}/{len(a_states) + len(b_states)}")

    print("  -> all reviews preserved exactly once; every card shows its single new state"
          if not failures else "  -> FAILURES (see summary)")
    return failures


# --------------------------------------------------------------------------- #
# Scenario 2 — same card reviewed differently on both devices.
# --------------------------------------------------------------------------- #
def run_same_card(base_path: str, conflict_cid: int) -> list[str]:
    failures: list[str] = []
    base_ids = _base_revlog_ids
    base_mtime = _base_states[conflict_cid]["mtime"]

    from anki.scheduler.v3 import CardAnswer

    a_path = _copy(base_path, "devA2")
    b_path = _copy(base_path, "devB2")

    # Device A grades the card "Again" (a lapse-ish outcome).
    col_a = _open(a_path)
    try:
        _review_card(col_a, conflict_cid, CardAnswer.AGAIN)
        a_state = _card_state(col_a, conflict_cid)
        a_ids = _revlog_ids(col_a) - base_ids
    finally:
        col_a.close()

    # Ensure device B's review lands at a strictly later wall-clock second, so its
    # card mtime is strictly greater (mtime is stored in whole seconds).
    while int(time.time()) <= a_state["mtime"]:
        time.sleep(0.05)

    # Device B grades the SAME card "Easy" (a very different resulting state).
    col_b = _open(b_path)
    try:
        _review_card(col_b, conflict_cid, CardAnswer.EASY)
        b_state = _card_state(col_b, conflict_cid)
        b_ids = _revlog_ids(col_b) - base_ids
    finally:
        col_b.close()

    print("\n=== Scenario 2: same card reviewed on both devices ===")
    print(f"  device A (Again): mtime={a_state['mtime']} due={a_state['due']} "
          f"ivl={a_state['ivl']} reps={a_state['reps']} stability={a_state['stability']}")
    print(f"  device B (Easy) : mtime={b_state['mtime']} due={b_state['due']} "
          f"ivl={b_state['ivl']} reps={b_state['reps']} stability={b_state['stability']}")

    # --- Reviews: both preserved, distinct ids ---
    union = a_ids | b_ids
    print(f"  revlog rows: A={len(a_ids)} B={len(b_ids)} union={len(union)} "
          f"overlap={len(a_ids & b_ids)}")
    if len(a_ids) != 1 or len(b_ids) != 1:
        failures.append("same-card: each device should have recorded exactly one review")
    if a_ids & b_ids:
        failures.append("same-card: the two reviews shared a revlog id (would double-count)")
    if len(union) != 2:
        failures.append(f"same-card: expected 2 preserved reviews, got {len(union)}")

    # --- Card state: later mtime wins (last-writer-wins) ---
    if not (a_state["mtime"] < b_state["mtime"]):
        failures.append("same-card: could not establish B as the strictly-later review")

    # Apply the documented rule to the two reconciliations. On the receiving side
    # the local card is pending (it has its own review); B is strictly newer.
    b_beats_a = incoming_card_wins(a_state["mtime"], True, b_state["mtime"])
    a_beats_b = incoming_card_wins(b_state["mtime"], True, a_state["mtime"])
    winner = b_state if (b_beats_a and not a_beats_b) else a_state
    print(f"  rule: B overwrites A = {b_beats_a}; A overwrites B = {a_beats_b} "
          f"-> winner is device {'B (later mtime)' if winner is b_state else 'A'}")

    if winner is not b_state:
        failures.append("same-card: later-mtime review (B) did not win the merge")
    if a_state == b_state:
        failures.append("same-card: the two reviews produced identical state (no real conflict)")
    if winner["due"] != b_state["due"] or winner["ivl"] != b_state["ivl"]:
        failures.append("same-card: winning state does not match device B")

    print("  -> both reviews kept in history; live card state = later-mtime (B) review"
          if not failures else "  -> FAILURES (see summary)")
    return failures


# Module-level snapshots of the shared base, filled in main().
_base_revlog_ids: set[int] = set()
_base_states: dict[int, dict] = {}


def main() -> int:
    base_path = _build_base()

    col = _open(base_path)
    try:
        base_cids = col.find_cards("")
        base_cids.sort()
        global _base_revlog_ids, _base_states
        _base_revlog_ids = _revlog_ids(col)
        _base_states = {cid: _card_state(col, cid) for cid in base_cids}
    finally:
        col.close()

    print(f"Shared base: {len(base_cids)} cards, {len(_base_revlog_ids)} revlog rows "
          "(both devices are copies of this file)")

    failures = []
    failures += run_disjoint(base_path, base_cids)
    # Use a card neither disjoint set touched as the conflict card.
    conflict_cid = base_cids[2 * DISJOINT_PER_DEVICE]
    failures += run_same_card(base_path, conflict_cid)

    print("\n=== Summary ===")
    if failures:
        for f in failures:
            print(f"  - {f}")
        print("\nSYNC CONFLICT TEST FAILED")
        return 1
    print(
        "  Reviews are never lost or double-counted (append-only revlog union), and\n"
        "  the same-card conflict resolves last-writer-wins by modification time,\n"
        "  matching rslib/src/sync/collection/chunks.rs (merge_revlog:168,\n"
        "  add_or_update_card_if_newer:182)."
    )
    print("\nSYNC CONFLICT TEST OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
