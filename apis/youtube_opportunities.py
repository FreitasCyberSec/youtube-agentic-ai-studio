"""Public YouTube search signals for topic opportunity research.

Uses the YouTube Data API v3 when a key is configured. Public view counts and
publication dates are weak demand signals, not estimates of future views.
"""
from datetime import datetime, timezone
import math

import config
from apis.http import get_json

_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
_VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"


def _parse_published(value, now=None):
    """Return non-negative age in days; malformed dates safely return None."""
    try:
        published = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if published.tzinfo is None:
            published = published.replace(tzinfo=timezone.utc)
        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None:
            current = current.replace(tzinfo=timezone.utc)
        return max(0.25, (current - published).total_seconds() / 86400)
    except (AttributeError, TypeError, ValueError):
        return None


def _get_candidate_videos(query, api_key, max_results=5, request=get_json):
    search = request(_SEARCH_URL, {
        "part": "snippet", "type": "video", "q": query,
        "maxResults": max(1, min(int(max_results), 10)),
        "order": "relevance", "key": api_key,
    }, timeout=12)
    ids = [
        item.get("id", {}).get("videoId")
        for item in search.get("items", [])
        if item.get("id", {}).get("videoId")
    ]
    if not ids:
        return []
    response = request(_VIDEOS_URL, {
        "part": "snippet,statistics", "id": ",".join(ids), "key": api_key,
    }, timeout=12)
    videos = []
    for item in response.get("items", []):
        stats = item.get("statistics") or {}
        snippet = item.get("snippet") or {}
        try:
            views = max(0, int(stats.get("viewCount", 0)))
        except (TypeError, ValueError):
            views = 0
        age_days = _parse_published(snippet.get("publishedAt"))
        if age_days is None:
            continue
        videos.append({
            "video_id": item.get("id", ""),
            "title": snippet.get("title", ""),
            "published_at": snippet.get("publishedAt", ""),
            "views": views,
            "age_days": round(age_days, 2),
            "views_per_day": round(views / age_days, 2),
        })
    return videos


def collect_topic_signals(candidates, api_key=None, max_results=5, request=get_json):
    """Collect public signals for candidate dicts, gracefully handling missing key/API errors.

    Result includes per-candidate sample size, median views/day and video details.
    No API key means an explicit unavailable result and no network request.
    """
    key = (api_key if api_key is not None else getattr(config, "YOUTUBE_API_KEY", "")).strip()
    valid = [c for c in candidates or [] if isinstance(c, dict) and str(c.get("topic", "")).strip()]
    if not key:
        return {"available": False, "reason": "missing_api_key", "candidates": []}
    results = []
    for candidate in valid:
        topic = str(candidate["topic"]).strip()
        try:
            videos = _get_candidate_videos(topic, key, max_results, request)
            rates = sorted(v["views_per_day"] for v in videos)
            if rates:
                mid = len(rates) // 2
                median_rate = rates[mid] if len(rates) % 2 else (rates[mid - 1] + rates[mid]) / 2
            else:
                median_rate = 0.0
            results.append({
                "topic": topic,
                "sample_size": len(videos),
                "median_views_per_day": round(median_rate, 2),
                "videos": videos,
                "status": "ok" if videos else "no_results",
            })
        except Exception as exc:
            results.append({
                "topic": topic, "sample_size": 0, "median_views_per_day": 0.0,
                "videos": [], "status": "error", "error": str(exc)[:200],
            })
    rates = [math.log1p(r["median_views_per_day"]) for r in results if r["sample_size"]]
    low, high = (min(rates), max(rates)) if rates else (0.0, 0.0)
    for result in results:
        if not result["sample_size"]:
            result["opportunity_score"] = None
        elif high == low:
            result["opportunity_score"] = 50.0
        else:
            rate = math.log1p(result["median_views_per_day"])
            result["opportunity_score"] = round(100 * (rate - low) / (high - low), 1)
    return {
        "available": True,
        "reason": None,
        "metric": "relative_median_public_views_per_day",
        "candidates": results,
        "limitations": [
            "Search results are a relevance-biased sample, not all competing videos.",
            "Public view counts do not expose impressions, click-through rate, or retention.",
            "Scores compare only the candidates in this request and are not view predictions.",
        ],
    }
