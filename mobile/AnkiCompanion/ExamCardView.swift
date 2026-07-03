// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import SwiftUI

/// Hosts a native, timed MCAT exam session. Owns the `ExamSessionStore` (bound
/// to the shared open collection) and swaps between loading / error / finished /
/// question states. Rendering is fully native SwiftUI — no WKWebView — so it
/// works offline and matches the desktop reviewer's auto-graded exam behaviour.
struct ExamView: View {
    @ObservedObject var collection: CollectionStore
    @StateObject private var exam: ExamSessionStore
    @Environment(\.dismiss) private var dismiss

    init(collection: CollectionStore) {
        self.collection = collection
        _exam = StateObject(wrappedValue: ExamSessionStore(collection: collection))
    }

    var body: some View {
        ZStack {
            Theme.ink.ignoresSafeArea()
            Group {
                if exam.loading {
                    loadingState
                } else if let message = exam.errorMessage {
                    errorState(message)
                } else if let question = exam.question {
                    ExamCardView(exam: exam, question: question)
                } else if exam.finished {
                    SessionSummaryView(exam: exam) { dismiss() }
                } else {
                    ProgressView().tint(Theme.chemphys)
                }
            }
        }
        .navigationTitle("Timed exam")
        .navigationBarTitleDisplayMode(.inline)
        .toolbarBackground(Theme.panel, for: .navigationBar)
        .toolbarBackground(.visible, for: .navigationBar)
        .task { await exam.start() }
        .onDisappear { Task { await exam.endSession() } }
    }

    private var loadingState: some View {
        VStack(spacing: 12) {
            ProgressView().tint(Theme.chemphys)
            Text("Loading exam")
                .font(.mcatMono(13, relativeTo: .caption)).foregroundStyle(Theme.muted)
        }
    }

    private func errorState(_ message: String) -> some View {
        VStack(spacing: 12) {
            Image(systemName: "exclamationmark.triangle")
                .font(.title).foregroundStyle(Theme.warn)
            Text("Couldn't start the exam")
                .font(.mcatBody(17, relativeTo: .headline, semibold: true))
                .foregroundStyle(Theme.text)
            Text(message)
                .font(.mcatMono(12, relativeTo: .caption)).foregroundStyle(Theme.muted)
                .multilineTextAlignment(.center)
        }
        .padding(24)
    }
}

/// A single native exam question: countdown, optional CARS passage, prompt, four
/// tappable options, and (after answering) the explanation + auto-grade note.
struct ExamCardView: View {
    @ObservedObject var exam: ExamSessionStore
    let question: ExamSessionStore.Question

    /// The section hue anchors the card in the shared colour language — CARS is
    /// always the CARS hue, the sciences map from their topic.
    private var hue: Color {
        question.isCars ? Theme.cars : MCATSection.hue(for: question.topic)
    }

    var body: some View {
        VStack(spacing: 0) {
            CountdownTimerView(
                budgetSeconds: question.budgetSeconds,
                paused: exam.revealed
            ) {
                Task { await exam.timeoutExpired() }
            }
            // Fresh timer per card so the clock restarts each question.
            .id(question.cardId)
            .padding(.horizontal, 16)
            .padding(.vertical, 10)
            .background(Theme.panel)
            .overlay(Rectangle().fill(Theme.hairline).frame(height: 1), alignment: .bottom)

            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    if question.isCars, let passage = question.passage, !passage.isEmpty {
                        PassageView(html: passage, hue: hue)
                    }
                    if !question.topic.isEmpty {
                        HStack(spacing: 6) {
                            Circle().fill(hue).frame(width: 7, height: 7)
                            Text(HTMLText.plain(from: question.topic).uppercased())
                                .font(.mcatMono(11, relativeTo: .caption2, medium: true))
                                .tracking(1)
                                .foregroundStyle(Theme.muted)
                        }
                    }
                    Text(html: question.prompt)
                        .font(.mcatBody(18, relativeTo: .title3, semibold: true))
                        .foregroundStyle(Theme.text)
                        .fixedSize(horizontal: false, vertical: true)

                    ForEach(question.options) { option in
                        OptionButton(
                            option: option,
                            state: optionState(for: option),
                            enabled: !exam.revealed,
                            hue: hue
                        ) {
                            Task { await exam.choose(option.letter) }
                        }
                    }

                    if exam.revealed {
                        ExplanationView(exam: exam, question: question, hue: hue)
                    }
                }
                .padding(16)
            }

