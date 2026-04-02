#!/usr/bin/env bash
# Baseline retrieval evaluation — run BEFORE any Tier 1/2 changes.
# Captures the baseline across all metric dimensions.
set -euo pipefail

MODEL_NAME="${MODEL_NAME:-BAAI/bge-m3}"
PATH_SOURCE="${PATH_SOURCE:?Set PATH_SOURCE to corpus parquet}"
PATH_MODEL_DIR="${PATH_MODEL_DIR:?Set PATH_MODEL_DIR to model directory}"
PATH_QUERIES_DIR="${PATH_QUERIES_DIR:?Set PATH_QUERIES_DIR to query files}"
NR_TPCS="${NR_TPCS:-15}"

PATH_SAVE_INDICES="${PATH_SAVE_INDICES:-data/ablations/retrieval/baseline/${MODEL_NAME}}"
PATH_OUT="${PATH_OUT:-data/ablations/retrieval/baseline/${MODEL_NAME}}"

mkdir -p "$PATH_SAVE_INDICES/topic_${NR_TPCS}" "$PATH_OUT/topic_${NR_TPCS}"

echo "=== BASELINE retrieval evaluation ==="
echo "Model: $MODEL_NAME | Topics: $NR_TPCS"

python3 ablation/retrieval/get_relevant_passages.py \
  --model_name "$MODEL_NAME" \
  --path_source "$PATH_SOURCE" \
  --path_queries_dir "$PATH_QUERIES_DIR" \
  --path_model_dir "$PATH_MODEL_DIR" \
  --path_save_indices "$PATH_SAVE_INDICES/topic_${NR_TPCS}" \
  --out_dir "$PATH_OUT/topic_${NR_TPCS}" \
  --nr_tpcs "$NR_TPCS"

echo "Baseline complete. Results at $PATH_OUT/topic_${NR_TPCS}"
