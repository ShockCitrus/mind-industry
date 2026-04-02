# RAG Retrieval Improvements for Detection System

## Current Retrieval Architecture

The system uses **topic-based retrieval with embedding-based pre-filtering**:

1. **Topic-filtered FAISS search** (TB-ENN or TB-ANN):
   - Uses Inner Product (cosine-like) distance on normalized embeddings
   - Per-topic `IndexFlatIP` / `IndexIVFFlat` indices reduce search space
   - Documents optionally weighted by topic relevance scores (`do_weighting: True`)
   - Per-topic thresholds computed via `dynamic_thresholds()` using KneeLocator elbow detection on the topic-document CDF
   - **Returns**: top_k results per topic, merged and deduplicated (`retriever.py:148–204`)

2. **Embedding pre-filter** (Strategy 3):
   - Computes dot-product similarity: `question ⊗ chunk_text` via `_prefilter_target_chunks()` (`pipeline.py:1021–1043`)
   - Drops chunks below `embedding_prefilter_threshold` (default: 0.5; tuned to 0.250 for cross-lingual)
   - Uses same `BAAI/bge-m3` model as retrieval (shared `retriever.encode_queries()`)

3. **Score-ratio cutoff** (Strategy 6):
   - Keeps only chunks scoring ≥ `ratio × best_score` (`pipeline.py:600–613`)
   - `retrieval_min_score_ratio: 0.35` — keeps chunks within 65% of the best FAISS score
   - Reduces weak matches before LLM evaluation; logged as "Cost optimization"

### Retrieval Method Reference

| Method | FAISS Index | Scope | When to Use |
|--------|-------------|-------|-------------|
| **ENN** | `IndexFlatIP` (exact) | Global corpus | Small corpora, max accuracy |
| **ANN** | `IndexIVFFlat` (approx) | Global corpus | Large corpora, latency-sensitive |
| **TB-ENN** | Per-topic `IndexFlatIP` | Topic-stratified | **Default**; bilingual, topic-aligned queries |
| **TB-ANN** | Per-topic `IndexIVFFlat` | Topic-stratified | Large corpora + topic alignment |

Default configured at `app/config/config.yaml:66` as `method: TB-ENN`.

---

## Identified Issues for Bilingual Retrieval

### Problem 1: Inner Product Distance in Cross-Lingual Space

**Current**: `IndexFlatIP` uses inner product on normalized embeddings (≈ cosine similarity), configured at `retriever.py:349`.

**Issue**:
- Cross-lingual embeddings are inherently noisier than monolingual ones
- When `do_norm: True` (current for `BAAI/bge-m3`), inner product = cosine, so normalization is correctly handled
- However, topic-weighted scores (`score = dist * weight`) can distort ranking when topic weights are skewed

**Note**: The normalization concern is partially mitigated — `retriever.py` sets `do_norm: True` for `BAAI/bge-m3` in `config.yaml`. The core issue is topic-weight distortion for cross-lingual pairs.

**Solution**: Consider **L2 distance** or a **learned similarity metric** for better cross-lingual alignment, or disable topic weighting (`do_weighting: False`) when in bilingual mode.

---

### Problem 2: Pre-filter Using Raw Dot Product

**Current** (`pipeline.py:1033`):
```python
similarity = float(np.dot(question_embedding, chunk_embedding))
```

**Issue**:
- `encode_queries()` does NOT normalize internally unless `do_norm: True` is set on the retriever
- When `do_norm: False`, dot product is not equivalent to cosine; longer chunks have inflated scores
- Thresholds (tuned from 0.75 → 0.250) are brittle and dataset-dependent because the scale isn't bounded to [0, 1]

**Solution**: Use **cosine similarity** (normalized dot product) — stable bounds, language-invariant thresholds.

---

### Problem 3: Single-Stage Retrieval + Naive Filter

**Current**: Retrieve `retrieval_max_k=10` candidates globally, apply score-ratio cutoff, then embedding pre-filter.

**Issue**:
- Score-ratio cutoff (`0.35 × best_score`) depends on the best score found; if best FAISS score is 0.267 (observed in logs), cutoff is 0.093 — very permissive, letting in many weak chunks
- In cross-lingual mode, many valid matches fall in the "ambiguous" band (0.2–0.35)
- Pre-filter threshold compounds the problem — it's tuned independently

