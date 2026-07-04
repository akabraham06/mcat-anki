#!/usr/bin/env python3
# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Dynamic MCAT card-generation pipeline.

Turns the staged, openly-licensed OpenStax corpus into custom MCAT flashcard
decks, guided by the embedded MCAT content outline (the taxonomy) and spanning a
WIDE difficulty range.

For every taxonomy topic this pipeline:

1. pulls the topic's registered source excerpt(s) (OpenStax, CC BY-NC-SA 4.0),
2. asks the existing Phase-2 AI generator for cards at each difficulty TIER,
   feeding the taxonomy topic into the prompt so questions match MCAT-style
   scope per topic (not generic trivia),
3. runs every candidate through the existing 9.4 quality checker (this happens
   *inside* ``generate_cards`` — source-grounding, duplicate, taxonomy-tag and
   the model's factual/vagueness/triviality categories),
4. accepts the cards that pass into a deck, tagging each with its
   ``mcat::section::topic`` tag AND a ``difficulty::<tier>`` tag.

Difficulty tiers (see ``rslib/src/mcat/ai/generate.rs``):

* ``recall``  — basic recall / definition.
* ``mcat``    — exam-level application / reasoning (the standard MCAT band).
* ``stretch`` — HARDER than the real MCAT: multi-concept integration, edge
  cases, wider scope.

The per-topic target distribution is explicit and configurable (``--recall``,
``--mcat``, ``--stretch`` or the ``MCAT_DIST`` env var) and is reflected both in
the generation prompt and in the ``difficulty::*`` tags.

Design notes
------------
* **Reuses the existing RPCs** (``mcat_register_ai_source`` /
  ``mcat_generate_cards`` / ``mcat_accept_generated_cards``) rather than a
  parallel path. No card is ever auto-added: each passes the quality gate first.
* **Offline / mock friendly.** With ``MCAT_AI_MOCK=1`` (or ``mcat.ai.mock``
  config) the deterministic mock AI client produces tiered cards with no network
  and no key, so the whole pipeline runs end-to-end and yields a sample deck
  offline. This is how the tests and ``just mcat-build-deck`` run.
* **Graceful degradation.** If a live provider is configured but the key is
  invalid (e.g. the current OpenAI key returns 401), generation reports
  ``ai_available=false`` with a reason; the pipeline prints that reason and
  exits cleanly instead of crashing. Live generation needs a *valid* key.
* **Idempotent + single-writer safe.** The default build runs in a private
  temporary collection and exports ``mcat/dist/mcat_generated.apkg``; because the
  mock is deterministic, re-running reproduces the same deck and it never opens
  the live SQLite database. Passing ``--collection PATH`` writes into a real
  collection instead (RUN WITH THE DESKTOP APP CLOSED) and is made idempotent by
  first removing this pipeline's previously generated notes.
* **Dry-run** (``--dry-run``) does everything except accept/export, reporting the
  planned per-tier counts.

Khan Academy
------------
Khan Academy content is deliberately NOT used: their Terms of Service prohibit
scraping, so it is never fetched here. Grounding relies solely on the staged
OpenStax corpus (CC BY-NC-SA 4.0, provenance in ``mcat/sources/openstax/``). Any
additional source must be openly licensed with recorded provenance/license.

Usage
-----
    # Offline sample deck (deterministic mock, no key/network):
    MCAT_AI_MOCK=1 PYTHONPATH=out/pylib:pylib \\
        out/pyenv/bin/python mcat/build_deck.py

    # See the plan without writing anything:
    MCAT_AI_MOCK=1 PYTHONPATH=out/pylib:pylib \\
        out/pyenv/bin/python mcat/build_deck.py --dry-run

    # Custom distribution and into a real collection (APP CLOSED):
    PYTHONPATH=out/pylib:pylib out/pyenv/bin/python mcat/build_deck.py \\
        --recall 6 --mcat 6 --stretch 3 \\
        --collection "~/Library/Application Support/Anki2/User 1/collection.anki2"
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from dataclasses import dataclass

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(HERE, "sources"))

