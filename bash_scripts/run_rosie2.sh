#!/usr/bin/env bash
set -euo pipefail

LLM_MODEL="llama3.3:70b" #"qwen:32b"
# Set LLM_SERVER via environment variable before running, e.g.:
#   export LLM_SERVER="http://your-ollama-host:11434"
# Or override inline: LLM_SERVER="http://..." bash run_rosie2.sh
LLM_SERVER="${LLM_SERVER:?ERROR: LLM_SERVER is not set. Export it before running this script.}"
TOPICS="24"
SAMPLE_SIZE=500 #1000
PATH_SAVE="data/mind_runs/rosie/results"

SRC_CORPUS_PATH="/export/usuarios_ml4ds/lbartolome/Repos/umd/LinQAForge/data/source/corpus_rosie/passages/26_jan/df_1.parquet"
SRC_THETAS_PATH="/export/usuarios_ml4ds/lbartolome/Repos/umd/LinQAForge/data/models/28_jan/poly_rosie_1_30/mallet_output/thetas_EN.npz"
SRC_ID_COL="doc_id"
SRC_PASSAGE_COL="text"
SRC_FULL_DOC_COL="full_doc"
SRC_LANG_FILTER="EN"
SRC_FILTER_IDS_PATH="data/mind_runs/rosie/v1/src_filter_ids.txt"

TGT_CORPUS_PATH="/export/usuarios_ml4ds/lbartolome/Repos/umd/LinQAForge/data/source/corpus_rosie/passages/26_jan/df_1.parquet"
TGT_THETAS_PATH="/export/usuarios_ml4ds/lbartolome/Repos/umd/LinQAForge/data/models/28_jan/poly_rosie_1_30/mallet_output/thetas_ES.npz"
TGT_ID_COL="doc_id"
TGT_PASSAGE_COL="text"
TGT_FULL_DOC_COL="full_doc"
TGT_LANG_FILTER="ES"
TGT_INDEX_PATH="data/mind_runs/rosie/indexes"
TGT_FILTER_IDS_PATH="data/mind_runs/rosie/v1/src_filter_ids.txt"
#PREVIOUS_CHECK="data/mind_runs/rosie/results/results_topic_15_504_check.parquet"
# --previous_check "$PREVIOUS_CHECK"

CMD=(python3 src/mind/cli.py
  --llm_model "$LLM_MODEL"
  --llm_server "$LLM_SERVER"
  --topics "$TOPICS"
  --sample_size "$SAMPLE_SIZE"
  --path_save "$PATH_SAVE"
  --src_corpus_path "$SRC_CORPUS_PATH"
  --src_thetas_path "$SRC_THETAS_PATH"
  --src_id_col "$SRC_ID_COL"
  --src_passage_col "$SRC_PASSAGE_COL"
  --src_full_doc_col "$SRC_FULL_DOC_COL"
  --src_lang_filter "$SRC_LANG_FILTER"
  --tgt_corpus_path "$TGT_CORPUS_PATH"
  --tgt_thetas_path "$TGT_THETAS_PATH"
  --tgt_id_col "$TGT_ID_COL"
  --tgt_passage_col "$TGT_PASSAGE_COL"
  --tgt_full_doc_col "$TGT_FULL_DOC_COL"
  --tgt_lang_filter "$TGT_LANG_FILTER"
  --tgt_index_path "$TGT_INDEX_PATH"
  --src_filter_ids_path "$SRC_FILTER_IDS_PATH"
  --tgt_filter_ids_path "$TGT_FILTER_IDS_PATH"
)

# Show the exact command (quoted)
printf 'Running: '; printf '%q ' "${CMD[@]}"; echo

# Execute
"${CMD[@]}"

echo "Done."