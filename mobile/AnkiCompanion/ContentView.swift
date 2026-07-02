// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import SwiftUI

struct ContentView: View {
    @StateObject private var store = CollectionStore()

    var body: some View {
        NavigationStack {
            Group {
                if store.loading {
                    ProgressView("Loading engine…")
                } else if let message = store.errorMessage {
                    VStack(spacing: 12) {
                        Text("Couldn't load readiness").font(.headline)
                        Text(message)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                            .multilineTextAlignment(.center)
                    }
                    .padding()
                } else if let readiness = store.readiness {
                    ReadinessView(readiness: readiness)
                } else {
                    Text("No data")
                }
            }
            .navigationTitle("MCAT Readiness")
        }
        .task { await store.start() }
    }
}

struct ReadinessView: View {
    let readiness: Anki_Mcat_ExamReadiness

    private var scores: [Anki_Mcat_ScoreEstimate] {
        [readiness.readiness, readiness.memory, readiness.performance]
    }

    var body: some View {
        List {
            Section("Scores") {
                ForEach(scores, id: \.label) { score in
                    ScoreRow(score: score)
                }
            }
            if readiness.hasRecommendation, readiness.recommendation.available {
                Section("Study next") {
                    Text(readiness.recommendation.topicName).font(.headline)
                    Text(readiness.recommendation.explanation)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
            if readiness.hasXp {
                Section("Progress") {
                    Text("Level \(readiness.xp.level) • \(readiness.xp.totalXp) XP")
                    Text("\(readiness.xp.streakDays)-day streak")
                        .foregroundStyle(.secondary)
                }
            }
        }
    }
}

struct ScoreRow: View {
    let score: Anki_Mcat_ScoreEstimate

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(score.label).font(.headline)
            if score.available {
                Text("\(Int(score.point.rounded())) "
                    + "(\(Int(score.low.rounded()))–\(Int(score.high.rounded())))")
                    .font(.title3).bold()
                Text("Coverage \(Int(score.coveragePercent.rounded()))% • "
                    + "\(score.confidence) confidence")
                    .font(.caption).foregroundStyle(.secondary)
            } else {
                Text("No score yet").foregroundStyle(.secondary)
                Text(score.abstainReason)
                    .font(.caption).foregroundStyle(.secondary)
            }
        }
        .padding(.vertical, 2)
    }
}

#Preview {
    ContentView()
}
