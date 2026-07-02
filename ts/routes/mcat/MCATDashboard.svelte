<!--
Copyright: Ankitects Pty Ltd and contributors
License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
-->
<script lang="ts">
    import type {
        ExamReadiness,
        InterleavedSession,
        ScoreEstimate,
        TopicMasteryList,
        TopicTargetList,
    } from "@generated/anki/mcat_pb";
    import { buildInterleavedSession } from "@generated/backend";
    import { bridgeCommand, bridgeCommandsAvailable } from "@tslib/bridgecommand";

    export let readiness: ExamReadiness;
    export let targets: TopicTargetList;
    export let mastery: TopicMasteryList;

    // Only meaningful when hosted inside the desktop main window (the MCAT home
    // state). In dev/preview there is no Qt bridge, so hide the buttons.
    const inDesktopShell = bridgeCommandsAvailable();
    const study = (): void => bridgeCommand("study");
    const openDecks = (): void => bridgeCommand("decks");

    const pct = (n: number): string => `${Math.round(n)}%`;
    const one = (n: number): string => n.toFixed(1);

    // --- Pacing (timed review): target vs. actual, per covered topic ---
    interface Pace {
        name: string;
        target: number;
        actual: number;
        overtime: number;
    }
    $: masteryByKey = new Map(mastery.topics.map((t) => [t.topicKey, t]));
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

    // --- Timed interleaved session builder (the study feature under test) ---
    let interleave = true;
    let session: InterleavedSession | null = null;
    let building = false;
    const targetByKey = new Map(targets.targets.map((t) => [t.topicKey, t]));
    async function buildSession(): Promise<void> {
        building = true;
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
    $: sessionTargetSecs = session
        ? session.topicKeys.reduce(
              (sum, k) => sum + (targetByKey.get(k)?.targetSeconds ?? 0),
              0,
          )
        : 0;

    function barLeft(est: ScoreEstimate): number {
        const range = est.scaleMax - est.scaleMin || 1;
        return ((est.low - est.scaleMin) / range) * 100;
    }
    function barWidth(est: ScoreEstimate): number {
        const range = est.scaleMax - est.scaleMin || 1;
        return ((est.high - est.low) / range) * 100;
    }
    function pointLeft(est: ScoreEstimate): number {
        const range = est.scaleMax - est.scaleMin || 1;
        return ((est.point - est.scaleMin) / range) * 100;
    }

    $: scores = [readiness.readiness, readiness.memory, readiness.performance].filter(
        (s): s is ScoreEstimate => !!s,
    );
    $: recommendation = readiness.recommendation;
    $: xp = readiness.xp;
    $: giveUpRule = readiness.giveUpRule;
    $: transferGaps = readiness.transferGaps ?? [];
    $: memoryDetail = readiness.memoryDetail;
    $: performanceDetail = readiness.performanceDetail;
    $: readinessDetail = readiness.readinessDetail;
</script>

<div class="mcat">
    <header>
        <h1>{readiness.exam} Readiness</h1>
        <div class="meta">
            <span>Coverage {pct(readiness.overallCoveragePercent)}</span>
            <span>•</span>
            <span>{readiness.gradedReviews} graded reviews</span>
        </div>
        {#if giveUpRule}
            <p class="rule">{giveUpRule.description}</p>
        {/if}
        {#if inDesktopShell}
            <div class="cta">
                <button class="cta-primary" on:click={study}>
                    Start studying
                    {#if recommendation && recommendation.available}
                        · {recommendation.topicName}
                    {/if}
                </button>
                <button class="cta-secondary" on:click={openDecks}>Browse decks</button>
            </div>
        {/if}
    </header>

    <section class="cards">
        {#each scores as est (est.label)}
            <div class="card" class:abstain={!est.available}>
                <h2>{est.label}</h2>
                {#if est.available}
                    <div class="point">{Math.round(est.point)}</div>
                    <div class="rangetext">
                        {Math.round(est.low)}–{Math.round(est.high)}
                        <span class="conf conf-{est.confidence}">
                            {est.confidence} confidence
                        </span>
                    </div>
                    <div class="scale">
                        <div
                            class="band"
                            style="left:{barLeft(est)}%;width:{barWidth(est)}%"
                        ></div>
                        <div class="marker" style="left:{pointLeft(est)}%"></div>
                    </div>
                    <div class="scaleends">
                        <span>{est.scaleMin}</span>
                        <span>{est.scaleMax}</span>
                    </div>
                    <div class="coverage">Coverage {pct(est.coveragePercent)}</div>
                    <ul class="reasons">
                        {#each est.reasons as reason (reason)}
                            <li>{reason}</li>
                        {/each}
                    </ul>
                {:else}
                    <div class="nodata">No score yet</div>
                    <p class="why">{est.abstainReason}</p>
                    <div class="coverage">Coverage {pct(est.coveragePercent)}</div>
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
                        <dt>Graded reviews</dt>
                        <dd>{memoryDetail.gradedReviews}</dd>
                        <dt>Mature / young</dt>
                        <dd>{memoryDetail.matureCards} / {memoryDetail.youngCards}</dd>
                        <dt>Breadth</dt>
                        <dd>
                            {memoryDetail.coveredTopics} / {memoryDetail.totalTopics} topics
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
                            <dt>Correct</dt>
                            <dd>
                                {performanceDetail.correct} / {performanceDetail.questionsAnswered}
                            </dd>
                        {/if}
                        <dt>Topics covered</dt>
                        <dd>
                            {performanceDetail.coveredTopics} / {performanceDetail.totalTopics}
                        </dd>
                    </dl>
                {:else if est.label === "Readiness" && readinessDetail}
                    <dl class="stats">
                        <dt>Graded reviews</dt>
                        <dd class:met={readinessDetail.gradedReviewsMet}>
                            {readinessDetail.gradedReviews} / {readinessDetail.requiredGradedReviews}
                        </dd>
                        <dt>Coverage</dt>
                        <dd class:met={readinessDetail.coverageMet}>
                            {pct(readinessDetail.coveragePercent)} / {pct(
                                readinessDetail.requiredCoveragePercent,
                            )}
                        </dd>
                    </dl>
                {/if}
            </div>
        {/each}
    </section>

    {#if recommendation && recommendation.available}
        <section class="reco">
            <h2>Study next</h2>
            <p class="pick">{recommendation.topicName}</p>
            <p class="explain">{recommendation.explanation}</p>
            {#if recommendation.candidates.length}
                <table>
                    <thead>
                        <tr>
                            <th>Topic</th>
                            <th>Priority</th>
                            <th>Weight</th>
                            <th>Weakness</th>
                            <th>Due</th>
                        </tr>
                    </thead>
                    <tbody>
                        {#each recommendation.candidates as c (c.topicKey)}
                            <tr>
                                <td>{c.topicName}</td>
                                <td>{one(c.priorityScore)}</td>
                                <td>{c.examWeight}</td>
                                <td>{pct(c.weakness * 100)}</td>
                                <td>{c.dueCards}</td>
                            </tr>
                        {/each}
                    </tbody>
                </table>
            {/if}
        </section>
    {/if}

    {#if readiness.sections.length}
        <section class="sections">
            <h2>By section (memory)</h2>
            {#each readiness.sections as s (s.sectionKey)}
                <div class="srow">
                    <span class="sname">{s.sectionName}</span>
                    {#if s.available}
                        <span class="sscore">
                            {Math.round(s.point)} ({Math.round(s.low)}–{Math.round(
                                s.high,
                            )})
                        </span>
                        <span class="smem">mem {pct(s.memoryPercent)}</span>
                    {:else}
                        <span class="sscore muted">no data</span>
                        <span class="smem muted">—</span>
                    {/if}
                    <span class="scards">{s.cardsReviewed}/{s.cardsTotal} cards</span>
                    <span class="scov">cov {pct(s.coveragePercent)}</span>
                </div>
            {/each}
        </section>
    {/if}

    {#if transferGaps.length}
        <section class="transfer">
            <h2>Transfer gaps (recall − application)</h2>
            <table>
                <thead>
                    <tr>
                        <th>Topic</th>
                        <th>Recall</th>
                        <th>Application</th>
                        <th>Gap</th>
                    </tr>
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
        <section class="pacing">
            <h2>Pacing (timed review)</h2>
            <table>
                <thead>
                    <tr>
                        <th>Topic</th>
                        <th>Target</th>
                        <th>Actual avg</th>
                        <th>Overtime</th>
                    </tr>
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

    <section class="session">
        <h2>Timed interleaved session</h2>
        <label class="toggle">
            <input type="checkbox" bind:checked={interleave} />
            Interleave topics (off = blocked practice)
        </label>
        <button on:click={buildSession} disabled={building}>Build session</button>
        {#if session}
            <p class="log">
                {session.cardIds.length} cards • target ~{Math.round(
                    sessionTargetSecs / 60,
                )} min •
                {session.interleaved ? "interleaved" : "blocked"}
            </p>
            <ol class="order">
                {#each session.topicKeys as key, i (i)}
                    <li>{targetByKey.get(key)?.topicName ?? key}</li>
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
        max-width: 52em;
        margin: 0 auto;
        padding: 1.5rem;
        font-size: var(--font-size, 14px);
        color: var(--fg);
    }
    header h1 {
        margin-bottom: 0.25rem;
    }
    .meta {
        color: var(--fg-subtle);
        display: flex;
        gap: 0.5rem;
    }
    .rule {
        font-style: italic;
        color: var(--fg-subtle);
        margin-top: 0.25rem;
    }
    .cta {
        display: flex;
        flex-wrap: wrap;
        gap: 0.75rem;
        margin-top: 1rem;
    }
    .cta button {
        padding: 0.6rem 1.4rem;
        border-radius: var(--border-radius, 6px);
        font-size: 1rem;
        font-weight: 600;
        cursor: pointer;
        border: 1px solid var(--border);
    }
    .cta-primary {
        background: var(--fg-link, #3b82f6);
        color: #fff;
        border-color: transparent !important;
    }
    .cta-primary:hover {
        filter: brightness(1.08);
    }
    .cta-secondary {
        background: var(--canvas-elevated, var(--canvas));
        color: var(--fg);
    }
    .cards {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(14rem, 1fr));
        gap: 1rem;
        margin: 1rem 0;
    }
    .card {
        border: 1px solid var(--border);
        border-radius: var(--border-radius, 6px);
        padding: 1rem;
        background: var(--canvas-elevated, var(--canvas));
    }
    .card.abstain {
        opacity: 0.85;
    }
    .card h2 {
        margin: 0 0 0.5rem;
        font-size: 1rem;
    }
    .point {
        font-size: 2.5rem;
        font-weight: 700;
        line-height: 1;
    }
    .nodata {
        font-size: 1.4rem;
        font-weight: 600;
        color: var(--fg-subtle);
    }
    .why {
        color: var(--fg-subtle);
        margin: 0.25rem 0;
    }
    .rangetext {
        color: var(--fg-subtle);
        margin: 0.25rem 0 0.5rem;
    }
    .conf {
        margin-left: 0.4rem;
        font-size: 0.8em;
        text-transform: uppercase;
        letter-spacing: 0.03em;
    }
    .conf-high {
        color: var(--state-new, #2e7d32);
    }
    .conf-medium {
        color: var(--flag-2, #b8860b);
    }
    .conf-low {
        color: var(--flag-1, #c62828);
    }
    .scale {
        position: relative;
        height: 8px;
        background: var(--canvas-inset, var(--border));
        border-radius: 4px;
        margin: 0.25rem 0;
    }
    .band {
        position: absolute;
        top: 0;
        height: 100%;
        background: var(--fg-link, #3b82f6);
        opacity: 0.35;
        border-radius: 4px;
    }
    .marker {
        position: absolute;
        top: -2px;
        width: 3px;
        height: 12px;
        background: var(--fg-link, #3b82f6);
        border-radius: 2px;
    }
    .scaleends {
        display: flex;
        justify-content: space-between;
        font-size: 0.75em;
        color: var(--fg-subtle);
    }
    .coverage {
        margin-top: 0.5rem;
        font-size: 0.85em;
        color: var(--fg-subtle);
    }
    .reasons {
        margin: 0.5rem 0 0;
        padding-left: 1.1rem;
        font-size: 0.85em;
        color: var(--fg-subtle);
    }
    section {
        margin: 1.5rem 0;
    }
    .reco .pick {
        font-size: 1.3rem;
        font-weight: 600;
        margin: 0.25rem 0;
    }
    .explain {
        color: var(--fg-subtle);
    }
    table {
        width: 100%;
        border-collapse: collapse;
        margin-top: 0.5rem;
    }
    th,
    td {
        text-align: left;
        padding: 0.3rem 0.5rem;
        border-bottom: 1px solid var(--border);
        font-size: 0.9em;
    }
    td.pos {
        color: var(--flag-1, #c62828);
        font-weight: 600;
    }
    .srow {
        display: grid;
        grid-template-columns: 1fr auto auto auto auto;
        gap: 1rem;
        padding: 0.3rem 0;
        border-bottom: 1px solid var(--border);
    }
    .smem,
    .scards,
    .scov {
        color: var(--fg-subtle);
        font-size: 0.9em;
        white-space: nowrap;
    }
    .muted {
        color: var(--fg-subtle);
    }
    .stats {
        display: grid;
        grid-template-columns: auto 1fr;
        gap: 0.15rem 0.6rem;
        margin: 0.6rem 0 0;
        padding-top: 0.5rem;
        border-top: 1px solid var(--border);
        font-size: 0.85em;
    }
    .stats dt {
        color: var(--fg-subtle);
    }
    .stats dd {
        margin: 0;
        text-align: right;
        font-variant-numeric: tabular-nums;
    }
    .stats dd.met {
        color: var(--state-new, #2e7d32);
        font-weight: 600;
    }
    .xp {
        display: flex;
        flex-wrap: wrap;
        gap: 0.75rem;
        align-items: center;
        border-top: 1px solid var(--border);
        padding-top: 1rem;
        color: var(--fg-subtle);
    }
    .badge {
        background: var(--fg-link, #3b82f6);
        color: white;
        border-radius: 999px;
        padding: 0.1rem 0.6rem;
        font-size: 0.8em;
    }
    td.slow {
        color: var(--flag-1, #c62828);
        font-weight: 600;
    }
    .toggle {
        display: block;
        margin: 0.5rem 0;
    }
    .session button {
        padding: 0.35rem 0.9rem;
        border: 1px solid var(--border);
        border-radius: var(--border-radius, 6px);
        background: var(--canvas-elevated, var(--canvas));
        color: var(--fg);
        cursor: pointer;
    }
    .session button:disabled {
        opacity: 0.6;
        cursor: default;
    }
    .log {
        color: var(--fg-subtle);
        margin: 0.5rem 0;
    }
    .order {
        columns: 2;
        font-size: 0.9em;
        color: var(--fg-subtle);
    }
</style>