            SessionProgressBar(exam: exam)
        }
    }

    private func optionState(for option: ExamSessionStore.Option) -> OptionButton.State {
        guard exam.revealed else { return .neutral }
        if option.letter == question.correct { return .correct }
        if option.letter == exam.selectedLetter { return .wrong }
        return .neutral
    }
}

/// The CARS reading passage, shown above the question. Genuinely long, so it
/// lives inside the card's scroll view.
private struct PassageView: View {
    let html: String
    let hue: Color
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Eyebrow("Passage", accent: hue)
            Text(html: html)
                .font(.mcatBody(15, relativeTo: .subheadline))
                .foregroundStyle(Theme.text)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Theme.panel2)
        .overlay(alignment: .leading) { Rectangle().fill(hue).frame(width: 3) }
        .overlay(RoundedRectangle(cornerRadius: 12).stroke(Theme.hairline, lineWidth: 1))
        .clipShape(RoundedRectangle(cornerRadius: 12))
    }
}

/// A tappable answer option that recolours to show the verdict after answering.
struct OptionButton: View {
    enum State { case neutral, correct, wrong }

    let option: ExamSessionStore.Option
    let state: State
    let enabled: Bool
    var hue: Color = Theme.chemphys
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(alignment: .firstTextBaseline, spacing: 12) {
                Text(option.letter)
                    .font(.mcatMono(15, relativeTo: .body, medium: true))
                    .foregroundStyle(letterColor)
                    .frame(minWidth: 18, alignment: .leading)
                Text(html: option.text)
                    .font(.mcatBody(15, relativeTo: .body))
                    .foregroundStyle(Theme.text)
                    .fixedSize(horizontal: false, vertical: true)
                    .frame(maxWidth: .infinity, alignment: .leading)
                if state == .correct {
                    Image(systemName: "checkmark.circle.fill").foregroundStyle(Theme.ready)
                } else if state == .wrong {
                    Image(systemName: "xmark.circle.fill").foregroundStyle(Theme.miss)
                }
            }
            .padding(.vertical, 13).padding(.horizontal, 14)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(background)
            .overlay(
                RoundedRectangle(cornerRadius: 12).stroke(border, lineWidth: 1)
            )
            .clipShape(RoundedRectangle(cornerRadius: 12))
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .disabled(!enabled)
    }

    private var letterColor: Color {
        switch state {
        case .correct: return Theme.ready
        case .wrong: return Theme.miss
        case .neutral: return hue
        }
    }

    private var background: Color {
        switch state {
        case .correct: return Theme.ready.opacity(0.16)
        case .wrong: return Theme.miss.opacity(0.16)
        case .neutral: return Theme.panel
        }
    }

    private var border: Color {
        switch state {
        case .correct: return Theme.ready
        case .wrong: return Theme.miss
        case .neutral: return Theme.hairline
        }
    }
}

/// Verdict + correct answer + explanation + the honest "Auto-graded" note and
/// the Next button, revealed after answering (mirrors the desktop card).
private struct ExplanationView: View {
    @ObservedObject var exam: ExamSessionStore
    let question: ExamSessionStore.Question
    let hue: Color

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Rectangle().fill(Theme.hairline).frame(height: 1)
            Text(verdictText)
                .font(.mcatDisplay(22, relativeTo: .title3, bold: true))
                .foregroundStyle(verdictColor)
            Text("Correct answer: \(question.correct)")
                .font(.mcatMono(14, relativeTo: .subheadline, medium: true))
                .foregroundStyle(Theme.text)
            if !question.explanation.isEmpty {
                Text(html: question.explanation)
                    .font(.mcatBody(15, relativeTo: .subheadline))
                    .foregroundStyle(Theme.text)
                    .fixedSize(horizontal: false, vertical: true)
            }
            // Transparency: show exactly how the auto-grade mapped, like desktop.
            Text(exam.lastCorrect == true ? "Auto-graded: Good" : "Auto-graded: Again")
                .font(.mcatMono(11, relativeTo: .caption2)).italic()
                .foregroundStyle(Theme.muted)

            Button {
                Task { await exam.advance() }
            } label: {
                Text("Next")
            }
            .buttonStyle(InstrumentButtonStyle(tint: hue))
            .padding(.top, 4)
        }
    }

    private var verdictText: String {
        if exam.timedOut && exam.selectedLetter == nil { return "Time expired" }
        return exam.lastCorrect == true ? "Correct" : "Incorrect"
    }

    private var verdictColor: Color {
        exam.lastCorrect == true ? Theme.ready : Theme.miss
    }
}

