// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import Foundation
// Provided by the AnkiEngine.xcframework (module map exposes ankiffi.h).
import AnkiEngine
import SwiftProtobuf

/// Thin Swift wrapper over the Anki engine's C FFI. This is the mobile analogue
/// of pylib's rsbridge: it drives the exact same Rust engine the desktop uses,
/// so the companion shows identical scores for a synced collection.
final class AnkiBackend {
    enum BackendError: LocalizedError {
        case open(String)
        case command(String)

        var errorDescription: String? {
            switch self {
            case let .open(message): return message
            case let .command(message): return message
            }
        }
    }

    /// Backend service indices, taken from the generated backend
    /// (`out/pylib/anki/_backend_generated.py`). Re-run
    /// `patch_service_indices.sh` after regenerating the backend to keep these
    /// in sync. Method indices below are the declaration order within the proto.
    enum Service: UInt32 {
        case sync = 1
        case collection = 3
        case cards = 5
        case decks = 7
        case scheduler = 13
        case notes = 25
        case cardRendering = 27
        case mcat = 41
    }

    enum McatMethod: UInt32 {
        case getTopicMastery = 0
        case getExamReadiness = 1
        case getStudyRecommendation = 2
        case buildInterleavedSession = 3
        case getTopicTargets = 4
    }

    // NOTE: method indices below are the BACKEND service method indices (the
    // same (service, method) pairs `_backend_generated.py` dispatches through
    // `_run_command`), which is exactly what `anki_backend_command` uses. For
    // SchedulerService these do NOT match the frontend proto declaration order,
    // because BackendSchedulerService injects extra methods — always read the
    // real indices from out/pylib/anki/_backend_generated.py.

    /// Method indices within SchedulerService (backend dispatch order).
    enum SchedulerMethod: UInt32 {
        case getQueuedCards = 3
        case answerCard = 4
        case countsForDeckToday = 10
        case getSchedulingStates = 23
    }

    /// Method indices within NotesService (backend dispatch order).
    enum NotesMethod: UInt32 {
        case getNote = 6
    }

    /// Method indices within CardsService (backend dispatch order).
    enum CardsMethod: UInt32 {
        case getCard = 0
    }

    /// Method indices within DecksService (backend dispatch order).
    enum DecksMethod: UInt32 {
        case getDeckIdByName = 7
        case setCurrentDeck = 22
    }

    /// Method indices within BackendSyncService (proto declaration order).
    enum SyncMethod: UInt32 {
        case syncMedia = 0
        case abortMediaSync = 1
        case mediaSyncStatus = 2
        case syncLogin = 3
        case syncStatus = 4
        case syncCollection = 5
        case fullUploadOrDownload = 6
        case abortSync = 7
        case setCustomCertificate = 8
    }

    private let handle: OpaquePointer

    init(initMessage: Data) throws {
        var errPtr: UnsafeMutablePointer<CChar>? = nil
        let handle = initMessage.withUnsafeBytes { raw -> OpaquePointer? in
            anki_backend_open(
                raw.bindMemory(to: UInt8.self).baseAddress,
                initMessage.count,
                &errPtr
            )
        }
        guard let handle else {
            let message = errPtr.map { String(cString: $0) } ?? "unknown error"
            if let errPtr { anki_free_string(errPtr) }
            throw BackendError.open(message)
        }
        self.handle = handle
    }

    deinit {
        anki_backend_close(handle)
    }

    /// Run a raw service method, returning the protobuf-encoded response.
    func run(service: UInt32, method: UInt32, input: Data) throws -> Data {
        let buffer = input.withUnsafeBytes { raw in
            anki_backend_command(
                handle,
                service,
                method,
                raw.bindMemory(to: UInt8.self).baseAddress,
                input.count
            )
        }
        defer { anki_free_buffer(buffer) }
        let bytes: Data
        if let data = buffer.data, buffer.len > 0 {
            bytes = Data(bytes: data, count: buffer.len)
        } else {
            bytes = Data()
        }
        if buffer.is_error {
            // The engine encodes failures as an anki.backend.BackendError whose
            // `message` is a localized, user-facing string.
            let message = (try? Anki_Backend_BackendError(serializedBytes: bytes))?.message
            throw BackendError.command(message ?? "backend error (\(bytes.count) bytes)")
        }
        return bytes
    }

