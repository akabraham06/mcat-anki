// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import SwiftUI

struct ContentView: View {
    @StateObject private var store = CollectionStore()
    @Environment(\.scenePhase) private var scenePhase
    @State private var showingLogin = false

    var body: some View {
        NavigationStack {
            ZStack {
                Theme.ink.ignoresSafeArea()
                Group {
                    if store.loading {
                        loadingState
                    } else if let readiness = store.readiness {
                        ReadinessView(readiness: readiness, store: store)
                    } else if let message = store.errorMessage {
                        errorState(message)
                    } else {
                        Text("No data").font(.mcatBody(16)).foregroundStyle(Theme.muted)
                    }
                }
            }
            .navigationTitle("Readiness")
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    SyncButton(store: store, showingLogin: $showingLogin)
                }
            }
            .safeAreaInset(edge: .bottom) {
                if let message = store.syncMessage {
                    Text(message)
                        .font(.mcatMono(12, relativeTo: .caption))
                        .foregroundStyle(Theme.muted)
                        .frame(maxWidth: .infinity)
                        .padding(8)
                        .background(Theme.panel)
                        .overlay(Rectangle().fill(Theme.hairline).frame(height: 1), alignment: .top)
                }
            }
            .toolbarBackground(Theme.panel, for: .navigationBar)
            .toolbarBackground(.visible, for: .navigationBar)
        }
        .tint(Theme.chemphys)
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

    private var loadingState: some View {
        VStack(spacing: 14) {
            ProgressView().tint(Theme.chemphys)
            Text("Warming up the engine")
                .font(.mcatMono(13, relativeTo: .caption)).foregroundStyle(Theme.muted)
        }
    }

    private func errorState(_ message: String) -> some View {
        VStack(spacing: 12) {
            Image(systemName: "exclamationmark.triangle")
                .font(.title).foregroundStyle(Theme.warn)
            Text("Couldn't load readiness").font(.mcatBody(17, relativeTo: .headline, semibold: true))
                .foregroundStyle(Theme.text)
            Text(message)
                .font(.mcatMono(12, relativeTo: .caption)).foregroundStyle(Theme.muted)
                .multilineTextAlignment(.center)
        }
        .padding(24)
    }
}

// MARK: - Readiness instrument panel (viewport-fit primary content)

/// The cockpit. The primary content — the readiness gauge, the two supporting
/// scores, a "study next" cue and the actions — is sized to sit in one viewport
/// without scrolling. The dense rubric lives behind "Full breakdown".
struct ReadinessView: View {
    let readiness: Anki_Mcat_ExamReadiness
    @ObservedObject var store: CollectionStore

    /// Semantic accent for the headline gauge: green once the readiness gate
    /// (enough graded reviews + coverage) is met, amber while still below it.
    private var readinessMet: Bool {
        readiness.hasReadinessDetail
            && readiness.readinessDetail.gradedReviewsMet
            && readiness.readinessDetail.coverageMet
    }
    private var heroAccent: Color { readinessMet ? Theme.ready : Theme.warn }

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HeroGauge(score: readiness.readiness, accent: heroAccent)

            if readiness.hasRecommendation, readiness.recommendation.available {
                StudyNextCue(recommendation: readiness.recommendation)
            }

            HStack(spacing: 12) {
                MiniScore(score: readiness.memory)
                MiniScore(score: readiness.performance)
            }

            CoverageStrip(readiness: readiness)

            Spacer(minLength: 0)

            actions
        }
        .padding(16)
    }

    private var actions: some View {
        VStack(spacing: 10) {
            NavigationLink {
                ExamView(collection: store)
            } label: {
                Label("Start timed exam", systemImage: "timer")
            }
            .buttonStyle(InstrumentButtonStyle(tint: Theme.chemphys))

            HStack(spacing: 10) {
                NavigationLink {
                    DeckListView(collection: store)
                } label: {
                    Label("Browse decks", systemImage: "rectangle.stack")
                }
                .buttonStyle(InstrumentButtonStyle(tint: Theme.biobiochem, prominent: false))

                NavigationLink {
                    BreakdownView(readiness: readiness, store: store)
                } label: {
                    Label("Full breakdown", systemImage: "chart.bar.doc.horizontal")
                }
                .buttonStyle(InstrumentButtonStyle(tint: Theme.cars, prominent: false))
            }
        }
    }
}

