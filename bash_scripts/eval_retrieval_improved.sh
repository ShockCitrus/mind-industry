#!/usr/bin/env bash
# Improved retrieval evaluation — run AFTER applying Tier 1/2 changes.
# Toggle each improvement independently via env vars.
set -euo pipefail

MODEL_NAME="${MODEL_NAME:-BAAI/bge-m3}"
PATH_SOURCE="${PATH_SOURCE:?Set PATH_SOURCE to corpus parquet}"
PATH_MODEL_DIR="${PATH_MODEL_DIR:?Set PATH_MODEL_DIR to model directory}"
PATH_QUERIES_DIR="${PATH_QUERIES_DIR:?Set PATH_QUERIES_DIR to query files}"
NR_TPCS="${NR_TPCS:-15}"

PATH_SAVE_INDICES="${PATH_SAVE_INDICES:-data/ablations/retrieval/improved/${MODEL_NAME}}"
PATH_OUT="${PATH_OUT:-data/ablations/retrieval/improved/${MODEL_NAME}}"

mkdir -p "$PATH_SAVE_INDICES/topic_${NR_TPCS}" "$PATH_OUT/topic_${NR_TPCS}"

# Toggle improvements (set to 1 to enable)
ENABLE_COSINE_PREFILTER="${ENABLE_COSINE_PREFILTER:-1}"
ENABLE_PERCENTILE_CUTOFF="${ENABLE_PERCENTILE_CUTOFF:-1}"
ENABLE_CROSS_ENCODER="${ENABLE_CROSS_ENCODER:-0}"
ENABLE_BIDIRECTIONAL="${ENABLE_BIDIRECTIONAL:-0}"
CROSS_ENCODER_MODEL="${CROSS_ENCODER_MODEL:-BAAI/bge-reranker-v2-m3}"
BIDIRECTIONAL_ALPHA="${BIDIRECTIONAL_ALPHA:-0.6}"

echo "=== IMPROVED retrieval evaluation ==="
echo "Model: $MODEL_NAME | Topics: $NR_TPCS"
echo "Cosine prefilter: $ENABLE_COSINE_PREFILTER | Percentile cutoff: $ENABLE_PERCENTILE_CUTOFF"
echo "Cross-encoder: $ENABLE_CROSS_ENCODER | Bidirectional: $ENABLE_BIDIRECTIONAL"

# Build CLI flags
EXTRA_FLAGS=""
[[ "$ENABLE_COSINE_PREFILTER" == "1" ]] && EXTRA_FLAGS="$EXTRA_FLAGS --use_cosine_prefilter"
[[ "$ENABLE_PERCENTILE_CUTOFF" == "1" ]] && EXTRA_FLAGS="$EXTRA_FLAGS --use_percentile_cutoff"
[[ "$ENABLE_CROSS_ENCODER" == "1" ]] && EXTRA_FLAGS="$EXTRA_FLAGS --use_cross_encoder_rerank --cross_encoder_model $CROSS_ENCODER_MODEL"
[[ "$ENABLE_BIDIRECTIONAL" == "1" ]] && EXTRA_FLAGS="$EXTRA_FLAGS --use_bidirectional --bidirectional_alpha $BIDIRECTIONAL_ALPHA"

python3 ablation/retrieval/get_relevant_passages.py \
  --model_name "$MODEL_NAME" \
  --path_source "$PATH_SOURCE" \
  --path_queries_dir "$PATH_QUERIES_DIR" \
  --path_model_dir "$PATH_MODEL_DIR" \
  --path_save_indices "$PATH_SAVE_INDICES/topic_${NR_TPCS}" \
  --out_dir "$PATH_OUT/topic_${NR_TPCS}" \
  --nr_tpcs "$NR_TPCS" \
  $EXTRA_FLAGS

echo "Improved run complete. Results at $PATH_OUT/topic_${NR_TPCS}"
