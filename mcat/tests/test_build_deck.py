#!/usr/bin/env python3
# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Deterministic tests for the MCAT card-generation pipeline (``build_deck.py``).

Runs entirely OFFLINE via the deterministic mock AI provider (``MCAT_AI_MOCK``),
so there is no network and no key. Covers the difficulty tiering + tagging and
the deck-assembly behaviour that are the heart of the pipeline.

Run standalone:

    MCAT_AI_MOCK=1 PYTHONPATH=out/pylib:pylib \\
        out/pyenv/bin/python mcat/tests/test_build_deck.py

or via ``just mcat-build-deck-test`` (which builds pylib + sets the env).
"""

from __future__ import annotations

import os
import sys
import tempfile

os.environ.setdefault("MCAT_AI_MOCK", "1")

HERE = os.path.dirname(os.path.abspath(__file__))
MCAT_DIR = os.path.dirname(HERE)
sys.path.insert(0, MCAT_DIR)

import build_deck as bd  # noqa: E402

from anki.collection import Collection  # noqa: E402


def _new_collection() -> tuple[Collection, str]:
    tmp = tempfile.mkdtemp(prefix="mcat_pipeline_test_")
    path = os.path.join(tmp, "c.anki2")
    Collection(path).close()
    return path


def _cfg(path: str, **overrides) -> bd.Config:
    base = dict(
        distribution={"recall": 2, "mcat": 2, "stretch": 1},
        dry_run=False,
        collection=path,
        out_path=os.path.join(tempfile.mkdtemp(), "out.apkg"),
    )
    base.update(overrides)
    return bd.Config(**base)


def test_split_count_is_even_and_conserves_total() -> None:
    assert bd.split_count(4, 2) == [2, 2]
    assert bd.split_count(5, 2) == [3, 2]
    assert bd.split_count(2, 3) == [1, 1, 0]
    assert bd.split_count(0, 3) == [0, 0, 0]
    assert bd.split_count(7, 0) == []
    for total in range(0, 13):
        for parts in range(1, 6):
            parts_list = bd.split_count(total, parts)
            assert sum(parts_list) == total
            assert len(parts_list) == parts


def test_tiers_match_rust_vocabulary() -> None:
    # Guards the Python/Rust contract: difficulty::<tier> tags + prompt tiers.
    assert bd.TIERS == ("recall", "mcat", "stretch")


def test_pipeline_generates_tagged_tiered_cards() -> None:
    path = _new_collection()
    dist = {"recall": 3, "mcat": 3, "stretch": 2}
    result = bd.run(_cfg(path, distribution=dist))
    assert result["ai_available"], "mock provider must be available"

    tallies = result["tallies"]
    # Every tier produced and accepted at least one card => wide range covered.
    for tier in bd.TIERS:
        assert tallies[tier].generated > 0, f"{tier}: nothing generated"
        assert tallies[tier].accepted > 0, f"{tier}: nothing accepted"

    # CARS topics have no openly-licensed source and must be skipped, not errored.
    assert any(t.startswith("mcat::cars::") for t in result["topics_without_sources"])

    col = Collection(path)
    try:
        total = len(col.find_cards("tag:ai-generated"))
        by_tier = {
            tier: len(col.find_cards(f"tag:difficulty::{tier}")) for tier in bd.TIERS
        }
        assert total == sum(by_tier.values()) == sum(t.accepted for t in tallies.values())
        # Each accepted card carries: ai-generated + a difficulty tier + a real
        # mcat topic tag.
        for nid in col.find_notes("tag:ai-generated"):
            tags = col.get_note(nid).tags
            assert "ai-generated" in tags
            assert sum(1 for t in tags if t.startswith("difficulty::")) == 1
            assert any(t.startswith("mcat::") and t.count("::") == 2 for t in tags)
    finally:
        col.close()

    print(f"  tiered cards: {by_tier} (total {total})")


def test_pipeline_is_idempotent_into_a_collection() -> None:
    path = _new_collection()
    cfg = _cfg(path)
    first = sum(t.accepted for t in bd.run(cfg)["tallies"].values())
    second = sum(t.accepted for t in bd.run(cfg)["tallies"].values())
    assert first == second, "re-run should be deterministic"
    col = Collection(path)
    try:
        total = len(col.find_cards("tag:ai-generated"))
    finally:
        col.close()
    assert total == second, "re-running must not accumulate duplicate notes"


def test_dry_run_writes_nothing() -> None:
    path = _new_collection()
    result = bd.run(_cfg(path, dry_run=True))
    assert result["ai_available"]
    # Dry run reports generated candidates but accepts nothing.
    assert sum(t.generated for t in result["tallies"].values()) > 0
    assert sum(t.accepted for t in result["tallies"].values()) == 0
    col = Collection(path)
    try:
        assert len(col.find_cards("tag:ai-generated")) == 0
    finally:
        col.close()


TESTS = [
    test_split_count_is_even_and_conserves_total,
    test_tiers_match_rust_vocabulary,
    test_pipeline_generates_tagged_tiered_cards,
    test_pipeline_is_idempotent_into_a_collection,
    test_dry_run_writes_nothing,
]


def main() -> int:
    failed = 0
    for t in TESTS:
        try:
            t()
            print(f"PASS {t.__name__}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"FAIL {t.__name__}: {e}")
    print(f"\n{len(TESTS) - failed}/{len(TESTS)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
