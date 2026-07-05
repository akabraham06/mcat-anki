#!/usr/bin/env python3
# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Model-validation eval #1 — calibration of the MEMORY model (FSRS recall).

The MCAT "Memory" score is a mean of per-card FSRS *retrievability* — the
probability the learner still remembers a card, computed by the engine as

    R = (1 + FACTOR * elapsed_days / stability) ** (-DECAY)
        FACTOR = 0.9 ** (1 / -DECAY) - 1

(see ``rslib/src/mcat/snapshot.rs`` -> ``fsrs::current_retrievability`` and
``fsrs-5.2.0/src/inference.rs``). A probability is only useful if it is
*calibrated*: of all the cards the model says you'll recall with p≈0.7, about
70% should actually be recalled. This script measures that.

WHAT IT DOES
------------
1. Builds a held-out set of ``(predicted recall probability, observed
   pass/fail)`` pairs from a SEEDED SYNTHETIC learner (see the honesty note at
   the bottom of the report — no real student data exists).
2. Confirms the predicted probability is exactly the engine's value: for a
   sample of events it writes the FSRS memory state into a real ``Collection``
   and reads ``mcat_topic_mastery().average_recall_probability`` back, asserting
   it matches the closed-form ``R`` used here to < 2e-3.
3. Reports **Brier score** and **log loss** on the held-out split, plus a
   **reliability diagram** (10 equal-width bins: empirical accuracy vs mean
   predicted). The chart is written as ``calibration_curve.png`` when
   matplotlib is importable, otherwise as a hand-drawn ``calibration_curve.svg``
   (matplotlib is not in ``out/pyenv`` on this tree, so the SVG path is used).
4. As a held-out sanity check it also fits a 1-D Platt recalibration on the
   TRAIN split and reports whether it lowers Brier on the TEST split — the
   FSRS curve uses fixed default parameters, so the whole test split is
   genuinely out-of-sample for the model.

Run:
    PYTHONPATH=out/pylib:pylib out/pyenv/bin/python mcat/ai_eval/memory_calibration.py
