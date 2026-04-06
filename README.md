<h1 align="center">MIND — Multilingual Inconsistent Notion Detection</h1>
<p align="center">
  <img src="figures_tables/Raupi5.png" alt="MIND pipeline" width="100%">
</p>

<p align="center">
  <a href="docs/technical-documentation.md"><strong>Docs</strong></a> · 
  <a href="https://huggingface.co/collections/lcalvobartolome/mind-data-68e2a690025b4dc28c5e8458"><strong>Datasets</strong></a> ·
  <a href="#installation"><strong>Install</strong></a> · 
  <a href="#usage"><strong>Usage</strong></a>
</p>

<p align="center">
  <img alt="License" src="https://img.shields.io/badge/license-MIT-blue.svg">
  <img alt="Python" src="https://img.shields.io/badge/python-3.12-blue.svg">
</p>

---

**MIND** is a user-in-the-loop AI pipeline that systematically detects **contradictions and factual discrepancies** within text databases. As AI agents and large context databases become central to enterprise operations, a fundamental question arises:

> *"How can my agents trust my data if it is not consistent?"*

MIND addresses this by highlighting and checking for **absolute contextual integrity** — ensuring that knowledge bases are free of contradictions and serve as reliable backbones for agentic workflows.

## Why MIND?

| Problem | MIND's Solution |
|---------|----------------|
| Enterprise knowledge bases accumulate contradictions over time | Automated discrepancy detection across the full database |
| Multilingual documentation drifts out of sync | Polylingual topic modeling + cross-language consistency checks |
| Manual auditing doesn't scale | LLM-powered pipeline with human-in-the-loop verification |
| Inconsistent context produces unreliable AI agent answers | Clean, verified knowledge bases as a foundation for agentic AI |

## Key Features

- **Multi-LLM Backend** — OpenAI, Google Gemini, Ollama, vLLM, and llama.cpp, configurable from a single YAML file. We believe in a BYOL (Bring Your Own LLM) approach.
- **Polylingual Topic Modeling** — Extract and align topics across languages (EN, ES, DE, IT).
- **Hybrid Retrieval** — Combines topic-based and embedding-based search with FAISS.
- **Lightweight CLI** — Headless command-line interface for large-scale batch processing and automated pipelines.
- **Modular Data Ingestion** — CSV, Parquet, Markdown, YAML, XML, TXT, or compressed archives (ZIP, TAR, 7z).
- **Extensible Architecture** — Add new LLM backends, parsers, or embedding models without touching core code.

---

## Pipeline Architecture

The MIND pipeline follows this data flow:

```
Raw Data → Segmenter → Translator → Data Preparer → Topic Model → MIND Pipeline → Results
                                                         │
                                    ┌────────────────────┤
                                    │                    │
                              Question            Discrepancy
                              Generation          Detection
                                    │                    │
                              Hybrid Retrieval     NLI + LLM
                              (FAISS + Topics)     Verification
```

---

## Installation

Install the MIND CLI with `uv tool`:

```bash
# Install with Python 3.12
uv tool install cli-mind-industry --python 3.12

# Verify installation
mind --help
```

