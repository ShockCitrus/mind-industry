"""``mind data`` — preprocessing commands (segment, translate, prepare)."""

from pathlib import Path
from typing import Optional

import typer

from mind.cli._config_loader import (
    build_nlpipe_temp_config,
    load_run_config,
    resolve_system_config,
)
from mind.cli._console import console, error, install_rich_logging, success
from mind.cli._schemas import PrepareConfig, SegmentConfig, TranslateConfig

app = typer.Typer(help="Data preprocessing commands.")


# ---------------------------------------------------------------------------
# mind data segment
# ---------------------------------------------------------------------------

@app.command()
def segment(
    config: Path = typer.Option(
        ..., "--config", "-c", help="Path to run_config.yaml",
        exists=True, dir_okay=False, readable=True,
    ),
    system_config: Optional[str] = typer.Option(
        None, "--system-config", help="Path to system config/config.yaml",
    ),
) -> None:
    """Segment raw documents into passages."""
    run_cfg = load_run_config(config)
    seg_section = (run_cfg.get("data") or {}).get("segment")
    if seg_section is None:
        error("Run config must contain a 'data.segment' section.")
        raise typer.Exit(1)

    seg = SegmentConfig(**seg_section)
    sys_cfg_path = resolve_system_config(system_config)
    install_rich_logging()

    with console.status("[bold green]Segmenting documents…"):
        from mind.corpus_building.segmenter import Segmenter

        segmenter = Segmenter(config_path=sys_cfg_path)
        result_path = segmenter.segment(
            path_df=Path(seg.input),
            path_save=Path(seg.output),
            text_col=seg.text_col,
            id_col=seg.id_col,
            min_length=seg.min_length,
            sep=seg.separator,
        )

    import pandas as pd
    df = pd.read_parquet(result_path)
    success(f"Segmented into {len(df)} passages → {result_path}")


# ---------------------------------------------------------------------------
# mind data translate
# ---------------------------------------------------------------------------

SUPPORTED_PAIRS = {
    ("en", "es"), ("es", "en"),
    ("en", "de"), ("de", "en"),
    ("en", "it"), ("it", "en"),
}


@app.command()
def translate(
    config: Path = typer.Option(
        ..., "--config", "-c", help="Path to run_config.yaml",
        exists=True, dir_okay=False, readable=True,
    ),
    bilingual: Optional[bool] = typer.Option(
        None, "--bilingual/--no-bilingual",
        help=(
            "Bilingual mode: split a mixed-language dataset by language, "
            "translate each side in both directions (src→tgt and tgt→src), "
            "and save two ready-to-prepare output files. "
            "This mirrors the web application's preprocessing flow. "
            "Outputs: <output>_<src>2<tgt> and <output>_<tgt>2<src>."
        ),
    ),
    system_config: Optional[str] = typer.Option(
        None, "--system-config", help="Path to system config/config.yaml",
    ),
) -> None:
    """Translate passages between supported language pairs.

    By default translates src_lang rows and appends them to the dataset.

    Use --bilingual for mixed-language datasets (e.g. EN+ES together): it
    splits them by language, translates each side in both directions, and
    produces two output files ready for [bold]mind data prepare[/bold].
    This is the same flow used by the web application.
    """
    run_cfg = load_run_config(config)
    tr_section = (run_cfg.get("data") or {}).get("translate")
    if tr_section is None:
        error("Run config must contain a 'data.translate' section.")
        raise typer.Exit(1)

    tr = TranslateConfig(**tr_section)

    # CLI flag overrides config value
    if bilingual is not None:
        tr.bilingual = bilingual

    sys_cfg_path = resolve_system_config(system_config)
    install_rich_logging()

    src = tr.src_lang.lower()
    tgt = tr.tgt_lang.lower()

    for pair in [(src, tgt), (tgt, src)]:
        if pair not in SUPPORTED_PAIRS:
            error(
                f"Unsupported language pair: {pair[0]}→{pair[1]}. "
                f"Supported pairs: {sorted(SUPPORTED_PAIRS)}"
            )
            raise typer.Exit(1)

    import pandas as pd
    from mind.corpus_building.translator import Translator

    translator = Translator(config_path=sys_cfg_path)

    if not tr.bilingual:
        # ----------------------------------------------------------------
        # Default mode: translate src→tgt, append to dataset
        # ----------------------------------------------------------------
        console.print(f"[bold]Translating[/bold] {src} → {tgt}")
        result_df = translator.translate(
            path_df=Path(tr.input),
            src_lang=src,
            tgt_lang=tgt,
            text_col=tr.text_col,
            lang_col=tr.lang_col,
            save_path=tr.output,
        )
        success(f"Translated {len(result_df)} rows → {tr.output}")

    else:
        # ----------------------------------------------------------------
        # Bilingual mode: mirrors the web app's preprocessing flow.
        #
        # 1. Load dataset and split by language
        # 2. Translate src→tgt (EN+its translations appended)
        # 3. Translate tgt→src (ES+its translations appended)
        # 4. Save two output files ready for DataPreparer:
        #      <output>_<src>2<tgt>   ← anchor
        #      <output>_<tgt>2<src>   ← comparison
        # ----------------------------------------------------------------
        console.print(
            f"[bold]Bilingual translation[/bold] "
            f"({src.upper()}+{tgt.upper()} dataset → two output files)"
        )

        df = pd.read_parquet(Path(tr.input))
        lang_col = tr.lang_col

        # Normalise lang column to lowercase for filtering
        df[lang_col] = df[lang_col].astype(str).str.lower()

        df_src = df[df[lang_col] == src].copy()
        df_tgt = df[df[lang_col] == tgt].copy()

        if df_src.empty:
            error(f"No rows found with lang='{src}' in {tr.input}")
            raise typer.Exit(1)
        if df_tgt.empty:
            error(f"No rows found with lang='{tgt}' in {tr.input}")
            raise typer.Exit(1)

        console.print(
            f"  Split: {len(df_src)} {src.upper()} rows, "
            f"{len(df_tgt)} {tgt.upper()} rows"
        )

        import tempfile
        output_src2tgt = f"{tr.output}_{src}2{tgt}"
        output_tgt2src = f"{tr.output}_{tgt}2{src}"

        # Write temporary per-language files (Translator expects a file path)
        with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as tmp_src, \
             tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as tmp_tgt:
            tmp_src_path = Path(tmp_src.name)
            tmp_tgt_path = Path(tmp_tgt.name)

        df_src.to_parquet(tmp_src_path)
        df_tgt.to_parquet(tmp_tgt_path)

        try:
            # src → tgt  (e.g. EN → ES)
            console.print(f"  [1/2] Translating {src.upper()} → {tgt.upper()}…")
            translator.translate(
                path_df=tmp_src_path,
                src_lang=src,
                tgt_lang=tgt,
                text_col=tr.text_col,
                lang_col=lang_col,
                save_path=output_src2tgt,
            )

            # tgt → src  (e.g. ES → EN)
            console.print(f"  [2/2] Translating {tgt.upper()} → {src.upper()}…")
            translator.translate(
                path_df=tmp_tgt_path,
                src_lang=tgt,
                tgt_lang=src,
                text_col=tr.text_col,
                lang_col=lang_col,
                save_path=output_tgt2src,
            )
        finally:
            tmp_src_path.unlink(missing_ok=True)
            tmp_tgt_path.unlink(missing_ok=True)

        df_a = pd.read_parquet(output_src2tgt)
        df_b = pd.read_parquet(output_tgt2src)
        success(
            f"Anchor   ({src}2{tgt}): {len(df_a)} rows → {output_src2tgt}\n"
            f"  Comparison ({tgt}2{src}): {len(df_b)} rows → {output_tgt2src}\n\n"
            f"  Pass these as [bold]anchor[/bold] and [bold]comparison[/bold] "
            f"in your [bold]data.prepare[/bold] config."
        )