**Solution**: **Two-stage retrieval**:
1. Retrieve more candidates (20–50) loosely — keep all
2. Rerank with a stronger signal (cross-encoder, semantic reranking)

---

### Problem 4: No Reciprocal Retrieval

**Current**: Direction is always `question → target_chunks` via `corpus.retrieve_relevant_chunks()` (`corpus.py:377`).

**Issue**:
- In bilingual mode, the source question may not align well with target passages
- Misses cases where target passages are topically similar but phrase differently

**Solution**: **Reciprocal retrieval** — also retrieve in reverse (`chunk_embedding → question`) and merge top results.

---

## Proposed Improvements

> **NOTE:** All changes must maintain **backward compatibility** with the current baseline. Each improvement must be toggleable via config flags. Use the existing `cost_optimization:` section of `config.yaml` as the canonical place for new flags.

---

### Tier 1: Quick Wins (< 30 min each)

#### 1A. Fix Pre-Filter Distance Metric

**File**: [src/mind/pipeline/pipeline.py](src/mind/pipeline/pipeline.py) line 1033

**Change**:
```python
# Current (line 1033):
similarity = float(np.dot(question_embedding, chunk_embedding))

# Proposed:
from sklearn.metrics.pairwise import cosine_similarity
q = question_embedding.reshape(1, -1)
c = chunk_embedding.reshape(1, -1)
similarity = float(cosine_similarity(q, c)[0, 0])
```

> `sklearn` is already available via `scipy>=1.9.0` dependencies; `sklearn.metrics.pairwise` is a safe choice. Alternatively, since `BAAI/bge-m3` uses `do_norm: True`, `np.dot` already equals cosine on normalized vectors — but guard against the case where it isn't:
```python
q_norm = question_embedding / (np.linalg.norm(question_embedding) + 1e-9)
c_norm = chunk_embedding / (np.linalg.norm(chunk_embedding) + 1e-9)
similarity = float(np.dot(q_norm, c_norm))
```

**Why**: Cosine similarity is bounded [-1, 1], thresholds are intuitive (0.5 = 50% similar). Works correctly for cross-lingual embeddings regardless of normalization state.

**Cost**: One extra norm per pair. Negligible for 10–20 candidates.

**Config change**: None required — existing `embedding_prefilter_threshold` continues to work but now has consistent semantics.

---

#### 1B. Dynamic Percentile-Based Score Cutoff

**File**: [src/mind/pipeline/pipeline.py](src/mind/pipeline/pipeline.py) lines 600–613

**Change**:
```python
# Instead of fixed ratio (0.35):
if self._retrieval_min_score_ratio > 0 and all_target_chunks:
    scores = [tc.metadata.get("score", 0) for tc in all_target_chunks]
    if scores:
        # Reinterpret ratio as percentile: 0.35 → keep top 65% of chunks
        cutoff = np.percentile(scores, (1 - self._retrieval_min_score_ratio) * 100)
        pre_count = len(all_target_chunks)
        all_target_chunks = [tc for tc in all_target_chunks if tc.metadata.get("score", 0) >= cutoff]
        self._logger.info(
            f"Percentile-based cutoff ({self._retrieval_min_score_ratio:.2f} → "
            f"p{(1-self._retrieval_min_score_ratio)*100:.0f}={cutoff:.3f}) "
            f"kept {len(all_target_chunks)}/{pre_count} chunks")
```

**Why**: The current ratio (`0.35 × best_score`) depends entirely on the best score found. When the best FAISS score is 0.267 (observed in production logs), the cutoff becomes 0.093 — nearly useless as a quality filter. Percentile-based filtering is data-driven and adapts to the score distribution regardless of absolute values.

**Config change**: Reinterpret `retrieval_min_score_ratio` as "fraction of chunks to retain" — `0.35` means "keep top 35% of retrieved chunks". **Backward compatible** as long as documentation is updated.

---

### Tier 2: Medium Effort (1–2 hours)

#### 2A. Cross-Encoder Reranking

**What**: A lightweight cross-encoder model reranks candidates after initial FAISS retrieval. This is the highest-impact improvement for bilingual use cases.

**Recommended models** (evaluated for bilingual EN↔ES/DE):

