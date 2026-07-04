#!/usr/bin/env python3
# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Zero-config live-AI smoke check for the desktop backend path.

Confirms that, with a CLEAN environment (no OPENAI_API_KEY / MCAT_AI_* and no
MCAT_AI_MOCK), the app resolves the built-in hosted proxy, reports the AI status
pill as *available*, and that a real feature (the 9.4 card-quality checker) gets
a genuine judgement back through the live proxy.

Run: PYTHONPATH=out/pylib:pylib out/pyenv/bin/python mcat/ai_eval/verify_live_ai.py
"""

from __future__ import annotations

import os
import sys
import tempfile

# Hard-guarantee a clean env so we exercise the built-in proxy default, not a
# stray developer key or the offline mock.
for key in (
    "OPENAI_API_KEY",
    "MCAT_AI_API_KEY",
    "MCAT_AI_BASE_URL",
    "MCAT_AI_MODEL",
    "MCAT_AI_MOCK",
):
    os.environ.pop(key, None)

from anki.collection import Collection  # noqa: E402

SOURCE_EXCERPT = (
    "Competitive inhibitors bind the active site and raise the apparent Km of an "
    "enzyme while leaving Vmax unchanged, because increasing substrate "
    "concentration can outcompete them."
)


def main() -> int:
    tmp = tempfile.mkdtemp(prefix="mcat_live_ai_")
    col = Collection(os.path.join(tmp, "c.anki2"))
    try:
        status = col.mcat_ai_status()
        print("=== AI status pill (zero config) ===")
        print(f"  available     : {status.available}")
        print(f"  configured    : {status.configured}")
        print(f"  enabled       : {status.enabled}")
        print(f"  provider      : {status.provider}")
        print(f"  model         : {status.model}")
        print(f"  checker_cutoff: {status.checker_cutoff}")
        print(f"  reason        : {status.reason}")

        assert status.available, "AI must be available via the built-in proxy"
        assert "netlify.app" in status.provider, "should resolve the built-in proxy"

        # A real, live judgement through the proxy: a strong, specific card.
        src = list(
            col.mcat_register_ai_source(
                source_name="Live Smoke — Enzyme Kinetics",
                excerpt=SOURCE_EXCERPT,
                source_section="smoke",
            )
        )
        source_id = src[-1].source_id
        report = col.mcat_check_card(
            question="How does a competitive inhibitor affect the apparent Km and Vmax of an enzyme?",
            answer=(
                "A competitive inhibitor raises the apparent Km while leaving Vmax "
                "unchanged, since excess substrate can outcompete it."
            ),
            topic_tag="mcat::biobiochem::enzymes",
            source_id=source_id,
            source_excerpt=SOURCE_EXCERPT,
        )
        print("\n=== Live 9.4 checker call through the proxy ===")
        print(f"  ai_available : {report.ai_available}")
        print(f"  verdict      : {report.verdict}")
        print(f"  overall_score: {report.overall_score:.3f}  (cutoff {report.cutoff:.2f})")
        for c in report.categories:
            mark = "PASS" if c.passed else "FAIL"
            print(f"    [{mark}] {c.key:<18} {c.score:.2f}  {c.reason}")

        assert report.ai_available, "checker must reach the live model"
        assert len(report.categories) == 9, "expected 6 AI + 3 deterministic categories"

        # Live source-grounded generation (9.3): a real batch from the proxy.
        gen = col.mcat_generate_cards(source_id=source_id, count=3)
        print("\n=== Live 9.3 generation through the proxy ===")
        print(f"  ai_available : {gen.ai_available}")
        print(f"  cards        : {len(gen.cards)}")
        for card in gen.cards:
            print(
                f"    [{card.difficulty:<7}] src='{card.source_name}' :: {card.question}"
            )
        assert gen.ai_available, "generation must reach the live model"
        assert gen.cards, "expected at least one generated candidate"
        assert all(c.source_name for c in gen.cards), "every card must name its source"

        print("\nLIVE AI OK: proxy available with zero user input; real checker + generation returned.")
        return 0
    finally:
        col.close()


if __name__ == "__main__":
    raise SystemExit(main())