    /// Typed convenience wrappers using the generated SwiftProtobuf messages.
    func examReadiness() throws -> Anki_Mcat_ExamReadiness {
        let request = Anki_Mcat_ExamReadinessRequest()
        let out = try run(
            service: Service.mcat.rawValue,
            method: McatMethod.getExamReadiness.rawValue,
            input: try request.serializedData()
        )
        return try Anki_Mcat_ExamReadiness(serializedBytes: out)
    }

    func interleavedSession(interleave: Bool, maxCards: UInt32 = 20)
        throws -> Anki_Mcat_InterleavedSession
    {
        var request = Anki_Mcat_InterleavedSessionRequest()
        request.interleave = interleave
        request.maxCards = maxCards
        let out = try run(
            service: Service.mcat.rawValue,
            method: McatMethod.buildInterleavedSession.rawValue,
            input: try request.serializedData()
        )
        return try Anki_Mcat_InterleavedSession(serializedBytes: out)
    }

    /// Per-topic target answer times (CARS 90s / sciences 35–50s) used to size
    /// the per-question countdown. Mirrors the desktop reviewer's
    /// `mcat_topic_targets()`.
    func topicTargets() throws -> Anki_Mcat_TopicTargetList {
        let request = Anki_Mcat_ExamReadinessRequest()
        let out = try run(
            service: Service.mcat.rawValue,
            method: McatMethod.getTopicTargets.rawValue,
            input: try request.serializedData()
        )
        return try Anki_Mcat_TopicTargetList(serializedBytes: out)
    }

    // MARK: - Study / exam loop (scheduler + notes + decks)
    //
    // These drive the same SchedulerService the desktop reviewer uses, over the
    // generic FFI, so reviews written here are real: they update FSRS memory
    // state, the review log, and (once synced) show up identically on desktop.

    /// Resolve a deck id by exact name (e.g. "MCAT::Exam"). Returns 0 if the
    /// deck doesn't exist yet.
    func deckId(named name: String) throws -> Int64 {
        var request = Anki_Generic_String()
        request.val = name
        let out = try run(
            service: Service.decks.rawValue,
            method: DecksMethod.getDeckIdByName.rawValue,
            input: try request.serializedData()
        )
        return try Anki_Decks_DeckId(serializedBytes: out).did
    }

    /// Select the deck the scheduler should draw its queue from. GetQueuedCards
    /// always works against the current deck, so exam study scopes to
    /// MCAT::Exam by setting it current first.
    func setCurrentDeck(id: Int64) throws {
        var request = Anki_Decks_DeckId()
        request.did = id
        _ = try run(
            service: Service.decks.rawValue,
            method: DecksMethod.setCurrentDeck.rawValue,
            input: try request.serializedData()
        )
    }

    /// Fetch the next batch of due cards for the current deck. Each QueuedCard
    /// carries the Card plus its precomputed SchedulingStates.
    func queuedCards(fetchLimit: UInt32 = 1) throws -> Anki_Scheduler_QueuedCards {
        var request = Anki_Scheduler_GetQueuedCardsRequest()
        request.fetchLimit = fetchLimit
        let out = try run(
            service: Service.scheduler.rawValue,
            method: SchedulerMethod.getQueuedCards.rawValue,
            input: try request.serializedData()
        )
        return try Anki_Scheduler_QueuedCards(serializedBytes: out)
    }