| Model | Params | Languages | Notes |
|-------|--------|-----------|-------|
| `cross-encoder/ms-marco-MiniLM-L-6-v2` | 22M | EN | Fast baseline, EN-only |
| `BAAI/bge-reranker-v2-m3` | 568M | Multilingual | Best for bilingual; same family as bge-m3 |
| `BAAI/bge-reranker-base` | 278M | EN+ZH | Lighter version |
| `jinaai/jina-reranker-v2-base-multilingual` | 278M | 100+ langs | Good alternative |

**Recommendation**: `BAAI/bge-reranker-v2-m3` — aligns with the existing `BAAI/bge-m3` embedder and is specifically designed for cross-lingual reranking. It uses the same model family, so consistency is maintained.

**Implementation** in `corpus.py` after `retrieve_relevant_chunks()`, or as a post-retrieval step in `pipeline.py`:
```python
# In pipeline.py, after all_target_chunks is assembled (line ~615):
if self._use_cross_encoder_rerank and all_target_chunks:
    from sentence_transformers import CrossEncoder
    # Cache this at pipeline init time, not here
    scores = self._cross_encoder.predict(
        [[question, chunk.text] for chunk in all_target_chunks],
        batch_size=32
    )
    # Re-sort by cross-encoder scores, update metadata
    ranked = sorted(zip(scores, all_target_chunks), reverse=True)
    all_target_chunks = [chunk for _, chunk in ranked]
    for score, chunk in ranked:
        chunk.metadata["cross_encoder_score"] = float(score)
```

**Initialization** (at pipeline setup, not per-query):
```python
if config.get("use_cross_encoder_rerank", False):
    from sentence_transformers import CrossEncoder
    self._cross_encoder = CrossEncoder(
        config.get("cross_encoder_model", "BAAI/bge-reranker-v2-m3")
    )
```

**Pros**:
- Directly addresses bilingual retrieval quality
- ~50–150ms for 10 pairs on CPU; negligible on GPU
- Cross-encoder inherently handles asymmetric query–document pairs

**Cons**: Extra model to load (~500MB for bge-reranker-v2-m3); adds inference latency.

**Config change**:
```yaml
cost_optimization:
  use_cross_encoder_rerank: false          # Toggle reranking
  cross_encoder_model: "BAAI/bge-reranker-v2-m3"  # Configurable model
```

---

#### 2B. Bidirectional / Reciprocal Retrieval

**What**: Retrieve both `question → chunks` and `chunk → question`, merge results.

**Implementation** in [src/mind/pipeline/corpus.py](src/mind/pipeline/corpus.py), adding a new method alongside `retrieve_relevant_chunks()`:
```python
def retrieve_relevant_chunks_bidirectional(self, query: str, theta_query=None, top_k: int = None):
    """Two-directional retrieval: forward (question→chunks) + reverse (chunk→question)."""
    top_k = top_k or self.retriever.top_k
    
    # Forward: question → chunks (existing path)
    forward = self.retrieve_relevant_chunks(query, theta_query, top_k=top_k * 2)
    
    # Reverse: re-score forward results by similarity to query
    # Use the forward chunks as "pseudo-queries" to identify best matches
    reverse_scores = {}
    if hasattr(self.retriever, 'encode_queries'):
        query_emb = self.retriever.encode_queries(query)
        for chunk in forward:
            chunk_emb = self.retriever.encode_queries(chunk.text)
            q_norm = query_emb / (np.linalg.norm(query_emb) + 1e-9)
            c_norm = chunk_emb / (np.linalg.norm(chunk_emb) + 1e-9)
            reverse_scores[chunk.id] = float(np.dot(q_norm, c_norm))
    
    # Merge: combine forward FAISS score with reverse cosine score
    for chunk in forward:
        fwd_score = chunk.metadata.get("score", 0)
        rev_score = reverse_scores.get(chunk.id, 0)
        chunk.metadata["score"] = 0.6 * fwd_score + 0.4 * rev_score  # tunable alpha
    
    return sorted(forward, key=lambda c: c.metadata["score"], reverse=True)[:top_k]
```

**Pros**: Catches "opposite direction" matches missed by forward-only retrieval. No extra model needed.

**Cons**: ~2× encoding calls for the reverse pass (mitigated if cross-encoder is already running).

