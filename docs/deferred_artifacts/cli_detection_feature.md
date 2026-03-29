# MIND CLI — Detection via Command Line

> **Status:** Enhanced — grounded in codebase analysis
> **Date:** 2026-03-29
> **Enhancement:** Spec enriched with actual class signatures, config structure, and integration patterns from `src/mind/` and `app/backend/`

---

## 1. Problem Statement

Currently, the only way to run MIND's discrepancy detection is through the **web mode** — which requires spinning up Docker containers and a full GUI frontend. This is unsuitable for:

- **Massive datasets** where GUI overhead is wasteful
- **On-premise / server deployments** with no display or limited resources
- **Automated pipelines** and batch jobs that need scriptable, headless execution
- **Development and debugging** workflows where Docker overhead is unacceptable

The goal is a **lightweight, non-invasive CLI** that wraps the existing `MIND` pipeline class with a polished Typer + Rich interface, without touching any `src/` internals.

---

## 2. Core Constraint: Non-Invasive Design

> **CRITICAL:** The CLI must NEVER modify `src/mind/` internals. Both web mode and CLI mode must coexist and call the same underlying classes.

This means:
- No changes to `MIND.__init__()` or `MIND.run_pipeline()` signatures in [src/mind/pipeline/pipeline.py](src/mind/pipeline/pipeline.py)
- No changes to `Segmenter`, `Translator`, `DataPreparer`, `PolylingualTM` APIs
- No changes to `config/config.yaml` structure
- No changes to `app/` (Flask backend remains fully functional)
- The CLI is a **thin wrapper**: load config → validate → build kwargs → call existing class

---

## 3. Scope

The CLI covers the full preprocessing → detection pipeline that today is only accessible via the web UI:

| Step | Web mode path | CLI command |
|------|--------------|-------------|
| Segmentation | Frontend → `/preprocessing/segmenter` | `mind data segment --config run.yaml` |
| Translation | Frontend → `/preprocessing/translator` | `mind data translate --config run.yaml` |
| Data preparation | Frontend → `/preprocessing/preparer` | `mind data prepare --config run.yaml` |
| Topic model training | Frontend → `/preprocessing/topicmodeling` | `mind tm train --config run.yaml` |
| Topic label generation | Frontend → `/preprocessing/labeltopic` | `mind tm label --config run.yaml` |
| Discrepancy detection | Frontend → `/detection/analyse_contradiction` | `mind detect run --config run.yaml` |

---

## 4. Architecture

The CLI lives entirely under a **new `src/mind/cli/` package** that wraps existing classes.

```
src/mind/
├── cli/
│   ├── __init__.py          ← Exports comma_separated_ints for backward compat (imported by app/backend/detection.py:17)
│   ├── main.py              ← Root Typer app (`mind`)
│   ├── _config_loader.py    ← YAML loading, deep-merge, path resolution
│   ├── _console.py          ← Rich Console singleton + helpers
│   ├── _schemas.py          ← Pydantic v2 models for config validation
│   ├── _legacy.py           ← Original cli.py body (backward compat)
│   └── commands/
│       ├── __init__.py
│       ├── data.py          ← `mind data {segment,translate,prepare}`
│       ├── detect.py        ← `mind detect {run,init-config}`
│       └── tm.py            ← `mind tm {train,label}`
├── pipeline/                ← UNTOUCHED
├── corpus_building/         ← UNTOUCHED
├── topic_modeling/          ← UNTOUCHED
└── ...
```

> **⚠️ Name collision:** The existing `src/mind/cli.py` currently defines only `comma_separated_ints` (a one-liner used by `app/backend/detection.py:566`). It **must be deleted before** the `cli/` package is created — Python cannot have both a module file and a package directory with the same name. The function must be re-exported from `cli/__init__.py` to keep the existing import `from mind.cli import comma_separated_ints` working without any changes to `app/backend/detection.py`.

---

## 5. Codebase Grounding

