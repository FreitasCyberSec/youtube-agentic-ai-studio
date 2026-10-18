"""Offline tests for public YouTube opportunity signals."""
from datetime import datetime, timezone

from apis import youtube_opportunities as opportunities


def test_missing_key_does_not_call_api():
    def fail(*args, **kwargs):
        raise AssertionError("network must not be called without a key")
    result = opportunities.collect_topic_signals([{"topic": "space"}], api_key="", request=fail)
    assert result["available"] is False
    assert result["reason"] == "missing_api_key"


def test_parse_published_handles_bad_dates():
    assert opportunities._parse_published("not-a-date") is None
    age = opportunities._parse_published(
        "2026-10-17T00:00:00Z",
        now=datetime(2026, 10, 18, tzinfo=timezone.utc),
    )
    assert 0.99 <= age <= 1.01


def test_collects_views_and_compares_candidates():
    calls = []
    def fake_request(url, params, timeout=12):
        calls.append(url)
        if url.endswith("/search"):
            return {"items": [{"id": {"videoId": params["q"] + "-1"}}]}
        topic = params["id"].split("-")[0]
        views = 10000 if topic == "popular" else 100
        return {"items": [{
            "id": params["id"],
            "snippet": {"title": topic, "publishedAt": "2026-10-17T00:00:00Z"},
            "statistics": {"viewCount": str(views)},
        }]}
    result = opportunities.collect_topic_signals(
        [{"topic": "popular"}, {"topic": "niche"}],
        api_key="test-key", request=fake_request,
    )
    assert result["available"] is True
    assert len(result["candidates"]) == 2
    assert result["candidates"][0]["median_views_per_day"] > result["candidates"][1]["median_views_per_day"]
    assert result["candidates"][0]["opportunity_score"] == 100.0
    assert result["candidates"][1]["opportunity_score"] == 0.0


def test_api_error_is_isolated_to_candidate():
    def fail(*args, **kwargs):
        raise RuntimeError("quota")
    result = opportunities.collect_topic_signals(
        [{"topic": "space"}], api_key="test-key", request=fail
    )
    assert result["available"] is True
    assert result["candidates"][0]["status"] == "error"
    assert result["candidates"][0]["opportunity_score"] is None
