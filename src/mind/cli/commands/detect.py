"""``mind detect`` — discrepancy detection commands."""

import os
import re
import signal
import sys
import textwrap
from pathlib import Path
from typing import Optional

import pandas as pd
import typer
from rich.progress import Progress, SpinnerColumn, TextColumn

from mind.cli._config_loader import (
    build_merged_config,
    load_run_config,
    resolve_system_config,
)
from mind.cli._console import console, error, install_rich_logging, print_config_panel, success
from mind.cli._schemas import DetectConfig

app = typer.Typer(help="Discrepancy detection commands.")


# ---------------------------------------------------------------------------
# Inlined process_mind_results (from app/backend/utils.py — avoids Flask dep)
# ---------------------------------------------------------------------------

def _process_mind_results(topics: list[int], directory: str) -> Optional[Path]:
    """Consolidate per-topic parquet checkpoints into ``mind_results.parquet``.

    This is an inline copy of ``app/backend/utils.py:process_mind_results`` to
    avoid pulling in Flask as a dependency.
    """
    topics_regex = "|".join(str(t) for t in topics)
    pattern = re.compile(rf"results_topic_(?:({topics_regex})|final)_(\d+)\.parquet$")

    mapping = {
        "source_chunk": "anchor_passage",
        "source_chunk_id": "anchor_passage_id",
        "a_s": "anchor_answer",
        "target_chunk": "comparison_passage",
        "target_chunk_id": "comparison_passage_id",
        "a_t": "comparison_answer",
    }
    order = [
        "topic", "question_id", "question",
        "anchor_passage_id", "anchor_passage", "anchor_answer",
        "comparison_passage_id", "comparison_passage", "comparison_answer",
        "label", "final_label", "reason", "Notes", "secondary_label",
    ]

    dataframes = []
    matched_files: list[str] = []

    for filename in os.listdir(directory):
        filepath = os.path.join(directory, filename)
        if not os.path.isfile(filepath):
            continue
        if pattern.match(filename):
            matched_files.append(filename)
            df = pd.read_parquet(filepath)
            df["final_label"] = df["label"]
            df = df.rename(columns=mapping)
            top = [col for col in order if col in df.columns]
            bottom = [col for col in df.columns if col not in order]
            df = df[top + bottom]
            dataframes.append(df)

    output_path = os.path.join(directory, "mind_results.parquet")
    if dataframes:
        result = pd.concat(dataframes, ignore_index=True)
        result.to_parquet(output_path)
    else:
        return None

    # Clean up intermediate files
    for filename in os.listdir(directory):
        filepath = os.path.join(directory, filename)
        if os.path.isfile(filepath) and filename != "mind_results.parquet":
            os.remove(filepath)

    return Path(output_path)


# ---------------------------------------------------------------------------
# mind detect run
# ---------------------------------------------------------------------------

