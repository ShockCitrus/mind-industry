# Fresh Tech Contradictions Dataset (150 rows)

## Purpose

Created a brand new synthetic dataset with **50 completely new contradictions** (not reused from the original 10-row blueprint). Designed specifically for comprehensive testing across **5 distinct, well-separated tech topics** to enable domain-specific analysis.

## Dataset Structure

- **Size**: 150 total passages (75 in English, 75 in Spanish)
- **Pairs**: 75 EN-ES passage pairs
- **Contradictory Pairs**: 50 pairs (100 passages) with fresh contradictions
- **Non-Contradictory Pairs**: 25 pairs (50 passages) with aligned translations
- **Location**: `data/expanded/documents_fresh_150.parquet`

### Topic Breakdown

| Topic | Contradictions | Passages | Characteristics |
|-------|---|---|---|
| **Cloud Infrastructure** | 10 | 20 | Kubernetes, Lambda, multi-cloud, serverless, edge computing, VPC, spot instances, sharding, service mesh |
| **Data Analytics** | 10 | 20 | MapReduce, data lakes, columnar storage, streaming, deduplication, OLTP/OLAP, Spark, orchestration |
| **Web Security** | 10 | 20 | TLS 1.3, HTTPS adoption, OAuth 2.0, certificate pinning, CORS, JWT, rate limiting, CSP, headers, password hashing |
| **Mobile Development** | 10 | 20 | Cross-platform performance, API access, app store review, device fragmentation, notifications, battery, PWAs |
| **DevOps & Deployment** | 10 | 20 | CI/CD automation, image scanning, IaC, blue-green, log aggregation, canary, config drift, rollbacks, monitoring |
| **General (aligned)** | 0 | 50 | REST APIs, GraphQL, microservices, API design patterns (non-contradictory) |

**Total**: 150 passages, 50 unique contradictions across 5 domains

## Sample Contradictions

### 1. Cloud Infrastructure — Kubernetes Scaling

**EN**: "Kubernetes automatically scales pod replicas based on CPU utilization metrics to handle traffic spikes."

**ES**: "Kubernetes requiere configuración manual de cada réplica de pod para manejar picos de tráfico."

**Type**: Feature capability mismatch

---

### 2. Data Analytics — Spark Performance

**EN**: "Apache Spark's in-memory processing makes it 100x faster than MapReduce for iterative algorithms."

**ES**: "El procesamiento en memoria de Spark solo proporciona mejora de 2-3x sobre MapReduce en casos especiales."

**Type**: Performance claim contradiction

---

### 3. Web Security — TLS Handshake

**EN**: "TLS 1.3 eliminates the extra round trip in the TLS handshake, improving latency over TLS 1.2."

**ES**: "TLS 1.3 requiere round trips adicionales en el handshake en comparación con TLS 1.2."

**Type**: Technical characteristic mismatch

---

### 4. Mobile Development — Cross-Platform Performance

**EN**: "Cross-platform frameworks like React Native have 10-30% performance overhead vs native code."

**ES**: "React Native ejecuta con el mismo rendimiento que el código nativo sin sobrecarga."

**Type**: Performance comparison contradiction

---

### 5. DevOps & Deployment — CI/CD Benefits

**EN**: "Automated CI/CD pipelines reduce deployment errors by 70-90% compared to manual processes."

**ES**: "La automatización de CI/CD aumenta los errores de implementación debido a falta de revisión humana."

**Type**: Effectiveness claim contradiction

---

## Key Differences from Original Blueprint

| Aspect | Blueprint (Tech_EN_ES) | Fresh Dataset |
|--------|---|---|
| **Contradictions** | 5 reused pairs | 50 unique, never-before-seen pairs |
| **Topics** | 6 mixed (ad-hoc) | 5 clearly separated, organized domains |
| **Scaling** | Topic variants added | Pure contradictions, no variants needed |
| **Domain Coherence** | Low (Quantum, Starship, Blockchain mix) | High (Cloud, Data, Security, Mobile, DevOps) |
| **Complexity** | Simple factual contradictions | Mixed: features, performance, standards, architecture |
| **Use Case** | Quick smoke tests | Comprehensive domain-specific evaluation |

## Generation Script

**File**: `scripts/generate_fresh_tech_dataset.py`

### Usage

```bash
python3 scripts/generate_fresh_tech_dataset.py data/expanded/documents_fresh_150.parquet
```

### Configuration

Customize dataset generation:

```python
generate_fresh_dataset(
    n_total_passages=150,              # Total passages (EN + ES)
    output_path=Path("data/expanded/documents_fresh_150.parquet"),
    contradiction_ratio=0.67,          # 67% contradictory, 33% aligned
)
```

### Generating Variants

**200-row dataset** (add more aligned pairs):
```python
# Edit script: n_total_passages=200, contradiction_ratio=0.50
# Result: 50 contradictory + 50 aligned pairs
python3 scripts/generate_fresh_tech_dataset.py data/expanded/documents_fresh_200.parquet
```

**Heavy contradiction bias** (test on harder cases):
```python
# Edit script: contradiction_ratio=0.80
# Result: 120 contradictory + 30 aligned pairs
python3 scripts/generate_fresh_tech_dataset.py data/expanded/documents_fresh_hard.parquet
```

