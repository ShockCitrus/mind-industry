# Detection Step: LLM Cost Optimization Guide

> **Document Version:** 1.0  
> **Last Updated:** 2026-03-01  
> **Target Audience:** AI Agents implementing optimizations, human reviewers  
> **Scope:** Reducing LLM API call count in the MIND contradiction detection pipeline  
> **Prerequisite Reading:** [optimization-guide.md](file:///home/alonso/Projects/Mind-Industry/docs/implementation_artifacts/optimization-guide.md) (for existing OPT-001 through OPT-012)

---

## Table of Contents

1. [Problem Statement](#1-problem-statement)
2. [Current Pipeline Architecture](#2-current-pipeline-architecture)
3. [Call Count Analysis](#3-call-count-analysis)
4. [External Repository Evaluation](#4-external-repository-evaluation)
5. [Optimization Strategies](#5-optimization-strategies)
6. [Implementation Plan](#6-implementation-plan)
7. [Verification Plan](#7-verification-plan)

---

## 1. Problem Statement

The MIND detection pipeline's primary cost driver is the **multiplicative explosion of LLM API calls** during contradiction detection. For each source chunk, the pipeline generates questions, creates subqueries, retrieves target chunks, checks relevance, generates answers, and classifies contradictions — each step requiring a separate LLM call. Even for small datasets (e.g., 100 source chunks), this produces **thousands of LLM calls**, making operation prohibitively expensive.

> [!IMPORTANT]
> This guide focuses specifically on **reducing the total number of LLM API calls** (the cost multiplier), NOT on latency or throughput optimizations (already addressed by OPT-010 batched calls in the existing optimization guide).

### What Already Exists

The existing [optimization-guide.md](file:///home/alonso/Projects/Mind-Industry/docs/implementation_artifacts/optimization-guide.md) covers:
- **OPT-010**: Batched LLM calls via `prompt_batch()` — reduces *latency* by running calls concurrently, but does NOT reduce call *count*
- **OPT-002**: Batched query embeddings — speeds up retrieval, not LLM calls
- **OPT-004**: Async checkpoint writes — I/O optimization only

**None of these address the fundamental problem: there are too many calls to begin with.**

---

## 2. Current Pipeline Architecture

### 2.1 Call Flow Per Source Chunk

The current pipeline ([pipeline.py](file:///home/alonso/Projects/Mind-Industry/src/mind/pipeline/pipeline.py)) processes each source chunk through a nested loop structure:

```
For each SOURCE CHUNK in topic:
│
├── 🔴 LLM CALL 1: _generate_questions(chunk)
│   └── Prompt: question_generation.txt → generates N yes/no questions
│
└── For each QUESTION (N questions):
    │
    ├── 🔴 LLM CALL 2: _generate_answer(question, source_chunk)
    │   └── Prompt: question_answering.txt → answer from source passage
    │
    ├── 🔴 LLM CALL 3: _generate_subqueries(question, chunk)
    │   └── Prompt: query_generation.txt → search queries for retrieval
    │
    └── For each TARGET CHUNK (M chunks retrieved per subquery):
        │
        ├── 🔴 LLM CALL 4: _check_is_relevant(question, target_chunk)
        │   └── Prompt: relevance_checking.txt → YES/NO relevance
        │
        ├── 🔴 LLM CALL 5: _generate_answer(question, target_chunk)
        │   └── Prompt: question_answering.txt → answer from target passage
        │   └── (Only if relevant)
        │
        └── 🔴 LLM CALL 6: _check_contradiction(question, a_s, a_t)
            └── Prompt: discrepancy_detection.txt → classification
            └── (Only if target answer is meaningful)
```

### 2.2 Prompt Templates Summary

| Step | Prompt File | Purpose | Input Size |
|------|-------------|---------|------------|
| Question Generation | [question_generation.txt](file:///home/alonso/Projects/Mind-Industry/src/mind/pipeline/prompts/question_generation.txt) | Generate yes/no questions from passage | ~500 tokens |
| Source Answer | [question_answering.txt](file:///home/alonso/Projects/Mind-Industry/src/mind/pipeline/prompts/question_answering.txt) | Answer question using source passage | ~600 tokens |
| Subquery Generation | [query_generation.txt](file:///home/alonso/Projects/Mind-Industry/src/mind/pipeline/prompts/query_generation.txt) | Generate search queries for retrieval | ~400 tokens |
| Relevance Check | [relevance_checking.txt](file:///home/alonso/Projects/Mind-Industry/src/mind/pipeline/prompts/relevance_checking.txt) | Check if target passage is relevant | ~300 tokens |
| Target Answer | question_answering.txt | Answer question using target passage | ~600 tokens |
| Contradiction Check | [discrepancy_detection.txt](file:///home/alonso/Projects/Mind-Industry/src/mind/pipeline/prompts/discrepancy_detection.txt) | Classify discrepancy type | ~800 tokens |

---

## 3. Call Count Analysis

### 3.1 Formula

For a single topic with `C` source chunks, assuming:
- `Q` = average questions per chunk (typically 2-4)
- `S` = average subqueries per question (typically 1-2)
- `T` = average target chunks retrieved per subquery (typically 5-10, controlled by `top_k`)
- `r` = relevance hit rate (~50-70%)

**Total LLM calls per topic:**

```
Calls = C × [1 + Q × (1 + 1 + S × T × (1 + r + r))]
      = C × [1 + Q × (2 + S × T × (1 + 2r))]
```

### 3.2 Concrete Example

For a small dataset: `C=50`, `Q=3`, `S=2`, `T=5`, `r=0.6`:

```
Calls = 50 × [1 + 3 × (2 + 2 × 5 × (1 + 1.2))]
      = 50 × [1 + 3 × (2 + 22)]
      = 50 × [1 + 72]
      = 50 × 73
      = 3,650 LLM calls
```

> [!CAUTION]
> For a moderate dataset of 500 chunks, this exceeds **36,500 calls**. With Gemini API pricing at ~$0.0375/1K input+output tokens and ~600 avg tokens per call, this costs approximately **$0.82 per topic** — and real datasets have multiple topics.

### 3.3 Where the Calls Multiply

| Step | Calls per Chunk | % of Total | Addressable? |
|------|-----------------|------------|--------------|
| Question Generation | 1 | 1.4% | Yes (merge with subquery) |
| Source Answer | Q = 3 | 4.1% | Yes (can eliminate) |
| Subquery Generation | Q = 3 | 4.1% | Yes (can eliminate) |
| **Relevance Check** | **Q × S × T = 30** | **41.1%** | **High priority** |
| **Target Answer** | **Q × S × T × r = 18** | **24.7%** | **High priority** |
| **Contradiction Check** | **Q × S × T × r = 18** | **24.7%** | **Medium priority** |

The inner loop (relevance → answer → classify) consumes **~90% of all LLM calls**.

---

## 4. External Repository Evaluation

### 4.1 LCoT2Tree — Long Chain-of-Thought Analysis with GNN

**Repository:** [GangweiJiang/LCoT2Tree](https://github.com/GangweiJiang/LCoT2Tree)

#### What It Does
LCoT2Tree is a **post-hoc analysis framework** for understanding long chain-of-thought (CoT) reasoning produced by LLMs like DeepSeek-R1. Its pipeline:
1. Generates model outputs using LightEval on math tasks
2. Splits CoT into individual thought nodes
3. Extracts reasoning sketches and assigns functions to thoughts
4. Builds a tree structure from the thoughts
5. Trains a Graph Neural Network (GIN) to classify/explain reasoning patterns
6. Uses GNN explainability to identify which thought patterns lead to correct/incorrect answers

#### Critical Assessment for Our Use Case

> [!WARNING]
> **Verdict: NOT APPLICABLE to our problem.**

| Dimension | LCoT2Tree | Our Need |
|-----------|-----------|----------|
| **Problem type** | Post-hoc analysis of existing CoT outputs | Reduce the number of LLM calls during pipeline execution |
| **Domain** | Mathematical reasoning (MATH-500) | Cross-document contradiction detection in natural language |
| **LLM usage** | Generates CoT *once*, then analyzes offline | Needs to reduce generation calls themselves |
| **GNN role** | Classifies reasoning quality after the fact | We need to reduce calls *before* they happen |
| **Data requirements** | Requires many CoT traces for training | We have passage-question-answer triplets, completely different structure |
| **Infrastructure** | Requires GPU for GNN training, LightEval, Volcengine SDK | Adds significant complexity for no clear benefit |

**Why it doesn't help:** LCoT2Tree is designed to understand *why* LLMs make mistakes in mathematical reasoning by analyzing the structure of their thought chains. It does not address reducing LLM call volume. Its GNN-based approach requires a different kind of training data (thought trees) that has no mapping to our passage-level contradiction detection problem.

**What we could theoretically borrow:** The concept of structuring reasoning as a tree and pruning unproductive branches. However, this idea is better served by simpler heuristics (see Strategy 3 below) without the overhead of GNN training.

---

### 4.2 RATT — Retrieval Augmented Thought Tree

**Repository:** [jinghanzhang1998/RATT](https://github.com/jinghanzhang1998/RATT)  
**Paper:** [arXiv:2406.02746](https://arxiv.org/abs/2406.02746)

#### What It Does
RATT combines Tree of Thought (ToT) with Retrieval-Augmented Generation (RAG) to improve factual correctness and logical coherence. Its pipeline:
1. Generates N drafts using N "agents" (multiple LLM calls with high temperature)
2. Splits each draft into paragraphs
3. For each paragraph: generates a search query → retrieves web content → fact-checks and revises the paragraph against retrieved content
4. Merges all agent drafts into a refined unified answer
5. Iterates for M steps, each time expanding and revising based on previous answers

#### Critical Assessment for Our Use Case

> [!CAUTION]
> **Verdict: NOT RECOMMENDED — it would INCREASE our cost, not decrease it.**

**Quantitative analysis of RATT's call count:**
- Per step: `N_agents × (1 draft + P paragraph revisions × 3 web sources) + 1 merge`
- With defaults (3 agents, 3 steps, ~5 paragraphs): **3 × (1 + 5×3×2) + 1 = 94 calls per step × 3 steps = ~282+ LLM calls per question**
- This is **orders of magnitude worse** than our current approach

| Dimension | RATT | Our Need |
|-----------|------|----------|
| **Call volume** | Extremely high (100+ calls per question) | We need to reduce from ~73 to <20 per chunk |
| **Design goal** | Maximize answer quality at any cost | Minimize cost while maintaining detection quality |
| **RAG approach** | Web search (Google API) | We have a fixed corpus with FAISS indices |
| **Relevance** | Creative writing, open-ended QA | Binary/categorical classification of discrepancies |
| **Complexity** | Multi-agent, multi-step iterative refinement | We need simpler, direct classification |

**What we can genuinely borrow from RATT's concepts:**
1. **Generate-then-verify pattern**: The idea of generating a draft answer and then verifying it against retrieved evidence. We already do this — it's our core pipeline.
2. **Lookahead/pruning at each reasoning step**: RATT evaluates whether to continue down a thought branch. We could apply similar early-exit logic (see Strategy 3).

**Key insight from analyzing RATT:** The paper demonstrates that simply doing more LLM calls with more retrieval does improve factual correctness. But this is the opposite of what we need. Our situation calls for maintaining quality with **fewer** calls, not achieving marginally better quality with **many more** calls.

---

### 4.3 Summary of External Repo Analysis

| Repository | Useful for Us? | Core Reason |
|------------|---------------|-------------|
| LCoT2Tree | ❌ No | Post-hoc CoT analysis tool; completely different problem domain |
| RATT | ❌ No (as-is) | Would multiply our already excessive call count by 10-100x |

> [!TIP]
> **The most impactful optimizations come from rethinking our own pipeline structure**, not from importing external frameworks designed for different problems. The strategies in the next section draw on well-established NLI/NLP patterns that directly address our cost problem.

---

## 5. Optimization Strategies

### Strategy 1: Merged Prompt — Eliminate Separate Answer + Classify Steps
**Impact: ~40-50% call reduction | Effort: Low**

Currently, for each relevant target chunk we make TWO separate calls:
1. `_generate_answer(question, target_chunk)` — answer the question from the target
2. `_check_contradiction(question, a_s, a_t)` — classify the discrepancy

These can be **merged into a single prompt** that answers the question AND classifies the discrepancy in one call, providing the source answer for comparison directly.

#### Merged Prompt Design

```
You will be given a QUESTION, a SOURCE_ANSWER (derived from one passage), and a
TARGET_PASSAGE. Your tasks are:

1. Determine whether the TARGET_PASSAGE contains information to answer the QUESTION.
   If NO, output DISCREPANCY_TYPE: NOT_ENOUGH_INFO and stop.

2. If YES, extract the answer from the TARGET_PASSAGE and classify the relationship
   between the SOURCE_ANSWER and the extracted answer.

{categories_block}

Response Format:
- TARGET_ANSWER: [Answer derived from the target passage, or "N/A" if not relevant]
- REASON: [Brief explanation]
- DISCREPANCY_TYPE: [Category]

{examples_block}

#### YOUR TASK ####
QUESTION: {question}
SOURCE_ANSWER: {answer_s}
TARGET_PASSAGE: {target_passage}
```

This eliminates:
- The separate `_check_is_relevant` call (now embedded in the merged prompt)
- The separate `_generate_answer` for target (now embedded)
- Keeps only the merged classification call

**Result:** 3 calls → 1 call per target chunk.

#### Implementation Details

**Files to modify:**

##### [MODIFY] [pipeline.py](file:///home/alonso/Projects/Mind-Industry/src/mind/pipeline/pipeline.py)

1. Create a new method `_evaluate_pair_merged()` that replaces the current `_evaluate_pair()`:
```python
def _evaluate_pair_merged(self, question, a_s, source_chunk, target_chunk, topic, subquery, path_save=None, save=True):
    """Evaluate a source-target pair with a single merged LLM call."""
    template_formatted = self.prompts["merged_evaluation"].format(
        question=question,
        answer_s=a_s,
        target_passage=target_chunk.text,
    )
    response, _ = self._prompter.prompt(
        question=template_formatted,
        dry_run=self.dry_run
    )
    # Parse response for TARGET_ANSWER, REASON, DISCREPANCY_TYPE
    a_t, discrepancy_label, reason = self._parse_merged_response(response)
    # ... rest of logging and saving logic unchanged
```

2. Add a parsing method `_parse_merged_response()` to extract all three fields from the merged response.

3. Register the new prompt template in `__init__` under `self.prompts["merged_evaluation"]`.

##### [NEW] [merged_evaluation.txt](file:///home/alonso/Projects/Mind-Industry/src/mind/pipeline/prompts/merged_evaluation.txt)

Create the merged prompt template as described above.

##### [NEW] [merged_evaluation_dynamic.txt](file:///home/alonso/Projects/Mind-Industry/src/mind/pipeline/prompts/merged_evaluation_dynamic.txt)

Dynamic version supporting custom categories (same structure as `discrepancy_detection_dynamic.txt` but for the merged prompt).

---

### Strategy 2: Eliminate Subquery Generation — Use Questions Directly
**Impact: ~15-20% call reduction | Effort: Low**

Currently, for each question, we make a separate LLM call to `_generate_subqueries()` to create search queries for retrieval. But the generated questions are already well-formed yes/no queries suitable for retrieval.

#### Approach

Instead of calling the LLM to generate subqueries, derive retrieval queries directly:
1. Use the **question itself** as the primary retrieval query
2. Optionally extract **key noun phrases** from the question using lightweight NLP (spaCy entities/noun chunks) as secondary queries — no LLM call needed

```python
def _get_retrieval_queries(self, question: str, chunk) -> list[str]:
    """Derive retrieval queries without LLM calls."""
    queries = [question]  # Primary: the question itself

    # Optional: add key entities/phrases for broader recall
    # This uses spaCy (already a project dependency) instead of LLM
    doc = self._nlp(question)
    noun_phrases = [np.text for np in doc.noun_chunks if len(np.text.split()) > 1]
    if noun_phrases:
        queries.append(" ".join(noun_phrases))

    return queries
```

**Files to modify:**
- [pipeline.py](file:///home/alonso/Projects/Mind-Industry/src/mind/pipeline/pipeline.py): Replace `_generate_subqueries()` call in `_process_question()` with `_get_retrieval_queries()`

**Trade-off:** The question was designed for human-like search queries. Using it directly as a retrieval query may yield slightly different recall. **Mitigation:** The sentence-transformer embeddings used for FAISS retrieval handle semantic similarity well with natural-language questions, so direct use should maintain comparable retrieval quality.

---

### Strategy 3: Embedding-Based Pre-Filter — Skip Irrelevant Pairs Early
**Impact: ~20-40% call reduction | Effort: Medium**

Before calling the LLM on any target chunk, use the **already-computed embeddings** to filter out obviously irrelevant pairs. This replaces many `_check_is_relevant` LLM calls with a fast embedding cosine similarity check.

#### Approach

```python
def _prefilter_target_chunks(self, question: str, target_chunks: list, threshold: float = 0.3) -> list:
    """Filter target chunks by embedding similarity before making LLM calls."""
    question_embedding = self.target_corpus._retriever.encode_queries(question)

    filtered = []
    for chunk in target_chunks:
        chunk_embedding = chunk.metadata.get("embedding")
        if chunk_embedding is not None:
            similarity = np.dot(question_embedding.flatten(), chunk_embedding.flatten())
            if similarity >= threshold:
                filtered.append(chunk)
            else:
                self._logger.info(
                    f"Pre-filtered chunk {chunk.id} (sim={similarity:.3f} < {threshold})")
        else:
            filtered.append(chunk)  # Keep if no embedding available

    return filtered
```

**Why this works:** The retriever already uses embedding similarity to find target chunks, but it retrieves based on *subquery* similarity, not *question* similarity. Some retrieved chunks may be tangentially related to the subquery but irrelevant to the actual question. A secondary cosine-similarity check against the question itself can eliminate these without an LLM call.

**Files to modify:**
- [pipeline.py](file:///home/alonso/Projects/Mind-Industry/src/mind/pipeline/pipeline.py): Add `_prefilter_target_chunks()` and call it before the target chunk loop in `_process_question()`
- [corpus.py](file:///home/alonso/Projects/Mind-Industry/src/mind/pipeline/corpus.py): Store embeddings in chunk metadata during indexing

**Threshold tuning:** Start with `threshold=0.3` (permissive — only removes clearly irrelevant chunks). Tune based on validation data.

---

### Strategy 4: NLI-Based Pre-Filter — Replace LLM Relevance Check with Local Model
**Impact: ~40% call reduction of inner loop | Effort: Medium**

Replace the LLM-based `_check_is_relevant()` call with a lightweight local NLI (Natural Language Inference) model. The pipeline already has NLI infrastructure (`_check_entailment` using DeBERTa), so this extends that pattern.

#### Approach

Use a cross-encoder or NLI model to score (question, target_passage) relevance locally:

```python
def _check_is_relevant_local(self, question: str, chunk) -> tuple[int, str]:
    """Check relevance using local NLI model instead of LLM API call."""
    from transformers import pipeline as hf_pipeline

    if not hasattr(self, '_relevance_classifier'):
        self._relevance_classifier = hf_pipeline(
            "zero-shot-classification",
            model="cross-encoder/nli-deberta-v3-base",
            device=0 if torch.cuda.is_available() else -1
        )

    result = self._relevance_classifier(
        chunk.text,
        candidate_labels=[question],
        hypothesis_template="This passage answers the question: {}",
    )
    relevance_score = result['scores'][0]
    is_relevant = 1 if relevance_score > 0.5 else 0
    return is_relevant, f"NLI score: {relevance_score:.3f}"
```

Alternatively, use a simpler sentence-transformer cross-encoder:

```python
from sentence_transformers import CrossEncoder

# Load once in __init__
self._cross_encoder = CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')

def _check_is_relevant_local(self, question: str, chunk) -> tuple[int, str]:
    score = self._cross_encoder.predict([(question, chunk.text)])[0]
    return (1 if score > 0.0 else 0), f"CE score: {score:.3f}"
```

**Files to modify:**
- [pipeline.py](file:///home/alonso/Projects/Mind-Industry/src/mind/pipeline/pipeline.py): Add local relevance method and toggle via config
- [config.yaml](file:///home/alonso/Projects/Mind-Industry/config/config.yaml): Add `mind.relevance_method: "local"` vs `"llm"` config option

**GPU consideration:** The cross-encoder runs on CPU acceptably (ms-marco-MiniLM-L-6 is 22M params). On GPU it's even faster. This is much cheaper than an LLM API call.

---

### Strategy 5: Reduce Question Count — Quality Over Quantity
**Impact: ~25-50% call reduction (linear) | Effort: Low**

Currently, the LLM generates 2-4 questions per chunk, each spawning the entire inner loop. Reducing to 1-2 high-quality questions per chunk cuts total calls proportionally.

#### Approach A: Prompt Engineering

Modify [question_generation.txt](file:///home/alonso/Projects/Mind-Industry/src/mind/pipeline/prompts/question_generation.txt) to explicitly request fewer, higher-quality questions:

```diff
- Your task is to generate such questions that would lead a retrieval system
- to find the passage and use it to generate an answer.
+ Your task is to generate exactly ONE or TWO such questions that capture the
+ most important factual claims in the passage. Focus on the single most
+ significant and verifiable factual claim. Only generate a second question
+ if the passage contains a clearly distinct second factual claim.
```

#### Approach B: Configurable Question Limit

Add a `max_questions_per_chunk` config parameter and truncate after filtering:

```python
# In _process_chunk, after generating and filtering questions:
max_q = self.config.get("max_questions_per_chunk", 2)
questions = questions[:max_q]
```

**Files to modify:**
- [question_generation.txt](file:///home/alonso/Projects/Mind-Industry/src/mind/pipeline/prompts/question_generation.txt): Prompt modification
- [pipeline.py](file:///home/alonso/Projects/Mind-Industry/src/mind/pipeline/pipeline.py): Add configurable limit in `_process_chunk()`
- [config.yaml](file:///home/alonso/Projects/Mind-Industry/config/config.yaml): Add `mind.max_questions_per_chunk` parameter

---

### Strategy 6: Reduce Retrieved Target Count
**Impact: ~20-40% call reduction | Effort: Low**

The `top_k` parameter in retrieval controls how many target chunks are compared per subquery. Reducing this from the default (e.g., 10) to a lower value (e.g., 3-5) has a linear effect on call count.

#### Approach: Dynamic top_k with Relevance Cutoff

Instead of a fixed `top_k`, use a similarity-score cutoff to only return chunks above a threshold:

```python
def retrieve_with_cutoff(self, query, theta_query, max_k=10, min_similarity=0.4):
    """Retrieve up to max_k chunks, but stop early if similarity drops."""
    results = self.retrieve(query, theta_query, top_k=max_k)
    filtered = [r for r in results if r['score'] >= min_similarity]
    return filtered
```

**Files to modify:**
- [retriever.py](file:///home/alonso/Projects/Mind-Industry/src/mind/pipeline/retriever.py): Add `retrieve_with_cutoff()` method
- [pipeline.py](file:///home/alonso/Projects/Mind-Industry/src/mind/pipeline/pipeline.py): Use cutoff retrieval in `_process_question()`
- [config.yaml](file:///home/alonso/Projects/Mind-Industry/config/config.yaml): Add `mind.retrieval_min_similarity` parameter

---

### Strategy 7: Source Answer Caching Across Questions
**Impact: ~5-10% | Effort: Very Low**

The pipeline already caches preloaded answers in `chunk.metadata["answers"]`. Extend this to cache generated answers so that if the same chunk-question pair appears across different topics, the answer is reused.

Already partially implemented via `seen_triplets` — but answers are not cached, only the triplet dedup is performed. Add proper answer caching.

---

## 6. Implementation Plan

### 6.1 Priority Order

| Priority | Strategy | Call Reduction | Effort | Risk to Quality |
|----------|----------|---------------|--------|-----------------|
| **1** | **Strategy 1: Merged Prompt** | ~40-50% | Low | Low — same information, fewer round-trips |
| **2** | **Strategy 5: Reduce Questions** | ~25-50% | Very Low | Low-Medium — fewer but more focused questions |
| **3** | **Strategy 2: Eliminate Subqueries** | ~15-20% | Low | Low — questions are already good retrieval queries |
| **4** | **Strategy 3: Embedding Pre-filter** | ~20-40% | Medium | Low — only removes clearly irrelevant pairs |
| **5** | **Strategy 6: Dynamic top_k** | ~20-40% | Low | Medium — may miss some relevant targets |
| **6** | **Strategy 4: Local NLI** | ~40% of inner | Medium | Medium — model quality matters |
| **7** | **Strategy 7: Answer Caching** | ~5-10% | Very Low | None |

### 6.2 Combined Impact Estimate

Applying Strategies 1 + 2 + 5 (the three lowest-effort, highest-impact changes):

**Before (50 chunks, Q=3, S=2, T=5, r=0.6):** 3,650 calls

**After:**
- Strategy 5: Q reduces from 3 → 2 → **cuts ~33% at the question level**
- Strategy 2: Eliminates S=2 subquery calls → **saves Q calls per chunk**
- Strategy 1: Inner loop goes from 3 calls (relevance + answer + classify) to 1 → **cuts ~67% of inner loop**

```
New calls = C × [1 + Q' × (1 + 0 + T' × 1)]      # No subquery call, 1 merged call per target
          = 50 × [1 + 2 × (1 + 5)]
          = 50 × [1 + 12]
          = 50 × 13
          = 650 calls
```

> [!TIP]
> **This represents an ~82% reduction** (3,650 → 650 calls) using only the three simplest strategies. Adding Strategies 3, 4, and 6 could push this to ~90%+ reduction.

### 6.3 Implementation Phases

#### Phase 1: Quick Wins (1-2 days)
- [ ] **Strategy 1**: Create merged prompt template + `_evaluate_pair_merged()` method
- [ ] **Strategy 5**: Add `max_questions_per_chunk` config parameter
- [ ] **Strategy 7**: Add answer caching extension

#### Phase 2: Retrieval Optimization (2-3 days)
- [ ] **Strategy 2**: Replace `_generate_subqueries()` with direct question retrieval
- [ ] **Strategy 6**: Add dynamic top_k with similarity cutoff

#### Phase 3: Local Model Integration (3-5 days)
- [ ] **Strategy 3**: Add embedding-based pre-filter
- [ ] **Strategy 4**: Add local cross-encoder relevance check as config option

### 6.4 Configuration Additions

Add to `config.yaml` under the `mind` section:

```yaml
mind:
  # Cost optimization settings
  cost_optimization:
    # Strategy 1: Use merged evaluation prompt (answer + classify in one call)
    use_merged_evaluation: true

    # Strategy 2: Skip LLM-based subquery generation, use questions directly
    skip_subquery_generation: true

    # Strategy 4: Use local model for relevance checking instead of LLM
    relevance_method: "local"  # "llm" or "local" or "embedding"

    # Strategy 5: Maximum questions per source chunk
    max_questions_per_chunk: 2

    # Strategy 6: Minimum similarity for retrieved target chunks
    retrieval_min_similarity: 0.35
    retrieval_max_k: 5

    # Strategy 3: Embedding pre-filter threshold
    embedding_prefilter_threshold: 0.3
```

---

## 7. Verification Plan

### 7.1 Quality Regression Testing

Before and after each optimization, run the pipeline on a **held-out validation set** and compare:

1. **Detection Accuracy**: Compare classified labels (CONTRADICTION, CULTURAL_DISCREPANCY, NOT_ENOUGH_INFO, NO_DISCREPANCY) against ground truth or against the un-optimized pipeline's results
2. **Recall**: Ensure optimizations don't cause the pipeline to miss genuine contradictions
3. **Precision**: Ensure false positive rate doesn't increase

```bash
# Run both original and optimized pipelines on the same dataset
python -m mind.cli detect --config original_config.yaml --output results_baseline/
python -m mind.cli detect --config optimized_config.yaml --output results_optimized/

# Compare results
python -c "
import pandas as pd
baseline = pd.read_parquet('results_baseline/mind_results.parquet')
optimized = pd.read_parquet('results_optimized/mind_results.parquet')
# Compare label distributions
print('Baseline labels:', baseline['label'].value_counts().to_dict())
print('Optimized labels:', optimized['label'].value_counts().to_dict())
"
```

### 7.2 Cost Measurement

Instrument the Prompter to count actual API calls:

```python
# Add to Prompter.__init__:
self._call_count = 0

# Add to Prompter.prompt:
self._call_count += 1

# Add property:
@property
def total_calls(self):
    return self._call_count
```

Log the call count at the end of each pipeline run and compare against the baseline formula from Section 3.

### 7.3 A/B Testing Protocol

For each strategy:
1. Run on 3+ datasets of varying sizes (small: 50 chunks, medium: 200 chunks, large: 500+ chunks)
2. Measure: total LLM calls, total wall-clock time, detection quality metrics
3. Accept strategy if: call reduction ≥ 20% AND quality metrics within 5% of baseline

---

## Appendix A: Conceptual Borrowings vs Direct Integration

This section clarifies what concepts from the external repos could theoretically inform our design, distinct from direct code integration:

| Concept | Source | How It Could Inform Us |
|---------|--------|----------------------|
| Tree pruning | RATT, LCoT2Tree | Early exit in evaluation loop when confidence is high |
| Iterative refinement | RATT | If a contradiction is borderline, do a second pass (but only for borderlines) |
| Thought structuring | LCoT2Tree | Organize question-answer chains into dependency graphs for parallel processing |
| Web retrieval fallback | RATT | For high-confidence contradictions, optionally verify against external sources |

None of these justify adopting either framework wholesale. They are architectural inspirations at best.

---

## Appendix B: Quick Reference — Current vs Optimized Call Profiles

```
CURRENT PIPELINE (per source chunk, Q=3 questions, T=5 targets):
┌─────────────────────────┬──────┐
│ Step                    │ Calls│
├─────────────────────────┼──────┤
│ Question Generation     │    1 │
│ Source Answers (×Q)     │    3 │
│ Subquery Generation (×Q)│    3 │
│ Relevance Checks (×Q×T) │   15 │
│ Target Answers (×Q×T×r) │    9 │
│ Contradiction (×Q×T×r)  │    9 │
├─────────────────────────┼──────┤
│ TOTAL per chunk         │   40 │
└─────────────────────────┴──────┘

OPTIMIZED PIPELINE (Strategies 1+2+5, Q'=2, T=5):
┌─────────────────────────┬──────┐
│ Step                    │ Calls│
├─────────────────────────┼──────┤
│ Question Generation     │    1 │
│ Source Answers (×Q')    │    2 │
│ Subquery Generation     │    0 │ ← Eliminated (Strategy 2)
│ Merged Eval (×Q'×T)    │   10 │ ← Replaces relevance+answer+classify (Strategy 1)
├─────────────────────────┼──────┤
│ TOTAL per chunk         │   13 │
└─────────────────────────┴──────┘

REDUCTION: 40 → 13 calls per chunk (67.5% reduction)
```
