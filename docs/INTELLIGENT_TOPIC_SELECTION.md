# Intelligent topic selection (experimental)

YAAS can now ask the language model for three distinct topic candidates and rank
them locally before fact-grounding the selected topic.

## What is scored

The offline scorer in `agents/topic_scorer.py` assigns a transparent 0–100
heuristic score using:

- overlap with current Trend Radar headlines (when available);
- curiosity language and a concrete hook question;
- topic specificity and fit with the configured channel description;
- title length/readability heuristics;
- presence of enough narrative key points;
- lexical overlap with topics listed as already covered/banned.

The selected result includes `topic_score`, `topic_score_breakdown`, and
`topic_candidates_evaluated`. These fields are metadata for debugging and
future UI improvements; they do not guarantee views or predict audience
behaviour.

If a model/provider does not return `topic_candidates`, YAAS keeps the
top-level result and continues with the previous behaviour. Explicit user topic
overrides are never replaced by the automatic ranker.

## Limitations

This is a deterministic heuristic, not a trained recommendation model. It does
not yet inspect competitor video statistics, YouTube impressions/click-through
rate, audience retention, or historical performance of the user's channel.
Trend headlines are only weak demand signals. The next iteration should add
proper candidate sourcing and, later, learn from the user's own YouTube
Analytics after enough videos have been published.

## Tests

Run the offline tests with:

```bash
pip install pytest
pytest tests/test_topic_scorer.py
```
