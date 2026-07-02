<!--
Copyright: Ankitects Pty Ltd and contributors
License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
-->
<script lang="ts">
    import type { PageData } from "./$types";
    import MCATDashboard from "./MCATDashboard.svelte";

    export let data: PageData;
</script>

<MCATDashboard
    readiness={data.readiness}
    targets={data.targets}
    mastery={data.mastery}
    aiStatus={data.aiStatus}
    aiPlan={data.aiPlan}
/>
