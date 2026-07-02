// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import Foundation
import SwiftProtobuf

/// Opens the shared engine and a collection, then exposes MCAT readiness to the
/// SwiftUI views. On the desktop the collection is opened by aqt; here we open
/// a collection file kept at a stable app path, which the AnkiWeb sync then
/// keeps in step with the desktop.
@MainActor
final class CollectionStore: ObservableObject {
    @Published var readiness: Anki_Mcat_ExamReadiness?
    @Published var errorMessage: String?
    @Published var loading = false

    // Sync state.
    @Published var syncing = false
    @Published var syncMessage: String?
    @Published var loggedIn = false
    /// Human-readable AnkiWeb account label (endpoint host), for the UI.
    @Published var endpointLabel: String?

    // Interleaved-session builder (the study feature under test).
    @Published var session: Anki_Mcat_InterleavedSession?
    @Published var buildingSession = false

    private var backend: AnkiBackend?
    private var auth: Anki_Sync_SyncAuth?

    /// The shared engine handle, so a study session drives the *same* open
    /// collection (opening the file twice would risk conflicting handles).
    var engine: AnkiBackend? { backend }

    /// Whether a sync is possible (used to decide whether to push study writes).
    var canSync: Bool { loggedIn }

    /// Path to the collection the companion reads. A stable location under the
    /// app's Documents directory so it survives launches and is the single file
    /// the AnkiWeb sync reads and writes.
    var collectionPath: URL {
        let docs = FileManager.default.urls(
            for: .documentDirectory, in: .userDomainMask
        )[0]
        return docs.appendingPathComponent("collection.anki2")
    }

    private var mediaFolderPath: URL {
        collectionPath.deletingLastPathComponent()
            .appendingPathComponent("collection.media")
    }

    private var mediaDBPath: URL {
        collectionPath.deletingLastPathComponent()
            .appendingPathComponent("collection.media.db2")
    }

    // MARK: - Lifecycle

    func start() async {
        loading = true
        defer { loading = false }
        do {
            let backend = try AnkiBackend(initMessage: makeInitMessage())
            self.backend = backend
            try openCollection(backend)
            restoreAuth()
            self.readiness = try backend.examReadiness()
        } catch {
            self.errorMessage = "\(error)"
        }
        // If we already have credentials, sync on launch to pull desktop changes.
        if loggedIn {
            await sync()
        }
    }

    /// Refresh the readiness snapshot from the (possibly just-synced) collection.
    func refresh() async {
        guard let backend else { return }
        do {
            self.readiness = try await background { try backend.examReadiness() }
        } catch {
            self.errorMessage = "\(error)"
        }
    }

    /// Build an ordered study session, interleaved across topics or blocked by
    /// topic (the ablation toggle). Mirrors the desktop dashboard's builder.
    func buildSession(interleave: Bool) async {
        guard let backend else { return }
        buildingSession = true
        defer { buildingSession = false }
        do {
            self.session = try await background {
                try backend.interleavedSession(interleave: interleave)
            }
        } catch {
            self.errorMessage = "\(error)"
        }
    }

    // MARK: - Sync

    func logIn(username: String, password: String, endpoint: String?) async {
        guard let backend else { return }
        syncing = true
        syncMessage = "Signing in…"
        defer { syncing = false }
        do {
            let auth = try await background {
                try backend.syncLogin(
                    username: username, password: password, endpoint: endpoint
                )
            }
            storeAuth(auth)
            syncMessage = "Signed in."
            await sync()
        } catch {
            syncMessage = "Sign-in failed: \(error.localizedDescription)"
            self.errorMessage = "\(error)"
        }
    }

    func logOut() {
        Keychain.clear()
        auth = nil
        loggedIn = false
        endpointLabel = nil
        syncMessage = nil
    }

