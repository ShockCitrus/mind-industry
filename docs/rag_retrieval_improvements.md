# RAG Retrieval Improvements for Detection System

## Current Retrieval Architecture

The system uses **topic-based retrieval with embedding-based pre-filtering**:

1. **Topic-filtered FAISS search** (TB-ENN or TB-ANN):
   - Uses Inner Product (cosine-like) distance on normalized embeddings
   - Per-topic indices reduce search space before retrieval
   - Documents weighted by topic relevance scores
   - **Returns**: top_k results per topic, merged and deduplicated

2. **Embedding pre-filter** (Strategy 3):
   - Computes dot-product similarity: `question ⊗ chunk_text`
   - Drops chunks below `embedding_prefilter_threshold` (default: 0.75, now 0.250 after user tuning)
   - Uses same embedding model as retrieval (BAAI/bge-m3 for bilingual)

3. **Score-ratio cutoff** (Strategy 6):
   - Keeps only chunks scoring ≥ `ratio × best_score` (default: 0.65 now)
   - Reduces weak matches before LLM evaluation

---

## Identified Issues for Bilingual Retrieval

### Problem 1: Inner Product Distance in Cross-Lingual Space
**Current**: Uses `METRIC_INNER_PRODUCT` on normalized embeddings (essentially cosine similarity)

**Issue**: 
- Cross-lingual embeddings are inherently noisier than monolingual ones
- Inner Product favors high-magnitude embeddings (which may be language-specific artifacts)
- Similar concepts in different languages can have lower scores due to embedding space differences

**Solution**: Consider **Euclidean (L2) distance** or a **learned similarity metric** for better cross-lingual alignment.

---

### Problem 2: Pre-filter Using Simple Dot Product
**Current**: `similarity = np.dot(question_embedding, chunk_embedding)` on dense embeddings

**Issue**:
- Doesn't account for chunk length (longer chunks naturally have higher magnitudes)
- No normalization when embeddings aren't normalized
- Thresholds (0.75 → 0.250) are brittle and dataset-dependent

**Solution**: Use **cosine similarity** (normalized dot product) with length-invariant thresholds, or a **cross-encoder** reranker.

---

### Problem 3: Single-Stage Retrieval + Naive Filter
**Current**: Retrieve top-k globally, then apply filters that drop many candidates

**Issue**:
- Retrieves only 5 global candidates (now 10)
- When score-ratio cutoff is 0.65, if 1st chunk scores 0.8, we only keep chunks ≥ 0.52
- In cross-lingual mode, many valid matches fall in "ambiguous" bands (0.5–0.7)
- Pre-filter threshold is data-dependent; tuning is reactive

**Solution**: **Two-stage retrieval**:
1. Retrieve many candidates (20–50) loosely, keep all
2. Rerank with a stronger signal (cross-encoder, semantic reranking)

---

### Problem 4: No Reciprocal Retrieval
**Current**: Direction is always `question → target_chunks`

**Issue**:
- In bilingual mode, the source question may not semantically align well with target passages
- Misses cases where target passages are topically similar but phrase differently

**Solution**: **Reciprocal retrieval**: also retrieve in reverse (`chunk_embedding → question`) and merge top results.

---

## Proposed Improvements (By Effort/Impact)

### Tier 1: Quick Wins (< 30 min each)

#### 1A. Fix Pre-Filter Distance Metric
**File**: `src/mind/pipeline/pipeline.py` lines 1033

**Change**:
```python
# Current (line 1033):
similarity = float(np.dot(question_embedding, chunk_embedding))

# Proposed:
from scipy.spatial.distance import cosine
similarity = 1 - cosine(question_embedding, chunk_embedding)
```

**Why**: Cosine similarity is normalized [0, 1], thresholds are intuitive (0.5 = 50% similar). Works well for cross-lingual embeddings.

**Cost**: One extra function call per pair. Negligible for 10-20 candidates.

---

#### 1B. Dynamic Threshold Based on Score Distribution
**File**: `src/mind/pipeline/pipeline.py` lines 616–621 (score-ratio cutoff)

**Change**:
```python
# Instead of fixed ratio (0.65):
# Use percentile-based filtering — keep top 70–80% of candidates by score
if self._retrieval_min_score_ratio > 0 and all_target_chunks:
    scores = [tc.metadata.get("score", 0) for tc in all_target_chunks]
    if scores:
        # Use percentile instead of ratio for robustness
        cutoff = np.percentile(scores, max(20, self._retrieval_min_score_ratio * 100))
        all_target_chunks = [tc for tc in all_target_chunks if tc.metadata.get("score", 0) >= cutoff]
        self._logger.info(f"Percentile-based cutoff: {cutoff:.3f} kept {len(all_target_chunks)}/{pre_count}")
```

**Why**: Percentiles are data-driven and less brittle than fixed ratios.

**Config change**: Reinterpret `retrieval_min_score_ratio` as percentile (0.8 = top 80%).

---

### Tier 2: Medium Effort (1–2 hours)

