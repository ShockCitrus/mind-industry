# MIND CLI UX Improvement & Professionalization — Agent Implementation Guide

> **Audience:** Agentic AI implementing this spec  
> **Last updated:** 2026-03-01  
> **Status:** Design — awaiting approval

---

## 1. Executive Summary

The MIND project currently offers five separate Python scripts executed with `python3 src/mind/...` and up to 15 manual CLI arguments. The goal is to consolidate them into **one installable command** (`mind`) with semantic subcommands, declarative YAML-based configuration, and polished Rich terminal output — while making **zero changes to the underlying pipeline classes**.

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

```
src/mind/
├── cli/                         ← NEW package
│   ├── __init__.py
│   ├── main.py                  ← Root Typer app, version, global options
│   ├── _config_loader.py        ← YAML loading + merge logic
│   ├── _console.py              ← Rich Console singleton + helpers
│   ├── commands/
│   │   ├── __init__.py
│   │   ├── data.py              ← `mind data {segment,translate,prepare}`
│   │   ├── detect.py            ← `mind detect {run,init-config}`
│   │   └── tm.py                ← `mind tm {train}`
│   └── _schemas.py              ← Pydantic/dataclass models for config sections
├── cli.py                       ← KEPT for backward compat (thin redirect)
├── pipeline/                    ← UNTOUCHED
├── corpus_building/             ← UNTOUCHED
├── topic_modeling/              ← UNTOUCHED
└── ...
```

**Design principles:**
1. **Thin wrapper only** — Each command loads config → builds the kwargs dict → calls the existing class method. No business logic in the CLI layer.
2. **Config-first** — Every subcommand accepts `--config path.yaml`. Individual flags override config values. If neither flag nor config provides a required value, the command exits with a clear error message.
3. **Existing `config.yaml` reuse** — The run config file extends the existing `config/config.yaml` schema with new top-level sections (`run`, `data`, `tm`). The system layer config sections (`logger`, `optimization`, `mind`, `llm`) are left untouched and loaded by the pipeline classes as they always have been.

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
  source:
    corpus_path: data/corpora/polylingual_df.parquet
    thetas_path: data/corpora/thetas_EN.npz
    id_col: doc_id          # default
    passage_col: text       # default
    full_doc_col: full_doc  # default
    lang_filter: EN         # default
    filter_ids_path: null
    previous_check: null
  target:
    corpus_path: data/corpora/polylingual_df.parquet
    thetas_path: data/corpora/thetas_DE.npz
    id_col: doc_id
    passage_col: text
    full_doc_col: full_doc
    lang_filter: DE
    index_path: data/mind_runs/ende/indexes
    filter_ids_path: null
  load_thetas: true

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

# --- Topic modeling settings ---
tm:
  train:
    input: data/processed/prepared.parquet
    lang1: EN
    lang2: DE
    model_folder: data/models/tm_ende
    num_topics: 30
    alpha: 1.0
```

### 3.2 Config Load & Merge Logic

```
Priority (highest to lowest):
  1. Explicit CLI flags (e.g., --topics 7,15)
  2. Run config file (--config run_config.yaml)
  3. System config file (config/config.yaml) — always loaded as base
  4. Hardcoded defaults in code
```

The `_config_loader.py` module:
1. Loads `config/config.yaml` as the base (path configurable via `--system-config`).
2. Deep-merges the user's `--config` file on top.
3. Overlays any explicit CLI flags.
4. Returns a flat dict ready for the target class constructor.

---

## 4. Detailed Implementation Steps

### Step 1 — Add Dependencies

**Files to modify:** `pyproject.toml`, `requirements.txt`

| Package | Why | Size impact |
|---------|-----|-------------|
| `typer>=0.12` | CLI framework with type hints, auto-help, subcommands | ~100 KB |
| `rich>=13.0` | Progress bars, tables, formatted console output (Typer dependency) | ~1.5 MB |

> [!IMPORTANT]
> Do NOT add `typer[all]` — that pulls in `shellingham` and `click-completion` which are unnecessary. Use bare `typer` (Rich is pulled in automatically as a Typer dependency since 0.12).

**Actions:**
1. Add `"typer>=0.12"` and `"rich>=13.0"` to the `dependencies` list in `pyproject.toml`.
2. Add `typer>=0.12` and `rich>=13.0` to the root `requirements.txt`.
3. Add `typer>=0.12` and `rich>=13.0` to `app/backend/requirements.txt` (the backend Dockerfile uses this file).
4. Verify the Docker build still works by running `docker compose build backend`.

---

### Step 2 — Create `src/mind/cli/` Package

**Files to create:**

#### 2.1 `src/mind/cli/__init__.py`
Empty init file.

#### 2.2 `src/mind/cli/commands/__init__.py`
Empty init file.

#### 2.3 `src/mind/cli/_console.py` — Rich Console Singleton

Provide a shared `Console` instance and helper functions for consistent output formatting across all commands.

```python
"""Shared Rich console and output helpers."""
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

