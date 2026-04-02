# Dataset Comparison Guide

## Overview

The project now has three datasets for testing the discrepancy detection system:

1. **Original Blueprint** (10 rows) — `data/raw/documents.parquet`
2. **Expanded Dataset** (150 rows) — `data/expanded/documents_150.parquet`
3. **Fresh Dataset** (150 rows) — `data/expanded/documents_fresh_150.parquet`

This guide helps you choose the right dataset for your testing goals.

## Quick Reference

| Property | Blueprint | Expanded | Fresh |
|----------|---|---|---|
| **Passages** | 20 | 150 | 150 |
| **Contradictory Pairs** | 5 | 50 | 50 |
| **Non-Contradictory Pairs** | 0 | 25 | 25 |
| **Unique Contradictions** | 5 | 5 (repeated) | 50 (unique) |
| **Topics** | 6 mixed | 6 mixed | 5 organized |
| **Scaling Method** | Manual | Topic variants | Pure new content |
| **File Size** | 2 KB | 12 KB | 12 KB | 
| **Use Case** | Smoke tests | General testing | Domain-specific |

## Detailed Comparison

### Blueprint (10 rows)

**Contradictions**:
- Bitcoin Proof of Work vs Proof of Stake
- Firewall update status (recent vs old)
- Tesla sensors (vision-only vs LiDAR)
- Moore's Law (dead vs accelerating)
- Starship (success vs failure)

**Characteristics**:
- ✓ Minimal, quick to process
- ✓ Good for initial development
- ✗ Too small for statistical analysis
- ✗ Limited domain coverage
- ✗ No diversity in contradiction types

**Best For**:
- Smoke tests (Does the pipeline run?)
- Quick integration tests
- Early-stage debugging
- Minimal CI/CD overhead

**Example Usage**:
```bash
# Quick test in CI/CD
python3 -m mind.pipeline.pipeline \
  --source_corpus data/raw/documents.parquet
```

---

### Expanded Dataset (150 rows, original contradictions)

**Contradictions**:
- 5 unique contradictions
- Each repeated with 10 topic variants (e.g., `[Theory]`, `[Implementation]`, `[Future]`)
- 50 total pairs to reach 150 passages

**Characteristics**:
- ✓ Larger sample (15× bigger)
- ✓ Fixed topic variants (reproducible scaling)
- ✓ Good for measuring statistical improvement
- ✗ Reused contradictions (not ideal for generalization)
- ✗ Topics still mixed (not domain-organized)

**Best For**:
- Measuring baseline metrics
- Ablation studies of improvements
- Statistically valid experiments
- Comparing before/after performance

**Example Usage**:
```bash
# Baseline measurement
python3 -m mind.pipeline.pipeline \
  --source_corpus data/expanded/documents_150.parquet \
  --output_file results/baseline.json

# Measure improvement
python3 -m mind.pipeline.pipeline \
  --source_corpus data/expanded/documents_150.parquet \
  --use_cross_encoder_rerank \
  --output_file results/with_improvement.json
```

---

### Fresh Dataset (150 rows, new contradictions)

**Contradictions**:
- 50 completely new, unique contradictions
- Never appeared in original blueprint
- Organized across 5 distinct topics
- No scaling via variants (pure content)

**Topics**:
1. **Cloud Infrastructure** (10 pairs)
   - Kubernetes, Lambda, multi-cloud, serverless, edge, VPC, spot instances, sharding, service mesh
   
2. **Data Analytics** (10 pairs)
   - MapReduce, data lakes, columnar storage, streaming, Spark, deduplication, OLTP/OLAP
   
3. **Web Security** (10 pairs)
   - TLS 1.3, HTTPS adoption, OAuth 2.0, certificate pinning, CORS, JWT, rate limiting, CSP, password hashing
   
4. **Mobile Development** (10 pairs)
   - Cross-platform frameworks, API access, app store review, fragmentation, notifications, battery, PWAs
   
5. **DevOps & Deployment** (10 pairs)
   - CI/CD, image scanning, IaC, blue-green, log aggregation, canary, config drift, rollbacks, monitoring

**Characteristics**:
- ✓ 50 unique, diverse contradictions
- ✓ Organized by clear topics
- ✓ Better tests generalization
- ✓ Domain-specific analysis possible
- ✓ No "reuse bias" from blueprint
- ✓ Mixed contradiction types/difficulty

**Best For**:
- Measuring generalization across domains
- Domain-specific performance analysis
- Publication-quality benchmarks
- Testing robustness on new content
- Ablation studies with domain breakdown

**Example Usage**:
```bash
# Evaluate per domain
for topic in "Cloud Infrastructure" "Data Analytics" "Web Security" "Mobile Development" "DevOps & Deployment"; do
  python3 -m mind.pipeline.pipeline \
    --source_corpus data/expanded/documents_fresh_150.parquet \
    --filter_topic "$topic" \
    --output_file "results/fresh_${topic// /_}.json"
done

# Measure generalization
python3 scripts/compute_topic_metrics.py results/fresh_*.json
```

---

## Choosing a Dataset

### For Development & Integration Testing
**Use: Blueprint**

Quick iteration and validation during development.
```bash
python3 -m mind.pipeline.pipeline --source_corpus data/raw/documents.parquet
```

### For Baseline Metrics
**Use: Expanded**

Establish performance baseline before testing improvements.
```bash
python3 -m mind.pipeline.pipeline \
  --source_corpus data/expanded/documents_150.parquet \
  --output_file results/baseline_expanded.json
```

