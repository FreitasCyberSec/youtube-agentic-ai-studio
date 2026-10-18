"""
Research Agent — uses shared Gemini client with model fallback chain.
Banned topics are read from banned_topics.txt (one topic per line) in the
project root. Edit that file — or use the GUI textarea — instead of changing
Python code.
"""
import os
import random
import time
import config
from agents.gemini_client import generate
from agents.json_utils import extract_json
from agents.topic_scorer import score_candidate, select_best_candidate

_BANNED_TOPICS_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "banned_topics.txt",
)

_BUILTIN_BANNED = [
    "The Boltzmann Brain",
    "Simulation Theory",
    "Quantum Immortality",
]

FOCUS_ANGLES = [
    "Theoretical Physics & Time Travel",
    "The Dark Forest Theory & Aliens",
    "Existential Human Psychology & Illusions",
    "Frightening AI Futures & Simulation Theory",
    "Mind-bending Mathematical Paradoxes",
    "The limits of Human Biology & Immortality",
    "Quantum Mechanics & Alternate Realities",
    "Cosmic scale, Black Holes, and the end of the Universe",
    "Neuroscience & the Mystery of Consciousness",
    "Ancient Civilisations & Lost History",
    "Cutting-edge Biotechnology & Genetic Engineering",
    "The Future of Space Colonisation",
]


def load_banned_topics() -> list:
    """Return built-in plus user-managed banned topics; never raise."""
    topics = list(_BUILTIN_BANNED)
    try:
        if os.path.exists(_BANNED_TOPICS_FILE):
            with open(_BANNED_TOPICS_FILE, encoding="utf-8") as f:
                for line in f:
                    topic = line.strip()
                    if topic and not topic.startswith("#") and topic not in topics:
                        topics.append(topic)
    except Exception as exc:
        print(f"   ⚠ Could not read banned_topics.txt: {exc}")
    return topics


def save_banned_topics(topics: list) -> None:
    """Write user-managed banned topics; built-ins are always applied."""
    user_topics = [t.strip() for t in topics if isinstance(t, str)
                   and t.strip() and t.strip() not in _BUILTIN_BANNED]
    with open(_BANNED_TOPICS_FILE, "w", encoding="utf-8") as f:
        f.write("# One banned topic per line. Lines starting with # are comments.\n")
        f.write("# Built-in banned: The Boltzmann Brain, Simulation Theory, Quantum Immortality\n")
        f.write("# Add topics here after you make a video about them.\n\n")
        f.write("\n".join(user_topics) + ("\n" if user_topics else ""))


def _grounding(topic: str) -> dict:
    """Wikipedia + arXiv background facts for a topic (empty if disabled/offline)."""
    if not getattr(config, "FACT_GROUNDING", True):
        return {"facts": "", "sources": []}
    from apis.knowledge import gather_context
    print(f"   → Grounding facts: Wikipedia + arXiv for \"{topic[:60]}\"…")
    ctx = gather_context(topic)
    print(f"   → {len(ctx['sources'])} sources found")
    return ctx


def _parse(raw: str) -> dict:
    data = extract_json(raw, "Researcher")
    for field in ["topic", "video_title", "key_points", "tags"]:
        if field not in data:
            raise ValueError(f"Research JSON missing field: '{field}'")
    return data