def print_config_table(config: dict, title: str = "Configuration") -> None:
    """Render a key-value config dict as a Rich table."""
    table = Table(title=title, show_header=True)
    table.add_column("Parameter", style="cyan")
    table.add_column("Value", style="white")
    for key, value in config.items():
        table.add_row(str(key), str(value))
    console.print(table)
```

#### 2.4 `src/mind/cli/_config_loader.py` — YAML Config Loading & Merging

This module implements the config loading, deep-merge, and CLI-flag overlay logic described in Section 3.2. It must:

1. Accept two optional paths: `system_config` (defaults to `config/config.yaml`) and `run_config` (the user's `--config` file).
2. Load both as dicts using `PyYAML` (already a project dependency).
3. Deep-merge: run config overwrites system config at the leaf level.
4. Provide a function to overlay explicit CLI flags on top.
5. Return the final merged dict.

```python
"""YAML configuration loader with deep-merge support."""
from pathlib import Path
from typing import Any, Dict, Optional
import copy
import yaml

DEFAULT_SYSTEM_CONFIG = Path("config/config.yaml")

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
    system_config_path: Path = DEFAULT_SYSTEM_CONFIG,
    cli_overrides: Optional[Dict[str, Any]] = None,
) -> dict:
    """Load and merge system config, run config, and CLI overrides."""
    # 1. System config (always loaded)
    with open(system_config_path) as f:
        system = yaml.safe_load(f) or {}
    
    # 2. Run config (user-supplied, optional)
    merged = system
    if run_config_path:
        with open(run_config_path) as f:
            run = yaml.safe_load(f) or {}
        merged = _deep_merge(system, run)
    
    # 3. CLI overrides (highest priority)
    if cli_overrides:
        merged = _deep_merge(merged, cli_overrides)
    
    return merged
```

---

### Step 3 — Implement Command Modules

Each command module is a Typer sub-application with one or more commands. Every command follows the same pattern:

```
1. Accept --config (Path, optional) and specific CLI flags.
2. Call _config_loader.load_config() merging config + flags.
3. Extract the relevant section from the merged config.
4. Print a Rich summary table of the resolved configuration.
5. Instantiate the target class (e.g., Segmenter, MIND).
6. Call the target method.
7. Print a Rich success summary.
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

Implementation logic:
```python
# Thin wrapper — these 3 lines are the core:
segmenter = Segmenter(config_path=system_config_path)
result_path = segmenter.segment(
    path_df=Path(input), path_save=Path(output),
    text_col=text_col, min_length=min_length, sep=separator
)
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

Implementation logic:
```python
translator = Translator(config_path=system_config_path)
translated_df = translator.translate(
    path_df=Path(input), src_lang=src_lang, tgt_lang=tgt_lang,
    text_col=text_col, lang_col=lang_col, save_path=output
)
```

**`mind data prepare`**

| CLI Flag | Config Key | Required | Default |
|----------|-----------|----------|---------|
| `--config` | — | No | `None` |
| `--anchor` | `data.prepare.anchor` | **Yes** | — |
| `--comparison` | `data.prepare.comparison` | **Yes** | — |
| `--output` | `data.prepare.output` | **Yes** | — |
| `--schema` | `data.prepare.schema` | **Yes** | — |

Implementation logic:
```python
preparer = DataPreparer(schema=schema, ...)
final_df = preparer.format_dataframes(
    anchor_path=Path(anchor), comparison_path=Path(comparison),
    path_save=Path(output)
)
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
# 1. Read filter IDs from file if paths are given
src_filter_ids = _read_filter_ids(cfg["detect"]["source"].get("filter_ids_path"))
tgt_filter_ids = _read_filter_ids(cfg["detect"]["target"].get("filter_ids_path"))

# 2. Build the EXACTLY same dicts that the old cli.py passes
source_corpus = {
    "corpus_path": cfg["detect"]["source"]["corpus_path"],
    "thetas_path": cfg["detect"]["source"]["thetas_path"],
    "id_col": cfg["detect"]["source"].get("id_col", "doc_id"),
    "passage_col": cfg["detect"]["source"].get("passage_col", "text"),
    "full_doc_col": cfg["detect"]["source"].get("full_doc_col", "full_doc"),
    "language_filter": cfg["detect"]["source"].get("lang_filter", "EN"),
    "filter_ids": src_filter_ids,
    "load_thetas": cfg["detect"].get("load_thetas", False),
}
target_corpus = { ... }  # same pattern

