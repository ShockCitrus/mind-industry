# Testing Discrepancy Detection with Synthetic Data

## Overview

The project includes synthetic datasets for testing the discrepancy detection pipeline without relying on real-world corpora. Two datasets are available:

1. **Blueprint (10 rows)**: Original minimal test set in `data/raw/documents.parquet`
2. **Expanded (150 rows)**: Larger dataset in `data/expanded/documents_150.parquet` for comprehensive testing

## Quick Start

### 1. Generate the Expanded Dataset

```bash
python3 scripts/generate_expanded_tech_dataset.py data/expanded/documents_150.parquet
```

This creates 150 passages (75 EN + 75 ES) with:
- **50 contradictory pairs** (100 passages): factual contradictions across 6 categories
- **25 non-contradictory pairs** (50 passages): aligned translations

### 2. Inspect the Dataset

```bash
python3 scripts/inspect_expanded_dataset.py data/expanded/documents_150.parquet
```

Shows:
- Language and contradiction distribution
- Category breakdown
- Sample EN↔ES pairs
- Data validation (balance, uniqueness, completeness)

### 3. Run Detection Pipeline

```bash
python3 -m mind.pipeline.pipeline \
  --config_path app/config/config.yaml \
  --source_corpus data/expanded/documents_150.parquet \
  --target_corpus data/expanded/documents_150.parquet \
  --retrieval_method TB-ENN
```

## Dataset Structure

### Schema

```
Column Name      Type    Description
─────────────────────────────────────────────────────────────
id_preproc       str     Unique identifier (e.g., "Tech_EN_0")
text             str     Passage text (78–173 chars)
lang             str     Language code ("EN" or "ES")
title            str     Topic with variant suffix
category         str     Topic category
is_contradictory bool    True if contradictory pair
```

### Categories

| Category | Contradictions | Description |
|----------|---|---|
| **AI** | 9 | Generative AI progress (5 topic variants) |
| **Consensus** | 9 | Bitcoin Proof of Work vs Stake |
| **Security** | 8 | Firewall update status |
| **Vehicles** | 8 | Tesla sensor approach |
| **Semiconductors** | 8 | Moore's Law dead vs accelerating |
| **Space** | 8 | Starship success vs failure |
| **General** | 0 | Non-contradictory (React, 5G, Cloud, etc.) |

### Example Contradictions

**Bitcoin Consensus**
```
EN: "Bitcoin currently uses a Proof of Work consensus mechanism..."
ES: "Bitcoin utiliza un mecanismo de Proof of Stake..."
Category: Consensus
```

**Tesla Autopilot**
```
EN: "Tesla's approach relies entirely on pure vision-based systems..."
ES: "Tesla depende de radar, LiDAR y mapeo del terreno..."
Category: Vehicles
```

**Moore's Law**
```
EN: "Moore's Law is effectively dead due to physical limits..."
ES: "Moore's Law sigue vigente y se está acelerando..."
Category: Semiconductors
```

## Testing Workflows

### 1. Baseline Performance Measurement

Establish baseline metrics with the Tier 1 improvements:

```bash
export CONFIG_PATH="app/config/config.yaml"
export CORPUS_PATH="data/expanded/documents_150.parquet"

python3 -m mind.pipeline.pipeline \
  --config_path "$CONFIG_PATH" \
  --source_corpus "$CORPUS_PATH" \
  --target_corpus "$CORPUS_PATH" \
  --retrieval_method TB-ENN \
  --output_file results/baseline_150.json
```

Expected metrics:
- **Contradiction Detection Rate**: >80% (detect ≥40 of 50 pairs)
- **False Positive Rate**: <10% (flag <5 of 50 non-contradictory pairs)
- **Latency**: <2s per passage pair

### 2. Ablation Study: Tier 1 Improvements

Test Tier 1A (cosine pre-filter) + 1B (percentile cutoff):

```bash
# Pipeline automatically uses cosine similarity for pre-filter
# Enable percentile-based score cutoff in config
python3 -c "
import yaml
with open('app/config/config.yaml') as f:
    cfg = yaml.safe_load(f)
cfg['mind']['cost_optimization']['retrieval_min_score_ratio'] = 0.35
with open('app/config/config.yaml', 'w') as f:
    yaml.dump(cfg, f)
"

python3 -m mind.pipeline.pipeline \
  --config_path "app/config/config.yaml" \
  --source_corpus "$CORPUS_PATH" \
  --target_corpus "$CORPUS_PATH" \
  --output_file results/tier1_150.json
```

Expected improvements:
- Recall@5 +5–10%
- Precision stable or +2–5%

### 3. Ablation Study: Tier 2 Improvements

Test cross-encoder reranking (Tier 2A):

```bash
# Enable cross-encoder in config
python3 -c "
import yaml
with open('app/config/config.yaml') as f:
    cfg = yaml.safe_load(f)
cfg['mind']['cost_optimization']['use_cross_encoder_rerank'] = True
cfg['mind']['cost_optimization']['cross_encoder_model'] = 'BAAI/bge-reranker-v2-m3'
with open('app/config/config.yaml', 'w') as f:
    yaml.dump(cfg, f)
"

python3 -m mind.pipeline.pipeline \
  --config_path "app/config/config.yaml" \
  --source_corpus "$CORPUS_PATH" \
  --target_corpus "$CORPUS_PATH" \
  --output_file results/tier2a_150.json
```

