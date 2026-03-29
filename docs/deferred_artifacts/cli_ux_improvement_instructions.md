# MIND CLI UX Improvement & Professionalization — Agent Implementation Guide

> **Audience:** Agentic AI implementing this spec  
> **Last updated:** 2026-03-27  
> **Status:** Reviewed & corrected — ready for implementation

---

## 1. Executive Summary

The MIND project currently offers five separate Python scripts executed with `python3 src/mind/...` and up to 15 manual CLI arguments. The goal is to consolidate them into **one installable command** (`mind`) with semantic subcommands, declarative YAML-based configuration, Pydantic-validated config, and polished Rich terminal output — while making **zero changes to the underlying pipeline classes**.

### What changes
| Area | Currently | After |
|------|-----------|-------|
| Entry point | `python3 src/mind/cli.py ...` | `mind detect run --config run.yaml` |
| Segmentation | `python3 src/mind/corpus_building/segmenter.py ...` | `mind data segment --config run.yaml` |
| Translation | `python3 src/mind/corpus_building/translator.py ...` | `mind data translate --config run.yaml` |
| Data preparation | `python3 src/mind/corpus_building/data_preparer.py ...` | `mind data prepare --config run.yaml` |
| Topic modeling | `python3 src/mind/topic_modeling/polylingual_tm.py ...` | `mind tm train --config run.yaml` |
| Terminal output | Raw `print()` / `logging` | Rich tables, progress bars, formatted output |
| Installation | None (`PYTHONPATH` hacks) | `pip install -e .` → `mind` is on `$PATH` |

### What does NOT change
- `MIND.__init__()` / `run_pipeline()` signatures in `src/mind/pipeline/pipeline.py`
- `Segmenter`, `Translator`, `DataPreparer`, `PolylingualTM` class APIs
- `config/config.yaml` structure and semantics
- Docker multi-stage build pipeline (`app/backend/Dockerfile`)
- Flask web application in `app/`

---

## 2. Architecture Overview

> [!IMPORTANT]
> The existing `src/mind/cli.py` **must be deleted** before creating the `src/mind/cli/` package.
> Python cannot have both a module file and a package directory with the same name.
> The old `cli.py` body is preserved in `src/mind/cli/_legacy.py` for backward compatibility.

```
src/mind/
├── cli/                         ← NEW package (replaces old cli.py)
│   ├── __init__.py              ← Empty init
│   ├── main.py                  ← Root Typer app, version, global options
│   ├── _config_loader.py        ← YAML loading + merge + path resolution
│   ├── _console.py              ← Rich Console singleton + helpers
│   ├── _schemas.py              ← Pydantic models for config validation
│   ├── _legacy.py               ← Old cli.py body (backward compat)
│   └── commands/
│       ├── __init__.py
│       ├── data.py              ← `mind data {segment,translate,prepare}`
│       ├── detect.py            ← `mind detect {run,init-config}`
│       └── tm.py                ← `mind tm {train}`
├── pipeline/                    ← UNTOUCHED
├── corpus_building/             ← UNTOUCHED
├── topic_modeling/              ← UNTOUCHED
└── ...
```

**Design principles:**
1. **Thin wrapper only** — Each command loads config → validates with Pydantic → builds the kwargs dict → calls the existing class method. No business logic in the CLI layer.
2. **Config-first** — Every subcommand accepts `--config path.yaml`. Individual flags override config values. If neither flag nor config provides a required value, the command exits with a clear error message and exit code 1.
3. **Existing `config.yaml` reuse** — The run config file extends the existing `config/config.yaml` schema with new top-level sections (`detect`, `data`, `tm`). The system layer config sections (`logger`, `optimization`, `mind`, `llm`) are left untouched and loaded by the pipeline classes as they always have been.
4. **Fail fast** — Pydantic validation catches config errors immediately with human-readable messages, rather than crashing deep in the pipeline with inscrutable tracebacks.
5. **Graceful shutdown** — Signal handlers ensure `AsyncCheckpointer` flushes pending writes on Ctrl+C.

---

## 3. Extended Config Schema

The existing `config/config.yaml` contains system-level settings (`logger`, `optimization`, `mind`, `llm`). Run-specific settings will be added as **new top-level sections** in a separate run config file that the user provides via `--config`. The CLI will merge this on top of the system config.

### 3.1 Example Run Config File (`run_config.yaml`)

```yaml
# ---------------------------------------------------------------
# Run-specific configuration (extends config/config.yaml)
# ---------------------------------------------------------------

# Override system config if needed (optional)
llm:
  default:
    backend: ollama
    model: llama3.3:70b

# --- Detection run settings ---
detect:
  topics: [7, 15]
  sample_size: 200
  path_save: data/mind_runs/ende/results
  dry_run: false
  no_entailment: false
  previous_check: null       # Path to file with IDs from previous checks
  load_thetas: true
  source:
    corpus_path: data/corpora/polylingual_df.parquet
    thetas_path: data/corpora/thetas_EN.npz
    id_col: doc_id            # default
    passage_col: text         # default
    full_doc_col: full_doc    # default
    lang_filter: EN           # default
    filter_ids_path: null
  target:
    corpus_path: data/corpora/polylingual_df.parquet
    thetas_path: data/corpora/thetas_DE.npz
    id_col: doc_id
    passage_col: text
    full_doc_col: full_doc
    lang_filter: DE
    index_path: data/mind_runs/ende/indexes
    filter_ids_path: null

# --- Data preprocessing settings ---
data:
  segment:
    input: data/raw/documents.parquet
    output: data/processed/segmented.parquet
    text_col: text
    min_length: 100
    separator: "\n"
  translate:
    input: data/processed/segmented.parquet
    output: data/processed/translated.parquet
    src_lang: en
    tgt_lang: de
    text_col: text
    lang_col: lang
  prepare:
    anchor: data/processed/segmented.parquet
    comparison: data/processed/translated.parquet
    output: data/processed/prepared.parquet
    schema:
      chunk_id: id_preproc
      text: text
      lang: lang
      full_doc: full_doc
      doc_id: doc_id
    # NLPipe preprocessing (optional — if omitted, input must already have 'lemmas' column)
    preproc_script: null       # e.g. externals/NLPipe/src/nlpipe/main.py
    nlpipe_config: null        # e.g. config.json
    stw_path: null             # e.g. externals/NLPipe/stw
    spacy_models:              # Required if preproc_script is set
      en: en_core_web_sm
      de: de_core_news_sm

# --- Topic modeling settings ---
tm:
  train:
    input: data/processed/prepared.parquet
    lang1: EN
    lang2: DE
    model_folder: data/models/tm_ende
    num_topics: 30
    alpha: 1.0
    mallet_path: externals/Mallet-202108/bin/mallet   # Path to Mallet binary
    stops_path: src/mind/topic_modeling/stops           # Stopword lists directory
```