mind_cfg = {
    "llm_model": cfg.get("llm", {}).get("default", {}).get("model"),
    "llm_server": cfg.get("llm_server"),
    "source_corpus": source_corpus,
    "target_corpus": target_corpus,
    "dry_run": cfg["detect"].get("dry_run", False),
    "do_check_entailement": not cfg["detect"].get("no_entailment", False),
}

# 3. Instantiate and run
mind = MIND(**mind_cfg)
mind.run_pipeline(
    topics=cfg["detect"]["topics"],
    path_save=cfg["detect"]["path_save"],
    sample_size=cfg["detect"].get("sample_size"),
    previous_check=cfg["detect"]["source"].get("previous_check"),
)
```

**`mind detect init-config`** — Scaffolds a run config template.

Prints a commented YAML template (the full example from Section 3.1) to stdout so users can redirect it: `mind detect init-config > my_run.yaml`.

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

Implementation logic:
```python
ptm = PolylingualTM(
    lang1=lang1, lang2=lang2,
    model_folder=pathlib.Path(model_folder),
    num_topics=num_topics, alpha=alpha,
)
ptm.train(df_path=pathlib.Path(input))
```

---

### Step 4 — Create Root Application (`src/mind/cli/main.py`)

This is the entry point that assembles all subcommand groups.

```python
"""MIND CLI — Unified command-line interface for the MIND pipeline."""
import typer
from mind.cli.commands import data, detect, tm

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
def main(version: bool = typer.Option(False, "--version", "-v", help="Show version.")):
    """MIND — Multilingual Information Discrepancy Detection CLI."""
    if version:
        from importlib.metadata import version as get_version
        typer.echo(f"mind {get_version('mind')}")
        raise typer.Exit()

def entrypoint():
    """Console script entry point."""
    app()

if __name__ == "__main__":
    entrypoint()
```

---

### Step 5 — Register Console Script in `pyproject.toml`

Add the following section to `pyproject.toml`:

```toml
[project.scripts]
mind = "mind.cli.main:entrypoint"
```

After this, `pip install -e .` will make the `mind` command globally available on the `$PATH`.

---

### Step 6 — Backward Compatibility Redirect in Old `cli.py`

Preserve the old `src/mind/cli.py` so that existing scripts (`python3 src/mind/cli.py ...`) continue to work. Add a deprecation notice:

```python
"""Legacy CLI entry point — redirects to mind.cli.main."""
import sys
import warnings

def main():
    warnings.warn(
        "Running 'python3 src/mind/cli.py' is deprecated. "
        "Use 'mind detect run --config ...' instead.",
        DeprecationWarning, stacklevel=2,
    )
    # Fall through to the old argparse logic for backward compat
    from mind.cli._legacy import legacy_main
    legacy_main()
