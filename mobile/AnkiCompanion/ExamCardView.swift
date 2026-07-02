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
        Group {
            if exam.loading {
                ProgressView("Loading exam…")
            } else if let message = exam.errorMessage {
                errorState(message)
            } else if let question = exam.question {
                ExamCardView(exam: exam, question: question)
            } else if exam.finished {
                SessionSummaryView(exam: exam) { dismiss() }
            } else {
                ProgressView()
            }
        }
        .navigationTitle("Exam")
        .navigationBarTitleDisplayMode(.inline)
        .task { await exam.start() }
        .onDisappear { Task { await exam.endSession() } }
    }

    private func errorState(_ message: String) -> some View {
        VStack(spacing: 12) {
            Image(systemName: "exclamationmark.triangle")
                .font(.largeTitle).foregroundStyle(.secondary)
            Text("Couldn't start the exam").font(.headline)
            Text(message)
                .font(.caption).foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
        }
        .padding()
    }
}

/// A single native exam question: countdown, optional CARS passage, prompt, four
/// tappable options, and (after answering) the explanation + auto-grade note.
struct ExamCardView: View {
    @ObservedObject var exam: ExamSessionStore
    let question: ExamSessionStore.Question

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
            .padding(.horizontal)
            .padding(.vertical, 8)

            ScrollView {
                VStack(alignment: .leading, spacing: 14) {
                    if question.isCars, let passage = question.passage, !passage.isEmpty {
                        PassageView(html: passage)
                    }
                    if !question.topic.isEmpty {
                        Text(html: question.topic)
                            .font(.caption).textCase(.uppercase)
                            .foregroundStyle(.secondary)
                    }
                    Text(html: question.prompt)
                        .font(.headline)
                        .fixedSize(horizontal: false, vertical: true)

                    ForEach(question.options) { option in
                        OptionButton(
                            option: option,
                            state: optionState(for: option),
                            enabled: !exam.revealed
                        ) {
                            Task { await exam.choose(option.letter) }
                        }
                    }

                    if exam.revealed {
                        ExplanationView(exam: exam, question: question)
                    }
                }
                .padding()
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

/// The CARS reading passage, shown above the question.
private struct PassageView: View {
    let html: String
    var body: some View {
        Text(html: html)
            .font(.subheadline)
            .fixedSize(horizontal: false, vertical: true)
            .padding()
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Color.secondary.opacity(0.08))
            .clipShape(RoundedRectangle(cornerRadius: 10))
    }
}

/// A tappable answer option that recolours to show the verdict after answering.
struct OptionButton: View {
    enum State { case neutral, correct, wrong }

    let option: ExamSessionStore.Option
    let state: State
    let enabled: Bool
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(alignment: .firstTextBaseline, spacing: 10) {
                Text("\(option.letter).")
                    .font(.body.bold())
                    .frame(minWidth: 20, alignment: .leading)
                Text(html: option.text)
                    .fixedSize(horizontal: false, vertical: true)
                    .frame(maxWidth: .infinity, alignment: .leading)
                if state == .correct {
                    Image(systemName: "checkmark.circle.fill").foregroundStyle(.green)
                } else if state == .wrong {
                    Image(systemName: "xmark.circle.fill").foregroundStyle(.red)
                }
            }
            .padding(.vertical, 12).padding(.horizontal, 14)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(background)
            .overlay(
                RoundedRectangle(cornerRadius: 10).stroke(border, lineWidth: 1)
            )
            .clipShape(RoundedRectangle(cornerRadius: 10))
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .disabled(!enabled)
    }

    private var background: Color {
        switch state {
        case .correct: return .green.opacity(0.15)
        case .wrong: return .red.opacity(0.15)
        case .neutral: return Color.secondary.opacity(0.06)
        }
    }

    private var border: Color {
        switch state {
        case .correct: return .green
        case .wrong: return .red
        case .neutral: return Color.secondary.opacity(0.3)
        }
    }
}

/// Verdict + correct answer + explanation + the honest "Auto-graded" note and
/// the Next button, revealed after answering (mirrors the desktop card).
private struct ExplanationView: View {
    @ObservedObject var exam: ExamSessionStore
    let question: ExamSessionStore.Question

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Divider()
            Text(verdictText)
                .font(.title3.bold())
                .foregroundStyle(verdictColor)
            Text("Correct answer: \(question.correct)")
                .font(.subheadline)
            if !question.explanation.isEmpty {
                Text(html: question.explanation)
                    .font(.subheadline)
                    .fixedSize(horizontal: false, vertical: true)
            }
            // Transparency: show exactly how the auto-grade mapped, like desktop.
            Text(exam.lastCorrect == true
                ? "Auto-graded: Good"
                : "Auto-graded: Again")
                .font(.caption).italic()
                .foregroundStyle(.secondary)

            Button {
                Task { await exam.advance() }
            } label: {
                Text("Next")
                    .font(.headline)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 10)
            }
            .buttonStyle(.borderedProminent)
            .padding(.top, 4)
        }
    }

    private var verdictText: String {
        if exam.timedOut && exam.selectedLetter == nil { return "Time expired" }
        return exam.lastCorrect == true ? "Correct" : "Incorrect"
    }

    private var verdictColor: Color {
        exam.lastCorrect == true ? .green : .red
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
        .font(.caption).foregroundStyle(.secondary)
        .padding(.horizontal).padding(.vertical, 6)
        .frame(maxWidth: .infinity)
        .background(.thinMaterial)
    }
}

/// End-of-queue summary once no exam cards remain due.
private struct SessionSummaryView: View {
    @ObservedObject var exam: ExamSessionStore
    let onDone: () -> Void

    var body: some View {
        VStack(spacing: 16) {
            Image(systemName: "checkmark.seal.fill")
                .font(.system(size: 52)).foregroundStyle(.green)
            Text("Exam session complete").font(.title2.bold())
            if exam.answeredCount > 0 {
                Text("\(exam.correctCount) / \(exam.answeredCount) correct "
                    + "(\(Int((Double(exam.correctCount) / Double(exam.answeredCount) * 100).rounded()))%)")
                    .font(.headline).foregroundStyle(.secondary)
            } else {
                Text("No exam cards were due.")
                    .font(.subheadline).foregroundStyle(.secondary)
            }
            Text("Your answers were written to the collection and "
                + "\(exam.answeredCount > 0 ? "synced" : "will sync") to AnkiWeb, so "
                + "your scores update on the desktop too.")
                .font(.caption).foregroundStyle(.secondary)
                .multilineTextAlignment(.center).padding(.horizontal)
            Button("Done", action: onDone)
                .buttonStyle(.borderedProminent)
        }
        .padding()
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