/// The headline readiness gauge: the one big Space Grotesk number, its
/// confidence interval, and the signature range needle.
private struct HeroGauge: View {
    let score: Anki_Mcat_ScoreEstimate
    let accent: Color

    var body: some View {
        InstrumentCard(accent: accent, padding: 16) {
            VStack(alignment: .leading, spacing: 10) {
                HStack {
                    Eyebrow("Exam readiness", accent: accent)
                    Spacer()
                    if score.available { ConfidenceBadge(confidence: score.confidence) }
                }
                if score.available {
                    HStack(alignment: .firstTextBaseline, spacing: 10) {
                        Text("\(Int(score.point.rounded()))")
                            .font(.mcatDisplay(60, relativeTo: .largeTitle, bold: true))
                            .foregroundStyle(Theme.text)
                            .monospacedDigit()
                            .minimumScaleFactor(0.6)
                            .lineLimit(1)
                        Text("\(Int(score.low.rounded()))–\(Int(score.high.rounded()))")
                            .font(.mcatMono(15, relativeTo: .callout))
                            .foregroundStyle(Theme.muted)
                        Spacer()
                    }
                    GaugeBar(
                        point: score.point, low: score.low, high: score.high,
                        scaleMin: score.scaleMin, scaleMax: score.scaleMax,
                        tint: accent, height: 12
                    )
                    HStack {
                        Text("\(Int(score.scaleMin.rounded()))")
                        Spacer()
                        Text("\(Int(score.scaleMax.rounded()))")
                    }
                    .font(.mcatMono(11, relativeTo: .caption2))
                    .foregroundStyle(Theme.muted)
                    if let reason = score.reasons.first {
                        Text(reason)
                            .font(.mcatBody(13, relativeTo: .footnote))
                            .foregroundStyle(Theme.muted)
                            .lineLimit(2)
                    }
                } else {
                    Text("No score yet")
                        .font(.mcatDisplay(30, relativeTo: .title))
                        .foregroundStyle(Theme.muted)
                    Text(score.abstainReason)
                        .font(.mcatBody(13, relativeTo: .footnote))
                        .foregroundStyle(Theme.muted)
                        .lineLimit(3)
                }
            }
        }
    }
}

/// One of the two supporting scores (Memory, Performance) as a compact gauge.
private struct MiniScore: View {
    let score: Anki_Mcat_ScoreEstimate

