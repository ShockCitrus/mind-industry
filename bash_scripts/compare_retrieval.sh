#!/usr/bin/env bash
# Compare baseline vs improved retrieval metrics using generate_table_eval.py
set -euo pipefail

MODEL_NAME="${MODEL_NAME:-BAAI/bge-m3}"
NR_TPCS="${NR_TPCS:-15}"
PATH_GOLD="${PATH_GOLD:?Set PATH_GOLD to gold annotations parquet}"
PATH_BASELINE="${PATH_BASELINE:-data/ablations/retrieval/baseline/${MODEL_NAME}/topic_${NR_TPCS}}"
PATH_IMPROVED="${PATH_IMPROVED:-data/ablations/retrieval/improved/${MODEL_NAME}/topic_${NR_TPCS}}"

echo "============================================"
echo "  Retrieval Comparison: Baseline vs Improved"
echo "  Model: $MODEL_NAME | Topics: $NR_TPCS"
echo "============================================"

echo ""
echo "=== BASELINE ==="
python3 ablation/retrieval/generate_table_eval.py \
  --path_gold_relevant "$PATH_GOLD" \
  --paths_found_relevant "$PATH_BASELINE" \
  --tpc "$NR_TPCS"

echo ""
echo "=== IMPROVED ==="
python3 ablation/retrieval/generate_table_eval.py \
  --path_gold_relevant "$PATH_GOLD" \
  --paths_found_relevant "$PATH_IMPROVED" \
  --tpc "$NR_TPCS"

echo ""
echo "Compare Recall@5, MRR@5, NDCG@5 between the two runs."
echo "Thresholds: Recall@5 +5%, MRR@5 +5%, NDCG@5 +3%"
