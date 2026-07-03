// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import SwiftUI
import WebKit
import SwiftProtobuf

/// Drives a generic review session against any deck's scheduler queue, using the
/// engine's own template renderer (CardRenderingService.RenderExistingCard) for
/// the question/answer HTML — the same path the desktop reviewer uses. Answers
/// are real reviews written to the collection (FSRS + revlog), so they sync back
/// to AnkiWeb and show up identically on the desktop.
///
/// Media/LaTeX are intentionally NOT wired up in this pass: the rendered HTML is
/// loaded into a plain WKWebView with no media server, so images may not appear.
@MainActor
final class ReviewStore: ObservableObject {
    /// A rendered card: the full HTML documents for each side plus the
    /// scheduling states needed to answer it.
    struct RenderedCard {
        let cardId: Int64
        let questionHTML: String
        let answerHTML: String
        let states: Anki_Scheduler_SchedulingStates
    }

    /// One answer button: rating + human-readable next-interval label.
    struct Button: Identifiable {
        let rating: Anki_Scheduler_CardAnswer.Rating
        let label: String
        let title: String
        var id: Int { rating.rawValue }
    }

    @Published var card: RenderedCard?
    @Published var revealed = false
    @Published var buttons: [Button] = []
    @Published var loading = false
    @Published var finished = false
    @Published var errorMessage: String?
    @Published private(set) var answeredCount = 0

    private let collection: CollectionStore
    private let deckId: Int64
    let deckName: String
    private var cardShownAt = Date()

    private var backend: AnkiBackend? { collection.engine }

    init(collection: CollectionStore, deckId: Int64, deckName: String) {
        self.collection = collection
        self.deckId = deckId
        self.deckName = deckName
    }

    // MARK: - Session lifecycle

    /// Scope the scheduler to this deck, then show the first due card.
    func start() async {
        guard let backend else {
            errorMessage = "Engine not ready."
            return
        }
        loading = true
        defer { loading = false }
        finished = false
        answeredCount = 0
        let deckId = self.deckId
        do {
            try await background { try backend.setCurrentDeck(id: deckId) }
            await loadNextCard()
        } catch {
            errorMessage = "\(error)"
        }
    }

    /// Fetch the next queued card, render both sides, and prepare the buttons.
    private func loadNextCard() async {
        guard let backend else { return }
        revealed = false
        do {
            let (rendered, labels): (RenderedCard?, [String]) = try await background {
                let queued = try backend.queuedCards(fetchLimit: 1)
                guard let qc = queued.cards.first else { return (nil, []) }
                let response = try backend.renderExistingCard(cardId: qc.card.id)
                let question = Self.document(
                    nodes: response.questionNodes, css: response.css)
                let answer = Self.document(
                    nodes: response.answerNodes, css: response.css)
                let labels = (try? backend.describeNextStates(qc.states)) ?? []
                let rendered = RenderedCard(
                    cardId: qc.card.id,
                    questionHTML: question,
                    answerHTML: answer,
                    states: qc.states
                )
                return (rendered, labels)
            }
            guard let rendered else {
                card = nil
                finished = true
                await syncStudyWrites()
                return
            }
            card = rendered
            buttons = Self.makeButtons(labels: labels)
            cardShownAt = Date()
        } catch {
            errorMessage = "\(error)"
        }
    }

    // MARK: - Answering

    func showAnswer() {
        revealed = true
    }

    /// Record the chosen rating as a real review, then advance.
    func answer(_ rating: Anki_Scheduler_CardAnswer.Rating) async {
        guard let backend, let card else { return }
        let elapsedMs = UInt32(
            min(Double(UInt32.max),
                max(0, Date().timeIntervalSince(cardShownAt) * 1000))
        )
        var answer = Anki_Scheduler_CardAnswer()
        answer.cardID = card.cardId
        answer.currentState = card.states.current
        answer.newState = newState(for: rating, states: card.states)
        answer.rating = rating
        answer.answeredAtMillis = Int64(Date().timeIntervalSince1970 * 1000)
        answer.millisecondsTaken = elapsedMs
        do {
            try await background { try backend.answerCard(answer) }
            answeredCount += 1
            await loadNextCard()
        } catch {
            errorMessage = "Failed to record answer: \(error)"
        }
    }

