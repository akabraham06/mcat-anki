<!--
Copyright: Ankitects Pty Ltd and contributors
License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
-->
<!--
    Decorative-only pseudo-3D accent for the MCAT dashboard, drawn with the
    vendored (offline) Zdog engine. It renders a small "gyroscope" instrument —
    interlocking orbit rings in the four MCAT section hues around a core — that
    fits the diagnostic-instrument identity of the surface.

    Deliberately featherweight: ONE small canvas, a handful of vector shapes,
    and a low-cost rotate-and-redraw loop that PAUSES whenever the tab is hidden
    or the canvas scrolls offscreen. Honours prefers-reduced-motion by rendering
    a single static frame with no animation. Purely decorative (aria-hidden).
-->
<script lang="ts">
    import { onDestroy, onMount } from "svelte";

    import Zdog from "./vendor/zdog";
    import type { ZAnchor, ZIllustration } from "./vendor/zdog";
    import {
        prefersReducedMotion,
        readMcatColors,
        watchReducedMotion,
        watchTheme,
    } from "./zdog-theme";

    /** Rendered pixel size of the (square) canvas. */
    export let size = 72;
    /** Radians of Y rotation added per frame while animating (kept slow). */
    export let speed = 0.006;
    /** Optional accessible label; defaults to fully decorative (hidden). */
    export let label = "";

    let canvas: HTMLCanvasElement;
    let illo: ZIllustration | null = null;
    let rings: ZAnchor[] = [];
    let frame = 0;
    let visible = true; // in-viewport
    let animating = false;
    let reduced = prefersReducedMotion();

    const TAU = Zdog.TAU;
    // A gentle fixed viewing tilt so the rings read as 3D even when static.
    const BASE_TILT_X = -TAU * 0.08;

    function build(): void {
        if (!canvas) {
            return;
        }
        const c = readMcatColors(canvas);
        const hues = [c.chemphys, c.biobiochem, c.psychsoc, c.cars];

        illo = new Zdog.Illustration({
            element: canvas,
            zoom: size / 30,
        });
        illo.setSize(size, size);
        illo.rotate.x = BASE_TILT_X;

        const D = 20;
        const stroke = 2.4;
        rings = [
            new Zdog.Ellipse({
                addTo: illo,
                diameter: D,
                stroke,
                color: hues[0],
                rotate: { y: 0 },
            }),
            new Zdog.Ellipse({
                addTo: illo,
                diameter: D,
                stroke,
                color: hues[1],
                rotate: { y: TAU / 4 },
            }),
            new Zdog.Ellipse({
                addTo: illo,
                diameter: D * 0.7,
                stroke,
                color: hues[2],
                rotate: { x: TAU / 4 },
            }),
            // Core: a stout dot at the centre in the "ready" accent.
            new Zdog.Shape({
                addTo: illo,
                stroke: 6,
                color: hues[3],
            }),
        ];
    }

    function render(): void {
        illo?.updateRenderGraph();
    }

    function recolor(): void {
        if (!canvas) {
            return;
        }
        const c = readMcatColors(canvas);
        const hues = [c.chemphys, c.biobiochem, c.psychsoc, c.cars];
        rings.forEach((ring, i) => {
            // `color` is a runtime Zdog property not on our minimal type.
            (ring as unknown as { color: string }).color = hues[i];
        });
        render();
    }

    function loop(): void {
        if (!illo) {
            return;
        }
        illo.rotate.y += speed;
        render();
        frame = requestAnimationFrame(loop);
    }

    function shouldAnimate(): boolean {
        return !reduced && visible && !document.hidden;
    }

    function sync(): void {
        if (shouldAnimate()) {
            if (!animating) {
                animating = true;
                frame = requestAnimationFrame(loop);
            }
        } else if (animating) {
            animating = false;
            cancelAnimationFrame(frame);
        }
    }

    function onVisibilityChange(): void {
        sync();
    }

    let io: IntersectionObserver | null = null;
    let stopReducedWatch: (() => void) | null = null;
    let stopThemeWatch: (() => void) | null = null;

    onMount(() => {
        build();
        // Always draw at least one frame so the accent is present (and this is
        // the only frame ever drawn under reduced-motion).
        render();

        if (typeof IntersectionObserver !== "undefined") {
            io = new IntersectionObserver(
                (entries) => {
                    visible = entries.some((e) => e.isIntersecting);
                    sync();
                },
                { threshold: 0.01 },
            );
            io.observe(canvas);
        }
        document.addEventListener("visibilitychange", onVisibilityChange);
        stopReducedWatch = watchReducedMotion((r) => {
            reduced = r;
            if (reduced) {
                // Settle back to the neutral tilt for a calm static pose.
                if (illo) {
                    illo.rotate.y = 0;
                }
                render();
            }
            sync();
        });
        stopThemeWatch = watchTheme(recolor);

        sync();
    });

    onDestroy(() => {
        if (animating) {
            cancelAnimationFrame(frame);
        }
        io?.disconnect();
        document.removeEventListener("visibilitychange", onVisibilityChange);
        stopReducedWatch?.();
        stopThemeWatch?.();
        illo = null;
        rings = [];
    });
</script>

<canvas
    bind:this={canvas}
    class="zdog-instrument"
    width={size}
    height={size}
    style="width:{size}px;height:{size}px"
    aria-hidden={label ? undefined : "true"}
    role={label ? "img" : undefined}
    aria-label={label || undefined}
></canvas>

<style>
    .zdog-instrument {
        display: block;
        /* Decorative: never intercept pointer events from the panel beneath. */
        pointer-events: none;
        user-select: none;
    }
</style>
