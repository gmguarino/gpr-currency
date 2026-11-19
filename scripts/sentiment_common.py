"""Shared prompts and JSON schemas for rating the view of the USA that an article conveys (1-5) and whether it is relevant.

Used by sentiment_benchmark.py (Ollama) and score_sentiment.py (OpenAI-compatible server, e.g.
vLLM), so that both score articles with the same instructions. review_sentiment.py and
arbitrate_sentiment.py use the review and arbiter prompts below to audit those scores. All three
prompts share FOCUS, RELEVANCE, SCALE and JUDGE, so they always judge the same thing.
"""

# Identifies the wording of the scale. It is stored with every result; the clients refuse to mix results
# made with different versions (a changed scale means everything must be scored again).
# Bump it whenever FOCUS / RELEVANCE / SCALE / JUDGE or the schemas change.
# Results without a version were made with the original "attitude" prompt (1 = completely negative ...).
PROMPT_VERSION = "stance-v3"

SYSTEM = (
    "You are an expert analyst of Chinese state media and of China-US economic and sanctions relations. "
    "You judge the view of the United States that an article conveys."
)

FOCUS = """the view of the United States that the article conveys, as an economic, commercial, financial, sanctions and geopolitical actor and as a counterpart of China. The United States includes its government, leaders, institutions, companies and policies, and references such as 美方, 白宫, 华盛顿, 美国总统, 美联储, 国会"""

RELEVANCE = """The article is relevant if the United States is a real subject of its economic, commercial, financial, sanctions or geopolitical content, or if it portrays the United States or the West as strong, weak, divided, failing or in decline, or if an American official, scholar or outlet comments on the economy, trade or geopolitics (such an article scores 3 unless the comment expresses a view of the United States itself). It is NOT relevant if the United States is only incidental: a place, venue or stop on an itinerary, a name mentioned in passing, an American quoted about something unrelated to these matters, or sport, culture, entertainment, an accident or a disaster that says nothing about how the United States is portrayed"""

SCALE = """1 = hostile: the US is portrayed as an aggressor or bully (imposing or threatening sanctions, tariffs, export controls), blamed and condemned
2 = critical: the US is criticised or portrayed negatively (in the wrong, hypocritical, divided, weak, failing or in decline) without outright condemnation
3 = neutral: no clear view of the US: factual reporting, balanced positive and negative, or a text about China or others that expresses no view of the US (praise of China is not praise of the US)
4 = favourable: the US is portrayed positively (a constructive or credible partner, succeeding, cooperating)
5 = very favourable: strong praise of the US or of cooperation with it"""

JUDGE = ("Judge what the article conveys about the United States itself, not about China or third countries, and not "
         "whether the events are good or bad news in general. An American (official, scholar, company or outlet) "
         "praising China, or describing China's success, is NOT praise of the United States: score such an article 3 "
         "unless it also expresses a view of the United States itself.")

_PROMPT = """Read the following People's Daily article. Decide whether it is relevant, and rate {focus}.

Relevance: {relevance}.

Scale (use it only for relevant articles):
{scale}

{judge} {{reply}}

Title: {{title}}

Article:
{{text}}""".format(focus=FOCUS, relevance=RELEVANCE, scale=SCALE, judge=JUDGE)

_REPLY_WITH_REASON = ('Reply as JSON with "relevant" (true or false), "score" (integer 1-5; 3 if not relevant) '
                      'and "reason" (at most 20 words, in English).')
_REPLY_SCORE_ONLY = 'Reply as JSON with "relevant" (true or false) and "score" (integer 1-5; 3 if not relevant) only.'

SCHEMA = {
    "type": "object",
    "properties": {
        "relevant": {"type": "boolean"},
        "score": {"type": "integer", "minimum": 1, "maximum": 5},
        "reason": {"type": "string"},
    },
    "required": ["relevant", "score", "reason"],
}
SCHEMA_SCORE_ONLY = {
    "type": "object",
    "properties": {"relevant": {"type": "boolean"}, "score": {"type": "integer", "minimum": 1, "maximum": 5}},
    "required": ["relevant", "score"],
}


def build_messages(title: str, text: str, with_reason: bool = True) -> list[dict]:
    """Chat messages asking for relevance and a 1-5 score (and optionally a short reason)."""
    reply = _REPLY_WITH_REASON if with_reason else _REPLY_SCORE_ONLY
    return [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": _PROMPT.format(reply=reply, title=title, text=text)},
    ]


