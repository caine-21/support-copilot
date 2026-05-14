"""
FAQ knowledge base with two-tier search:
  Primary:  sentence-transformers cosine similarity
  Fallback: BM25 keyword scoring (pure Python, no deps)
"""
import sys
import os
import json
import math
import re
sys.stdout.reconfigure(encoding='utf-8')

_FAQ_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'faq', 'acme_collab_faq.json')

_faqs: list[dict] = []
_embeddings = None        # numpy array [N, D]
_embed_model = None
_use_embeddings = False


def _load_faqs() -> list[dict]:
    global _faqs
    if not _faqs:
        with open(_FAQ_PATH, encoding='utf-8') as f:
            _faqs = json.load(f)
    return _faqs


def _faq_text(faq: dict) -> str:
    return f"{faq['question']} {faq['answer']}"


def _try_load_embeddings():
    global _embeddings, _embed_model, _use_embeddings
    if _use_embeddings is not False:
        return
    try:
        from sentence_transformers import SentenceTransformer
        import numpy as np
        faqs = _load_faqs()
        _embed_model = SentenceTransformer('all-MiniLM-L6-v2')
        texts = [_faq_text(f) for f in faqs]
        _embeddings = _embed_model.encode(texts, normalize_embeddings=True)
        _use_embeddings = True
        print("[KB] sentence-transformers index built")
    except Exception as e:
        print(f"[KB] sentence-transformers unavailable ({e}), using BM25 fallback")
        _use_embeddings = False


# ── BM25 ──────────────────────────────────────────────────────────────────────

def _tokenize(text: str) -> list[str]:
    return re.findall(r'\w+', text.lower())


def _bm25_score(query_tokens: list[str], doc_tokens: list[str], avg_dl: float, k1=1.5, b=0.75) -> float:
    dl = len(doc_tokens)
    freq: dict[str, int] = {}
    for t in doc_tokens:
        freq[t] = freq.get(t, 0) + 1
    score = 0.0
    for qt in set(query_tokens):
        f = freq.get(qt, 0)
        if f == 0:
            continue
        idf = math.log(1 + 1)  # simplified: N=1 doc per query, positive weight
        tf = (f * (k1 + 1)) / (f + k1 * (1 - b + b * dl / avg_dl))
        score += idf * tf
    return score


def _bm25_search(query: str, top_k: int = 3) -> list[dict]:
    faqs = _load_faqs()
    query_tokens = _tokenize(query)
    doc_token_lists = [_tokenize(_faq_text(f)) for f in faqs]
    avg_dl = sum(len(d) for d in doc_token_lists) / max(len(doc_token_lists), 1)
    scored = []
    for i, (faq, doc_tokens) in enumerate(zip(faqs, doc_token_lists)):
        s = _bm25_score(query_tokens, doc_tokens, avg_dl)
        scored.append((s, i))
    scored.sort(reverse=True)
    results = []
    for score, idx in scored[:top_k]:
        if score > 0:
            faq = faqs[idx]
            results.append({
                "doc_id": faq["id"],
                "snippet": faq["answer"][:300],
                "score": round(score, 3),
                "method": "bm25",
            })
    return results


def _embedding_search(query: str, top_k: int = 3) -> list[dict]:
    import numpy as np
    faqs = _load_faqs()
    q_vec = _embed_model.encode([query], normalize_embeddings=True)[0]
    scores = (_embeddings @ q_vec).tolist()
    indexed = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)
    results = []
    for idx, score in indexed[:top_k]:
        if score > 0.2:
            faq = faqs[idx]
            results.append({
                "doc_id": faq["id"],
                "snippet": faq["answer"][:300],
                "score": round(float(score), 3),
                "method": "embedding",
            })
    return results


def search(query: str, top_k: int = 3) -> list[dict]:
    """Return top-k FAQ matches. Primary: embeddings, fallback: BM25."""
    _try_load_embeddings()
    if _use_embeddings:
        try:
            results = _embedding_search(query, top_k)
            if results:
                return results
            # no match above threshold — fall through to BM25
        except Exception as e:
            print(f"[KB] embedding search failed ({e}), falling back to BM25")
    return _bm25_search(query, top_k)


def get_faq_by_id(doc_id: str) -> dict | None:
    faqs = _load_faqs()
    for faq in faqs:
        if faq["id"] == doc_id:
            return faq
    return None