### 3.2 Config Load & Merge Logic

```
Priority (highest to lowest):
  1. Explicit CLI flags (e.g., --topics 7,15)
  2. Run config file (--config run_config.yaml)
  3. System config file (config/config.yaml) — always loaded as base
  4. Hardcoded defaults in code / Pydantic model defaults
```

The `_config_loader.py` module:
1. Resolves the system config path using a resolution chain (see Section 4.4).
2. Loads `config/config.yaml` as the base.
3. Deep-merges the user's `--config` file on top.
4. Overlays any explicit CLI flags.
5. Returns a `ConfigResult` containing the merged dict AND the resolved system config path (needed by pipeline classes).
6. Pydantic validation is applied by each command after extracting its relevant section.

---

## 4. Detailed Implementation Steps

### Step 1 — Add Dependencies & Fix pyproject.toml

**Files to modify:** `pyproject.toml`, `requirements.txt`, `app/backend/requirements.txt`

| Package | Why | Size impact |
|---------|-----|-------------|
| `typer>=0.12` | CLI framework with type hints, auto-help, subcommands | ~100 KB |
| `pydantic>=2.0` | Config schema validation with clear error messages | ~2 MB |

> [!IMPORTANT]
> - Do NOT add `typer[all]` — that pulls in `shellingham` and `click-completion` which are unnecessary. Use bare `typer`. Rich is already a transitive dependency of Typer ≥0.12.
> - Do NOT add `rich>=13.0` as a separate explicit dependency — let Typer manage this to avoid version conflicts.

**Actions:**
1. Add `"typer>=0.12"` and `"pydantic>=2.0"` to the `dependencies` list in `pyproject.toml`.
2. Add `typer>=0.12` and `pydantic>=2.0` to the root `requirements.txt`.
3. Add `typer>=0.12` and `pydantic>=2.0` to `app/backend/requirements.txt`.
4. **Fix `[tool.uv]`**: Change `package = false` to `package = true` in `pyproject.toml`. Without this, `uv pip install -e .` refuses to create the console script entry point.
5. Verify the Docker build still works by running `docker compose build backend`.

> [!WARNING]
> `requirements.txt` (root) and `pyproject.toml` currently have divergent dependencies (e.g., `faiss-gpu-cu12` vs `faiss-cpu`, `google-genai` in one but not the other). Reconcile them or document that `requirements.txt` is GPU-specific and `pyproject.toml` is the canonical source.

---

### Step 2 — Delete Old `cli.py` and Create `src/mind/cli/` Package

> [!CAUTION]
> **You MUST delete `src/mind/cli.py` BEFORE creating `src/mind/cli/`.** Python cannot have both a module file and a package directory with the same name. All subsequent steps depend on this.

**Procedure:**
1. Move the body of `src/mind/cli.py` (the `build_parser`, `comma_separated_ints`, and `main` functions) into `src/mind/cli/_legacy.py`.
2. Delete `src/mind/cli.py`.
3. Create the `src/mind/cli/` directory with all files below.

**Files to create:**

#### 2.1 `src/mind/cli/__init__.py`
Empty init file.

#### 2.2 `src/mind/cli/commands/__init__.py`
Empty init file.

#### 2.3 `src/mind/cli/_console.py` — Rich Console Singleton

Provide a shared `Console` instance and helper functions for consistent output formatting across all commands.

```python
"""Shared Rich console and output helpers."""
import time
from contextlib import contextmanager
from typing import Any, Dict

from rich.console import Console
from rich.table import Table

console = Console()


def print_header(title: str) -> None:
    """Print a styled section header."""
    console.rule(f"[bold cyan]{title}[/bold cyan]")


def print_success(message: str) -> None:
    console.print(f"[bold green]✓[/bold green] {message}")


def print_error(message: str) -> None:
    console.print(f"[bold red]✗[/bold red] {message}")


def print_warning(message: str) -> None:
    console.print(f"[bold yellow]⚠[/bold yellow] {message}")


def _flatten_dict(d: Dict[str, Any], parent_key: str = "", sep: str = ".") -> Dict[str, Any]:
    """Flatten a nested dict into dotted keys for table display."""
    items = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(_flatten_dict(v, new_key, sep).items())
        else:
            items.append((new_key, v))
    return dict(items)


def print_config_table(config: dict, title: str = "Configuration") -> None:
    """Render a key-value config dict as a Rich table. Nested dicts are flattened with dotted keys."""
    table = Table(title=title, show_header=True)
    table.add_column("Parameter", style="cyan")
    table.add_column("Value", style="white")
    flat = _flatten_dict(config)
    for key, value in flat.items():
        table.add_row(str(key), str(value))
    console.print(table)


@contextmanager
def timed_operation(title: str):
    """Context manager that prints a header, yields, then prints elapsed time."""
    print_header(title)
    start = time.perf_counter()
    yield
    elapsed = time.perf_counter() - start
    print_success(f"Completed in {elapsed:.1f}s")
```

#### 2.4 `src/mind/cli/_config_loader.py` — YAML Config Loading & Merging

This module implements config loading, deep-merge, path resolution, and CLI-flag overlay logic.