    func endSession() async {
        await syncStudyWrites()
    }

    private func syncStudyWrites() async {
        guard collection.canSync else { return }
        await collection.sync()
    }

    // MARK: - Helpers

    private func newState(
        for rating: Anki_Scheduler_CardAnswer.Rating,
        states: Anki_Scheduler_SchedulingStates
    ) -> Anki_Scheduler_SchedulingState {
        switch rating {
        case .again: return states.again
        case .hard: return states.hard
        case .good: return states.good
        case .easy: return states.easy
        case .UNRECOGNIZED: return states.good
        }
    }

    /// Build the four answer buttons. `describeNextStates` returns the interval
    /// labels in again/hard/good/easy order; fall back to plain titles if the
    /// engine returned nothing.
    private static func makeButtons(labels: [String]) -> [Button] {
        let ratings: [Anki_Scheduler_CardAnswer.Rating] = [.again, .hard, .good, .easy]
        let titles = ["Again", "Hard", "Good", "Easy"]
        return ratings.enumerated().map { i, rating in
            Button(
                rating: rating,
                label: i < labels.count ? labels[i] : "",
                title: titles[i]
            )
        }
    }

    /// Wrap the rendered template nodes in a minimal HTML document, applying the
    /// card's CSS. Fully-rendered cards yield text nodes; any leftover
    /// replacement (e.g. an unknown filter) falls back to its current text.
    private static func document(
        nodes: [Anki_CardRendering_RenderedTemplateNode], css: String
    ) -> String {
        var body = ""
        for node in nodes {
            switch node.value {
            case let .text(text): body += text
            case let .replacement(rep): body += rep.currentText
            case nil: break
            }
        }
        return """
        <!DOCTYPE html>
        <html>
        <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1">
        <style>
        :root { color-scheme: light dark; }
        body { margin: 16px; -webkit-text-size-adjust: 100%; }
        \(css)
        </style>
        </head>
        <body class="card">
        \(body)
        </body>
        </html>
        """
    }

    private func background<T>(_ work: @escaping () throws -> T) async throws -> T {
        try await withCheckedThrowingContinuation { continuation in
            DispatchQueue.global(qos: .userInitiated).async {
                do {
                    continuation.resume(returning: try work())
                } catch {
                    continuation.resume(throwing: error)
                }
            }
        }
    }
}

/// The generic reviewer screen: a WKWebView showing the rendered card, with a
/// "Show answer" button that flips to the four rating buttons. The card itself
/// is engine-rendered HTML; the surrounding cockpit (background, dividers,
/// buttons) is themed to match the instrument.
struct ReviewView: View {
    @ObservedObject var collection: CollectionStore
    @StateObject private var review: ReviewStore
    @Environment(\.dismiss) private var dismiss

    init(collection: CollectionStore, deckId: Int64, deckName: String) {
        self.collection = collection
        _review = StateObject(wrappedValue: ReviewStore(
            collection: collection, deckId: deckId, deckName: deckName))
    }

    var body: some View {
        ZStack {
            Theme.ink.ignoresSafeArea()
            Group {
                if review.loading {
                    loadingState
                } else if let message = review.errorMessage {
                    errorState(message)
                } else if let card = review.card {
                    cardView(card)
                } else if review.finished {
                    summary
                } else {
                    ProgressView().tint(Theme.chemphys)
                }
            }
        }
        .navigationTitle(review.deckName)
        .navigationBarTitleDisplayMode(.inline)
        .toolbarBackground(Theme.panel, for: .navigationBar)
        .toolbarBackground(.visible, for: .navigationBar)
        .task { await review.start() }
        .onDisappear { Task { await review.endSession() } }
    }

    private var loadingState: some View {
        VStack(spacing: 12) {
            ProgressView().tint(Theme.chemphys)
            Text("Loading cards")
                .font(.mcatMono(13, relativeTo: .caption)).foregroundStyle(Theme.muted)
        }
    }

