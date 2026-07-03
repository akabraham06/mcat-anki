// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import SwiftUI

/// A per-question COUNTDOWN, matching the desktop reviewer's MCAT exam-mode
/// timer (qt/aqt/reviewer.py `_showAnswerButton`): it counts *down* from the
/// topic's target budget, turning ready-green → warn-amber → red as time runs
/// out, and fires `onExpire` once when it reaches zero.
///
/// The view keys its lifetime to a fresh instance per question (via `.id(...)`
/// in the parent), so each card restarts the clock. When `paused` becomes true
/// (an answer was revealed) the countdown freezes, like the desktop's freeze on
/// selection. The clock reads in IBM Plex Mono so digits don't jitter.
struct CountdownTimerView: View {
    let budgetSeconds: Int
    let paused: Bool
    let onExpire: () -> Void

    @State private var remaining: Double
    @State private var expired = false
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    init(budgetSeconds: Int, paused: Bool, onExpire: @escaping () -> Void) {
        self.budgetSeconds = max(budgetSeconds, 1)
        self.paused = paused
        self.onExpire = onExpire
        _remaining = State(initialValue: Double(max(budgetSeconds, 1)))
    }

    private let tick = Timer.publish(every: 0.1, on: .main, in: .common).autoconnect()

    private var fraction: Double {
        min(max(remaining / Double(budgetSeconds), 0), 1)
    }

    /// Green when comfortable (uses the readiness hue), amber under a third left
    /// (the warn hue), red in the final stretch — a quick-read pacing cue drawn
    /// from the same semantic palette as the dashboard.
    private var color: Color {
        if fraction > 0.5 { return Theme.ready }
        if fraction > 0.2 { return Theme.warn }
        return Theme.miss
    }

    var body: some View {
        HStack(spacing: 10) {
            Image(systemName: "timer")
                .font(.system(size: 13, weight: .medium))
                .foregroundStyle(color)
            GeometryReader { geo in
                ZStack(alignment: .leading) {
                    Capsule().fill(Theme.hairline)
                    Capsule().fill(color)
                        .frame(width: max(geo.size.width * fraction, 2))
                        .animation(reduceMotion ? nil : .linear(duration: 0.1), value: fraction)
                }
            }
            .frame(height: 6)
            Text(timeLabel)
                .font(.mcatMono(15, relativeTo: .subheadline, medium: true))
                .foregroundStyle(color)
                .frame(minWidth: 46, alignment: .trailing)
                .monospacedDigit()
        }
        .onReceive(tick) { _ in
            guard !paused, !expired else { return }
            remaining = max(remaining - 0.1, 0)
            if remaining <= 0 {
                expired = true
                onExpire()
            }
        }
    }

    private var timeLabel: String {
        let secs = Int(remaining.rounded(.up))
        return "0:\(String(format: "%02d", secs))"
    }
}
