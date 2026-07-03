#!/usr/bin/env python3
# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Register the staged OpenStax MCAT source corpus into the live collection.

    >>> ⚠️  RUN ONLY WITH THE DESKTOP APP CLOSED. <<<
    The collection is a single-writer SQLite database; opening it here while
    Anki is running will fail (database locked) or risk corruption.

What it does
------------
Reads the staged corpus produced by
``mcat/sources/openstax/fetch_openstax.py`` (``index.json`` + ``text/*.txt``)
and, for each source, calls the pylib register-source wrapper
(``Collection.mcat_register_ai_source``) so AI card generation can cite a real,
inspectable, license-attributed source.

It is **idempotent**: a source whose name already exists in the collection is
skipped, so re-running only adds what is new.

How to run later (app closed, built pylib on the path)::

    # from the repo root, with the app quit:
    PYTHONPATH=out/pylib:pylib out/pyenv/bin/python mcat/sources/register_sources.py

    # optional: point at a specific collection / dry-run first
    MCAT_COLLECTION=/path/to/collection.anki2 python mcat/sources/register_sources.py
    MCAT_DRY_RUN=1 python mcat/sources/register_sources.py

Note: registering sources does NOT generate any cards. Generation is a separate,
gated step that additionally requires a working AI provider key (the OpenAI key
was returning 401 at staging time) and, again, the app free to open the
collection.
"""

from __future__ import annotations

import json
import os

from anki.collection import Collection

HERE = os.path.dirname(os.path.abspath(__file__))
INDEX_PATH = os.path.join(HERE, "openstax", "index.json")

# Default collection location (mirrors mcat/migrate_live.py).
HOME = os.path.expanduser("~")
DEFAULT_COL = os.path.join(
    HOME, "Library", "Application Support", "Anki2", "User 1", "collection.anki2"
)
COL_PATH = os.environ.get("MCAT_COLLECTION", DEFAULT_COL)
DRY_RUN = bool(os.environ.get("MCAT_DRY_RUN"))

# Cap the grounding excerpt so each source stays a focused, batch-sized chunk
# and the collection config does not balloon. Long sections are truncated on a
# paragraph boundary. Raise/lower to taste.
MAX_EXCERPT_CHARS = 12000


def _load_index() -> dict:
    with open(INDEX_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def _read_text(rel_path: str) -> str:
    with open(os.path.join(HERE, "openstax", rel_path), encoding="utf-8") as fh:
        return fh.read().strip()


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    cut = text.rfind("\n\n", 0, limit)
    if cut < limit * 0.5:  # no nearby paragraph break; fall back to hard cut
        cut = limit
    return text[:cut].rstrip() + "\n\n[…excerpt truncated for grounding…]"


def _build_excerpt(record: dict) -> str:
    body = _truncate(_read_text(record["text_file"]), MAX_EXCERPT_CHARS)
    # Keep the license/attribution inside the excerpt so it is visible in the
    # source trace and travels with anything grounded in this source.
    return f"{body}\n\n---\nSource & license: {record['attribution']}"


def main() -> None:
    index = _load_index()
    records = index["sources"]
    print(f"Loaded {len(records)} staged sources from {INDEX_PATH}")
    print(f"Collection: {COL_PATH}")
    if DRY_RUN:
        print("DRY RUN — no changes will be written.\n")

    if not os.path.exists(COL_PATH):
        raise SystemExit(f"collection not found: {COL_PATH} (set MCAT_COLLECTION)")

    col = Collection(COL_PATH)
    try:
        existing_names = {s.source_name for s in col.mcat_list_ai_sources()}
        created = skipped = 0
        for rec in records:
            name = rec["name"]
            if name in existing_names:
                skipped += 1
                continue
            if DRY_RUN:
                print(f"WOULD REGISTER: {name}")
                created += 1
                continue
            col.mcat_register_ai_source(
                source_name=name,
                excerpt=_build_excerpt(rec),
                source_section=rec["source_section"],
                # Stable id keyed on the staged source so updates are in place.
                source_id=f"openstax-{rec['source_key']}",
            )
            existing_names.add(name)
            created += 1
            print(f"registered: {name}")

        if not DRY_RUN:
            col.save()
        print(f"\nDone. {created} registered, {skipped} skipped (already present).")
    finally:
        col.close()


if __name__ == "__main__":
    main()
