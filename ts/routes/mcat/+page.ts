// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
import { getAiStatus, getAiStudyPlan, getExamReadiness, getTopicMastery, getTopicTargets } from "@generated/backend";

import type { PageLoad } from "./$types";

export const load = (async () => {
    const req = { search: "", tagPrefix: "", defaultTargetSeconds: 0 };
    // The AI status/plan RPCs are gated and always return a typed result (with a
    // deterministic fallback plan), so they never break the dashboard when AI is
    // off/offline/erroring.
    const [readiness, targets, mastery, aiStatus, aiPlan] = await Promise.all([
        getExamReadiness(req),
        getTopicTargets(req),
        getTopicMastery(req),
        getAiStatus({ tagPrefix: "" }),
        getAiStudyPlan(req),
    ]);
    return { readiness, targets, mastery, aiStatus, aiPlan };
}) satisfies PageLoad;
