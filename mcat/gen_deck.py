#!/usr/bin/env python3
# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Build the MCAT starter deck (`mcat_starter.apkg`).

The package contains tagged knowledge cards (Basic notetype -> memory model)
and exam-style performance questions (MCATPerf notetype -> performance model),
so the Rust engine can compute coverage, the three scores, transfer gaps and a
recommendation as soon as the deck is imported and studied.

Run against the built library, e.g.:

    PYTHONPATH=out/pylib:pylib python mcat/gen_deck.py

Output: mcat/dist/mcat_starter.apkg
"""

from __future__ import annotations

import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from content import KNOWLEDGE, PERFORMANCE  # noqa: E402

from anki.collection import Collection, ExportAnkiPackageOptions  # noqa: E402

DECK_NAME = "MCAT"
OUT_DIR = os.path.join(HERE, "dist")
OUT_PATH = os.path.join(OUT_DIR, "mcat_starter.apkg")


def make_perf_notetype(col: Collection):
    mm = col.models
    existing = mm.by_name("MCATPerf")
    if existing:
        return existing
    perf = mm.new("MCATPerf")
    mm.add_field(perf, mm.new_field("Front"))
    mm.add_field(perf, mm.new_field("Back"))
    tmpl = mm.new_template("Card 1")
    tmpl["qfmt"] = "{{Front}}"
    tmpl["afmt"] = "{{FrontSide}}\n\n<hr id=answer>\n\n{{Back}}"
    mm.add_template(perf, tmpl)
    mm.add(perf)
    return mm.by_name("MCATPerf")


def add_note(col, model, deck_id, front, back, tags):
    note = col.new_note(model)
    note["Front"] = front
    note["Back"] = back
    note.tags = list(tags)
    col.add_note(note, deck_id)


def build(path: str) -> tuple[int, int]:
    tmp = tempfile.mkdtemp(prefix="mcat_gen_")
    col_path = os.path.join(tmp, "collection.anki2")
    col = Collection(col_path)
    try:
        deck_id = col.decks.id(DECK_NAME)
        basic = col.models.by_name("Basic")
        perf = make_perf_notetype(col)

        for tag, front, back in KNOWLEDGE:
            add_note(col, basic, deck_id, front, back, [tag])

        for tag, question, answer in PERFORMANCE:
            add_note(col, perf, deck_id, question, answer, [tag, "mcat::perf"])

        os.makedirs(os.path.dirname(path), exist_ok=True)
        options = ExportAnkiPackageOptions(
            with_scheduling=False,
            with_media=False,
            legacy=True,
        )
        col.export_anki_package(out_path=path, options=options, limit=None)
        return len(KNOWLEDGE), len(PERFORMANCE)
    finally:
        col.close()


def main() -> None:
    knowledge, performance = build(OUT_PATH)
    topics = {t for t, *_ in KNOWLEDGE} | {t for t, *_ in PERFORMANCE}
    print(f"Wrote {OUT_PATH}")
    print(
        f"  {knowledge} knowledge cards + {performance} performance questions"
        f" across {len(topics)} topics"
    )


if __name__ == "__main__":
    main()
