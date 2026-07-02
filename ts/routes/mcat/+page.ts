// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
import { getExamReadiness, getTopicMastery, getTopicTargets } from "@generated/backend";

import type { PageLoad } from "./$types";

export const load = (async () => {
    const req = { search: "", tagPrefix: "", defaultTargetSeconds: 0 };
    const [readiness, targets, mastery] = await Promise.all([
        getExamReadiness(req),
        getTopicTargets(req),
        getTopicMastery(req),
    ]);
    return { readiness, targets, mastery };
}) satisfies PageLoad;
