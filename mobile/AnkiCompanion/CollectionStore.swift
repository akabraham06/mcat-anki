// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import Foundation
import SwiftProtobuf

/// Opens the shared engine and a collection, then exposes MCAT readiness to the
/// SwiftUI views. On the desktop the collection is opened by aqt; here we open
/// a collection file synced/copied into the app's Documents directory.
@MainActor
final class CollectionStore: ObservableObject {
    @Published var readiness: Anki_Mcat_ExamReadiness?
    @Published var errorMessage: String?
    @Published var loading = false

    private var backend: AnkiBackend?

    /// Path to the collection the companion reads. In a full build this is the
    /// synced collection; for the demo it is a copy of the generated starter
    /// deck imported into a fresh collection.
    var collectionPath: URL {
        let docs = FileManager.default.urls(
            for: .documentDirectory, in: .userDomainMask
        )[0]
        return docs.appendingPathComponent("collection.anki2")
    }

    func start() async {
        loading = true
        defer { loading = false }
        do {
            let backend = try AnkiBackend(initMessage: makeInitMessage())
            self.backend = backend
            try openCollection(backend)
            self.readiness = try backend.examReadiness()
        } catch {
            self.errorMessage = "\(error)"
        }
    }

    /// Build an anki.backend.BackendInit message. Language + folder are enough
    /// to boot the engine; see proto/anki/backend.proto.
    private func makeInitMessage() -> Data {
        var init_ = Anki_Backend_BackendInit()
        init_.preferredLangs = ["en"]
        init_.localeFolderPath = ""
        init_.server = false
        return (try? init_.serializedData()) ?? Data()
    }

    /// Open the collection via CollectionService.OpenCollection.
    private func openCollection(_ backend: AnkiBackend) throws {
        var request = Anki_Collection_OpenCollectionRequest()
        request.collectionPath = collectionPath.path
        // OpenCollection is method 0 of CollectionService.
        _ = try backend.run(
            service: AnkiBackend.Service.collection.rawValue,
            method: 0,
            input: try request.serializedData()
        )
    }
}
