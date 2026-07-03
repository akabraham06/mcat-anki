<!--
Copyright: Ankitects Pty Ltd and contributors
License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
-->
<script lang="ts">
    import type {
        AiStatus,
        AiStudyPlan,
        ExamReadiness,
        InterleavedSession,
        ScoreEstimate,
        SectionScore,
        TopicMasteryList,
        TopicTargetList,
    } from "@generated/anki/mcat_pb";
    import { buildInterleavedSession } from "@generated/backend";
    import { bridgeCommand, bridgeCommandsAvailable } from "@tslib/bridgecommand";
    import { onMount } from "svelte";

    import "./mcat-tokens.scss";

    export let readiness: ExamReadiness;
    export let targets: TopicTargetList;
    export let mastery: TopicMasteryList;
    export let aiStatus: AiStatus | undefined = undefined;
    export let aiPlan: AiStudyPlan | undefined = undefined;

    // --- Section hue language (single source of truth in mcat-tokens.scss) ---
    const sectionHue: Record<string, string> = {
        chemphys: "var(--mc-chemphys)",
        cars: "var(--mc-cars)",
        biobiochem: "var(--mc-biobiochem)",
        psychsoc: "var(--mc-psychsoc)",
    };
    const hueOf = (key: string): string => sectionHue[key] ?? "var(--mc-muted)";
    const sectionShortLabels: Record<string, string> = {
        biobiochem: "Bio/Biochem",
        chemphys: "Chem/Phys",
        cars: "CARS",
        psychsoc: "Psych/Soc",
    };
    const shortSection = (key: string, name: string): string =>
        sectionShortLabels[key] ?? name ?? key;

    const pct = (n: number): string => `${Math.round(n)}%`;
    const one = (n: number): string => n.toFixed(1);

    // --- The plan prefers AI, always keeps the deterministic recommender. ---
    $: planItems = aiPlan?.items ?? [];
    $: planEvidence = aiPlan?.evidence ?? [];
    $: usingFallback = aiPlan?.usedFallback ?? true;

    $: aiOn = aiStatus?.available ?? false;
    // Turn an AI error/reason string into interface-voice direction.
    $: aiReason = aiStatus?.reason ?? "";
    $: aiDirection = (() => {
        const r = aiReason.toLowerCase();
        if (aiOn) {
            return aiReason || "Grounding plans and explanations in your data.";
        }
        if (r.includes("401") || r.includes("key rejected") || r.includes("invalid")) {
            return "AI key rejected. Update it in AI settings.";
        }
        if (r.includes("offline") || r.includes("unreachable")) {
            return "AI offline — the deterministic plan is running instead.";
        }
        if (r.includes("no api key") || r.includes("not configured")) {
            return "Add a key in AI settings to ground plans in your data.";
        }
        return "Deterministic plan is running. Turn on AI for grounded advice.";
    })();

    // Only meaningful inside the desktop shell (real MCAT home). No Qt bridge in
    // dev/preview, so hide the buttons there.
    const inDesktopShell = bridgeCommandsAvailable();
    const study = (): void => bridgeCommand("study");
    const openDecks = (): void => bridgeCommand("decks");
    const openAiSettings = (): void => bridgeCommand("mcat:ai-settings");

    // --- Readiness gauge (the signature Calibration Gauge, 472–528) ---
    $: rd = readiness.readiness as ScoreEstimate | undefined;
    $: scaleMin = rd?.scaleMin || 472;
    $: scaleMax = rd?.scaleMax || 528;
    // Position (0..100%) of a score on the 472–528 scale.
    const posOf = (v: number, min: number, max: number): number => {
        const range = max - min || 1;
        return Math.max(0, Math.min(100, ((v - min) / range) * 100));
    };
    $: gaugeReady = !!rd?.available;

    // Real AAMC percentile anchors — reference ticks a pre-med recognises.
    const percentileTicks = [
        { score: 500, label: "50th" },
        { score: 510, label: "80th" },
        { score: 515, label: "90th" },
        { score: 520, label: "97th" },
    ];

    // --- User-settable target score (persisted client-side; see steps.md).
    const TARGET_KEY = "mcat.targetScore";
    const DEFAULT_TARGET = 515;
    let target = DEFAULT_TARGET;
    let editingTarget = false;
    const clampTarget = (v: number): number =>
        Math.max(472, Math.min(528, Math.round(v || DEFAULT_TARGET)));
    function commitTarget(v: number): void {
        target = clampTarget(v);
        try {
            localStorage.setItem(TARGET_KEY, String(target));
        } catch {
            // storage unavailable (private mode / preview): keep the in-memory value.
        }
    }
    function nudgeTarget(delta: number): void {
        commitTarget(target + delta);
    }

    // One orchestrated motion: the needle settles from the low end into the
    // band on load. Disabled for prefers-reduced-motion via CSS.
    let settled = false;
    onMount(() => {
        try {
            const stored = Number(localStorage.getItem(TARGET_KEY));
            if (stored) {
                target = clampTarget(stored);
            }
        } catch {
            // ignore
        }
        requestAnimationFrame(() => {
            settled = true;
        });
    });

    $: point = rd?.point ?? scaleMin;
    $: onTarget = gaugeReady && point >= target;
    // Needle rests at the low end until settled, then moves to the point.
    $: needlePos = settled && gaugeReady ? posOf(point, scaleMin, scaleMax) : 0;
    $: bandLeft = rd ? posOf(rd.low, scaleMin, scaleMax) : 0;
    $: bandRight = rd ? posOf(rd.high, scaleMin, scaleMax) : 0;
    $: targetPos = posOf(target, scaleMin, scaleMax);

    // Actionable unlock copy when readiness abstains.
    $: rdd = readiness.readinessDetail;
    $: unlockMessage = (() => {
        if (gaugeReady) {
            return "Readiness is live.";
        }
        if (rdd) {
            if (!rdd.gradedReviewsMet) {
                const n = Math.max(
                    1,
                    Number(rdd.requiredGradedReviews) - Number(rdd.gradedReviews),
                );
                return `${n} more graded question${n === 1 ? "" : "s"} unlocks your readiness score.`;
            }
            if (!rdd.coverageMet) {
                const gap = Math.max(
                    1,
                    Math.round(rdd.requiredCoveragePercent - rdd.coveragePercent),
                );
                return `Cover ${gap}% more of your topics to unlock your readiness score.`;
            }
        }
        return rd?.abstainReason ?? "Keep studying to unlock your readiness score.";
    })();

    // --- Section vitals (memory), 118–132 mini-gauges ---
    $: sections = readiness.sections ?? [];
    const SECTION_MIN = 118;
    const SECTION_MAX = 132;
    let selectedSection = "";
    function focusSection(key: string): void {
        selectedSection = selectedSection === key ? "" : key;
    }

    // --- Coverage map: decks reframed by MCAT taxonomy (Section → Topic) ---
    $: masteryByKey = new Map(mastery.topics.map((t) => [t.topicKey, t]));
    interface CoverageTopic {
        key: string;
        name: string;
        coverage: number;
        recall: number;
        inDeck: boolean;
    }
    interface CoverageSection {
        key: string;
        name: string;
        topics: CoverageTopic[];
        coverage: number;
    }
    $: coverageSections = (() => {
        const bySection = new Map<string, CoverageSection>();
        for (const t of targets.targets) {
            let sec = bySection.get(t.sectionKey);
            if (!sec) {
                sec = {
                    key: t.sectionKey,
                    name: t.sectionName,
                    topics: [],
                    coverage: 0,
                };
                bySection.set(t.sectionKey, sec);
            }
            const m = masteryByKey.get(t.topicKey);
            sec.topics.push({
                key: t.topicKey,
                name: t.topicName,
                coverage: m?.coveragePercent ?? 0,
                recall: (m?.averageRecallProbability ?? 0) * 100,
                inDeck: t.inDeck,
            });
        }
        for (const sec of bySection.values()) {
            const covered = sec.topics.filter((t) => t.coverage > 0).length;
            sec.coverage = sec.topics.length
                ? (covered / sec.topics.length) * 100
                : 0;
        }
        return [...bySection.values()];
    })();
    $: visibleCoverage = selectedSection
        ? coverageSections.filter((s) => s.key === selectedSection)
        : coverageSections;

    // --- Existing analytics (unchanged data), kept as quiet instrument rows ---
    interface Pace {
        name: string;
        target: number;
        actual: number;
        overtime: number;
    }
    $: pacing = targets.targets
        .filter((t) => t.inDeck)
        .map((t): Pace => {
            const m = masteryByKey.get(t.topicKey);
            return {
                name: t.topicName,
                target: t.targetSeconds,
                actual: m?.averageResponseTimeSecs ?? 0,
                overtime: (m?.overtimeRate ?? 0) * 100,
            };
        })
        .filter((p) => p.actual > 0);

    // --- Timed interleaved session builder (preserved) ---
    let interleave = true;
    let session: InterleavedSession | null = null;
    let building = false;
    const targetByKey = new Map(targets.targets.map((t) => [t.topicKey, t]));
    async function buildSession(): Promise<void> {
        building = true;
        session = null;
        try {
            session = await buildInterleavedSession({
                tagPrefix: "",
                maxCards: 20,
                interleave,
            });
        } finally {
            building = false;
        }
    }
    function startSession(): void {
        if (!session) {
            return;
        }
        bridgeCommand(`mcat:start-session:${interleave ? 1 : 0}`);
    }
    $: sessionTargetSecs = session
        ? session.topicKeys.reduce(
              (sum, k) => sum + (targetByKey.get(k)?.targetSeconds ?? 0),
              0,
          )
        : 0;
    interface SessionItem {
        topicName: string;
        sectionName: string;
        sectionKey: string;
    }
    $: sessionItems = (session?.topicKeys ?? []).map((key): SessionItem => {
        const t = targetByKey.get(key);
        return {
            topicName: t?.topicName ?? key,
            sectionName: t?.sectionName ?? "",
            sectionKey: t?.sectionKey ?? "",
        };
    });

    $: recommendation = readiness.recommendation;
    $: firstMin = planItems[0]?.minutes ?? Math.max(15, Math.round(sessionTargetSecs / 60));
    $: xp = readiness.xp;
    $: transferGaps = readiness.transferGaps ?? [];
    $: memoryDetail = readiness.memoryDetail;
    $: performanceDetail = readiness.performanceDetail;

    // Detail scores shown as supporting instrument readouts (memory / perf).
    $: supportScores = [readiness.memory, readiness.performance].filter(
        (s): s is ScoreEstimate => !!s,
    );

    function sectionPos(s: SectionScore): number {
        return posOf(s.point, SECTION_MIN, SECTION_MAX);
    }
    function sectionBand(s: SectionScore): { left: number; right: number } {
        return {
            left: posOf(s.low, SECTION_MIN, SECTION_MAX),
            right: posOf(s.high, SECTION_MIN, SECTION_MAX),
        };
    }