/// Compact running tally at the bottom of the exam.
private struct SessionProgressBar: View {
    @ObservedObject var exam: ExamSessionStore
    var body: some View {
        HStack {
            Text("Answered \(exam.answeredCount)")
            Spacer()
            if exam.answeredCount > 0 {
                Text("\(exam.correctCount) correct • "
                    + "\(Int((Double(exam.correctCount) / Double(exam.answeredCount) * 100).rounded()))%")
            }
        }
        .font(.mcatMono(12, relativeTo: .caption))
        .foregroundStyle(Theme.muted)
        .padding(.horizontal, 16).padding(.vertical, 8)
        .frame(maxWidth: .infinity)
        .background(Theme.panel)
        .overlay(Rectangle().fill(Theme.hairline).frame(height: 1), alignment: .top)
    }
}

/// End-of-queue summary once no exam cards remain due.
private struct SessionSummaryView: View {
    @ObservedObject var exam: ExamSessionStore
    let onDone: () -> Void

    private var accuracy: Int {
        guard exam.answeredCount > 0 else { return 0 }
        return Int((Double(exam.correctCount) / Double(exam.answeredCount) * 100).rounded())
    }

    var body: some View {
        VStack(spacing: 18) {
            Image(systemName: "checkmark.seal.fill")
                .font(.system(size: 48)).foregroundStyle(Theme.ready)
            Text("Session complete")
                .font(.mcatDisplay(26, relativeTo: .title, bold: true))
                .foregroundStyle(Theme.text)
            if exam.answeredCount > 0 {
                VStack(spacing: 4) {
                    Text("\(exam.correctCount) / \(exam.answeredCount)")
                        .font(.mcatMono(28, relativeTo: .title, medium: true))
                        .foregroundStyle(Theme.text)
                    Text("\(accuracy)% correct")
                        .font(.mcatMono(14, relativeTo: .subheadline))
                        .foregroundStyle(Theme.muted)
                }
            } else {
                Text("No exam cards were due.")
                    .font(.mcatBody(14, relativeTo: .subheadline))
                    .foregroundStyle(Theme.muted)
            }
            Text("Your answers were written to the collection and "
                + "\(exam.answeredCount > 0 ? "synced" : "will sync") to AnkiWeb, so "
                + "your scores update on the desktop too.")
                .font(.mcatBody(12, relativeTo: .caption))
                .foregroundStyle(Theme.muted)
                .multilineTextAlignment(.center)
            Button("Done", action: onDone)
                .buttonStyle(InstrumentButtonStyle(tint: Theme.chemphys))
                .padding(.horizontal, 40)
        }
        .padding(24)
    }
}

// MARK: - Lightweight HTML → text

/// The MCAT notetype fields carry light HTML (paragraphs, <b>, entities like
/// &rarr;). We render natively rather than in a web view, so we reduce that
/// markup to readable plain text. This is intentionally simple: block tags
/// become line breaks and the remaining tags are stripped.
extension Text {
    init(html: String) {
        self.init(verbatim: HTMLText.plain(from: html))
    }
}

enum HTMLText {
    static func plain(from html: String) -> String {
        var s = html
        // Normalise common block-level breaks to newlines.
        for tag in ["<br>", "<br/>", "<br />", "</p>", "</div>", "</li>"] {
            s = s.replacingOccurrences(of: tag, with: "\n", options: .caseInsensitive)
        }
        // Strip any remaining tags.
        s = s.replacingOccurrences(
            of: "<[^>]+>", with: "", options: .regularExpression
        )
        // Decode the handful of entities our content uses.
        let entities: [String: String] = [
            "&rarr;": "→", "&larr;": "←", "&amp;": "&", "&lt;": "<",
            "&gt;": ">", "&quot;": "\"", "&#39;": "'", "&apos;": "'",
            "&nbsp;": " ", "&mdash;": "—", "&ndash;": "–",
        ]
        for (k, v) in entities {
            s = s.replacingOccurrences(of: k, with: v, options: .caseInsensitive)
        }
        // Collapse runs of blank lines and trim.
        s = s.replacingOccurrences(
            of: "\n[ \t]*\n[ \t\n]*", with: "\n\n", options: .regularExpression
        )
        return s.trimmingCharacters(in: .whitespacesAndNewlines)
    }
}
