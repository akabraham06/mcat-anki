// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import SwiftUI

struct ContentView: View {
    @StateObject private var store = CollectionStore()
    @Environment(\.scenePhase) private var scenePhase
    @State private var showingLogin = false

    var body: some View {
        NavigationStack {
            Group {
                if store.loading {
                    ProgressView("Loading engine…")
                } else if let readiness = store.readiness {
                    ReadinessView(readiness: readiness, store: store)
                } else if let message = store.errorMessage {
                    errorState(message)
                } else {
                    Text("No data")
                }
            }
            .navigationTitle("MCAT Readiness")
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    SyncButton(store: store, showingLogin: $showingLogin)
                }
            }
            .safeAreaInset(edge: .bottom) {
                if let message = store.syncMessage {
                    Text(message)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .frame(maxWidth: .infinity)
                        .padding(6)
                        .background(.thinMaterial)
                }
            }
        }
        .sheet(isPresented: $showingLogin) {
            LoginView(store: store)
        }
        .task { await store.start() }
        .onChange(of: scenePhase) { phase in
            // Pull desktop changes when the app returns to the foreground.
            if phase == .active, store.loggedIn, !store.loading {
                Task { await store.sync() }
            }
        }
    }

    private func errorState(_ message: String) -> some View {
        VStack(spacing: 12) {
            Text("Couldn't load readiness").font(.headline)
            Text(message)
                .font(.caption)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
        }
        .padding()
    }
}

// MARK: - Readiness dashboard

struct ReadinessView: View {
    let readiness: Anki_Mcat_ExamReadiness
    @ObservedObject var store: CollectionStore

    private var scores: [Anki_Mcat_ScoreEstimate] {
        [readiness.readiness, readiness.memory, readiness.performance]
    }

    var body: some View {
        List {
            Section {
                HStack {
                    Label("Coverage \(pct(readiness.overallCoveragePercent))",
                          systemImage: "chart.pie")
                    Spacer()
                    Text("\(readiness.gradedReviews) graded reviews")
                        .foregroundStyle(.secondary)
                }
                .font(.caption)
                if readiness.hasGiveUpRule {
                    Text(readiness.giveUpRule.description_p)
                        .font(.caption).italic()
                        .foregroundStyle(.secondary)
                }
            }

            Section("Scores") {
                ForEach(scores, id: \.label) { score in
                    ScoreRow(score: score, readiness: readiness)
                }
            }

            if readiness.hasRecommendation, readiness.recommendation.available {
                RecommendationSection(recommendation: readiness.recommendation)
            }

            if !readiness.sections.isEmpty {
                SectionBreakdown(sections: readiness.sections)
            }

            if !readiness.transferGaps.isEmpty {
                TransferGapSection(gaps: readiness.transferGaps)
            }

            DeckBrowseSection(store: store)

            InterleaveSection(store: store)

            ExamEntrySection(store: store)

            if readiness.hasXp {
                XpSection(xp: readiness.xp)
            }
        }
        .refreshable { await store.sync() }
    }
}

// MARK: - Score card with honesty metadata + per-score detail

struct ScoreRow: View {
    let score: Anki_Mcat_ScoreEstimate
    let readiness: Anki_Mcat_ExamReadiness

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(score.label).font(.headline)
            if score.available {
                Text("\(Int(score.point.rounded())) "
                    + "(\(Int(score.low.rounded()))–\(Int(score.high.rounded())))")
                    .font(.title3).bold()
                RangeBar(score: score)
                Text("Coverage \(pct(score.coveragePercent)) • "
                    + "\(score.confidence) confidence")
                    .font(.caption).foregroundStyle(.secondary)
                if !score.reasons.isEmpty {
                    VStack(alignment: .leading, spacing: 1) {
                        ForEach(score.reasons, id: \.self) { reason in
                            Text("• \(reason)")
                        }
                    }
                    .font(.caption2).foregroundStyle(.secondary)
                }
            } else {
                Text("No score yet").font(.title3).foregroundStyle(.secondary)
                Text(score.abstainReason)
                    .font(.caption).foregroundStyle(.secondary)
                Text("Coverage \(pct(score.coveragePercent))")
                    .font(.caption2).foregroundStyle(.secondary)
            }
            detail
        }
        .padding(.vertical, 2)
    }

    @ViewBuilder
    private var detail: some View {
        if score.label == "Memory", readiness.hasMemoryDetail {
            MemoryDetailView(detail: readiness.memoryDetail)
        } else if score.label == "Performance", readiness.hasPerformanceDetail {
            PerformanceDetailView(detail: readiness.performanceDetail)
        } else if score.label == "Readiness", readiness.hasReadinessDetail {
            ReadinessDetailView(detail: readiness.readinessDetail)
        }
    }
}