**Requirements:**
- [uv](https://docs.astral.sh/uv/getting-started/installation/) (Python package installer)
- Python 3.12+

---

## Usage

The MIND CLI is a lightweight, headless interface for discrepancy detection in large-scale text databases. Run the full pipeline with a single command, or use individual subcommands for each stage.

### Quick Start

**1. Scaffold a configuration file:**

```bash
mind detect init-config --output run_config.yaml
```

This creates a template with all required sections. Edit it with your corpus paths, languages, and LLM settings.

**2. Run the full pipeline:**

```bash
mind detect run --config run_config.yaml
```

The CLI will:
- Load and validate your configuration
- Resolve system config (`config/config.yaml`) and merge overrides
- Initialize the MIND pipeline with your LLM backend
- Run discrepancy detection on specified topics
- Consolidate results into `mind_results.parquet`
- Display real-time progress and statistics

**3. Override parameters on the command line:**

```bash
# Override topics and sample size
mind detect run --config run_config.yaml --topics 7,15 --sample-size 100

# Use a different LLM backend
mind detect run --config run_config.yaml \
  --llm-model llama3.3:70b --llm-server http://kumo01:11434

# Enable entailment checking
mind detect run --config run_config.yaml --check-entailment

# Dry run (no output written)
mind detect run --config run_config.yaml --dry-run

# Write logs to a file
mind detect run --config run_config.yaml --log-file pipeline.log
```

### Command Reference

```
mind
├── detect               Discrepancy detection
│   ├── run             Run the full MIND pipeline
│   └── init-config     Scaffold a run_config.yaml template
├── data                 Data preprocessing
│   ├── segment         Segment raw documents into passages
│   ├── translate       Translate passages between languages
│   └── prepare         Run NLPipe preprocessing and DataPreparer
└── tm                   Topic modeling
    ├── train           Train a topic model (Polylingual or LDA)
    └── label           Generate topic labels using an LLM
```

Run any command with `--help` for full options:

```bash
mind detect run --help
mind data segment --help
mind tm train --help
```

### Configuration File Format

Create `run_config.yaml` with the following structure:

```yaml
# Optional: override system config LLM settings
# llm:
#   default:
#     backend: ollama
#     model: llama3.3:70b

detect:
  monolingual: false                          # bilingual or monolingual
  topics: [1, 2, 3]                           # 1-indexed topic IDs
  sample_size: null                           # null = all passages
  path_save: data/results
  method: TB-ENN                              # retrieval method
  do_weighting: true
  do_check_entailment: false
  selected_categories: null
  source:
    corpus_path: data/corpora/polylingual_df.parquet
    thetas_path: data/corpora/thetas_EN.npz
    id_col: doc_id
    passage_col: text
    full_doc_col: full_doc
    lang_filter: EN
    filter_ids_path: null
  target:
    corpus_path: data/corpora/polylingual_df.parquet
    thetas_path: data/corpora/thetas_DE.npz
    id_col: doc_id
    passage_col: text
    full_doc_col: full_doc
    lang_filter: DE
    index_path: data/indexes

# Optional: preprocessing pipeline
data:
  segment:
    input: data/raw/documents.parquet
    output: data/processed/segmented
    text_col: text
    id_col: id_preproc
    min_length: 100
    separator: "\n"
  translate:
    input: data/processed/segmented   # mixed-language dataset (EN+DE)
    output: data/processed/translated
    src_lang: en
    tgt_lang: de
    text_col: text
    lang_col: lang
    bilingual: true   # recommended: splits by lang, translates both directions
                      # outputs: translated_en2de (anchor) + translated_de2en (comparison)
  prepare:
    anchor: data/processed/translated_en2de     # output from bilingual translation
    comparison: data/processed/translated_de2en # output from bilingual translation
    output: data/processed/prepared
    schema:
      chunk_id: id_preproc
      text: text
      lang: lang
      full_doc: full_doc
      doc_id: doc_id
    nlpipe_script: externals/NLPipe/src/nlpipe/cli.py
    nlpipe_config: externals/NLPipe/config.json
    stw_path: externals/NLPipe/src/nlpipe/stw_lists
    spacy_models:
      en: en_core_web_sm
      de: de_core_news_sm

# Optional: topic modeling
tm:
  train:
    input: data/processed/prepared
    lang1: EN
    lang2: DE                               # null or omit for monolingual
    model_folder: data/models/tm_ende
    num_topics: 30
    alpha: 1.0
    mallet_path: externals/Mallet-202108/bin/mallet
    stops_path: src/mind/topic_modeling/stops
  label:
    model_folder: data/models/tm_ende
    lang1: EN
    lang2: DE
```

### Example Workflow

```bash
# 1. Scaffold config
mind detect init-config --output my_config.yaml
# Edit my_config.yaml with your paths and settings

# 2. Segment documents (optional — if starting from raw text)
mind data segment --config my_config.yaml

# 3. Translate passages (optional — for bilingual datasets)
#    Use --bilingual if your dataset has mixed languages (e.g. EN+ES in one file).
#    Splits by language, translates both directions, and outputs two ready-to-use files.
mind data translate --config my_config.yaml --bilingual

# 4. Prepare for topic modeling (optional)
#    After --bilingual translation, set prepare.anchor and prepare.comparison
#    to the two output files: translated_en2es and translated_es2en
mind data prepare --config my_config.yaml

# 5. Train topic model (optional)
mind tm train --config my_config.yaml

# 6. Label topics with LLM (optional)
mind tm label --config my_config.yaml --llm-model llama3.3:70b

# 7. Run discrepancy detection
mind detect run --config my_config.yaml --topics 1,5,10
```

### Bilingual Translation

If your dataset has **mixed languages** (e.g. EN and ES rows in the same file), use `--bilingual`. This mirrors what the web application does under the hood:

```
Mixed dataset (EN + ES rows)
             │
             ▼
     Split by language
    ┌────────┴─────────┐
  EN rows           ES rows
    │                  │
  EN→ES               ES→EN
    │                  │
    ▼                  ▼
translated_en2es   translated_de2en
    │                  │
    └──────┬───────────┘
           ▼
    mind data prepare
    (anchor + comparison)
```

```bash
# In run_config.yaml:
data:
  translate:
    input: data/processed/segmented   # mixed EN+ES dataset
    output: data/processed/translated
    src_lang: en
    tgt_lang: es
    bilingual: true                   # ← enables the bilingual flow

  prepare:
    anchor: data/processed/translated_en2es     # ← output from bilingual
    comparison: data/processed/translated_es2en # ← output from bilingual
    ...

# Or override via flag at runtime:
mind data translate --config my_config.yaml --bilingual
```

### Advanced Features

**Graceful Shutdown:** The CLI handles `Ctrl+C` gracefully, flushing all pending checkpoints before exiting.

**Custom System Config:** If `config/config.yaml` is not found:
```bash
mind detect run --config my_config.yaml --system-config /custom/path/config.yaml
# Or set environment variable:
export MIND_CONFIG_PATH=/custom/path/config.yaml
mind detect run --config my_config.yaml
```

**Supported Language Pairs for Translation:**
- English ↔ Spanish (`en`↔`es`)
- English ↔ German (`en`↔`de`)
- English ↔ Italian (`en`↔`it`)

**Topic Indexing:** Topics in config files are **1-indexed** (e.g., `topics: [1, 5, 10]`). The CLI converts them to 0-indexed internally when calling the pipeline.

### Troubleshooting

| Issue | Solution |
|-------|----------|
| `Config file not found` | Verify path in `--config` or set `MIND_CONFIG_PATH` env var |
| `System config not found` | Place `config/config.yaml` at project root or use `--system-config` |
| `Import error: mind.cli` | Run `uv pip install -e .` from project root |
| `Topics must be comma-separated integers` | Use `--topics 1,2,3` (no spaces) |
| `Unsupported language pair` | Check [supported pairs](#advanced-features) above |
| Mixed-language output has duplicates | Use `bilingual: true` in translate config (or `--bilingual` flag) |

For more details, see [docs/deferred_artifacts/cli_detection_feature.md](docs/deferred_artifacts/cli_detection_feature.md).

---

## Configuration

All pipeline behavior is controlled through [`config/config.yaml`](config/config.yaml):

| Section | What it controls |
|---------|-----------------|
| `logger` | Log directory, verbosity, and file rotation |
| `optimization` | Performance profiles (`balanced`, `memory_optimized`, `speed_optimized`) |
| `mind` | Top-k retrieval, batch size, prompt paths, embedding models, NLI model |
| `llm` | Active backend + model, temperature, available models per backend |

### Supported LLM Backends

| Backend | Models | Setup |
|---------|--------|-------|
| **Gemini** | gemini-2.5-flash, gemini-2.0-flash, etc. | API key in `.env` |
| **OpenAI** | GPT-4o, GPT-4, GPT-3.5-turbo, etc. | API key in `.env` |
| **Ollama** | Qwen 2.5, Llama 3.x, etc. | Self-hosted server URL |
| **vLLM** | Any HuggingFace model | Self-hosted server URL |
| **llama.cpp** | GGUF models | Self-hosted server URL |

---

## Project Structure

```
mind/
├── src/mind/                   # Core library
│   ├── corpus_building/        #   Segmenter, Translator, Data Preparer
│   ├── topic_modeling/         #   Polylingual Topic Model (PLTM)
│   ├── pipeline/               #   MIND detection pipeline + prompts
│   ├── ingestion/              #   Modular data ingestion (archives, parsers, schema mapping)
│   ├── prompter/               #   LLM backend abstraction layer
│   ├── cli/                    #   Command-line interface (entry points)
│   └── utils/                  #   Shared utilities and helpers
├── config/                     # Pipeline configuration (config.yaml)
├── tests/                      # Automated test suite
├── ablation/                   # Ablation study scripts and notebooks
├── use_cases/                  # Applied use cases (e.g., Wikipedia EN-DE)
├── docs/                       # Technical and functional documentation
└── pyproject.toml              # Python packaging and dependencies
```

---

## Research & Data

### ROSIE-MIND Dataset

**ROSIE-MIND** is an annotated dataset created by subsampling topics from health-domain Wikipedia articles:

- **v1**: 80 samples (*quora-distilbert-multilingual* + *qwen:32b*)
- **v2**: 651 samples (*BAAI/bge-m3* + *llama3.3:70b*)

Available on [HuggingFace](https://huggingface.co/datasets/lcalvobartolome/rosie_mind).

### Ablation Studies

Replication scripts for all experiments are included:

```bash
# Question & Answering ablation
./bash_scripts/run_answering_disc.sh

# Retrieval ablation
./bash_scripts/run_retrieval.sh

# Discrepancy detection ablation
python3 ablation/discrepancies/run_disc_ablation_controlled.py
```

See `ablation/` for full instructions and Jupyter notebooks with analysis.

### Use Cases

- **Wikipedia (DE-EN)**: End-to-end pipeline on German-English article pairs. See [`use_cases/wikipedia/`](use_cases/wikipedia/).

---

## Documentation

| Document | Audience | Content |
|----------|----------|---------|
| [Technical Documentation](docs/technical-documentation.md) | Developers | CLI architecture, modules, configuration, LLM backends |
| [Functional Documentation](docs/functional-documentation.md) | Researchers | Methodology, use cases, ablation studies |
| [Architecture Diagrams](docs/architecture-diagrams.md) | Everyone | Pipeline flow, component interactions, data structures |

---

## Contributing

Contributions are welcome. For bug reports and feature requests, please use [GitHub Issues](https://github.com/lcalvobartolome/mind/issues). For code contributions, submit a pull request.

If you use MIND in your research, please cite:

```bibtex
@inproceedings{calvo2025discrepancy,
  title={Discrepancy Detection at the Data Level: Toward Consistent Multilingual Question Answering},
  author={Calvo-Bartolom{\'e}, Lorena and Aldana, Val{\'e}rie and Cantarero, Karla and de Mesa, Alonso Madro{\~n}al and Arenas-Garc{\'\i}a, Jer{\'o}nimo and Boyd-Graber, Jordan Lee},
  booktitle={Proceedings of the 2025 Conference on Empirical Methods in Natural Language Processing},
  pages={22024--22065},
  year={2025}
}
```

## License

MIT License. Copyright (c) 2024 Lorena Calvo-Bartolomé. See [LICENSE](LICENSE) for details.

---

<p align="center">
  <a href="https://huggingface.co/collections/lcalvobartolome/mind-data-68e2a690025b4dc28c5e8458">Datasets</a> · 
  <a href="https://github.com/lcalvobartolome/mind">GitHub</a>
</p>