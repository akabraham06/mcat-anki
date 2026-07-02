# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Integration test for the MCAT Anki Mastery topic-mastery query.

Exercises the new Rust backend change end-to-end from Python: notes are added
with MCAT topic tags, and the aggregation is computed by the Rust engine and
returned over protobuf.
"""

from tests.shared import getEmptyCol


def add_tagged(col, front, tags):
    note = col.newNote()
    note["Front"] = front
    note.tags = tags
    col.addNote(note)
    return note


def test_mcat_topic_mastery():
    col = getEmptyCol()

    add_tagged(col, "a", ["mcat::biobiochem::metabolism"])
    add_tagged(col, "b", ["mcat::biobiochem::metabolism"])
    add_tagged(col, "c", ["mcat::chemphys::electrochem"])
    add_tagged(col, "d", ["unrelated"])  # ignored - no mcat tag
    add_tagged(col, "e", ["mcat"])  # ignored - bare prefix, no topic

    res = col.mcat_topic_mastery()

    # Two topics, ignoring the untagged and bare-prefix notes.
    assert len(res.topics) == 2
    by_key = {t.topic_key: t for t in res.topics}
    metab = by_key["mcat::biobiochem::metabolism"]
    assert metab.section == "biobiochem"
    assert metab.topic_name == "metabolism"
    assert metab.cards_total == 2
    assert metab.cards_seen == 0
    assert metab.coverage_percent == 0.0

    # Distinct-card rollups count only the three MCAT-tagged cards.
    assert res.cards_total == 3
    assert res.cards_seen == 0
    assert res.overall_coverage_percent == 0.0

    # Review one metabolism card; coverage should reflect it.
    col.reset()
    card = col.sched.getCard()
    col.sched.answerCard(card, 3)

    res2 = col.mcat_topic_mastery()
    assert res2.cards_seen == 1
    assert res2.overall_coverage_percent > 0.0

    col.close()


def test_mcat_exam_readiness_and_recommender():
    col = getEmptyCol()

    add_tagged(col, "a", ["mcat::biobiochem::metabolism"])
    add_tagged(col, "b", ["mcat::biobiochem::metabolism"])
    add_tagged(col, "c", ["mcat::chemphys::stoichiometry"])

    readiness = col.mcat_exam_readiness()

    # The give-up rule is present and readiness abstains without enough data.
    assert readiness.give_up_rule.min_graded_reviews == 100
    assert not readiness.readiness.available
    assert readiness.readiness.abstain_reason
    # Memory abstains too (no reviews / memory state yet).
    assert not readiness.memory.available
    # Partial coverage of the whole taxonomy.
    assert 0.0 < readiness.overall_coverage_percent < 100.0

    # Recommender is deterministic and self-explaining; metabolism (weight 5,
    # two due cards) outranks stoichiometry (weight 2).
    rec = readiness.recommendation
    assert rec.available
    assert rec.topic_key == "mcat::biobiochem::metabolism"
    assert "Metabolism" in rec.explanation

    # Same result via the dedicated RPC.
    rec2 = col.mcat_study_recommendation()
    assert rec2.topic_key == rec.topic_key

    col.close()


def test_mcat_interleaving_and_targets():
    col = getEmptyCol()

    add_tagged(col, "m1", ["mcat::biobiochem::metabolism"])
    add_tagged(col, "m2", ["mcat::biobiochem::metabolism"])
    add_tagged(col, "s1", ["mcat::chemphys::stoichiometry"])
    add_tagged(col, "s2", ["mcat::chemphys::stoichiometry"])

    inter = col.mcat_interleaved_session(interleave=True)
    assert inter.interleaved
    assert len(inter.card_ids) == 4
    # Interleaved: adjacent cards are from different topics.
    assert inter.topic_keys[0] != inter.topic_keys[1]

    blocked = col.mcat_interleaved_session(interleave=False)
    assert not blocked.interleaved
    assert blocked.topic_keys[0] == blocked.topic_keys[1]

    # Topic targets expose per-topic pacing metadata from the taxonomy.
    targets = col.mcat_topic_targets()
    assert len(targets.targets) > 20
    metab = next(
        t for t in targets.targets if t.topic_key == "mcat::biobiochem::metabolism"
    )
    assert metab.target_seconds > 0
    assert metab.in_deck

    col.close()
