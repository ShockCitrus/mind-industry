"""
Ingestion Pipeline Orchestrator.

Main entry point for all data ingestion flows. Routes files through
the appropriate extraction, traversal, and parsing steps.
"""

import logging
import shutil
from pathlib import Path
from typing import Optional

import pandas as pd

from mind.ingestion.archive_handler import extract_archive, is_archive
from mind.ingestion.parsers import ParserRegistry, create_default_registry
from mind.ingestion.schema_mapper import records_to_dataframe
from mind.ingestion.traversal import walk_files

logger = logging.getLogger(__name__)


def ingest_file(
    file_path: Path,
    registry: Optional[ParserRegistry] = None,
    **kwargs,
) -> pd.DataFrame:
    """
    Ingest a file and produce a DataFrame matching the Dataset schema.

    Supports:
    - Archives (.zip, .tar, .tar.gz, .tar.bz2, .tar.xz, .7z):
      Extracts, walks directory tree, parses each file, merges results.
    - Single files (.md, .yaml, .yml, .xml, .txt, .csv, .parquet):
      Parses directly with the appropriate parser.

    Args:
        file_path: Path to the file to ingest.
        registry: Optional custom ParserRegistry. Uses default if None.
        **kwargs: Additional arguments passed to parsers (e.g., sep, text_column).

    Returns:
        pd.DataFrame with columns: id_preproc, text, lang, title.

    Raises:
        ValueError: If the file format is unsupported, no content is found,
                     or language detection fails.
    """
    if registry is None:
        registry = create_default_registry()

    ext = file_path.suffix.lstrip(".").lower()

    # Handle compound extensions (.tar.gz, .tar.bz2, .tar.xz)
    name_lower = file_path.name.lower()
    if name_lower.endswith((".tar.gz", ".tar.bz2", ".tar.xz")):
        is_arch = True
    else:
        is_arch = is_archive(ext)

    if is_arch:
        return _ingest_archive(file_path, registry, **kwargs)
    else:
        return _ingest_single(file_path, ext, registry, **kwargs)


def _ingest_archive(
    file_path: Path,
    registry: ParserRegistry,
    **kwargs,
) -> pd.DataFrame:
    """Extract archive, walk files, parse each, and merge into a DataFrame."""
    temp_dir = None
    try:
        temp_dir = extract_archive(file_path)
        logger.info(f"Extracted archive to {temp_dir}")

        all_records = []
        skipped_files = []

        for file_info in walk_files(temp_dir):
            parser = registry.get_parser(file_info.extension)
            if parser:
                try:
                    records = parser.extract(file_info.path, **kwargs)
                    all_records.extend(records)
                    logger.debug(
                        f"Parsed {file_info.relative_path}: "
                        f"{len(records)} record(s)"
                    )
                except Exception as e:
                    logger.warning(
                        f"Failed to parse {file_info.relative_path}: {e}"
                    )
            else:
                skipped_files.append(file_info.relative_path)

        if skipped_files:
            logger.info(
                f"Skipped {len(skipped_files)} file(s) with unsupported "
                f"extensions: {', '.join(set(f.split('.')[-1] for f in skipped_files))}"
            )

        if not all_records:
            raise ValueError(
                f"No parseable content found in archive '{file_path.name}'. "
                f"Supported file formats inside archives: "
                f"{', '.join('.' + e for e in registry.supported_extensions())}"
            )

        return records_to_dataframe(all_records, file_path.stem)

    finally:
        if temp_dir and temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)
            logger.info(f"Cleaned up temp dir: {temp_dir}")


def _ingest_single(
    file_path: Path,
    ext: str,
    registry: ParserRegistry,
    **kwargs,
) -> pd.DataFrame:
    """Parse a single file directly with the appropriate parser."""
    parser = registry.get_parser(ext)
    if not parser:
        raise ValueError(
            f"Unsupported file format: '.{ext}'. "
            f"Supported formats: "
            f"{', '.join('.' + e for e in registry.supported_extensions())}, "
            f".zip, .tar, .tar.gz, .tar.bz2, .tar.xz, .7z"
        )

    records = parser.extract(file_path, **kwargs)
    if not records:
        raise ValueError(
            f"No content extracted from file: '{file_path.name}'. "
            f"All content may be shorter than the minimum threshold "
            f"(100 characters per section)."
        )

    return records_to_dataframe(records, file_path.stem)