```

Move the current `cli.py` body (the `build_parser` + `main` function) into `src/mind/cli/_legacy.py` so it still works but is clearly marked as legacy.

---

### Step 7 — Rich Terminal Enhancements

Apply Rich output helpers across all commands using the `_console.py` helpers:

1. **Before execution:** Print a `print_config_table()` showing the resolved configuration.
2. **During execution:** Where the underlying classes emit progress (e.g., `tqdm` in `Segmenter`/`Translator`), wrap with `rich.progress.Progress` bars. Initially, just let existing `tqdm` output through — Rich and `tqdm` coexist. In a follow-up, `tqdm` can be replaced with Rich progress in the core classes.
3. **After execution:** Print a `print_success()` summary showing output paths, row counts, and elapsed time.
4. **On error:** Catch exceptions at the command level, format them with `print_error()` and `console.print_exception()`, then exit with code 1.

---

### Step 8 — Docker Compatibility Verification

**Constraint:** The Dockerfile (`app/backend/Dockerfile`) copies `src/mind` into `/src/mind` and sets `PYTHONPATH="/backend:/src:/backend/NLPipe/src"`. This means:
- The new `src/mind/cli/` package will be automatically included.
- The `console_scripts` entry point (`mind`) will be installed if the package is `pip install`-ed, but the Docker image uses `PYTHONPATH` injection, not `pip install`. The Docker image does NOT need the `mind` CLI command (it uses Flask), so no changes to Dockerfile are required.
- Typer and Rich must be in `app/backend/requirements.txt` since they become importable modules referenced by `src/mind/cli/`.

**Actions:**
1. Add `typer>=0.12` and `rich>=13.0` to `app/backend/requirements.txt`.
2. Run `docker compose build` and verify it succeeds.
3. Run `docker compose up` and verify the web UI still works identically.

---

### Step 9 — Documentation

Create/update the following:

1. **`docs/cli_usage.md`** — New document with:
   - Installation instructions (`pip install -e .`)
   - Quick start examples for each command
   - Full config file reference
   - Command reference (auto-generated via `mind --help`)
2. **`README.md`** — Add a "CLI Usage" section linking to `docs/cli_usage.md`.

---

## 5. Red-Team Notes & Design Corrections

The following are corrections/improvements identified during analysis of the original guide:

| Original Idea | Issue | Correction |
|---------------|-------|------------|
| "Create `src/mind/cli/` with `main.py`" | Did not address backward compatibility of existing `cli.py` | Added Step 6: legacy redirect so existing shell scripts don't break |
| "Update config parser to read run params from YAML" | Could pollute `config.yaml` | Separated run config from system config; `--config` loads a user file that deep-merges on top |
| "Replace logs with Rich progress" | Dangerous to modify core classes | Rich output stays in the CLI layer only; existing `tqdm`/logging in core classes is untouched |
| "Add `typer[all]`" | Pulls unnecessary extras (shellingham, etc.) | Use bare `typer` — Rich is already a dependency |
| No mention of error handling | CLI would crash with tracebacks | Added structured error handling with `print_error()` + `console.print_exception()` |
| No mention of `--help` auto-generation | Users need self-documenting commands | Typer auto-generates `--help` from type hints and docstrings |
| No mention of config validation | Silently incorrect configs | Can optionally add Pydantic validation via `_schemas.py` in a follow-up phase |

---

## 6. Implementation Order (Chunked for Agents)

> [!TIP]
> Each phase is independently testable. Complete one before moving to the next.

### Phase 1 — Skeleton & Infrastructure
1. Add dependencies to `pyproject.toml` and `requirements.txt`
2. Create `src/mind/cli/__init__.py`
3. Create `src/mind/cli/_console.py`
4. Create `src/mind/cli/_config_loader.py`
5. Create `src/mind/cli/commands/__init__.py`
6. Create `src/mind/cli/main.py` (root app with no commands yet)
7. Add `[project.scripts]` to `pyproject.toml`
8. Run `pip install -e .` and verify `mind --help` prints the app help

### Phase 2 — Detection Commands
1. Create `src/mind/cli/commands/detect.py` with `run` and `init-config`
2. Move old `cli.py` body to `src/mind/cli/_legacy.py`
3. Add deprecation redirect in `src/mind/cli.py` (note: keeping the old module path)
4. Test `mind detect init-config` → verify YAML template output
5. Test `mind detect run --config sample.yaml` end-to-end with a real dataset

### Phase 3 — Data Preprocessing Commands
1. Create `src/mind/cli/commands/data.py` with `segment`, `translate`, `prepare`
2. Test each command individually with small datasets
3. Test full pipeline: `mind data segment` → `mind data translate` → `mind data prepare`

### Phase 4 — Topic Modeling Commands
1. Create `src/mind/cli/commands/tm.py` with `train`
2. Test `mind tm train --config ...` end-to-end

### Phase 5 — Polish & Documentation
1. Add Rich output enhancements (config tables, success messages, error formatting)
2. Create `docs/cli_usage.md`
3. Update `README.md`
4. Verify Docker build still works

---

## 7. Verification Plan

### Automated Tests

1. **Unit test: config loader** — Write `tests/test_cli_config_loader.py`:
   - Test `_deep_merge()` with nested dicts
   - Test `load_config()` with system-only, system+run, and system+run+overrides
   - Command: `python -m pytest tests/test_cli_config_loader.py -v`

2. **Unit test: commands parse correctly** — Write `tests/test_cli_commands.py`:
   - Use `typer.testing.CliRunner` to invoke each command with `--help` and verify exit code 0
   - Use `CliRunner` to invoke `mind detect init-config` and verify YAML output is valid
   - Command: `python -m pytest tests/test_cli_commands.py -v`

3. **Smoke test: Docker build** — Run `docker compose build backend` and verify exit code 0.

### Manual Verification (for the user)

1. **Install and run:** `pip install -e .` → `mind --help`
   - Verify the help output lists `data`, `detect`, and `tm` subcommand groups
2. **Generate config:** `mind detect init-config > /tmp/test_run.yaml`
   - Open the file and verify it contains a valid, commented template
3. **End-to-end run:** Use an existing dataset and run the full pipeline through the new CLI commands
4. **Legacy compatibility:** Run `python3 src/mind/cli.py --help` and verify it still works with a deprecation warning