    var body: some View {
        InstrumentCard(padding: 12) {
            VStack(alignment: .leading, spacing: 6) {
                Eyebrow(score.label)
                if score.available {
                    Text("\(Int(score.point.rounded()))")
                        .font(.mcatDisplay(30, relativeTo: .title, bold: true))
                        .foregroundStyle(Theme.text)
                        .monospacedDigit()
                        .minimumScaleFactor(0.6)
                        .lineLimit(1)
                    Text("\(Int(score.low.rounded()))–\(Int(score.high.rounded()))")
                        .font(.mcatMono(11, relativeTo: .caption2))
                        .foregroundStyle(Theme.muted)
                    GaugeBar(
                        point: score.point, low: score.low, high: score.high,
                        scaleMin: score.scaleMin, scaleMax: score.scaleMax,
                        tint: Theme.needle, height: 6
                    )
                    Text("cov \(pct(score.coveragePercent))")
                        .font(.mcatMono(11, relativeTo: .caption2))
                        .foregroundStyle(Theme.muted)
                } else {
                    Text("—")
                        .font(.mcatDisplay(30, relativeTo: .title, bold: true))
                        .foregroundStyle(Theme.muted)
                    Text("no score yet")
                        .font(.mcatMono(11, relativeTo: .caption2))
                        .foregroundStyle(Theme.muted)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }
}

/// A one-line coverage readout under the scores.
private struct CoverageStrip: View {
    let readiness: Anki_Mcat_ExamReadiness

    var body: some View {
        HStack(spacing: 6) {
            Image(systemName: "chart.pie")
                .font(.system(size: 12))
                .foregroundStyle(Theme.muted)
            Text("Coverage \(pct(readiness.overallCoveragePercent))")
            Text("•").foregroundStyle(Theme.hairline)
            Text("\(readiness.gradedReviews) graded reviews")
            Spacer()
        }
        .font(.mcatMono(12, relativeTo: .caption))
        .foregroundStyle(Theme.muted)
    }
}

/// A compact "study next" cue: the recommended topic, colour-coded by section.
private struct StudyNextCue: View {
    let recommendation: Anki_Mcat_StudyRecommendation

    var body: some View {
        let hue = MCATSection.hue(for: recommendation.topicName)
        return HStack(spacing: 10) {
            Circle().fill(hue).frame(width: 8, height: 8)
            VStack(alignment: .leading, spacing: 1) {
                Eyebrow("Study next", accent: hue)
                Text(recommendation.topicName)
                    .font(.mcatBody(15, relativeTo: .subheadline, semibold: true))
                    .foregroundStyle(Theme.text)
                    .lineLimit(1)
            }
            Spacer()
        }
        .padding(.horizontal, 12).padding(.vertical, 10)
        .background(Theme.panel2)
        .overlay(RoundedRectangle(cornerRadius: 10).stroke(Theme.hairline, lineWidth: 1))
        .clipShape(RoundedRectangle(cornerRadius: 10))
    }
}

private struct ConfidenceBadge: View {
    let confidence: String
    var body: some View {
        Text(confidence)
            .font(.mcatMono(10, relativeTo: .caption2, medium: true))
            .tracking(0.5)
            .foregroundStyle(Theme.muted)
            .padding(.horizontal, 8).padding(.vertical, 3)
            .background(Capsule().fill(Theme.panel2))
            .overlay(Capsule().stroke(Theme.hairline, lineWidth: 1))
    }
}

// MARK: - Full breakdown (scrollable secondary content)

/// The deep rubric: per-score evidence, section vitals, transfer gaps, the
/// interleave builder and progress. This is genuinely long, so it scrolls.
struct BreakdownView: View {
    let readiness: Anki_Mcat_ExamReadiness
    @ObservedObject var store: CollectionStore

    private var scores: [Anki_Mcat_ScoreEstimate] {
        [readiness.readiness, readiness.memory, readiness.performance]
    }

    var body: some View {
        ZStack {
            Theme.ink.ignoresSafeArea()
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    if readiness.hasGiveUpRule {
                        Text(readiness.giveUpRule.description_p)
                            .font(.mcatBody(12, relativeTo: .caption))
                            .foregroundStyle(Theme.muted)
                            .italic()
                    }

                    PanelSection("Scores") {
                        VStack(spacing: 12) {
                            ForEach(scores, id: \.label) { score in
                                ScoreCard(score: score, readiness: readiness)
                            }
                        }
                    }

                    if !readiness.sections.isEmpty {
                        PanelSection("Section vitals") {
                            SectionBreakdown(sections: readiness.sections)
                        }
                    }

                    if !readiness.transferGaps.isEmpty {
                        PanelSection("Transfer gaps · recall − application") {
                            TransferGapSection(gaps: readiness.transferGaps)
                        }
                    }

                    if readiness.hasRecommendation, readiness.recommendation.available {
                        PanelSection("Study queue") {
                            RecommendationSection(recommendation: readiness.recommendation)
                        }
                    }

                    PanelSection("Timed interleaved session") {
                        InterleaveSection(store: store)
                    }

                    if readiness.hasXp {
                        PanelSection("Progress") {
                            XpSection(xp: readiness.xp)
                        }
                    }
                }
                .padding(16)
            }
            .refreshable { await store.sync() }
        }
        .navigationTitle("Breakdown")
        .navigationBarTitleDisplayMode(.inline)
        .toolbarBackground(Theme.panel, for: .navigationBar)
        .toolbarBackground(.visible, for: .navigationBar)
    }
}

/// A titled group: an eyebrow header above a panel.
struct PanelSection<Content: View>: View {
    let title: String
    var accent: Color = Theme.muted
    @ViewBuilder var content: Content
    init(_ title: String, accent: Color = Theme.muted, @ViewBuilder content: () -> Content) {
        self.title = title
        self.accent = accent
        self.content = content()
    }
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Eyebrow(title, accent: accent)
            content
        }
    }
}

