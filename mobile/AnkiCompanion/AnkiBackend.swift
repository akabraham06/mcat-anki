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
    enum BackendError: Error {
        case open(String)
        case command(String)
    }

    /// Backend service indices, taken from the generated backend
    /// (`out/pylib/anki/_backend_generated.py`). Re-run
    /// `patch_service_indices.sh` after regenerating the backend to keep these
    /// in sync. Method indices below are the declaration order within the proto.
    enum Service: UInt32 {
        case collection = 3
        case mcat = 41
    }

    enum McatMethod: UInt32 {
        case getTopicMastery = 0
        case getExamReadiness = 1
        case getStudyRecommendation = 2
        case buildInterleavedSession = 3
        case getTopicTargets = 4
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
            throw BackendError.command("backend error (\(bytes.count) bytes)")
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
}