**Key design decisions:**
- Returns a `ConfigResult` namedtuple containing both the merged dict AND the resolved system config path (the pipeline classes need the path, not the dict).
- System config path is resolved via a chain: explicit flag → `MIND_CONFIG` env var → walk up from CWD → hardcoded default.

```python
"""YAML configuration loader with deep-merge support and path resolution."""
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional
import copy
import yaml


@dataclass
class ConfigResult:
    """Result of config loading — includes both the merged dict and the resolved system config path."""
    config: dict
    system_config_path: Path


def _resolve_system_config(explicit_path: Optional[Path] = None) -> Path:
    """Resolve the system config path using a priority chain.
    
    Resolution order:
      1. Explicit --system-config flag
      2. MIND_CONFIG environment variable
      3. Walk up from CWD looking for config/config.yaml
      4. Fall back to config/config.yaml relative to CWD
    """
    # 1. Explicit flag
    if explicit_path and explicit_path.exists():
        return explicit_path.resolve()

    # 2. Environment variable
    env_path = os.environ.get("MIND_CONFIG")
    if env_path:
        p = Path(env_path)
        if p.exists():
            return p.resolve()

    # 3. Walk up from CWD
    current = Path.cwd()
    for parent in [current, *current.parents]:
        candidate = parent / "config" / "config.yaml"
        if candidate.exists():
            return candidate.resolve()

    # 4. Fallback (will raise FileNotFoundError downstream if missing)
    return Path("config/config.yaml").resolve()


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge override into base. override wins on conflicts."""
    result = copy.deepcopy(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def load_config(
    run_config_path: Optional[Path] = None,
    system_config_path: Optional[Path] = None,
    cli_overrides: Optional[Dict[str, Any]] = None,
) -> ConfigResult:
    """Load and merge system config, run config, and CLI overrides.
    
    Returns a ConfigResult with both the merged dict and the resolved
    system config path (needed by pipeline classes that load their own
    config sections from the file).
    """
    resolved_system = _resolve_system_config(system_config_path)

    # 1. System config (always loaded)
    if not resolved_system.exists():
        raise FileNotFoundError(
            f"System config not found: {resolved_system}\n"
            f"Set MIND_CONFIG env var or use --system-config flag."
        )
    with open(resolved_system) as f:
        system = yaml.safe_load(f) or {}

    # 2. Run config (user-supplied, optional)
    merged = system
    if run_config_path:
        if not Path(run_config_path).exists():
            raise FileNotFoundError(f"Run config not found: {run_config_path}")
        with open(run_config_path) as f:
            run = yaml.safe_load(f) or {}
        merged = _deep_merge(system, run)

    # 3. CLI overrides (highest priority)
    if cli_overrides:
        merged = _deep_merge(merged, cli_overrides)

    return ConfigResult(config=merged, system_config_path=resolved_system)
```

#### 2.5 `src/mind/cli/_schemas.py` — Pydantic Config Validation

> [!IMPORTANT]
> Config validation is **not optional** for enterprise grade. A typo like `topcs` instead of `topics` in YAML would silently become `None` and crash deep in the pipeline. Pydantic catches these immediately with human-readable errors.

```python
"""Pydantic models for CLI config validation."""
from pathlib import Path
from typing import Dict, List, Optional
from pydantic import BaseModel, field_validator


# --- Detect schemas ---

class CorpusSourceConfig(BaseModel):
    corpus_path: str
    thetas_path: str
    id_col: str = "doc_id"
    passage_col: str = "text"
    full_doc_col: str = "full_doc"
    lang_filter: str = "EN"
    filter_ids_path: Optional[str] = None

class CorpusTargetConfig(BaseModel):
    corpus_path: str
    thetas_path: str
    id_col: str = "doc_id"
    passage_col: str = "text"
    full_doc_col: str = "full_doc"
    lang_filter: str
    index_path: str
    filter_ids_path: Optional[str] = None

class DetectConfig(BaseModel):
    topics: List[int]
    path_save: str
    sample_size: Optional[int] = None
    dry_run: bool = False
    no_entailment: bool = False
    previous_check: Optional[str] = None
    load_thetas: bool = False
    source: CorpusSourceConfig
    target: CorpusTargetConfig

    @field_validator("topics", mode="before")
    @classmethod
    def parse_topics(cls, v):
        if isinstance(v, str):
            return [int(x.strip()) for x in v.split(",")]
        return v


# --- Data schemas ---

class SegmentConfig(BaseModel):
    input: str
    output: str
    text_col: str = "text"
    min_length: int = 100
    separator: str = "\n"

class TranslateConfig(BaseModel):
    input: str
    output: str
    src_lang: str
    tgt_lang: str
    text_col: str = "text"
    lang_col: str = "lang"

class PrepareSchemaMap(BaseModel):
    chunk_id: str
    text: str
    lang: str
    full_doc: str
    doc_id: str

class PrepareConfig(BaseModel):
    anchor: str
    comparison: str
    output: str
    schema: PrepareSchemaMap
    preproc_script: Optional[str] = None
    nlpipe_config: Optional[str] = None
    stw_path: Optional[str] = None
    spacy_models: Optional[Dict[str, str]] = None


# --- Topic Modeling schemas ---

class TmTrainConfig(BaseModel):
    input: str
    lang1: str
    lang2: str
    model_folder: str
    num_topics: int
    alpha: float = 1.0
    mallet_path: str = "externals/Mallet-202108/bin/mallet"
    stops_path: str = "src/mind/topic_modeling/stops"
```

#### 2.6 `src/mind/cli/_legacy.py` — Old CLI Body (Backward Compat)

Move the **entire current body** of `src/mind/cli.py` (the `build_parser`, `comma_separated_ints`, and `main` functions) into this file unchanged. Add a deprecation warning at the top of `main()`:

