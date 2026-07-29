import re
import unicodedata
from collections import Counter


STOPWORDS = {
    "and",
    "or",
    "with",
    "without",
    "the",
    "a",
    "an",
    "of",
    "to",
    "in",
    "raw",
    "fresh",
    "prepared",
    "cooked",
}


def normalize_text(value):
    if value is None:
        return ""
    text = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode()
    text = text.lower()
    text = re.sub(r"[^a-z0-9%]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def normalize_unicode_text(value):
    if value is None:
        return ""
    text = unicodedata.normalize("NFKC", str(value)).lower()
    text = re.sub(r"[^\w%]+", " ", text, flags=re.UNICODE)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def tokens(value):
    return [token for token in normalize_text(value).split() if token and token not in STOPWORDS]


def unicode_tokens(value):
    return [
        token
        for token in normalize_unicode_text(value).split()
        if token and token not in STOPWORDS
    ]


def char_ngrams(value, n=3):
    text = normalize_text(value).replace(" ", "_")
    if len(text) <= n:
        return Counter([text]) if text else Counter()
    return Counter(text[i : i + n] for i in range(len(text) - n + 1))


def unicode_char_ngrams(value, n=3):
    text = normalize_unicode_text(value).replace(" ", "_")
    if len(text) <= n:
        return Counter([text]) if text else Counter()
    return Counter(text[i : i + n] for i in range(len(text) - n + 1))


def cosine_counts(left, right):
    if not left or not right:
        return 0.0
    common = set(left).intersection(right)
    numerator = sum(left[key] * right[key] for key in common)
    left_norm = sum(v * v for v in left.values()) ** 0.5
    right_norm = sum(v * v for v in right.values()) ** 0.5
    if not left_norm or not right_norm:
        return 0.0
    return numerator / (left_norm * right_norm)


def token_jaccard(left_text, right_text):
    left = set(tokens(left_text))
    right = set(tokens(right_text))
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def unicode_token_jaccard(left_text, right_text):
    left = set(unicode_tokens(left_text))
    right = set(unicode_tokens(right_text))
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def name_similarity(left, right):
    left_norm = normalize_text(left)
    right_norm = normalize_text(right)
    if not left_norm or not right_norm:
        return 0.0
    if left_norm == right_norm:
        return 1.0
    if left_norm in right_norm or right_norm in left_norm:
        containment = min(len(left_norm), len(right_norm)) / max(len(left_norm), len(right_norm))
    else:
        containment = 0.0
    ngram_score = cosine_counts(char_ngrams(left_norm), char_ngrams(right_norm))
    token_score = token_jaccard(left_norm, right_norm)
    return round((0.55 * ngram_score) + (0.35 * token_score) + (0.10 * containment), 4)


def unicode_name_similarity(left, right):
    left_norm = normalize_unicode_text(left)
    right_norm = normalize_unicode_text(right)
    if not left_norm or not right_norm:
        return 0.0
    if left_norm == right_norm:
        return 1.0
    if left_norm in right_norm or right_norm in left_norm:
        containment = min(len(left_norm), len(right_norm)) / max(len(left_norm), len(right_norm))
    else:
        containment = 0.0
    ngram_score = cosine_counts(unicode_char_ngrams(left_norm), unicode_char_ngrams(right_norm))
    token_score = unicode_token_jaccard(left_norm, right_norm)
    return round((0.55 * ngram_score) + (0.35 * token_score) + (0.10 * containment), 4)


def confidence_tier(score):
    if score >= 0.86:
        return "high"
    if score >= 0.72:
        return "medium"
    if score >= 0.58:
        return "low"
    return "review"
