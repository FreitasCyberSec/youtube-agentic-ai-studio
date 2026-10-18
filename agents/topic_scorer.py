"""Deterministic topic scoring for YAAS.

Scores are prioritisation heuristics, not predictions of views. They use only
candidate text, the channel description, the current trend headlines and the
user's banned-topic list; no paid API or external dependency is required.
"""
import re
from collections import Counter

_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "but", "by", "can", "could",
    "did", "do", "does", "for", "from", "how", "if", "in", "into", "is",
    "it", "its", "of", "on", "or", "our", "that", "the", "their", "this",
    "to", "was", "what", "when", "where", "which", "why", "will", "with",
    "you", "your", "a", "an", "the", "about", "after", "before", "over",
    "under", "than", "they", "them", "these", "those", "through", "could",
}
_CURIOSITY_TERMS = {
    "secret", "hidden", "strange", "mystery", "mysterious", "impossible",
    "unknown", "unexpected", "why", "what if", "never", "first", "last",
    "dark", "lost", "discovered", "actually", "really", "truth", "danger",
    "survive", "disappear", "paradox", "universe", "ancient", "forgotten",
}


def _tokens(value):
    return {
        token for token in re.findall(r"[a-z0-9]+", str(value or "").lower())
        if len(token) > 2 and token not in _STOPWORDS
    }


def _candidate_text(candidate):
    fields = (
        candidate.get("topic", ""), candidate.get("video_title", ""),
        candidate.get("why_now", ""), candidate.get("hook_question", ""),
        " ".join(str(x) for x in candidate.get("key_points", []) if x),
    )
    return " ".join(fields)


def _trend_relevance(candidate, trend_context):
    trends = []
    for item in trend_context or []:
        if isinstance(item, dict):
            trends.append(" ".join(str(item.get(k, "")) for k in ("title", "detail")))
        else:
            trends.append(str(item))
    trend_tokens = set().union(*(_tokens(t) for t in trends)) if trends else set()
    if not trend_tokens:
        return 60.0  # neutral, not a penalty when trend data is unavailable
    candidate_tokens = _tokens(_candidate_text(candidate))
    overlap = len(candidate_tokens & trend_tokens)
    return min(100.0, 100.0 * overlap / 4.0)


def _novelty(candidate, banned_topics):
    topic_tokens = _tokens(candidate.get("topic", ""))
    if not topic_tokens:
        return 0.0
    worst_overlap = 0.0
    for banned in banned_topics or []:
        banned_tokens = _tokens(banned)
        if banned_tokens:
            overlap = len(topic_tokens & banned_tokens) / len(topic_tokens | banned_tokens)
            worst_overlap = max(worst_overlap, overlap)
    return max(0.0, 100.0 * (1.0 - min(1.0, worst_overlap * 1.8)))


def score_candidate(candidate, trend_context=None, banned_topics=None,
                    channel_description=""):
    """Return a 0-100 heuristic score and transparent component breakdown."""
    topic = str(candidate.get("topic", "")).strip()
    title = str(candidate.get("video_title", "")).strip()
    hook = str(candidate.get("hook_question", "")).strip()
    points = candidate.get("key_points") or []
    text = _candidate_text(candidate)
    tokens = _tokens(topic)

    trend = _trend_relevance(candidate, trend_context)
    curiosity_hits = sum(1 for term in _CURIOSITY_TERMS if term in text.lower())
    curiosity = min(100.0, 35.0 + curiosity_hits * 13.0 + (15 if "?" in hook else 0))
    specificity = min(100.0, max(0.0, len(tokens) * 9.0))
    if re.search(r"\b(19|20)\d{2}\b|\b\d+(?:\.\d+)?\b", topic):
        specificity = min(100.0, specificity + 15.0)
    if len(title) < 25:
        title_quality = max(25.0, len(title) * 2.5)
    elif len(title) <= 70:
        title_quality = 100.0
    else:
        title_quality = max(20.0, 100.0 - (len(title) - 70) * 2.5)
    depth = min(100.0, len([p for p in points if str(p).strip()]) * 20.0)
    if hook and len(hook.split()) >= 5:
        depth = min(100.0, depth + 10.0)
    novelty = _novelty(candidate, banned_topics)

    channel_tokens = _tokens(channel_description)
    if channel_tokens:
        relevance = 100.0 * len(tokens & channel_tokens) / max(1, len(tokens))
        # Channel relevance acts as a modest adjustment, not a hard filter.
        specificity = specificity * 0.85 + relevance * 0.15

    components = {
        "trend_relevance": round(trend, 1),
        "curiosity": round(curiosity, 1),
        "specificity_and_channel_fit": round(specificity, 1),
        "title_quality": round(title_quality, 1),
        "narrative_depth": round(depth, 1),
        "novelty": round(novelty, 1),
    }
    score = (
        trend * 0.25 + curiosity * 0.20 + specificity * 0.20
        + title_quality * 0.15 + depth * 0.10 + novelty * 0.10
    )
    return {"score": round(score, 1), "components": components}


def select_best_candidate(candidates, trend_context=None, banned_topics=None,
                          channel_description=""):
    """Select the highest-scoring non-empty candidate; return None if invalid."""
    valid = [
        candidate for candidate in (candidates or [])
        if isinstance(candidate, dict) and str(candidate.get("topic", "")).strip()
    ]
    if not valid:
        return None
    ranked = []
    for candidate in valid:
        result = score_candidate(candidate, trend_context, banned_topics, channel_description)
        ranked.append((result["score"], candidate, result["components"]))
    ranked.sort(key=lambda item: item[0], reverse=True)
    score, winner, components = ranked[0]
    selected = dict(winner)
    selected["topic_score"] = score
    selected["topic_score_breakdown"] = components
    selected["topic_candidates_evaluated"] = len(ranked)
    return selected
