# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""MCAT AI Card Studio (Phase 2, feature 9.3 + 9.4 + 9.9 desktop UI).

A single Qt window that lets the user:

* register / select / inspect a named grounding source (9.3, 9.9 fake-source
  defence — generation is impossible without a registered source),
* generate N source-grounded card candidates,
* review a per-card queue showing the quality-checker verdict, the category
  breakdown, and the inspectable source trace,
* accept passing candidates → real, ``ai-generated``-tagged notes in the MCAT
  deck, or reject them.

Everything degrades gracefully when AI is off/offline/erroring: the window
still opens, shows an "AI unavailable" pill with the reason, and disables the
generate action (9.9). No API key is ever hardcoded — it is configured through
the AI Settings dialog and stored in the collection config.
"""

from __future__ import annotations

from concurrent.futures import Future
from typing import Any

import aqt
import aqt.main
from anki.mcat_pb2 import (
    GENERATED_CARD_STATUS_ACCEPTED,
    GENERATED_CARD_STATUS_BLOCKED,
    GENERATED_CARD_STATUS_DUPLICATE,
    GENERATED_CARD_STATUS_NEEDS_REVIEW,
    GeneratedCard,
)
from aqt.operations import QueryOp
from aqt.qt import *
from aqt.utils import (
    disable_help_button,
    restoreGeom,
    saveGeom,
    showInfo,
    showWarning,
    tooltip,
)

_STATUS_LABEL = {
    GENERATED_CARD_STATUS_BLOCKED: "Blocked",
    GENERATED_CARD_STATUS_NEEDS_REVIEW: "Needs review",
    GENERATED_CARD_STATUS_ACCEPTED: "Accepted",
    GENERATED_CARD_STATUS_DUPLICATE: "Duplicate",
}
_STATUS_COLOR = {
    GENERATED_CARD_STATUS_BLOCKED: "#c0392b",
    GENERATED_CARD_STATUS_NEEDS_REVIEW: "#2d6cdf",
    GENERATED_CARD_STATUS_ACCEPTED: "#1e8e3e",
    GENERATED_CARD_STATUS_DUPLICATE: "#b8860b",
}


class AiSettingsDialog(QDialog):
    """Small modal for the provider-agnostic (OpenAI-compatible) AI config."""

    def __init__(self, parent: QWidget, mw: aqt.main.AnkiQt) -> None:
        super().__init__(parent)
        self.mw = mw
        disable_help_button(self)
        self.setWindowTitle("MCAT AI Settings")
        self.setMinimumWidth(460)

        cfg = mw.col.mcat_ai_get_config()

        self.base_url = QLineEdit(cfg.base_url)
        self.base_url.setPlaceholderText("https://api.openai.com/v1")
        self.model = QLineEdit(cfg.model)
        self.model.setPlaceholderText("gpt-4o-mini")
        self.api_key = QLineEdit()
        self.api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key.setPlaceholderText(
            cfg.api_key if cfg.api_key_set else "not set — paste a key"
        )
        self.cutoff = QDoubleSpinBox()
        self.cutoff.setRange(0.1, 1.0)
        self.cutoff.setSingleStep(0.05)
        self.cutoff.setDecimals(2)
        self.cutoff.setValue(cfg.checker_cutoff or 0.7)
        self.enabled = QCheckBox("Enable AI features")
        self.enabled.setChecked(cfg.enabled)

        form = QFormLayout()
        form.addRow("Base URL", self.base_url)
        form.addRow("Model", self.model)
        form.addRow("API key", self.api_key)
        form.addRow("Checker cutoff", self.cutoff)
        form.addRow("", self.enabled)

        hint = QLabel(
            "Works with any OpenAI-compatible endpoint (OpenAI, or a local "
            "Ollama server at http://localhost:11434/v1). The key is stored in "
            "this collection's config and never leaves your device except to "
            "your chosen provider. Leave the key blank to keep the existing one; "
            'enter "-" to clear it.'
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: gray; font-size: 11px;")

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        qconnect(buttons.accepted, self._save)
        qconnect(buttons.rejected, self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(hint)
        layout.addWidget(buttons)

    def _save(self) -> None:
        self.mw.col.mcat_ai_set_config(
            base_url=self.base_url.text().strip(),
            model=self.model.text().strip(),
            api_key=self.api_key.text().strip(),
            checker_cutoff=self.cutoff.value(),
            enabled=self.enabled.isChecked(),
        )
        self.accept()


class NewSourceDialog(QDialog):
    """Register a named source (name, section/page, excerpt) for grounding."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        disable_help_button(self)
        self.setWindowTitle("Register source")
        self.setMinimumWidth(520)

        self.name = QLineEdit()
        self.name.setPlaceholderText("e.g. Kaplan Biochemistry")
        self.section = QLineEdit()
        self.section.setPlaceholderText("e.g. Ch. 9, p. 312")
        self.excerpt = QPlainTextEdit()
        self.excerpt.setPlaceholderText(
            "Paste the source text to ground generation in. Cards can only cite "
            "text that appears here."
        )
        self.excerpt.setMinimumHeight(180)

        form = QFormLayout()
        form.addRow("Name", self.name)
        form.addRow("Section / page", self.section)
        form.addRow("Excerpt", self.excerpt)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        qconnect(buttons.accepted, self._accept)
        qconnect(buttons.rejected, self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def _accept(self) -> None:
        if not self.name.text().strip() or not self.excerpt.toPlainText().strip():
            showWarning("A source needs both a name and a non-empty excerpt.", parent=self)
            return
        self.accept()

    def values(self) -> tuple[str, str, str]:
        return (
            self.name.text().strip(),
            self.excerpt.toPlainText().strip(),
            self.section.text().strip(),
        )


class MCATAiStudio(QDialog):
    """The AI Card Studio window (registered in the dialog manager)."""

    def __init__(self, mw: aqt.main.AnkiQt) -> None:
        QDialog.__init__(self, mw, Qt.WindowType.Window)
        mw.garbage_collect_on_dialog_finish(self)
        self.mw = mw
        self.name = "MCATAiStudio"
        self._candidates: list[GeneratedCard] = []
        disable_help_button(self)
        self.setWindowTitle("MCAT AI Card Studio")
        self.setMinimumSize(860, 640)
        restoreGeom(self, self.name, default_size=(1000, 720))

        self._build_ui()
        self._reload_sources()
        self._refresh_status()
        self.show()
        self.activateWindow()

    # UI construction
    ##########################################################################

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        # Status / settings bar.
        bar = QHBoxLayout()
        self.status_pill = QLabel("Checking AI…")
        self.status_pill.setStyleSheet(self._pill_style("#666"))
        bar.addWidget(self.status_pill)
        bar.addStretch()
        settings_btn = QPushButton("AI Settings…")
        qconnect(settings_btn.clicked, self._open_settings)
        bar.addWidget(settings_btn)
        root.addLayout(bar)

        # Source + generation controls.
        controls = QHBoxLayout()
        controls.addWidget(QLabel("Source:"))
        self.source_combo = QComboBox()
        self.source_combo.setMinimumWidth(240)
        qconnect(self.source_combo.currentIndexChanged, lambda _: self._show_source_trace())
        controls.addWidget(self.source_combo)
        new_src = QPushButton("New…")
        qconnect(new_src.clicked, self._new_source)
        controls.addWidget(new_src)
        self.remove_src = QPushButton("Remove")
        qconnect(self.remove_src.clicked, self._remove_source)
        controls.addWidget(self.remove_src)

        controls.addSpacing(16)
        controls.addWidget(QLabel("Topic tag:"))
        self.topic_hint = QLineEdit()
        self.topic_hint.setPlaceholderText("mcat::biobiochem::enzymes")
        self.topic_hint.setMinimumWidth(200)
        controls.addWidget(self.topic_hint)
        controls.addWidget(QLabel("Count:"))
        self.count = QSpinBox()
        self.count.setRange(1, 20)
        self.count.setValue(5)
        controls.addWidget(self.count)
        self.generate_btn = QPushButton("Generate")
        qconnect(self.generate_btn.clicked, self._generate)
        controls.addWidget(self.generate_btn)
        controls.addStretch()
        root.addLayout(controls)

        # Split: candidate list | detail (trace + categories).
        splitter = QSplitter(Qt.Orientation.Horizontal)

        self.card_list = QListWidget()
        self.card_list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        qconnect(self.card_list.currentRowChanged, self._on_row_changed)
        splitter.addWidget(self.card_list)

        self.detail = QTextBrowser()
        self.detail.setOpenExternalLinks(False)
        splitter.addWidget(self.detail)
        splitter.setSizes([420, 520])
        root.addWidget(splitter, 1)

        # Accept / reject actions.
        actions = QHBoxLayout()
        self.summary = QLabel("")
        self.summary.setStyleSheet("color: gray;")
        actions.addWidget(self.summary)
        actions.addStretch()
        self.reject_btn = QPushButton("Reject")
        qconnect(self.reject_btn.clicked, self._reject_current)
        actions.addWidget(self.reject_btn)
        self.accept_btn = QPushButton("Accept checked → MCAT deck")
        qconnect(self.accept_btn.clicked, self._accept_checked)
        actions.addWidget(self.accept_btn)
        root.addLayout(actions)

        close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        qconnect(close.rejected, self.reject)
        root.addWidget(close)

    @staticmethod
    def _pill_style(color: str) -> str:
        return (
            f"background:{color}; color:white; border-radius:9px; padding:3px 10px; "
            "font-weight:600;"
        )

    # Status + sources
    ##########################################################################

    def _refresh_status(self) -> None:
        status = self.mw.col.mcat_ai_status()
        if status.available:
            self.status_pill.setText(f"AI ready · {status.model}")
            self.status_pill.setStyleSheet(self._pill_style("#1e8e3e"))
        else:
            self.status_pill.setText("AI unavailable")
            self.status_pill.setStyleSheet(self._pill_style("#c0392b"))
        self.status_pill.setToolTip(status.reason)
        # 9.9: with AI off/unavailable, generation is disabled but the window,
        # sources, and review queue all keep working.
        has_source = self.source_combo.count() > 0
        self.generate_btn.setEnabled(status.available and has_source)
        if not status.available:
            self.generate_btn.setToolTip(status.reason)
        elif not has_source:
            self.generate_btn.setToolTip("Register a source first.")
        else:
            self.generate_btn.setToolTip("")

    def _reload_sources(self, select_id: str | None = None) -> None:
        sources = list(self.mw.col.mcat_list_ai_sources().sources)
        self.source_combo.blockSignals(True)
        self.source_combo.clear()
        for src in sources:
            label = src.source_name
            if src.source_section:
                label += f" ({src.source_section})"
            self.source_combo.addItem(label, src.source_id)
        self.source_combo.blockSignals(False)
        if select_id:
            idx = self.source_combo.findData(select_id)
            if idx >= 0:
                self.source_combo.setCurrentIndex(idx)
        self.remove_src.setEnabled(self.source_combo.count() > 0)
        self._sources_by_id = {s.source_id: s for s in sources}
        self._show_source_trace()

    def _current_source_id(self) -> str | None:
        if self.source_combo.count() == 0:
            return None
        return self.source_combo.currentData()

    def _show_source_trace(self) -> None:
        if not self._candidates:
            sid = self._current_source_id()
            src = self._sources_by_id.get(sid) if sid else None
            if src:
                self.detail.setHtml(
                    f"<h3>Source trace</h3><p><b>{_esc(src.source_name)}</b> "
                    f"{_esc(src.source_section)}</p>"
                    f"<pre style='white-space:pre-wrap'>{_esc(src.excerpt)}</pre>"
                )
            else:
                self.detail.setHtml(
                    "<p style='color:gray'>Register a source, then generate "
                    "candidate cards. Nothing is added to your deck until you "
                    "accept it.</p>"
                )

    def _open_settings(self) -> None:
        if AiSettingsDialog(self, self.mw).exec():
            self._refresh_status()

    def _new_source(self) -> None:
        dlg = NewSourceDialog(self)
        if not dlg.exec():
            return
        name, excerpt, section = dlg.values()
        result = self.mw.col.mcat_register_ai_source(
            source_name=name, excerpt=excerpt, source_section=section
        )
        sources = list(result.sources)
        new_id = sources[-1].source_id if sources else None
        self._reload_sources(select_id=new_id)
        self._refresh_status()

    def _remove_source(self) -> None:
        sid = self._current_source_id()
        if not sid:
            return
        self.mw.col.mcat_remove_ai_source(source_id=sid)
        self._reload_sources()
        self._refresh_status()

    # Generation
    ##########################################################################

    def _generate(self) -> None:
        sid = self._current_source_id()
        if not sid:
            showWarning("Register and select a source first.", parent=self)
            return
        count = self.count.value()
        topic = self.topic_hint.text().strip()

        def op(col: Any) -> Any:
            return col.mcat_generate_cards(
                source_id=sid, count=count, topic_hint=topic
            )

        QueryOp(parent=self, op=op, success=self._on_generated).with_progress(
            "Generating source-grounded cards…"
        ).run_in_background()

    def _on_generated(self, result: Any) -> None:
        if not result.ai_available:
            self._candidates = []
            self._populate_list()
            showWarning(
                f"AI unavailable: {result.unavailable_reason}", parent=self
            )
            self._refresh_status()
            return
        self._candidates = list(result.cards)
        self._populate_list()
        if not self._candidates:
            tooltip("No candidates were produced.", parent=self)

    def _populate_list(self) -> None:
        self.card_list.clear()
        accepted = 0
        blocked = 0
        for card in self._candidates:
            item = QListWidgetItem()
            passed = card.status == GENERATED_CARD_STATUS_NEEDS_REVIEW
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            # Only auto-checkable candidates that passed the gate can be accepted.
            item.setCheckState(
                Qt.CheckState.Checked if passed else Qt.CheckState.Unchecked
            )
            if not passed:
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsUserCheckable)
                blocked += 1
            else:
                accepted += 1
            label = _STATUS_LABEL.get(card.status, "?")
            color = _STATUS_COLOR.get(card.status, "#666")
            item.setText(f"[{label}]  {card.question}")
            item.setForeground(QColor(color))
            self.card_list.addItem(item)
        self.summary.setText(
            f"{len(self._candidates)} candidates · {accepted} passing · "
            f"{blocked} blocked/duplicate"
        )
        if self._candidates:
            self.card_list.setCurrentRow(0)

    def _on_row_changed(self, row: int) -> None:
        if row < 0 or row >= len(self._candidates):
            return
        card = self._candidates[row]
        self.detail.setHtml(self._card_detail_html(card))

    def _card_detail_html(self, card: GeneratedCard) -> str:
        q = card.quality
        rows = []
        for cat in q.categories:
            mark = "✓" if cat.passed else "✗"
            col = "#1e8e3e" if cat.passed else "#c0392b"
            rows.append(
                f"<tr><td style='color:{col}'>{mark}</td><td>{_esc(cat.label)}</td>"
                f"<td>{cat.score:.2f}</td><td style='color:gray'>{_esc(cat.reason)}</td></tr>"
            )
        cats = "".join(rows)
        verdict_color = "#1e8e3e" if q.passed else "#c0392b"
        return f"""
        <h3>{_esc(card.question)}</h3>
        <p><b>Answer:</b> {_esc(card.answer)}</p>
        <p><b>Topic:</b> {_esc(card.topic_tag) or '—'} &nbsp; <b>Difficulty:</b> {_esc(card.difficulty) or '—'}</p>
        <p><b>Verdict:</b> <span style='color:{verdict_color};font-weight:600'>{_esc(q.verdict)}</span>
           &nbsp; overall {q.overall_score:.2f} / cutoff {q.cutoff:.2f}
           {'· DUPLICATE' if q.duplicate else ''}</p>
        <table cellpadding='4' style='border-collapse:collapse'>
          <tr><th></th><th align='left'>Category</th><th>Score</th><th align='left'>Reason</th></tr>
          {cats}
        </table>
        <h4>Source trace</h4>
        <p><b>{_esc(card.source_name)}</b> {_esc(card.source_section)}</p>
        <pre style='white-space:pre-wrap;background:#f5f5f5;padding:8px'>{_esc(card.source_excerpt)}</pre>
        """

    # Accept / reject
    ##########################################################################

    def _reject_current(self) -> None:
        row = self.card_list.currentRow()
        if 0 <= row < len(self._candidates):
            self._candidates.pop(row)
            self._populate_list()

    def _accept_checked(self) -> None:
        chosen: list[GeneratedCard] = []
        for i in range(self.card_list.count()):
            if self.card_list.item(i).checkState() == Qt.CheckState.Checked:
                chosen.append(self._candidates[i])
        if not chosen:
            tooltip("Check one or more passing cards to accept.", parent=self)
            return

        def op(col: Any) -> Any:
            return col.mcat_accept_generated_cards(cards=chosen)

        def done(result: Any) -> None:
            showInfo(
                f"Added {result.created} AI-generated card(s) to the MCAT deck "
                f"(skipped {result.skipped}). They are tagged 'ai-generated' and "
                "will sync to mobile.",
                parent=self,
            )
            # Clear the accepted cards from the queue.
            self._candidates = [c for c in self._candidates if c not in chosen]
            self._populate_list()

        QueryOp(parent=self, op=op, success=done).with_progress(
            "Creating notes…"
        ).run_in_background()

    def reject(self) -> None:
        saveGeom(self, self.name)
        aqt.dialogs.markClosed("MCATAiStudio")
        QDialog.reject(self)

    def closeWithCallback(self, callback: Any) -> None:
        self.reject()
        callback()


def _esc(text: str) -> str:
    return (
        (text or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