</script>

<div class="mcat">
    <!-- ===== Signature: the Calibration Gauge (472–528) ===== -->
    <section class="gauge-panel" aria-label="Exam readiness gauge">
        <div class="gauge-top">
            <div class="gauge-id">
                <span class="eyebrow">{readiness.exam} readiness</span>
                <div class="readout">
                    {#if gaugeReady}
                        <span class="score" class:ready={onTarget} class:warn={!onTarget}>
                            {Math.round(point)}
                        </span>
                        <span class="range">
                            CI {Math.round(rd?.low ?? 0)}–{Math.round(rd?.high ?? 0)}
                        </span>
                    {:else}
                        <span class="score muted">– – –</span>
                        <span class="range">calibrating</span>
                    {/if}
                </div>
                <p class="unlock" class:live={gaugeReady}>{unlockMessage}</p>
            </div>

            <div class="gauge-side">
                <button
                    type="button"
                    class="vital"
                    class:on={aiOn}
                    on:click={inDesktopShell && !aiOn ? openAiSettings : undefined}
                    disabled={!inDesktopShell || aiOn}
                    title={aiReason}
                >
                    <span class="dot"></span>
                    <span class="vital-label">
                        AI assistant: {aiOn ? "on" : "off"}{!aiOn && inDesktopShell
                            ? " — turn on"
                            : ""}
                    </span>
                </button>
                <div class="target-control">
                    <span class="tc-label">Target</span>
                    {#if editingTarget}
                        <!-- svelte-ignore a11y-autofocus -->
                        <input
                            class="tc-input"
                            type="number"
                            min="472"
                            max="528"
                            autofocus
                            value={target}
                            on:change={(e) =>
                                commitTarget(Number(e.currentTarget.value))}
                            on:blur={() => (editingTarget = false)}
                        />
                    {:else}
                        <button
                            type="button"
                            class="tc-value"
                            on:click={() => (editingTarget = true)}
                        >
                            {target}
                        </button>
                    {/if}
                    <span class="tc-steppers">
                        <button
                            type="button"
                            aria-label="Raise target score"
                            on:click={() => nudgeTarget(1)}>+</button
                        >
                        <button
                            type="button"
                            aria-label="Lower target score"
                            on:click={() => nudgeTarget(-1)}>−</button
                        >
                    </span>
                </div>
            </div>
        </div>

        <div class="gauge" class:abstain={!gaugeReady}>
            <!-- ready zone: target → max -->
            <div
                class="ready-zone"
                style="left:{targetPos}%;width:{Math.max(0, 100 - targetPos)}%"
            ></div>
            <!-- confidence interval band -->
            {#if gaugeReady}
                <div
                    class="band"
                    class:ready={onTarget}
                    class:warn={!onTarget}
                    style="left:{bandLeft}%;width:{Math.max(1.5, bandRight - bandLeft)}%"
                ></div>
            {/if}
            <!-- percentile reference ticks -->
            {#each percentileTicks as tick (tick.score)}
                <div
                    class="ptick"
                    style="left:{posOf(tick.score, scaleMin, scaleMax)}%"
                >
                    <span class="ptick-label">{tick.label}</span>
                </div>
            {/each}
            <!-- target flag -->
            <div class="target-flag" style="left:{targetPos}%" title="Target {target}">
                <span class="flag-pole"></span>
                <span class="flag">{target}</span>
            </div>
            <!-- needle -->
            {#if gaugeReady}
                <div
                    class="needle"
                    class:ready={onTarget}
                    class:warn={!onTarget}
                    style="left:{needlePos}%"
                ></div>
            {/if}
        </div>
        <div class="scale-ends">
            <span>{Math.round(scaleMin)}</span>
            <span class="scale-caption">MCAT scaled score</span>
            <span>{Math.round(scaleMax)}</span>
        </div>

        <div class="gauge-meta">
            <span>Coverage <b>{pct(readiness.overallCoveragePercent)}</b></span>
            <span class="sep"></span>
            <span><b>{readiness.gradedReviews}</b> graded reviews</span>
        </div>
    </section>

    <!-- ===== Primary CTA: the next hour ===== -->
    <section class="plan-panel">
        <header class="panel-head">
            <h2>Your next hour</h2>
            <span class="src" class:ai={!usingFallback}>
                {usingFallback ? "deterministic plan" : "AI · grounded in your data"}
            </span>
        </header>
        {#if aiPlan?.summary}
            <p class="plan-summary">{aiPlan.summary}</p>
        {/if}
        {#if planItems.length}
            <ol class="plan">
                {#each planItems as item, i (i)}
                    <li>
                        <span class="step-min">{item.minutes}<small>min</small></span>
                        <div class="step-body">
                            <span class="step-action">{item.action}</span>
                            {#if item.reason}
                                <p class="step-reason">{item.reason}</p>
                            {/if}
                            {#if item.evidence.length}
                                <details class="step-evidence">
                                    <summary>Evidence</summary>
                                    <ul>
                                        {#each item.evidence as ev (ev)}
                                            <li>{ev}</li>
                                        {/each}
                                    </ul>
                                </details>
                            {/if}
                        </div>
                    </li>
                {/each}
            </ol>
        {:else}
            <p class="plan-summary">
                Answer a few graded questions and your prescriptive plan appears here.
            </p>
        {/if}

        {#if inDesktopShell}
            <div class="cta">
                <button class="cta-primary" on:click={study}>
                    {#if recommendation && recommendation.available}
                        Study {recommendation.topicName} — {firstMin} min
                    {:else}
                        Study now — {firstMin} min
                    {/if}
                </button>
                <button class="cta-secondary" on:click={openDecks}>Browse decks</button>
            </div>
        {/if}

        {#if planEvidence.length}
            <details class="evidence">
                <summary>All data behind this plan</summary>
                <ul>
                    {#each planEvidence as ev (ev)}
                        <li>{ev}</li>
                    {/each}
                </ul>
            </details>
        {/if}
        {#if !aiOn}
            <p class="ai-note">{aiDirection}</p>
        {/if}
    </section>

    <!-- ===== Section vitals strip ===== -->
    {#if sections.length}
        <section class="vitals">
            <header class="panel-head">
                <h2>Section vitals</h2>
                <span class="src">memory, per section (118–132)</span>
            </header>
            <div class="vital-strip">
                {#each sections as s (s.sectionKey)}
                    <button
                        type="button"
                        class="mini"
                        class:selected={selectedSection === s.sectionKey}
                        style="--hue:{hueOf(s.sectionKey)}"
                        on:click={() => focusSection(s.sectionKey)}
                        title="Show {shortSection(s.sectionKey, s.sectionName)} coverage"
                    >
                        <span class="mini-name">
                            {shortSection(s.sectionKey, s.sectionName)}
                        </span>
                        {#if s.available}
                            <span class="mini-score">{Math.round(s.point)}</span>
                            <div class="mini-gauge">
                                <div
                                    class="mini-band"
                                    style="left:{sectionBand(s).left}%;width:{Math.max(
                                        2,
                                        sectionBand(s).right - sectionBand(s).left,
                                    )}%"
                                ></div>
                                <div
                                    class="mini-needle"
                                    style="left:{sectionPos(s)}%"
                                ></div>
                            </div>
                            <span class="mini-sub">mem {pct(s.memoryPercent)}</span>
                        {:else}
                            <span class="mini-score muted">—</span>
                            <div class="mini-gauge empty"></div>
                            <span class="mini-sub muted">no data yet</span>
                        {/if}
                    </button>
                {/each}
            </div>
        </section>
    {/if}

    <!-- ===== Coverage map: decks reframed by MCAT taxonomy ===== -->
    {#if coverageSections.length}
        <section class="coverage-map">
            <header class="panel-head">
                <h2>Coverage map</h2>
                {#if selectedSection}
                    <button class="chip-clear" on:click={() => (selectedSection = "")}>
                        Show all sections
                    </button>
                {:else}
                    <span class="src">by section → topic</span>
                {/if}
            </header>
            {#each visibleCoverage as sec (sec.key)}
                <div class="cov-section" style="--hue:{hueOf(sec.key)}">
                    <div class="cov-head">
                        <span class="cov-name">
                            {shortSection(sec.key, sec.name)}
                        </span>
                        <span class="cov-stat">{pct(sec.coverage)} topics covered</span>
                    </div>
                    <ul class="cov-topics">
                        {#each sec.topics as t (t.key)}
                            <li class:dim={!t.inDeck}>
                                <span class="cov-topic">{t.name}</span>
                                <div class="cov-bar">
                                    <div
                                        class="cov-fill"
                                        style="width:{Math.max(0, Math.min(100, t.coverage))}%"
                                    ></div>
                                </div>
                                <span class="cov-pct">{pct(t.coverage)}</span>
                            </li>
                        {/each}
                    </ul>
                </div>
            {/each}
        </section>
    {/if}

    <!-- ===== Supporting readouts (quiet) ===== -->
    {#if supportScores.length}
        <section class="support">
            {#each supportScores as est (est.label)}
                <div class="readout-card" class:abstain={!est.available}>
                    <span class="rc-label">{est.label}</span>
                    {#if est.available}
                        <span class="rc-score">{Math.round(est.point)}</span>
                        <span class="rc-range">
                            {Math.round(est.low)}–{Math.round(est.high)} ·
                            <span class="conf conf-{est.confidence}"
                                >{est.confidence}</span
                            >
                        </span>
                    {:else}
                        <span class="rc-score muted">—</span>
                        <span class="rc-range">{est.abstainReason}</span>
                    {/if}
                    {#if est.label === "Memory" && memoryDetail}
                        <dl class="stats">
                            <dt>Cards reviewed</dt>
                            <dd>
                                {memoryDetail.cardsReviewed} / {memoryDetail.cardsTotal}
                            </dd>
                            {#if memoryDetail.cardsReviewed > 0}
                                <dt>Avg retention</dt>
                                <dd>{pct(memoryDetail.averageRetentionPercent)}</dd>
                            {/if}
                            <dt>Mature / young</dt>
                            <dd>
                                {memoryDetail.matureCards} / {memoryDetail.youngCards}
                            </dd>
                            <dt>Breadth</dt>
                            <dd>
                                {memoryDetail.coveredTopics} / {memoryDetail.totalTopics}
                                ({pct(memoryDetail.breadthPercent)})
                            </dd>
                        </dl>
                    {:else if est.label === "Performance" && performanceDetail}
                        <dl class="stats">
                            <dt>Questions answered</dt>
                            <dd>{performanceDetail.questionsAnswered}</dd>
                            {#if performanceDetail.questionsAnswered > 0}
                                <dt>Accuracy</dt>
                                <dd>{pct(performanceDetail.accuracyPercent)}</dd>
                                <dt>On-time rate</dt>
                                <dd class:met={performanceDetail.onTimeRate >= 0.5}>
                                    {pct(performanceDetail.onTimeRate * 100)}
                                </dd>
                                <dt>Avg answer time</dt>
                                <dd class:slow={performanceDetail.overtimeRate > 0.5}>
                                    {one(performanceDetail.averageResponseTimeSecs)}s
                                </dd>
                            {/if}
                        </dl>
                    {/if}
                </div>
            {/each}
        </section>
    {/if}

    {#if transferGaps.length}
        <section class="panel">
            <header class="panel-head"><h2>Transfer gaps</h2>
                <span class="src">recall − application</span></header>
            <table>
                <thead>
                    <tr><th>Topic</th><th>Recall</th><th>Application</th><th>Gap</th></tr>
                </thead>
                <tbody>
                    {#each transferGaps as g (g.topicKey)}
                        <tr>
                            <td>{g.topicName}</td>
                            <td>{pct(g.memoryRecall * 100)}</td>
                            <td>{pct(g.performanceAccuracy * 100)}</td>
                            <td class:pos={g.gap > 0.15}>{pct(g.gap * 100)}</td>
                        </tr>
                    {/each}
                </tbody>
            </table>
        </section>
    {/if}

    {#if pacing.length}
        <section class="panel">
            <header class="panel-head"><h2>Pacing</h2>
                <span class="src">timed review</span></header>
            <table>
                <thead>
                    <tr><th>Topic</th><th>Target</th><th>Actual avg</th><th>Overtime</th></tr>
                </thead>
                <tbody>
                    {#each pacing as p (p.name)}
                        <tr>
                            <td>{p.name}</td>
                            <td>{one(p.target)}s</td>
                            <td class:slow={p.actual > p.target}>{one(p.actual)}s</td>
                            <td class:slow={p.overtime > 50}>{pct(p.overtime)}</td>
                        </tr>
                    {/each}
                </tbody>
            </table>
        </section>
    {/if}

    <section class="panel session">
        <header class="panel-head"><h2>Timed interleaved session</h2></header>
        <label class="toggle">
            <input type="checkbox" bind:checked={interleave} />
            Interleave topics (off = blocked practice)
        </label>
        <div class="session-actions">
            <button on:click={buildSession} disabled={building}>Build session</button>
            {#if inDesktopShell}
                <button
                    class="start"
                    on:click={startSession}
                    disabled={building || !session || session.cardIds.length === 0}
                    title="Open these cards in Anki's reviewer via a filtered deck"
                >
                    Start session in Anki
                </button>
            {/if}
        </div>
        {#if session}
            <p class="log">
                <strong>{session.cardIds.length}</strong> cards
                <span class="dot">•</span>
                target ~{Math.round(sessionTargetSecs / 60)} min
                <span class="dot">•</span>
                <span class="mode" class:interleaved={session.interleaved}>
                    {session.interleaved ? "interleaved" : "blocked"}
                </span>
            </p>
            <ol class="order">
                {#each sessionItems as item, i (i)}
                    <li>
                        <span class="idx">{i + 1}</span>
                        <span
                            class="chip"
                            style="--chip:{hueOf(item.sectionKey)}"
                            title={item.sectionName || item.sectionKey}
                        >
                            {shortSection(item.sectionKey, item.sectionName)}
                        </span>
                        <span class="topic">{item.topicName}</span>
                    </li>
                {/each}
            </ol>
        {/if}
    </section>

    {#if xp}
        <footer class="xp">
            <span>Level {xp.level}</span>
            <span>{xp.totalXp} XP</span>
            <span>{xp.streakDays}-day streak</span>
            <span>+{xp.xpToday} today</span>
            {#each xp.badges as badge (badge)}
                <span class="badge">{badge}</span>
            {/each}
        </footer>
    {/if}
</div>

<style lang="scss">
    .mcat {
        max-width: 60em;
        margin: 0 auto;
        padding: 1.5rem 1.25rem 3rem;
        color: var(--mc-text);
        background: var(--mc-ink);
        font-family: var(--mc-font-body);
        font-size: 14px;
        line-height: 1.5;
    }

    /* --- Shared panel chrome (kept quiet) --- */
    .panel,
    .plan-panel,
    .vitals,
    .coverage-map,
    .support {
        margin-top: 1.15rem;
    }
    .panel-head {
        display: flex;
        align-items: baseline;
        justify-content: space-between;
        gap: 1rem;
        margin-bottom: 0.6rem;
    }
    .panel-head h2 {
        font-family: var(--mc-font-body);
        font-weight: 600;
        font-size: 0.95rem;
        letter-spacing: 0.01em;
        margin: 0;
    }
    .src {
        font-family: var(--mc-font-mono);
        font-size: 0.68rem;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        color: var(--mc-muted);
    }
    .src.ai {
        color: var(--mc-ready);
    }

    /* ===================== Calibration Gauge (signature) ===================== */
    .gauge-panel {
        border: 1px solid var(--mc-hairline);
        border-radius: 14px;
        padding: 1.5rem 1.5rem 1.25rem;
        background:
            radial-gradient(
                120% 140% at 15% 0%,
                var(--mc-panel-2),
                var(--mc-panel) 60%
            );
    }
    .gauge-top {
        display: flex;
        justify-content: space-between;
        align-items: flex-start;
        gap: 1.5rem;
        flex-wrap: wrap;
    }
    .eyebrow {
        font-family: var(--mc-font-mono);
        font-size: 0.72rem;
        text-transform: uppercase;
        letter-spacing: 0.16em;
        color: var(--mc-muted);
    }
    .readout {
        display: flex;
        align-items: baseline;
        gap: 0.7rem;
        margin-top: 0.1rem;
    }
    .score {
        font-family: var(--mc-font-display);
        font-weight: 700;
        font-size: 4.25rem;
        line-height: 0.95;
        letter-spacing: 0.01em;
        font-variant-numeric: tabular-nums;
        font-feature-settings: "tnum" 1;
    }
    .score.ready {
        color: var(--mc-ready);
    }
    .score.warn {
        color: var(--mc-warn);
    }
    .score.muted {
        color: var(--mc-muted);
        letter-spacing: 0.1em;
    }
    .range {
        font-family: var(--mc-font-mono);
        font-size: 0.78rem;
        color: var(--mc-muted);
        letter-spacing: 0.04em;
    }
    .unlock {
        margin: 0.35rem 0 0;
        font-size: 0.85rem;
        color: var(--mc-muted);
    }
    .unlock.live {
        color: var(--mc-ready);
        font-weight: 600;
    }

    .gauge-side {
        display: flex;
        flex-direction: column;
        align-items: flex-end;
        gap: 0.55rem;
    }
    .vital {
        display: inline-flex;
        align-items: center;
        gap: 0.45rem;
        border: 1px solid var(--mc-hairline);
        border-radius: 999px;
        padding: 0.28rem 0.7rem;
        background: transparent;
        color: var(--mc-muted);
        font-family: var(--mc-font-mono);
        font-size: 0.72rem;
        letter-spacing: 0.04em;
        cursor: default;
    }
    .vital:not(:disabled) {
        cursor: pointer;
        color: var(--mc-text);
    }
    .vital .dot {
        width: 8px;
        height: 8px;
        border-radius: 50%;
        background: var(--mc-muted);
        box-shadow: 0 0 0 3px color-mix(in srgb, var(--mc-muted) 25%, transparent);
    }
    .vital.on .dot {
        background: var(--mc-ready);
        box-shadow: 0 0 0 3px color-mix(in srgb, var(--mc-ready) 30%, transparent);
        animation: pulse 2.4s ease-in-out infinite;
    }
    @keyframes pulse {
        50% {
            box-shadow: 0 0 0 5px color-mix(in srgb, var(--mc-ready) 12%, transparent);
        }
    }
    .vital:not(:disabled):hover {
        border-color: var(--mc-ready);
    }

    .target-control {
        display: inline-flex;
        align-items: center;
        gap: 0.4rem;
        font-family: var(--mc-font-mono);
        font-size: 0.75rem;
        color: var(--mc-muted);
    }
    .tc-label {
        text-transform: uppercase;
        letter-spacing: 0.1em;
        font-size: 0.66rem;
    }
    .tc-value {
        font-family: var(--mc-font-mono);
        font-weight: 500;
        font-size: 0.85rem;
        color: var(--mc-warn);
        background: transparent;
        border: 1px dashed var(--mc-hairline);
        border-radius: 5px;
        padding: 0.05rem 0.4rem;
        cursor: pointer;
    }
    .tc-input {
        width: 3.6rem;
        font-family: var(--mc-font-mono);
        background: var(--mc-panel-2);
        color: var(--mc-text);
        border: 1px solid var(--mc-warn);
        border-radius: 5px;
        padding: 0.05rem 0.3rem;
    }
    .tc-steppers {
        display: inline-flex;
        flex-direction: column;
    }
    .tc-steppers button {
        line-height: 1;
        width: 1.25rem;
        height: 0.85rem;
        font-size: 0.7rem;
        border: 1px solid var(--mc-hairline);
        background: var(--mc-panel-2);
        color: var(--mc-muted);
        cursor: pointer;
    }
    .tc-steppers button:first-child {
        border-radius: 4px 4px 0 0;
    }
    .tc-steppers button:last-child {
        border-radius: 0 0 4px 4px;
        border-top: none;
    }
    .tc-steppers button:hover {
        color: var(--mc-text);
    }

    .gauge {
        position: relative;
        height: 46px;
        /* Room above for the target flag, below for percentile labels. */
        margin: 2.6rem 0 1.9rem;
        border-radius: 6px;
        background: linear-gradient(
            to bottom,
            transparent 44%,
            var(--mc-hairline) 44%,
            var(--mc-hairline) 56%,
            transparent 56%
        );
    }
    .ready-zone {
        position: absolute;
        top: 44%;
        height: 12%;
        background: color-mix(in srgb, var(--mc-ready) 22%, transparent);
        border-radius: 0 6px 6px 0;
    }
    .band {
        position: absolute;
        top: 34%;
        height: 32%;
        border-radius: 4px;
        opacity: 0.5;
    }
    .band.ready {
        background: color-mix(in srgb, var(--mc-ready) 60%, transparent);
    }
    .band.warn {
        background: color-mix(in srgb, var(--mc-warn) 55%, transparent);
    }
    /* Percentile reference ticks read BELOW the track... */
    .ptick {
        position: absolute;
        top: 44%;
        height: 26%;
        width: 1px;
        background: var(--mc-muted);
        opacity: 0.5;
    }
    .ptick-label {
        position: absolute;
        top: calc(100% + 2px);
        left: 50%;
        transform: translateX(-50%);
        font-family: var(--mc-font-mono);
        font-size: 0.6rem;
        color: var(--mc-muted);
        white-space: nowrap;
    }
    /* ...the user's target flag reads ABOVE it, so the two never collide even
       when the target sits on a percentile line. */
    .target-flag {
        position: absolute;
        top: -0.35rem;
        bottom: -0.35rem;
        z-index: 3;
    }
    .flag-pole {
        position: absolute;
        top: 0;
        bottom: 0;
        width: 2px;
        margin-left: -1px;
        background: var(--mc-warn);
        border-radius: 2px;
    }
    .flag {
        position: absolute;
        bottom: calc(100% + 1px);
        left: 50%;
        transform: translateX(-50%);
        font-family: var(--mc-font-mono);
        font-size: 0.62rem;
        font-weight: 500;
        color: #0e1622;
        background: var(--mc-warn);
        border-radius: 3px;
        padding: 0.03rem 0.3rem;
        white-space: nowrap;
    }
    .flag::after {
        content: "";
        position: absolute;
        top: 100%;
        left: 50%;
        transform: translateX(-50%);
        border: 3px solid transparent;
        border-top-color: var(--mc-warn);
    }
    .needle {
        position: absolute;
        top: 50%;
        z-index: 4;
        transition: left 1100ms cubic-bezier(0.22, 1, 0.36, 1);
    }
    /* Precise instrument marker: a thin stem crossing the scale with a dot at
       the reading point. */
    .needle::before {
        content: "";
        position: absolute;
        top: -18px;
        left: -1px;
        width: 2px;
        height: 36px;
        background: var(--mc-needle);
        border-radius: 2px;
    }
    .needle::after {
        content: "";
        position: absolute;
        top: -6px;
        left: -6px;
        width: 12px;
        height: 12px;
        border-radius: 50%;
        background: var(--mc-needle);
        border: 2px solid var(--mc-panel);
    }
    .needle.ready::before,
    .needle.ready::after {
        background: var(--mc-ready);
    }
    .needle.ready::after {
        box-shadow: 0 0 10px color-mix(in srgb, var(--mc-ready) 65%, transparent);
    }
    .needle.warn::before,
    .needle.warn::after {
        background: var(--mc-warn);
    }
    .needle.warn::after {
        box-shadow: 0 0 10px color-mix(in srgb, var(--mc-warn) 60%, transparent);
    }
    @media (prefers-reduced-motion: reduce) {
        .needle {
            transition: none;
        }
        .vital.on .dot {
            animation: none;
        }
    }
    .scale-ends {
        display: flex;
        justify-content: space-between;
        margin-top: 0.6rem;
        font-family: var(--mc-font-mono);
        font-size: 0.72rem;
        color: var(--mc-muted);
    }
    .scale-caption {
        text-transform: uppercase;
        letter-spacing: 0.12em;
        font-size: 0.62rem;
    }
    .gauge-meta {
        display: flex;
        align-items: center;
        gap: 0.85rem;
        margin-top: 1rem;
        padding-top: 0.8rem;
        border-top: 1px solid var(--mc-hairline);
        font-family: var(--mc-font-mono);
        font-size: 0.78rem;
        color: var(--mc-muted);
    }
    .gauge-meta b {
        color: var(--mc-text);
        font-weight: 500;
    }
    .gauge-meta .sep {
        width: 1px;
        height: 0.9rem;
        background: var(--mc-hairline);
    }

    /* ===================== Plan (primary CTA) ===================== */
    .plan-panel {
        border: 1px solid var(--mc-hairline);
        border-radius: 12px;
        padding: 1.15rem 1.25rem;
        background: var(--mc-panel);
    }
    .plan-summary {
        margin: 0 0 0.75rem;
        color: var(--mc-muted);
    }
    .plan {
        list-style: none;
        margin: 0;
        padding: 0;
        display: flex;
        flex-direction: column;
    }
    .plan > li {
        display: flex;
        gap: 0.9rem;
        padding: 0.7rem 0;
        border-top: 1px solid var(--mc-hairline);
    }
    .plan > li:first-child {
        border-top: none;
    }
    .step-min {
        flex: none;
        width: 3.1rem;
        text-align: right;
        font-family: var(--mc-font-display);
        font-weight: 500;
        font-size: 1.35rem;
        font-variant-numeric: tabular-nums;
        color: var(--mc-text);
    }
    .step-min small {
        display: block;
        font-family: var(--mc-font-mono);
        font-size: 0.58rem;
        text-transform: uppercase;
        letter-spacing: 0.1em;
        color: var(--mc-muted);
    }
    .step-body {
        flex: 1;
        min-width: 0;
    }
    .step-action {
        font-weight: 600;
    }
    .step-reason {
        margin: 0.2rem 0 0;
        font-size: 0.88rem;
        color: var(--mc-muted);
    }
    .step-evidence {
        margin-top: 0.35rem;
        font-size: 0.82rem;
        color: var(--mc-muted);
    }
    .step-evidence summary {
        cursor: pointer;
        font-family: var(--mc-font-mono);
        font-size: 0.68rem;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        color: var(--mc-chemphys);
    }
    .step-evidence ul,
    .evidence ul {
        margin: 0.35rem 0 0;
        padding-left: 1.1rem;
    }
    .cta {
        display: flex;
        flex-wrap: wrap;
        gap: 0.6rem;
        margin-top: 1rem;
    }
    .cta button {
        padding: 0.65rem 1.3rem;
        border-radius: 8px;
        font-family: var(--mc-font-body);
        font-size: 0.95rem;
        font-weight: 600;
        cursor: pointer;
        border: 1px solid var(--mc-hairline);
    }
    .cta-primary {
        background: var(--mc-ready);
        color: #06231a;
        border-color: transparent;
    }
    .cta-primary:hover {
        filter: brightness(1.08);
    }
    .cta-secondary {
        background: transparent;
        color: var(--mc-text);
    }
    .cta-secondary:hover {
        border-color: var(--mc-muted);
    }
    .evidence {
        margin-top: 0.75rem;
        font-size: 0.85rem;
        color: var(--mc-muted);
    }
    .evidence summary {
        cursor: pointer;
        font-family: var(--mc-font-mono);
        font-size: 0.68rem;
        text-transform: uppercase;
        letter-spacing: 0.08em;
    }
    .ai-note {
        margin: 0.75rem 0 0;
        font-size: 0.82rem;
        color: var(--mc-muted);
        font-style: italic;
    }

    /* ===================== Section vitals ===================== */
    .vital-strip {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(9rem, 1fr));
        gap: 0.7rem;
    }
    .mini {
        text-align: left;
        border: 1px solid var(--mc-hairline);
        border-top: 3px solid var(--hue);
        border-radius: 10px;
        padding: 0.7rem 0.8rem;
        background: var(--mc-panel);
        cursor: pointer;
        display: flex;
        flex-direction: column;
        gap: 0.3rem;
    }
    .mini:hover,
    .mini.selected {
        background: var(--mc-panel-2);
        box-shadow: 0 0 0 1px var(--hue);
    }
    .mini-name {
        font-family: var(--mc-font-mono);
        font-size: 0.7rem;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        color: var(--mc-muted);
    }
    .mini-score {
        font-family: var(--mc-font-display);
        font-weight: 700;
        font-size: 1.8rem;
        line-height: 1;
        font-variant-numeric: tabular-nums;
        color: var(--hue);
    }
    .mini-score.muted {
        color: var(--mc-muted);
    }
    .mini-gauge {
        position: relative;
        height: 5px;
        border-radius: 3px;
        background: var(--mc-hairline);
        margin: 0.15rem 0;
    }
    .mini-gauge.empty {
        opacity: 0.5;
    }
    .mini-band {
        position: absolute;
        top: 0;
        height: 100%;
        border-radius: 3px;
        background: var(--hue);
        opacity: 0.4;
    }
    .mini-needle {
        position: absolute;
        top: -2px;
        width: 3px;
        height: 9px;
        margin-left: -1.5px;
        border-radius: 2px;
        background: var(--hue);
    }
    .mini-sub {
        font-family: var(--mc-font-mono);
        font-size: 0.68rem;
        color: var(--mc-muted);
    }

    /* ===================== Coverage map ===================== */
    .cov-section {
        border-left: 3px solid var(--hue);
        padding: 0.35rem 0 0.5rem 0.8rem;
        margin-bottom: 0.7rem;
    }
    .cov-head {
        display: flex;
        justify-content: space-between;
        align-items: baseline;
        gap: 1rem;
        margin-bottom: 0.35rem;
    }
    .cov-name {
        font-weight: 600;
        color: var(--hue);
    }
    .cov-stat {
        font-family: var(--mc-font-mono);
        font-size: 0.72rem;
        color: var(--mc-muted);
    }
    .cov-topics {
        list-style: none;
        margin: 0;
        padding: 0;
    }
    .cov-topics li {
        display: grid;
        grid-template-columns: minmax(6rem, 14rem) 1fr 2.6rem;
        align-items: center;
        gap: 0.7rem;
        padding: 0.18rem 0;
    }
    .cov-topics li.dim {
        opacity: 0.5;
    }
    .cov-topic {
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
        font-size: 0.88rem;
    }
    .cov-bar {
        height: 6px;
        border-radius: 3px;
        background: var(--mc-hairline);
        overflow: hidden;
    }
    .cov-fill {
        height: 100%;
        background: var(--hue);
        border-radius: 3px;
    }
    .cov-pct {
        font-family: var(--mc-font-mono);
        font-size: 0.72rem;
        text-align: right;
        color: var(--mc-muted);
        font-variant-numeric: tabular-nums;
    }
    .chip-clear {
        font-family: var(--mc-font-mono);
        font-size: 0.68rem;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        color: var(--mc-chemphys);
        background: transparent;
        border: 1px solid var(--mc-hairline);
        border-radius: 999px;
        padding: 0.15rem 0.6rem;
        cursor: pointer;
    }
    .chip-clear:hover {
        border-color: var(--mc-chemphys);
    }

    /* ===================== Support readouts ===================== */
    .support {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(15rem, 1fr));
        gap: 0.8rem;
    }
    .readout-card {
        border: 1px solid var(--mc-hairline);
        border-radius: 10px;
        padding: 0.9rem 1rem;
        background: var(--mc-panel);
    }
    .readout-card.abstain {
        opacity: 0.85;
    }
    .rc-label {
        font-family: var(--mc-font-mono);
        font-size: 0.7rem;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        color: var(--mc-muted);
        display: block;
    }
    .rc-score {
        font-family: var(--mc-font-display);
        font-weight: 700;
        font-size: 2.2rem;
        line-height: 1.1;
        font-variant-numeric: tabular-nums;
    }
    .rc-score.muted {
        color: var(--mc-muted);
    }
    .rc-range {
        display: block;
        font-family: var(--mc-font-mono);
        font-size: 0.74rem;
        color: var(--mc-muted);
    }
    .conf {
        text-transform: uppercase;
        letter-spacing: 0.04em;
    }
    .conf-high {
        color: var(--mc-ready);
    }
    .conf-medium {
        color: var(--mc-warn);
    }
    .conf-low {
        color: var(--mc-cars);
    }
    .stats {
        display: grid;
        grid-template-columns: auto 1fr;
        gap: 0.12rem 0.6rem;
        margin: 0.7rem 0 0;
        padding-top: 0.6rem;
        border-top: 1px solid var(--mc-hairline);
        font-size: 0.82rem;
    }
    .stats dt {
        color: var(--mc-muted);
    }
    .stats dd {
        margin: 0;
        text-align: right;
        font-family: var(--mc-font-mono);
        font-variant-numeric: tabular-nums;
    }
    .stats dd.met {
        color: var(--mc-ready);
    }
    .stats dd.slow {
        color: var(--mc-warn);
    }

    /* ===================== Quiet tables ===================== */
    table {
        width: 100%;
        border-collapse: collapse;
    }
    th,
    td {
        text-align: left;
        padding: 0.32rem 0.5rem;
        border-bottom: 1px solid var(--mc-hairline);
        font-size: 0.86rem;
    }
    th {
        font-family: var(--mc-font-mono);
        font-size: 0.68rem;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        color: var(--mc-muted);
        font-weight: 500;
    }
    td {
        font-variant-numeric: tabular-nums;
    }
    td.pos,
    td.slow {
        color: var(--mc-warn);
        font-weight: 600;
    }

    /* ===================== Session ===================== */
    .toggle {
        display: block;
        margin: 0.35rem 0 0.6rem;
        color: var(--mc-muted);
        font-size: 0.88rem;
    }
    .session-actions {
        display: flex;
        flex-wrap: wrap;
        gap: 0.5rem;
    }
    .session button {
        padding: 0.4rem 0.9rem;
        border: 1px solid var(--mc-hairline);
        border-radius: 7px;
        background: transparent;
        color: var(--mc-text);
        font-family: var(--mc-font-body);
        cursor: pointer;
    }
    .session button:hover:not(:disabled) {
        border-color: var(--mc-muted);
    }
    .session button:disabled {
        opacity: 0.55;
        cursor: default;
    }
    .session-actions .start {
        background: var(--mc-chemphys);
        color: #04122e;
        border-color: transparent;
        font-weight: 600;
    }
    .log {
        display: flex;
        flex-wrap: wrap;
        align-items: baseline;
        gap: 0.4rem;
        margin: 0.75rem 0;
        color: var(--mc-muted);
        font-family: var(--mc-font-mono);
        font-size: 0.82rem;
    }
    .log strong {
        color: var(--mc-text);
    }
    .log .dot {
        opacity: 0.5;
    }
    .mode {
        border-radius: 999px;
        padding: 0.05rem 0.5rem;
        font-size: 0.8em;
        background: var(--mc-hairline);
        color: var(--mc-muted);
    }
    .mode.interleaved {
        background: color-mix(in srgb, var(--mc-ready) 25%, transparent);
        color: var(--mc-ready);
    }
    .order {
        list-style: none;
        margin: 0.5rem 0 0;
        padding: 0;
        font-size: 0.88rem;
    }
    .order li {
        display: flex;
        align-items: baseline;
        gap: 0.55rem;
        padding: 0.15rem 0;
        border-bottom: 1px solid var(--mc-hairline);
    }
    .order li:last-child {
        border-bottom: none;
    }
    .order .idx {
        flex: none;
        color: var(--mc-muted);
        font-family: var(--mc-font-mono);
        min-width: 1.6em;
        text-align: right;
        font-size: 0.8em;
    }
    .order .chip {
        flex: none;
        width: 6.5em;
        text-align: center;
        border-radius: 999px;
        padding: 0.05rem 0.4rem;
        font-family: var(--mc-font-mono);
        font-size: 0.7em;
        font-weight: 500;
        color: #0a0f16;
        background: var(--chip, var(--mc-muted));
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }
    .order .topic {
        flex: 1;
        min-width: 0;
        overflow-wrap: anywhere;
    }

    /* ===================== XP footer ===================== */
    .xp {
        display: flex;
        flex-wrap: wrap;
        gap: 0.75rem;
        align-items: center;
        margin-top: 1.5rem;
        border-top: 1px solid var(--mc-hairline);
        padding-top: 1rem;
        color: var(--mc-muted);
        font-family: var(--mc-font-mono);
        font-size: 0.8rem;
    }
    .badge {
        background: var(--mc-chemphys);
        color: #04122e;
        border-radius: 999px;
        padding: 0.1rem 0.6rem;
        font-size: 0.8em;
    }

    /* Visible keyboard focus everywhere. */
    button:focus-visible,
    input:focus-visible,
    summary:focus-visible {
        outline: 2px solid var(--mc-chemphys);
        outline-offset: 2px;
    }

    @media (max-width: 640px) {
        .score {
            font-size: 3.1rem;
        }
        .gauge-side {
            align-items: flex-start;
        }
        .cov-topics li {
            grid-template-columns: minmax(5rem, 1fr) 1fr 2.4rem;
        }
    }
</style>