```python
"""Legacy CLI entry point — preserved for backward compatibility."""
import warnings

# ... (paste the full body of the current cli.py here, unchanged) ...

# Wrap the existing main() to add a deprecation warning:
_original_main = main

def main():
    warnings.warn(
        "Running via the legacy CLI is deprecated. "
        "Use 'mind detect run --config ...' instead. "
        "See docs/cli_usage.md for migration instructions.",
        DeprecationWarning,
        stacklevel=2,
    )
    _original_main()
```

---

### Step 3 — Implement Command Modules

Each command module is a Typer sub-application with one or more commands. Every command follows the same pattern:

```
1. Accept --config (Path, optional) and specific CLI flags.
2. Call _config_loader.load_config(), receiving a ConfigResult.
3. Extract the relevant section from the merged config dict.
4. Validate with the corresponding Pydantic model (fail fast on errors).
5. Print a Rich summary table of the resolved configuration.
6. Instantiate the target class, passing system_config_path explicitly.
7. Call the target method.
8. Print a Rich success summary with elapsed time.
9. On error: catch exceptions, print_error() + console.print_exception(), exit code 2.
```

#### 3.1 `src/mind/cli/commands/data.py` — Preprocessing Commands

Contains three commands: `segment`, `translate`, `prepare`.

**`mind data segment`**

| CLI Flag | Config Key | Required | Default |
|----------|-----------|----------|---------|
| `--config` | — | No | `None` |
| `--input` | `data.segment.input` | **Yes** (from either) | — |
| `--output` | `data.segment.output` | **Yes** | — |
| `--text-col` | `data.segment.text_col` | No | `text` |
| `--min-length` | `data.segment.min_length` | No | `100` |
| `--separator` | `data.segment.separator` | No | `\n` |
| `--dry-run` | — | No | `False` |

Implementation logic:
```python
from mind.cli._schemas import SegmentConfig

# 1. Load & merge config
result = load_config(run_config_path=config, system_config_path=system_config,
                     cli_overrides=overrides)
cfg = result.config

# 2. Validate
seg_cfg = SegmentConfig(**cfg.get("data", {}).get("segment", {}))

# 3. Print resolved config
print_config_table(seg_cfg.model_dump(), title="Segment Configuration")

# 4. Dry run check
if dry_run:
    print_warning("Dry run — exiting without processing.")
    raise typer.Exit()

# 5. Execute (thin wrapper)
with timed_operation("Segmentation"):
    segmenter = Segmenter(config_path=result.system_config_path)
    result_path = segmenter.segment(
        path_df=Path(seg_cfg.input),
        path_save=Path(seg_cfg.output),
        text_col=seg_cfg.text_col,
        min_length=seg_cfg.min_length,
        sep=seg_cfg.separator,
    )
    print_success(f"Output saved to {result_path}")
```

**`mind data translate`**

| CLI Flag | Config Key | Required | Default |
|----------|-----------|----------|---------|
| `--config` | — | No | `None` |
| `--input` | `data.translate.input` | **Yes** | — |
| `--output` | `data.translate.output` | **Yes** | — |
| `--src-lang` | `data.translate.src_lang` | **Yes** | — |
| `--tgt-lang` | `data.translate.tgt_lang` | **Yes** | — |
| `--text-col` | `data.translate.text_col` | No | `text` |
| `--lang-col` | `data.translate.lang_col` | No | `lang` |
| `--dry-run` | — | No | `False` |

Implementation logic:
```python
from mind.cli._schemas import TranslateConfig

tr_cfg = TranslateConfig(**cfg.get("data", {}).get("translate", {}))

with timed_operation("Translation"):
    translator = Translator(config_path=result.system_config_path)
    translated_df = translator.translate(
        path_df=Path(tr_cfg.input),
        src_lang=tr_cfg.src_lang,
        tgt_lang=tr_cfg.tgt_lang,
        text_col=tr_cfg.text_col,
        lang_col=tr_cfg.lang_col,
        save_path=tr_cfg.output,
    )
    print_success(f"Translated {len(translated_df)} rows → {tr_cfg.output}")
```

**`mind data prepare`**

| CLI Flag | Config Key | Required | Default |
|----------|-----------|----------|---------|
| `--config` | — | No | `None` |
| `--anchor` | `data.prepare.anchor` | **Yes** | — |
| `--comparison` | `data.prepare.comparison` | **Yes** | — |
| `--output` | `data.prepare.output` | **Yes** | — |
| `--schema` | `data.prepare.schema` | **Yes** | — |
| `--preproc-script` | `data.prepare.preproc_script` | No | `None` |
| `--nlpipe-config` | `data.prepare.nlpipe_config` | No | `None` |
| `--stw-path` | `data.prepare.stw_path` | No | `None` |
| `--dry-run` | — | No | `False` |

> [!NOTE]
> When `--schema` is passed as a CLI flag (not from config), it accepts either a JSON string or a path to a JSON file, matching the existing `data_preparer.py __main__` behavior. When loaded from YAML config, it is parsed as a YAML dict automatically.

Implementation logic:
```python
from mind.cli._schemas import PrepareConfig

prep_cfg = PrepareConfig(**cfg.get("data", {}).get("prepare", {}))

# Build constructor kwargs — NLPipe params are optional
preparer_kwargs = {
    "schema": prep_cfg.schema.model_dump(),
    "config_logger_path": result.system_config_path,
}
if prep_cfg.preproc_script:
    preparer_kwargs["preproc_script"] = prep_cfg.preproc_script
if prep_cfg.nlpipe_config:
    preparer_kwargs["config_path"] = prep_cfg.nlpipe_config
if prep_cfg.stw_path:
    preparer_kwargs["stw_path"] = prep_cfg.stw_path
if prep_cfg.spacy_models:
    preparer_kwargs["spacy_models"] = prep_cfg.spacy_models

with timed_operation("Data Preparation"):
    preparer = DataPreparer(**preparer_kwargs)
    final_df = preparer.format_dataframes(
        anchor_path=Path(prep_cfg.anchor),
        comparison_path=Path(prep_cfg.comparison),
        path_save=Path(prep_cfg.output),
    )
    print_success(f"Prepared {len(final_df)} rows → {prep_cfg.output}")
```

