"""``mind tm`` — topic modeling commands (train, label)."""

from pathlib import Path
from typing import Optional

import typer

from mind.cli._config_loader import load_run_config, resolve_system_config
from mind.cli._console import console, error, install_rich_logging, success
from mind.cli._schemas import TMLabelConfig, TMTrainConfig

app = typer.Typer(help="Topic modeling commands.")


# ---------------------------------------------------------------------------
# mind tm train
# ---------------------------------------------------------------------------

@app.command()
def train(
    config: Path = typer.Option(
        ..., "--config", "-c", help="Path to run_config.yaml",
        exists=True, dir_okay=False, readable=True,
    ),
    system_config: Optional[str] = typer.Option(
        None, "--system-config", help="Path to system config/config.yaml",
    ),
) -> None:
    """Train a topic model (Polylingual or LDA)."""
    run_cfg = load_run_config(config)
    tm_section = (run_cfg.get("tm") or {}).get("train")
    if tm_section is None:
        error("Run config must contain a 'tm.train' section.")
        raise typer.Exit(1)

    tm = TMTrainConfig(**tm_section)
    sys_cfg_path = resolve_system_config(system_config)
    install_rich_logging()

    is_monolingual = tm.lang2 is None

    if is_monolingual:
        console.print(
            f"[bold]Training monolingual LDA topic model[/bold] "
            f"({tm.lang1}, {tm.num_topics} topics)"
        )
        from mind.topic_modeling.lda_tm import LDATM

        model = LDATM(
            langs=[tm.lang1],
            model_folder=Path(tm.model_folder),
            num_topics=tm.num_topics,
            alpha=tm.alpha,
            mallet_path=tm.mallet_path,
        )
        result = model.train(Path(tm.input))
        if result is None:
            error("LDA training failed.")
            raise typer.Exit(1)
        success(f"LDA model trained → {result}")

    else:
        console.print(
            f"[bold]Training polylingual topic model[/bold] "
            f"({tm.lang1}/{tm.lang2}, {tm.num_topics} topics)"
        )
        from mind.topic_modeling.polylingual_tm import PolylingualTM

        model = PolylingualTM(
            lang1=tm.lang1,
            lang2=tm.lang2,
            model_folder=Path(tm.model_folder),
            num_topics=tm.num_topics,
            alpha=tm.alpha,
            mallet_path=tm.mallet_path,
            add_stops_path=tm.stops_path,
        )
        result = model.train(tm.input)
        if result != 2:
            error(f"Polylingual training returned unexpected status: {result}")
            raise typer.Exit(1)
        success(f"Polylingual model trained → {tm.model_folder}")


# ---------------------------------------------------------------------------
# mind tm label
# ---------------------------------------------------------------------------

@app.command()
def label(
    config: Path = typer.Option(
        ..., "--config", "-c", help="Path to run_config.yaml",
        exists=True, dir_okay=False, readable=True,
    ),
    llm_model: Optional[str] = typer.Option(
        None, "--llm-model", help="LLM model override",
    ),
    llm_server: Optional[str] = typer.Option(
        None, "--llm-server", help="LLM server URL override",
    ),
    system_config: Optional[str] = typer.Option(
        None, "--system-config", help="Path to system config/config.yaml",
    ),
) -> None:
    """Generate topic labels using an LLM."""
    run_cfg = load_run_config(config)
    lbl_section = (run_cfg.get("tm") or {}).get("label")
    if lbl_section is None:
        error("Run config must contain a 'tm.label' section.")
        raise typer.Exit(1)

    lbl = TMLabelConfig(**lbl_section)
    sys_cfg_path = resolve_system_config(system_config)
    install_rich_logging()

    # For monolingual, use lang1 as both
    lang2 = lbl.lang2 if lbl.lang2 else lbl.lang1

    console.print(
        f"[bold]Labelling topics[/bold] in {lbl.model_folder} "
        f"({lbl.lang1}/{lang2})"
    )

    from mind.topic_modeling.topic_label import TopicLabel

    tl = TopicLabel(
        lang1=lbl.lang1,
        lang2=lang2,
        model_folder=Path(lbl.model_folder),
        llm_model=llm_model,
        llm_server=llm_server,
        config_path=sys_cfg_path,
    )
    tl.label_topic()
    success(f"Topic labels generated → {lbl.model_folder}")
