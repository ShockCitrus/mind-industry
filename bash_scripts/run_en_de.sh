#!/usr/bin/env bash
set -euo pipefail


LLM_MODEL="llama3.3:70b" #"qwen:32b"
# Set LLM_SERVER via environment variable before running, e.g.:
#   export LLM_SERVER="http://your-ollama-host:11434"
# Or override inline: LLM_SERVER="http://..." bash run_en_de.sh
LLM_SERVER="${LLM_SERVER:?ERROR: LLM_SERVER is not set. Export it before running this script.}"
TOPICS="7"
SAMPLE_SIZE=200     
PATH_SAVE="data/mind_runs/ende/results"
SRC_CORPUS_PATH="/export/usuarios_ml4ds/lbartolome/Repos/alonso_mind/Data/polylingual_df.parquet"
SRC_THETAS_PATH="/export/usuarios_ml4ds/lbartolome/Repos/umd/mind/data/models/wiki/ende/poly_en_de_05_09_25/mallet_output/thetas_EN.npz"
SRC_ID_COL="doc_id"
SRC_PASSAGE_COL="text"
SRC_FULL_DOC_COL="full_doc"
SRC_LANG_FILTER="EN"
TGT_CORPUS_PATH="/export/usuarios_ml4ds/lbartolome/Repos/alonso_mind/Data/polylingual_df.parquet"
TGT_THETAS_PATH="/export/usuarios_ml4ds/lbartolome/Repos/umd/mind/data/models/wiki/ende/poly_en_de_05_09_25/mallet_output/thetas_DE.npz"
TGT_ID_COL="doc_id"
TGT_PASSAGE_COL="text"
TGT_FULL_DOC_COL="full_doc"
TGT_LANG_FILTER="DE"
TGT_INDEX_PATH="data/mind_runs/ende/indexes"
#PREVIOUS_CHECK="data/mind_runs/ende/results/results_topic_3_1138_check.parquet"
#--previous_check $PREVIOUS_CHECK
CMD="python3 src/mind/cli.py \
    --llm_model $LLM_MODEL \
    --llm_server $LLM_SERVER \
    --topics $TOPICS \
    --sample_size $SAMPLE_SIZE \
    --path_save $PATH_SAVE \
    --src_corpus_path $SRC_CORPUS_PATH \
    --src_thetas_path $SRC_THETAS_PATH \
    --src_id_col $SRC_ID_COL \
    --src_passage_col $SRC_PASSAGE_COL \
    --src_full_doc_col $SRC_FULL_DOC_COL \
    --src_lang_filter $SRC_LANG_FILTER \
    --tgt_corpus_path $TGT_CORPUS_PATH \
    --tgt_thetas_path $TGT_THETAS_PATH \
    --tgt_id_col $TGT_ID_COL \
    --tgt_passage_col $TGT_PASSAGE_COL \
    --tgt_full_doc_col $TGT_FULL_DOC_COL \
    --tgt_lang_filter $TGT_LANG_FILTER \
    --tgt_index_path $TGT_INDEX_PATH"

echo "$CMD"
eval "$CMD"

echo "Done."