#### 3.2 `src/mind/cli/commands/detect.py` — Detection Commands

**`mind detect run`** — This is the **main command**, replacing the old `cli.py`.

| CLI Flag | Config Key | Required | Default |
|----------|-----------|----------|---------|
| `--config` | — | No | `None` |
| `--topics` | `detect.topics` | **Yes** | — |
| `--sample-size` | `detect.sample_size` | No | `None` |
| `--path-save` | `detect.path_save` | **Yes** | — |
| `--llm-model` | `llm.default.model` | No | from config |
| `--llm-server` | — | No | `None` |
| `--dry-run` | `detect.dry_run` | No | `False` |
| `--no-entailment` | `detect.no_entailment` | No | `False` |
| `--print-config` | — | No | `False` |

Implementation logic:
```python
import signal
from typing import List, Optional
from pathlib import Path

from mind.cli._config_loader import load_config
from mind.cli._console import (
    console, print_config_table, print_error, print_success, print_warning, timed_operation,
)
from mind.cli._schemas import DetectConfig
from mind.pipeline.pipeline import MIND


def _read_filter_ids(path: Optional[str]) -> Optional[List[str]]:
    """Read a file of IDs (one per line) for corpus filtering."""
    if not path:
        return None
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Filter IDs file not found: {path}")
    with open(p) as f:
        return [line.strip() for line in f if line.strip()]


# Inside the run() command function:

# 1. Load & merge config
result = load_config(run_config_path=config, system_config_path=system_config,
                     cli_overrides=overrides)
cfg = result.config

# 2. Validate the detect section with Pydantic
detect_cfg = DetectConfig(**cfg.get("detect", {}))

# 3. Print resolved config
if print_config:
    print_config_table(detect_cfg.model_dump(), title="Detection Configuration")

# 4. Read filter IDs from files
src_filter_ids = _read_filter_ids(detect_cfg.source.filter_ids_path)
tgt_filter_ids = _read_filter_ids(detect_cfg.target.filter_ids_path)

# 5. Build the EXACTLY same dicts that the old cli.py passes
source_corpus = {
    "corpus_path": detect_cfg.source.corpus_path,
    "thetas_path": detect_cfg.source.thetas_path,
    "id_col": detect_cfg.source.id_col,
    "passage_col": detect_cfg.source.passage_col,
    "full_doc_col": detect_cfg.source.full_doc_col,
    "language_filter": detect_cfg.source.lang_filter,
    "filter_ids": src_filter_ids,
    "load_thetas": detect_cfg.load_thetas,
}
target_corpus = {
    "corpus_path": detect_cfg.target.corpus_path,
    "thetas_path": detect_cfg.target.thetas_path,
    "id_col": detect_cfg.target.id_col,
    "passage_col": detect_cfg.target.passage_col,
    "full_doc_col": detect_cfg.target.full_doc_col,
    "language_filter": detect_cfg.target.lang_filter,
    "filter_ids": tgt_filter_ids,
    "load_thetas": detect_cfg.load_thetas,
    "index_path": detect_cfg.target.index_path,
}

mind_cfg = {
    "llm_model": cfg.get("llm", {}).get("default", {}).get("model"),
    "llm_server": cfg.get("llm_server"),
    "source_corpus": source_corpus,
    "target_corpus": target_corpus,
    "dry_run": detect_cfg.dry_run,
    "do_check_entailement": not detect_cfg.no_entailment,
    "config_path": result.system_config_path,  # Critical: pass the resolved path
}

# 6. Register signal handler for graceful shutdown
mind_instance = None
def _handle_sigint(sig, frame):
    console.print("\n[bold yellow]⚠ Interrupted — flushing pending checkpoints…[/]")
    if mind_instance and hasattr(mind_instance, '_checkpointer') and mind_instance._checkpointer:
        mind_instance._checkpointer.wait_complete(timeout=30.0)
        mind_instance._checkpointer.shutdown()
        print_success("Checkpoints flushed.")
    raise SystemExit(130)
signal.signal(signal.SIGINT, _handle_sigint)

# 7. Instantiate and run
with timed_operation("Detection Pipeline"):
    mind_instance = MIND(**mind_cfg)
    mind_instance.run_pipeline(
        topics=detect_cfg.topics,
        path_save=detect_cfg.path_save,
        sample_size=detect_cfg.sample_size,
        previous_check=detect_cfg.previous_check,
    )
    print_success(f"Results saved to {detect_cfg.path_save}")
```

**`mind detect init-config`** — Scaffolds a run config template.

Prints a **fully commented** YAML template to stdout, including ALL optional fields with their defaults commented out, so users can redirect it: `mind detect init-config > my_run.yaml`.

The template should include every config key from Section 3.1 plus all optional parameters like `mallet_path`, `stops_path`, `preproc_script`, `nlpipe_config`, `stw_path`, `spacy_models`, etc.

#### 3.3 `src/mind/cli/commands/tm.py` — Topic Modeling Commands

**`mind tm train`**

| CLI Flag | Config Key | Required | Default |
|----------|-----------|----------|---------|
| `--config` | — | No | `None` |
| `--input` | `tm.train.input` | **Yes** | — |
| `--lang1` | `tm.train.lang1` | **Yes** | — |
| `--lang2` | `tm.train.lang2` | **Yes** | — |
| `--model-folder` | `tm.train.model_folder` | **Yes** | — |
| `--num-topics` | `tm.train.num_topics` | **Yes** | — |
| `--alpha` | `tm.train.alpha` | No | `1.0` |
| `--mallet-path` | `tm.train.mallet_path` | No | `externals/Mallet-202108/bin/mallet` |
| `--stops-path` | `tm.train.stops_path` | No | `src/mind/topic_modeling/stops` |
| `--dry-run` | — | No | `False` |

