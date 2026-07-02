# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""MCAT Anki Mastery dashboard window.

Hosts the SvelteKit `mcat` page, which renders the three separate scores
(memory, performance, readiness) with ranges/coverage/abstention, the
best-next-topic recommendation, transfer gaps and XP. All numbers are computed
by the shared Rust engine, so the desktop dashboard and the mobile companion
show identical figures for a synced collection.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

import aqt
import aqt.main
from anki.collection import Collection, OpChanges
from anki.consts import QUEUE_TYPE_REV
from anki.decks import DeckId, FilteredDeckConfig
from anki.utils import int_time
from aqt.qt import *
from aqt.sound import av_player
from aqt.toolbar import BottomBar
from aqt.utils import (
    disable_help_button,
    restoreGeom,
    saveGeom,
    showWarning,
    tooltip,
    tr,
)
from aqt.webview import AnkiWebView, AnkiWebViewKind

# Reusable native filtered deck backing the "Timed interleaved session" block.
# It is rebuilt (not duplicated) on every launch, and being filtered it is
# non-destructive: emptying/deleting it returns every card to its home deck.
MCAT_SESSION_DECK_NAME = "MCAT Session"


def build_mcat_session_deck(col: Collection, card_ids: Sequence[int]) -> DeckId:
    """Create/reuse the "MCAT Session" filtered deck holding exactly `card_ids`,
    then reposition them so the reviewer presents them in the given order.

    Returns the filtered deck's id. Kept free of any Qt dependency so it can be
    exercised directly against a collection. Raises if `card_ids` is empty.
    """
    if not card_ids:
        raise ValueError("no cards to study")

    existing = col.decks.id_for_name(MCAT_SESSION_DECK_NAME)
    deck = col.sched.get_or_create_filtered_deck(deck_id=existing or DeckId(0))
    deck.name = MCAT_SESSION_DECK_NAME
    # Reschedule on: studying updates real scheduling/FSRS/revlog (which feeds the
    # MCAT scores), and cards are returned to their home decks when emptied.
    deck.config.reschedule = True
    # allow_empty avoids a hard error if a race means nothing matches.
    deck.allow_empty = True

    search = "cid:" + ",".join(str(c) for c in card_ids)
    del deck.config.search_terms[:]
    deck.config.search_terms.append(
        FilteredDeckConfig.SearchTerm(
            search=search,
            limit=len(card_ids),
            order=FilteredDeckConfig.SearchTerm.ADDED,
        )
    )

    out = col.sched.add_or_update_filtered_deck(deck)
    did = DeckId(out.id)
    _reposition_session_cards(col, did, card_ids)
    return did


def _reposition_session_cards(
    col: Collection, did: DeckId, card_ids: Sequence[int]
) -> None:
    """Best-effort order fidelity: within a filtered deck a review card's queue
    position is stored in `due`, and the v3 scheduler serves review cards by
    ascending `due`. Rewriting `due` to the interleaved rank therefore reproduces
    the planned sequence for review cards without disturbing real scheduling
    (`odue` is preserved, so emptying/rebuilding restores the true due date).

    Only review-queue cards are touched; new and interday-learning cards are
    positioned by Anki's queue-mixing rules, so cross-type interleaving is
    approximate for those.
    """
    usn = col.usn()
    mod = int_time()
    for rank, cid in enumerate(card_ids):
        col.db.execute(
            "update cards set due=?, usn=?, mod=? where id=? and did=? and queue=?",
            rank,
            usn,
            mod,
            cid,
            did,
            QUEUE_TYPE_REV,
        )


class MCATHomeBottomBar:
    """Web context for the MCAT home bottom bar (used by set_bridge_command)."""

    def __init__(self, mcat_home: MCATHome) -> None:
        self.mcat_home = mcat_home