**Config change**:
```yaml
cost_optimization:
  use_bidirectional_retrieval: false
  bidirectional_alpha: 0.6  # Weight of forward score vs reverse score
```

---

#### 2C. Sparse / Dense Hybrid Retrieval

**What**: Combine dense (FAISS embedding) retrieval with sparse (BM25/TF-IDF) retrieval. Dense retrieval excels at semantic similarity; sparse retrieval excels at exact keyword matching. Hybrid is especially valuable for queries with domain-specific terminology.

**Assessment against current codebase**:
- Current `IndexRetriever` only supports FAISS (dense). BM25 would require a new index type.
- `pyproject.toml` does not include `rank_bm25` or `elasticsearch`. Adding BM25 means a new dependency.
- The topic-stratified index structure means BM25 indices would also need to be per-topic.

**Implementation options**:
1. **BM25 via `rank_bm25`** (lightweight, no server): Add `rank_bm25>=0.2.2` to dependencies. Build per-topic BM25 indices alongside FAISS indices. Score fusion with Reciprocal Rank Fusion (RRF).
2. **Sparse via Qdrant/Weaviate** (heavier): Replace FAISS — not recommended as it breaks the current index structure.

**Recommended**: Option 1 with RRF for score fusion:
```python
# RRF fusion — standard formula, k=60 is a common default
def rrf_score(rank, k=60):
    return 1.0 / (k + rank)

# After getting dense_results (FAISS) and sparse_results (BM25):
scores = {}
for rank, result in enumerate(dense_results):
    scores[result["doc_id"]] = rrf_score(rank)
for rank, result in enumerate(sparse_results):
    scores[result["doc_id"]] = scores.get(result["doc_id"], 0) + rrf_score(rank)
```

**Config change**:
```yaml
cost_optimization:
  use_hybrid_retrieval: false
  hybrid_sparse_weight: 0.5  # 0 = pure dense, 1 = pure sparse
```

> **Gap**: This requires building and persisting BM25 indices in `retriever.py:index()`. The `build_or_load_index()` method would need to be extended. This is the highest-effort item in Tier 2.

---

## Testing Strategy

> One of the most important parts of this plan. We need **clear, replicable experiments** that can be run both pre- and post-changes to measure retrieval quality objectively. The baseline best FAISS score observed in logs is ~0.267 — this is the number to beat.

### Existing Infrastructure

The ablation framework already exists at [ablation/retrieval/](ablation/retrieval/) with:
- `get_relevant_passages.py` — runs ENN, ANN, TB-ENN, TB-ANN for all queries and saves results
- `generate_table_eval.py` — computes Precision@k, Recall@k, MRR@k, NDCG@k with bootstrap CIs and Wilcoxon significance tests
- `get_gold_passages.py` — generates ground-truth relevant passages via LLM judge

Supported metrics: **MRR@3, MRR@5, Precision@3, Precision@5, Recall@3, Recall@5, NDCG@3, NDCG@5** with 95% bootstrap CIs and Holm-adjusted Wilcoxon significance testing.

### New Test Scripts Required

The following scripts should live in [bash_scripts/](bash_scripts/) and follow the pattern of `run_retrieval.sh`:

#### `bash_scripts/eval_retrieval_baseline.sh`
Run the existing pipeline without any Tier 1/2 changes. Captures the baseline across all metric dimensions.

```bash
#!/usr/bin/env bash
# Baseline retrieval evaluation — run BEFORE any changes
set -euo pipefail

MODEL_NAME="BAAI/bge-m3"
PATH_SOURCE="<your_corpus_path>"
PATH_MODEL_DIR="<your_model_dir>"
PATH_SAVE_INDICES="<your_index_path>/baseline/${MODEL_NAME}"
PATH_OUT="<your_output_path>/baseline/${MODEL_NAME}"

mkdir -p "$PATH_SAVE_INDICES" "$PATH_OUT"

python3 ablation/retrieval/get_relevant_passages.py \
  --model_name "$MODEL_NAME" \
  --path_source "$PATH_SOURCE" \
  --path_queries_dir "<your_queries_dir>" \
  --path_model_dir "$PATH_MODEL_DIR" \
  --path_save_indices "$PATH_SAVE_INDICES" \
  --out_dir "$PATH_OUT"

echo "Baseline complete. Results at $PATH_OUT"
```