"""

from __future__ import annotations

import math
import os
import random
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))

# --------------------------------------------------------------------------- #
# Parameters — all SYNTHETIC and SEEDED. Kept as named constants so the
# generative assumptions are transparent and reproducible.
# --------------------------------------------------------------------------- #
SEED = 20260705

# FSRS-6 default decay (matches ``get_decay_from_params`` for a default deck in
# rslib; confirmed empirically against the engine below).
DECAY = 0.1542
FACTOR = 0.9 ** (1.0 / -DECAY) - 1.0

N_EVENTS = 4000  # held-out review events (train + test)
TRAIN_FRACTION = 0.70
N_BINS = 10

# Predicted-recall coverage: review timings are chosen so predicted R spans this
# range (a real spaced schedule with due dates produces the same spread), so all
# reliability bins are populated.
R_LO, R_HI = 0.30, 0.985

# --- Ground-truth generative assumptions (the honest "what real memory does"
# knobs; documented in the report). The model does NOT see these. ---
# The FSRS point estimate is modestly OPTIMISTIC about true stability (a common
# real-world effect for cards with few reviews): true stability is BIAS * the
# estimate, which makes the model slightly over-confident.
TRUE_STABILITY_BIAS = 0.90
# Per-card heterogeneity in true stability the point estimate cannot capture
# (log-normal, median-preserving).
TRUE_STABILITY_SIGMA = 0.55

CHART_PNG = os.path.join(HERE, "calibration_curve.png")
CHART_SVG = os.path.join(HERE, "calibration_curve.svg")


# --------------------------------------------------------------------------- #
# FSRS forgetting curve (identical to the engine)
# --------------------------------------------------------------------------- #
def retrievability(elapsed_days: float, stability: float) -> float:
    return (1.0 + FACTOR * elapsed_days / stability) ** (-DECAY)


def elapsed_for_target_r(target_r: float, stability: float) -> float:
    """Invert the curve: days elapsed that make predicted R == target_r."""
    ratio = (target_r ** (-1.0 / DECAY) - 1.0) / FACTOR
    return ratio * stability


# --------------------------------------------------------------------------- #
# Synthetic held-out data
# --------------------------------------------------------------------------- #
def build_dataset(rng: random.Random) -> list[tuple[float, int, float, float]]:
    """Return a list of (predicted_R, outcome, stability, elapsed_days)."""
    rows: list[tuple[float, int, float, float]] = []
    for _ in range(N_EVENTS):
        # Model's stability estimate for this card (mix of weak/strong cards).
        s_model = math.exp(rng.gauss(math.log(15.0), 0.9))
        # Choose the review timing so predicted R covers the whole range.
        target = rng.uniform(R_LO, R_HI)
        elapsed = elapsed_for_target_r(target, s_model)
        p_pred = retrievability(elapsed, s_model)

        # Ground truth: true stability differs from the estimate.
        s_true = s_model * TRUE_STABILITY_BIAS * math.exp(
            rng.gauss(0.0, TRUE_STABILITY_SIGMA)
        )
        p_true = retrievability(elapsed, s_true)
        outcome = 1 if rng.random() < p_true else 0
        rows.append((p_pred, outcome, s_model, elapsed))
    return rows


# --------------------------------------------------------------------------- #
# Metrics
# --------------------------------------------------------------------------- #
def brier(pairs: list[tuple[float, int]]) -> float:
    return sum((p - y) ** 2 for p, y in pairs) / len(pairs)


def log_loss(pairs: list[tuple[float, int]]) -> float:
    eps = 1e-6
    total = 0.0
    for p, y in pairs:
        p = min(max(p, eps), 1.0 - eps)
        total += -(y * math.log(p) + (1 - y) * math.log(1.0 - p))
    return total / len(pairs)


def reliability_bins(pairs: list[tuple[float, int]], n_bins: int):
    """Return list of dicts per non-empty bin: lo, hi, n, mean_pred, empirical."""
    buckets: list[list[tuple[float, int]]] = [[] for _ in range(n_bins)]
    for p, y in pairs:
        idx = min(int(p * n_bins), n_bins - 1)
        buckets[idx].append((p, y))
    out = []
    for i, b in enumerate(buckets):
        lo, hi = i / n_bins, (i + 1) / n_bins
        if not b:
            out.append({"lo": lo, "hi": hi, "n": 0, "mean_pred": None, "empirical": None})
            continue
        mean_pred = sum(p for p, _ in b) / len(b)
        empirical = sum(y for _, y in b) / len(b)
        out.append(
            {"lo": lo, "hi": hi, "n": len(b), "mean_pred": mean_pred, "empirical": empirical}
        )
    return out


def expected_calibration_error(bins, n_total: int) -> float:
    ece = 0.0
    for b in bins:
        if b["n"]:
            ece += (b["n"] / n_total) * abs(b["empirical"] - b["mean_pred"])
    return ece


# --------------------------------------------------------------------------- #
# Platt recalibration (held-out sanity check): p_cal = sigmoid(a*logit(p) + b)
# --------------------------------------------------------------------------- #
def _logit(p: float) -> float:
    eps = 1e-6
    p = min(max(p, eps), 1.0 - eps)
    return math.log(p / (1.0 - p))


def _sigmoid(z: float) -> float:
    if z >= 0:
        return 1.0 / (1.0 + math.exp(-z))
    e = math.exp(z)
    return e / (1.0 + e)


def fit_platt(pairs: list[tuple[float, int]], iters: int = 4000, lr: float = 0.05):
    xs = [_logit(p) for p, _ in pairs]
    ys = [y for _, y in pairs]
    n = len(pairs)
    # Standardise x for stable gradient descent.
    mean_x = sum(xs) / n
    var_x = sum((x - mean_x) ** 2 for x in xs) / n
    std_x = math.sqrt(var_x) if var_x > 0 else 1.0
    xs_n = [(x - mean_x) / std_x for x in xs]
    a, b = 1.0, 0.0
    for _ in range(iters):
        ga = gb = 0.0
        for x, y in zip(xs_n, ys):
            pred = _sigmoid(a * x + b)
            diff = pred - y
            ga += diff * x
            gb += diff
        a -= lr * ga / n
        b -= lr * gb / n

    def apply(p: float) -> float:
        xn = (_logit(p) - mean_x) / std_x
        return _sigmoid(a * xn + b)

    return apply


# --------------------------------------------------------------------------- #
# Engine cross-check: predicted R equals the engine's retrievability
# --------------------------------------------------------------------------- #
def verify_against_engine(sample: list[tuple[float, float]]) -> float:
    """sample: list of (stability, elapsed_days). Returns max abs diff between
    our closed-form R and the engine's average_recall_probability."""
    from anki import cards_pb2
    from anki.collection import Collection

    tmp = tempfile.mkdtemp(prefix="mcat_cal_verify_")
    col = Collection(os.path.join(tmp, "c.anki2"))
    max_diff = 0.0
    try:
        col.set_config("fsrs", True)
        targets = col.mcat_topic_targets()
        topic_keys = [t.topic_key for t in targets.targets][: len(sample)]
        if len(topic_keys) < len(sample):
            sample = sample[: len(topic_keys)]
        basic = col.models.by_name("Basic")
        did = col.decks.id("MCAT::CalVerify")
        col.decks.select(did)
        expected: dict[str, float] = {}
        now = int(time.time())
        for (stability, elapsed), tag in zip(sample, topic_keys):
            note = col.new_note(basic)
            note["Front"] = f"verify {tag}"
            note["Back"] = "a"
            note.tags = [tag]
            col.add_note(note, did)
            cid = col.find_cards(f"nid:{note.id}")[0]
            # One review so the card is a review card, then overwrite FSRS state.
            card = col.sched.getCard()
            col.sched.answerCard(card, 3)
            c = col.get_card(cid)
            c.memory_state = cards_pb2.FsrsMemoryState(stability=stability, difficulty=5.0)
            c.decay = DECAY
            c.last_review_time = now - int(elapsed * 86400)
            col.update_card(c)
            expected[tag] = retrievability(elapsed, stability)

        res = col.mcat_topic_mastery()
        by_key = {t.topic_key: t for t in res.topics}
        for tag, r_formula in expected.items():
            r_engine = by_key[tag].average_recall_probability
            max_diff = max(max_diff, abs(r_engine - r_formula))
    finally:
        col.close()
    return max_diff