Implementation logic:
```python
import pathlib
from mind.cli._schemas import TmTrainConfig

tm_cfg = TmTrainConfig(**cfg.get("tm", {}).get("train", {}))

# Validate Mallet binary exists
mallet = Path(tm_cfg.mallet_path)
if not mallet.exists():
    print_error(
        f"Mallet binary not found at: {mallet}\n"
        f"Install Mallet or set --mallet-path / tm.train.mallet_path in config."
    )
    raise typer.Exit(code=1)

with timed_operation("Topic Model Training"):
    ptm = PolylingualTM(
        lang1=tm_cfg.lang1,
        lang2=tm_cfg.lang2,
        model_folder=pathlib.Path(tm_cfg.model_folder),
        num_topics=tm_cfg.num_topics,
        alpha=tm_cfg.alpha,
        mallet_path=tm_cfg.mallet_path,
        add_stops_path=tm_cfg.stops_path,
    )
    ptm.train(df_path=pathlib.Path(tm_cfg.input))
    print_success(f"Model saved to {tm_cfg.model_folder}")
```

---

### Step 4 — Create Root Application (`src/mind/cli/main.py`)

This is the entry point that assembles all subcommand groups and defines global options.

```python
"""MIND CLI — Unified command-line interface for the MIND pipeline."""
import typer
from typing import Optional
from pathlib import Path

from mind.cli.commands import data, detect, tm
from mind.cli._console import console

# --- Exit code constants ---
EXIT_SUCCESS = 0
EXIT_CONFIG_ERROR = 1
EXIT_RUNTIME_ERROR = 2
EXIT_INTERRUPTED = 130

app = typer.Typer(
    name="mind",
    help="MIND — Multilingual Information Discrepancy Detection",
    no_args_is_help=True,
    rich_markup_mode="rich",
)

# Register subcommand groups
app.add_typer(data.app, name="data", help="Data preprocessing (segment, translate, prepare)")
app.add_typer(detect.app, name="detect", help="Discrepancy detection pipeline")
app.add_typer(tm.app, name="tm", help="Topic modeling")


@app.callback()
def main(
    ctx: typer.Context,
    version: bool = typer.Option(
        False, "--version", "-V", help="Show version and exit."
    ),
    system_config: Optional[Path] = typer.Option(
        None, "--system-config", envvar="MIND_CONFIG",
        help="Path to system config.yaml. Default: auto-resolved from CWD.",
    ),
    verbose: int = typer.Option(
        0, "--verbose", "-v", count=True,
        help="Increase verbosity (-v for INFO, -vv for DEBUG).",
    ),
    quiet: bool = typer.Option(
        False, "--quiet", "-q",
        help="Suppress all output except errors. For CI/scripted usage.",
    ),
):
    """MIND — Multilingual Information Discrepancy Detection CLI."""
    if version:
        try:
            from importlib.metadata import version as get_version
            v = get_version("mind")
        except Exception:
            v = "0.1.0-dev"
        typer.echo(f"mind {v}")
        raise typer.Exit()

    # Store global options in Typer context for subcommands to access
    ctx.ensure_object(dict)
    ctx.obj["system_config"] = system_config
    ctx.obj["verbose"] = verbose
    ctx.obj["quiet"] = quiet

    # Configure console based on verbosity
    if quiet:
        console.quiet = True


def entrypoint():
    """Console script entry point."""
    app()


if __name__ == "__main__":
    entrypoint()
```

**Key changes from original:**
- `-V` for version (not `-v`) — `-v` is reserved for verbose per POSIX convention.
- `--system-config` global option, passed to all subcommands via `typer.Context`.
- `--verbose` / `-v` with `count=True` for increasing verbosity levels.
- `--quiet` / `-q` for CI/scripted environments.
- Version fallback to `"0.1.0-dev"` when package metadata is unavailable (e.g., PYTHONPATH-based development).

---

### Step 5 — Register Console Script in `pyproject.toml`

Add the following section to `pyproject.toml`:

```toml
[project.scripts]
mind = "mind.cli.main:entrypoint"
```

**Also change** the existing `[tool.uv]` section:

```toml
[tool.uv]
package = true
```

After this, `pip install -e .` (or `uv pip install -e .`) will make the `mind` command globally available on `$PATH`.

---

### Step 6 — Backward Compatibility

Since `src/mind/cli.py` was deleted (Step 2), the old invocation `python3 src/mind/cli.py ...` will no longer work.

**Migration strategy:**
1. The old CLI body is preserved in `src/mind/cli/_legacy.py` (see Step 2.6).
2. Create an optional wrapper script at `scripts/legacy_detect.py` for users who need the old invocation:

```python
#!/usr/bin/env python3
"""Backward compatibility shim — delegates to the legacy CLI.

Usage: python3 scripts/legacy_detect.py [old-style arguments]
"""
import warnings
warnings.warn(
    "This script is deprecated. Use 'mind detect run --config ...' instead.",
    DeprecationWarning,
    stacklevel=2,
)
from mind.cli._legacy import main
main()
```

3. **Update README.md** with a migration table mapping old flags to new commands/config keys.
4. **Update any bash scripts** in `bash_scripts/` that reference `python3 src/mind/cli.py`.

---

### Step 7 — Rich Terminal Enhancements

Apply Rich output helpers across all commands using the `_console.py` helpers:

1. **Before execution:** Print a `print_config_table()` showing the resolved configuration (Pydantic model dump, not raw dict — this guarantees all defaults are visible).
2. **During execution:** Where the underlying classes emit progress (e.g., `tqdm` in `Segmenter`/`Translator`), let existing `tqdm` output through. Rich and `tqdm` coexist. In a follow-up, `tqdm` can be replaced with Rich progress in the core classes.
3. **After execution:** Print a `print_success()` summary showing output paths, row counts, and elapsed time (via `timed_operation` context manager).
4. **On error:** Catch exceptions at the command level, format them with `print_error()` and `console.print_exception()`, then exit with the appropriate exit code.
5. **Quiet mode:** When `--quiet` is passed, suppress all non-error output. Only `print_error()` output is shown.

**Exit code strategy:**