def _select_topic(data: dict, trend_context, banned, channel_description) -> dict:
    """Rank AI candidates locally, optionally blending public YouTube signals."""
    candidates = data.get("topic_candidates")
    selected = select_best_candidate(
        candidates,
        trend_context=trend_context,
        banned_topics=banned,
        channel_description=channel_description,
    )
    if not selected:
        # Backwards compatible with providers/models that return the old schema.
        data["topic_score"] = None
        data["topic_score_breakdown"] = {}
        data["topic_candidates_evaluated"] = 1
        data["topic_market_signals"] = {"available": False, "reason": "no_candidates"}
        return data

    # Optional public market signals. Missing key or API failure must never break
    # the existing heuristic path. API scores are relative to this candidate set.
    market = {"available": False, "reason": "not_configured", "candidates": []}
    try:
        from apis.youtube_opportunities import collect_topic_signals
        market = collect_topic_signals(candidates)
    except Exception as exc:
        market = {"available": False, "reason": "collector_error", "error": str(exc)[:200]}

    market_by_topic = {
        item.get("topic"): item for item in market.get("candidates", [])
        if isinstance(item, dict) and item.get("topic")
    }
    ranked = []
    valid_candidates = [
        candidate for candidate in candidates
        if isinstance(candidate, dict) and str(candidate.get("topic", "")).strip()
    ]
    for candidate in valid_candidates:
        heuristic = score_candidate(
            candidate, trend_context=trend_context,
            banned_topics=banned, channel_description=channel_description,
        )
        market_item = market_by_topic.get(str(candidate.get("topic", "")).strip())
        market_score = (
            market_item.get("opportunity_score")
            if market_item and market_item.get("status") == "ok"
            else None
        )
        # Keep the heuristic dominant; only blend real, successful samples.
        combined = (
            round(heuristic["score"] * 0.8 + float(market_score) * 0.2, 1)
            if market_score is not None else heuristic["score"]
        )
        ranked.append((combined, candidate, heuristic, market_item))
    if ranked:
        ranked.sort(key=lambda item: item[0], reverse=True)
        combined_score, winner, heuristic, market_item = ranked[0]
        selected = dict(winner)
        selected["topic_score"] = combined_score
        selected["topic_score_breakdown"] = dict(heuristic["components"])
        if market_item and market_item.get("opportunity_score") is not None:
            selected["topic_score_breakdown"]["public_youtube_opportunity"] = market_item["opportunity_score"]
            selected["topic_score_breakdown"]["heuristic_score"] = heuristic["score"]
        selected["topic_candidates_evaluated"] = len(ranked)
    selected["topic_market_signals"] = {
        "available": bool(market.get("available")),
        "reason": market.get("reason"),
        "metric": market.get("metric"),
        "selected_candidate": market_by_topic.get(selected.get("topic", "")),
        "limitations": market.get("limitations", []),
    }

    result = dict(data)
    result.pop("topic_candidates", None)
    for key in (
        "topic", "why_now", "video_title", "description", "hook_question",
        "key_points", "target_audience", "tags", "thumbnail_concept",
        "estimated_virality",
    ):
        value = selected.get(key)
        if value not in (None, "", [], {}):
            result[key] = value
    result["topic_score"] = selected["topic_score"]
    result["topic_score_breakdown"] = selected["topic_score_breakdown"]
    result["topic_candidates_evaluated"] = selected["topic_candidates_evaluated"]
    result["topic_market_signals"] = selected["topic_market_signals"]
    print(
        f"   → Topic ranking selected \"{result['topic']}\" "
        f"(score {result['topic_score']}/100 from "
        f"{result['topic_candidates_evaluated']} candidates; "
        f"public YouTube signals {'used' if market.get('available') else 'not available'})"
    )
    return result