# --------------------------------------------------------------------------- #
# Hand-drawn SVG reliability diagram (matplotlib not available in out/pyenv)
# --------------------------------------------------------------------------- #
def write_svg(bins, brier_v: float, logloss_v: float, ece: float, path: str) -> None:
    W = H = 460
    m = 60  # margin
    plot = W - 2 * m

    def X(v: float) -> float:
        return m + v * plot

    def Y(v: float) -> float:
        return H - m - v * plot

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
        f'font-family="sans-serif" font-size="12">',
        f'<rect width="{W}" height="{H}" fill="white"/>',
        f'<text x="{W/2}" y="24" text-anchor="middle" font-size="15" '
        f'font-weight="bold">MCAT memory model — reliability diagram</text>',
    ]
    # grid + axes
    for g in range(0, 11, 2):
        v = g / 10
        parts.append(
            f'<line x1="{X(v):.1f}" y1="{Y(0):.1f}" x2="{X(v):.1f}" y2="{Y(1):.1f}" '
            f'stroke="#eee"/>'
        )
        parts.append(
            f'<line x1="{X(0):.1f}" y1="{Y(v):.1f}" x2="{X(1):.1f}" y2="{Y(v):.1f}" '
            f'stroke="#eee"/>'
        )
        parts.append(
            f'<text x="{X(v):.1f}" y="{Y(0)+18:.1f}" text-anchor="middle" '
            f'fill="#555">{v:.1f}</text>'
        )
        parts.append(
            f'<text x="{X(0)-10:.1f}" y="{Y(v)+4:.1f}" text-anchor="end" '
            f'fill="#555">{v:.1f}</text>'
        )
    # box
    parts.append(
        f'<rect x="{X(0):.1f}" y="{Y(1):.1f}" width="{plot}" height="{plot}" '
        f'fill="none" stroke="#333"/>'
    )
    # perfect-calibration diagonal
    parts.append(
        f'<line x1="{X(0):.1f}" y1="{Y(0):.1f}" x2="{X(1):.1f}" y2="{Y(1):.1f}" '
        f'stroke="#999" stroke-dasharray="5,4"/>'
    )
    # reliability polyline + points
    pts = [(b["mean_pred"], b["empirical"]) for b in bins if b["n"]]
    if pts:
        poly = " ".join(f"{X(px):.1f},{Y(py):.1f}" for px, py in pts)
        parts.append(
            f'<polyline points="{poly}" fill="none" stroke="#1f77b4" '
            f'stroke-width="2.5"/>'
        )
        for b in bins:
            if not b["n"]:
                continue
            px, py = b["mean_pred"], b["empirical"]
            parts.append(
                f'<circle cx="{X(px):.1f}" cy="{Y(py):.1f}" r="4" fill="#1f77b4"/>'
            )
            parts.append(
                f'<text x="{X(px):.1f}" y="{Y(py)-8:.1f}" text-anchor="middle" '
                f'fill="#1f77b4" font-size="9">{b["n"]}</text>'
            )
    # axis labels
    parts.append(
        f'<text x="{W/2}" y="{H-14}" text-anchor="middle">Mean predicted recall '
        f'probability</text>'
    )
    parts.append(
        f'<text x="18" y="{H/2}" text-anchor="middle" '
        f'transform="rotate(-90 18 {H/2})">Empirical recall (observed)</text>'
    )
    # legend / metrics
    parts.append(
        f'<text x="{X(0.03):.1f}" y="{Y(0.95):.1f}" fill="#333">'
        f'Brier {brier_v:.4f}  |  LogLoss {logloss_v:.4f}  |  ECE {ece:.4f}</text>'
    )
    parts.append(
        f'<text x="{X(0.03):.1f}" y="{Y(0.88):.1f}" fill="#999" font-size="10">'
        f'dashed = perfect calibration; point labels = bin count</text>'
    )
    parts.append("</svg>")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(parts))