| Code | Meaning | When |
|------|---------|------|
| `0` | Success | Command completed normally |
| `1` | Configuration error | Missing config file, invalid YAML, Pydantic validation failure, missing required field |
| `2` | Runtime error | Pipeline crash, LLM failure, file I/O error, OOM |
| `130` | Interrupted | User pressed Ctrl+C (SIGINT) |

Each command should wrap its body in a try/except:
```python
try:
    # ... command logic ...
except pydantic.ValidationError as e:
    print_error(f"Configuration error:\n{e}")
    raise typer.Exit(code=EXIT_CONFIG_ERROR)
except FileNotFoundError as e:
    print_error(str(e))
    raise typer.Exit(code=EXIT_CONFIG_ERROR)
except Exception as e:
    print_error(f"Runtime error: {e}")
    console.print_exception()
    raise typer.Exit(code=EXIT_RUNTIME_ERROR)
```

---

### Step 8 — Docker Compatibility Verification

**Constraint:** The Dockerfile (`app/backend/Dockerfile`) copies `src/mind` into `/src/mind` and sets `PYTHONPATH="/backend:/src:/backend/NLPipe/src"`. This means:
- The new `src/mind/cli/` package will be automatically included.
- The `console_scripts` entry point (`mind`) will be installed if the package is `pip install`-ed, but the Docker image uses `PYTHONPATH` injection, not `pip install`. The Docker image does NOT need the `mind` CLI command (it uses Flask), so no changes to Dockerfile are required.
- Typer and Pydantic must be in `app/backend/requirements.txt` since they become importable modules referenced by `src/mind/cli/`.

> [!WARNING]
> The `docker-compose.yml` overrides `PYTHONPATH` to `/backend:/src` (missing `/backend/NLPipe/src` which is present in the Dockerfile). Verify that `docker compose up` (not just `build`) works correctly — this is an existing issue unrelated to the CLI changes, but should be caught in verification.

**Actions:**
1. Add `typer>=0.12` and `pydantic>=2.0` to `app/backend/requirements.txt`.
2. Run `docker compose build` and verify it succeeds.
3. Run `docker compose up` and verify the web UI still works identically.
4. Verify that importing `mind.cli` inside the Docker container doesn't crash the Flask app (it shouldn't — imports are lazy).

---

### Step 9 — Documentation

Create/update the following:

1. **`docs/cli_usage.md`** — New document with:
   - Installation instructions (`pip install -e .`)
   - Migration guide from old CLI to new CLI (flag mapping table)
   - Quick start examples for each command
   - Full run config file reference with ALL options documented
   - Command reference (auto-generated via `mind --help`)
   - Environment variables (`MIND_CONFIG`)
   - Exit code reference
   - Troubleshooting section (common errors and fixes)
2. **`README.md`** — Add a "CLI Usage" section linking to `docs/cli_usage.md`.

---

## 5. Red-Team Notes & Design Corrections

The following corrections/improvements were identified and applied during adversarial review:

| # | Original Issue | Correction Applied |
|---|---------------|-------------------|
| C1 | Architecture showed `cli.py` coexisting with `cli/` package — impossible in Python | `cli.py` is deleted; body moved to `cli/_legacy.py`; backward compat via `scripts/legacy_detect.py` |
| C2 | `[tool.uv] package = false` prevents `pip install -e .` from creating console scripts | Changed to `package = true` |
| C3 | `MIND.__init__` defaults `config_path` to Docker path `/src/config/config.yaml` | CLI now explicitly passes `config_path=result.system_config_path` to MIND() |
| H1 | `_read_filter_ids()` referenced but never defined | Full implementation added in detect.py Section 3.2 |
| H2 | `previous_check` field missing from config schema, pseudocode location wrong | Added to `detect` level in config schema and Pydantic model |
| H3 | `load_thetas` only set on `source_corpus`, missing from `target_corpus` | Both corpora now receive `load_thetas` from `detect.load_thetas` |
| H4 | `DataPreparer` constructor needs NLPipe params — guide ignored them | Added `preproc_script`, `nlpipe_config`, `stw_path`, `spacy_models` to config schema and CLI flags |
| H5 | `PolylingualTM` needs `mallet_path` — no CLI flag or config key existed | Added `--mallet-path` and `--stops-path` flags + config keys + pre-flight existence check |
| H6 | Pipeline classes need `config_path` as a file path — not available from merged dict | `ConfigResult` now returns both the merged dict AND the resolved system config path |
| M1 | `DEFAULT_SYSTEM_CONFIG` was CWD-relative — breaks from any other directory | Implemented resolution chain: flag → env var → walk-up → fallback |
| M2 | `--system-config` mentioned but never defined as CLI flag | Added as global option in `@app.callback()` |
| M3 | `importlib.metadata.version()` fails without pip install | Added fallback to `"0.1.0-dev"` |
| M4 | `--schema` format for `data prepare` was unspecified | Documented: YAML dict from config, JSON string/path from CLI flag |
| M5 | `target_corpus` dict missing `index_path` in pseudocode | Full `target_corpus` dict now shown explicitly with `index_path` |
| M6 | No signal handling — AsyncCheckpointer could lose data on Ctrl+C | Added SIGINT handler in detect command that flushes checkpoints |
| M7 | Config values are strings but class methods expect `Path` | All path strings are wrapped in `Path()` before passing to class methods |
| E1 | Pydantic validation deferred to "follow-up" | Moved to Phase 1 — `_schemas.py` is now a core module |
| E2 | No `--quiet` / `--verbose` flags | Added as global options in `@app.callback()` |
| E3 | `-v` used for version (POSIX uses `-V`) | Changed to `-V` for version, `-v` for verbose |
| E4 | No exit code strategy | Defined 4 exit codes: 0 (success), 1 (config), 2 (runtime), 130 (interrupted) |
| E5 | No `--dry-run` for `data` subcommands | Added `--dry-run` to all data commands |
| E6 | No timing utility | Added `timed_operation()` context manager to `_console.py` |
| E7 | `init-config` template was incomplete | Template now includes ALL optional fields with defaults commented out |
| S1 | `print_config_table` couldn't display nested dicts | Added `_flatten_dict()` to display as dotted keys |
| S2 | `rich>=13.0` explicit dep could conflict with Typer's bundled Rich | Removed separate Rich dep — rely on Typer's transitive dependency |
| S3 | `requirements.txt` diverges from `pyproject.toml` | Added warning to reconcile before adding new deps |
| S4 | Docker PYTHONPATH mismatch between Dockerfile and docker-compose.yml | Added to verification checklist |

