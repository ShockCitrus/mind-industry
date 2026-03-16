# Monolingual Support Implementation Guide

## Overview

This guide provides a complete implementation plan for adding monolingual dataset support to the application. Currently, the entire pipeline (preprocessing, topic modeling, and detection) is built around the assumption of **bilingual datasets** — two languages, paired translations, and cross-language comparison.

**Current Bilingual Architecture (summary of key touchpoints):**

| Component | File | Bilingual Assumption |
|-----------|------|---------------------|
| **Segmenter** | [segmenter.py](file:///home/alonso/Projects/Mind-Industry/src/mind/corpus_building/segmenter.py) | Splits dataset by `lang` column into 2 per-language parquets |
| **Backend Segmenter** | [preprocessing.py](file:///home/alonso/Projects/Mind-Industry/app/backend/preprocessing.py) `segmenter()` L70–133 | Splits into `dataset_{src_lang}` and `dataset_{tgt_lang}` — **raises error if either is empty** |
| **Translator** | [translator.py](file:///home/alonso/Projects/Mind-Industry/src/mind/corpus_building/translator.py) | Translates `src_lang` → `tgt_lang`, appends translated rows |
| **Backend Translator** | [preprocessing.py](file:///home/alonso/Projects/Mind-Industry/app/backend/preprocessing.py) `translator()` L135–193 | Expects 2 language-split parquets as input |
| **Data Preparer** | [data_preparer.py](file:///home/alonso/Projects/Mind-Industry/src/mind/corpus_building/data_preparer.py) | `format_dataframes(anchor_path, comparison_path)` — **requires 2 parquet files** (one per language) |
| **Backend Preparer** | [preprocessing.py](file:///home/alonso/Projects/Mind-Industry/app/backend/preprocessing.py) `preparer()` L196–278 | Passes `anchor_path` and `comparison_path` as separate files |
| **Topic Modeling** | [polylingual_tm.py](file:///home/alonso/Projects/Mind-Industry/src/mind/topic_modeling/polylingual_tm.py) | `PolylingualTM(lang1, lang2, ...)` — creates `corpus_lang1.txt` + `corpus_lang2.txt`, trains bilingual Mallet PLTM |
| **Backend TM** | [preprocessing.py](file:///home/alonso/Projects/Mind-Industry/app/backend/preprocessing.py) `topicmodelling()` L280–346 | **Only instantiates `PolylingualTM`**, never `LDATM` |
| **Detection CLI** | [cli.py](file:///home/alonso/Projects/Mind-Industry/src/mind/cli.py) | Separate `--src_*` and `--tgt_*` args (both required) |
| **Detection Backend** | [detection.py](file:///home/alonso/Projects/Mind-Industry/app/backend/detection.py) `analyse_contradiction()` L429–563 | Builds separate `source_corpus` and `target_corpus` dicts with different `thetas_path` and `language_filter` |
| **MIND Pipeline** | [pipeline.py](file:///home/alonso/Projects/Mind-Industry/src/mind/pipeline/pipeline.py) `MIND.__init__()` L142–262 | Selects multilingual vs monolingual **embedding model** based on `multilingual` bool parameter; loads separate source/target corpora |
| **Frontend Detection** | [detection.html](file:///home/alonso/Projects/Mind-Industry/app/frontend/templates/detection.html) L40–45 | Shows `Docs {{ lang_1 }}` and `Docs {{ lang_2 }}` buttons; iterates over `['EN', 'ES', 'DE', 'IT']` for keyword display (L251) |
| **LDA (monolingual)** | [lda_tm.py](file:///home/alonso/Projects/Mind-Industry/src/mind/topic_modeling/lda_tm.py) | `LDATM(langs, ...)` — **already exists** but is unused in the web app |

**Key insight:** The monolingual `LDATM` class already exists in `src/mind/topic_modeling/lda_tm.py` and is fully functional. The main work is plumbing it into the web app pipeline and adapting the preprocessing and detection flows.

---

## Implementation Steps Checklist

| Step | Description | Status |
| :--- | :--- | :---: |
| **0. Fix LDATM Import Path** | Fix the broken import in `lda_tm.py` before integration. | [ ] |
| **1. Preprocessing Refactor** | Bypass translator, adapt data_preparer for single-language input. | [ ] |
| **2. Topic Modeling Adaptation** | Route monolingual datasets to `LDATM` instead of `PolylingualTM`. | [ ] |
| **3. Detection & Search Logic** | Handle `src_corpus == tgt_corpus` with self-exclusion and same-topic comparison. | [ ] |
| **4. Frontend UI/UX Updates** | Hide second-language elements for monolingual datasets. | [ ] |
| **5. Testing & Validation** | End-to-end manual validation through the GUI. | [ ] |

---

## Detailed Implementation Steps

### Step 0: Fix LDATM Import Path

> [!CAUTION]
> The `LDATM` class has a **broken import** at line 29 of [lda_tm.py](file:///home/alonso/Projects/Mind-Industry/src/mind/topic_modeling/lda_tm.py) that must be fixed before any integration work:

```diff
# lda_tm.py line 29
- from src.utils.utils import file_lines
+ from mind.utils.utils import file_lines
```

This is a prerequisite blocker — the class will fail to import without this fix.

---

### Step 1: Preprocessing Refactor

#### 1a. Monolingual Detection (Automatic — No User Input Required)

**When to detect:** After the segmenter step in [preprocessing.py](file:///home/alonso/Projects/Mind-Industry/app/backend/preprocessing.py) `segmenter()` (L70–133). Currently, the segmenter splits the dataset by language and **raises an error** if either split is empty (L121–122). This is the exact point where the monolingual branch must diverge.

```python
df_segmented = pd.read_parquet(f'{output_dir}/dataset', engine='pyarrow')
df_segmented['lang'] = df_segmented['lang'].astype(str).str.upper()
unique_langs = df_segmented['lang'].unique()
is_monolingual = len(unique_langs) == 1
```

> [!TIP]
> Instead of asking the user to manually select "monolingual" vs "bilingual", detect it automatically after the Segmenter step completes. Display a toast notification to the user: *"Monolingual dataset detected — translation step will be skipped."* This is cleaner UX and eliminates user error.

#### 1b. Bypass Translator

For monolingual datasets, the translator step is skipped entirely. The frontend orchestrator in [preprocessing.py](file:///home/alonso/Projects/Mind-Industry/app/frontend/preprocessing.py) `preprocess_stage1()` (L98–188) must branch:

```python
if is_monolingual:
    # Skip translator entirely
    # Proceed to monolingual preparer
    pass
else:
    # Existing bilingual flow: segmenter → translator → preparer
    ...
```

#### 1c. Adapt DataPreparer

File: [data_preparer.py](file:///home/alonso/Projects/Mind-Industry/src/mind/corpus_building/data_preparer.py)

Add a new method `format_monolingual(input_path: Path, path_save: Path)`:

```python
def format_monolingual(self, input_path: Path, path_save: Path = None) -> pd.DataFrame:
    """Process a single-language dataset (no cross-language pairing needed)."""
    df = pd.read_parquet(input_path, engine='pyarrow')
    df = self._normalize(df)
    
    lang = df['lang'].iloc[0].upper()
    df = self._preprocess_df(df, lang, tag="mono", path_save=path_save)
    
    if path_save:
        df.to_parquet(path_save, engine='pyarrow')
    return df
```

> [!IMPORTANT]
> The output parquet must have the same columns as the bilingual output so that Topic Modeling and Detection steps can consume it without branching. Required columns: `chunk_id`, `chunk_text` (or the configurable `passage_col`), `lang`, `full_doc`, `lemmas`.

#### 1d. Update Backend Preparer Route

In [preprocessing.py](file:///home/alonso/Projects/Mind-Industry/app/backend/preprocessing.py) `preparer()` (L196–278):

```python
if is_monolingual:
    res = prep.format_monolingual(
        input_path=Path(f'{dataset_path}/dataset'),
        path_save=Path(f'{output_dir}/dataset')
    )
else:
    res = prep.format_dataframes(
        anchor_path=...,
        comparison_path=...,
        path_save=...
    )
```

#### 1e. Signal Monolingual State Downstream

**Recommended approach:** Infer from data (stateless). Every subsequent step that needs to branch can check `df['lang'].nunique() == 1`. This avoids adding metadata files or schema changes.

---

### Step 2: Topic Modeling Adaptation

#### Key Insight: `LDATM` Already Exists

The `LDATM` class in [lda_tm.py](file:///home/alonso/Projects/Mind-Industry/src/mind/topic_modeling/lda_tm.py):
- Accepts `langs: list` — for monolingual, pass `["EN"]`.
- Creates per-language `.mallet` files and trains separate LDA models.
- Outputs `thetas_<lang>.npz` and topic keys — same format as `PolylingualTM`.

#### Tasks

##### 2a. Route to `LDATM` in the backend

File: [preprocessing.py](file:///home/alonso/Projects/Mind-Industry/app/backend/preprocessing.py) `topicmodelling()` (L280–346)

```python
if is_monolingual:
    from mind.topic_modeling.lda_tm import LDATM
    model = LDATM(
        langs=[lang1],
        model_folder=str(Path(output_dir)),
        num_topics=int(k),
        mallet_path="/backend/Mallet/bin/mallet",
    )
else:
    from mind.topic_modeling.polylingual_tm import PolylingualTM
    model = PolylingualTM(lang1=lang1, lang2=lang2, ...)
```

##### 2b. Verify output compatibility

The detection pipeline expects:
- `thetas_{lang}.npz` — both `LDATM` and `PolylingualTM` produce this. ✅
- `topickeys.txt` — both produce this. ✅
- `model_info.json` — `PolylingualTM` produces this via `save_model_info()`. Check if `LDATM` does the same; if not, add it. ⚠️

> [!TIP]
> Test `LDATM` independently first with the instruction example files before integrating into the web pipeline. Use the `if __name__ == "__main__"` block already present in `lda_tm.py`.

---

### Step 3: Detection & Search Logic

This is the most nuanced step. The question: **How should monolingual detection work?**

#### Recommended Strategy: Same-Topic Intra-Corpus Comparison

After studying the full architecture, the recommended approach for monolingual detection is: **compare paragraphs within the same topic cluster, excluding the source paragraph itself** (paragraph-level self-exclusion, not document-level).

##### Rationale

| Approach | Pros | Cons | Verdict |
|----------|------|------|---------|
| **Same-topic, exclude self-paragraph** | Consistent with bilingual mode; topic-based narrowing improves relevance; self-exclusion prevents trivial matches | Might miss cross-topic contradictions | ✅ **Recommended** |
| **Same-topic, exclude same-document** | Prevents all intra-document matches | Too restrictive — contradictions WITHIN a document are valid and valuable | ❌ |
| **All-topic, exclude self-paragraph** | Maximum coverage; finds contradictions across topics | Creates an explosion of irrelevant comparisons; LLM cost/time scales poorly; most matches will be topic-unrelated | ❌ |
| **Same-document only** | Finds intra-document contradictions | Too narrow; misses cross-document discrepancies which are the primary use case | ❌ |

**Why same-topic is the right choice:**

1. **Consistency**: The bilingual pipeline already uses topic-based retrieval (TB-ENN) to narrow the search space. Monolingual should do the same — topics define the "subject area" where discrepancies are meaningful.
2. **Scalability**: Without topic narrowing, a 10,000-paragraph corpus would require O(n²) comparisons. Topic-based retrieval keeps it at O(n × k) where k = `top_k` (default 10).
3. **Relevance**: Comparing a paragraph about "tax policy" with a paragraph about "healthcare" is unlikely to produce meaningful discrepancies, even if they're in the same language.
4. **Self-exclusion granularity**: Excluding only the source *paragraph* (not the whole document) is critical because contradictions can exist **within a single document** — e.g., a report's introduction may claim one thing while a later section contradicts it.

##### 3a. Path Resolution: `src_corpus == tgt_corpus`

File: [detection.py](file:///home/alonso/Projects/Mind-Industry/app/backend/detection.py) `analyse_contradiction()` (L429–563)

For monolingual, both source and target corpus dicts point to the **same data**:
```python
if is_monolingual:
    corpus_config = {
        "corpus_path": pathCorpus,
        "thetas_path": f'{pathTM}/mallet_output/thetas_{lang[0]}.npz',
        "language_filter": lang[0],
        "index_path": f'/data/{email}/3_TopicModel/{TM}/',
        ...
    }
    source_corpus = corpus_config
    target_corpus = corpus_config.copy()
```

The `obtain_langs_TM()` function in [utils.py](file:///home/alonso/Projects/Mind-Industry/app/backend/utils.py) (L210–217) must handle monolingual models that return only one language:
```python
def obtain_langs_TM(pathTM: str):
    # ... existing logic ...
    if len(langs) == 1:
        return langs  # Return single-language list; caller handles monolingual case
```

##### 3b. Paragraph-Level Self-Exclusion

File: [pipeline.py](file:///home/alonso/Projects/Mind-Industry/src/mind/pipeline/pipeline.py) `_process_question()` (L402–463)

At L452, target chunks are iterated. Add a self-exclusion filter:

```python
for target_chunk in all_target_chunks:
    # Self-exclusion: skip if target is the exact same passage
    src_id = getattr(source_chunk, "id", None)
    tgt_id = getattr(target_chunk, "id", None)
    if tgt_id == src_id:
        continue

    qkey = self._normalize(question)
    triplet = (qkey, src_id, tgt_id)
    if triplet in self.seen_triplets:
        continue
    self.seen_triplets.add(triplet)

    self._evaluate_pair(question, a_s, source_chunk,
                        target_chunk, topic, subquery, path_save)
```

> [!IMPORTANT]
> The exclusion is at the **paragraph/chunk** level (by `chunk.id`), NOT at the document level. Comparing different paragraphs within the same document is valid and desired — contradictions can exist within a single document.

##### 3c. Retrieval Adjustment for Self-Exclusion

The `Corpus.retrieve_relevant_chunks()` method in [corpus.py](file:///home/alonso/Projects/Mind-Industry/src/mind/pipeline/corpus.py) delegates to `IndexRetriever.retrieve()`. For monolingual, the source chunk itself will always be the most similar (cosine similarity ≈ 1.0) and will consume one of the `top_k` slots.

**Solution:** When operating in monolingual mode, increase `top_k` by 1 so that after self-exclusion, the effective number of target chunks remains the configured value.

In `MIND.__init__()`, add a `monolingual` flag that is propagated to the retriever configuration:
```python
if not multilingual:  # monolingual mode
    effective_top_k = self.config.get("mind", {}).get("top_k", 10) + 1
```

---

### Step 4: Frontend UI/UX Updates

#### 4a. Adaptive Menus & Buttons

File: [detection.html](file:///home/alonso/Projects/Mind-Industry/app/frontend/templates/detection.html)

**Language buttons (L40–45):**
```html
{% if docs_data_1 %}
<button type="button" class="btn btn-outline-primary" id="btn-docs1">Docs {{ lang_1 }}</button>
{% endif %}
{% if docs_data_2 %}
<button type="button" class="btn btn-outline-primary" id="btn-docs2">Docs {{ lang_2 }}</button>
{% endif %}
```
These are already conditionally rendered. For monolingual, `docs_data_2` will be `None`, so `btn-docs2` won't appear. ✅ **No change needed.**

**Keyword display (L251–258):**
```html
{% for lang in ['EN', 'ES', 'DE', 'IT'] %}
{% if topic['keywords_' + lang] is defined %}
```
This iterates over a hardcoded language list. For monolingual models, only 1 language's keywords will be defined, so the others will be skipped. ✅ **No change needed.**

#### 4b. State Management

The detection page endpoint in [views.py](file:///home/alonso/Projects/Mind-Industry/app/frontend/views.py) `detection_page()` (L258–301) should pass an `is_monolingual` flag to the template. Derive from topic key metadata: if only 1 language is present, it's monolingual.

#### 4c. Frontend Preprocessing Flow

File: [preprocessing.html](file:///home/alonso/Projects/Mind-Industry/app/frontend/templates/preprocessing.html)

For monolingual datasets:
- Auto-disable or hide the `tgt_lang` field.
- Skip the "Translate" step visually (grey it out or show "Skipped").
- Display a toast notification: *"Monolingual dataset detected — translation step will be skipped."*

**Approach:** Auto-detect after the Segmenter step completes. In `preprocess_stage1()` (L98–188), check the segmentation result and branch accordingly:
```python
if is_monolingual:
    preprocess_stage1_mono(task_id, task_name, email, dataset, segmenter_data, preparer_data)
else:
    preprocess_stage1(task_id, task_name, email, dataset, segmenter_data, translator_data, preparer_data)
```

---

### Step 5: Testing & Validation

#### Test Strategy

| Test | Type | Description |
|------|------|-------------|
| **LDATM import fix** | Manual | Verify `from mind.utils.utils import file_lines` resolves correctly |
| **Monolingual segmentation** | Manual | Upload a single-language dataset, verify segmenter detects monolingual |
| **Translator bypass** | Manual | Verify translator step is skipped; preparer receives correct input |
| **LDA training** | Manual | Train LDATM on monolingual data, verify outputs (`thetas`, `topickeys`) |
| **Self-exclusion** | Manual | Run detection, verify no passage matches itself in results |
| **Frontend display** | Manual | Verify second-language buttons are hidden, only 1 lang's keywords shown |
| **Bilingual regression** | Manual | Re-run the full bilingual pipeline, verify no regressions |

#### Debugging Support
- All pipeline steps log to `/data/<email>/pipeline-mind.log`.
- Use the existing "Check Status" modal in the detection page (terminal log viewer) to monitor pipeline progress.

---

## Verification Plan

### Automated Tests
- Unit test `LDATM` with a small monolingual corpus (use the instruction examples from `instruction_examples/md/`).
- Unit test `DataPreparer.format_monolingual()` with a single-language parquet.
- Unit test self-exclusion logic: create two chunks with same id, verify one is filtered.

### Manual Verification
- Full end-to-end: Upload monolingual dataset → Segment → (skip Translate) → Prepare → Train LDA → Detect → View Results.
- Verify `detection.html` renders correctly with only 1 language.
- Verify existing bilingual datasets still work without regressions.
- Verify self-exclusion: in results, no row should have `source_chunk_id == target_chunk_id`.
