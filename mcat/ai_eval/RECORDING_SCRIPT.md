# Submission recording script — Sunday final (desktop + mobile + proof)

Everything is shown **inside the actual apps and one terminal**. Say the SAY
lines in your own words; do the DO steps on screen. There are **four short
recordings**; you can also record them as one continuous take.

- **Recording A — Desktop app (features + AI + scores with AI off)** — ~5 min
- **Recording B — Mobile (two-way sync, offline, conflict, three scores)** — ~3 min
- **Recording C — Proof in the terminal (evals, models, benchmark, crash, sync rule)** — ~4 min
- **Recording D — Clean installs (desktop installer + phone build on a clean device)** — ~2 min

Before you start: the desktop app is running, and on the MCAT dashboard the
**"AI assistant: on"** pill is green (built-in proxy — no API key is ever typed
in). Sign both the desktop and the phone into the **same AnkiWeb account**.

> Everything below maps to the Sunday rubric. The requirement each scene proves
> is named in **(parentheses)**. A full coverage checklist is at the bottom.

---

## RECORDING A — Desktop app

### Scene 0 — Intro (~15s)

- **SAY:** "This is my MCAT study app, built inside Anki's Rust engine. It has
  three separate scores, a source-grounded AI layer, and it syncs to my phone.
  I'll show the features live, then prove the numbers in the terminal. Nothing
  uses a hand-typed API key — AI ships behind a built-in proxy."

### Scene 1 — The dashboard: three scores with ranges (models: score mapping + range)

- **DO:** Open the MCAT dashboard (top-toolbar MCAT link, or Tools → MCAT Home).
- **DO:** Point at the big **Readiness gauge** on the 472–528 scale: the score,
  its **CI low–high range**, the target flag, and the percentile ticks.
- **DO:** Open **"Memory & performance detail"** to show the **Memory** and
  **Performance** scores, each with its own range and confidence.
- **SAY:** "Three separate scores, each on the real 472–528 MCAT scale with a
  confidence range. The mapping is written down in `docs/model-descriptions.md`.
  Readiness abstains until my give-up rule is met — 100 graded reviews and 50%
  topic coverage."

### Scene 2 — Weak spots + one-tap study (feature: prescriptive coaching)

- **DO:** Point at the **Weak spots** panel under the gauge — the ranked weakest
  topics with section chip, recall %, and due count.
- **DO:** Click **Study** on one weak topic; show it opens the reviewer scoped to
  that topic.
- **SAY:** "The engine ranks my weakest topics and lets me drill any one of them
  in one tap — this is the deterministic recommender, no AI required."

### Scene 3 — Coverage map + abstention (challenge 7c)

- **DO:** Open **"Section scores & coverage map"**. Point at the overall
  **Coverage %** and the per-section → per-topic coverage bars.
- **SAY:** "Every topic on the official MCAT outline is listed; I show the percent
  covered, and if coverage is below the line the app abstains instead of showing
  a fake 'ready'."

### Scene 4 — Source-grounded generation + fake-source defense (features 9.3 / 9.9)

- **DO:** On the dashboard, expand **"Generate AI flashcards"** (it's inline on
  the dashboard now, not a separate window). Point at the green **"AI ready ·
  gpt-4o-mini"** pill.