    /// Run a full sync cycle: a normal (incremental) sync, escalating to a
    /// one-way full upload/download when the server requires it. Mirrors the
    /// desktop's sync_collection → full_sync flow.
    func sync() async {
        guard let backend, let auth else {
            syncMessage = "Sign in to AnkiWeb to sync."
            return
        }
        syncing = true
        syncMessage = "Syncing…"
        defer { syncing = false }
        do {
            let result: Anki_Sync_SyncCollectionResponse = try await background {
                let response = try backend.syncCollection(auth: auth, syncMedia: false)
                switch response.required {
                case .fullDownload:
                    try backend.fullUploadOrDownload(auth: auth, upload: false)
                case .fullUpload:
                    try backend.fullUploadOrDownload(auth: auth, upload: true)
                case .fullSync:
                    // Both sides diverged and the server can't pick a direction.
                    // Default to pulling the desktop's collection, which is the
                    // source of truth for study history.
                    try backend.fullUploadOrDownload(auth: auth, upload: false)
                case .noChanges, .normalSync, .UNRECOGNIZED:
                    break
                }
                return response
            }
            // Persist any endpoint the server redirected us to.
            if result.hasNewEndpoint {
                storeAuth(updatingEndpoint: result.newEndpoint)
            }
            syncMessage = syncSummary(for: result.required)
            await refresh()
        } catch {
            syncMessage = "Sync failed: \(error.localizedDescription)"
            self.errorMessage = "\(error)"
        }
    }

    private func syncSummary(for required: Anki_Sync_SyncCollectionResponse.ChangesRequired) -> String {
        switch required {
        case .noChanges: return "Up to date."
        case .normalSync: return "Synced."
        case .fullDownload: return "Downloaded full collection."
        case .fullUpload: return "Uploaded full collection."
        case .fullSync: return "Downloaded full collection."
        case .UNRECOGNIZED: return "Synced."
        }
    }

    // MARK: - Auth persistence

    private func storeAuth(_ auth: Anki_Sync_SyncAuth) {
        self.auth = auth
        loggedIn = true
        endpointLabel = auth.hasEndpoint ? URL(string: auth.endpoint)?.host ?? auth.endpoint : "AnkiWeb"
        Keychain.save(hkey: auth.hkey, endpoint: auth.hasEndpoint ? auth.endpoint : nil)
    }

    private func storeAuth(updatingEndpoint endpoint: String) {
        guard var auth else { return }
        auth.endpoint = endpoint
        storeAuth(auth)
    }

    private func restoreAuth() {
        guard let hkey = Keychain.loadHkey() else {
            loggedIn = false
            return
        }
        var auth = Anki_Sync_SyncAuth()
        auth.hkey = hkey
        if let endpoint = Keychain.loadEndpoint() { auth.endpoint = endpoint }
        self.auth = auth
        loggedIn = true
        endpointLabel = auth.hasEndpoint ? URL(string: auth.endpoint)?.host ?? auth.endpoint : "AnkiWeb"
    }

    // MARK: - Engine plumbing

    /// Build an anki.backend.BackendInit message. Language + folder are enough
    /// to boot the engine; see proto/anki/backend.proto.
    private func makeInitMessage() -> Data {
        var init_ = Anki_Backend_BackendInit()
        init_.preferredLangs = ["en"]
        init_.localeFolderPath = ""
        init_.server = false
        return (try? init_.serializedData()) ?? Data()
    }

    /// Open the collection via CollectionService.OpenCollection, supplying media
    /// paths so a future media sync has a home.
    private func openCollection(_ backend: AnkiBackend) throws {
        try? FileManager.default.createDirectory(
            at: mediaFolderPath, withIntermediateDirectories: true
        )
        var request = Anki_Collection_OpenCollectionRequest()
        request.collectionPath = collectionPath.path
        request.mediaFolderPath = mediaFolderPath.path
        request.mediaDbPath = mediaDBPath.path
        // OpenCollection is method 0 of CollectionService.
        _ = try backend.run(
            service: AnkiBackend.Service.collection.rawValue,
            method: 0,
            input: try request.serializedData()
        )
    }

    /// Run blocking engine work off the main thread and await the result. The
    /// engine performs network/DB I/O synchronously, so this keeps the UI live.
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
