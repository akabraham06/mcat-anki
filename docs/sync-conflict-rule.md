# Sync & the same-card conflict rule (7b)

Both the desktop app and the iOS companion link the **same Rust engine**, so they
share one sync client. Sync is Anki's incremental, USN-based collection sync over
AnkiWeb (or a self-hosted server). This document writes down exactly how a
conflict is resolved when the **same card is reviewed on two devices offline** and
then both sync — and why the "20 reviews on two devices" case never loses or
double-counts a review.

## Where the rule lives in code

All of the merge logic is in `rslib/src/sync/collection/chunks.rs`:

- **Reviews (`revlog`) are append-only** — `merge_revlog()` calls
  `add_revlog_entry(&entry, false)` for **every** incoming review
  (`chunks.rs:168`). Each review is a row keyed by a globally-unique id (its
  epoch-millisecond timestamp), so copying rows between devices can never drop a
  review and can never create a duplicate.
- **Cards use last-writer-wins by modification time** —
  `add_or_update_card_if_newer()` (`chunks.rs:182`) applies an incoming card iff:

  ```rust
  !existing_card.usn.is_pending_sync(pending_usn) || existing_card.mtime < entry.mtime
  ```

  i.e. if the local card has **not** been changed since the last sync, the
  incoming version is taken; if it **has** local pending changes, the incoming
  version wins only when it is **newer** (`existing.mtime < incoming.mtime`).
- **Notes** use the identical rule (`add_or_update_note_if_newer`, `chunks.rs:202`).

## The rule, stated plainly

> **Reviews are never lost or double-counted; the card's live scheduling state is
> resolved last-writer-wins by modification time.**

Concretely, when the same card is reviewed on both devices while offline and both
then sync:

1. **Both reviews are preserved.** Each device wrote its own `revlog` row with a
   distinct millisecond id; sync unions the rows. The study log / review counts
   therefore reflect that _two_ reviews genuinely happened — correct, not
   double-counting (they were two real, distinct reviews).
2. **The card's current state has one clear winner:** the review with the **later
   modification timestamp** wins. The card's due date, interval, ease, reps and
   FSRS memory state become those produced by the later review; the earlier
   review remains in the history but does not determine the live state.
3. Ties (identical mtime, which is sub-second-unlikely across two humans) resolve
   in favour of the side already holding local pending changes (the `<` is
   strict).

## The "10 + 10 on two devices" case (different cards)

When the 10 phone cards and 10 desktop cards are **different**, there is no
conflict at all: the two sets of `revlog` rows and the two sets of card rows are
disjoint, so after sync **all 20 reviews land exactly once** and every card shows
its single new state. Nothing is lost and nothing is counted twice.

## How to reproduce / verify

Run `just mcat-sync-conflict` (see `mcat/tests/sync_conflict_test.py`), which:

1. builds two collections from one shared base,
2. reviews 10 distinct cards in each **without syncing**, then asserts the union
   of their reviews has all 20 present once (no loss, no duplicate revlog ids) and
   every card shows its single new state,
3. reviews the **same** card differently in each and asserts the winner is the
   later-`mtime` review, matching the rule above.

The reviews and card states are produced by the **real Rust engine**; a full
AnkiWeb round-trip is not available offline, so the test reconciles the two
devices with a Python function that mirrors `add_or_update_card_if_newer`
(`chunks.rs:182`) verbatim — i.e. it is a deterministic **merge simulation of the
documented rule**, not a live network sync. The test's module docstring states
this explicitly.

## Caveat

Media sync is currently disabled on the mobile build, so images/audio are not
transferred to the phone yet (card text, scheduling and reviews are). This does
not affect scheduling-conflict resolution.
