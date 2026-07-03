// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import SwiftUI
import CoreText

/// The MCAT "diagnostic instrument" design identity, ported from the desktop
/// tokens (ts/routes/mcat/mcat-tokens.scss) so the companion reads as the same
/// lab-readout instrument. Three things carry the identity:
///
///   1. A blue-slate surface system that flips between light and dark.
///   2. Four section hues used as a consistent colour LANGUAGE (a section reads
///      the same colour on the gauge, the timer bar and the deck list).
///   3. A two-family type system — Source Serif 4 (a refined transitional
///      serif) for the scores and all body/UI copy, IBM Plex Mono for every
///      number, interval and clock. This matches the desktop, which standardised
///      on Source Serif 4 (numerics stay on IBM Plex Mono).
///
/// Colours are declared as dynamic (light/dark) `Color`s so every screen adapts
/// to `colorScheme` automatically without threading the environment through.
enum Theme {
    // MARK: Surfaces (flip with the system appearance)

    static let ink = Color(light: 0xEEF3F7, dark: 0x0E1622)
    static let panel = Color(light: 0xFFFFFF, dark: 0x16212E)
    static let panel2 = Color(light: 0xF4F8FB, dark: 0x1B2836)
    static let hairline = Color(light: 0xD6E0E8, dark: 0x24323F)
    static let text = Color(light: 0x0E1622, dark: 0xEAF1F6)
    static let muted = Color(light: 0x51616F, dark: 0x93A4B3)
    static let needle = Color(light: 0x16212E, dark: 0xEAF1F6)

    // MARK: Section hues (identical in both themes — a shared colour language)

    static let chemphys = Color(hex: 0x4E8CFF)
    static let cars = Color(hex: 0xC77DFF)
    static let biobiochem = Color(hex: 0x34C7A0)
    static let psychsoc = Color(hex: 0xFF9F45)

    // MARK: Readiness is semantic, never decorative

    static let warn = Color(hex: 0xE8A13A) // below target
    static let ready = Color(hex: 0x3FB37F) // at / above target
    static let miss = Color(hex: 0xE5484D) // wrong answer / out of time
}

// MARK: - MCAT sections

/// The four MCAT sections, each with its instrument hue. Classification is
/// forgiving: it matches on a name, key or tag from anywhere in the pipeline
/// (readiness sections, exam topics, deck names), checking the compound
/// sections (Biochem, Psych/Soc) before the simple ones so "biochem" doesn't
/// get miscoloured as chemistry.
enum MCATSection: CaseIterable {
    case chemPhys, cars, bioBiochem, psychSoc

    var hue: Color {
        switch self {
        case .chemPhys: return Theme.chemphys
        case .cars: return Theme.cars
        case .bioBiochem: return Theme.biobiochem
        case .psychSoc: return Theme.psychsoc
        }
    }

    var shortLabel: String {
        switch self {
        case .chemPhys: return "C/P"
        case .cars: return "CARS"
        case .bioBiochem: return "B/B"
        case .psychSoc: return "P/S"
        }
    }

    /// Best-effort mapping from any free-form section/topic/deck string.
    static func classify(_ raw: String) -> MCATSection? {
        let s = raw.lowercased()
        if s.contains("cars") || s.contains("critical analysis") || s.contains("reasoning skill") {
            return .cars
        }
        if s.contains("psych") || s.contains("soc") || s.contains("behav") {
            return .psychSoc
        }
        if s.contains("bio") || s.contains("biochem") {
            return .bioBiochem
        }
        if s.contains("chem") || s.contains("phys") {
            return .chemPhys
        }
        return nil
    }

    /// A stable hue for an arbitrary label, falling back to a neutral accent so
    /// unclassifiable rows still look intentional.
    static func hue(for raw: String) -> Color {
        classify(raw)?.hue ?? Theme.chemphys
    }
}

// MARK: - Type roles

extension Font {
    /// Source Serif 4 — the big display scores, set in its heavier weights.
    /// `relativeTo` keeps it responsive to Dynamic Type; bundled fonts fall back
    /// to the system face automatically if registration ever fails.
    static func mcatDisplay(
        _ size: CGFloat, relativeTo style: TextStyle = .largeTitle, bold: Bool = false
    ) -> Font {
        .custom(bold ? "SourceSerif4-Bold" : "SourceSerif4-SemiBold", size: size, relativeTo: style)
    }

    /// Source Serif 4 — body and UI copy.
    static func mcatBody(
        _ size: CGFloat, relativeTo style: TextStyle = .body, semibold: Bool = false
    ) -> Font {
        .custom(semibold ? "SourceSerif4-SemiBold" : "SourceSerif4-Regular", size: size, relativeTo: style)
    }

    /// IBM Plex Mono — every number, interval, ratio and clock. Inherently
    /// tabular, so columns of figures line up.
    static func mcatMono(
        _ size: CGFloat, relativeTo style: TextStyle = .body, medium: Bool = false
    ) -> Font {
        .custom(medium ? "IBMPlexMono-Medium" : "IBMPlexMono-Regular", size: size, relativeTo: style)
    }
}