### 5.1 The `MIND` class — actual constructor signature

From [src/mind/pipeline/pipeline.py:144](src/mind/pipeline/pipeline.py#L144):

```python
class MIND:
    def __init__(
        self,
        llm_model: str = None,
        llm_server: str = None,
        source_corpus: Union[Corpus, dict] = None,
        target_corpus: Union[Corpus, dict] = None,
        retrieval_method: str = "TB-ENN",
        multilingual: bool = True,
        monolingual: bool = False,
        lang: str = "en",
        config_path: Path = Path("/src/config/config.yaml"),  # ← Docker path!
        logger=None,
        dry_run: bool = False,
        do_check_entailement: bool = False,   # note: typo in source (two 'e's)
        env_path=None,
        selected_categories: list = None,
    )
```

```python
def run_pipeline(self, topics, sample_size=None, previous_check=None, path_save="mind_results.parquet")
```

**Key CLI implications:**
- `config_path` defaults to `/src/config/config.yaml` (a Docker absolute path). The CLI **must** resolve and pass this explicitly as a local path — it cannot rely on the default.
- `topics` in `run_pipeline()` expects **0-indexed** integer list. The web backend converts: `[x - 1 for x in comma_separated_ints(topics)]`. The CLI must do the same.
- `path_save` is a **directory** (not a file). The pipeline writes `results_topic_<N>_<idx>.parquet` files inside it, then `process_mind_results()` consolidates them into `mind_results.parquet`.
- `monolingual=True` also sets `multilingual=False` internally. Setting both is not needed.

### 5.2 Corpus dict structure (required keys)

From [src/mind/pipeline/pipeline.py:361-405](src/mind/pipeline/pipeline.py#L361):

```python
required_keys = {"corpus_path", "id_col", "passage_col", "full_doc_col"}
# Optional keys: thetas_path, language_filter, load_thetas, filter_ids,
#                method, index_path (target only), row_top_k
```

For the **target corpus only**, an `index_path` is required — `IndexRetriever.build_or_load_index()` writes the FAISS index there.

### 5.3 The `process_mind_results()` function

From [app/backend/utils.py:219](app/backend/utils.py#L219):

This function is in `app/backend/utils.py` (a web-only module that also imports Flask). The CLI **cannot import it directly** without pulling in Flask as a dependency.

**Solution:** The CLI must either:
1. Inline the result-consolidation logic (it's ~40 lines of pure pandas), or
2. Move `process_mind_results()` to a shared location (e.g., `src/mind/utils/results.py`). This is non-invasive since it only uses `os`, `re`, and `pandas`.

The function:
- Globs all `results_topic_<N>_<idx>.parquet` files in `path_save`
- Renames columns: `source_chunk → anchor_passage`, `a_s → anchor_answer`, etc.
- Concatenates and writes `mind_results.parquet`
- Deletes all intermediate files

### 5.4 LLM backend — actual `Prompter` resolution

From [src/mind/prompter/prompter.py:40-72](src/mind/prompter/prompter.py#L40):

The `Prompter` class supports: `openai`, `ollama`, `vllm`, `llama_cpp`, `gemini`. Model routing is based on membership in `{GPT_MODELS, OLLAMA_MODELS, VLLM_MODELS, GEMINI_MODELS}` sets loaded from `config.yaml`.

`Prompter.from_config()` is the zero-config path — it reads `llm.default.backend` + `llm.default.model` from `config.yaml` and constructs the Prompter automatically. The CLI should default to this when no LLM is explicitly provided.

For **Ollama**, `llm_server` is resolved via:
```python
servers = config["ollama"]["servers"]  # Named server map (e.g., kumo01, kumo02)
default_server = config["ollama"]["default_server"]
```
So in the CLI config, either a server name OR a full URL can be accepted.

For **GPT**, the API key is loaded from `.env` (path `config["gpt"]["path_api_key"]`). The CLI should either accept `--gpt-api-key` or auto-load from `.env`.

### 5.5 `config.yaml` actual structure relevant to CLI

From [config/config.yaml](config/config.yaml):

```yaml
logger:
  dir_logger: data/logs      # ← relative path, must resolve against CWD
  log_level: INFO

optimization:
  profile: balanced          # options: balanced, memory_optimized, speed_optimized
  parquet_compression: zstd

mind:
  top_k: 10
  batch_size: 32
  min_clusters: 8
  do_weighting: True
  method: TB-ENN
  prompts:                   # ← all prompt paths are RELATIVE to project root
    question_generation: src/mind/pipeline/prompts/question_generation.txt
    ...
  cost_optimization:
    use_merged_evaluation: true
    skip_subquery_generation: true
    embedding_prefilter_threshold: 0.5
    max_questions_per_chunk: 2
    retrieval_min_score_ratio: 0.5
    retrieval_max_k: 5

llm:
  default:
    backend: gemini
    model: gemini-2.5-flash
  ollama:
    servers:
      kumo01: http://kumo01.tsc.uc3m.es:11434
      kumo02: http://kumo02.tsc.uc3m.es:11434
    default_server: kumo01
  gemini:
    path_api_key: .env
  gpt:
    path_api_key: .env
```

**Key implication:** All prompt file paths are relative to the project root. The CLI must either `chdir` to the project root before calling `MIND()`, or resolve these paths against the detected project root.

### 5.6 `Segmenter` — actual API

From [src/mind/corpus_building/segmenter.py:9](src/mind/corpus_building/segmenter.py#L9):

```python
Segmenter(config_path=Path("config/config.yaml"), logger=None)

seg.segment(
    path_df: Path,       # input parquet
    path_save: Path,     # output path (no extension — saved as parquet)
    text_col: str = "text",
    id_col: str = "id_preproc",
    min_length: int = 100,
    sep: str = "\n"
)
# Returns: path_save
```

Output always includes `id_preproc` column (generated as `<orig_id>_<para_idx>`), `full_doc`, `lang` (auto-detected), `id` (global reset).

### 5.7 `Translator` — supported language pairs

From [src/mind/corpus_building/translator.py:26](src/mind/corpus_building/translator.py#L26):

```python
supported = {
    ("en", "es"): "Helsinki-NLP/opus-mt-en-es",
    ("es", "en"): "Helsinki-NLP/opus-mt-es-en",
    ("en", "de"): "Helsinki-NLP/opus-mt-en-de",
    ("de", "en"): "Helsinki-NLP/opus-mt-de-en",
    ("en", "it"): "Helsinki-NLP/opus-mt-en-it",
    ("it", "en"): "Helsinki-NLP/opus-mt-it-en",
}
```

Only these 6 pairs are currently supported. The CLI should validate this and surface a clear error if an unsupported pair is requested.

### 5.8 `DataPreparer` — required schema and NLPipe config

From [src/mind/corpus_building/data_preparer.py:37](src/mind/corpus_building/data_preparer.py#L37):

```python
DataPreparer(
    preproc_script: Optional[str] = None,      # path to NLPipe cli.py
    config_path: Optional[str] = None,         # path to NLPipe config.json
    stw_path: Optional[str] = None,            # path to stopword lists
    python_exe: str = "python3",
    spacy_models: Optional[Dict[str, str]] = None,  # {"en": "en_core_web_sm", ...}
    schema: Optional[Dict[str, str]] = None,   # REQUIRED: maps chunk_id, text, lang, full_doc, doc_id
    config_logger_path: Path = Path("config/config.yaml"),
)
```

**Required schema fields:** `chunk_id`, `text`, `lang`, `full_doc`, `doc_id` — all must be mapped to actual column names in the parquet file.

NLPipe `config.json` uses a dataset-keyed structure (see [externals/NLPipe/config.json](externals/NLPipe/config.json)). The web backend patches the `"mind"` key dynamically before calling `DataPreparer`. The CLI must do the same.

For monolingual mode: `prep.format_monolingual(input_path, path_save)`.
For bilingual mode: `prep.format_dataframes(anchor_path, comparison_path, path_save)`.

### 5.9 `PolylingualTM` and `LDATM` — actual constructors

**PolylingualTM** (bilingual) from [src/mind/topic_modeling/polylingual_tm.py:54](src/mind/topic_modeling/polylingual_tm.py#L54):
```python
PolylingualTM(
    lang1, lang2, model_folder, num_topics,
    alpha=1.0, mallet_path="externals/Mallet-202108/bin/mallet",
    add_stops_path="src/mind/topic_modeling/stops",
    is_second_level=False
)
model.train(dataset_path)  # returns 2 on success
```

**LDATM** (monolingual) from [src/mind/topic_modeling/lda_tm.py:32](src/mind/topic_modeling/lda_tm.py#L32):
```python
LDATM(
    langs: list, model_folder: pathlib.Path, num_topics=35,
    alpha=5.0, mallet_path="src/topic_modeling/Mallet-202108/bin/mallet"
)
model.train(pathlib.Path(dataset_path))  # returns mallet_out_folder on success, None on failure
```

Both `mallet_path` defaults are **relative paths** (different between the two classes!). The CLI must accept an explicit path.

### 5.10 `TopicLabel` — actual constructor

From [src/mind/topic_modeling/topic_label.py:11](src/mind/topic_modeling/topic_label.py#L11):
```python
TopicLabel(
    lang1, lang2,          # For monolingual, use lang1 as both
    model_folder: str,     # Must contain mallet_output/ and train_data/
    llm_model=None,        # None → uses Prompter.from_config()
    llm_server=None,
    config_path=Path("config/config.yaml"),
    env_path=None
)
tl.label_topic()
```

### 5.11 `pyproject.toml` — no CLI entry point yet, no typer/rich dependencies

From [pyproject.toml](pyproject.toml): There is currently **no `[project.scripts]` section** and neither `typer` nor `rich` are listed as dependencies. Both must be added.

The project uses `hatchling` as build backend with `sources = ["src"]`, meaning `src/mind/` is the package root. A `mind` entry point maps to `mind.cli.main:app`.

The project currently uses `uv` (`[tool.uv] package = false`). This must be changed to `package = true` (or removed) to enable the entry point to be installed.

---

## 6. The `detect run` Command (Primary Feature)

This is the main deliverable — the CLI path to run discrepancy detection without Docker/web.

### 6.1 Invocation

```bash
mind detect run --config run.yaml
mind detect run --config run.yaml --topics 7,15 --sample-size 100 --dry-run
mind detect run --config run.yaml --llm-model llama3.3:70b --llm-server http://kumo01:11434
```

### 6.2 Exact `cfg` dict to build (mirrors `app/backend/detection.py:553`)

```python
cfg = {
    "llm_model": llm_model,        # None → Prompter.from_config()
    "llm_server": llm_server,      # None for gemini/default
    "source_corpus": {
        "corpus_path": ...,
        "thetas_path": ...,
        "id_col": "doc_id",
        "passage_col": "text",
        "full_doc_col": "full_doc",
        "language_filter": "EN",
        "filter_ids": None,
        "load_thetas": True,
        "method": config["method"],
    },
    "target_corpus": {
        "corpus_path": ...,
        "thetas_path": ...,
        "id_col": "doc_id",
        "passage_col": "text",
        "full_doc_col": "full_doc",
        "language_filter": "DE",
        "filter_ids": None,
        "load_thetas": True,
        "method": config["method"],
        "index_path": ...,     # Required for target
    },
    "retrieval_method": config["method"],
    "config_path": resolved_system_config_path,  # NOT the Docker default
    "env_path": None,          # or path to .env for GPT
    "monolingual": is_monolingual,
    "selected_categories": config.get("selected_categories"),
}

run_kwargs = {
    "topics": [x - 1 for x in parsed_topics],   # ← 0-indexed!
    "sample_size": sample_size or None,
    "path_save": path_save
}
```

### 6.3 Post-run: result consolidation

After `mind.run_pipeline(**run_kwargs)`, the CLI must call `process_mind_results()`. Since this function lives in `app/backend/utils.py` (Flask-dependent), the CLI should contain an inlined or relocated copy.

The function consolidates per-topic parquet checkpoints into `mind_results.parquet` and applies the column rename mapping:
```python
mapping = {
    'source_chunk': 'anchor_passage',
    'source_chunk_id': 'anchor_passage_id',
    'a_s': 'anchor_answer',
    'target_chunk': 'comparison_passage',
    'target_chunk_id': 'comparison_passage_id',
    'a_t': 'comparison_answer'
}
```

### 6.4 LLM backend support

| `llm_type` | `llm_model` | `llm_server` | Notes |
|------------|-------------|--------------|-------|
| `default` / `gemini` | `None` | `None` | `Prompter.from_config()` reads `llm.default` |
| `ollama` | e.g. `llama3.3:70b` | URL or server name | Validated against `llm.ollama.servers` |
| `vllm` | e.g. `Qwen/Qwen3-8B` | URL or server name | Similar to ollama |
| `gpt` | e.g. `gpt-4o` | N/A | API key from `.env` or `--gpt-api-key` |

For **monolingual runs**, `MIND(monolingual=True)` also needs the embedding model resolved from `config["embedding_models"]["monolingual"][lang]` rather than the multilingual model.

---

## 7. Full Command Tree

```
mind
├── detect
│   ├── run              ← Run full discrepancy detection pipeline
│   └── init-config      ← Scaffold a run.yaml template
├── data
│   ├── segment          ← Segment raw documents into passages
│   ├── translate        ← Translate passages (bilingual mode)
│   └── prepare          ← Run NLPipe preprocessing + DataPreparer
└── tm
    ├── train            ← Train topic model (LDA / Polylingual)
    └── label            ← Label topics with LLM
```

---

## 8. Config System

### 8.1 Config file format (run_config.yaml)

```yaml
# Optional: override system config llm settings
llm:
  default:
    backend: ollama
    model: llama3.3:70b

detect:
  monolingual: false               # true for monolingual corpora
  topics: [7, 15]                  # 1-indexed (CLI converts to 0-indexed internally)
  sample_size: 200                 # null = all passages in topic
  path_save: data/results
  method: TB-ENN                   # retrieval method; written to config.yaml mind.method
  do_weighting: true               # written to config.yaml mind.do_weighting
  selected_categories: null        # or list of category dicts for dynamic prompts
  source:
    corpus_path: data/corpora/polylingual_df.parquet
    thetas_path: data/corpora/thetas_EN.npz
    id_col: doc_id
    passage_col: text
    full_doc_col: full_doc
    lang_filter: EN
    filter_ids_path: null          # optional path to file with IDs to filter
  target:
    corpus_path: data/corpora/polylingual_df.parquet
    thetas_path: data/corpora/thetas_DE.npz
    id_col: doc_id
    passage_col: text
    full_doc_col: full_doc
    lang_filter: DE
    index_path: data/mind_runs/indexes  # FAISS index storage for target corpus

# Data preprocessing (for mind data segment/translate/prepare)
data:
  segment:
    input: data/raw/documents.parquet
    output: data/processed/segmented
    text_col: text
    id_col: id_preproc
    min_length: 100
    separator: "\n"
  translate:
    input: data/processed/segmented
    output: data/processed/translated
    src_lang: en
    tgt_lang: de
    text_col: text
    lang_col: lang
  prepare:
    anchor: data/processed/translated_en2de
    comparison: data/processed/translated_de2en
    output: data/processed/prepared
    schema:
      chunk_id: id_preproc
      text: text
      lang: lang
      full_doc: full_doc
      doc_id: doc_id
    nlpipe_script: externals/NLPipe/src/nlpipe/cli.py    # or null if lemmas already present
    nlpipe_config: externals/NLPipe/config.json
    stw_path: externals/NLPipe/src/nlpipe/stw_lists
    spacy_models:
      en: en_core_web_sm
      de: de_core_news_sm

# Topic modeling
tm:
  train:
    input: data/processed/prepared
    lang1: EN
    lang2: DE                    # null or omit for monolingual
    model_folder: data/models/tm_ende
    num_topics: 30
    alpha: 1.0
    mallet_path: externals/Mallet/bin/mallet
    stops_path: src/mind/topic_modeling/stops
  label:
    model_folder: data/models/tm_ende
    lang1: EN
    lang2: DE
```

### 8.2 Config merge priority

```
CLI flags  >  run_config.yaml  >  config/config.yaml (system)  >  code defaults
```

### 8.3 System config path resolution (critical for non-Docker use)

All `src/mind/` classes default to `/src/config/config.yaml` (a Docker absolute path). The CLI must resolve the real path and pass it explicitly.

Resolution chain:
1. `--system-config` CLI flag
2. `MIND_CONFIG_PATH` environment variable
3. Auto-discovery: walk up from the CLI's `__file__` location, find `config/config.yaml`
4. Fallback: `config/config.yaml` relative to CWD

> **Implementation note:** The `Prompter` and `MIND` classes call `load_yaml_config_file(config_path, section, logger)` ([src/mind/utils/utils.py:51](src/mind/utils/utils.py#L51)) — it raises `FileNotFoundError` immediately if the path doesn't exist. Failing early with a clear message is the existing behavior; the CLI just needs to pass the right path.

### 8.4 The `method`/`do_weighting` config mutation problem

The web backend **mutates `config/config.yaml`** in place before running:
```python
# app/backend/detection.py:572
data['mind']['method'] = config['method']
data['mind']['do_weighting'] = config['do_weighting']
with open('/src/config/config.yaml', 'w') as f:
    yaml.safe_dump(data, f, sort_keys=False)
```

This is a side effect of the web mode. The CLI should **not** mutate the system config. Instead, since `method` and `do_weighting` are passed through the corpus dict and `MIND.__init__()` directly (`retrieval_method=config['method']` and `do_weighting` via `self.config.get("do_weighting")`), the CLI should rely on the run config's values being correctly set and let the pipeline read them from the already-loaded config. If override is needed, the CLI can write to a **temporary copy** of the config and pass that path to `MIND()`.

---

## 9. Rich Terminal UX

### 9.1 Required behavior

Replace raw `print()` and `logging` output with:

- **Startup panel** — config summary before pipeline begins
- **Progress bars** — `rich.progress.Progress` wrapping the per-topic loop (currently uses `tqdm` in `pipeline.py:499`, which will remain)
- **Status spinners** — during `MIND.__init__()` (model loading, index building)
- **Color-coded log levels** — green = INFO, yellow = WARNING, red = ERROR
- **Completion table** — summary of results written (N records, path)

### 9.2 Log capture strategy

The `MIND` pipeline uses Python's `logging` module (via `init_logger()` in utils). The CLI should:
1. Not suppress the existing logger output
2. Optionally redirect to a `rich.logging.RichHandler` for prettier formatting
3. Leave `tqdm` progress bars untouched (they work in terminal mode)

### 9.3 Example startup panel

```
┌─────────────────────────────────────────────────────────────┐
│  MIND Detection Run                                         │
├───────────────────┬─────────────────────────────────────────┤
│  Topics           │  7, 15 (0-indexed: 6, 14)               │
│  Sample size      │  200 per topic                          │
│  Method           │  TB-ENN                                 │
│  LLM              │  llama3.3:70b (ollama @ kumo01)         │
│  Source corpus    │  EN — data/corpora/polylingual_df.parquet│
│  Target corpus    │  DE — data/corpora/polylingual_df.parquet│
│  Output           │  data/results/                          │
│  Monolingual      │  No                                     │
└───────────────────┴─────────────────────────────────────────┘
```

---

## 10. Installation

### 10.1 `pyproject.toml` changes needed

```toml
# Add to [project.optional-dependencies] or [project.dependencies]
dependencies = [
    ...existing...,
    "typer>=0.12",
    "rich>=13",
    "pydantic>=2.0",
]

# Add new section:
[project.scripts]
mind = "mind.cli.main:app"

# Change [tool.uv] from:
# package = false
# to:
# package = true
# (or remove it entirely — 'false' disables the package entry point)
```

### 10.2 Install

```bash
pip install -e .
# or with uv:
uv pip install -e .
```

---

## 11. Key Integration Points

| Component | Location | Used by CLI command | Key notes |
|-----------|----------|---------------------|-----------|
| `MIND` | [src/mind/pipeline/pipeline.py:131](src/mind/pipeline/pipeline.py#L131) | `detect run` | Pass resolved `config_path`; topics are 0-indexed |
| `Corpus` | [src/mind/pipeline/corpus.py:25](src/mind/pipeline/corpus.py#L25) | Used internally by `MIND` | Accepts dict or Corpus object |
| `Segmenter` | [src/mind/corpus_building/segmenter.py:9](src/mind/corpus_building/segmenter.py#L9) | `data segment` | Output has no file extension |
| `Translator` | [src/mind/corpus_building/translator.py:16](src/mind/corpus_building/translator.py#L16) | `data translate` | Only 6 language pairs supported |
| `DataPreparer` | [src/mind/corpus_building/data_preparer.py:36](src/mind/corpus_building/data_preparer.py#L36) | `data prepare` | Schema dict is mandatory; patches NLPipe config.json |
| `PolylingualTM` | [src/mind/topic_modeling/polylingual_tm.py:54](src/mind/topic_modeling/polylingual_tm.py#L54) | `tm train` (bilingual) | Returns `2` on success |
| `LDATM` | [src/mind/topic_modeling/lda_tm.py:32](src/mind/topic_modeling/lda_tm.py#L32) | `tm train` (monolingual) | Returns mallet folder on success, `None` on failure |
| `TopicLabel` | [src/mind/topic_modeling/topic_label.py:11](src/mind/topic_modeling/topic_label.py#L11) | `tm label` | model_folder must have `mallet_output/` and `train_data/` |
| `process_mind_results` | [app/backend/utils.py:219](app/backend/utils.py#L219) | `detect run` (post-run) | Must be inlined/moved — Flask import in utils.py |
| `config/config.yaml` | [config/config.yaml](config/config.yaml) | All commands | Use local copy, not Docker path |
| `externals/NLPipe/config.json` | [externals/NLPipe/config.json](externals/NLPipe/config.json) | `data prepare` | CLI must patch `"mind"` key before calling DataPreparer |

---

## 12. Gap Analysis

### 12.1 Critical gaps requiring resolution before implementation

| Gap | Severity | Description |
|-----|----------|-------------|
| `process_mind_results` location | **Critical** | Lives in `app/backend/utils.py` with Flask imports. CLI cannot use it directly. Must be inlined or moved to `src/mind/utils/results.py`. |
| `config.yaml` mutation for `method`/`do_weighting` | **High** | Web mode mutates system config before pipeline. CLI must use a temp config or find another safe override path. |
| `tool.uv.package = false` | **High** | Blocks entry point installation. Must be changed to `true` or removed. |
| `typer`/`rich`/`pydantic` not in dependencies | **High** | Must be added to `pyproject.toml`. |
| Topics indexing | **Medium** | Web passes 1-indexed topics to the API, converts to 0-indexed before `run_pipeline()`. CLI must document and enforce 1-indexed input, converting internally. |

### 12.2 Design decisions that need input

1. **`process_mind_results` handling:** Inline in `detect.py` vs. move to `src/mind/utils/results.py`. Moving is cleaner but constitutes a minor change to the src module layout (though not to any existing logic).

- **USER_INPUT**: To solve this and avoid error we will use the inline approach. Messier but more robust.

2. **Checkpoint resumption:** `run_pipeline()` has internal async checkpointing (`AsyncCheckpointer`). If interrupted mid-run, partial `results_topic_<N>_<idx>.parquet` files remain in `path_save`. The CLI could detect these and offer to resume (or wipe). Currently there's no resume mechanism in the pipeline itself.

- **USER_INPUT**: Since there is no resume mechanism, lets not implement it. Changes must be respectful with the web execution as not to break anything.

3. **NLPipe config.json patching:** The web backend writes `"mind": {...}` into the shared `externals/NLPipe/config.json` before calling `DataPreparer`. This is a shared-state mutation that could cause race conditions. The CLI should instead write a **temporary copy** of the config file.

- **USER_INPUT**: If you are able to do the wiring properly for the new temporary copy without breaking the flow. Go ahead.

4. **`do_check_entailment`:** This parameter exists on `MIND.__init__()` but is not exposed through the web UI. Should the CLI expose it via `--check-entailment` flag?

- **USER_INPUT**: Yes.

5. **Signal handling for graceful shutdown:** `AsyncCheckpointer` uses a background thread. On `Ctrl+C`, the CLI should call `checkpointer.shutdown()` before exiting to flush pending writes. This needs a `signal.signal(SIGINT, ...)` handler in the CLI.

- **USER_INPUT** : Yes. Shutdown must be graceful.

### 12.3 Architecture considerations

- The web backend runs the pipeline in a **separate `multiprocessing.Process`** to isolate it from Flask. The CLI runs in a single process. This is fine and preferable for CLI use, but means that an unhandled exception in the pipeline will propagate directly to the CLI.
- The `StreamForwarder` class in `app/backend/detection.py` redirects `sys.stdout`/`sys.stderr` to both a log file and the frontend endpoint. The CLI does not need this — Rich's logging handler provides equivalent terminal output, and a `--log-file` option can write plain text to disk.
- The `MIND` logger is initialized once in `__init__()`. Rich's `RichHandler` can be installed on the root logger before `MIND()` is created to capture all output.

---

## 13. Non-Goals

- No changes to Flask/web routes in `app/`
- No changes to Docker Compose or Dockerfiles
- No GUI or web server in CLI mode
- No streaming of results to frontend during CLI run
- No auth/multi-user concerns — CLI runs as single user
- No changes to `MIND.__init__()`, `run_pipeline()`, or any `src/mind/` class internals

---

## 14. Open Questions (resolved and unresolved)

| # | Question | Status | Answer | User Answer |
|---|----------|--------|--------| ----------- |
| 1 | Resume from checkpoint after interruption? | **Open** | No existing mechanism in pipeline; would require CLI-side partial result detection | Dont create this mode, it is not in the pipeline |
| 2 | `--watch` mode for live log tailing? | **Open** | Low priority; Rich live display covers real-time output | Rich already does this to an extent, not needed |
| 3 | NLPipe config.json: auto-discover or always explicit? | **Resolved** | Always explicit — required by `DataPreparer` constructor | As stated in answer |
| 4 | Write `.log` file to `path_save/`? | **Open** | Recommend yes — mirrors web mode behavior and aids debugging | Write them to path_save |
| 5 | Expose `do_check_entailment`? | **Open** | Needs user decision | Expose it |
| 6 | `method`/`do_weighting` override strategy? | **Resolved** | Write to temporary config copy, pass that path to `MIND()` | Solved |
| 7 | Where does `process_mind_results` live? | **Open (recommended)** | Move to `src/mind/utils/results.py` — pure pandas, no Flask dependency | It lives inline |
