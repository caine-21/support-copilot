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

    Pipeline (v8 — multi-intent aware):
      1. normalize_multi() → intent_set (all matching intents)
      2. If requires_clarification → return [] (reasoner → L1)
      3. _intent_set_search(intent_set):
           full coverage  → merged results, score=1.0
           partial        → merged results, score capped at 0.59 → grounding=weak → L1
           all gaps       → []
      4. intent_set == ["unknown"] → embedding → BM25 fallback
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

    # Fallback: embedding → BM25 (intent_set == ["unknown"] or unknown intent_id)
    inl = normalize(query)
    effective_query = inl.get("canonical_query", query)
    if effective_query != query:
        print(f"[KB] INL fallback: '{query[:55]}' → '{effective_query[:55]}'")

    _try_load_embeddings()
    if _use_embeddings:
        try:
            results = _embedding_search(effective_query, top_k)
            if results:
                return results
        except Exception as e:
            print(f"[KB] embedding search failed ({e}), falling back to BM25")
    return _bm25_search(effective_query, top_k)


def get_faq_by_id(doc_id: str) -> dict | None:
    faqs = _load_faqs()
    for faq in faqs:
        if faq["id"] == doc_id:
            return faq
    return None
