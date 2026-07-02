#!/usr/bin/env python3
# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Build the MCAT starter deck (`mcat_starter.apkg`).

The package is split into two subdecks:

* ``MCAT::Learning`` — recall cards that feed the *memory* model: plain Basic
  cards plus native typed fill-in cards (``{{type:Answer}}``).
* ``MCAT::Exam`` — auto-graded, timed exam cards that feed the *performance*
  model: multiple-choice ``MCATExam`` cards and ``MCATCarsPassage`` reading
  cards. Every exam card carries the ``mcat::exam`` marker tag so the reviewer
  can gate the countdown timer + click-to-grade behaviour to exam cards only,
  and so the Rust engine treats their reviews as performance evidence.

All cards keep their ``mcat::<section>::<topic>`` tag so the Rust engine maps
them onto the embedded taxonomy for coverage, the three scores, transfer gaps,
pacing and a recommendation as soon as the deck is imported and studied.

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

from content import (  # noqa: E402
    CARS_PASSAGES,
    EXAM_MCQ,
    KNOWLEDGE,
    LEARNING_TYPED,
)

from anki.collection import Collection, ExportAnkiPackageOptions  # noqa: E402

LEARNING_DECK = "MCAT::Learning"
EXAM_DECK = "MCAT::Exam"
EXAM_TAG = "mcat::exam"
OUT_DIR = os.path.join(HERE, "dist")
OUT_PATH = os.path.join(OUT_DIR, "mcat_starter.apkg")


# Shared styling for the multiple-choice exam cards + CARS passages.
MCQ_CSS = """
.card { font-family: -apple-system, Helvetica, Arial, sans-serif; font-size: 18px;
  color: var(--text-fg, #202020); background: var(--canvas, #fff);
  text-align: left; max-width: 46em; margin: 0 auto; padding: 0 0.5em; }
.mcat-passage { line-height: 1.5; margin-bottom: 1.1em; }
.mcat-passage p { margin: 0 0 0.7em; }
.mcat-topic { font-size: 0.72em; text-transform: uppercase; letter-spacing: 0.05em;
  color: #888; margin-bottom: 0.4em; }
.mcat-q { font-weight: 600; margin-bottom: 0.8em; line-height: 1.4; }
.mcat-options { display: flex; flex-direction: column; gap: 0.5em; }
.mcat-opt { display: flex; align-items: baseline; gap: 0.6em; text-align: left;
  padding: 0.7em 0.9em; border: 1px solid #c9c9c9; border-radius: 8px;
  background: #f7f7f8; color: inherit; font-size: 1em; cursor: pointer;
  transition: background 0.12s, border-color 0.12s; }
.mcat-opt:hover:not(:disabled) { background: #eef2ff; border-color: #9db2ff; }
.mcat-opt:disabled { cursor: default; }
.mcat-letter { font-weight: 700; min-width: 1.2em; }
.mcat-opt.mcat-correct { background: #e3f6e8; border-color: #2e7d32; }
.mcat-opt.mcat-wrong { background: #fde8e8; border-color: #c62828; }
.mcat-explanation { display: none; margin-top: 1.1em; padding-top: 0.9em;
  border-top: 1px solid #ddd; }
.mcat-explanation.mcat-show { display: block; }
.mcat-verdict { font-weight: 700; font-size: 1.1em; margin-bottom: 0.3em; }
.mcat-verdict.mcat-ok { color: #2e7d32; }
.mcat-verdict.mcat-bad { color: #c62828; }
.mcat-answer-line { margin-bottom: 0.5em; }
.mcat-why { line-height: 1.45; color: #333; }
.mcat-ease-note { margin-top: 0.6em; font-size: 0.82em; color: #666; font-style: italic; }
.mcat-next { margin-top: 1em; padding: 0.55em 1.4em; font-size: 1em; font-weight: 600;
  border: none; border-radius: 8px; background: #3b82f6; color: #fff; cursor: pointer; }
.mcat-next:hover { filter: brightness(1.08); }
.mcat-answer .mcat-why { margin-top: 0.4em; }
.nightMode.card, .nightMode .card { color: #ddd; }
.nightMode .mcat-opt { background: #2b2b2f; border-color: #444; }
.nightMode .mcat-opt:hover:not(:disabled) { background: #33384a; }
.nightMode .mcat-opt.mcat-correct { background: #1e3a24; border-color: #4caf50; }
.nightMode .mcat-opt.mcat-wrong { background: #3a1e1e; border-color: #ef5350; }
.nightMode .mcat-why { color: #ccc; }
"""

