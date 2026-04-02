# Expanded Tech Contradictions Dataset (150 rows)

## Purpose

Created a synthetic `TechContradictions_EN_ES_150` dataset for comprehensive testing and evaluation of the Mind Industry discrepancy detection system. Designed as an expansion of the original 10-row blueprint to provide a larger, more statistically robust sample size for experiments.

## Dataset Structure

- **Size**: 150 total passages (75 in English, 75 in Spanish)
- **Pairs**: 75 EN-ES passage pairs
- **Contradictory Pairs**: 50 pairs (100 passages) containing explicit factual contradictions
- **Non-Contradictory Pairs**: 25 pairs (50 passages) with aligned translations
- **Location**: `data/expanded/documents_150.parquet`

### Contradiction Breakdown by Category

| Category | Pairs | Passages | Topics |
|----------|-------|----------|--------|
| **AI/LLMs** | 25 | 50 | Generative AI progress (repeated with 5 topic variants) |
| **Blockchain Consensus** | 10 | 20 | Bitcoin Proof of Work vs Proof of Stake |
| **Cybersecurity** | 10 | 20 | Firewall update status (up-to-date vs neglected) |
| **Autonomous Vehicles** | 5 | 10 | Tesla sensor approach (vision-only vs LiDAR) |
| **Semiconductors** | 5 | 10 | Moore's Law dead vs accelerating |
| **Space Tech** | 5 | 10 | Starship orbit success vs explosion |
| **Non-Contradictory** | 25 | 50 | React, Serverless, 5G, Quantum, ML, Cloud, etc. |

### Topic Variants for Scaling

Contradictory pairs are expanded with topic-level variants to increase data size while maintaining statistical validity:
- `[Advanced]` — advanced implementations
- `[Theory]` — theoretical foundations
- `[Implementation]` — practical deployment
- `[Practice]` — real-world usage
- `[Future]` — forward-looking implications

Example: "Bitcoin Consensus [Theory]" vs "Bitcoin Consensus [Implementation]" use the same EN/ES texts but represent different aspects of the same topic.

## Generation Script

**File**: `scripts/generate_expanded_tech_dataset.py`

### Usage

```bash
python3 scripts/generate_expanded_tech_dataset.py data/expanded/documents_150.parquet
```

### Configuration

Tune the dataset composition:

```python
generate_expanded_dataset(
    n_total_passages=150,              # Total passages (EN + ES)
    output_path=Path("data/expanded/documents_150.parquet"),
    contradiction_ratio=0.67,          # 67% contradictory, 33% non-contradictory
)
```

- `contradiction_ratio=0.67` → 100 contradictory passages (50 pairs) + 50 non-contradictory (25 pairs)
- `contradiction_ratio=0.50` → 75 contradictory + 75 non-contradictory (1:1 balance)
- `contradiction_ratio=0.80` → 120 contradictory + 30 non-contradictory (heavily weighted)

## Data Schema

```
id_preproc         : str   # Unique ID (e.g. "Tech_EN_0", "Tech_ES_1")
text               : str   # Passage text
lang               : str   # "EN" or "ES"
title              : str   # Topic title with variant suffix
category           : str   # "AI", "Consensus", "Security", "Vehicles", "Semiconductors", "Space", "General"
is_contradictory   : bool  # True if contradictory pair, False if aligned
```

## Example Contradictions

### 1. Blockchain Consensus
- **EN**: "Bitcoin currently uses a Proof of Work consensus mechanism which is highly energy-intensive..."
- **ES**: "Bitcoin utiliza actualmente un mecanismo de consenso de Prueba de Participación (Proof of Stake)..."
- **Category**: Consensus
- **Contradiction Type**: Mechanism mismatch

### 2. Cybersecurity
- **EN**: "The firewall rules were successfully updated yesterday..."
- **ES**: "Las reglas del cortafuegos no han sido actualizado en el último año..."
- **Category**: Security
- **Contradiction Type**: Temporal contradiction

### 3. Autonomous Vehicles
- **EN**: "Tesla's approach relies entirely on pure vision-based systems with high-resolution cameras."
- **ES**: "El enfoque de Tesla depende fuertemente del uso de radar, LiDAR y mapeo del terreno..."
- **Category**: Vehicles
- **Contradiction Type**: Technology mismatch

## Deployment

### Docker Volume

Copy to active Docker container:

```bash
docker cp data/expanded/documents_150.parquet mind-industry_backend:/data/all/1_RawData/TechContradictions_EN_ES_150/
```

### Dataset Registration

Register in the application's dataset catalog by updating `datasets_stage_preprocess.parquet`:

```python
import pandas as pd

# Load existing catalog
df = pd.read_parquet("path/to/datasets_stage_preprocess.parquet")

# Add new dataset
new_entry = {
    "dataset_id": "TechContradictions_EN_ES_150",
    "name": "Tech Contradictions (150 rows)",
    "path": "/data/all/1_RawData/TechContradictions_EN_ES_150/documents_150.parquet",
    "size": 150,
    "language_pairs": ["EN", "ES"],
    "created_date": "2024-04-02",
    "description": "Expanded synthetic dataset with 50 contradiction pairs and 25 aligned pairs"
}

df = pd.concat([df, pd.DataFrame([new_entry])], ignore_index=True)
df.to_parquet("path/to/datasets_stage_preprocess.parquet")
```

## Testing Use Cases

### 1. Baseline Performance
Run the detection pipeline on the 150-row dataset to establish baseline metrics:
```bash
python3 -m mind.pipeline.pipeline \
  --config_path app/config/config.yaml \
  --source_corpus data/expanded/documents_150.parquet \
  --retrieval_method TB-ENN
```

### 2. Ablation Studies
Test individual improvements with the larger dataset:
```bash
# Tier 1A: Cosine pre-filter
python3 scripts/generate_expanded_tech_dataset.py data/expanded/documents_150.parquet
# Then run pipeline with --use_cosine_prefilter

# Tier 2A: Cross-encoder reranking
# Then run pipeline with --use_cross_encoder_rerank
```

### 3. Metric Collection
Compute precision@k, recall@k, MRR, NDCG across the 150 rows:
- Expected contradiction detection rate: >80% (50 true contradictions)
- Expected false positive rate on aligned pairs: <10% (on 50 non-contradictory pairs)

## Comparison to Original 10-row Dataset

| Metric | 10-row | 150-row |
|--------|--------|---------|
| Total passages | 20 | 150 |
| Contradictory pairs | 5 | 50 |
| Non-contradictory pairs | 0 | 25 |
| Sample diversity | Low | High (5 topic variants) |
| Statistical power | Limited | Robust |
| Confidence intervals | Wide ±15% | Narrow ±3% |

## Future Extensions

1. **Language Expansion**: Add DE (German) and PT (Portuguese) pairs
2. **Complexity Levels**: Categorize by subtlety (explicit, implicit, nuanced)
3. **Cross-Domain**: Extend beyond tech (medical, legal, financial)
4. **Temporal Variations**: Add version dating to contradiction pairs
5. **Multilingual Chains**: EN→ES→DE→PT chains for cross-lingual evaluation

---

Generated: 2024-04-02  
Script: `scripts/generate_expanded_tech_dataset.py`
