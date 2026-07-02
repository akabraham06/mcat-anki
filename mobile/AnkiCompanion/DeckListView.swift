// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import SwiftUI

/// Loads the collection's deck tree (with today's new/learning/review counts)
/// so the user can browse and review ANY synced deck, not just MCAT::Exam. This
/// drives the exact same DecksService the desktop deck list uses, so the counts
/// match the desktop for a synced collection.
@MainActor
final class DeckListStore: ObservableObject {
    /// One flattened deck row, ready to render as an indented list entry.
    struct Row: Identifiable {
        let id: Int64
        let name: String
        let level: Int
        let newCount: UInt32
        let learnCount: UInt32
        let reviewCount: UInt32

        var hasDue: Bool { newCount + learnCount + reviewCount > 0 }
    }

    @Published var rows: [Row] = []
    @Published var loading = false
    @Published var errorMessage: String?

    private let collection: CollectionStore
    private var backend: AnkiBackend? { collection.engine }

    init(collection: CollectionStore) {
        self.collection = collection
    }

    /// Fetch and flatten the deck tree. The synthetic root (deck id 0) is
    /// skipped; its children are the top-level decks.
    func load() async {
        guard let backend else {
            errorMessage = "Engine not ready."
            return
        }
        loading = true
        defer { loading = false }
        do {
            let tree = try await background { try backend.deckTree() }
            var flattened: [Row] = []
            flatten(node: tree, into: &flattened)
            rows = flattened
        } catch {
            errorMessage = "\(error)"
        }
    }

    private func flatten(node: Anki_Decks_DeckTreeNode, into rows: inout [Row]) {
        // The root node (level 0, deck id 0) is a container, not a real deck.
        if node.deckID != 0 {
            rows.append(Row(
                id: node.deckID,
                name: node.name,
                level: Int(node.level),
                newCount: node.newCount,
                learnCount: node.learnCount,
                reviewCount: node.reviewCount
            ))
        }
        for child in node.children {
            flatten(node: child, into: &rows)
        }
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

/// Browsable list of every deck in the collection. Tapping a deck opens the
/// generic reviewer scoped to that deck's due cards.
struct DeckListView: View {
    @ObservedObject var collection: CollectionStore
    @StateObject private var store: DeckListStore

    init(collection: CollectionStore) {
        self.collection = collection
        _store = StateObject(wrappedValue: DeckListStore(collection: collection))
    }

    var body: some View {
        Group {
            if store.loading {
                ProgressView("Loading decks…")
            } else if let message = store.errorMessage {
                errorState(message)
            } else if store.rows.isEmpty {
                emptyState
            } else {
                List(store.rows) { row in
                    NavigationLink {
                        ReviewView(collection: collection,
                                   deckId: row.id,
                                   deckName: row.name)
                    } label: {
                        DeckRowView(row: row)
                    }
                }
                .refreshable {
                    await collection.sync()
                    await store.load()
                }
            }
        }
        .navigationTitle("Decks")
        .navigationBarTitleDisplayMode(.inline)
        .task { await store.load() }
    }

    private var emptyState: some View {
        VStack(spacing: 12) {
            Image(systemName: "tray")
                .font(.largeTitle).foregroundStyle(.secondary)
            Text("No decks yet").font(.headline)
            Text("Sign in and sync with AnkiWeb to pull your decks.")
                .font(.caption).foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
        }
        .padding()
    }

    private func errorState(_ message: String) -> some View {
        VStack(spacing: 12) {
            Image(systemName: "exclamationmark.triangle")
                .font(.largeTitle).foregroundStyle(.secondary)
            Text("Couldn't load decks").font(.headline)
            Text(message)
                .font(.caption).foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
        }
        .padding()
    }
}

/// One deck row: indented name plus the three colour-coded due counts.
private struct DeckRowView: View {
    let row: DeckListStore.Row

    var body: some View {
        HStack {
            Text(row.name)
                .padding(.leading, CGFloat(row.level) * 14)
                .lineLimit(1)
            Spacer()
            HStack(spacing: 10) {
                count(row.newCount, .blue)
                count(row.learnCount, .red)
                count(row.reviewCount, .green)
            }
            .font(.caption).monospacedDigit()
        }
    }

    private func count(_ n: UInt32, _ color: Color) -> some View {
        Text("\(n)")
            .foregroundStyle(n > 0 ? color : Color.secondary.opacity(0.5))
    }
}