## Data Schema

```
id_preproc         : str   # Unique ID (e.g., "Tech_EN_0")
text               : str   # Passage text (70–180 characters)
lang               : str   # "EN" or "ES"
title              : str   # Contradiction topic (e.g., "Kubernetes Deployment")
topic              : str   # Domain category (Cloud, Data, Security, Mobile, DevOps, General)
is_contradictory   : bool  # True if contradictory pair, False if aligned
```

## Testing Workflows

### 1. Topic-Specific Evaluation

Evaluate detection performance per domain:

```bash
python3 -c "
import pandas as pd

df = pd.read_parquet('data/expanded/documents_fresh_150.parquet')

for topic in df[df['is_contradictory']]['topic'].unique():
    topic_pairs = df[df['topic'] == topic]['is_contradictory'].sum() // 2
    print(f'{topic:25} {topic_pairs:2} pairs')
    
    # Run pipeline on this topic only
    topic_df = df[df['topic'] == topic]
    # ... evaluate ...
"
```

### 2. Ablation by Domain

Test improvements on each domain independently:

```bash
# Cloud Infrastructure only
python3 -m mind.pipeline.pipeline \
  --source_corpus data/expanded/documents_fresh_150.parquet \
  --filter_topic "Cloud Infrastructure"

# Data Analytics only
python3 -m mind.pipeline.pipeline \
  --source_corpus data/expanded/documents_fresh_150.parquet \
  --filter_topic "Data Analytics"
```

### 3. Cross-Domain Generalization

Measure how well improvements generalize across topics:

```python
import pandas as pd

df = pd.read_parquet('data/expanded/documents_fresh_150.parquet')
results = []

for topic in df['topic'].unique():
    topic_data = df[df['topic'] == topic]
    # Run pipeline...
    # Compute metrics...
    results.append({
        'topic': topic,
        'precision': ...,
        'recall': ...,
        'f1': ...,
    })

print(pd.DataFrame(results))
```

## Contradiction Complexity Levels

Contradictions vary in subtlety and difficulty:

### Type 1: Direct Feature Contradiction
Clear opposite claims about capabilities.
```
EN: "Feature is enabled by default"
ES: "Feature must be manually configured"
```
**Difficulty**: Easy to detect | **Examples**: 8 pairs

### Type 2: Performance Claim Contradiction
Quantified performance metrics differ significantly.
```
EN: "10-30% overhead"
ES: "No overhead / same performance"
```
**Difficulty**: Medium (requires domain knowledge) | **Examples**: 15 pairs

### Type 3: Architecture Decision Contradiction
Different recommended approaches or best practices.
```
EN: "Use strategy A because of benefits"
ES: "Strategy A adds complexity; avoid"
```
**Difficulty**: Hard (context-dependent) | **Examples**: 27 pairs

## Expected Baseline Performance

Based on 50 contradictory pairs + 25 aligned pairs:

| Metric | Expected Range | Notes |
|--------|---|---|
| **Contradiction Detection Rate** | 75–90% | Varies by domain and model |
| **False Positive Rate** | <5% | Should rarely flag aligned pairs |
| **Precision@5** | 70–85% | Top 5 chunks likely contain contradiction |
| **Recall@5** | 80–95% | Most contradictions found in top 5 |
| **Per-Domain Variance** | ±10% | Cloud/DevOps easier, Security harder |

## Comparison with Original Blueprint

**Blueprint Use Cases**:
- Quick smoke tests
- Integration testing
- Early-stage development

**Fresh Dataset Use Cases**:
- Comprehensive evaluation
- Domain-specific analysis
- Ablation studies
- Measuring generalization
- Publication-quality benchmarks

## Future Extensions

1. **Multilingual Expansion**: Add German, Portuguese, French versions
2. **Difficulty Levels**: Separate easy/medium/hard contradictions
3. **Domain Expansion**: Legal, medical, financial domains
4. **Temporal Analysis**: Add version history and evolution of contradictions
5. **Cross-Domain Chains**: EN→ES→DE chains testing multi-hop translation
6. **Implicit Contradictions**: Softer conflicts requiring inference

## Deployment

### Docker Volume

```bash
docker cp data/expanded/documents_fresh_150.parquet \
  mind-industry_backend:/data/all/1_RawData/TechContradictions_Fresh_150/
```

### Dataset Registration

Add to application catalog:

```python
import pandas as pd

new_entry = {
    "dataset_id": "TechContradictions_Fresh_150",
    "name": "Tech Contradictions - Fresh (150 rows)",
    "path": "/data/all/1_RawData/TechContradictions_Fresh_150/documents_fresh_150.parquet",
    "size": 150,
    "language_pairs": ["EN", "ES"],
    "topics": 5,
    "created_date": "2024-04-02",
    "description": "50 fresh contradictions across Cloud, Data, Security, Mobile, DevOps"
}
```

---

Generated: 2024-04-02  
Script: `scripts/generate_fresh_tech_dataset.py`  
Contradictions: 50 unique pairs (100 passages)  
Coverage: 5 distinct tech domains
