<!--
Copyright: Ankitects Pty Ltd and contributors
License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
-->
<!--
    A tiny STATIC pseudo-3D "disc stack" emblem drawn with the vendored Zdog
    engine (SVG renderer), used to give the section-hue vitals cards a light
    sense of depth. It is rendered exactly once (plus once more if the theme
    swaps), so it costs nothing on an ongoing basis and is inherently
    reduced-motion safe — there is no animation loop at all. Decorative only.
-->
<script lang="ts">
    import { onDestroy, onMount } from "svelte";

    import Zdog from "./vendor/zdog";
    import type { ZAnchor, ZIllustration } from "./vendor/zdog";
    import type { McatColors } from "./zdog-theme";
    import { readMcatColors, watchTheme } from "./zdog-theme";

    /** MCAT section key selecting which hue token to use. */
    export let section = "chemphys";
    /** Rendered pixel size of the (square) emblem. */
    export let size = 26;

    let svg: SVGSVGElement;
    let illo: ZIllustration | null = null;
    let discs: ZAnchor[] = [];
    let stopThemeWatch: (() => void) | null = null;

    const TAU = Zdog.TAU;
    const STACK = 5;

    function hueFor(c: McatColors): string {
        const map: Record<string, string> = {
            chemphys: c.chemphys,
            cars: c.cars,
            biobiochem: c.biobiochem,
            psychsoc: c.psychsoc,
        };
        return map[section] ?? c.muted;
    }

    function build(): void {
        const c = readMcatColors(svg);
        const hue = hueFor(c);

        illo = new Zdog.Illustration({ element: svg, zoom: size / 16 });
        illo.setSize(size, size);
        // A fixed isometric-ish tilt so the extruded stack reads as 3D.
        illo.rotate.x = -TAU * 0.12;
        illo.rotate.z = -TAU * 0.03;

        discs = [];
        const span = 3.2;
        for (let i = 0; i < STACK; i++) {
            const t = i / (STACK - 1);
            discs.push(
                new Zdog.Ellipse({
                    addTo: illo,
                    diameter: 11,
                    stroke: 1.4,
                    fill: true,
                    color: hue,
                    translate: { z: -span / 2 + t * span },
                }),
            );
        }
    }

    function recolor(): void {
        const hue = hueFor(readMcatColors(svg));
        discs.forEach((d) => {
            (d as unknown as { color: string }).color = hue;
        });
        illo?.updateRenderGraph();
    }

    onMount(() => {
        build();
        illo?.updateRenderGraph();
        stopThemeWatch = watchTheme(recolor);
    });

    onDestroy(() => {
        stopThemeWatch?.();
        illo = null;
        discs = [];
    });
</script>

<svg
    bind:this={svg}
    class="zdog-badge"
    width={size}
    height={size}
    aria-hidden="true"
></svg>

<style>
    .zdog-badge {
        display: block;
        pointer-events: none;
        user-select: none;
        overflow: visible;
    }
</style>