# Interactive multiple-choice logic. Self-contained; re-run safe (guards against
# double-binding). Communicates the auto-grade to the reviewer via pycmd, which
# maps correct -> Good(3) and wrong -> Again(1) and gates on the mcat::exam tag.
MCQ_SCRIPT = """
<script>
(function () {
  var exam = document.querySelector('.mcat-exam');
  if (!exam || exam.dataset.mcatBound) return;
  exam.dataset.mcatBound = "1";
  var correct = (exam.dataset.correct || "").trim().toUpperCase();
  var opts = exam.querySelectorAll('.mcat-opt');
  var answered = false;
  function grade(chosen) {
    if (answered) return;
    answered = true;
    var isCorrect = chosen === correct;
    opts.forEach(function (b) {
      b.disabled = true;
      var l = b.getAttribute('data-letter');
      if (l === correct) b.classList.add('mcat-correct');
      if (l === chosen && !isCorrect) b.classList.add('mcat-wrong');
    });
    var cl = exam.querySelector('.mcat-correct-letter');
    if (cl) cl.textContent = correct;
    var verdict = exam.querySelector('.mcat-verdict');
    if (!chosen) { verdict.textContent = 'Time expired'; verdict.className = 'mcat-verdict mcat-bad'; }
    else if (isCorrect) { verdict.textContent = 'Correct'; verdict.className = 'mcat-verdict mcat-ok'; }
    else { verdict.textContent = 'Incorrect'; verdict.className = 'mcat-verdict mcat-bad'; }
    var note = exam.querySelector('.mcat-ease-note');
    if (note) note.textContent = isCorrect ? 'Auto-graded: Good (3)' : 'Auto-graded: Again (1)';
    exam.querySelector('.mcat-explanation').classList.add('mcat-show');
    if (chosen) { try { pycmd('mcat_answer:' + (isCorrect ? 3 : 1)); } catch (e) {} }
  }
  opts.forEach(function (b) {
    b.addEventListener('click', function () { grade(b.getAttribute('data-letter')); });
  });
  window.mcatNext = function () { try { pycmd('mcat_next'); } catch (e) {} };
  // Called by the reviewer when the countdown hits zero with no selection.
  window.mcatReveal = function () { if (!answered) grade(''); };
})();
</script>
"""


def mcq_body(prefix: str = "") -> str:
    """The clickable MCQ block, using the given field-name prefix.

    ``prefix`` is "" for the single-question MCATExam / MCATCarsPassage
    notetypes (fields Question, A, B, C, D, Correct, Explanation, Topic).
    """
    q = f"{{{{{prefix}Question}}}}"
    topic = f"{{{{{prefix}Topic}}}}"
    correct = f"{{{{{prefix}Correct}}}}"
    expl = f"{{{{{prefix}Explanation}}}}"
    opts = "".join(
        f'<button class="mcat-opt" data-letter="{letter}">'
        f'<span class="mcat-letter">{letter}.</span>'
        f"<span>{{{{{prefix}{letter}}}}}</span></button>\n"
        for letter in ("A", "B", "C", "D")
    )
    return f"""<div class="mcat-exam" data-correct="{correct}">
<div class="mcat-topic">{topic}</div>
<div class="mcat-q">{q}</div>
<div class="mcat-options">
{opts}</div>
<div class="mcat-explanation">
<div class="mcat-verdict"></div>
<div class="mcat-answer-line">Correct answer: <b class="mcat-correct-letter"></b></div>
<div class="mcat-why">{expl}</div>
<div class="mcat-ease-note"></div>
<button class="mcat-next" onclick="mcatNext()">Next &rarr;</button>
</div>
</div>
{MCQ_SCRIPT}"""


def mcq_afmt(prefix: str = "") -> str:
    """Static fallback answer view (used only if the normal Show-Answer path is
    taken instead of clicking an option)."""
    q = f"{{{{{prefix}Question}}}}"
    correct = f"{{{{{prefix}Correct}}}}"
    expl = f"{{{{{prefix}Explanation}}}}"
    return (
        f'<div class="mcat-answer"><div class="mcat-q">{q}</div>'
        f"Correct answer: <b>{correct}</b>"
        f'<div class="mcat-why">{expl}</div></div>'
    )


def make_notetype(col: Collection, name: str, fields: list[str], qfmt: str, afmt: str):
    mm = col.models
    existing = mm.by_name(name)
    if existing:
        return existing
    nt = mm.new(name)
    for f in fields:
        mm.add_field(nt, mm.new_field(f))
    tmpl = mm.new_template("Card 1")
    tmpl["qfmt"] = qfmt
    tmpl["afmt"] = afmt
    mm.add_template(nt, tmpl)
    nt["css"] = MCQ_CSS
    mm.add(nt)
    return mm.by_name(name)