    /// The four next-state options for a card (again/hard/good/easy + current),
    /// needed to populate `new_state` when answering.
    func schedulingStates(cardId: Int64) throws -> Anki_Scheduler_SchedulingStates {
        var request = Anki_Cards_CardId()
        request.cid = cardId
        let out = try run(
            service: Service.scheduler.rawValue,
            method: SchedulerMethod.getSchedulingStates.rawValue,
            input: try request.serializedData()
        )
        return try Anki_Scheduler_SchedulingStates(serializedBytes: out)
    }

    /// Record an answer. Writes a review to the collection (FSRS + revlog).
    func answerCard(_ answer: Anki_Scheduler_CardAnswer) throws {
        _ = try run(
            service: Service.scheduler.rawValue,
            method: SchedulerMethod.answerCard.rawValue,
            input: try answer.serializedData()
        )
    }

    /// Fetch a note's fields + tags, used to render the MCQ/CARS card natively.
    func note(id: Int64) throws -> Anki_Notes_Note {
        var request = Anki_Notes_NoteId()
        request.nid = id
        let out = try run(
            service: Service.notes.rawValue,
            method: NotesMethod.getNote.rawValue,
            input: try request.serializedData()
        )
        return try Anki_Notes_Note(serializedBytes: out)
    }

    // MARK: - Sync (AnkiWeb)
    //
    // These drive the exact SyncService the desktop uses, over the generic FFI.
    // The engine performs the network I/O synchronously on its own runtime, so
    // callers must invoke them off the main thread (see CollectionStore).

    /// Exchange AnkiWeb credentials for a sync key (hkey) + resolved endpoint.
    func syncLogin(username: String, password: String, endpoint: String?)
        throws -> Anki_Sync_SyncAuth
    {
        var request = Anki_Sync_SyncLoginRequest()
        request.username = username
        request.password = password
        if let endpoint, !endpoint.isEmpty { request.endpoint = endpoint }
        let out = try run(
            service: Service.sync.rawValue,
            method: SyncMethod.syncLogin.rawValue,
            input: try request.serializedData()
        )
        return try Anki_Sync_SyncAuth(serializedBytes: out)
    }

    /// Lightweight check of whether the server has changes to offer.
    func syncStatus(auth: Anki_Sync_SyncAuth) throws -> Anki_Sync_SyncStatusResponse {
        let out = try run(
            service: Service.sync.rawValue,
            method: SyncMethod.syncStatus.rawValue,
            input: try auth.serializedData()
        )
        return try Anki_Sync_SyncStatusResponse(serializedBytes: out)
    }

    /// Perform a normal (incremental) sync of the open collection. The response
    /// tells us whether a one-way full upload/download is required instead.
    func syncCollection(auth: Anki_Sync_SyncAuth, syncMedia: Bool)
        throws -> Anki_Sync_SyncCollectionResponse
    {
        var request = Anki_Sync_SyncCollectionRequest()
        request.auth = auth
        request.syncMedia = syncMedia
        let out = try run(
            service: Service.sync.rawValue,
            method: SyncMethod.syncCollection.rawValue,
            input: try request.serializedData()
        )
        return try Anki_Sync_SyncCollectionResponse(serializedBytes: out)
    }

    /// One-way full sync. The engine closes, transfers, and reopens the
    /// collection internally (mirroring the desktop's close_for_full_sync +
    /// reopen(after_full_sync:) dance), so no reopen is needed afterwards.
    /// `serverUsn` is only supplied when media syncing; omitting it skips media.
    func fullUploadOrDownload(auth: Anki_Sync_SyncAuth, upload: Bool, serverUsn: Int32? = nil)
        throws
    {
        var request = Anki_Sync_FullUploadOrDownloadRequest()
        request.auth = auth
        request.upload = upload
        if let serverUsn { request.serverUsn = serverUsn }
        _ = try run(
            service: Service.sync.rawValue,
            method: SyncMethod.fullUploadOrDownload.rawValue,
            input: try request.serializedData()
        )
    }
}
