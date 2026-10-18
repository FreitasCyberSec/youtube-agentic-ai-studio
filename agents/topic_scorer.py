"""Deterministic, explainable topic scoring for YAAS.

Scores prioritise candidates; they are not predictions of views. The scorer
uses only candidate text, channel description, trend headlines and a list of
already-covered topics. It requires no API key or third-party dependency.
"""
import re
import unicodedata

_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "but", "by", "can", "could",
    "did", "do", "does", "for", "from", "how", "if", "in", "into", "is",
    "it", "its", "of", "on", "or", "our", "that", "the", "their", "this",
    "to", "was", "what", "when", "where", "which", "why", "will", "with",
    "you", "your", "about", "after", "before", "over", "under", "than",
    "they", "them", "these", "those", "through", "de", "da", "do", "das",
    "dos", "e", "em", "um", "uma", "o", "os", "as", "no", "na", "nos",
    "nas", "por", "para", "com", "que", "como", "qual", "quais", "ao",
    "aos", "ou", "se", "ser", "foi", "mais", "menos",
}
_CURIOSITY_TERMS = {
    "secret", "hidden", "strange", "mystery", "mysterious", "impossible",
    "unknown", "unexpected", "never", "first", "last", "dark", "lost",
    "discovered", "actually", "really", "truth", "danger", "survive",
    "disappear", "paradox", "universe", "ancient", "forgotten", "mistério",
    "segredo", "desapareceu", "desconhecido", "impossível", "verdade",
    "perdido", "antigo", "perigoso", "descoberta",
}


def _tokens(value):
    """Normalise case/diacritics and return meaningful word tokens."""
    text = unicodedata.normalize("NFKD", str(value or "").casefold())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return {
        token for token in re.findall(r"[a-z0-9]+", text)
        if len(token) > 2 and token not in _STOPWORDS
    }


def _as_text_list(value):
    """Accept list-like fields safely; a string is one item, not characters."""
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value if item is not None and str(item).strip()]
    return []


def _candidate_text(candidate):
    fields = [
        candidate.get("topic", ""),
        candidate.get("video_title", ""),
        candidate.get("why_now", ""),
        candidate.get("hook_question", ""),
    ]
    fields.extend(_as_text_list(candidate.get("key_points", [])))
    return " ".join(str(field) for field in fields if field)


def _trend_text(item):
    if isinstance(item, dict):
        return " ".join(str(item.get(key, "")) for key in ("title", "detail"))
    return str(item or "")


def _trend_relevance(candidate, trend_context):
    """Compare against individual headlines, avoiding false matches across all trends."""
    candidate_tokens = _tokens(_candidate_text(candidate))
    if not candidate_tokens:
        return 60.0 if not trend_context else 0.0
    trend_sets = [
        _tokens(_trend_text(item))
        for item in (trend_context or [])
    ]
    trend_sets = [tokens for tokens in trend_sets if tokens]
    if not trend_sets:
        return 60.0  # neutral when trend data is unavailable
    scores = sorted(
        (100.0 * len(candidate_tokens & tokens) / max(1, len(candidate_tokens | tokens))
         for tokens in trend_sets),
        reverse=True,
    )
    # One closely relevant headline matters more than many unrelated headlines.
    best = scores[0]
    top_three_mean = sum(scores[:3]) / min(3, len(scores))
    return round(0.70 * best + 0.30 * top_three_mean, 1)


def _novelty(candidate, covered_topics):
    """Penalise lexical duplication with topics already covered by this channel."""
    topic_tokens = _tokens(candidate.get("topic", ""))
    if not topic_tokens:
        return 0.0
    worst_overlap = 0.0
    for previous in covered_topics or []:
        previous_tokens = _tokens(previous)
        if previous_tokens:
            overlap = len(topic_tokens & previous_tokens) / len(topic_tokens | previous_tokens)
            worst_overlap = max(worst_overlap, overlap)
    return max(0.0, 100.0 * (1.0 - min(1.0, worst_overlap * 1.8)))


def score_candidate(candidate, trend_context=None, banned_topics=None,
                    channel_description=""):
    """Return a 0–100 heuristic score and transparent component breakdown."""
    if not isinstance(candidate, dict):
        candidate = {}
    topic = str(candidate.get("topic", "") or "").strip()
    title = str(candidate.get("video_title", "") or "").strip()
    hook = str(candidate.get("hook_question", "") or "").strip()
    points = _as_text_list(candidate.get("key_points", []))
    text = _candidate_text(candidate)
    tokens = _tokens(topic)

    trend = _trend_relevance(candidate, trend_context)
    text_tokens = _tokens(text)
    curiosity_hits = len(text_tokens & _CURIOSITY_TERMS)
    curiosity = min(100.0, 35.0 + curiosity_hits * 13.0 + (15 if "?" in hook else 0))

    specificity = min(100.0, max(0.0, len(tokens) * 9.0))
    if re.search(r"\b(19|20)\d{2}\b|\b\d+(?:\.\d+)?\b", topic):
        specificity = min(100.0, specificity + 15.0)

    # Avoid rewarding any title purely for being within a length band.
    title_tokens = _tokens(title)
    if not title:
        title_quality = 0.0
    elif len(title) < 25:
        title_quality = max(25.0, len(title) * 2.5)
    elif len(title) <= 70:
        title_quality = min(100.0, 70.0 + len(title_tokens) * 3.0)
    else:
        title_quality = max(20.0, 100.0 - (len(title) - 70) * 2.5)

    depth = min(100.0, len(points) * 20.0)
    if hook and len(hook.split()) >= 5:
        depth = min(100.0, depth + 10.0)
    novelty = _novelty(candidate, banned_topics)

    channel_tokens = _tokens(channel_description)
    if channel_tokens and tokens:
        relevance = 100.0 * len(tokens & channel_tokens) / len(tokens)
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
    return {"score": round(max(0.0, min(100.0, score)), 1), "components": components}


def select_best_candidate(candidates, trend_context=None, banned_topics=None,
                          channel_description=""):
    """Select the highest-scoring non-empty candidate; return None if invalid."""
    if not isinstance(candidates, (list, tuple)):
        return None
    valid = [
        candidate for candidate in candidates
        if isinstance(candidate, dict) and str(candidate.get("topic", "") or "").strip()
    ]
    if not valid:
        return None
    ranked = []
    for candidate in valid:
        result = score_candidate(candidate, trend_context, banned_topics, channel_description)
        ranked.append((result["score"], candidate, result["components"]))
    # Stable tie-break: preserve the model's order if scores are equal.
    ranked.sort(key=lambda item: item[0], reverse=True)
    score, winner, components = ranked[0]
    selected = dict(winner)
    selected["topic_score"] = score
    selected["topic_score_breakdown"] = components
    selected["topic_candidates_evaluated"] = len(ranked)
    return selected