---

## 6. Implementation Order (Chunked for Agents)

> [!TIP]
> Each phase is independently testable. Complete one before moving to the next.

### Phase 1 — Skeleton, Infrastructure & Validation
1. Add `typer>=0.12` and `pydantic>=2.0` to `pyproject.toml` and `requirements.txt`
2. Change `[tool.uv] package = false` to `package = true` in `pyproject.toml`
3. Move `src/mind/cli.py` body to `src/mind/cli/_legacy.py`
4. **Delete** `src/mind/cli.py`
5. Create `src/mind/cli/__init__.py`
6. Create `src/mind/cli/_console.py` (with `_flatten_dict`, `timed_operation`)
7. Create `src/mind/cli/_config_loader.py` (with `ConfigResult`, `_resolve_system_config`)
8. Create `src/mind/cli/_schemas.py` (all Pydantic models)
9. Create `src/mind/cli/commands/__init__.py`
10. Create `src/mind/cli/main.py` (root app with global options, no commands yet)
11. Add `[project.scripts]` to `pyproject.toml`
12. Run `pip install -e .` and verify `mind --help` prints the app help
13. Run `mind --version` and verify version output

### Phase 2 — Detection Commands
1. Create `src/mind/cli/commands/detect.py` with `run` and `init-config`
2. Include `_read_filter_ids()` helper function
3. Include SIGINT signal handler for graceful checkpoint shutdown
4. Wire up `system_config_path` from `ConfigResult` → `MIND(config_path=...)`
5. Test `mind detect init-config` → verify YAML template output is exhaustive
6. Test `mind detect run --config sample.yaml --print-config` → verify config table
7. Test `mind detect run --config sample.yaml` end-to-end with a real dataset

### Phase 3 — Data Preprocessing Commands
1. Create `src/mind/cli/commands/data.py` with `segment`, `translate`, `prepare`
2. Wire up NLPipe params for `prepare` (pass through to `DataPreparer` constructor)
3. Add `--dry-run` to all three commands
4. Test each command individually with small datasets
5. Test full pipeline: `mind data segment` → `mind data translate` → `mind data prepare`

### Phase 4 — Topic Modeling Commands
1. Create `src/mind/cli/commands/tm.py` with `train`
2. Include `--mallet-path` and `--stops-path` flags with pre-flight validation
3. Test `mind tm train --config ...` end-to-end

### Phase 5 — Polish, Backward Compat & Documentation
1. Create `scripts/legacy_detect.py` for backward compat
2. Update any `bash_scripts/` that reference old `cli.py`
3. Create `docs/cli_usage.md` with migration guide
4. Update `README.md`
5. Verify Docker build: `docker compose build`
6. Verify Docker runtime: `docker compose up` and test web UI
7. Check PYTHONPATH handling in docker-compose.yml vs Dockerfile

---

## 7. Verification Plan

### Automated Tests

1. **Unit test: config loader** — Write `tests/test_cli_config_loader.py`:
   - Test `_deep_merge()` with nested dicts
   - Test `_resolve_system_config()` with explicit path, env var, and fallback
   - Test `load_config()` with system-only, system+run, and system+run+overrides
   - Test `load_config()` raises `FileNotFoundError` for missing config
   - Command: `python -m pytest tests/test_cli_config_loader.py -v`

2. **Unit test: Pydantic schemas** — Write `tests/test_cli_schemas.py`:
   - Test valid config dicts pass validation
   - Test missing required fields raise `ValidationError` with clear message
   - Test `DetectConfig.parse_topics` handles comma-separated strings
   - Test default values are populated correctly
   - Command: `python -m pytest tests/test_cli_schemas.py -v`

3. **Unit test: commands parse correctly** — Write `tests/test_cli_commands.py`:
   - Use `typer.testing.CliRunner` to invoke each command with `--help` and verify exit code 0
   - Use `CliRunner` to invoke `mind detect init-config` and verify YAML output is valid
   - Use `CliRunner` to invoke `mind --version` and verify output format
   - Verify `--quiet` suppresses non-error output
   - Command: `python -m pytest tests/test_cli_commands.py -v`

4. **Smoke test: Docker build** — Run `docker compose build backend` and verify exit code 0.

### Manual Verification (for the user)

1. **Install and run:** `pip install -e .` → `mind --help`
   - Verify the help output lists `data`, `detect`, and `tm` subcommand groups
   - Verify `--system-config`, `--verbose`, `--quiet`, `--version` global options are shown
2. **Version:** `mind -V`
   - Verify version string is printed (e.g., `mind 0.1.0`)
3. **Generate config:** `mind detect init-config > /tmp/test_run.yaml`
   - Open the file and verify it contains all required and optional fields
4. **Config validation:** Edit the generated config to have a typo (e.g., `topcs: [7]`) and run `mind detect run --config /tmp/test_run.yaml`
   - Verify a clear Pydantic error message is shown (not a deep traceback)
   - Verify exit code is 1
5. **End-to-end run:** Use an existing dataset and run the full pipeline through the new CLI commands
6. **Dry run:** `mind data segment --config ... --dry-run` — verify config is printed but no processing occurs
7. **Signal handling:** Start a long-running `mind detect run`, press Ctrl+C
   - Verify "flushing checkpoints" message appears and exit code is 130
8. **Quiet mode:** `mind detect run --config ... --quiet 2>/dev/null`
   - Verify no stdout output on success (only stderr on error)
9. **Legacy compat:** `python3 scripts/legacy_detect.py --help`
   - Verify it works with a deprecation warning
10. **Docker:** `docker compose build && docker compose up` — verify web UI works