/// Registers the bundled OFL faces at process scope so `Font.custom` can find
/// them without an Info.plist `UIAppFonts` array. Safe to call once at launch;
/// silently no-ops (and the type helpers fall back to system fonts) if a file
/// is missing.
enum MCATFonts {
    private static let files = [
        "source-serif-400", "source-serif-600", "source-serif-700",
        "ibm-plex-mono-400", "ibm-plex-mono-500",
    ]

    static func register() {
        for name in files {
            guard let url = Bundle.main.url(forResource: name, withExtension: "ttf") else { continue }
            CTFontManagerRegisterFontsForURL(url as CFURL, .process, nil)
        }
    }
}

// MARK: - Reusable instrument surfaces

/// A panel with the instrument's hairline border and optional left hue rail —
/// the shared container for scores, sections and actions.
struct InstrumentCard<Content: View>: View {
    var accent: Color?
    var padding: CGFloat = 14
    @ViewBuilder var content: Content

    var body: some View {
        content
            .padding(padding)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Theme.panel)
            .overlay(alignment: .leading) {
                if let accent {
                    Rectangle().fill(accent).frame(width: 3)
                }
            }
            .overlay(
                RoundedRectangle(cornerRadius: 12)
                    .stroke(Theme.hairline, lineWidth: 1)
            )
            .clipShape(RoundedRectangle(cornerRadius: 12))
    }
}

/// A small uppercase eyebrow label — the instrument's captions.
struct Eyebrow: View {
    let text: String
    var accent: Color = Theme.muted
    init(_ text: String, accent: Color = Theme.muted) {
        self.text = text
        self.accent = accent
    }
    var body: some View {
        Text(text.uppercased())
            .font(.mcatMono(11, relativeTo: .caption2, medium: true))
            .tracking(1.2)
            .foregroundStyle(accent)
    }
}

/// The signature range gauge: a track, a confidence band and a needle at the
/// point estimate. Colour is semantic — green once at/above target, amber
/// below — so the readiness verdict reads at a glance.
struct GaugeBar: View {
    let point: Double
    let low: Double
    let high: Double
    let scaleMin: Double
    let scaleMax: Double
    /// Optional target line; the needle turns green at/above it.
    var target: Double?
    var tint: Color?
    var height: CGFloat = 10

    private var range: Double { max(scaleMax - scaleMin, 1) }
    private func frac(_ v: Double) -> Double {
        min(max((v - scaleMin) / range, 0), 1)
    }

    private var needleColor: Color {
        if let tint { return tint }
        if let target { return point >= target ? Theme.ready : Theme.warn }
        return Theme.needle
    }

    var body: some View {
        GeometryReader { geo in
            let w = geo.size.width
            let bandLeft = frac(low) * w
            let bandWidth = max((frac(high) - frac(low)) * w, 2)
            let pointX = frac(point) * w
            ZStack(alignment: .leading) {
                Capsule().fill(Theme.hairline).frame(height: height)
                Capsule().fill(needleColor.opacity(0.28))
                    .frame(width: bandWidth, height: height)
                    .offset(x: bandLeft)
                if let target {
                    Rectangle().fill(Theme.muted.opacity(0.6))
                        .frame(width: 1.5, height: height + 6)
                        .offset(x: min(max(frac(target) * w, 0), w - 1.5), y: -3)
                }
                Capsule().fill(needleColor)
                    .frame(width: 3, height: height + 6)
                    .offset(x: min(max(pointX - 1.5, 0), w - 3), y: -3)
            }
            .frame(height: height + 6, alignment: .center)
        }
        .frame(height: height + 6)
    }
}

// MARK: - Button styles

/// The primary action: a filled, hue-tinted control used for the exam start,
/// Next and Done actions.
struct InstrumentButtonStyle: ButtonStyle {
    var tint: Color = Theme.chemphys
    var prominent: Bool = true

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.mcatBody(16, relativeTo: .headline, semibold: true))
            .foregroundStyle(prominent ? Color.white : tint)
            .frame(maxWidth: .infinity)
            .padding(.vertical, 13)
            .background(
                RoundedRectangle(cornerRadius: 12)
                    .fill(prominent ? tint : Theme.panel2)
            )
            .overlay(
                RoundedRectangle(cornerRadius: 12)
                    .stroke(prominent ? Color.clear : tint.opacity(0.5), lineWidth: 1)
            )
            .opacity(configuration.isPressed ? 0.82 : 1)
            .scaleEffect(configuration.isPressed ? 0.99 : 1)
    }
}

// MARK: - Colour helpers

extension Color {
    /// A hex colour that is the same in light and dark (section hues, semantics).
    init(hex: UInt32) {
        self.init(
            .sRGB,
            red: Double((hex >> 16) & 0xFF) / 255,
            green: Double((hex >> 8) & 0xFF) / 255,
            blue: Double(hex & 0xFF) / 255,
            opacity: 1
        )
    }

    /// A dynamic colour that resolves per appearance, so surfaces flip with the
    /// system light/dark setting.
    init(light: UInt32, dark: UInt32) {
        self.init(UIColor { traits in
            let hex = traits.userInterfaceStyle == .dark ? dark : light
            return UIColor(
                red: CGFloat((hex >> 16) & 0xFF) / 255,
                green: CGFloat((hex >> 8) & 0xFF) / 255,
                blue: CGFloat(hex & 0xFF) / 255,
                alpha: 1
            )
        })
    }
}
