// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import Foundation
import Security

/// Minimal Keychain-backed store for the AnkiWeb sync key (hkey) and endpoint.
/// The hkey is a long-lived credential, so it belongs in the Keychain rather
/// than UserDefaults. No third-party dependency is used — just the Security
/// framework the Rust engine already links.
enum Keychain {
    private static let service = "net.ankiweb.ankicompanion.sync"
    private static let hkeyAccount = "hkey"
    private static let endpointAccount = "endpoint"

    static func save(hkey: String, endpoint: String?) {
        set(hkeyAccount, hkey)
        set(endpointAccount, endpoint ?? "")
    }

    static func loadHkey() -> String? {
        guard let value = get(hkeyAccount), !value.isEmpty else { return nil }
        return value
    }

    static func loadEndpoint() -> String? {
        guard let value = get(endpointAccount), !value.isEmpty else { return nil }
        return value
    }

    static func clear() {
        delete(hkeyAccount)
        delete(endpointAccount)
    }

    // MARK: - Primitives

    private static func set(_ account: String, _ value: String) {
        delete(account)
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
            kSecValueData as String: Data(value.utf8),
            kSecAttrAccessible as String: kSecAttrAccessibleAfterFirstUnlock,
        ]
        SecItemAdd(query as CFDictionary, nil)
    }

    private static func get(_ account: String) -> String? {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
            kSecReturnData as String: true,
            kSecMatchLimit as String: kSecMatchLimitOne,
        ]
        var result: AnyObject?
        guard SecItemCopyMatching(query as CFDictionary, &result) == errSecSuccess,
              let data = result as? Data
        else { return nil }
        return String(data: data, encoding: .utf8)
    }

    private static func delete(_ account: String) {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
        ]
        SecItemDelete(query as CFDictionary)
    }
}
