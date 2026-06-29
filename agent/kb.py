"""
FAQ knowledge base with two-tier search:
  Primary:  deterministic INTENT_FAQ_MAP lookup (known intents)
  Fallback: hybrid search — dense embedding + BM25 fused via RRF (unknown intents)
"""
import sys
import os
import json
import math
import re
sys.stdout.reconfigure(encoding='utf-8')
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

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
                "snippet": faq["answer"][:600],
                "score": round(score, 3),
                "method": "bm25",
            })
    return results


def _rrf_fuse(
    embedding_results: list[dict],
    bm25_results: list[dict],
    cosine_by_id: dict[str, float] | None = None,
    top_k: int = 3,
    k: int = 60,
) -> list[dict]:
    """Reciprocal Rank Fusion of dense and sparse results.

    RRF score = 1/(rank_embedding + k) + 1/(rank_bm25 + k)
    k=60 is the standard constant from the original RRF paper.
    Uses rank rather than raw scores so cosine and BM25 scales don't conflict.
    """
    rrf_scores: dict[str, float] = {}
    sources: dict[str, dict] = {}

    for rank, result in enumerate(embedding_results):
        doc_id = result["doc_id"]
        rrf_scores[doc_id] = rrf_scores.get(doc_id, 0.0) + 1.0 / (rank + k)
        sources[doc_id] = {**result, "method": "hybrid_rrf"}

    for rank, result in enumerate(bm25_results):
        doc_id = result["doc_id"]
        rrf_scores[doc_id] = rrf_scores.get(doc_id, 0.0) + 1.0 / (rank + k)
        if doc_id not in sources:
            sources[doc_id] = {**result, "method": "hybrid_rrf"}
        else:
            sources[doc_id]["method"] = "hybrid_rrf"

    ranked = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)
    results = []
    for doc_id, rrf_score in ranked[:top_k]:
        result = {**sources[doc_id], "rrf_score": round(rrf_score, 4)}
        if cosine_by_id is not None:
            result["score"] = round(cosine_by_id.get(doc_id, 0.0), 3)
        results.append(result)
    return results


def _cosine_scores_by_id(query: str) -> dict[str, float]:
    faqs = _load_faqs()
    q_vec = _embed_model.encode([query], normalize_embeddings=True)[0]
    scores = (_embeddings @ q_vec).tolist()
    return {faq["id"]: float(score) for faq, score in zip(faqs, scores)}


def _hybrid_search(query: str, top_k: int = 3) -> list[dict]:
    """Run embedding + BM25 in parallel, fuse via RRF.

    Degrades gracefully: if embeddings unavailable, returns BM25-only results.
    """
    _try_load_embeddings()
    bm25_results = _bm25_search(query, top_k * 3)
    if not _use_embeddings:
        # TODO: BM25-only fallback still uses BM25 score scale. Normal runtime
        # should use embeddings so grounding strength remains cosine-based.
        return bm25_results[:top_k]
    try:
        emb_results = _embedding_search(query, top_k * 3)
        cosine_by_id = _cosine_scores_by_id(query)
        fused = _rrf_fuse(emb_results, bm25_results, cosine_by_id, top_k)
        return fused if fused else bm25_results[:top_k]
    except Exception as e:
        print(f"[KB] hybrid: embedding failed ({e}), returning BM25 only")
        return bm25_results[:top_k]


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
                "snippet": faq["answer"][:600],
                "score": round(float(score), 3),
                "method": "embedding",
            })
    return results


# ── Intent → FAQ index (v7 deterministic lookup) ─────────────────────────────
#
# Maps stable intent_id (from INL) to FAQ doc_id list.
# Score 1.0 = perfect grounding — no embedding uncertainty.
# Empty list = no KB coverage → reasoner sees grounding=none → L1/L2 by policy.
#
# Embedding search is fallback-only for intent_id == "unknown".

INTENT_FAQ_MAP: dict[str, list[str]] = {
    "payment_methods":    ["FAQ-billing-06"],
    "cancellation_fee":   ["FAQ-billing-07"],
    "refund_eligibility": ["FAQ-billing-08", "FAQ-billing-03"],
    "refund_status":      [],               # needs agent lookup → L1
    "invoice_customize":  [],               # not self-serve → L1
    "plan_change":        ["FAQ-account-02"],
    "cancel_subscription":[],               # no self-serve answer → L2 (churn)
    "password_reset":     ["FAQ-account-01"],
    "data_export":        ["FAQ-feature-04"],
    "permission_levels":  ["FAQ-feature-02"],
    "feature_feedback":   [],               # no self-serve path → L1
    "version_history":    ["FAQ-feature-07"],
    "sso_issue":          [],               # SSO broken needs investigation → L1
    "sso_setup":          ["FAQ-security-01"],
    "audit_logs":         ["FAQ-security-03"],
    "signup_issue":       ["FAQ-troubleshoot-01"],
    "workspace_setup":    [],               # no FAQ → L1
    "upload_error":       [],               # L1 — FAQ doesn't resolve size/format issues
    "ui_preferences":     [],               # feature availability → L1
    "account_deletion":   [],               # escalate
    "sla_uptime":         ["FAQ-policy-01"],
    "invoice_download":   ["FAQ-billing-01"],
    "unknown_plan":       [],               # requires_clarification → L1
}