// MARK: - Score card with honesty metadata + per-score detail

struct ScoreCard: View {
    let score: Anki_Mcat_ScoreEstimate
    let readiness: Anki_Mcat_ExamReadiness

    var body: some View {
        InstrumentCard(padding: 14) {
            VStack(alignment: .leading, spacing: 8) {
                HStack {
                    Text(score.label)
                        .font(.mcatBody(15, relativeTo: .headline, semibold: true))
                        .foregroundStyle(Theme.text)
                    Spacer()
                    if score.available { ConfidenceBadge(confidence: score.confidence) }
                }
                if score.available {
                    HStack(alignment: .firstTextBaseline, spacing: 8) {
                        Text("\(Int(score.point.rounded()))")
                            .font(.mcatDisplay(34, relativeTo: .title, bold: true))
                            .foregroundStyle(Theme.text)
                            .monospacedDigit()
                        Text("\(Int(score.low.rounded()))–\(Int(score.high.rounded()))")
                            .font(.mcatMono(13, relativeTo: .caption))
                            .foregroundStyle(Theme.muted)
                        Spacer()
                    }
                    GaugeBar(
                        point: score.point, low: score.low, high: score.high,
                        scaleMin: score.scaleMin, scaleMax: score.scaleMax,
                        tint: Theme.needle, height: 8
                    )
                    Text("Coverage \(pct(score.coveragePercent))")
                        .font(.mcatMono(11, relativeTo: .caption2))
                        .foregroundStyle(Theme.muted)
                    ForEach(score.reasons, id: \.self) { reason in
                        Text("• \(reason)")
                            .font(.mcatBody(12, relativeTo: .caption))
                            .foregroundStyle(Theme.muted)
                    }
                } else {
                    Text("No score yet")
                        .font(.mcatDisplay(22, relativeTo: .title3))
                        .foregroundStyle(Theme.muted)
                    Text(score.abstainReason)
                        .font(.mcatBody(12, relativeTo: .caption))
                        .foregroundStyle(Theme.muted)
                    Text("Coverage \(pct(score.coveragePercent))")
                        .font(.mcatMono(11, relativeTo: .caption2))
                        .foregroundStyle(Theme.muted)
                }
                detail
            }
        }
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
        VStack(alignment: .leading, spacing: 6) {
            StatGrid(rows: [
                ("Graded reviews",
                 "\(detail.gradedReviews) / \(detail.requiredGradedReviews)",
                 detail.gradedReviewsMet),
                ("Coverage",
                 "\(pct(detail.coveragePercent)) / \(pct(detail.requiredCoveragePercent))",
                 detail.coverageMet),
                ("Speed factor", pct(detail.speedFactor * 100), detail.speedFactor >= 0.999),
                ("Overtime rate", pct(detail.overtimeRate * 100), false),
            ])
            StatGrid(rows: [
                ("Weights (mem / perf / speed)",
                 "\(pct(detail.memoryWeight * 100)) / "
                    + "\(pct(detail.performanceWeight * 100)) / "
                    + "\(pct(detail.speedWeight * 100))"),
            ])
            if !detail.speedReason.isEmpty {
                Text(detail.speedReason)
                    .font(.mcatBody(11, relativeTo: .caption2)).italic()
                    .foregroundStyle(Theme.muted)
            }
        }
    }
}

/// Two-column label/value grid. A "met" row turns green so the readiness gate
/// is transparent.
struct StatGrid: View {
    let rows: [(label: String, value: String, met: Bool)]

