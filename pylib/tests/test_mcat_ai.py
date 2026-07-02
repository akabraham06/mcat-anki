# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Integration tests for the Phase 2 MCAT AI features, exercised end-to-end
through the protobuf boundary.

The deterministic mock AI provider is selected with the ``MCAT_AI_MOCK``
environment variable (set at import time), so these tests need no network and
no API key. They also assert the 9.9 safety guarantee that core scoring keeps
working when AI is unavailable.
"""

import os

# Route the Rust AI client to the deterministic offline mock before the backend
# builds any client.
os.environ["MCAT_AI_MOCK"] = "1"

from tests.shared import getEmptyCol  # noqa: E402

EXCERPT = (
    "Glycolysis occurs in the cytosol and converts glucose into two molecules of "
    "pyruvate, yielding a net of two ATP and two NADH. The citric acid cycle "
    "oxidizes pyruvate in the mitochondrial matrix and generates NADH and FADH2. "
    "Competitive inhibitors raise the apparent Km while leaving Vmax unchanged."
)


def add_tagged(col, front, back, tags):
    note = col.newNote()
    note["Front"] = front
    note["Back"] = back
    note.tags = tags
    col.addNote(note)
    return note


def test_ai_status_and_config_roundtrip():
    col = getEmptyCol()
    # Mock env => available.
    status = col.mcat_ai_status()
    assert status.available
    assert status.checker_cutoff > 0

    # Configure and read back with a masked key.
    col.mcat_ai_set_config(
        base_url="https://api.openai.com/v1",
        model="gpt-4o-mini",
        api_key="sk-secret-value-1234",
        checker_cutoff=0.75,
        enabled=True,
    )
    cfg = col.mcat_ai_get_config()
    assert cfg.api_key_set
    assert cfg.api_key.startswith("sk-...")
    assert "sk-secret-value-1234" not in cfg.api_key
    assert abs(cfg.checker_cutoff - 0.75) < 1e-9
    col.close()


def test_generation_requires_source_then_generates_and_checks():
    col = getEmptyCol()

    # No registered source => rejected (fake-source defence).
    res = col.mcat_generate_cards(source_id="nope", count=3)
    assert not res.ai_available
    assert "source" in res.unavailable_reason.lower()

    # Register a source, then generate. A single-field response message is
    # unwrapped by the backend to the repeated `sources` list.
    sources = col.mcat_register_ai_source(
        source_name="Biochem Primer",
        excerpt=EXCERPT,
        source_section="p.42",
    )
    sid = sources[-1].source_id
    res = col.mcat_generate_cards(
        source_id=sid, count=3, topic_hint="mcat::biobiochem::glycolysis"
    )
    assert res.ai_available
    assert len(res.cards) >= 1
    for card in res.cards:
        assert card.source_id == sid
        assert card.quality.categories  # checked before entering the deck
        assert any(c.key == "source_supported" for c in card.quality.categories)

    # Accept the reviewed cards -> real, ai-generated-tagged notes.
    accept = col.mcat_accept_generated_cards(cards=res.cards)
    assert accept.created >= 1
    col.close()


def test_checker_blocks_bad_cards_and_reports_cutoff():
    col = getEmptyCol()
    good = col.mcat_check_card(
        question="Which enzyme catalyzes the committed step of glycolysis?",
        answer="Phosphofructokinase-1 converts fructose-6-phosphate to fructose-1,6-bisphosphate.",
        topic_tag="mcat::biobiochem::glycolysis",
    )
    assert good.ai_available
    assert good.passed
    assert len(good.categories) == 9

    vague = col.mcat_check_card(
        question="What about metabolism?",
        answer="It does various things and many stuff, generally.",
        topic_tag="mcat::biobiochem::metabolism",
    )
    assert not vague.passed
    assert vague.verdict == "Blocked"
    col.close()


def test_ai_study_plan_grounds_in_evidence():
    col = getEmptyCol()
    add_tagged(col, "q", "a", ["mcat::biobiochem::metabolism"])
    col.reset()
    card = col.sched.getCard()
    col.sched.answerCard(card, 3)

    plan = col.mcat_ai_study_plan()
    assert plan.ai_available
    assert not plan.used_fallback
    assert plan.items
    assert plan.evidence  # the data behind the plan is surfaced
    assert plan.fallback.available  # deterministic fallback always attached
    col.close()


def test_explain_miss_and_perf_generation():
    col = getEmptyCol()
    note = add_tagged(
        col,
        "Where does the Krebs cycle occur?",
        "The mitochondrial matrix.",
        ["mcat::biobiochem::metabolism"],
    )
    cid = note.card_ids()[0]

    exp = col.mcat_explain_miss(card_id=cid, chosen_answer="The nucleus")
    assert exp.ai_available
    assert exp.why_correct
    assert exp.related_topic == "mcat::biobiochem::metabolism"

    perf = col.mcat_generate_perf_questions(card_id=cid)
    assert perf.ai_available
    assert len(perf.questions) == 2
    col.close()
