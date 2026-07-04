# Submission recording script (comprehensive) — desktop + mobile

Everything is shown **inside the actual apps**. Say the SAY lines in your own
words. Two recordings:

- **Recording A — Desktop (AI):** the Mac app + one terminal window (~4 min).
- **Recording B — Mobile (sync):** the iPhone/simulator next to the desktop (~2–3 min).

Before you start: the desktop app is running and the AI status shows **"AI ready"**
(built-in proxy — no API key is ever typed in). Sign both the desktop and the
phone into the **same AnkiWeb account**.

---

## RECORDING A — Desktop (AI)

### Scene 0 — Intro (~15s)
- **SAY:** "This is my MCAT study app, built on Anki. I added five AI features for
  authoring and coaching. I'll show each one live in the app. Nothing uses a
  hand-typed API key — it ships with a built-in proxy, so AI works with zero setup."

### Scene 1 — The written note (requirement: "what AI you built, why, what you skipped")
- **DO:** Open `mcat/ai_eval/AI_NOTES.md` on screen and scroll it.
- **SAY:** "Here's my note: five features, two rules that run through all of them —
  every AI output cites a named source, and AI never touches the score — plus what
  I deliberately skipped and why."

### Scene 2 — Open the AI hub
- **DO:** In the app, go to **Tools → MCAT Dashboard** (or the MCAT link in the top
  toolbar). On the dashboard, click the **AI settings / "Turn on AI"** control in the
  planner card. The **MCAT AI Card Studio** window opens.
- **SAY:** "This is my AI Card Studio — it's where three of the features live."
- **DO:** Point at the top-left pill: **"AI ready · gpt-4o-mini."**
- **SAY:** "AI is on through the built-in proxy — notice I never entered a key."

### Scene 3 — Source-grounded generation + fake-source defense (features 9.3 / 9.9)
- **DO:** Click **New…**, register a source: **Name** (e.g. "Kaplan Biochemistry"),
  optional **Section**, and paste an **Excerpt**. Save.
- **SAY:** "Generation is impossible without a registered source — the Generate
  button stays disabled until one exists. This is the fake-source defense."
- **DO:** Set **Count** to ~5, click **Generate**, wait for the candidates to appear.

### Scene 4 — The quality gate + source traceability (features 9.4 / traceability)
- **DO:** Click a candidate card. In the right panel, point at, in order:
  1. **Verdict** + **overall score / cutoff 0.70** — the quality gate.
  2. The **category breakdown** (✓/✗: vague, trivial, circular, unsupported, duplicate).
  3. The **Source trace** at the bottom — the exact excerpt the card is grounded in.
- **SAY:** "Each card is scored against a cutoff I set beforehand of 0.70, with a
  reason per category, and every card carries the source text it came from."
- **DO:** Check a passing card, click **"Accept checked → MCAT deck."** Read the
  confirmation.
- **SAY:** "Accepted cards become real notes tagged `ai-generated` and
  `ai-source::<id>`, with a visible 'Source:' citation — and they sync to mobile."

### Scene 5 — Missed-question explanations (feature 9.5)
- **DO:** Close the Studio. From the dashboard click **Study now** and review an
  **MCAT-tagged card**. Flip to the **answer side**.
- **DO:** Click the **"EXPLAIN THIS MISS (AI)"** button that appears under the answer.
- **SAY:** "On any MCAT card, the answer side offers a source-grounded AI
  explanation of why the right answer is right — and it never feeds the score."

### Scene 6 — AI study planner (feature 9.6)
- **DO:** Go back to the **MCAT dashboard** and point at the **plan / recommendation
  card**.
- **SAY:** "With AI on, the planner turns my real review data into grounded, cited
  next steps. With AI off it falls back to the deterministic recommender."

### Scene 7 — The app still scores with AI OFF (requirement)
- **DO:** Open **AI Settings…** (in the Card Studio or dashboard), untick **Enable
  AI features**, Save. Return to the dashboard.
- **SAY:** "AI is now off. The three scores — Readiness, Memory, Performance, plus
  the section breakdown — are still here, computed deterministically from review
  history. Readiness abstains under my give-up rule until there's enough evidence.
  AI is never part of scoring."