- **SAY:** "AI is on through the built-in proxy — I never entered a key."
- **DO:** Click **New source…**, register a source: **Name** (e.g. "Kaplan
  Biochemistry"), optional **Section**, paste an **Excerpt**, Save.
- **SAY:** "Generation is impossible without a registered source — the Generate
  button stays disabled until one exists. That's the fake-source defense."
- **DO:** Set **Count** ~5, choose a **Difficulty** tier, click **Generate**.

### Scene 5 — The quality gate + traceability (feature 9.4 / every output cites a source)

- **DO:** Click a candidate to expand it. Point at, in order:
  1. the **Verdict** + **overall score / cutoff 0.70**,
  2. the **category breakdown** (✓/✗: vague, trivial, circular, unsupported, duplicate),
  3. the **Source trace** — the exact excerpt the card is grounded in.
- **SAY:** "Every card is scored against a 0.70 cutoff I set beforehand, with a
  reason per category, and each carries the source text it came from."
- **DO:** Check a passing card → **"Accept checked → MCAT deck."** Read the
  confirmation.
- **SAY:** "Accepted cards become real notes tagged `ai-generated` with a visible
  'Source:' citation — and they sync to the phone."

### Scene 6 — Missed-question explanations (feature 9.5)

- **DO:** From a weak-topic study session, flip a card to the **answer side** and
  click **"Explain this miss (AI)."**
- **SAY:** "On any MCAT card the answer side offers a source-grounded explanation
  of why the right answer is right — and it never feeds the score."

### Scene 7 — Both apps still score with AI OFF (requirement: AI off still gives a score)

- **DO:** Click the **"AI assistant: on"** pill (or Tools → MCAT AI Settings…),
  untick **Enable AI features**, Save. Return to the dashboard.
- **SAY:** "AI is now off. All three scores, the section breakdown, coverage, and
  weak spots are still here — computed deterministically from review history. AI
  is never part of scoring."
- **DO (optional):** Re-enable AI when done.

---

## RECORDING B — Mobile (two-way sync, offline, conflict, three scores)

Put the **phone/simulator and the desktop side by side**, both on the **same
AnkiWeb account**. The iOS app opens to the **Readiness** screen.

### Scene 1 — Two-way sync, none lost or double-counted (challenge 7b, part 1)

- **DO (phone → desktop):** Review **10 cards on the phone**, tap **Sync**; then
  **Sync** on the desktop and show those 10 reviews landed, counted once.
- **DO (desktop → phone):** Review **10 different cards on the desktop**, sync,
  then **Sync** on the phone and show they appear.
- **SAY:** "Twenty reviews total — ten each side — all land in one place, none
  lost and none double-counted."

### Scene 2 — Offline review, then sync on reconnect (challenge 7g, part 2)

- **DO:** Turn on **Airplane Mode**, review a card or two (works with no network),
  turn networking back on, tap **Sync**, then **Sync** on desktop and show the
  offline reviews arrived.
- **SAY:** "Airplane mode — I can still review and still see a score. Reconnect,
  sync, and the offline reviews show up on the desktop. Nothing lost."

### Scene 3 — Same-card conflict, documented rule (challenge 7b, part 2)

- **DO:** With **both devices offline**, review the **same card** on each,
  answering **differently** (e.g. Again on the phone, Good on the desktop).
  Reconnect and sync both.
- **DO:** Open `docs/sync-conflict-rule.md` on screen.
- **SAY:** "When both devices touch the same card offline, my rule is: reviews are
  append-only so every review is kept, and the card's scheduling state resolves
  last-writer-wins by modification time. That's documented here, and the
  `just mcat-sync-conflict` simulation demonstrates it."

### Scene 4 — Three scores with ranges + give-up rule (requirement)

- **DO:** On the phone's **Readiness** screen point at the **Readiness** gauge and
  range, then the **Memory** and **Performance** mini-scores with their ranges.
  Open **Breakdown** to show the written give-up rule / "No score yet" state.
- **SAY:** "The phone shows all three scores, each with a range, and follows the
  same give-up rule as the desktop — identical numbers on a synced collection
  because both run the same Rust engine."

### Scene 5 — Phone scores with AI off (requirement)

- **DO:** Toggle AI off (or just note it needs no AI) and show the scores remain.
- **SAY:** "The phone gives its three scores with AI off, too."

---

## RECORDING C — Proof in the terminal (run from the repo root)

### Scene 1 — Eval runs before students, and beats simpler methods (Friday requirement, kept)

- **DO:** `just mcat-ai-eval` (or open `mcat/ai_eval/report.md`).
- **SAY:** "On a held-out set of 50 labelled cards — 20 good, 30 deliberately bad
  — my AI quality gate hits **100% accuracy and a 0% wrong-answer rate** at the
  0.70 cutoff. Keyword search is **86% / 24%**, vector TF-IDF is **84% / 23%**.
  All **5 of 5** AI features beat their no-AI baseline. This runs before any card
  reaches a student."

### Scene 2 — Memory model is calibrated (models: calibration chart + score)

- **DO:** `just mcat-eval-calibration`; open `mcat/ai_eval/calibration_curve.svg`
  and `mcat/ai_eval/model_validation_report.md`.
- **SAY:** "On a 1,200-item held-out split, the FSRS memory model scores **Brier
  0.1897, log loss 0.5604, ECE 0.022** — well-calibrated, very slightly
  over-confident, shown in this reliability diagram. I cross-checked the number
  against the live Rust engine to within 3e-4, so it's genuinely the engine's
  output."

### Scene 3 — Performance model held-out accuracy (models)

- **DO:** `just mcat-eval-performance`.
- **SAY:** "The performance model predicts unseen exam-style questions at **71.3%
  accuracy vs a 59.6% majority baseline**, Brier 0.1847."

### Scene 4 — Paraphrase / transfer gap (challenge 7d)

- **DO:** `just mcat-eval-paraphrase`.
- **SAY:** "30 cards, each with two reworded questions. Recall on the originals is
  **70.9%** but accuracy on the reworded versions is **49.6%** — a **21.3-point
  transfer gap**. My control run drives that gap to 0.0, proving the performance
  signal isn't just copying memory."

### Scene 5 — Three-build study, with an honest negative result (models: three builds, equal time)

- **DO:** `just mcat-eval-study`.
- **SAY:** "Under an **equal budget of 23 reviews per arm**: blocked practice
  69.1%, interleaved **75.3%**, interleaved-plus-recommender 74.7%. Interleaving
  wins by +6.2 points — but, honestly, weighting by the recommender actually lost
  0.6 points at a fixed budget. I report the result that didn't work."

### Scene 6 — Leakage scan is clean (challenge 7e)

- **DO:** `just mcat-eval-leakage`.
- **SAY:** "The scan flags any held-out item within 0.70 Jaccard of training data:
  **0 of 66 leaked**, nearest neighbour only 0.44, and a planted duplicate is
  caught — so the scanner isn't blind."

### Scene 7 — AI card gold-set check (challenge 7f)

- **DO:** `just mcat-eval-goldset`.
- **SAY:** "50 candidates from one real source, cutoff fixed at 0.70 before
  looking. Ground truth: 20 correct-and-useful, 6 wrong-fact, 24 bad-teaching.
  The checker **blocks 30 of 50** — catching **6/6 wrong facts and 24/24
  bad-teaching cards** while wrongly blocking **0/20** good ones. Zero bad cards
  reach a student."

### Scene 8 — Crash + offline safety (challenge 7g)

- **DO:** `just mcat-crash-test`.
- **SAY:** "This force-kills the engine mid-review **20 times in a row**. After
  every kill the integrity check is clean — **zero corrupted collections** — and
  the review count is monotonic, so nothing is lost or invented. It also confirms
  scoring works with AI off."

### Scene 9 — One-command benchmark on 50,000 cards (challenge 7h)

- **DO:** `just mcat-bench` (uses the shared 50k deck; open
  `mcat/bench/results/bench_50000.md`).
- **SAY:** "One command loads a **50,000-card** deck (44,957 reviews) and prints
  p50 / p95 / worst for each action. My Rust mastery query — the backend change —
  powers the dashboard at **p50 383 ms, p95 396 ms** on 50k cards; readiness
  352 / 360 ms; answering a card 0.5 / 1.3 ms; undo 0.5 / 0.7 ms; search 13 ms."

### Scene 10 — The Rust change (challenge 7a)

- **DO:** Show `rslib/src/mcat/` (the mastery query + its unit tests) and mention
  the Python test that calls it.
- **SAY:** "The backend change is the mastery query in the Rust engine — per
  topic, how many cards are mastered and the average recall — fast enough to
  power the dashboard on 50k cards, with Rust unit tests plus a Python round-trip
  test. Because the engine is shared, it ships to the phone too."

---

## RECORDING D — Clean installs (requirement: both builds install & run on clean devices)

### Scene 1 — Desktop installer

- **DO:** Download the installer artifact from the GitHub Actions
  **build-installers** workflow (`.github/workflows/build-installers.yml`) — or
  build locally — and install it on a clean machine / fresh VM. Launch it, open
  the MCAT dashboard, show a score.
- **SAY:** "Here's the packaged desktop installer running on a clean machine — it
  opens, and the MCAT dashboard scores immediately."

### Scene 2 — Phone build

- **DO:** Install the phone build on a clean device following
  `mobile/AnkiCompanion/DISTRIBUTION.md` (sideload / ad-hoc IPA / TestFlight via
  `build_ipa.sh`). Launch it, sign into AnkiWeb, sync, show the three scores.
- **SAY:** "And the packaged phone build on a clean device — install, sign in,
  sync, and the same three scores appear."

---

## The exact numbers to cite (so you don't misspeak)

| Claim                                      | Number                                                                     |
| ------------------------------------------ | -------------------------------------------------------------------------- |
| Checker cutoff (set before testing)        | **0.70**                                                                   |
| AI quality gate                            | **100%** accuracy, **0%** wrong-answer rate                                |
| Keyword search baseline                    | 86% accuracy, 24% wrong-answer rate                                        |
| Vector (TF-IDF) baseline                   | 84% accuracy, 23% wrong-answer rate                                        |
| AI features beating their no-AI baseline   | **5 / 5**                                                                  |
| Memory calibration (held-out n=1200)       | **Brier 0.1897, log loss 0.5604, ECE 0.022**                               |
| Calibration vs live engine                 | matches to **max \|Δ\| = 2.8e-04**                                         |
| Performance model (held-out)               | **71.3%** acc vs **59.6%** majority (Brier 0.1847)                         |
| Paraphrase / transfer gap                  | recall **70.9%** − reworded **49.6%** = **21.3 pt** (control 0.0)          |
| Three builds (equal budget 23 reviews/arm) | blocked 69.1% · **interleaved 75.3%** · +recommender 74.7%                 |
| Honest negative                            | recommender weighting **−0.6 pt** at fixed budget                          |
| Leakage scan                               | **0 / 66** leaked (Jaccard 0.70; nearest 0.44)                             |
| Gold set (50 candidates)                   | 20 good / 6 wrong / 24 bad-teaching; **blocks 30/50**, 0 bad reach student |
| Crash test                                 | **20** mid-review SIGKILLs, **0** corruption, monotonic                    |
| Benchmark deck                             | **50,000 cards**, 44,957 reviews, 40 iters                                 |
| Mastery query (7a) on 50k                  | **p50 383 ms / p95 396 ms**                                                |
| Readiness / answer / undo on 50k           | 352/360 ms · 0.5/1.3 ms · 0.5/0.7 ms                                       |
| Give-up rule threshold                     | 100 graded reviews **and** 50% topic coverage                              |
| Score scale                                | 472–528 (real MCAT scaled score)                                           |

## One-liners for each proof command

| Command                           | Proves                                              |
| --------------------------------- | --------------------------------------------------- |
| `just mcat-ai-eval`               | AI gate vs keyword/vector baselines (report.md)     |
| `just mcat-eval-calibration`      | Memory calibration + `calibration_curve.svg`        |
| `just mcat-eval-performance`      | Performance held-out accuracy                       |
| `just mcat-eval-paraphrase`       | Recall-vs-transfer gap (7d)                         |
| `just mcat-eval-study`            | Three-build equal-time study (+ honest negative)    |
| `just mcat-eval-leakage`          | Train/test leakage scan is clean (7e)               |
| `just mcat-eval-goldset`          | 50-card gold-set quality check (7f)                 |
| `just mcat-eval-all`              | Runs the whole model-validation + measurement suite |
| `just mcat-crash-test`            | 20 crashes, zero corruption, AI-off scoring (7g)    |
| `just mcat-bench`                 | One-command 50k benchmark, p50/p95/worst (7h)       |
| `just mcat-sync-conflict`         | Same-card offline conflict merge (7b)               |
| `just mcat-ai-verify-scoring-off` | Scores computed with AI disabled                    |

## Files / artifacts a grader can open

- `mcat/ai_eval/AI_NOTES.md` — the written "what AI, why, what I skipped" note
- `mcat/ai_eval/report.md` — AI eval + baseline comparison
- `mcat/ai_eval/model_validation_report.md` + `calibration_curve.svg` — models & calibration
- `mcat/ai_eval/experiments_report.md` — 7d/7e/7f + three-build study, negatives included
- `docs/model-descriptions.md` — the three models + score mapping and range
- `docs/sync-conflict-rule.md` — the documented conflict rule
- `docs/brainlift.md` — the Brainlift
- `mcat/bench/results/bench_50000.md` — 50k benchmark numbers
- `rslib/src/mcat/` — the Rust mastery-query change + tests
- `.github/workflows/build-installers.yml` — packaged desktop installers
- `mobile/AnkiCompanion/DISTRIBUTION.md` — phone build / install routes

## Sunday rubric coverage checklist

- [x] Memory model calibrated — chart + Brier/log loss on held-out (Rec C, Scene 2)
- [x] Performance model held-out accuracy (Rec C, Scene 3)
- [x] Score mapping written down, with a range (Rec A, Scene 1 + `docs/model-descriptions.md`)
- [x] Study feature tested with three builds, equal time (Rec C, Scene 5)
- [x] Honest reporting incl. results that didn't work (Rec C, Scene 5)
- [x] Packaged desktop installer + phone build on clean devices (Rec D)
- [x] Sync handles same-card conflict, documented (Rec B, Scene 3)
- [x] Both apps run with AI off and still score (Rec A, Scene 7; Rec B, Scene 5)
- [x] 7a Rust change + tests, ships to phone (Rec C, Scene 10)
- [x] 7b sync test: 10+10, none lost/doubled, conflict rule (Rec B, Scenes 1 & 3)
- [x] 7c coverage map + abstain below line (Rec A, Scene 3)
- [x] 7d paraphrase transfer gap (Rec C, Scene 4)
- [x] 7e leakage scan clean (Rec C, Scene 6)
- [x] 7f gold-set AI card check with pre-set cutoff (Rec C, Scene 7)
- [x] 7g crash x20 + offline, still scores (Rec C, Scene 8; Rec B, Scene 2)
- [x] 7h one-command benchmark, p50/p95/worst (Rec C, Scene 9)
- [x] Proof: eval numbers, model descriptions, Brainlift, recordings of both builds (Rec C & D)