    init(rows: [(String, String)]) {
        self.rows = rows.map { ($0.0, $0.1, false) }
    }
    init(rows: [(String, String, Bool)]) {
        self.rows = rows.map { ($0.0, $0.1, $0.2) }
    }

    var body: some View {
        VStack(spacing: 3) {
            ForEach(rows.indices, id: \.self) { i in
                HStack(alignment: .firstTextBaseline) {
                    Text(rows[i].label)
                        .font(.mcatBody(12, relativeTo: .caption))
                        .foregroundStyle(Theme.muted)
                    Spacer()
                    Text(rows[i].value)
                        .font(.mcatMono(12, relativeTo: .caption, medium: rows[i].met))
                        .foregroundStyle(rows[i].met ? Theme.ready : Theme.text)
                }
            }
        }
        .padding(.top, 6)
        .overlay(Rectangle().fill(Theme.hairline).frame(height: 1), alignment: .top)
    }
}

// MARK: - Recommendation

struct RecommendationSection: View {
    let recommendation: Anki_Mcat_StudyRecommendation
    var body: some View {
        InstrumentCard(accent: MCATSection.hue(for: recommendation.topicName), padding: 14) {
            VStack(alignment: .leading, spacing: 6) {
                Text(recommendation.topicName)
                    .font(.mcatBody(15, relativeTo: .headline, semibold: true))
                    .foregroundStyle(Theme.text)
                Text(recommendation.explanation)
                    .font(.mcatBody(12, relativeTo: .caption))
                    .foregroundStyle(Theme.muted)
                ForEach(recommendation.candidates, id: \.topicKey) { c in
                    HStack {
                        Circle().fill(MCATSection.hue(for: c.topicName)).frame(width: 6, height: 6)
                        Text(c.topicName)
                            .font(.mcatBody(13, relativeTo: .subheadline))
                            .foregroundStyle(Theme.text)
                        Spacer()
                        Text("w \(one(c.priorityScore)) • \(c.dueCards) due")
                            .font(.mcatMono(11, relativeTo: .caption2))
                            .foregroundStyle(Theme.muted)
                    }
                }
            }
        }
    }
}

// MARK: - Section breakdown (memory % + reviewed/total)

struct SectionBreakdown: View {
    let sections: [Anki_Mcat_SectionScore]
    var body: some View {
        VStack(spacing: 10) {
            ForEach(sections, id: \.sectionKey) { s in
                let hue = MCATSection.hue(for: s.sectionName + " " + s.sectionKey)
                InstrumentCard(accent: hue, padding: 12) {
                    VStack(alignment: .leading, spacing: 4) {
                        HStack {
                            Text(s.sectionName)
                                .font(.mcatBody(14, relativeTo: .subheadline, semibold: true))
                                .foregroundStyle(Theme.text)
                            Spacer()
                            if s.available {
                                Text("\(Int(s.point.rounded())) "
                                    + "(\(Int(s.low.rounded()))–\(Int(s.high.rounded())))")
                                    .font(.mcatMono(12, relativeTo: .caption))
                                    .foregroundStyle(Theme.text)
                            } else {
                                Text("no data")
                                    .font(.mcatMono(12, relativeTo: .caption))
                                    .foregroundStyle(Theme.muted)
                            }
                        }
                        HStack {
                            Text(s.available ? "mem \(pct(s.memoryPercent))" : "—")
                            Spacer()
                            Text("\(s.cardsReviewed)/\(s.cardsTotal) cards")
                            Spacer()
                            Text("cov \(pct(s.coveragePercent))")
                        }
                        .font(.mcatMono(11, relativeTo: .caption2))
                        .foregroundStyle(Theme.muted)
                    }
                }
            }
        }
    }
}

// MARK: - Transfer gaps (recall − application)