### For Improvement Evaluation
**Use: Expanded + Fresh**

Test on original contradictions (expanded) then validate on new content (fresh).
```bash
# Test on expanded (within-distribution)
python3 -m mind.pipeline.pipeline \
  --source_corpus data/expanded/documents_150.parquet \
  --use_cross_encoder_rerank \
  --output_file results/improved_expanded.json

# Validate on fresh (out-of-distribution)
python3 -m mind.pipeline.pipeline \
  --source_corpus data/expanded/documents_fresh_150.parquet \
  --use_cross_encoder_rerank \
  --output_file results/improved_fresh.json

# Compare: fresh should show less improvement (true generalization test)
```

### For Domain Analysis
**Use: Fresh**

Understand how performance varies by technical domain.
```bash
# Create subsets by topic
python3 -c "
import pandas as pd

df = pd.read_parquet('data/expanded/documents_fresh_150.parquet')
for topic in df['topic'].unique():
    subset = df[df['topic'] == topic]
    subset.to_parquet(f'data/expanded/fresh_{topic.replace(\" \", \"_\")}.parquet')
"

# Evaluate each domain separately
python3 scripts/evaluate_by_domain.py
```

### For Publication
**Use: Fresh**

More representative of real-world diversity.
- 50 unique contradictions (not 5 repeated)
- 5 organized domains (not mixed topics)
- Tests true generalization
- Avoids "memorization" of blueprint content

---

## Mixing Datasets in Experiments

### Cross-Validation Setup

Use blueprint for training, expanded for validation, fresh for testing:

```bash
# 1. Quick test on blueprint (sanity check)
python3 -m mind.pipeline.pipeline \
  --source_corpus data/raw/documents.parquet

# 2. Measure baseline on expanded (establish metrics)
python3 -m mind.pipeline.pipeline \
  --source_corpus data/expanded/documents_150.parquet \
  --output_file results/baseline.json

# 3. Test improvements on expanded (within-distribution)
python3 -m mind.pipeline.pipeline \
  --source_corpus data/expanded/documents_150.parquet \
  --use_cross_encoder_rerank \
  --output_file results/improved_expanded.json

# 4. Validate on fresh (out-of-distribution)
python3 -m mind.pipeline.pipeline \
  --source_corpus data/expanded/documents_fresh_150.parquet \
  --use_cross_encoder_rerank \
  --output_file results/improved_fresh.json

# 5. Compare metrics
python3 scripts/compare_results.py results/baseline.json results/improved_expanded.json results/improved_fresh.json
```

### A/B Testing Improvements

**Test on both datasets to ensure robustness**:

```python
import pandas as pd

baseline_expanded = pd.read_json('results/baseline_expanded.json')
improved_expanded = pd.read_json('results/improved_expanded.json')
improved_fresh = pd.read_json('results/improved_fresh.json')

# Check: improvement is consistent
print("Expanded Recall (baseline → improved):", 
      baseline_expanded['recall'].mean(), "→", improved_expanded['recall'].mean())

# Check: improvement generalizes to fresh data
print("Fresh Recall (improved):", improved_fresh['recall'].mean())

# Fresh recall should be lower (harder domain) but still improved
# If fresh recall is much lower, generalization may be weak
```

---

## Metric Interpretation by Dataset

### Within-Distribution (Expanded)
- **Higher absolute metrics** (60–80% recall)
- **Larger improvements** from new methods (+15–25%)
- **Less variance** across pairs

### Out-of-Distribution (Fresh)
- **Lower absolute metrics** (50–70% recall)
- **Smaller improvements** from new methods (+5–15%)
- **Higher variance** across topics
- **More representative** of real-world performance

### Generalization Gap
```
Generalization Gap = Recall(Expanded) - Recall(Fresh)

Small gap (<5%)  → Excellent generalization
Medium gap (5–10%) → Good generalization
Large gap (>10%)  → Potential overfitting
```

---

## Summary Table

| Goal | Dataset | Rationale |
|------|---------|-----------|
| **Quick test** | Blueprint | Minimal overhead, runs in seconds |
| **Establish baseline** | Expanded | Larger, reproducible contradictions |
| **Test improvement** | Expanded + Fresh | Measure within- and out-of-distribution |
| **Domain analysis** | Fresh | 5 organized topics |
| **Publication** | Fresh | Diverse, representative, unbiased |
| **CI/CD** | Blueprint or Expanded | Tradeoff between speed and rigor |

---

## Generation & Updates

### Regenerate Datasets

```bash
# Regenerate expanded (same contradictions, fresh variants)
python3 scripts/generate_expanded_tech_dataset.py data/expanded/documents_150.parquet

# Regenerate fresh (brand new contradictions)
python3 scripts/generate_fresh_tech_dataset.py data/expanded/documents_fresh_150.parquet
```

### Create Custom Dataset

Combine specific domains from fresh dataset:

```python
import pandas as pd

df = pd.read_parquet('data/expanded/documents_fresh_150.parquet')

# Just Cloud + Data
subset = df[df['topic'].isin(['Cloud Infrastructure', 'Data Analytics'])]
subset.to_parquet('data/custom/cloud_data_pairs.parquet')
```

---

**Last Updated**: 2024-04-02  
**Datasets**: 3 (Blueprint, Expanded, Fresh)  
**Total Contradictions**: 55 unique pairs  
**Total Passages**: 320 passages
