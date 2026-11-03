"""A small, dependency-free BM25 index for the Hotela knowledge base.

Used only when RETRIEVAL_HYBRID is on. The knowledge base is a few dozen
sections, so an in-memory index over the chunk texts is cheap and keeps the
retrieval stage free of a new dependency.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+|[\u0600-\u06FF]+")

# English + Urdu stop words. Small on purpose: over-stopping hurts short
# visitor questions more than it helps.
STOP_WORDS = frozenset(
    """
    a an the of to in on for and or is are was were be been being do does did doing
    i you he she it we they me my your his her its our their mein mein ka ki ke ko
    se par aur or lein liye kya kyun kab kahan kaise kaun kis konsi konsay
    what which who when where why how is are was were do does did can could should
    would will shall may might must
    """.split()
)


def tokenize(text: str) -> list[str]:
    """Latin words plus whole Urdu words. Urdu is not whitespace segmented."""
    tokens: list[str] = []
    for match in _TOKEN_RE.findall(text or ""):
        lowered = match.lower()
        if len(lowered) < 2 and not lowered.isdigit():
            continue
        if lowered in STOP_WORDS:
            continue
        tokens.append(lowered)
    return tokens


@dataclass
class BM25Index:
    """Standard Okapi BM25 over a fixed set of documents."""

    documents: list[str]
    k1: float = 1.5
    b: float = 0.75
    _doc_tokens: list[list[str]] = field(default_factory=list, repr=False)
    _df: dict[str, int] = field(default_factory=dict, repr=False)
    _idf: dict[str, float] = field(default_factory=dict, repr=False)
    _avg_len: float = 0.0

    def __post_init__(self) -> None:
        self._doc_tokens = [tokenize(document) for document in self.documents]
        lengths = [len(tokens) for tokens in self._doc_tokens]
        self._avg_len = (sum(lengths) / len(lengths)) if lengths else 0.0
        for tokens in self._doc_tokens:
            for token in set(tokens):
                self._df[token] = self._df.get(token, 0) + 1
        total = len(self.documents) or 1
        for token, frequency in self._df.items():
            self._idf[token] = math.log(1 + (total - frequency + 0.5) / (frequency + 0.5))

    def scores(self, query: str) -> list[float]:
        query_tokens = tokenize(query)
        if not query_tokens:
            return [0.0] * len(self.documents)
        result: list[float] = []
        for tokens in self._doc_tokens:
            if not tokens:
                result.append(0.0)
                continue
            counts: dict[str, int] = {}
            for token in tokens:
                counts[token] = counts.get(token, 0) + 1
            length = len(tokens)
            score = 0.0
            for token in query_tokens:
                frequency = counts.get(token, 0)
                if not frequency:
                    continue
                idf = self._idf.get(token, 0.0)
                denominator = frequency + self.k1 * (1 - self.b + self.b * length / (self._avg_len or 1.0))
                score += idf * (frequency * (self.k1 + 1)) / denominator
            result.append(score)
        return result