# Must stay one step below reasoner._GROUNDING_STRONG (0.60).
# If that threshold changes, update this constant too.
_PARTIAL_COVERAGE_SCORE = 0.60 - 0.01   # = 0.59


def _intent_set_search(intent_set: list[str]) -> list[dict] | None:
    """
    Multi-intent FAQ lookup (v8).

    Coverage policy:
    - All intents have non-empty FAQ → return merged results, score=1.0 (full)
    - Any intent has []              → cap score at _PARTIAL_COVERAGE_SCORE (partial; grounding=weak → L1)
    - All intents have []            → return [] (no coverage → L1)

    Returns None if any intent_id is unknown (not in INTENT_FAQ_MAP) — caller
    should fall through to embedding search.
    """
    all_results: list[dict] = []
    has_gap   = False  # any intent with no FAQ coverage
    has_cover = False  # any intent with FAQ coverage

    for intent_id in intent_set:
        faq_ids = INTENT_FAQ_MAP.get(intent_id)
        if faq_ids is None:
            return None          # unknown intent → fall through to embedding
        if not faq_ids:
            has_gap = True
            print(f"[KB] intent_set gap: {intent_id} → no KB coverage")
            continue
        has_cover = True
        results = _intent_index_search(intent_id) or []
        all_results.extend(results)

    # Deduplicate by doc_id
    seen: set[str] = set()
    deduped = [r for r in all_results if not (r["doc_id"] in seen or seen.add(r["doc_id"]))]

    if not has_cover:
        print(f"[KB] intent_set: {intent_set} → all gaps, no KB coverage")
        return []

    if has_gap:
        # Partial coverage: cap score below _GROUNDING_STRONG (0.60) → grounding=weak → L1
        capped = [{**r, "score": min(r["score"], _PARTIAL_COVERAGE_SCORE), "method": "intent_set_partial"} for r in deduped]
        print(f"[KB] intent_set: {intent_set} → partial coverage, score capped → L1")
        return capped

    print(f"[KB] intent_set: {intent_set} → full coverage, {len(deduped)} FAQ(s)")
    return deduped


def _intent_index_search(intent_id: str) -> list[dict] | None:
    """
    Deterministic FAQ lookup by intent_id.

    Returns:
      None  — intent_id not in INTENT_FAQ_MAP (caller should fall through to embedding)
      []    — intent_id mapped to no FAQs (no KB coverage; caller returns empty)
      [...]  — FAQs found; score=1.0, method=intent_index
    """
    faq_ids = INTENT_FAQ_MAP.get(intent_id)
    if faq_ids is None:
        return None         # not in map → fall through to embedding
    if not faq_ids:
        return []           # known intent with no KB coverage
    faqs = _load_faqs()
    id_set = set(faq_ids)
    results = []
    for faq in faqs:
        if faq["id"] in id_set:
            results.append({
                "doc_id": faq["id"],
                "snippet": faq["answer"][:600],
                "score": 1.0,
                "method": "intent_index",
            })
    return results


def search(query: str, top_k: int = 3) -> list[dict]:
    """
    Return top-k FAQ matches.

    Pipeline (v9 — hybrid fallback):
      1. normalize_multi() → intent_set (all matching intents)
      2. If requires_clarification → return [] (reasoner → L1)
      3. _intent_set_search(intent_set):
           full coverage  → merged results, score=1.0
           partial        → merged results, score capped at 0.59 → grounding=weak → L1
           all gaps       → []
      4. intent_set == ["unknown"] → hybrid search (BM25 + embedding fused via RRF)
    """
    from intent_normalizer import normalize, normalize_multi
    multi = normalize_multi(query)

    if multi["requires_clarification"]:
        print(f"[KB] INL: clarification required — unknown entity '{multi['unknown_entity']}'")
        return []

    intent_set = multi["intent_set"]

    if intent_set and intent_set != ["unknown"]:
        set_result = _intent_set_search(intent_set)
        if set_result is not None:
            return set_result

    # Fallback: hybrid search (embedding + BM25 via RRF) for unknown intents
    inl = normalize(query)
    effective_query = inl.get("canonical_query", query)
    if effective_query != query:
        print(f"[KB] INL fallback: '{query[:55]}' → '{effective_query[:55]}'")

    return _hybrid_search(effective_query, top_k)


def get_faq_by_id(doc_id: str) -> dict | None:
    faqs = _load_faqs()
    for faq in faqs:
        if faq["id"] == doc_id:
            return faq
    return None
