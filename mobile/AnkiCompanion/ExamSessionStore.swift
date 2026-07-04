// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import Foundation
import SwiftProtobuf

/// Drives a native, timed MCAT exam session against the `MCAT::Exam` scheduler
/// queue. This is the mobile analogue of the desktop reviewer's MCAT exam mode
/// (see qt/aqt/reviewer.py): each answer is a *real* review written back to the
/// collection (FSRS memory state + review log), so the scores update identically
/// everywhere and — once synced — reach the desktop.
///
/// Grading mirrors the desktop: a correct MCQ selection → Good, a wrong one (or
/// a countdown timeout with no selection) → Again. The per-question budget comes
/// from the topic's target time (CARS ~90s, sciences ~35–50s).
@MainActor
final class ExamSessionStore: ObservableObject {
    /// One tappable multiple-choice option.
    struct Option: Identifiable {
        let letter: String
        let text: String
        var id: String { letter }
    }

    /// A single exam question, parsed from the note's fields, ready to render.
    struct Question {
        let cardId: Int64
        let noteId: Int64
        let isCars: Bool
        let passage: String?
        let topic: String
        let prompt: String
        let options: [Option]
        /// The correct option letter (A–D), upper-cased.
        let correct: String
        let explanation: String
        /// Per-question countdown budget in seconds.
        let budgetSeconds: Int
        /// Precomputed next-state options, needed to answer the card.
        let states: Anki_Scheduler_SchedulingStates
    }

    @Published var question: Question?
    @Published var loading = false
    @Published var submitting = false
    @Published var finished = false
    @Published var errorMessage: String?

    // Session tally.
    @Published private(set) var answeredCount = 0
    @Published private(set) var correctCount = 0

    // Per-question interaction state.
    @Published private(set) var selectedLetter: String?
    @Published private(set) var revealed = false
    /// nil until answered; then true (Good) / false (Again).
    @Published private(set) var lastCorrect: Bool?
    /// True when the reveal happened because the countdown expired.
    @Published private(set) var timedOut = false

    private let collection: CollectionStore
    private var targets: [String: Double] = [:]
    /// When the current question was first shown, for `milliseconds_taken`.
    private var questionStart = Date()

    /// Default budget when a topic target is unknown (matches the desktop's
    /// CARS/default fallback in `_mcat_time_budget`).
    private let defaultBudget = 90
    private let examDeckName = "MCAT::Exam"

    init(collection: CollectionStore) {
        self.collection = collection
    }

    private var backend: AnkiBackend? { collection.engine }

    // MARK: - Session lifecycle

    /// Load topic targets, scope the scheduler to MCAT::Exam, and show the first
    /// card.
    func start() async {
        guard let backend else {
            errorMessage = "Engine not ready."
            return
        }
        loading = true
        defer { loading = false }
        finished = false
        answeredCount = 0
        correctCount = 0
        do {
            let targetList = try await background { try backend.topicTargets() }
            targets = Dictionary(
                targetList.targets.map { ($0.topicKey, $0.targetSeconds) },
                uniquingKeysWith: { a, _ in a }
            )
            let deckName = examDeckName
            let deckId = try await background { try backend.deckId(named: deckName) }
            guard deckId != 0 else {
                errorMessage = "No \(examDeckName) deck found. Sync your "
                    + "collection first, then try again."
                return
            }
            try await background { try backend.setCurrentDeck(id: deckId) }
            await loadNextCard()
        } catch {
            errorMessage = "\(error)"
        }
    }

    /// Fetch and parse the next queued exam card, or mark the session finished
    /// when the queue is empty.
    private func loadNextCard() async {
        guard let backend else { return }
        resetQuestionState()
        do {
            let queued = try await background { try backend.queuedCards(fetchLimit: 1) }
            guard let qc = queued.cards.first else {
                question = nil
                finished = true
                await syncStudyWrites()
                return
            }
            let noteId = qc.card.noteID
            let note = try await background { try backend.note(id: noteId) }
            question = makeQuestion(card: qc, note: note)
            questionStart = Date()
        } catch {
            errorMessage = "\(error)"
        }
    }

    // MARK: - Answering

    /// The user tapped an option. Reveal the verdict and write the review.
    func choose(_ letter: String) async {
        await reveal(chosen: letter, timedOut: false)
    }