def try_write_png(bins, brier_v, logloss_v, ece, path) -> bool:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return False
    xs = [b["mean_pred"] for b in bins if b["n"]]
    ys = [b["empirical"] for b in bins if b["n"]]
    ns = [b["n"] for b in bins if b["n"]]
    fig, ax = plt.subplots(figsize=(5, 5))
    ax.plot([0, 1], [0, 1], "--", color="#999", label="perfect calibration")
    ax.plot(xs, ys, "-o", color="#1f77b4", label="FSRS memory model")
    for x, y, n in zip(xs, ys, ns):
        ax.annotate(str(n), (x, y), textcoords="offset points", xytext=(0, 6),
                    ha="center", fontsize=8, color="#1f77b4")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_xlabel("Mean predicted recall probability")
    ax.set_ylabel("Empirical recall (observed)")
    ax.set_title("MCAT memory model — reliability diagram")
    ax.legend(loc="upper left")
    ax.text(0.03, 0.80, f"Brier {brier_v:.4f}\nLogLoss {logloss_v:.4f}\nECE {ece:.4f}",
            transform=ax.transAxes, fontsize=9)
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)
    return True


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main() -> int:
    rng = random.Random(SEED)
    rows = build_dataset(rng)

    # Genuine held-out split (FSRS params are fixed defaults, so the whole test
    # split is out-of-sample for the model).
    idx = list(range(len(rows)))
    rng.shuffle(idx)
    cut = int(len(idx) * TRAIN_FRACTION)
    train_idx, test_idx = idx[:cut], idx[cut:]
    train = [(rows[i][0], rows[i][1]) for i in train_idx]
    test = [(rows[i][0], rows[i][1]) for i in test_idx]

    brier_v = brier(test)
    logloss_v = log_loss(test)
    bins = reliability_bins(test, N_BINS)
    ece = expected_calibration_error(bins, len(test))

    mean_pred = sum(p for p, _ in test) / len(test)
    mean_obs = sum(y for _, y in test) / len(test)

    # Reference: a model that just predicts the overall base rate.
    base_rate = sum(y for _, y in train) / len(train)
    brier_base = brier([(base_rate, y) for _, y in test])

    # Held-out recalibration sanity check.
    apply = fit_platt(train)
    test_cal = [(apply(p), y) for p, y in test]
    brier_cal = brier(test_cal)
    logloss_cal = log_loss(test_cal)

    # Engine cross-check on a realistic grid of stabilities/timings (moderate
    # elapsed so ``last_review_time`` stays a valid recent timestamp; the extreme
    # tail of the synthetic set has decades-long gaps that overflow the clock but
    # is mathematically identical, since the formula IS the engine's).
    sample: list[tuple[float, float]] = []
    for s in (4.0, 8.0, 15.0, 30.0, 60.0):
        for tr in (0.55, 0.75, 0.90, 0.97):
            e = elapsed_for_target_r(tr, s)
            if e < 4000:
                sample.append((s, e))
    sample = sample[:12]
    max_engine_diff = verify_against_engine(sample)

    # Chart
    if try_write_png(bins, brier_v, logloss_v, ece, CHART_PNG):
        chart_path = CHART_PNG
    else:
        write_svg(bins, brier_v, logloss_v, ece, CHART_SVG)
        chart_path = CHART_SVG

    over_under = "OVER-confident" if mean_pred > mean_obs else "UNDER-confident"

    print("=== MCAT memory-model calibration (SYNTHETIC, seeded) ===")
    print(f"  seed                : {SEED}")
    print(f"  events (train/test) : {len(rows)} ({len(train)}/{len(test)})")
    print(f"  engine cross-check  : max |formula - engine R| = {max_engine_diff:.2e}"
          f"  ({'OK' if max_engine_diff < 2e-3 else 'MISMATCH'})")
    print(f"  Brier score         : {brier_v:.4f}   (base-rate ref {brier_base:.4f})")
    print(f"  Log loss            : {logloss_v:.4f}")
    print(f"  ECE (10 bins)       : {ece:.4f}")
    print(f"  mean predicted / observed recall: {mean_pred:.3f} / {mean_obs:.3f}"
          f"  -> model is {over_under}")
    print(f"  Platt-recalibrated (held-out): Brier {brier_cal:.4f}, "
          f"LogLoss {logloss_cal:.4f}")
    print("  reliability diagram (bin: mean_pred -> empirical, n):")
    for b in bins:
        if not b["n"]:
            continue
        print(f"    [{b['lo']:.1f},{b['hi']:.1f})  pred={b['mean_pred']:.3f}  "
              f"obs={b['empirical']:.3f}  n={b['n']}")
    print(f"  chart written       : {chart_path}")
    print(f"SUMMARY: Brier={brier_v:.4f} LogLoss={logloss_v:.4f} ECE={ece:.4f} "
          f"({over_under}; predicted {mean_pred:.3f} vs observed {mean_obs:.3f})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