#### `bash_scripts/eval_retrieval_improved.sh`
Run after applying Tier 1 + Tier 2 changes. Same structure as baseline but pointing to an "improved" output directory and using updated config flags.

```bash
#!/usr/bin/env bash
# Improved retrieval evaluation — run AFTER applying changes
set -euo pipefail

MODEL_NAME="BAAI/bge-m3"
PATH_SOURCE="<your_corpus_path>"
PATH_MODEL_DIR="<your_model_dir>"
PATH_SAVE_INDICES="<your_index_path>/improved/${MODEL_NAME}"
PATH_OUT="<your_output_path>/improved/${MODEL_NAME}"

# Pass new config flags as env vars or CLI args (update get_relevant_passages.py if needed)
USE_COSINE_PREFILTER=true
USE_PERCENTILE_CUTOFF=true
USE_CROSS_ENCODER=true

mkdir -p "$PATH_SAVE_INDICES" "$PATH_OUT"

python3 ablation/retrieval/get_relevant_passages.py \
  --model_name "$MODEL_NAME" \
  --path_source "$PATH_SOURCE" \
  --path_queries_dir "<your_queries_dir>" \
  --path_model_dir "$PATH_MODEL_DIR" \
  --path_save_indices "$PATH_SAVE_INDICES" \
  --out_dir "$PATH_OUT" \
  --use_cosine_prefilter \
  --use_percentile_cutoff \
  --use_cross_encoder_rerank

echo "Improved run complete. Results at $PATH_OUT"
```

#### `bash_scripts/compare_retrieval.sh`
Compare baseline vs improved using the existing `generate_table_eval.py`:

```bash
#!/usr/bin/env bash
# Compare baseline vs improved retrieval metrics
set -euo pipefail

PATH_GOLD="<path_to_gold_annotations>.parquet"
PATH_BASELINE_RESULTS="<your_output_path>/baseline/${MODEL_NAME}/topic_15"
PATH_IMPROVED_RESULTS="<your_output_path>/improved/${MODEL_NAME}/topic_15"

echo "=== BASELINE ==="
python3 ablation/retrieval/generate_table_eval.py \
  --path_gold_relevant "$PATH_GOLD" \
  --paths_found_relevant "$PATH_BASELINE_RESULTS" \
  --tpc 15

echo "=== IMPROVED ==="
python3 ablation/retrieval/generate_table_eval.py \
  --path_gold_relevant "$PATH_GOLD" \
  --paths_found_relevant "$PATH_IMPROVED_RESULTS" \
  --tpc 15
```

### Metrics Checklist

For each experiment (baseline and each improvement), report:

| Metric | Threshold to Consider "Improved" |
|--------|----------------------------------|
| Recall@5 | +5% absolute over baseline |
| MRR@5 | +5% absolute over baseline |
| NDCG@5 | +3% absolute over baseline |
| Avg best FAISS score | From 0.267 → >0.35 |
| LLM call count | Should not increase |

### Required Updates to `get_relevant_passages.py`

The current ablation script at [ablation/retrieval/get_relevant_passages.py](ablation/retrieval/get_relevant_passages.py) tests ENN/ANN/TB-ENN/TB-ANN but does **not** expose the Tier 1/2 improvements. To enable A/B testing, add CLI flags:
- `--use_cosine_prefilter` (Tier 1A)
- `--use_percentile_cutoff` (Tier 1B)
- `--use_cross_encoder_rerank` (Tier 2A)
- `--cross_encoder_model` (Tier 2A)
- `--use_bidirectional` (Tier 2B)

This is a **gap that needs to be filled** before the testing scripts above will work end-to-end.

---

## Config Changes Summary

**Current** (after threshold tuning):
```yaml
cost_optimization:
  embedding_prefilter_threshold: 0.250
  retrieval_min_score_ratio: 0.35
  retrieval_max_k: 10
```

