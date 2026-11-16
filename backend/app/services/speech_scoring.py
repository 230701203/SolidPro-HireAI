"""Compare what the applicant said (a transcript) with the expected sentence.

Deliberately simple and explainable, because a person reviews it:
* Words are lower-cased and stripped of punctuation. Extra words (fillers, repeated words) are NOT penalised.
* Words are aligned in order (edit-distance alignment), so word order matters.
* A near match (e.g. "drawing" heard for "drawings") earns half credit and is listed as a *possible recognition
  error*, so an accent that makes the recogniser slip is not punished as hard as a genuinely missing word.
* accuracy = credit / expected words. This is advisory: confidence and the audio decide, not this number alone.
"""

import re
from collections import Counter
from difflib import SequenceMatcher

_TOKEN = re.compile(r"[a-z0-9]+(?:['\-][a-z0-9]+)*")
NEAR_CUTOFF = 0.85
NEAR_CREDIT = 0.5


def tokenize(text: str) -> list[str]:
    return _TOKEN.findall(text.lower().replace("’", "'"))


def _near(a: str, b: str) -> bool:
    return a != b and min(len(a), len(b)) >= 4 and SequenceMatcher(None, a, b).ratio() >= NEAR_CUTOFF


def compare(expected: str, recognized: str) -> dict:
    exp, rec = tokenize(expected), tokenize(recognized)
    n, m = len(exp), len(rec)
    if n == 0:
        return {"expected_words": 0, "recognized_words": m, "accuracy": None, "completeness": None, "missing": [], "substituted": [], "near_matches": [], "extra": rec, "order_differs": False}

    def cost(a: str, b: str) -> float:
        return 0.0 if a == b else (0.5 if _near(a, b) else 1.0)

    # dp[i][j] = cheapest alignment of exp[:i] with rec[:j]
    dp = [[0.0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        dp[i][0] = float(i)
    for j in range(1, m + 1):
        dp[0][j] = float(j)
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            dp[i][j] = min(dp[i - 1][j - 1] + cost(exp[i - 1], rec[j - 1]), dp[i - 1][j] + 1.0, dp[i][j - 1] + 1.0)

    i, j = n, m
    credit = 0.0
    missing: list[str] = []
    substituted: list[dict] = []
    near: list[dict] = []
    extra: list[str] = []
    while i > 0 or j > 0:
        if i > 0 and j > 0 and abs(dp[i][j] - (dp[i - 1][j - 1] + cost(exp[i - 1], rec[j - 1]))) < 1e-9:
            c = cost(exp[i - 1], rec[j - 1])
            if c == 0.0:
                credit += 1.0
            elif c == 0.5:
                credit += NEAR_CREDIT
                near.append({"expected": exp[i - 1], "heard": rec[j - 1]})
            else:
                substituted.append({"expected": exp[i - 1], "heard": rec[j - 1]})
            i, j = i - 1, j - 1
        elif i > 0 and abs(dp[i][j] - (dp[i - 1][j] + 1.0)) < 1e-9:
            missing.append(exp[i - 1])
            i -= 1
        else:
            extra.append(rec[j - 1])
            j -= 1
    for lst in (missing, substituted, near, extra):
        lst.reverse()

    bag = sum((Counter(exp) & Counter(rec)).values())
    aligned_exact = round(credit - NEAR_CREDIT * len(near))
    order_differs = (bag - aligned_exact) / n >= 0.25  # most words were said, but not in the expected order
    return {
        "expected_words": n, "recognized_words": m,
        "accuracy": round(credit / n, 3), "completeness": round(1 - len(missing) / n, 3),
        "missing": missing, "substituted": substituted, "near_matches": near, "extra": extra, "order_differs": order_differs,
    }