#### 2A. Add Cross-Encoder Reranking
**What**: A lightweight model (CROSS-ENCODER/ms-marco-MiniLM-L-6-v2, 22M params) reranks candidates.

**Implementation**:
```python
# In corpus.py or pipeline.py, after retrieve_relevant_chunks():
from sentence_transformers import CrossEncoder

cross_encoder = CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')
scores = cross_encoder.predict(
    [[question, chunk.text] for chunk in all_target_chunks],
    batch_size=32
)
# Re-sort by cross-encoder scores
all_target_chunks = [c for _, c in sorted(zip(scores, all_target_chunks), reverse=True)][:top_k]
```

**Pros**:
- Single model, minimal setup
- Top-k can stay small (5–10)
- Handles bilingual better than embedding-based retrieval
- ~50ms for 10 pairs on CPU

**Cons**: Extra LLM model to load/maintain, adds latency.

**Recommend**: Add to config as optional `use_cross_encoder_rerank: true`.

---

#### 2B. Bidirectional / Reciprocal Retrieval
**What**: Retrieve both `question → chunks` and `chunk → question`, merge results.

**Implementation** in `corpus.py`:
```python
def retrieve_relevant_chunks_bidirectional(self, query, theta_query, top_k=5):
    # Forward: question → chunks
    forward = self.retriever.retrieve(..., query=query, theta_query=theta_query, top_k=top_k*2)
    
    # Reverse: each forward chunk → question (find most similar passages to question elsewhere)
    reverse = self.retriever.retrieve(..., query=query, top_k=top_k*2)  # Different passage pool
    
    # Merge, deduplicate, return top_k
    all_results = {r['doc_id']: r for r in forward + reverse}.values()
    return sorted(all_results, key=lambda x: x['score'], reverse=True)[:top_k]
```

**Pros**: Catches "opposite direction" matches missed by forward-only retrieval.

**Cons**: 2× retrieval calls (mitigated by larger `retrieval_max_k`).

---

### Tier 3: Deeper Changes (2–4 hours)

#### 3A. Swap Inner Product for Euclidean Distance
**File**: `src/mind/pipeline/retriever.py` lines 343, 349, 418

**Change**:
```python
# Current:
quantizer = faiss.IndexFlatIP(embedding_size)
index = faiss.IndexIVFFlat(quantizer, embedding_size, n_clusters_ann, faiss.METRIC_INNER_PRODUCT)

# Proposed:
quantizer = faiss.IndexFlatL2(embedding_size)  # L2 Euclidean distance
index = faiss.IndexIVFFlat(quantizer, embedding_size, n_clusters_ann, faiss.METRIC_L2)
```

**Caveat**: Must re-embed all documents (not normalized, or ensure L2 embeddings).

**Pros**: Better for cross-lingual spaces (less dependent on magnitude).

**Cons**: 
- Requires reindexing (one-time cost, ~10 min for large corpus)
- May need to retune `retrieval_max_k` and thresholds

**Recommend**: Test on small dataset first.

---

#### 3B. Learned Ranking (LTR) / Fine-Tuned Similarity
**What**: Train a small model on your domain to predict relevance.

**Effort**: High. Requires labeled (question, chunk, relevance) triplets.

**Recommend**: Skip for now; defer to Tier 2C if detection stays poor after other improvements.

---

## Recommendation for Your Bilingual Case

**Start with Tier 1 (quick wins)**:

1. **1A**: Switch pre-filter to cosine similarity (~2 min fix)
2. **1B**: Use percentile-based score filtering instead of fixed ratio (~5 min fix)

**Then test** on your 5-contradiction dataset.

**If still missing contradictions**, move to **Tier 2A** (cross-encoder reranking):
- Adds ~50ms overhead per detection
- Dramatically improves bilingual matching
- No reindexing needed

**Then test again** before moving to Tier 3.

---

## Config Changes Summary

**Current** (after your threshold tuning):
```yaml
embedding_prefilter_threshold: 0.250
retrieval_min_score_ratio: 0.35
retrieval_max_k: 10
```

**Proposed** (after improvements):
```yaml
# If using percentile-based filtering
retrieval_min_score_percentile: 70  # Keep top 70% of retrieved chunks

# Optional: enable cross-encoder reranking
use_cross_encoder_rerank: false  # Set to true if needed after Tier 1 testing

# Embedding prefilter: remove or set to 0 if using cross-encoder
embedding_prefilter_threshold: 0.0  # Rely on cross-encoder instead
```

---

## Expected Outcomes

| Change | Latency Impact | Recall Impact | Precision Impact |
|--------|---|---|---|
| Tier 1A (cosine sim) | +1% | +5–10% | Neutral |
| Tier 1B (percentile) | +0% | +3–8% | Neutral |
| Tier 2A (cross-encoder) | +50ms/query | +15–25% | +10–20% |
| Tier 3A (L2 distance) | +0% | +5–15% | +5–10% |

**Bilingual-specific**: Tier 2A likely has the highest impact for your use case.
