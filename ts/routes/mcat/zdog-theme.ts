// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

/**
 * Shared helpers for the MCAT Zdog decorative accents: resolving the design
 * tokens from `mcat-tokens.scss` into concrete colour strings (Zdog needs real
 * colours, not `var(--x)`), detecting reduced-motion, and reacting to the
 * light/dark theme swap Anki performs via the `.night-mode` root class.
 */

/** The MCAT token colours the accents consume. Never hard-coded here — always
 * read from the live CSS custom properties so the single source of truth stays
 * `mcat-tokens.scss`. */
export interface McatColors {
    chemphys: string;
    cars: string;
    biobiochem: string;
    psychsoc: string;
    ready: string;
    warn: string;
    muted: string;
    hairline: string;
    panel: string;
    needle: string;
}

const TOKEN_MAP: Record<keyof McatColors, string> = {
    chemphys: "--mc-chemphys",
    cars: "--mc-cars",
    biobiochem: "--mc-biobiochem",
    psychsoc: "--mc-psychsoc",
    ready: "--mc-ready",
    warn: "--mc-warn",
    muted: "--mc-muted",
    hairline: "--mc-hairline",
    panel: "--mc-panel",
    needle: "--mc-needle",
};

/** Resolve the MCAT token colours from a reference element's computed style. */
export function readMcatColors(reference: Element): McatColors {
    const style = getComputedStyle(reference);
    const read = (varName: string): string => style.getPropertyValue(varName).trim() || "#888";
    const out = {} as McatColors;
    for (const key of Object.keys(TOKEN_MAP) as (keyof McatColors)[]) {
        out[key] = read(TOKEN_MAP[key]);
    }
    return out;
}

/** True when the user has asked for reduced motion (or when matchMedia is
 * unavailable, we conservatively treat it as reduced). */
export function prefersReducedMotion(): boolean {
    if (typeof window === "undefined" || !window.matchMedia) {
        return true;
    }
    return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

/** Invoke `onChange` whenever the reduced-motion preference flips. Returns a
 * cleanup function. */
export function watchReducedMotion(onChange: (reduced: boolean) => void): () => void {
    if (typeof window === "undefined" || !window.matchMedia) {
        return () => {
            // no-op: matchMedia unavailable, nothing to unsubscribe
        };
    }
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    const handler = (): void => onChange(mq.matches);
    mq.addEventListener("change", handler);
    return () => mq.removeEventListener("change", handler);
}

/** Invoke `onChange` whenever the `.night-mode` root class toggles (Anki's
 * light/dark swap), so accents can re-resolve their token colours. Returns a
 * cleanup function. */
export function watchTheme(onChange: () => void): () => void {
    if (typeof document === "undefined" || typeof MutationObserver === "undefined") {
        return () => {
            // no-op: MutationObserver unavailable, nothing to disconnect
        };
    }
    let night = document.documentElement.classList.contains("night-mode");
    const observer = new MutationObserver(() => {
        const now = document.documentElement.classList.contains("night-mode");
        if (now !== night) {
            night = now;
            onChange();
        }
    });
    observer.observe(document.documentElement, {
        attributes: true,
        attributeFilter: ["class"],
    });
    return () => observer.disconnect();
}
