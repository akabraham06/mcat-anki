// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import SwiftUI

@main
struct AnkiCompanionApp: App {
    init() {
        // Register the bundled OFL faces (Space Grotesk / IBM Plex Sans / Mono)
        // so the instrument type system is available everywhere at first paint.
        MCATFonts.register()
    }

    var body: some Scene {
        WindowGroup {
            ContentView()
                // The instrument runs on either appearance; the accent seeds
                // system controls (nav bar, switches) with the Chem/Phys hue.
                .tint(Theme.chemphys)
        }
    }
}