def same_verdict(rel_a: bool, score_a: int, rel_b: bool, score_b: int) -> bool:
    """Two verdicts agree if both say irrelevant (the score is moot), or both say relevant with the same score."""
    return rel_a == rel_b and (not rel_a or score_a == score_b)


REVIEW_SYSTEM = (
    "You are a careful, sceptical reviewer of annotations of Chinese state media on China-US economic "
    "and sanctions relations. You do not defer to the previous annotator: you check the claim against the text."
)

_REVIEW_PROMPT = """Below is a People's Daily article and the verdict of a first annotator, who decided whether the article is relevant and, if so, scored {focus}.

Relevance: {relevance}.

Scale (for relevant articles):
{scale}

{judge}

Check the verdict and the reason against the article. Reply as JSON with:
- "agree": true if both the relevance and the score are defensible, false if either is wrong;
- "revised_relevant": your own relevance verdict (true or false); equal to the first one if you agree;
- "revised_score": your own score (integer 1-5; 3 if not relevant); equal to the first score if you agree;
- "explanation": in English, at most 40 words. If you disagree, say specifically why the first annotator is wrong (e.g. the US is only incidental, praise of China taken as praise of the US, a quote taken as the paper's own view, ignored mixed signals); if you agree, say what supports the verdict.

Title: {{title}}

Article:
{{text}}

First annotator: relevant = {{relevant}}, score = {{score}}
First annotator's reason: {{reason}}""".format(focus=FOCUS, relevance=RELEVANCE, scale=SCALE, judge=JUDGE)

SCHEMA_REVIEW = {
    "type": "object",
    "properties": {
        "agree": {"type": "boolean"},
        "revised_relevant": {"type": "boolean"},
        "revised_score": {"type": "integer", "minimum": 1, "maximum": 5},
        "explanation": {"type": "string"},
    },
    "required": ["agree", "revised_relevant", "revised_score", "explanation"],
}


def build_review_messages(title: str, text: str, score: int, reason: str, relevant: bool = True) -> list[dict]:
    """Chat messages asking a model to audit an existing verdict (relevance + score) and its reason."""
    return [
        {"role": "system", "content": REVIEW_SYSTEM},
        {"role": "user", "content": _REVIEW_PROMPT.format(
            title=title, text=text, score=score, reason=reason or "(none)", relevant=str(bool(relevant)).lower())},
    ]


ARBITER_SYSTEM = (
    "You are the final arbiter between two annotators who disagree about whether a Chinese state media "
    "article is relevant and what view of the United States it conveys. You decide from the text, not "
    "from who sounds more confident."
)

_ARBITER_PROMPT = """Two annotators judged a People's Daily article: whether it is relevant and, if so, {focus}. They disagree. Read the article, weigh both verdicts and both reasonings, and decide the final verdict. You may side with either annotator or choose a different one.

Relevance: {relevance}.

Scale (for relevant articles):
{scale}

{judge}

Reply as JSON with:
- "final_relevant": true or false;
- "final_score": integer 1-5 (3 if not relevant);
- "decision": "first" if you side with annotator A, "second" if with annotator B, "neither" if your verdict differs from both;
- "explanation": in English, at most 40 words, saying which reasoning holds up against the text and why.

Title: {{title}}

Article:
{{text}}

Annotator A: relevant = {{rel_a}}, score {{score_a}}. Reason: {{reason_a}}
Annotator B: relevant = {{rel_b}}, score {{score_b}}. Reason: {{reason_b}}""".format(
    focus=FOCUS, relevance=RELEVANCE, scale=SCALE, judge=JUDGE)

SCHEMA_ARBITER = {
    "type": "object",
    "properties": {
        "final_relevant": {"type": "boolean"},
        "final_score": {"type": "integer", "minimum": 1, "maximum": 5},
        "decision": {"type": "string", "enum": ["first", "second", "neither"]},
        "explanation": {"type": "string"},
    },
    "required": ["final_relevant", "final_score", "decision", "explanation"],
}


def build_arbiter_messages(title: str, text: str, rel_a: bool, score_a: int, reason_a: str,
                           rel_b: bool, score_b: int, reason_b: str) -> list[dict]:
    """Chat messages asking a model to settle a disagreement between two annotations."""
    b = lambda v: str(bool(v)).lower()  # noqa: E731
    return [
        {"role": "system", "content": ARBITER_SYSTEM},
        {"role": "user", "content": _ARBITER_PROMPT.format(
            title=title, text=text, rel_a=b(rel_a), score_a=score_a, reason_a=reason_a or "(none)",
            rel_b=b(rel_b), score_b=score_b, reason_b=reason_b or "(none)")},
    ]
