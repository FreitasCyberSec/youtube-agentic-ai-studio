"""Offline tests for the deterministic topic scorer."""
from agents.topic_scorer import score_candidate, select_best_candidate


def _candidate(topic, title, hook, points=None):
    return {
        "topic": topic,
        "video_title": title,
        "hook_question": hook,
        "why_now": "A surprising new angle with concrete evidence",
        "description": "A concise description.",
        "key_points": points or ["First discovery", "Unexpected consequence", "What happens next"],
        "tags": ["science", "history"],
    }


def test_score_is_bounded_and_explained():
    result = score_candidate(_candidate(
        "Why ancient Roman concrete survived for 2000 years",
        "The Roman Concrete Secret That Still Baffles Engineers",
        "Why has this ancient concrete survived for 2000 years?"
    ), trend_context=["Roman concrete discovery", "ancient engineering"])
    assert 0 <= result["score"] <= 100
    assert set(result["components"]) == {
        "trend_relevance", "curiosity", "specificity_and_channel_fit",
        "title_quality", "narrative_depth", "novelty",
    }


def test_trend_relevance_improves_matching_candidate():
    candidate = _candidate(
        "New black hole discovery explained",
        "The Strange Black Hole Discovery",
        "What makes this black hole so strange?"
    )
    with_trends = score_candidate(candidate, ["black hole discovery astronomy"])
    without_trends = score_candidate(candidate, [])
    assert with_trends["components"]["trend_relevance"] > 0
    assert with_trends["score"] != without_trends["score"]


def test_select_best_candidate_returns_score_metadata():
    weak = _candidate("A general look at space", "Space is interesting", "What is space?")
    strong = _candidate(
        "Why a black hole can trap even light",
        "Why Nothing Escapes a Black Hole",
        "How can a black hole trap even light?"
    )
    selected = select_best_candidate(
        [weak, strong], trend_context=["black hole gravity light"],
        banned_topics=["The Boltzmann Brain"]
    )
    assert selected["topic"] == strong["topic"]
    assert selected["topic_candidates_evaluated"] == 2
    assert "topic_score_breakdown" in selected


def test_empty_candidates_falls_back_cleanly():
    assert select_best_candidate([]) is None