# ---------------------------------------------------------------------------
# mind data prepare
# ---------------------------------------------------------------------------

@app.command()
def prepare(
    config: Path = typer.Option(
        ..., "--config", "-c", help="Path to run_config.yaml",
        exists=True, dir_okay=False, readable=True,
    ),
    system_config: Optional[str] = typer.Option(
        None, "--system-config", help="Path to system config/config.yaml",
    ),
) -> None:
    """Run NLPipe preprocessing and DataPreparer formatting."""
    run_cfg = load_run_config(config)
    prep_section = (run_cfg.get("data") or {}).get("prepare")
    if prep_section is None:
        error("Run config must contain a 'data.prepare' section.")
        raise typer.Exit(1)

    prep = PrepareConfig(**prep_section)
    sys_cfg_path = resolve_system_config(system_config)
    install_rich_logging()

    # Build schema dict for DataPreparer
    schema = prep.col_schema.model_dump()

    # Handle NLPipe config.json temp copy if configured.
    # Mirrors the web backend (preprocessing.py:283): patch the "mind" key with
    # the actual column names from the schema, and set title="" so NLPipe skips
    # title concatenation (avoids KeyError when the dataset has no title column).
    nlpipe_config_path = None
    tmp_nlpipe_config = None
    if prep.nlpipe_config:
        tmp_nlpipe_config = build_nlpipe_temp_config(
            original_config_path=Path(prep.nlpipe_config),
            dataset_key="mind",
            overrides={
                "id": schema["chunk_id"],
                "raw_text": schema["text"],
                "title": "",  # empty → NLPipe skips title concat (matches web behaviour)
            },
        )
        nlpipe_config_path = str(tmp_nlpipe_config)

    try:
        from mind.corpus_building.data_preparer import DataPreparer

        preparer = DataPreparer(
            preproc_script=prep.nlpipe_script,
            config_path=nlpipe_config_path or (prep.nlpipe_config if prep.nlpipe_config else None),
            stw_path=prep.stw_path,
            spacy_models=prep.spacy_models,
            schema=schema,
            config_logger_path=sys_cfg_path,
        )

        if prep.monolingual or prep.comparison is None:
            console.print("[bold]Running monolingual preparation…[/bold]")
            result_df = preparer.format_monolingual(
                input_path=Path(prep.anchor),
                path_save=Path(prep.output),
            )
        else:
            console.print(f"[bold]Running bilingual preparation…[/bold]")
            result_df = preparer.format_dataframes(
                anchor_path=Path(prep.anchor),
                comparison_path=Path(prep.comparison),
                path_save=Path(prep.output),
            )

        success(f"Prepared {len(result_df)} rows → {prep.output}")

    finally:
        if tmp_nlpipe_config:
            try:
                tmp_nlpipe_config.unlink(missing_ok=True)
            except Exception:
                pass