from register_sources import _build_excerpt, _load_index  # noqa: E402

from anki.collection import (  # noqa: E402
    Collection,
    ExportAnkiPackageOptions,
)

# The three tiers, ordered easy -> hard. Must match DIFFICULTY_TIERS in
# rslib/src/mcat/ai/generate.rs.
TIERS = ("recall", "mcat", "stretch")

# The authoritative MCAT outline. The embedded taxonomy is the per-topic
# question blueprint the Rust engine also scores against.
TAXONOMY_PATH = os.path.join(REPO_ROOT, "rslib", "src", "mcat", "taxonomy.json")

# Default per-topic difficulty distribution. Weighted toward the middle
# (exam-level) band while still covering basic recall and harder-than-MCAT
# stretch, so the deck spans a wide, measurable range. Override on the CLI.
DEFAULT_DISTRIBUTION: dict[str, int] = {"recall": 4, "mcat": 4, "stretch": 2}

DECK_ROOT = "MCAT::Generated"
OUT_DIR = os.path.join(HERE, "dist")
OUT_PATH = os.path.join(OUT_DIR, "mcat_generated.apkg")

# Human labels for the top-level sections (subdeck names).
SECTION_DECK = {
    "chemphys": "Chem-Phys",
    "biobiochem": "Bio-Biochem",
    "psychsoc": "Psych-Soc",
    "cars": "CARS",
}


@dataclass
class Config:
    distribution: dict[str, int]
    dry_run: bool
    collection: str | None
    out_path: str
    tag_prefix: str = "mcat"


