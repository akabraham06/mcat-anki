#!/usr/bin/env python3
# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Refresh the LIVE Anki collection with the freshly built MCAT starter deck.

Run ONLY with the desktop app CLOSED, e.g.:

    PYTHONPATH=out/pylib:pylib out/pyenv/bin/python mcat/migrate_live.py

It removes all existing notes and non-default decks, then imports
``mcat/dist/mcat_starter.apkg`` so the new MCAT::Learning / MCAT::Exam decks
(with CARS passages and auto-graded MCQs) appear on boot. FSRS is left as-is.
"""

from __future__ import annotations

import os

from anki.collection import (
    Collection,
    ImportAnkiPackageOptions,
    ImportAnkiPackageRequest,
)

HOME = os.path.expanduser("~")
COL_PATH = os.path.join(
    HOME, "Library", "Application Support", "Anki2", "User 1", "collection.anki2"
)
APKG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dist", "mcat_starter.apkg")


def main() -> None:
    col = Collection(COL_PATH)
    try:
        before_notes = len(col.find_notes(""))
        before_cards = len(col.find_cards(""))
        before_decks = [d.name for d in col.decks.all_names_and_ids()]
        print(f"BEFORE: {before_notes} notes, {before_cards} cards")
        print(f"BEFORE decks: {before_decks}")

        # Remove every note (this also removes their cards).
        nids = col.find_notes("")
        if nids:
            col.remove_notes(nids)

        # Remove all non-default decks (keep the Default deck, id 1).
        for d in col.decks.all_names_and_ids():
            if d.id != 1:
                col.decks.remove([d.id])

        # Import the freshly built starter package.
        req = ImportAnkiPackageRequest(
            package_path=APKG,
            options=ImportAnkiPackageOptions(
                merge_notetypes=False,
                with_scheduling=False,
                with_deck_configs=False,
            ),
        )
        col.import_anki_package(req)

        after_notes = len(col.find_notes(""))
        after_cards = len(col.find_cards(""))
        after_decks = [d.name for d in col.decks.all_names_and_ids()]
        exam_cards = len(col.find_cards('tag:mcat::exam'))
        learning_cards = len(col.find_cards('deck:"MCAT::Learning"'))
        exam_deck_cards = len(col.find_cards('deck:"MCAT::Exam"'))
        cars_cards = len(col.find_cards('tag:mcat::cars::*'))
        typed_cards = len(col.find_cards('note:MCATTypedLearning'))
        print(f"AFTER: {after_notes} notes, {after_cards} cards")
        print(f"AFTER decks: {after_decks}")
        print(f"  MCAT::Learning cards: {learning_cards}")
        print(f"  MCAT::Exam cards: {exam_deck_cards}")
        print(f"  tagged mcat::exam: {exam_cards}")
        print(f"  CARS cards: {cars_cards}")
        print(f"  typed fill-in cards: {typed_cards}")

        col.save()
    finally:
        col.close()


if __name__ == "__main__":
    main()
