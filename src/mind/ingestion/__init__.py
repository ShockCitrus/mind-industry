"""
Data Ingestion Abstraction Package.

Provides a modular, extensible data ingestion pipeline supporting:
- Compressed archives: .zip, .tar, .tar.gz, .tar.bz2, .tar.xz, .7z
- Unstructured files: .md, .yaml, .yml, .xml, .txt
- Structured files: .csv, .parquet

Public API:
    - ingest_file(): Main entry point for all ingestion flows
    - create_default_registry(): Get a registry with all built-in parsers
"""

from mind.ingestion.pipeline import ingest_file
from mind.ingestion.parsers import create_default_registry

__all__ = ["ingest_file", "create_default_registry"]
