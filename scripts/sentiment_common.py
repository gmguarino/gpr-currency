"""Shared prompt and JSON schema for scoring sentiment towards the USA (1-5).

Used by sentiment_benchmark.py (Ollama) and score_sentiment.py (OpenAI-compatible server,
e.g. vLLM), so that both score articles with the same instructions.
"""

SYSTEM = (
    "You are an expert analyst of Chinese state media. You rate the attitude an article "
    "expresses towards the United States."
)

_PROMPT = """Read the following People's Daily article. Rate the sentiment it expresses towards the United States (its government, leaders, institutions, military, companies and policies, including references such as 美方, 白宫, 华盛顿, 美国总统, 美联储, 国会).

Scale:
1 = completely negative (condemnation, hostility, sanctions, blame)
2 = negative (criticism, concern, disagreement)
3 = neutral (factual reporting, or mixed positive and negative)
4 = positive (cooperation, constructive engagement, praise)
5 = completely positive (strong praise, close friendship)

Judge the attitude towards the United States, not whether the events are good or bad news in general. {reply}

Title: {title}

Article:
{text}"""

_REPLY_WITH_REASON = 'Reply as JSON with "score" (integer 1-5) and "reason" (at most 20 words, in English).'
_REPLY_SCORE_ONLY = 'Reply as JSON with "score" (integer 1-5) only.'

SCHEMA = {
    "type": "object",
    "properties": {
        "score": {"type": "integer", "minimum": 1, "maximum": 5},
        "reason": {"type": "string"},
    },
    "required": ["score", "reason"],
}
SCHEMA_SCORE_ONLY = {
    "type": "object",
    "properties": {"score": {"type": "integer", "minimum": 1, "maximum": 5}},
    "required": ["score"],
}


def build_messages(title: str, text: str, with_reason: bool = True) -> list[dict]:
    """Chat messages asking for a 1-5 score (and optionally a short reason)."""
    reply = _REPLY_WITH_REASON if with_reason else _REPLY_SCORE_ONLY
    return [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": _PROMPT.format(reply=reply, title=title, text=text)},
    ]