    private func cardView(_ card: ReviewStore.RenderedCard) -> some View {
        VStack(spacing: 0) {
            CardWebView(html: review.revealed ? card.answerHTML : card.questionHTML)
                .id("\(card.cardId)-\(review.revealed)")

            Rectangle().fill(Theme.hairline).frame(height: 1)

            if review.revealed {
                ratingButtons
            } else {
                Button {
                    review.showAnswer()
                } label: {
                    Text("Show answer")
                }
                .buttonStyle(InstrumentButtonStyle(tint: Theme.chemphys))
                .padding(16)
            }
        }
    }

    private var ratingButtons: some View {
        HStack(spacing: 8) {
            ForEach(review.buttons) { button in
                Button {
                    Task { await review.answer(button.rating) }
                } label: {
                    VStack(spacing: 3) {
                        Text(button.title)
                            .font(.mcatBody(14, relativeTo: .subheadline, semibold: true))
                            .foregroundStyle(Theme.text)
                        if !button.label.isEmpty {
                            Text(button.label)
                                .font(.mcatMono(10, relativeTo: .caption2))
                                .foregroundStyle(Theme.muted)
                        }
                    }
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 10)
                    .background(color(for: button.rating).opacity(0.15))
                    .overlay(
                        RoundedRectangle(cornerRadius: 10)
                            .stroke(color(for: button.rating), lineWidth: 1)
                    )
                    .clipShape(RoundedRectangle(cornerRadius: 10))
                }
                .buttonStyle(.plain)
            }
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 10)
        .background(Theme.panel)
    }

    private func color(for rating: Anki_Scheduler_CardAnswer.Rating) -> Color {
        switch rating {
        case .again: return Theme.miss
        case .hard: return Theme.warn
        case .good: return Theme.ready
        case .easy: return Theme.chemphys
        case .UNRECOGNIZED: return Theme.muted
        }
    }

    private var summary: some View {
        VStack(spacing: 16) {
            Image(systemName: "checkmark.seal.fill")
                .font(.system(size: 48)).foregroundStyle(Theme.ready)
            Text("All done")
                .font(.mcatDisplay(26, relativeTo: .title, bold: true))
                .foregroundStyle(Theme.text)
            Text(review.answeredCount > 0
                ? "\(review.answeredCount) card\(review.answeredCount == 1 ? "" : "s") reviewed."
                : "No cards were due in this deck.")
                .font(.mcatBody(14, relativeTo: .subheadline))
                .foregroundStyle(Theme.muted)
            Text("Your reviews were written to the collection and "
                + "\(review.answeredCount > 0 ? "synced" : "will sync") to AnkiWeb.")
                .font(.mcatBody(12, relativeTo: .caption))
                .foregroundStyle(Theme.muted)
                .multilineTextAlignment(.center)
            Button("Done") { dismiss() }
                .buttonStyle(InstrumentButtonStyle(tint: Theme.chemphys))
                .padding(.horizontal, 40)
        }
        .padding(24)
    }

    private func errorState(_ message: String) -> some View {
        VStack(spacing: 12) {
            Image(systemName: "exclamationmark.triangle")
                .font(.title).foregroundStyle(Theme.warn)
            Text("Couldn't load cards")
                .font(.mcatBody(17, relativeTo: .headline, semibold: true))
                .foregroundStyle(Theme.text)
            Text(message)
                .font(.mcatMono(12, relativeTo: .caption)).foregroundStyle(Theme.muted)
                .multilineTextAlignment(.center)
        }
        .padding(24)
    }
}

/// Minimal WKWebView wrapper that renders a static HTML string. No media server
/// or custom URL-scheme handler this pass, so remote/media resources may not
/// load — that's expected for the lean reviewer.
struct CardWebView: UIViewRepresentable {
    let html: String

    func makeUIView(context: Context) -> WKWebView {
        let webView = WKWebView(frame: .zero, configuration: WKWebViewConfiguration())
        webView.isOpaque = false
        webView.backgroundColor = .clear
        webView.scrollView.backgroundColor = .clear
        return webView
    }

    func updateUIView(_ webView: WKWebView, context: Context) {
        webView.loadHTMLString(html, baseURL: nil)
    }
}
