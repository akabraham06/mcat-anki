// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

/**
 * Typed facade over the vendored, offline Zdog build (./zdog.min.js).
 *
 * Zdog ships as an untyped UMD bundle; this module gives the small subset of
 * its API we use for the MCAT decorative accents a minimal set of types, so
 * consumers stay type-checked without pulling an external @types dependency.
 */

import ZdogRuntime from "./zdog.min.js";

/** A Zdog 3D vector (also the shape of `.rotate` / `.translate` on anchors). */
export interface ZVector {
    x: number;
    y: number;
    z: number;
    set(o: Partial<ZVector>): ZVector;
}

/** Options accepted by Zdog anchors/shapes (superset; all optional). */
export interface ZOptions {
    addTo?: ZAnchor;
    element?: HTMLElement | SVGElement | string;
    translate?: Partial<ZVector>;
    rotate?: Partial<ZVector>;
    scale?: number | Partial<ZVector>;
    color?: string;
    backface?: string | boolean;
    stroke?: number | boolean;
    fill?: boolean | string;
    diameter?: number;
    width?: number;
    height?: number;
    depth?: number;
    length?: number;
    cornerRadius?: number;
    closed?: boolean;
    visible?: boolean;
    zoom?: number;
    quarters?: number;
}

/** Base scene node. */
export interface ZAnchor {
    rotate: ZVector;
    translate: ZVector;
    scale: ZVector;
    addChild(child: ZAnchor): void;
    updateGraph(): void;
}

/** Root node bound to a <canvas> or <svg> element. */
export interface ZIllustration extends ZAnchor {
    updateRenderGraph(): void;
    renderGraph(): void;
    setSize(width: number, height: number): void;
}

type ZAnchorCtor = new(opts?: ZOptions) => ZAnchor;
type ZIllustrationCtor = new(opts: ZOptions) => ZIllustration;

/** The subset of the Zdog namespace consumed by the MCAT accents. */
export interface ZdogStatic {
    readonly TAU: number;
    Illustration: ZIllustrationCtor;
    Anchor: ZAnchorCtor;
    Group: ZAnchorCtor;
    Shape: ZAnchorCtor;
    Ellipse: ZAnchorCtor;
    Rect: ZAnchorCtor;
    RoundedRect: ZAnchorCtor;
    Vector: new(o?: Partial<ZVector>) => ZVector;
}

const Zdog = ZdogRuntime as unknown as ZdogStatic;

export default Zdog;