struct RangeBar: View {
    let score: Anki_Mcat_ScoreEstimate

    var body: some View {
        GeometryReader { geo in
            let range = max(score.scaleMax - score.scaleMin, 1)
            let w = geo.size.width
            let bandLeft = CGFloat((score.low - score.scaleMin) / range) * w
            let bandWidth = CGFloat((score.high - score.low) / range) * w
            let pointX = CGFloat((score.point - score.scaleMin) / range) * w
            ZStack(alignment: .leading) {
                Capsule().fill(Color.secondary.opacity(0.2)).frame(height: 6)
                Capsule().fill(Color.accentColor.opacity(0.35))
                    .frame(width: max(bandWidth, 2), height: 6)
                    .offset(x: bandLeft)
                Capsule().fill(Color.accentColor)
                    .frame(width: 3, height: 12)
                    .offset(x: min(max(pointX - 1.5, 0), w - 3))
            }
            .frame(height: 12)
        }
        .frame(height: 12)
    }
}

// MARK: - Detail views (rubric parity with the desktop dashboard)

struct MemoryDetailView: View {
    let detail: Anki_Mcat_MemoryDetail
    var body: some View {
        StatGrid(rows: {
            var rows: [(String, String)] = [
                ("Cards reviewed", "\(detail.cardsReviewed) / \(detail.cardsTotal)"),
            ]
            if detail.cardsReviewed > 0 {
                rows.append(("Avg retention", pct(detail.averageRetentionPercent)))
            }
            rows.append(("Graded reviews", "\(detail.gradedReviews)"))
            rows.append(("Mature / young", "\(detail.matureCards) / \(detail.youngCards)"))
            rows.append(("Breadth",
                "\(detail.coveredTopics) / \(detail.totalTopics) topics "
                + "(\(pct(detail.breadthPercent)))"))
            return rows
        }())
    }
}

struct PerformanceDetailView: View {
    let detail: Anki_Mcat_PerformanceDetail
    var body: some View {
        StatGrid(rows: {
            var rows: [(String, String)] = [
                ("Questions answered", "\(detail.questionsAnswered)"),
            ]
            if detail.questionsAnswered > 0 {
                rows.append(("Accuracy", pct(detail.accuracyPercent)))
                rows.append(("Correct", "\(detail.correct) / \(detail.questionsAnswered)"))
                // Pacing: how fast (mean seconds) and how often within the target.
                rows.append(("Avg time", "\(one(detail.averageResponseTimeSecs))s"))
                rows.append(("On time", pct(detail.onTimeRate * 100)))
                rows.append(("Overtime", pct(detail.overtimeRate * 100)))
            }
            rows.append(("Topics covered", "\(detail.coveredTopics) / \(detail.totalTopics)"))
            return rows
        }())
    }
}

struct ReadinessDetailView: View {
    let detail: Anki_Mcat_ReadinessDetail
    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            StatGrid(rows: [
                ("Graded reviews",
                 "\(detail.gradedReviews) / \(detail.requiredGradedReviews)",
                 detail.gradedReviewsMet),
                ("Coverage",
                 "\(pct(detail.coveragePercent)) / \(pct(detail.requiredCoveragePercent))",
                 detail.coverageMet),
                // Speed/pacing sub-signal folded into readiness. 100% = every
                // answer within its per-topic time target (untimed = full speed).
                ("Speed factor", pct(detail.speedFactor * 100), detail.speedFactor >= 0.999),
                ("Overtime rate", pct(detail.overtimeRate * 100), false),
            ])
            // The weights are shown so the blend is transparent, never hidden.
            StatGrid(rows: [
                ("Weights (mem / perf / speed)",
                 "\(pct(detail.memoryWeight * 100)) / "
                    + "\(pct(detail.performanceWeight * 100)) / "
                    + "\(pct(detail.speedWeight * 100))"),
            ])
            if !detail.speedReason.isEmpty {
                Text(detail.speedReason)
                    .font(.caption2).italic()
                    .foregroundStyle(.secondary)
                    .padding(.top, 1)
            }
        }
    }
}

