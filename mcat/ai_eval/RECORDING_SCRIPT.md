# Submission recording script — what to say and do, in order

A scene-by-scene script for the screen recording(s). Each scene names the
**rubric requirement** it satisfies, the **action** to take on screen, and a
**line to say**. `SAY` lines are suggestions — say them in your own words.

Two recordings are cleanest:

- **Recording A — Desktop (AI):** one screen recording of your Mac (~3 min).
- **Recording B — Mobile (sync):** phone/simulator + desktop side by side (~2 min).

Start each with **Shift+Cmd+5 → Record**. Speak while things run.

---

## RECORDING A — Desktop (AI)

### Scene 0 — Intro (~15s)

- **DO:** Show the desktop app open (or your terminal in the `anki` folder).
- **SAY:** "This is my MCAT study app, built on Anki. I added five AI features
  for authoring and coaching. I'll now walk through each grading requirement and
  prove it live. Nothing here uses a hand-typed API key — the app ships with a
  built-in proxy, so AI works with zero user setup."

### Scene 1 — Run the guided proof (~10s to start)

- **DO:** In the terminal, run:
  ```bash
  bash mcat/ai_eval/walkthrough.sh
  ```
- **SAY:** "This one script runs each requirement's proof in order. It pauses
  between steps so I can explain — I'll press Enter to reveal each result."

### Scene 2 — REQUIREMENT: "A short note on what AI you built, why, and what you skipped."

- **DO:** Press Enter. The note (`AI_NOTES.md`) prints.
- **SAY:** "Here's my written note. Five features — a card-quality gate, source-
  grounded generation, missed-question explanations, a study planner, and
  performance-question generation. Each has to beat the no-AI fallback or it
  doesn't ship. I skipped things like a large paid live-judge sweep, a real
  embedding index, and fine-tuning — I explain why in the note. Two rules run
  through everything: every AI output cites a named source, and AI never touches
  the score."

### Scene 3 — REQUIREMENT: "An eval before students see anything: accuracy and

### wrong-answer rate on a held-out set, with your cutoff." + "A side-by-side

### showing your AI beats a simpler method (keyword or vector search)."

- **DO:** Press Enter. `just mcat-ai-eval` runs (~2s).
- **SAY:** "This eval runs before any card reaches a student. On a held-out set
  of 50 labelled cards — 20 good, 30 deliberately bad — my AI quality gate,
  scored at a cutoff I set beforehand of 0.70, hits **100% accuracy and a 0%
  wrong-answer rate**: it lets through zero bad cards. Side by side, the two
  simpler methods do far worse — keyword search 86% accuracy with a 24%
  wrong-answer rate, and vector TF-IDF search 84% with 23%. They can't see
  triviality, vagueness, or duplicates, so they leak bad cards to students.
  The full write-up is in report.md."

### Scene 4 — REQUIREMENT: "The app still gives a score with AI switched off."

- **DO:** Press Enter. `just mcat-ai-verify-scoring-off` runs (~2s).
- **SAY:** "With AI explicitly switched off, the app still produces the MCAT
  scores — Memory, Performance, and per-section — computed deterministically from
  review history. AI is never part of scoring. And Readiness correctly abstains
  here because it follows my give-up rule: no readiness number until at least 100
  graded reviews and 50% topic coverage."

### Scene 5 — REQUIREMENT: "Every AI output traces back to a named source." (shown LIVE, zero key)

- **DO:** Press Enter. `just mcat-ai-verify-live` runs (~25s — wait for it).
- **SAY:** "This is a real, live AI call. Notice the status: AI available, via my
  built-in proxy, with no API key entered. The quality checker returns a real
  judgement — including a 'source_supported' check. Then generation produces
  cards across recall, MCAT, and stretch difficulty — and every single card
  names the source it was grounded in. That's the traceability requirement:
  nothing the AI outputs is source-less."

### Scene 6 — Wrap desktop (~10s)

- **DO:** Let the script print the "PROOF ARTIFACTS" list, then stop recording.
- **SAY:** "So: a written note, a pre-student eval with accuracy and wrong-answer
  rate at a fixed cutoff, a side-by-side win over keyword and vector search,
  full scoring with AI off, and every AI output tied to a named source — all
  demonstrated live."

> Optional: open the real app (`just run`) and show an AI feature and the three
> scores in the actual UI for a nicer visual — but the script above is the proof.

---

## RECORDING B — Mobile (two-way sync, offline, scores)

Set up **phone (or simulator) and desktop visible together** before recording.
Make sure both are signed into the **same sync account**.

### Scene 1 — REQUIREMENT: "Two-way sync: review on the phone, see it on the desktop,

### and the reverse, with no lost or double-counted reviews."

- **DO (phone → desktop):**
  1. On the desktop, note a specific card's due state / count.
  2. On the **phone**, review that card (pick an answer button).
  3. Sync the phone. Then sync the desktop.
  4. Show the **same card** now updated on the desktop (new due date / count moved by exactly one).
- **SAY:** "I review this card on the phone… sync… now on the desktop the same
  card has advanced — one review, counted once, not lost and not doubled."
- **DO (desktop → phone):** Review a different card on the **desktop**, sync,
  sync the phone, show it updated on the phone.
- **SAY:** "And the reverse direction works the same way."

### Scene 2 — REQUIREMENT: "Offline review works, then syncs when the connection returns."

- **DO:**
  1. Put the phone in **Airplane Mode** (show the toggle on screen).
  2. Review one or two cards — show it works with no connection.
  3. Turn networking back **on**, sync.
  4. On the desktop, sync and show those offline reviews arrived.
- **SAY:** "Airplane mode — no network. I can still review. Reconnect, sync, and
  the reviews I did offline show up on the desktop. Nothing was lost."

### Scene 3 — REQUIREMENT: "The phone shows the three scores with ranges and follows the give-up rule."

- **DO:** On the phone, open the scores screen. Point at each of the **three
  scores (Readiness, Memory, Performance)** and their **ranges** (the low–high
  band). If you don't yet have 100 graded reviews + 50% coverage, show that
  Readiness **abstains** with the give-up message.
- **SAY:** "The phone shows the three scores, each with a confidence range. And
  it follows the same give-up rule as the desktop — it won't invent a Readiness
  score until there's enough evidence: 100 graded reviews and 50% coverage."

### Scene 4 — Wrap (~10s)

- **SAY:** "So the phone and desktop sync both ways with no lost or double
  reviews, offline review syncs on reconnect, and the phone shows all three
  scores with ranges and the give-up rule."

---

## The exact numbers to cite (so you don't misspeak)

| Claim                                      | Number                                        |
| ------------------------------------------ | --------------------------------------------- |
| Checker cutoff (set before testing)        | **0.70**                                      |
| Held-out set                               | 50 cards (20 good, 30 bad)                    |
| AI quality gate                            | **100%** accuracy, **0%** wrong-answer rate   |
| Keyword search                             | 86% accuracy, 24% wrong-answer rate           |
| Vector (TF-IDF) search                     | 84% accuracy, 23% wrong-answer rate           |
| AI features that beat their no-AI baseline | **5 / 5**                                     |
| Give-up rule threshold                     | 100 graded reviews **and** 50% topic coverage |

## Files a grader can open

- `mcat/ai_eval/AI_NOTES.md` — the written note
- `mcat/ai_eval/report.md` — full eval + baseline tables
- `mcat/ai_eval/walkthrough.sh` — the demo you ran
- `rslib/src/mcat/ai/generate.rs` — source-grounding in code
- `rslib/src/mcat/scores.rs` — deterministic scoring (AI-off)
