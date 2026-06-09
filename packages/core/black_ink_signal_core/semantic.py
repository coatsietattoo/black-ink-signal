"""Lightweight semantic search for leads using TF-IDF + cosine similarity.

No external ML deps — uses Python stdlib + basic math.
Designed for up to ~50k leads on a single machine.
"""

from __future__ import annotations
import math
import re
from collections import Counter
from typing import Optional

# ---------------------------------------------------------------------------
# Token processing
# ---------------------------------------------------------------------------

_STOP = frozenset("""
a an the is it in on at to for of and or but not with this that from was were
be been am are have has had do does did will would shall should can could may
might must i me my we our you your he she they them his her its their
""".split())

def _tokenize(text: str) -> list[str]:
    """Lowercase, strip punctuation, remove stop words."""
    words = re.findall(r'[a-z0-9]+', text.lower())
    return [w for w in words if w not in _STOP and len(w) > 1]

# ---------------------------------------------------------------------------
# Tattoo domain vocabulary (boost relevant terms)
# ---------------------------------------------------------------------------

DOMAIN_BOOST = {
    # Styles
    "realism": 2.0, "realistic": 2.0, "traditional": 2.0, "japanese": 2.0,
    "geometric": 2.0, "dotwork": 2.0, "watercolor": 2.0, "fineline": 2.0,
    "blackwork": 2.0, "neotraditional": 2.0, "tribal": 1.5, "minimalist": 2.0,
    "illustrative": 2.0, "surrealism": 2.0, "chicano": 2.0, "biomechanical": 2.0,
    "portrait": 2.0, "lettering": 1.5, "script": 1.5,
    # Projects
    "sleeve": 2.0, "halfsleeve": 2.0, "backpiece": 2.0, "chestpiece": 2.0,
    "coverup": 2.5, "memorial": 2.5, "tribute": 2.0,
    # Intent
    "artist": 1.5, "shop": 1.5, "studio": 1.5, "booking": 2.0,
    "consultation": 2.0, "portfolio": 1.5, "appointment": 2.0, "recommend": 1.5,
    # Emotion
    "nervous": 1.5, "excited": 1.3, "scared": 1.5, "frustrated": 1.5,
    "regret": 2.0, "unhappy": 1.5, "love": 1.2,
    # Geo
    "edmonton": 2.5, "yeg": 2.5, "alberta": 2.0, "calgary": 1.5,
}

# ---------------------------------------------------------------------------
# TF-IDF vectorizer (lightweight, in-memory)
# ---------------------------------------------------------------------------

class TFIDFIndex:
    """Simple TF-IDF index for semantic-ish lead search."""

    def __init__(self):
        self.docs: list[dict] = []  # [{id, tokens, tf}]
        self.idf: dict[str, float] = {}
        self._dirty = True

    def add(self, doc_id: int, text: str):
        tokens = _tokenize(text)
        if not tokens:
            return
        tf = Counter(tokens)
        total = len(tokens)
        self.docs.append({
            "id": doc_id,
            "tokens": tokens,
            "tf": {t: (c / total) * DOMAIN_BOOST.get(t, 1.0) for t, c in tf.items()},
        })
        self._dirty = True

    def build(self):
        """Recompute IDF values."""
        n = len(self.docs)
        if n == 0:
            return
        df: Counter = Counter()
        for doc in self.docs:
            df.update(set(doc["tf"].keys()))
        self.idf = {term: math.log(n / (1 + count)) for term, count in df.items()}
        self._dirty = False

    def search(self, query: str, top_k: int = 20) -> list[dict]:
        """Return top_k doc_ids with cosine similarity scores."""
        if self._dirty:
            self.build()
        if not self.docs:
            return []

        qtokens = _tokenize(query)
        if not qtokens:
            return []

        qtf = Counter(qtokens)
        total = len(qtokens)
        qvec = {t: (c / total) * DOMAIN_BOOST.get(t, 1.0) * self.idf.get(t, 0)
                for t, c in qtf.items()}
        qnorm = math.sqrt(sum(v * v for v in qvec.values()))
        if qnorm == 0:
            return []

        results = []
        for doc in self.docs:
            dvec = {t: tf * self.idf.get(t, 0) for t, tf in doc["tf"].items()}
            # Dot product
            dot = sum(qvec.get(t, 0) * dvec.get(t, 0) for t in set(qvec) & set(dvec))
            if dot == 0:
                continue
            dnorm = math.sqrt(sum(v * v for v in dvec.values()))
            sim = dot / (qnorm * dnorm) if dnorm > 0 else 0
            results.append({"id": doc["id"], "score": round(sim, 4)})

        results.sort(key=lambda x: -x["score"])
        return results[:top_k]

    def similar(self, doc_id: int, top_k: int = 10) -> list[dict]:
        """Find leads similar to a given lead."""
        doc = next((d for d in self.docs if d["id"] == doc_id), None)
        if not doc:
            return []
        # Use the doc's tokens as a query
        text = " ".join(doc["tokens"])
        results = self.search(text, top_k + 1)
        return [r for r in results if r["id"] != doc_id][:top_k]

    @property
    def size(self) -> int:
        return len(self.docs)