/// Two-column label/value grid used by the detail views. Rows may flag a "met"
/// state (green) so the readiness gate is transparent.
struct StatGrid: View {
    let rows: [(label: String, value: String, met: Bool)]

    init(rows: [(String, String)]) {
        self.rows = rows.map { ($0.0, $0.1, false) }
    }
    init(rows: [(String, String, Bool)]) {
        self.rows = rows.map { ($0.0, $0.1, $0.2) }
    }

    var body: some View {
        VStack(spacing: 2) {
            ForEach(rows.indices, id: \.self) { i in
                HStack {
                    Text(rows[i].label).foregroundStyle(.secondary)
                    Spacer()
                    Text(rows[i].value)
                        .foregroundStyle(rows[i].met ? Color.green : Color.primary)
                        .fontWeight(rows[i].met ? .semibold : .regular)
                        .monospacedDigit()
                }
            }
        }
        .font(.caption)
        .padding(.top, 4)
    }
}

// MARK: - Recommendation

struct RecommendationSection: View {
    let recommendation: Anki_Mcat_StudyRecommendation
    var body: some View {
        Section("Study next") {
            Text(recommendation.topicName).font(.headline)
            Text(recommendation.explanation)
                .font(.caption).foregroundStyle(.secondary)
            ForEach(recommendation.candidates, id: \.topicKey) { c in
                HStack {
                    Text(c.topicName)
                    Spacer()
                    Text("w \(one(c.priorityScore)) • \(c.dueCards) due")
                        .font(.caption).foregroundStyle(.secondary).monospacedDigit()
                }
                .font(.subheadline)
            }
        }
    }
}

// MARK: - Section breakdown (memory % + reviewed/total)

struct SectionBreakdown: View {
    let sections: [Anki_Mcat_SectionScore]
    var body: some View {
        Section("By section (memory)") {
            ForEach(sections, id: \.sectionKey) { s in
                VStack(alignment: .leading, spacing: 2) {
                    HStack {
                        Text(s.sectionName)
                        Spacer()
                        if s.available {
                            Text("\(Int(s.point.rounded())) "
                                + "(\(Int(s.low.rounded()))–\(Int(s.high.rounded())))")
                                .monospacedDigit()
                        } else {
                            Text("no data").foregroundStyle(.secondary)
                        }
                    }
                    HStack {
                        Text(s.available ? "mem \(pct(s.memoryPercent))" : "—")
                        Spacer()
                        Text("\(s.cardsReviewed)/\(s.cardsTotal) cards")
                        Spacer()
                        Text("cov \(pct(s.coveragePercent))")
                    }
                    .font(.caption).foregroundStyle(.secondary).monospacedDigit()
                }
            }
        }
    }
}

// MARK: - Transfer gaps (recall − application)

struct TransferGapSection: View {
    let gaps: [Anki_Mcat_TransferGap]
    var body: some View {
        Section("Transfer gaps (recall − application)") {
            ForEach(gaps, id: \.topicKey) { g in
                VStack(alignment: .leading, spacing: 2) {
                    Text(g.topicName)
                    HStack {
                        Text("recall \(pct(g.memoryRecall * 100))")
                        Spacer()
                        Text("applied \(pct(g.performanceAccuracy * 100))")
                        Spacer()
                        Text("gap \(pct(g.gap * 100))")
                            .foregroundStyle(g.gap > 0.15 ? Color.red : Color.secondary)
                            .fontWeight(g.gap > 0.15 ? .semibold : .regular)
                    }
                    .font(.caption).foregroundStyle(.secondary).monospacedDigit()
                }
            }
        }
    }
}

// MARK: - Interleaved session builder (the study feature under test)

struct InterleaveSection: View {
    @ObservedObject var store: CollectionStore
    @State private var interleave = true

    var body: some View {
        Section("Timed interleaved session") {
            Toggle("Interleave topics (off = blocked practice)", isOn: $interleave)
                .font(.subheadline)
            Button {
                Task { await store.buildSession(interleave: interleave) }
            } label: {
                if store.buildingSession {
                    ProgressView()
                } else {
                    Text("Build session")
                }
            }
            .disabled(store.buildingSession)

            if let session = store.session {
                Text("\(session.cardIds.count) cards • "
                    + (session.interleaved ? "interleaved" : "blocked"))
                    .font(.caption).foregroundStyle(.secondary)
                if !session.log.isEmpty {
                    Text(session.log)
                        .font(.caption2).foregroundStyle(.secondary)
                }
            }
        }
    }
}

