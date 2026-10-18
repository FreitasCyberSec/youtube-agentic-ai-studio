"""Offline tests for blending optional public YouTube signals into research."""
from agents import researcher


def _candidate(topic, title):
    return {
        "topic": topic,
        "video_title": title,
        "why_now": "A defensible topic with useful context",
        "description": "An explanation grounded in evidence.",
        "hook_question": "Why does this surprising thing happen?",
        "key_points": ["Mechanism", "Evidence", "Consequences", "Open questions"],
        "target_audience": "Curious science viewers",
        "tags": ["science", "explained"],
        "thumbnail_concept": "One clear visual contrast",
        "estimated_virality": "unknown",
    }


def _payload():
    a = _candidate("A broad topic about space", "Space explained simply")
    b = _candidate("Why black holes trap light", "Why Nothing Escapes a Black Hole")
    return {
        **a,
        "topic_candidates": [a, b],
    }


def test_missing_api_key_preserves_heuristic_selection(monkeypatch):
    monkeypatch.setattr(
        "apis.youtube_opportunities.collect_topic_signals",
        lambda candidates: {"available": False, "reason": "missing_api_key", "candidates": []},
    )
    result = researcher._select_topic(
        _payload(), ["black holes trap light"], [],
        "science, space and physics",
    )
    assert result["topic"] == "Why black holes trap light"
    assert result["topic_market_signals"]["available"] is False
    assert result["topic_score"] is not None


def test_public_signal_can_adjust_ranking_and_is_explained(monkeypatch):
    def fake_signals(candidates):
        return {
            "available": True,
            "reason": None,
            "metric": "relative_median_public_views_per_day",
            "limitations": ["relative sample"],
            "candidates": [
                {"topic": "A broad topic about space", "status": "ok",
                 "opportunity_score": 0.0, "median_views_per_day": 10,
                 "sample_size": 5},
                {"topic": "Why black holes trap light", "status": "ok",
                 "opportunity_score": 100.0, "median_views_per_day": 1000,
                 "sample_size": 5},
            ],
        }
    monkeypatch.setattr("apis.youtube_opportunities.collect_topic_signals", fake_signals)
    result = researcher._select_topic(
        _payload(), [], [],
        "science, space and physics",
    )
    assert result["topic"] == "Why black holes trap light"
    assert result["topic_market_signals"]["available"] is True
    assert result["topic_score_breakdown"]["public_youtube_opportunity"] == 100.0
    assert result["topic_score_breakdown"]["heuristic_score"] <= 100.0


def test_market_collector_exception_does_not_break_research(monkeypatch):
    def fail(candidates):
        raise RuntimeError("temporary API issue")
    monkeypatch.setattr("apis.youtube_opportunities.collect_topic_signals", fail)
    result = researcher._select_topic(_payload(), [], [], "science")
    assert result["topic"]
    assert result["topic_market_signals"]["available"] is False
    assert result["topic_market_signals"]["reason"] == "collector_error"