**Proposed** (all improvements enabled, backward-compatible defaults):
```yaml
cost_optimization:
  # Tier 1A: cosine instead of dot-product pre-filter
  # (code change in pipeline.py; no new config key needed)
  embedding_prefilter_threshold: 0.250  # now stable as cosine sim threshold

  # Tier 1B: percentile-based score cutoff
  # Reinterpret: 0.35 → keep top 35% of retrieved chunks
  retrieval_min_score_ratio: 0.35       # semantics changed; see Tier 1B notes

  # Tier 2A: cross-encoder reranking (default off)
  use_cross_encoder_rerank: false
  cross_encoder_model: "BAAI/bge-reranker-v2-m3"

  # Tier 2B: bidirectional retrieval (default off)
  use_bidirectional_retrieval: false
  bidirectional_alpha: 0.6

  # Tier 2C: hybrid sparse/dense retrieval (default off)
  use_hybrid_retrieval: false
  hybrid_sparse_weight: 0.5

  # Existing params
  retrieval_max_k: 10
  use_merged_evaluation: true
  skip_subquery_generation: true
  max_questions_per_chunk: 3
```

---

## Expected Outcomes

| Change | Latency Impact | Recall@5 Impact | Precision@5 Impact | Risk |
|--------|---|---|---|---|
| Tier 1A (cosine prefilter) | +1% | +5–10% | Neutral | Low |
| Tier 1B (percentile cutoff) | +0% | +3–8% | Neutral | Low |
| Tier 2A (cross-encoder rerank) | +50–150ms/query | +15–25% | +10–20% | Medium |
| Tier 2B (bidirectional) | +2× encode calls | +5–10% | Neutral | Medium |
| Tier 2C (hybrid BM25) | +10–30ms | +5–15% | +5–10% | High |

**Bilingual-specific**: Tier 2A with `BAAI/bge-reranker-v2-m3` likely has the highest impact for bilingual (EN↔ES/DE) use cases.

**Recommended implementation order**: 1A → 1B → measure → 2A → measure → 2B → measure. Avoid activating multiple changes simultaneously before evaluating each independently.

---

## Architectural Alignment

### What Already Exists

- **Multi-method FAISS** (`retriever.py`): ENN, ANN, TB-ENN, TB-ANN — all toggled via `method:` config. New improvements should follow this toggle pattern.
- **Cost optimization flags** (`pipeline.py` + `config.yaml`): The existing `cost_optimization:` section is the right home for new feature flags.
- **Batch encoding** (`retriever.encode_queries()`): Any new reranking must reuse this method — do not introduce a second encoder instance.
- **Ablation framework** (`ablation/retrieval/`): Full evaluation pipeline exists. Extend `get_relevant_passages.py` rather than writing from scratch.
- **Dynamic thresholds** (`retriever.dynamic_thresholds()`): The system already uses data-driven thresholds for topic assignment. The percentile-based score cutoff (Tier 1B) is consistent with this philosophy.

### What Needs to Be Built

- `get_relevant_passages.py` CLI flags for new improvement toggles
- Cross-encoder initialization and caching at pipeline startup
- BM25 index building in `retriever.index()` (Tier 2C only)
- `bash_scripts/eval_retrieval_baseline.sh` and `bash_scripts/eval_retrieval_improved.sh`

---

## Open Questions / Gaps Requiring User Input

1. **Tier 1B semantics change**: Reinterpreting `retrieval_min_score_ratio` as "fraction to keep" is a breaking change in semantics (though value 0.35 maps reasonably). Should this be a new key (`retrieval_min_score_percentile`) to be explicit?

If we are going to dinamically tackle this score, we should at least consider it in the config yaml. Can we convert it to a string to be parsed into a number or the word dynamic? In this way the user can still fix it or just let the system find the best option.

2. **Cross-encoder model size**: `BAAI/bge-reranker-v2-m3` is 568MB. Is this acceptable for the deployment environment? If memory-constrained, `bge-reranker-base` (278MB) is a drop-in alternative.

For the moment we can use the 568MB version, if it is not good enough we can change to the lighter one.

3. **Gold annotations for testing**: `generate_table_eval.py` requires pre-computed gold relevance annotations (`_all_added.parquet`) judged by multiple LLMs. Are these available for the current bilingual corpus, or do they need to be regenerated via `get_gold_passages.py`?

I think there is, however maybe not in the codebase, I will need to find it or to create one. 

4. **Bilingual topic thresholds**: `dynamic_thresholds()` is computed per-language separately. Is the same threshold set used for EN and ES/DE indices, or should each have its own CDF?

Im guessing that to each their own, however it can increase the complexity. AS a rule of thumb, lets try to be coherent with what has already been developed and aim for simplicity.