def load_taxonomy() -> dict:
    with open(TAXONOMY_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def sources_by_topic(index: dict) -> dict[str, list[dict]]:
    """Group the staged source records by their full ``mcat::section::topic`` tag."""
    grouped: dict[str, list[dict]] = {}
    for rec in index["sources"]:
        grouped.setdefault(rec["topic_key"], []).append(rec)
    return grouped


def split_count(total: int, parts: int) -> list[int]:
    """Split ``total`` cards across ``parts`` sources as evenly as possible."""
    if parts <= 0:
        return []
    base, extra = divmod(total, parts)
    return [base + (1 if i < extra else 0) for i in range(parts)]


def register_topic_sources(col: Collection, records: list[dict]) -> list[str]:
    """Register each staged source (idempotently) and return their source ids."""
    existing = {s.source_id for s in col.mcat_list_ai_sources()}
    ids = []
    for rec in records:
        sid = f"gen-openstax-{rec['source_key']}"
        if sid not in existing:
            col.mcat_register_ai_source(
                source_name=rec["name"],
                excerpt=_build_excerpt(rec),
                source_section=rec["source_section"],
                source_id=sid,
            )
            existing.add(sid)
        ids.append(sid)
    return ids


@dataclass
class TierResult:
    generated: int = 0
    passed: int = 0
    blocked: int = 0
    duplicate: int = 0
    accepted: int = 0


def generate_topic(
    col: Collection,
    cfg: Config,
    topic_tag: str,
    section_key: str,
    source_ids: list[str],
    tallies: dict[str, TierResult],
) -> None:
    """Generate + (optionally) accept cards for one topic across all tiers."""
    deck_name = f"{DECK_ROOT}::{SECTION_DECK.get(section_key, section_key)}"
    for tier in TIERS:
        want = cfg.distribution.get(tier, 0)
        if want <= 0 or not source_ids:
            continue
        per_source = split_count(want, len(source_ids))
        tr = tallies[tier]
        for sid, n in zip(source_ids, per_source):
            if n <= 0:
                continue
            res = col.mcat_generate_cards(
                source_id=sid,
                count=n,
                topic_hint=topic_tag,
                tag_prefix=cfg.tag_prefix,
                difficulty=tier,
            )
            if not res.ai_available:
                raise AiUnavailable(res.unavailable_reason)
            keep = []
            for card in res.cards:
                tr.generated += 1
                status = card.status
                # GENERATED_CARD_STATUS: 1=BLOCKED 2=NEEDS_REVIEW 5=DUPLICATE
                if status == 5:
                    tr.duplicate += 1
                elif status == 2:
                    tr.passed += 1
                    keep.append(card)
                else:
                    tr.blocked += 1
            if keep and not cfg.dry_run:
                resp = col.mcat_accept_generated_cards(
                    cards=keep, deck_name=deck_name, tag_prefix=cfg.tag_prefix
                )
                tr.accepted += resp.created


class AiUnavailable(RuntimeError):
    """Raised when the AI provider reports it cannot generate (e.g. bad key)."""


def clear_previous(col: Collection) -> int:
    """Remove notes previously produced by this pipeline (ai-generated + a
    difficulty tier tag), so a re-run into a real collection is idempotent."""
    nids = col.find_notes("tag:ai-generated (tag:difficulty::recall or "
                          "tag:difficulty::mcat or tag:difficulty::stretch)")
    if nids:
        col.remove_notes(nids)
    return len(nids)


def run(cfg: Config) -> dict:
    taxonomy = load_taxonomy()
    index = _load_index()
    grouped = sources_by_topic(index)

    tallies: dict[str, TierResult] = {t: TierResult() for t in TIERS}
    section_counts: dict[str, int] = {}
    topics_with_sources = 0
    topics_without_sources: list[str] = []

    owns_collection = cfg.collection is None
    if owns_collection:
        tmp = tempfile.mkdtemp(prefix="mcat_gen_")
        col_path = os.path.join(tmp, "collection.anki2")
    else:
        col_path = os.path.expanduser(cfg.collection)
        if not os.path.exists(col_path):
            raise SystemExit(f"collection not found: {col_path}")

    col = Collection(col_path)
    try:
        status = col.mcat_ai_status()
        print(f"AI provider: available={status.available} — {status.reason}")

        removed = 0
        if not owns_collection and not cfg.dry_run:
            removed = clear_previous(col)
            if removed:
                print(f"Removed {removed} previously generated notes (idempotent re-run).")

        for section in taxonomy["sections"]:
            skey = section["key"]
            for topic in section["topics"]:
                topic_tag = f"{cfg.tag_prefix}::{skey}::{topic['key']}"
                records = grouped.get(topic_tag, [])
                if not records:
                    topics_without_sources.append(topic_tag)
                    continue
                topics_with_sources += 1
                source_ids = register_topic_sources(col, records)
                before = sum(t.accepted for t in tallies.values())
                generate_topic(col, cfg, topic_tag, skey, source_ids, tallies)
                after = sum(t.accepted for t in tallies.values())
                section_counts[skey] = section_counts.get(skey, 0) + (after - before)

        if not cfg.dry_run:
            os.makedirs(os.path.dirname(cfg.out_path), exist_ok=True)
            if owns_collection:
                options = ExportAnkiPackageOptions(
                    with_scheduling=False, with_media=False, legacy=True
                )
                col.export_anki_package(out_path=cfg.out_path, options=options, limit=None)
    except AiUnavailable as e:
        print(
            "\nAI generation is unavailable, so no cards were produced:\n"
            f"  reason: {e}\n"
            "  Fix: set a VALID provider key (AI settings / OPENAI_API_KEY), or run\n"
            "  offline with MCAT_AI_MOCK=1 to use the deterministic mock provider.",
            file=sys.stderr,
        )
        return {
            "ai_available": False,
            "reason": str(e),
            "tallies": tallies,
            "section_counts": section_counts,
            "topics_with_sources": topics_with_sources,
            "topics_without_sources": topics_without_sources,
        }
    finally:
        col.close()

    return {
        "ai_available": True,
        "tallies": tallies,
        "section_counts": section_counts,
        "topics_with_sources": topics_with_sources,
        "topics_without_sources": topics_without_sources,
        "owns_collection": owns_collection,
    }


def print_report(cfg: Config, result: dict) -> None:
    tallies: dict[str, TierResult] = result["tallies"]
    total_accepted = sum(t.accepted for t in tallies.values())
    total_generated = sum(t.generated for t in tallies.values())
    print("\n=== MCAT card generation ===")
    print(f"Mode: {'DRY RUN (nothing written)' if cfg.dry_run else 'build'}")
    print(f"Per-topic target distribution: {cfg.distribution}")
    print(
        f"Topics with sources: {result['topics_with_sources']} | "
        f"without sources (skipped): {len(result['topics_without_sources'])}"
    )
    if result["topics_without_sources"]:
        print("  Skipped (no openly-licensed source mapped — e.g. CARS reasoning "
              "topics): " + ", ".join(result["topics_without_sources"]))
    if not result.get("ai_available", True):
        print("  AI unavailable — see message above.")
        return

    print("\nBy difficulty tier:")
    header = "  {:<9} {:>9} {:>7} {:>8} {:>9} {:>9}".format(
        "tier", "generated", "passed", "blocked", "duplicate", "accepted"
    )
    print(header)
    for tier in TIERS:
        t = tallies[tier]
        print(
            "  {:<9} {:>9} {:>7} {:>8} {:>9} {:>9}".format(
                tier, t.generated, t.passed, t.blocked, t.duplicate, t.accepted
            )
        )
    print(f"  {'TOTAL':<9} {total_generated:>9} "
          f"{sum(t.passed for t in tallies.values()):>7} "
          f"{sum(t.blocked for t in tallies.values()):>8} "
          f"{sum(t.duplicate for t in tallies.values()):>9} "
          f"{total_accepted:>9}")

    if not cfg.dry_run:
        print("\nAccepted cards by section:")
        for skey, n in sorted(result["section_counts"].items()):
            print(f"  {SECTION_DECK.get(skey, skey):<12} {n}")
        if result.get("owns_collection"):
            print(f"\nWrote {cfg.out_path} ({total_accepted} cards)")
        else:
            print(f"\nSaved {total_accepted} cards into the collection.")


def parse_args(argv: list[str] | None = None) -> Config:
    p = argparse.ArgumentParser(description="Generate MCAT decks from staged sources.")
    dist = dict(DEFAULT_DISTRIBUTION)
    env_dist = os.environ.get("MCAT_DIST")
    if env_dist:
        # e.g. MCAT_DIST="recall=6,mcat=6,stretch=3"
        for part in env_dist.split(","):
            k, _, v = part.partition("=")
            if k.strip() in dist:
                dist[k.strip()] = int(v)
    p.add_argument("--recall", type=int, default=dist["recall"])
    p.add_argument("--mcat", type=int, default=dist["mcat"])
    p.add_argument("--stretch", type=int, default=dist["stretch"])
    p.add_argument("--dry-run", action="store_true", help="plan only; write nothing")
    p.add_argument(
        "--collection",
        default=os.environ.get("MCAT_COLLECTION"),
        help="write into this collection (APP CLOSED); default builds a temp "
        "collection and exports an .apkg",
    )
    p.add_argument("--out", default=OUT_PATH, help="output .apkg path (temp-build mode)")
    args = p.parse_args(argv)
    return Config(
        distribution={"recall": args.recall, "mcat": args.mcat, "stretch": args.stretch},
        dry_run=args.dry_run,
        collection=args.collection,
        out_path=args.out,
    )


def main(argv: list[str] | None = None) -> int:
    cfg = parse_args(argv)
    result = run(cfg)
    print_report(cfg, result)
    return 0 if result.get("ai_available", True) else 2


if __name__ == "__main__":
    raise SystemExit(main())