    /// The countdown hit zero. Reveal (Again if nothing was chosen) and, after a
    /// short delay so the answer is visible, advance — mirroring the desktop's
    /// ~1.5s reveal delay on timeout.
    func timeoutExpired() async {
        guard !revealed, question != nil else { return }
        await reveal(chosen: nil, timedOut: true)
        try? await Task.sleep(nanoseconds: 1_500_000_000)
        // Only auto-advance if we're still on the same (revealed) card.
        if revealed { await advance() }
    }

    private func reveal(chosen letter: String?, timedOut: Bool) async {
        guard let q = question, !revealed, !submitting else { return }
        submitting = true
        defer { submitting = false }
        revealed = true
        self.timedOut = timedOut
        selectedLetter = letter
        let elapsedMs = UInt32(
            min(Double(UInt32.max), max(0, Date().timeIntervalSince(questionStart) * 1000))
        )
        let isCorrect = (letter?.uppercased() == q.correct)
        lastCorrect = isCorrect
        answeredCount += 1
        if isCorrect { correctCount += 1 }
        await writeAnswer(question: q, correct: isCorrect, elapsedMs: elapsedMs)
    }

    /// Build and send the CardAnswer. Correct → Good, wrong/timeout → Again,
    /// using the precomputed next-state so FSRS schedules the card correctly.
    private func writeAnswer(question q: Question, correct: Bool, elapsedMs: UInt32) async {
        guard let backend else { return }
        var answer = Anki_Scheduler_CardAnswer()
        answer.cardID = q.cardId
        answer.currentState = q.states.current
        answer.newState = correct ? q.states.good : q.states.again
        answer.rating = correct ? .good : .again
        answer.answeredAtMillis = Int64(Date().timeIntervalSince1970 * 1000)
        answer.millisecondsTaken = elapsedMs
        do {
            try await background { try backend.answerCard(answer) }
        } catch {
            if !"\(error)".contains("card was modified") {
                errorMessage = "Failed to record answer: \(error)"
            }
        }
    }

    /// Move to the next card (invoked by the "Next" button after a reveal).
    func advance() async {
        guard revealed else { return }
        await loadNextCard()
    }

    /// Push study writes to AnkiWeb so they reach the desktop. Best-effort: if
    /// not signed in, the reviews still live in the local collection and will
    /// sync on the next manual sync.
    func endSession() async {
        await syncStudyWrites()
    }

    private func syncStudyWrites() async {
        guard collection.canSync else { return }
        await collection.sync()
    }

    // MARK: - Parsing

    /// Parse a queued card's note into a renderable Question.
    ///
    /// Field order comes from mcat/gen_deck.py:
    ///   MCATExam (8):        Question, A, B, C, D, Correct, Explanation, Topic
    ///   MCATCarsPassage (9): Passage, Question, A, B, C, D, Correct, Explanation, Topic
    /// The extra leading Passage field is a reliable discriminator between the
    /// two exam notetypes that populate MCAT::Exam.
    private func makeQuestion(
        card qc: Anki_Scheduler_QueuedCards.QueuedCard,
        note: Anki_Notes_Note
    ) -> Question {
        let f = note.fields
        let isCars = f.count >= 9
        let base = isCars ? 1 : 0
        func field(_ i: Int) -> String { i < f.count ? f[i] : "" }

        let passage = isCars ? field(0) : nil
        let prompt = field(base + 0)
        let options = zip(["A", "B", "C", "D"], (1...4).map { field(base + $0) })
            .map { Option(letter: $0.0, text: $0.1) }
        let correct = field(base + 5).trimmingCharacters(in: .whitespacesAndNewlines).uppercased()
        let explanation = field(base + 6)
        let topic = field(base + 7)

        return Question(
            cardId: qc.card.id,
            noteId: note.id,
            isCars: isCars,
            passage: passage,
            topic: topic,
            prompt: prompt,
            options: options,
            correct: correct,
            explanation: explanation,
            budgetSeconds: budget(forTags: note.tags),
            states: qc.states
        )
    }

    /// Per-question countdown budget from the card's `mcat::section::topic` tag,
    /// falling back to the default. Mirrors the desktop's `_mcat_time_budget`.
    private func budget(forTags tags: [String]) -> Int {
        for tag in tags {
            if tag == "mcat::exam" || tag == "mcat::perf" { continue }
            if tag.hasPrefix("mcat::"),
               tag.components(separatedBy: "::").count >= 3,
               let secs = targets[tag], secs > 0 {
                return Int(secs.rounded())
            }
        }
        return defaultBudget
    }

    private func resetQuestionState() {
        selectedLetter = nil
        revealed = false
        lastCorrect = nil
        timedOut = false
    }

    /// Run blocking engine work off the main thread (mirrors CollectionStore).
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
