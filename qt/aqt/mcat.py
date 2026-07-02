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

from collections.abc import Callable
from typing import Any

import aqt
import aqt.main
from anki.collection import OpChanges
from aqt.qt import *
from aqt.sound import av_player
from aqt.toolbar import BottomBar
from aqt.utils import disable_help_button, restoreGeom, saveGeom, tr
from aqt.webview import AnkiWebView, AnkiWebViewKind


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
        return False

    def _study_now(self) -> None:
        # Move into the deck overview (which falls back to the deck browser if no
        # deck is selected); from there the user can begin reviewing.
        self.mw.onOverview()

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
