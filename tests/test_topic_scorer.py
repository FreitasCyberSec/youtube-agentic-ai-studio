"""Offline tests for the deterministic topic scorer."""
from agents.topic_scorer import score_candidate, select_best_candidate


def _candidate(topic, title, hook, points=None):
    return {
        "topic": topic,
        "video_title": title,
        "hook_question": hook,
        "why_now": "A surprising new angle with concrete evidence",
        "description": "A concise description.",
        "key_points": points if points is not None else [
            "First discovery", "Unexpected consequence", "What happens next"
        ],
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


def test_relevant_single_trend_beats_unrelated_headlines():
    candidate = _candidate(
        "New black hole discovery explained",
        "The Strange Black Hole Discovery",
        "What makes this black hole so strange?"
    )
    relevant = score_candidate(candidate, ["black hole discovery astronomy"])
    unrelated = score_candidate(candidate, [
        "celebrity wedding", "football results", "weather forecast"
    ])
    assert relevant["components"]["trend_relevance"] > unrelated["components"]["trend_relevance"]


def test_no_trends_uses_neutral_signal():
    result = score_candidate(_candidate("A topic", "A useful title", "What happens?"), [])
    assert result["components"]["trend_relevance"] == 60.0


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


def test_covered_topics_reduce_novelty():
    candidate = _candidate(
        "Roman concrete survived for 2000 years",
        "Why Roman Concrete Lasts",
        "How does Roman concrete survive?"
    )
    fresh = score_candidate(candidate)
    repeated = score_candidate(candidate, banned_topics=["Roman concrete survived for 2000 years"])
    assert repeated["components"]["novelty"] < fresh["components"]["novelty"]


def test_portuguese_diacritics_and_string_key_points_are_safe():
    result = score_candidate({
        "topic": "Mistérios do oceano profundo",
        "video_title": "O segredo do oceano profundo",
        "hook_question": "O que existe no fundo do oceano?",
        "key_points": "Uma descoberta surpreendente",
    }, trend_context=["mistérios do oceano profundo"])
    assert 0 <= result["score"] <= 100
    assert result["components"]["trend_relevance"] > 0
    assert result["components"]["narrative_depth"] > 0


def test_invalid_candidate_inputs_fail_closed():
    assert select_best_candidate(None) is None
    assert select_best_candidate("not a list") is None
    assert select_best_candidate([None, {}, {"topic": ""}]) is None


def test_score_handles_missing_fields():
    result = score_candidate({})
    assert 0 <= result["score"] <= 100
    assert result["components"]["title_quality"] == 0.0