class MCATHome:
    """MCAT Anki Mastery landing screen, rendered in the main webview.

    Unlike the legacy ``MCATDashboard`` dialog, this is a first-class main-window
    state (``mw.state == "mcat"``) that hosts the SvelteKit ``mcat`` page inside
    ``mw.web`` and provides a bottom bar with "Study now" and "Decks" buttons.
    Its lifecycle mirrors the deck browser / overview states.
    """

    def __init__(self, mw: aqt.main.AnkiQt) -> None:
        self.mw = mw
        self.web = mw.web
        self.bottom = BottomBar(mw, mw.bottomWeb)
        self._refresh_needed = False

    def show(self) -> None:
        av_player.stop_and_clear_queue()
        self.web.set_bridge_command(self._link_handler, self)
        # redraw top bar so the readiness pill / active link reflect this state
        self.mw.toolbar.redraw()
        self.refresh()

    def refresh(self) -> None:
        # The SvelteKit page fetches its own data (readiness/targets/mastery) via
        # the whitelisted McatService RPCs, so a reload is a full refresh.
        self.web.load_sveltekit_page("mcat")
        self._render_bottom()
        self._refresh_needed = False

    def refresh_if_needed(self) -> None:
        if self._refresh_needed:
            self.refresh()

    def op_executed(
        self, changes: OpChanges, handler: object | None, focused: bool
    ) -> bool:
        # Study/review activity changes the scores, so refresh when relevant.
        if changes.study_queues or changes.card or changes.note or changes.tag:
            self._refresh_needed = True

        if focused:
            self.refresh_if_needed()

        return self._refresh_needed

    # Event handlers
    ##########################################################################

    def _link_handler(self, url: str) -> Any:
        if url == "study":
            self._study_now()
        elif url == "decks":
            self.mw.moveToState("deckBrowser")
        elif url.startswith("mcat:start-session"):
            # url form: "mcat:start-session:<1|0>" (interleave on/off)
            interleave = not url.endswith(":0")
            self._start_interleaved_session(interleave)
        return False

    def _study_now(self) -> None:
        # Move into the deck overview (which falls back to the deck browser if no
        # deck is selected); from there the user can begin reviewing.
        self.mw.onOverview()

    def _start_interleaved_session(self, interleave: bool) -> None:
        """Turn the previewed interleaved plan into a real review.

        Recomputes the session on the Qt side with the same interleave flag so
        the order matches the preview deterministically, materialises it as the
        reusable "MCAT Session" filtered deck, then opens the reviewer on it.
        """
        col = self.mw.col
        session = col.mcat_interleaved_session(interleave=interleave)
        card_ids = list(session.card_ids)
        if not card_ids:
            tooltip(tr.studying_no_cards_are_due_yet(), parent=self.mw)
            return

        try:
            did = build_mcat_session_deck(col, card_ids)
        except Exception as exc:
            showWarning(f"Couldn't build the MCAT session deck: {exc}", parent=self.mw)
            return

        # Guarded log so a headless run can confirm the handler fired and the
        # filtered-deck build completed without exceptions.
        print(
            f"MCAT: launched session deck did={did} cards={len(card_ids)} "
            f"interleave={interleave} mode={'interleaved' if session.interleaved else 'blocked'}"
        )

        col.decks.select(did)
        col.startTimebox()
        self.mw.moveToState("review")

    # Bottom bar
    ##########################################################################

    def _render_bottom(self) -> None:
        buf = """
<button title="{study_tip}" onclick='pycmd("study")'>{study}</button>
<button title="{decks_tip}" onclick='pycmd("decks")'>{decks}</button>""".format(
            study=tr.studying_study_now(),
            study_tip=tr.actions_shortcut_key(val="S"),
            decks=tr.actions_decks(),
            decks_tip=tr.actions_shortcut_key(val="D"),
        )
        self.bottom.draw(
            buf=buf,
            link_handler=self._link_handler,
            web_context=MCATHomeBottomBar(self),
        )


class MCATDashboard(QDialog):
    def __init__(self, mw: aqt.main.AnkiQt) -> None:
        QDialog.__init__(self, mw, Qt.WindowType.Window)
        mw.garbage_collect_on_dialog_finish(self)
        self.mw = mw
        self.name = "mcatDashboard"
        disable_help_button(self)
        self.setWindowTitle("MCAT Dashboard")
        self.setMinimumSize(700, 600)
        restoreGeom(self, self.name, default_size=(900, 800))

        self.web = AnkiWebView(kind=AnkiWebViewKind.MCAT_DASHBOARD)
        self.web.setMinimumSize(600, 500)
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.web)
        self.setLayout(layout)

        self.web.set_bridge_command(self._on_bridge_cmd, self)
        self.web.load_sveltekit_page("mcat")
        self.show()
        self.activateWindow()

    def _on_bridge_cmd(self, cmd: str) -> bool:
        return False

    def reject(self) -> None:
        if self.web:
            self.web.cleanup()
            self.web = None  # type: ignore
        saveGeom(self, self.name)
        aqt.dialogs.markClosed("MCATDashboard")
        QDialog.reject(self)

    def closeWithCallback(self, callback: Callable[[], None]) -> None:
        self.reject()
        callback()
