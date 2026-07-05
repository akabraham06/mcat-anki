#!/usr/bin/env python3
# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Build a large, realistic MCAT collection for the performance benchmark.

Creates a **50,000-card** collection whose cards are tagged across the whole
embedded MCAT taxonomy (``rslib/src/mcat/taxonomy.json``), with a realistic mix
of *knowledge* (memory-model) cards and *exam* (performance-model, ``mcat::exam``
tagged) cards, and seeds a deterministic body of review history so that
``mcat_topic_mastery`` / ``mcat_exam_readiness`` return non-trivial scores
(readiness un-abstains: >=100 graded reviews and >=50% coverage).

The result is cached to ``mcat/bench/.cache/big_<n>.anki2`` so the benchmark can
reload it without regenerating. Everything is built in a throwaway ``tempfile``
directory first and only the finished ``.anki2`` is copied into the cache — the
user's real Anki profile/collection is never touched.

Run standalone (regenerates the cache and prints timing):

    PYTHONPATH=out/pylib:pylib out/pyenv/bin/python mcat/bench/gen_big_deck.py

Or import ``ensure_big_deck()`` from the benchmark to generate-or-load.
"""

from __future__ import annotations

import json
import os
import random
import shutil
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
TAXONOMY_PATH = os.path.join(REPO_ROOT, "rslib", "src", "mcat", "taxonomy.json")
CACHE_DIR = os.path.join(HERE, ".cache")

DEFAULT_NUM_CARDS = 50_000
EXAM_TAG = "mcat::exam"
# Roughly one in six cards is an auto-graded exam (performance) question; the
# rest are knowledge (memory) cards. Mirrors a realistic study deck.
PERF_FRACTION = 0.16
# Deterministic seed so the deck (and therefore the benchmark) is reproducible.
SEED = 20240705


def cache_path(num_cards: int) -> str:
    return os.path.join(CACHE_DIR, f"big_{num_cards}.anki2")


def _meta_path(num_cards: int) -> str:
    return os.path.join(CACHE_DIR, f"big_{num_cards}.meta.json")


def load_taxonomy() -> dict:
    with open(TAXONOMY_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def _topic_plan(tax: dict, num_cards: int) -> list[dict]:
    """Flatten the taxonomy into a per-topic plan with a weighted card count.

    Returns a list of dicts: ``full_tag``, ``section_key``, ``target_seconds``,
    ``n_cards`` (>=1 so every topic is covered → ~100% breadth), and a
    deterministic per-topic ``ability`` in ~0.45..0.95 so mastery varies.
    """
    prefix = tax["tag_prefix"]
    topics: list[dict] = []
    total_weight = 0
    for section in tax["sections"]:
        for topic in section["topics"]:
            total_weight += topic["weight"]
            topics.append(
                {
                    "full_tag": f"{prefix}::{section['key']}::{topic['key']}",
                    "section_key": section["key"],
                    "section_name": section["name"],
                    "target_seconds": float(topic["target_seconds"]),
                    "weight": topic["weight"],
                }
            )

    rng = random.Random(SEED)
    # Weighted split of num_cards across topics; guarantee at least 1 each.
    assigned = 0
    for t in topics:
        t["n_cards"] = max(1, round(num_cards * t["weight"] / total_weight))
        assigned += t["n_cards"]
    # Reconcile rounding drift against the largest topics.
    drift = num_cards - assigned
    order = sorted(range(len(topics)), key=lambda i: -topics[i]["n_cards"])
    i = 0
    while drift != 0 and order:
        idx = order[i % len(order)]
        step = 1 if drift > 0 else -1
        if topics[idx]["n_cards"] + step >= 1:
            topics[idx]["n_cards"] += step
            drift -= step
        i += 1

    for t in topics:
        # Ability spread by section so sections score differently.
        base = 0.55 + (hash(t["section_key"]) % 100) / 400.0  # 0.55..0.80
        t["ability"] = max(0.4, min(0.95, rng.gauss(base, 0.08)))
    return topics


def _round_robin_notes(topics: list[dict], num_cards: int) -> list[tuple[dict, bool]]:
    """Emit (topic, is_perf) pairs interleaved across topics so the first cards
    the seeding loop reviews span every section (good coverage fast)."""
    rng = random.Random(SEED + 1)
    remaining = {i: topics[i]["n_cards"] for i in range(len(topics))}
    plan: list[tuple[dict, bool]] = []
    while len(plan) < num_cards and any(v > 0 for v in remaining.values()):
        for i in range(len(topics)):
            if remaining[i] <= 0:
                continue
            remaining[i] -= 1
            is_perf = rng.random() < PERF_FRACTION
            plan.append((topics[i], is_perf))
            if len(plan) >= num_cards:
                break
    return plan


def _raise_deck_limits(col) -> None:
    """Lift the default deck's daily new/review caps so the seeding loop can
    grind through tens of thousands of cards in one pass."""
    for conf in col.decks.all_config():
        conf["new"]["perDay"] = 1_000_000
        conf["rev"]["perDay"] = 1_000_000
        col.decks.update_config(conf)


def _card_topic(col, cid, note_topic, topics):
    """Resolve (topic, is_perf) for a card id, memoised by note id."""
    note = col.get_note(col.get_card(cid).nid)
    key = note.id
    meta = note_topic.get(key)
    if meta is None:
        tag = next(
            (t for t in note.tags if t.startswith("mcat::") and t != EXAM_TAG), ""
        )
        is_perf = EXAM_TAG in note.tags
        meta = (topic_by_tag.get(tag, topics[0]), is_perf)
        note_topic[key] = meta
    return meta


def _seed_reviews(col, topics, deck_ids, note_topic, target_answers, log):
    """Answer cards through the real answering engine (``get_scheduling_states``
    + ``answer_card``), producing genuine revlog rows and card-state transitions
    while keeping the DB fully consistent (so fsck stays clean).

    We drive the answering engine directly per card id rather than through the
    queue so the seed isn't throttled by per-deck daily new limits — every
    answered card graduates New → Learning → Review across a few reps, exactly
    as it would over several study days.

    Ratings follow each topic's ``ability``; response times are sampled around
    the topic target (exam questions sometimes run over → pacing/overtime)."""
    from anki.scheduler.v3 import CardAnswer

    rng = random.Random(SEED + 2)

    all_cids = col.find_cards("")
    rng.shuffle(all_cids)
    # Answer ~90% of the deck; a handful of reps each takes us well past the
    # 100-graded-review readiness gate with a realistic spread of card states.
    n_cards = min(len(all_cids), max(1, target_answers // 3))
    selected = all_cids[:n_cards]

    def pick(states, correct):
        if correct:
            if rng.random() < 0.25:
                return CardAnswer.EASY, states.easy
            return CardAnswer.GOOD, states.good
        if rng.random() < 0.35:
            return CardAnswer.HARD, states.hard
        return CardAnswer.AGAIN, states.again

    answered = knowledge_reviews = perf_reviews = 0
    start = time.time()
    for cid in selected:
        topic, is_perf = _card_topic(col, cid, note_topic, topics)
        # 2–4 reps per card so it graduates and accrues a review trail.
        reps = rng.randint(2, 4)
        for _ in range(reps):
            states = col._backend.get_scheduling_states(cid)
            correct = rng.random() < topic["ability"]
            rating, new_state = pick(states, correct)
            target = topic["target_seconds"]
            secs = max(1.0, rng.gauss(target * 0.85, target * 0.35))
            if is_perf and rng.random() < 0.18:
                secs = target * rng.uniform(1.1, 2.2)
            ans = CardAnswer(
                card_id=cid,
                current_state=states.current,
                new_state=new_state,
                rating=rating,
                answered_at_millis=int(time.time() * 1000),
                milliseconds_taken=int(secs * 1000),
            )
            col.sched.answer_card(ans)
            answered += 1
            if is_perf:
                perf_reviews += 1
            else:
                knowledge_reviews += 1
        if answered and answered % 5000 < reps:
            rate = answered / (time.time() - start)
            log(f"    seeded {answered:,} answers ({rate:,.0f}/s)")

    return {
        "answers": answered,
        "cards_reviewed": len(selected),
        "knowledge_reviews": knowledge_reviews,
        "perf_reviews": perf_reviews,
    }


# Populated by build(); module-level so the seeding helper can resolve topics.
topic_by_tag: dict[str, dict] = {}


def build(num_cards: int = DEFAULT_NUM_CARDS, verbose: bool = True) -> dict:
    """Generate the collection in a tempdir, seed history, and copy it into the
    cache. Returns a stats dict (also written next to the cache as meta json)."""

    def log(msg: str) -> None:
        if verbose:
            print(msg, flush=True)

    from anki.collection import Collection

    tax = load_taxonomy()
    topics = _topic_plan(tax, num_cards)
    topic_by_tag.clear()
    topic_by_tag.update({t["full_tag"]: t for t in topics})
    plan = _round_robin_notes(topics, num_cards)

    tmp = tempfile.mkdtemp(prefix="mcat_bench_gen_")
    col_path = os.path.join(tmp, "collection.anki2")
    col = Collection(col_path)
    stats: dict = {"num_cards": num_cards}
    try:
        t0 = time.time()
        _raise_deck_limits(col)

        basic = col.models.by_name("Basic")
        # One subdeck per section for a realistic tree; parent gathers them all.
        deck_ids = {"parent": col.decks.id("MCAT")}
        for section in tax["sections"]:
            deck_ids[section["key"]] = col.decks.id(f"MCAT::{section['name']}")

        # Cache resolved (topic, is_perf) per note id during seeding so we only
        # pay the note lookup once per card.
        note_topic: dict[int, tuple] = {}
        n_perf = 0
        log(f"Adding {num_cards:,} notes across {len(topics)} topics ...")
        add_start = time.time()
        for i, (topic, is_perf) in enumerate(plan):
            note = col.new_note(basic)
            kind = "Exam" if is_perf else "Recall"
            note["Front"] = f"[{topic['section_key']}/{topic['full_tag'].split('::')[-1]}] {kind} prompt #{i}"
            note["Back"] = f"Answer #{i}"
            note.tags = [topic["full_tag"], EXAM_TAG] if is_perf else [topic["full_tag"]]
            col.add_note(note, deck_ids[topic["section_key"]])
            if is_perf:
                n_perf += 1
            if verbose and (i + 1) % 10_000 == 0:
                rate = (i + 1) / (time.time() - add_start)
                log(f"    added {i + 1:,} notes ({rate:,.0f}/s)")
        add_secs = time.time() - add_start
        stats["add_secs"] = add_secs
        stats["perf_cards"] = n_perf
        stats["knowledge_cards"] = num_cards - n_perf
        log(f"  added {num_cards:,} notes in {add_secs:.1f}s ({n_perf:,} exam / {num_cards - n_perf:,} knowledge)")

        # Seed a solid, deterministic body of review history. ~40% of cards get
        # answered (several passes each for learning graduation), which puts
        # graded reviews well over the 100-review readiness gate.
        target_answers = int(num_cards * 0.9)
        log(f"Seeding review history (target ~{target_answers:,} answers) ...")
        seed_start = time.time()
        seed_stats = _seed_reviews(
            col, topics, deck_ids, note_topic, target_answers, log
        )
        seed_secs = time.time() - seed_start
        stats.update(seed_stats)
        stats["seed_secs"] = seed_secs
        log(
            f"  seeded {seed_stats['answers']:,} answers in {seed_secs:.1f}s "
            f"({seed_stats['knowledge_reviews']:,} knowledge / {seed_stats['perf_reviews']:,} perf)"
        )

        # Sanity: confirm the scores are now non-trivial before caching.
        readiness = col.mcat_exam_readiness()
        stats["graded_reviews"] = readiness.graded_reviews
        stats["coverage_percent"] = readiness.overall_coverage_percent
        stats["memory_available"] = readiness.memory.available
        stats["performance_available"] = readiness.performance.available
        stats["readiness_available"] = readiness.readiness.available
        stats["memory_point"] = readiness.memory.point if readiness.memory.available else None
        stats["readiness_point"] = (
            readiness.readiness.point if readiness.readiness.available else None
        )
        log(
            "  scores: "
            f"graded_reviews={readiness.graded_reviews} "
            f"coverage={readiness.overall_coverage_percent:.0f}% "
            f"memory={'ok' if readiness.memory.available else 'abstain'} "
            f"perf={'ok' if readiness.performance.available else 'abstain'} "
            f"readiness={'ok' if readiness.readiness.available else 'abstain'}"
        )

        col.optimize()
        stats["gen_secs"] = time.time() - t0
    finally:
        col.close()

    os.makedirs(CACHE_DIR, exist_ok=True)
    dest = cache_path(num_cards)
    if os.path.exists(dest):
        os.remove(dest)
    shutil.copy2(col_path, dest)
    stats["cache_path"] = dest
    stats["size_bytes"] = os.path.getsize(dest)
    with open(_meta_path(num_cards), "w", encoding="utf-8") as fh:
        json.dump(stats, fh, indent=2)
    shutil.rmtree(tmp, ignore_errors=True)
    log(f"Cached collection -> {dest} ({stats['size_bytes'] / 1e6:.1f} MB)")
    return stats


def ensure_big_deck(num_cards: int = DEFAULT_NUM_CARDS, force: bool = False, verbose: bool = True) -> tuple[str, dict]:
    """Return (cache_path, stats), generating the cached collection if missing."""
    path = cache_path(num_cards)
    meta = _meta_path(num_cards)
    if not force and os.path.exists(path) and os.path.exists(meta):
        with open(meta, encoding="utf-8") as fh:
            stats = json.load(fh)
        if verbose:
            print(f"Using cached collection {path} ({stats.get('size_bytes', 0) / 1e6:.1f} MB)")
        return path, stats
    stats = build(num_cards, verbose=verbose)
    return path, stats


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Generate the 50k MCAT benchmark deck.")
    parser.add_argument("-n", "--num-cards", type=int, default=DEFAULT_NUM_CARDS)
    parser.add_argument("--force", action="store_true", help="regenerate even if cached")
    args = parser.parse_args()

    t0 = time.time()
    path, stats = ensure_big_deck(args.num_cards, force=args.force)
    print(f"\nDone in {time.time() - t0:.1f}s total. Cache: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