def research_topic(channel_description: str,
                   topic_override: str = "",
                   focus_angle: str = "",
                   trend_context: list | None = None) -> dict:
    """
    Research a topic and, for automatic selection, rank multiple AI candidates.

    Scores are transparent heuristics based on trend overlap, curiosity,
    specificity, title quality, narrative depth and banned-topic novelty.
    They are not view predictions. The chosen topic is then grounded in
    Wikipedia/arXiv as before.
    """
    banned = load_banned_topics()
    banned_str = ", ".join(f'"{t}"' for t in banned)

    # Mode 1: user explicitly chose the topic; do not replace it.
    if topic_override.strip():
        exact_topic = topic_override.strip()
        print(f"   → Exact topic override: \"{exact_topic}\"")
        grounding = _grounding(exact_topic)
        facts_block = (
            "\nVERIFIED BACKGROUND (from Wikipedia / arXiv — build on these, don't contradict them):\n"
            f"{grounding['facts'][:3500]}\n"
        ) if grounding["facts"] else ""
        prompt = f"""You are a careful YouTube content strategist.

Channel description:
{channel_description}

MANDATORY: make a video about this exact topic: >>> {exact_topic} <<<
Do not substitute another topic. User choice overrides the banned-topic list.
BANNED TOPICS for automatic suggestions: {banned_str}

Plan a compelling 6-8 minute video. Do not claim unsupported facts.
{facts_block}
Return ONLY valid JSON:
{{
  "topic": "{exact_topic}",
  "why_now": "Why this topic is relevant to this audience",
  "video_title": "Specific compelling title under 70 characters",
  "description": "Two-sentence description",
  "hook_question": "A concrete question the video answers",
  "key_points": ["Point one", "Point two", "Point three", "Point four", "Point five"],
  "target_audience": "Who will watch this",
  "tags": ["tag1", "tag2", "tag3"],
  "thumbnail_concept": "Visual concept for a thumbnail",
  "estimated_virality": "unknown"
}}"""
        data = _parse(generate(prompt))
        data["grounding"] = grounding
        data.setdefault("topic_score", None)
        data.setdefault("topic_score_breakdown", {})
        data.setdefault("topic_candidates_evaluated", 1)
        return data

    # Mode 2: AI proposes alternatives, then local heuristics rank them.
    if focus_angle.strip():
        chosen_angle = focus_angle.strip()
        print(f"   → Focus angle (GUI selected): {chosen_angle}")
    else:
        chosen_angle = random.choice(FOCUS_ANGLES)
        print(f"   → Focus angle (random): {chosen_angle}")

    print(f"   → Generating candidate topics within: {chosen_angle}")
    trend_block = ""
    if trend_context:
        print(f"   → Trend-aware: {len(trend_context)} live headlines from Trend Radar")
        joined = "\n".join(
            f"  - {item.get('title', '')}: {item.get('detail', '')}"
            if isinstance(item, dict) else f"  - {item}"
            for item in trend_context[:25]
        )
        trend_block = (
            "CURRENT TREND SIGNALS (use only when relevant; do not force a trend):\n"
            f"{joined}\n"
        )

    prompt = f"""You are a YouTube content strategist. Propose genuinely distinct, researchable video ideas.

Channel description:
{channel_description}

FOCUS THEME: >>> {chosen_angle} <<<
DO NOT reuse these already-covered topics: {banned_str}
{trend_block}
Generate 3 distinct candidates. Prefer a specific question, surprising but defensible angle,
clear audience value, and enough substance for a 6-8 minute video. Avoid generic listicles,
unsupported conspiracy claims, fake urgency, and titles that promise more than the story delivers.
Do not say an idea is trending unless the supplied signals support that claim.
For EACH candidate provide all fields below. Also fill the top-level fields with your own
initial best candidate for backwards compatibility. The local scorer will choose among candidates.

Return ONLY valid JSON:
{{
  "topic": "Initial best candidate topic",
  "why_now": "Evidence-based relevance",
  "video_title": "Specific title under 70 characters",
  "description": "Two-sentence description",
  "hook_question": "Concrete question answered by the video?",
  "key_points": ["Point one", "Point two", "Point three", "Point four"],
  "target_audience": "Specific intended audience",
  "tags": ["tag1", "tag2", "tag3"],
  "thumbnail_concept": "Concrete visual concept",
  "estimated_virality": "unknown",
  "topic_candidates": [
    {{
      "topic": "Candidate one topic",
      "why_now": "Why it is relevant, without unsupported trend claims",
      "video_title": "Specific title under 70 characters",
      "description": "Two-sentence description",
      "hook_question": "Question the story answers?",
      "key_points": ["Point one", "Point two", "Point three", "Point four"],
      "target_audience": "Specific audience",
      "tags": ["tag1", "tag2", "tag3"],
      "thumbnail_concept": "Concrete visual concept",
      "estimated_virality": "unknown"
    }},
    {{
      "topic": "Candidate two topic",
      "why_now": "Why it is relevant",
      "video_title": "Specific title under 70 characters",
      "description": "Two-sentence description",
      "hook_question": "Question the story answers?",
      "key_points": ["Point one", "Point two", "Point three", "Point four"],
      "target_audience": "Specific audience",
      "tags": ["tag1", "tag2", "tag3"],
      "thumbnail_concept": "Concrete visual concept",
      "estimated_virality": "unknown"
    }},
    {{
      "topic": "Candidate three topic",
      "why_now": "Why it is relevant",
      "video_title": "Specific title under 70 characters",
      "description": "Two-sentence description",
      "hook_question": "Question the story answers?",
      "key_points": ["Point one", "Point two", "Point three", "Point four"],
      "target_audience": "Specific audience",
      "tags": ["tag1", "tag2", "tag3"],
      "thumbnail_concept": "Concrete visual concept",
      "estimated_virality": "unknown"
    }}
  ]
}}"""

    data = _parse(generate(prompt))
    data = _select_topic(data, trend_context, banned, channel_description)
    data["grounding"] = _grounding(data["topic"])
    return data