struct TransferGapSection: View {
    let gaps: [Anki_Mcat_TransferGap]
    var body: some View {
        VStack(spacing: 10) {
            ForEach(gaps, id: \.topicKey) { g in
                let wide = g.gap > 0.15
                InstrumentCard(accent: wide ? Theme.warn : MCATSection.hue(for: g.topicName), padding: 12) {
                    VStack(alignment: .leading, spacing: 4) {
                        Text(g.topicName)
                            .font(.mcatBody(14, relativeTo: .subheadline, semibold: true))
                            .foregroundStyle(Theme.text)
                        HStack {
                            Text("recall \(pct(g.memoryRecall * 100))")
                            Spacer()
                            Text("applied \(pct(g.performanceAccuracy * 100))")
                            Spacer()
                            Text("gap \(pct(g.gap * 100))")
                                .foregroundStyle(wide ? Theme.warn : Theme.muted)
                        }
                        .font(.mcatMono(11, relativeTo: .caption2))
                        .foregroundStyle(Theme.muted)
                    }
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
        InstrumentCard(padding: 14) {
            VStack(alignment: .leading, spacing: 10) {
                Toggle(isOn: $interleave) {
                    Text("Interleave topics")
                        .font(.mcatBody(14, relativeTo: .subheadline))
                        .foregroundStyle(Theme.text)
                }
                .tint(Theme.chemphys)
                Text(interleave ? "Mixed practice across topics" : "Blocked practice, one topic at a time")
                    .font(.mcatBody(11, relativeTo: .caption2))
                    .foregroundStyle(Theme.muted)

                Button {
                    Task { await store.buildSession(interleave: interleave) }
                } label: {
                    if store.buildingSession {
                        ProgressView().tint(.white)
                    } else {
                        Text("Build session")
                    }
                }
                .buttonStyle(InstrumentButtonStyle(tint: Theme.chemphys))
                .disabled(store.buildingSession)

                if let session = store.session {
                    Text("\(session.cardIds.count) cards • "
                        + (session.interleaved ? "interleaved" : "blocked"))
                        .font(.mcatMono(12, relativeTo: .caption))
                        .foregroundStyle(Theme.muted)
                    if !session.log.isEmpty {
                        Text(session.log)
                            .font(.mcatMono(10, relativeTo: .caption2))
                            .foregroundStyle(Theme.muted)
                    }
                }
            }
        }
    }
}

// MARK: - XP / streak

struct XpSection: View {
    let xp: Anki_Mcat_XpSummary
    var body: some View {
        InstrumentCard(accent: Theme.ready, padding: 14) {
            VStack(alignment: .leading, spacing: 6) {
                HStack {
                    Text("Level \(xp.level)")
                        .font(.mcatBody(15, relativeTo: .headline, semibold: true))
                        .foregroundStyle(Theme.text)
                    Spacer()
                    Text("\(xp.totalXp) XP")
                        .font(.mcatMono(13, relativeTo: .caption))
                        .foregroundStyle(Theme.muted)
                }
                HStack {
                    Text("\(xp.streakDays)-day streak")
                    Spacer()
                    Text("+\(xp.xpToday) today")
                }
                .font(.mcatMono(12, relativeTo: .caption))
                .foregroundStyle(Theme.muted)
                if !xp.badges.isEmpty {
                    Text(xp.badges.joined(separator: " · "))
                        .font(.mcatBody(11, relativeTo: .caption2))
                        .foregroundStyle(Theme.muted)
                }
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
            ProgressView().tint(Theme.chemphys)
        } else if store.loggedIn {
            Button {
                Task { await store.sync() }
            } label: {
                Image(systemName: "arrow.triangle.2.circlepath")
            }
        } else {
            Button("Sign in") { showingLogin = true }
                .font(.mcatBody(15, relativeTo: .body, semibold: true))
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
                        .font(.mcatBody(12, relativeTo: .caption))
                        .foregroundStyle(Theme.muted)
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
        .tint(Theme.chemphys)
    }
}

// MARK: - Formatting helpers

func pct(_ n: Double) -> String { "\(Int(n.rounded()))%" }
func one(_ n: Double) -> String { String(format: "%.1f", n) }

#Preview {
    ContentView()
}