def make_typed_notetype(col: Collection):
    mm = col.models
    existing = mm.by_name("MCATTypedLearning")
    if existing:
        return existing
    nt = mm.new("MCATTypedLearning")
    mm.add_field(nt, mm.new_field("Front"))
    mm.add_field(nt, mm.new_field("Back"))
    tmpl = mm.new_template("Card 1")
    tmpl["qfmt"] = "{{Front}}<br><br>{{type:Back}}"
    tmpl["afmt"] = "{{FrontSide}}\n\n<hr id=answer>\n\n{{Back}}"
    mm.add_template(nt, tmpl)
    mm.add(nt)
    return mm.by_name("MCATTypedLearning")


def topic_label(tag: str) -> str:
    """Human-friendly label from an mcat::section::topic tag."""
    parts = tag.split("::")
    if len(parts) >= 3:
        return f"{parts[1]} / {parts[2]}".replace("_", " ")
    return tag


def build(path: str) -> dict[str, int]:
    tmp = tempfile.mkdtemp(prefix="mcat_gen_")
    col_path = os.path.join(tmp, "collection.anki2")
    col = Collection(col_path)
    try:
        learning_deck = col.decks.id(LEARNING_DECK)
        exam_deck = col.decks.id(EXAM_DECK)

        basic = col.models.by_name("Basic")
        typed_nt = make_typed_notetype(col)
        exam_nt = make_notetype(
            col,
            "MCATExam",
            ["Question", "A", "B", "C", "D", "Correct", "Explanation", "Topic"],
            mcq_body(),
            mcq_afmt(),
        )
        cars_nt = make_notetype(
            col,
            "MCATCarsPassage",
            ["Passage", "Question", "A", "B", "C", "D", "Correct", "Explanation", "Topic"],
            '<div class="mcat-passage">{{Passage}}</div>\n' + mcq_body(),
            mcq_afmt(),
        )

        counts = {"knowledge": 0, "typed": 0, "exam": 0, "cars": 0}

        # --- Learning subdeck: Basic recall + typed fill-in ---
        for tag, front, back in KNOWLEDGE:
            note = col.new_note(basic)
            note["Front"] = front
            note["Back"] = back
            note.tags = [tag]
            col.add_note(note, learning_deck)
            counts["knowledge"] += 1

        for tag, question, answer in LEARNING_TYPED:
            note = col.new_note(typed_nt)
            note["Front"] = question
            note["Back"] = answer
            note.tags = [tag]
            col.add_note(note, learning_deck)
            counts["typed"] += 1

        # --- Exam subdeck: multiple-choice questions ---
        for tag, question, options, correct, explanation in EXAM_MCQ:
            note = col.new_note(exam_nt)
            note["Question"] = question
            note["A"], note["B"], note["C"], note["D"] = options
            note["Correct"] = correct
            note["Explanation"] = explanation
            note["Topic"] = topic_label(tag)
            note.tags = [tag, EXAM_TAG]
            col.add_note(note, exam_deck)
            counts["exam"] += 1

        # --- Exam subdeck: CARS passages (one card per question) ---
        for passage in CARS_PASSAGES:
            for skill, question, options, correct, explanation in passage["questions"]:
                note = col.new_note(cars_nt)
                note["Passage"] = passage["passage"]
                note["Question"] = question
                note["A"], note["B"], note["C"], note["D"] = options
                note["Correct"] = correct
                note["Explanation"] = explanation
                note["Topic"] = topic_label(skill)
                note.tags = [skill, EXAM_TAG]
                col.add_note(note, exam_deck)
                counts["cars"] += 1

        os.makedirs(os.path.dirname(path), exist_ok=True)
        options = ExportAnkiPackageOptions(
            with_scheduling=False,
            with_media=False,
            legacy=True,
        )
        col.export_anki_package(out_path=path, options=options, limit=None)
        return counts
    finally:
        col.close()


def main() -> None:
    counts = build(OUT_PATH)
    topics = (
        {t for t, *_ in KNOWLEDGE}
        | {t for t, *_ in LEARNING_TYPED}
        | {t for t, *_ in EXAM_MCQ}
        | {q[0] for p in CARS_PASSAGES for q in p["questions"]}
    )
    print(f"Wrote {OUT_PATH}")
    print(
        f"  Learning: {counts['knowledge']} basic + {counts['typed']} typed fill-in\n"
        f"  Exam: {counts['exam']} MCQ + {counts['cars']} CARS passage questions"
        f" ({len(CARS_PASSAGES)} passages)\n"
        f"  across {len(topics)} topics"
    )


if __name__ == "__main__":
    main()
