# YouTube public opportunity signals (experimental)

The module `apis/youtube_opportunities.py` optionally queries YouTube Data API v3
for a small, relevance-biased sample of public videos matching each topic. It
collects public view counts and publication dates, then calculates each video's
views per day and the median rate per candidate. A log-scaled score from 0–100
compares only candidates evaluated in the same call.

## Setup

1. Enable **YouTube Data API v3** in a Google Cloud project.
2. Create an API key and add `YOUTUBE_API_KEY=...` to the local `.env` file,
   or use the app Settings page if it exposes that key.
3. Call `collect_topic_signals([{"topic": "..."}])` from Python.

Without a key, the function returns `available: false` without making requests.
Per-candidate API errors are returned as data so a caller can retain the existing
heuristic ranking rather than failing the video pipeline.

## Limits

- Search results are selected for relevance and do not represent every competitor.
- Views/day is a rough normalization, not audience demand or predicted performance.
- Public competitor data does not expose impressions, click-through rate, or retention.
- Scores are relative to candidates in the same call; they should not be compared
  across different runs as if they were calibrated probabilities.
- API quota applies. Keep candidate counts and result counts small and cache results
  before integrating this into automatic topic selection.

## Offline tests

Run `pytest -q tests/test_youtube_opportunities.py`. Tests use mocked responses and
do not require a key or network access.