// MARK: - Generic deck browser entry

struct DeckBrowseSection: View {
    @ObservedObject var store: CollectionStore
    var body: some View {
        Section("All decks") {
            NavigationLink {
                DeckListView(collection: store)
            } label: {
                Label {
                    VStack(alignment: .leading, spacing: 2) {
                        Text("Browse & review decks")
                        Text("Review any synced deck. Answers count and sync.")
                            .font(.caption).foregroundStyle(.secondary)
                    }
                } icon: {
                    Image(systemName: "rectangle.stack")
                }
            }
        }
    }
}

// MARK: - Native timed exam entry

struct ExamEntrySection: View {
    @ObservedObject var store: CollectionStore
    var body: some View {
        Section("Exam mode") {
            NavigationLink {
                ExamView(collection: store)
            } label: {
                Label {
                    VStack(alignment: .leading, spacing: 2) {
                        Text("Start timed exam")
                        Text("Auto-graded MCQ / CARS from MCAT::Exam. "
                            + "Answers count and sync.")
                            .font(.caption).foregroundStyle(.secondary)
                    }
                } icon: {
                    Image(systemName: "timer")
                }
            }
        }
    }
}

// MARK: - XP / streak

struct XpSection: View {
    let xp: Anki_Mcat_XpSummary
    var body: some View {
        Section("Progress") {
            HStack {
                Text("Level \(xp.level)")
                Spacer()
                Text("\(xp.totalXp) XP").foregroundStyle(.secondary)
            }
            HStack {
                Text("\(xp.streakDays)-day streak")
                Spacer()
                Text("+\(xp.xpToday) today").foregroundStyle(.secondary)
            }
            .font(.caption)
            if !xp.badges.isEmpty {
                Text(xp.badges.joined(separator: " · "))
                    .font(.caption2).foregroundStyle(.secondary)
            }
        }
    }
}

// MARK: - Sync UI

struct SyncButton: View {
    @ObservedObject var store: CollectionStore
    @Binding var showingLogin: Bool

    var body: some View {
        if store.syncing {
            ProgressView()
        } else if store.loggedIn {
            Button {
                Task { await store.sync() }
            } label: {
                Image(systemName: "arrow.triangle.2.circlepath")
            }
        } else {
            Button("Sign in") { showingLogin = true }
        }
    }
}

struct LoginView: View {
    @ObservedObject var store: CollectionStore
    @Environment(\.dismiss) private var dismiss
    @State private var username = ""
    @State private var password = ""
    @State private var endpoint = ""

    var body: some View {
        NavigationStack {
            Form {
                Section("AnkiWeb account") {
                    TextField("Email", text: $username)
                        .textContentType(.username)
                        .keyboardType(.emailAddress)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                    SecureField("Password", text: $password)
                        .textContentType(.password)
                }
                Section("Custom sync server (optional)") {
                    TextField("https://sync.example.com/", text: $endpoint)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                }
                if store.loggedIn {
                    Section {
                        Button("Sign out", role: .destructive) {
                            store.logOut()
                            dismiss()
                        }
                    } footer: {
                        if let label = store.endpointLabel {
                            Text("Signed in via \(label).")
                        }
                    }
                }
                Section {
                    Text("Sign in with the same AnkiWeb account used on the "
                        + "desktop. Both apps sync to AnkiWeb, which keeps your "
                        + "collection identical across devices.")
                        .font(.caption).foregroundStyle(.secondary)
                }
            }
            .navigationTitle("Sync")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Sign in") {
                        let ep = endpoint.trimmingCharacters(in: .whitespaces)
                        Task {
                            await store.logIn(
                                username: username,
                                password: password,
                                endpoint: ep.isEmpty ? nil : ep
                            )
                            dismiss()
                        }
                    }
                    .disabled(username.isEmpty || password.isEmpty || store.syncing)
                }
            }
        }
    }
}

// MARK: - Formatting helpers

func pct(_ n: Double) -> String { "\(Int(n.rounded()))%" }
func one(_ n: Double) -> String { String(format: "%.1f", n) }

#Preview {
    ContentView()
}
