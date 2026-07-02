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

import aqt
import aqt.main
from aqt.qt import *
from aqt.utils import disable_help_button, restoreGeom, saveGeom
from aqt.webview import AnkiWebView, AnkiWebViewKind


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