@app.command()
def run(
    config: Path = typer.Option(
        ..., "--config", "-c", help="Path to run_config.yaml",
        exists=True, dir_okay=False, readable=True,
    ),
    topics: Optional[str] = typer.Option(
        None, "--topics", "-t",
        help="Override topics (1-indexed, comma-separated). e.g. '7,15'",
    ),
    sample_size: Optional[int] = typer.Option(
        None, "--sample-size", "-n", help="Sample size per topic (default: all)",
    ),
    llm_model: Optional[str] = typer.Option(
        None, "--llm-model", help="LLM model override (e.g. llama3.3:70b)",
    ),
    llm_server: Optional[str] = typer.Option(
        None, "--llm-server", help="LLM server URL override",
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Run without writing outputs"),
    check_entailment: bool = typer.Option(
        False, "--check-entailment", help="Enable entailment checking",
    ),
    system_config: Optional[str] = typer.Option(
        None, "--system-config", help="Path to system config/config.yaml",
    ),
    log_file: Optional[Path] = typer.Option(
        None, "--log-file", help="Write plain-text log to this file",
    ),
) -> None:
    """Run the full MIND discrepancy detection pipeline."""
    # -- Load & validate config ------------------------------------------------
    run_cfg = load_run_config(config)
    detect_section = run_cfg.get("detect")
    if detect_section is None:
        error("Run config must contain a 'detect' section.")
        raise typer.Exit(1)

    det = DetectConfig(**detect_section)

    # CLI flag overrides
    if topics is not None:
        det.topics = [int(t.strip()) for t in topics.split(",")]
    if sample_size is not None:
        det.sample_size = sample_size
    if check_entailment:
        det.do_check_entailment = True

    # -- Resolve system config and build temp copy -----------------------------
    sys_config_path = resolve_system_config(system_config)
    merged_sys, tmp_config_path = build_merged_config(run_cfg, sys_config_path)

    install_rich_logging(merged_sys.get("logger", {}).get("log_level", "INFO"))

    # Optional log file
    if log_file is not None:
        import logging
        fh = logging.FileHandler(log_file)
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
        logging.getLogger().addHandler(fh)

    # -- Resolve LLM ----------------------------------------------------------
    effective_llm_model = llm_model  # None → Prompter.from_config()
    effective_llm_server = llm_server

    # -- Build corpus dicts (mirrors app/backend/detection.py:553) -------------
    def _load_filter_ids(path: Optional[str]) -> Optional[list]:
        if path is None:
            return None
        with open(path) as f:
            return [line.strip() for line in f if line.strip()]

    source_corpus = {
        "corpus_path": det.source.corpus_path,
        "thetas_path": det.source.thetas_path,
        "id_col": det.source.id_col,
        "passage_col": det.source.passage_col,
        "full_doc_col": det.source.full_doc_col,
        "language_filter": det.source.lang_filter,
        "filter_ids": _load_filter_ids(det.source.filter_ids_path),
        "load_thetas": True,
        "method": det.method,
    }

    target_corpus = {
        "corpus_path": det.target.corpus_path,
        "thetas_path": det.target.thetas_path,
        "id_col": det.target.id_col,
        "passage_col": det.target.passage_col,
        "full_doc_col": det.target.full_doc_col,
        "language_filter": det.target.lang_filter,
        "filter_ids": _load_filter_ids(det.target.filter_ids_path),
        "load_thetas": True,
        "method": det.method,
        "index_path": det.target.index_path,
    }

    # -- Topics: 1-indexed input → 0-indexed pipeline -------------------------
    topics_0idx = [t - 1 for t in det.topics]

    # -- Display startup panel ------------------------------------------------
    llm_display = effective_llm_model or merged_sys.get("llm", {}).get("default", {}).get("model", "from config")
    if effective_llm_server:
        llm_display += f" @ {effective_llm_server}"

    print_config_panel("MIND Detection Run", [
        ("Topics", f"{det.topics} (0-indexed: {topics_0idx})"),
        ("Sample size", str(det.sample_size or "all")),
        ("Method", det.method),
        ("LLM", llm_display),
        ("Source corpus", f"{det.source.lang_filter} — {det.source.corpus_path}"),
        ("Target corpus", f"{det.target.lang_filter} — {det.target.corpus_path}"),
        ("Output", det.path_save),
        ("Monolingual", "Yes" if det.monolingual else "No"),
        ("Entailment check", "Yes" if det.do_check_entailment else "No"),
        ("Dry run", "Yes" if dry_run else "No"),
    ])

    # -- Build MIND kwargs -----------------------------------------------------
    mind_kwargs = {
        "llm_model": effective_llm_model,
        "llm_server": effective_llm_server,
        "source_corpus": source_corpus,
        "target_corpus": target_corpus,
        "retrieval_method": det.method,
        "config_path": tmp_config_path,
        "monolingual": det.monolingual,
        "dry_run": dry_run,
        "do_check_entailement": det.do_check_entailment,  # note: upstream typo
        "selected_categories": det.selected_categories,
    }

    run_kwargs = {
        "topics": topics_0idx,
        "sample_size": det.sample_size,
        "path_save": det.path_save,
    }

    # -- Graceful shutdown handler ---------------------------------------------
    mind_instance = None

    def _shutdown_handler(signum, frame):
        console.print("\n[yellow]Interrupt received — shutting down gracefully…[/yellow]")
        if mind_instance is not None:
            checkpointer = getattr(mind_instance, "_checkpointer", None)
            if checkpointer is not None:
                console.print("[yellow]Flushing pending checkpoints…[/yellow]")
                checkpointer.shutdown()
        raise SystemExit(1)

    original_sigint = signal.getsignal(signal.SIGINT)
    signal.signal(signal.SIGINT, _shutdown_handler)

    # -- Run pipeline ----------------------------------------------------------
    try:
        with console.status("[bold green]Initialising MIND pipeline…"):
            from mind.pipeline.pipeline import MIND
            mind_instance = MIND(**mind_kwargs)

        console.print("[bold green]Pipeline initialised.[/bold green] Starting detection…\n")
        mind_instance.run_pipeline(**run_kwargs)

        # -- Post-run: consolidate results -------------------------------------
        console.print("\n[bold]Consolidating results…[/bold]")
        output = _process_mind_results(topics_0idx, det.path_save)
        if output:
            result_df = pd.read_parquet(output)
            success(f"Results saved to {output} ({len(result_df)} records)")
        else:
            console.print("[yellow]No result files found to consolidate.[/yellow]")

    except (KeyboardInterrupt, SystemExit):
        pass  # already handled
    except Exception as exc:
        error(f"Pipeline failed: {exc}")
        raise typer.Exit(1)
    finally:
        # Restore original signal handler
        signal.signal(signal.SIGINT, original_sigint)
        # Clean up temp config
        try:
            tmp_config_path.unlink(missing_ok=True)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# mind detect init-config
# ---------------------------------------------------------------------------

@app.command("init-config")
def init_config(
    output: Path = typer.Option(
        Path("run_config.yaml"), "--output", "-o",
        help="Where to write the scaffold config.",
    ),
) -> None:
    """Scaffold a template ``run_config.yaml``."""
    template = textwrap.dedent("""\
        # MIND CLI run configuration
        # See: docs/deferred_artifacts/cli_detection_feature.md

        # Optional: override system config LLM settings
        # llm:
        #   default:
        #     backend: ollama
        #     model: llama3.3:70b

        detect:
          monolingual: false
          topics: [1, 2, 3]                  # 1-indexed topic IDs
          sample_size: null                   # null = all passages
          path_save: data/results
          method: TB-ENN
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

        # data:
        #   segment:
        #     input: data/raw/documents.parquet
        #     output: data/processed/segmented
        #     text_col: text
        #     id_col: id_preproc
        #     min_length: 100
        #     separator: "\\n"
        #   translate:
        #     input: data/processed/segmented   # mixed-language dataset (EN+DE)
        #     output: data/processed/translated
        #     src_lang: en
        #     tgt_lang: de
        #     text_col: text
        #     lang_col: lang
        #     bilingual: true   # recommended for mixed datasets: splits by lang,
        #                       # translates both directions, outputs two files:
        #                       #   translated_en2de  ← use as anchor in prepare
        #                       #   translated_de2en  ← use as comparison in prepare
        #   prepare:
        #     anchor: data/processed/translated_en2de
        #     comparison: data/processed/translated_de2en
        #     output: data/processed/prepared
        #     schema:
        #       chunk_id: id_preproc
        #       text: text
        #       lang: lang
        #       full_doc: full_doc
        #       doc_id: doc_id
        #     nlpipe_script: externals/NLPipe/src/nlpipe/cli.py
        #     nlpipe_config: externals/NLPipe/config.json
        #     stw_path: externals/NLPipe/src/nlpipe/stw_lists
        #     spacy_models:
        #       en: en_core_web_sm
        #       de: de_core_news_sm

        # tm:
        #   train:
        #     input: data/processed/prepared
        #     lang1: EN
        #     lang2: DE
        #     model_folder: data/models/tm_ende
        #     num_topics: 30
        #     alpha: 1.0
        #     mallet_path: externals/Mallet-202108/bin/mallet
        #     stops_path: src/mind/topic_modeling/stops
        #   label:
        #     model_folder: data/models/tm_ende
        #     lang1: EN
        #     lang2: DE
    """)

    if output.exists():
        overwrite = typer.confirm(f"{output} already exists. Overwrite?", default=False)
        if not overwrite:
            raise typer.Abort()

    output.write_text(template)
    success(f"Template written to {output}")


# ---------------------------------------------------------------------------
# mind detect peek
# ---------------------------------------------------------------------------

from mind.cli.commands.peek import peek  # noqa: E402, F401

app.command()(peek)