Expected improvements:
- Recall@5 +15–25%
- Precision +10–20%
- Latency +50–150ms/query

### 4. Comparison: All Improvements

Run with all Tier 1 + 2 improvements enabled:

```bash
python3 -c "
import yaml
with open('app/config/config.yaml') as f:
    cfg = yaml.safe_load(f)
cfg['mind']['cost_optimization'] = {
    'use_merged_evaluation': True,
    'skip_subquery_generation': True,
    'embedding_prefilter_threshold': 0.25,
    'retrieval_min_score_ratio': 0.35,
    'retrieval_max_k': 10,
    'use_cross_encoder_rerank': True,
    'cross_encoder_model': 'BAAI/bge-reranker-v2-m3',
    'use_bidirectional_retrieval': True,
    'bidirectional_alpha': 0.6,
}
with open('app/config/config.yaml', 'w') as f:
    yaml.dump(cfg, f)
"

python3 -m mind.pipeline.pipeline \
  --config_path "app/config/config.yaml" \
  --source_corpus "$CORPUS_PATH" \
  --target_corpus "$CORPUS_PATH" \
  --output_file results/full_stack_150.json
```

## Customizing the Dataset

### Generate Different Sizes

```bash
# 300-row dataset (2x size)
python3 scripts/generate_expanded_tech_dataset.py data/expanded/documents_300.parquet
# Edit script to change n_total_passages=300

# 50-row dataset (half size, good for quick tests)
python3 scripts/generate_expanded_tech_dataset.py data/expanded/documents_50.parquet
# Edit script to change n_total_passages=50
```

### Adjust Contradiction Ratio

Edit `generate_expanded_tech_dataset.py` and change:

```python
# Default: 67% contradictory, 33% non-contradictory
generate_expanded_dataset(
    n_total_passages=150,
    contradiction_ratio=0.67,  # Change this
)
```

Options:
- `0.50` — 1:1 balance (75 contradictory + 75 non-contradictory)
- `0.67` — 2:1 ratio (100 contradictory + 50 non-contradictory) [**default**]
- `0.80` — Heavy bias (120 contradictory + 30 non-contradictory)

### Add Custom Topics

Edit `generate_expanded_tech_dataset.py` and extend `NON_CONTRADICTORY_TOPICS`:

```python
NON_CONTRADICTORY_TOPICS = [
    # ... existing topics ...
    {
        "title": "Custom Topic",
        "en": "English text about the topic...",
        "es": "Texto en español sobre el tema...",
    },
]
```

Or extend `BASE_CONTRADICTIONS` for custom contradictions:

```python
BASE_CONTRADICTIONS = [
    # ... existing contradictions ...
    {
        "id": "Tech_EN_ES_6",
        "title": "Custom Contradiction",
        "en": "English claim: X is true",
        "es": "Spanish claim: X is false",
        "category": "CustomCategory",
        "contradiction": True,
    },
]
```

## Metrics and Evaluation

### Key Metrics

| Metric | Target | Notes |
|--------|--------|-------|
| **Contradiction Detection Rate** | >80% | TP / (TP + FN) across 50 pairs |
| **False Positive Rate** | <10% | FP / (FP + TN) across 25 pairs |
| **Precision@5** | >70% | Top 5 retrieved chunks contain contradiction |
| **Recall@5** | >85% | Top 5 chunks include 85% of contradictions |
| **Latency** | <2s/pair | Per EN-ES pair comparison |
| **LLM Calls** | Minimize | Track API cost |

### Computing Metrics Manually

```python
import pandas as pd
from sklearn.metrics import precision_score, recall_score, f1_score

results = pd.read_json("results/baseline_150.json")

# Extract predictions vs ground truth
y_true = results['is_contradictory']
y_pred = results['detected_contradiction']

precision = precision_score(y_true, y_pred)
recall = recall_score(y_true, y_pred)
f1 = f1_score(y_true, y_pred)

print(f"Precision: {precision:.2%}")
print(f"Recall: {recall:.2%}")
print(f"F1 Score: {f1:.2%}")
```

## Troubleshooting

### Dataset Not Found
```
FileNotFoundError: data/expanded/documents_150.parquet
```
**Solution**: Run `python3 scripts/generate_expanded_tech_dataset.py data/expanded/documents_150.parquet`

### Memory Issues with Cross-Encoder
```
CUDA out of memory
```
**Solution**: Reduce batch size in cross-encoder prediction:
```python
# In pipeline.py line ~670
ce_scores = self._cross_encoder.predict(pairs, batch_size=16)  # Reduce from 32
```

### Unbalanced EN-ES Pairs
**Solution**: Run `python3 scripts/inspect_expanded_dataset.py` to validate and report issues

## Next Steps

1. **Deploy to Docker**: Copy dataset to container volume
2. **Register in UI**: Add to datasets catalog for frontend access
3. **Run Continuous Tests**: Schedule nightly evaluation of all improvements
4. **Expand to Other Languages**: Generate DE, PT versions
5. **Create Domain-Specific Datasets**: Medical, legal, financial contradictions

---

Generated: 2024-04-02  
Scripts: `scripts/generate_expanded_tech_dataset.py`, `scripts/inspect_expanded_dataset.py`  
Documentation: `docs/expanded_dataset_creation.md`