- **DO (optional):** Re-enable AI when done.

### Scene 8 — The eval numbers (requirements: eval before students + beats a simpler method)
- **DO:** In the terminal run `just mcat-ai-eval` (or open `mcat/ai_eval/report.md`).
- **SAY:** "This eval runs before any card reaches a student. On a held-out set of 50
  labelled cards — 20 good, 30 deliberately bad — my AI gate hits **100% accuracy
  and a 0% wrong-answer rate** at the 0.70 cutoff. Side by side, keyword search is
  86% / 24% and vector TF-IDF search is 84% / 23%. All five features beat their
  no-AI baseline."

### Scene 9 — Wrap desktop (~10s)
- **SAY:** "So: a written note, source-grounded generation, a quality gate, missed-
  question explanations, an AI planner, full scoring with AI off, and an eval that
  beats keyword and vector search — every AI output tied to a named source."

---

## RECORDING B — Mobile (two-way sync, offline, scores)

Put the **phone/simulator and the desktop side by side**, both on the **same
AnkiWeb account**. The iOS app opens to the **"Readiness"** screen.

### Scene 1 — Two-way sync, no lost or double-counted reviews (requirement)
- **DO (phone → desktop):**
  1. On the desktop, note a specific card's due date / review count.
  2. On the phone, open a deck and **review that card** (tap an answer button).
  3. Tap the **Sync** button (top of the Readiness screen). Then **Sync** on the
     desktop (Tools → Sync).
  4. Show the **same card** on the desktop now advanced — count moved by exactly one.
- **SAY:** "I review on the phone, sync, and on the desktop the same card advanced —
  counted once, not lost and not doubled."
- **DO (desktop → phone):** Review a different card on the **desktop**, sync, then
  **Sync** on the phone, and show it updated on the phone.
- **SAY:** "The reverse direction works the same way."

### Scene 2 — Offline review, then sync on reconnect (requirement)
- **DO:**
  1. Turn on **Airplane Mode** on the phone (show the toggle).
  2. Review a card or two — show it works with no connection.
  3. Turn networking back **on**, tap **Sync**.
  4. On the desktop, **Sync** and show those offline reviews arrived.
- **SAY:** "Airplane mode, no network — I can still review. Reconnect, sync, and the
  offline reviews show up on the desktop. Nothing was lost."

### Scene 3 — Three scores with ranges + give-up rule (requirement)
- **DO:** On the phone's **Readiness** screen, point at the big **Readiness** gauge
  and its **low–high range**, then the **Memory** and **Performance** mini-scores,
  each with its own range. Open the **Breakdown** screen to show the written
  give-up rule. If under the threshold, show **"No score yet"** with the reason.
- **SAY:** "The phone shows all three scores, each with a confidence range, and
  follows the same give-up rule as the desktop — no Readiness number until 100
  graded reviews and 50% topic coverage."

### Scene 4 — Wrap (~10s)
- **SAY:** "Phone and desktop sync both ways with no lost or double reviews, offline
  review syncs on reconnect, and the phone shows all three scores with ranges and
  the give-up rule."

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

## Where each AI feature lives (quick reference)

| Feature                              | In the app                                             |
| ------------------------------------ | ------------------------------------------------------ |
| Source-grounded generation (9.3)     | AI Card Studio → New source → Generate                 |
| Fake-source defense (9.9)            | AI Card Studio → Generate disabled with no source      |
| Card-quality gate (9.4)              | AI Card Studio → per-card Verdict / cutoff / categories |
| Missed-question explanations (9.5)   | Reviewer → answer side → "Explain this miss (AI)"      |
| Study planner (9.6)                  | MCAT Dashboard → plan / recommendation card            |
| Scores with AI off                   | AI Settings → untick Enable → dashboard still scores   |

## Files a grader can open
- `mcat/ai_eval/AI_NOTES.md` — the written note
- `mcat/ai_eval/report.md` — full eval + baseline tables
- `rslib/src/mcat/ai/generate.rs` — source-grounding in code
- `rslib/src/mcat/scores.rs` — deterministic scoring (AI-off)
