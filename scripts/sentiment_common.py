"""Shared prompt and JSON schema for scoring sentiment towards the USA (1-5).

Used by sentiment_benchmark.py (Ollama) and score_sentiment.py (OpenAI-compatible server,
e.g. vLLM), so that both score articles with the same instructions. review_sentiment.py uses
the review prompt below to have a model audit those scores.
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


REVIEW_SYSTEM = (
    "You are a careful, sceptical reviewer of sentiment annotations of Chinese state media. "
    "You do not defer to the previous annotator: you check the claim against the text."
)

_REVIEW_PROMPT = """Below is a People's Daily article and a sentiment score (1-5) that a first annotator gave for the attitude the article expresses towards the United States, with their reason.

Scale:
1 = completely negative (condemnation, hostility, sanctions, blame)
2 = negative (criticism, concern, disagreement)
3 = neutral (factual reporting, or mixed positive and negative)
4 = positive (cooperation, constructive engagement, praise)
5 = completely positive (strong praise, close friendship)

The score must reflect the attitude towards the United States, not whether the events are good or bad news in general.

Check the score and the reason against the article. Reply as JSON with:
- "agree": true if the score is defensible (within the scale's meaning), false if it is wrong;
- "revised_score": your own score (integer 1-5); equal to the first score if you agree;
- "explanation": in English, at most 40 words. If you disagree, say specifically why the first annotator is wrong (e.g. misread the target, took a quote as the paper's own view, ignored mixed signals); if you agree, say what supports the score.

Title: {title}

Article:
{text}

First annotator's score: {score}
First annotator's reason: {reason}"""

SCHEMA_REVIEW = {
    "type": "object",
    "properties": {
        "agree": {"type": "boolean"},
        "revised_score": {"type": "integer", "minimum": 1, "maximum": 5},
        "explanation": {"type": "string"},
    },
    "required": ["agree", "revised_score", "explanation"],
}


def build_review_messages(title: str, text: str, score: int, reason: str) -> list[dict]:
    """Chat messages asking a model to audit an existing score and its reason."""
    return [
        {"role": "system", "content": REVIEW_SYSTEM},
        {"role": "user", "content": _REVIEW_PROMPT.format(title=title, text=text, score=score, reason=reason or "(none)")},
    ]


ARBITER_SYSTEM = (
    "You are the final arbiter between two annotators who disagree about the sentiment of a "
    "Chinese state media article towards the United States. You decide from the text, not from "
    "who sounds more confident."
)

_ARBITER_PROMPT = """Two annotators scored the sentiment that the following People's Daily article expresses towards the United States, and they disagree. Read the article, then weigh both scores and both reasonings, and decide the final score. You may side with either annotator or choose a different score.

Scale:
1 = completely negative (condemnation, hostility, sanctions, blame)
2 = negative (criticism, concern, disagreement)
3 = neutral (factual reporting, or mixed positive and negative)
4 = positive (cooperation, constructive engagement, praise)
5 = completely positive (strong praise, close friendship)

The score must reflect the attitude towards the United States, not whether the events are good or bad news in general.

Reply as JSON with:
- "final_score": integer 1-5;
- "decision": "first" if you side with annotator A, "second" if with annotator B, "neither" if your score differs from both;
- "explanation": in English, at most 40 words, saying which reasoning holds up against the text and why.

Title: {title}

Article:
{text}

Annotator A: score {score_a}. Reason: {reason_a}
Annotator B: score {score_b}. Reason: {reason_b}"""

SCHEMA_ARBITER = {
    "type": "object",
    "properties": {
        "final_score": {"type": "integer", "minimum": 1, "maximum": 5},
        "decision": {"type": "string", "enum": ["first", "second", "neither"]},
        "explanation": {"type": "string"},
    },
    "required": ["final_score", "decision", "explanation"],
}


def build_arbiter_messages(title: str, text: str, score_a: int, reason_a: str,
                           score_b: int, reason_b: str) -> list[dict]:
    """Chat messages asking a model to settle a disagreement between two annotations."""
    return [
        {"role": "system", "content": ARBITER_SYSTEM},
        {"role": "user", "content": _ARBITER_PROMPT.format(
            title=title, text=text, score_a=score_a, reason_a=reason_a or "(none)",
            score_b=score_b, reason_b=reason_b or "(none)")},
    ]
