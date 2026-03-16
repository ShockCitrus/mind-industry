<h1 align="center">MIND — Multilingual Inconsistent Notion Detection</h1>
<p align="center">
  <img src="figures_tables/Raupi5.png" alt="MIND pipeline" width="100%">
</p>

<p align="center">
  <a href="https://mind.uc3m.es"><strong>Live Demo</strong></a> · 
  <a href="docs/technical-documentation.md"><strong>Docs</strong></a> · 
  <a href="https://huggingface.co/collections/lcalvobartolome/mind-data-68e2a690025b4dc28c5e8458"><strong>Datasets</strong></a> ·
  <a href="#installation"><strong>Install</strong></a>
</p>

<p align="center">
  <img alt="License" src="https://img.shields.io/badge/license-MIT-blue.svg">
  <img alt="Python" src="https://img.shields.io/badge/python-3.12-blue.svg">
  <img alt="Docker" src="https://img.shields.io/badge/docker-compose-2496ED.svg">
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
- **Hybrid Retrieval** — Combines topic-based and embedding-based search with FAISS
- **Interactive Web Application** — Full preprocessing, topic modeling, and discrepancy analysis through the browser. CLI version coming soon...
- **Modular Data Ingestion** — Upload CSV, Parquet, Markdown, YAML, XML, TXT, or compressed archives (ZIP, TAR, 7z). Neo4j + MongoDB access coming soon...
- **Extensible Architecture** — Add new LLM backends, parsers, or embedding models without touching core code.
- **Native Cloud / On Premise integration** — Deploy on your own infrastructure with Docker or Kubernetes. More cloud providers coming soon...


---

## Architecture

MIND runs as a **4-service Docker stack**:

```
┌─────────────────────────────────────────────────┐
│                   Frontend :5050                │
│         Flask + Jinja2 · User Interface         │
└────────────┬────────────────────┬───────────────┘
             │                    │
     ┌───────▼────────┐  ┌───────▼────────┐
     │ Backend :5001   │  │  Auth :5002     │
     │ Pipeline Engine │  │  User & Session │
     │ ML Workloads    │  │  Management     │
     └───────┬─────────┘  └───────┬────────┘
             │                    │
     ┌───────▼────────────────────▼────────┐
     │         PostgreSQL :5432             │
     │         Persistent Storage          │
     └─────────────────────────────────────┘
```

The **core pipeline** lives under `src/mind/` and follows this data flow:

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

### Option 1: Docker (Recommended)

The fastest way to run the full web application.

```bash
# Clone with submodules
git clone --recurse-submodules https://github.com/lcalvobartolome/mind.git
cd mind

# Build and start all services
docker compose build
docker compose up -d
```

Access the application at **http://localhost:5050**.

> **Environment files:** Before building, create `.env` files in `app/auth/`, `app/backend/`, and `app/frontend/`. See [`app/README.md`](app/README.md) for required variables.

### Option 2: Local Development (with uv)

For contributing or running the pipeline outside Docker.

```bash
# Clone with submodules
git clone --recurse-submodules https://github.com/lcalvobartolome/mind.git
cd mind

# Install uv (https://docs.astral.sh/uv/getting-started/installation/)
# Create and activate environment
uv venv .venv
source .venv/bin/activate   # Linux/macOS
# .venv\Scripts\activate    # Windows

# Install the package in editable mode
uv pip install -e .

# Verify
python -c "import mind; print('MIND installed successfully')"
```

---

## Usage

### Web Application

After deployment, the web application provides a guided workflow:

1. **Sign up / Log in** — Create an account to manage your datasets
2. **Upload a dataset** — Via the Profile page (supports CSV, Parquet, ZIP, MD, YAML, XML, TXT)
3. **Preprocess** — Segment, translate, and prepare your data
4. **Train a topic model** — Extract polylingual topics from your corpus
5. **Run detection** — Select topics and configure discrepancy analysis
6. **Review results** — Interactive table with filtering, labeling, and export

For a visual walkthrough, see the [Web Application Guide](app/README.md).

### CLI Pipeline

For programmatic use or large-scale batch processing:

#### 1. Preprocess Corpora

```bash
# Segment documents into passages
python3 src/mind/corpus_building/segmenter.py \
  --input INPUT_PATH --output OUTPUT_PATH \
  --text_col TEXT_COLUMN --id_col ID_COLUMN

# Translate passages between languages
python3 src/mind/corpus_building/translator.py \
  --input INPUT_PATH --output OUTPUT_PATH \
  --src_lang SRC_LANG --tgt_lang TGT_LANG \
  --text_col TEXT_COLUMN --lang_col LANG_COLUMN

# Prepare the final dataset
python3 src/mind/corpus_building/data_preparer.py \
  --anchor ANCHOR_PATH --comparison COMPARISON_PATH \
  --output OUTPUT_PATH --schema SCHEMA_JSON_OR_PATH
```

#### 2. Train a Topic Model

```bash
python3 src/mind/topic_modeling/polylingual_tm.py \
  --input PREPARED_DATASET_PATH \
  --lang1 LANG1 --lang2 LANG2 \
  --model_folder MODEL_OUTPUT_DIR \
  --num_topics NUM_TOPICS
```

#### 3. Run the MIND Pipeline

```bash
python3 src/mind/pipeline/cli.py \
  --src_corpus_path SRC_CORPUS_PATH \
  --src_thetas_path SRC_THETAS_PATH \
  --src_lang_filter SRC_LANG \
  --tgt_corpus_path TGT_CORPUS_PATH \
  --tgt_thetas_path TGT_THETAS_PATH \
  --tgt_lang_filter TGT_LANG \
  --topics TOPIC_IDS \
  --path_save RESULTS_DIR
```

Run any command with `--help` for the full list of options.

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
├── app/                        # Web application
│   ├── frontend/               #   Flask frontend (templates, static, routes)
│   ├── backend/                #   Flask backend (dataset, preprocessing, detection APIs)
│   ├── auth/                   #   Authentication service (PostgreSQL-backed)
│   └── README.md               #   Detailed web app documentation
├── src/mind/                   # Core library
│   ├── corpus_building/        #   Segmenter, Translator, Data Preparer
│   ├── topic_modeling/         #   Polylingual Topic Model (PLTM)
│   ├── pipeline/               #   MIND detection pipeline + prompts
│   ├── ingestion/              #   Modular data ingestion (archives, parsers, schema mapping)
│   ├── prompter/               #   LLM backend abstraction layer
│   └── utils/                  #   Shared utilities and helpers
├── config/                     # Pipeline configuration (config.yaml)
├── tests/                      # Automated test suite
├── ablation/                   # Ablation study scripts and notebooks
├── use_cases/                  # Applied use cases (e.g., Wikipedia EN-DE)
├── docs/                       # Technical, functional, and architecture docs
├── docker-compose.yml          # Multi-service deployment
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
| [Technical Documentation](docs/technical-documentation.md) | Developers | Stack, architecture, modules, config, deployment |
| [Functional Documentation](docs/functional-documentation.md) | Researchers | Methodology, use cases, ablation studies |
| [Architecture Diagrams](docs/architecture-diagrams.md) | Everyone | 30+ Mermaid diagrams of all system components |
| [Web App Guide](app/README.md) | Users | Screenshots, env setup, service overview |

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
  <a href="https://mind.uc3m.es">Live Demo</a> · 
  <a href="https://huggingface.co/collections/lcalvobartolome/mind-data-68e2a690025b4dc28c5e8458">Datasets</a> · 
  <a href="https://github.com/lcalvobartolome/mind">GitHub</a>
</p>