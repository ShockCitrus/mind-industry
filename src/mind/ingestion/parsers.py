"""
Modular File Parsers Module.

Provides an extensible registry/strategy pattern for format-specific file
parsers. Each parser extracts structured text records from a specific file
format.

Adding a new format:
    1. Subclass BaseParser
    2. Implement extract() and supported_extensions()
    3. Call registry.register(YourParser())
"""

import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

logger = logging.getLogger(__name__)

# Minimum content length to keep — consistent with segmenter.py min_length=100
MIN_SECTION_LENGTH = 100


# =============================================================================
# Base Parser
# =============================================================================

class BaseParser(ABC):
    """Base interface for all file parsers."""

    @abstractmethod
    def extract(self, filepath: Path, **kwargs) -> List[Dict[str, Any]]:
        """
        Parse a file and return a list of extracted records.

        Each record is a dict with keys:
        - "text": str (required) — the extracted textual content
        - "title": str (optional) — document or section title
        - "lang": str (optional) — detected or declared language
        - "metadata": dict (optional) — any additional metadata
        """
        pass

    @abstractmethod
    def supported_extensions(self) -> List[str]:
        """Return list of file extensions this parser handles (without dots)."""
        pass


# =============================================================================
# Parser Registry
# =============================================================================

class ParserRegistry:
    """Maps file extensions to parser instances."""

    def __init__(self):
        self._parsers: Dict[str, BaseParser] = {}

    def register(self, parser: BaseParser):
        """Register a parser for its supported extensions."""
        for ext in parser.supported_extensions():
            self._parsers[ext.lower()] = parser

    def get_parser(self, extension: str) -> Optional[BaseParser]:
        """Get parser for a file extension, or None if unsupported."""
        return self._parsers.get(extension.lower())

    def supported_extensions(self) -> List[str]:
        """Return list of all currently supported extensions."""
        return list(self._parsers.keys())


# =============================================================================
# Markdown Parser — Section-Based Chunking
# =============================================================================

class MarkdownParser(BaseParser):
    """
    Parses Markdown files by splitting on headings.

    Each heading section becomes a separate record. Sections shorter than
    MIN_SECTION_LENGTH characters are dropped. If all sections are too short,
    falls back to the entire file content as one record.
    """

    def extract(self, filepath: Path, **kwargs) -> List[Dict[str, Any]]:
        content = filepath.read_text(encoding="utf-8", errors="replace")
        sections = []
        current_title = filepath.stem
        current_text = []

        for line in content.splitlines():
            if line.startswith("#"):
                # Flush previous section
                if current_text:
                    text = "\n".join(current_text).strip()
                    if len(text) >= MIN_SECTION_LENGTH:
                        sections.append({
                            "text": text,
                            "title": current_title,
                            "metadata": {"source_file": filepath.name},
                        })
                current_title = line.lstrip("#").strip()
                current_text = []
            else:
                current_text.append(line)

        # Flush last section
        if current_text:
            text = "\n".join(current_text).strip()
            if len(text) >= MIN_SECTION_LENGTH:
                sections.append({
                    "text": text,
                    "title": current_title,
                    "metadata": {"source_file": filepath.name},
                })

        # Fallback: if all sections were too short, use entire file
        if not sections:
            full_text = content.strip()
            if len(full_text) >= MIN_SECTION_LENGTH:
                sections = [{"text": full_text, "title": filepath.stem}]

        return sections

    def supported_extensions(self) -> List[str]:
        return ["md"]


# =============================================================================
# YAML Parser — Recursive Text Extraction
# =============================================================================

class YAMLParser(BaseParser):
    """
    Parses YAML files by recursively walking the data structure and
    extracting string values that meet the minimum length requirement.
    """

    def extract(self, filepath: Path, **kwargs) -> List[Dict[str, Any]]:
        import yaml

        content = filepath.read_text(encoding="utf-8", errors="replace")
        try:
            data = yaml.safe_load(content)
        except yaml.YAMLError as e:
            logger.warning(f"Failed to parse YAML file {filepath.name}: {e}")
            return []

        records: List[Dict[str, Any]] = []
        self._walk_yaml(data, filepath.stem, records, filepath.name)
        return records

    def _walk_yaml(self, node, title: str, records: list, source: str):
        """Recursively walk YAML nodes, extracting text strings."""
        if isinstance(node, str) and len(node.strip()) >= MIN_SECTION_LENGTH:
            records.append({
                "text": node.strip(),
                "title": title,
                "metadata": {"source_file": source},
            })
        elif isinstance(node, dict):
            for key, value in node.items():
                self._walk_yaml(value, str(key), records, source)
        elif isinstance(node, list):
            for item in node:
                self._walk_yaml(item, title, records, source)

    def supported_extensions(self) -> List[str]:
        return ["yaml", "yml"]


# =============================================================================
# XML Parser — Leaf-Node Text Extraction
# =============================================================================

class XMLParser(BaseParser):
    """
    Parses XML files by iterating over all elements and extracting
    text content from nodes that meet the minimum length requirement.
    """

    def extract(self, filepath: Path, **kwargs) -> List[Dict[str, Any]]:
        import xml.etree.ElementTree as ET

        try:
            tree = ET.parse(filepath)
        except ET.ParseError as e:
            logger.warning(f"Failed to parse XML file {filepath.name}: {e}")
            return []

        root = tree.getroot()
        records = []

        for elem in root.iter():
            text = (elem.text or "").strip()
            if len(text) >= MIN_SECTION_LENGTH:
                # Strip namespace from tag name if present
                tag_name = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
                records.append({
                    "text": text,
                    "title": tag_name,
                    "metadata": {"source_file": filepath.name, "tag": elem.tag},
                })

        return records

    def supported_extensions(self) -> List[str]:
        return ["xml"]


# =============================================================================
# Text Parser — Plain Text Files
# =============================================================================

class TextParser(BaseParser):
    """
    Parses plain text files. For short files, returns the entire content
    as a single record. For longer files, splits by double-newlines
    (paragraph breaks) and filters by minimum length.
    """

    # If a file has more than this many characters, try paragraph splitting
    PARAGRAPH_SPLIT_THRESHOLD = 500

    def extract(self, filepath: Path, **kwargs) -> List[Dict[str, Any]]:
        content = filepath.read_text(encoding="utf-8", errors="replace").strip()

        if not content or len(content) < MIN_SECTION_LENGTH:
            return []

        # For short files, return as a single record
        if len(content) <= self.PARAGRAPH_SPLIT_THRESHOLD:
            return [{
                "text": content,
                "title": filepath.stem,
                "metadata": {"source_file": filepath.name},
            }]

        # For longer files, try splitting by blank lines
        paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
        records = [
            {
                "text": p,
                "title": filepath.stem,
                "metadata": {"source_file": filepath.name},
            }
            for p in paragraphs
            if len(p) >= MIN_SECTION_LENGTH
        ]

        # Fallback if paragraph splitting filters everything out
        if not records:
            records = [{
                "text": content,
                "title": filepath.stem,
                "metadata": {"source_file": filepath.name},
            }]

        return records

    def supported_extensions(self) -> List[str]:
        return ["txt"]


# =============================================================================
# CSV Parser — Wraps Existing pd.read_csv Logic
# =============================================================================

class CSVParser(BaseParser):
    """
    Parses CSV files using pandas. Maintains backward compatibility with
    the existing upload_dataset() logic, including support for custom
    separators and text column selection.

    Keyword args:
        sep (str): CSV separator (default: ',')
        text_column (str): Name of the text column (default: auto-detect)
    """

    def extract(self, filepath: Path, **kwargs) -> List[Dict[str, Any]]:
        sep = kwargs.get("sep", ",")

        try:
            df = pd.read_csv(filepath, sep=sep)
        except Exception as e:
            logger.error(f"Failed to read CSV file {filepath.name}: {e}")
            return []

        text_column = kwargs.get("text_column")
        if text_column and text_column in df.columns:
            text_col = text_column
        else:
            # Auto-detect: use first string column with reasonable content
            text_col = self._find_text_column(df)

        if text_col is None:
            logger.warning(f"No text column found in CSV file {filepath.name}")
            return []

        records = []
        title_col = self._find_title_column(df)

        for idx, row in df.iterrows():
            text = str(row[text_col]).strip()
            if len(text) >= MIN_SECTION_LENGTH:
                record = {
                    "text": text,
                    "title": str(row[title_col]).strip() if title_col else filepath.stem,
                    "metadata": {"source_file": filepath.name, "row_index": idx},
                }
                # Preserve language column if present
                if "lang" in df.columns:
                    record["lang"] = str(row["lang"]).strip().upper()
                records.append(record)

        return records

    def _find_text_column(self, df: pd.DataFrame) -> Optional[str]:
        """Find the best text column by average string length."""
        text_candidates = df.select_dtypes(include=["object"]).columns
        if len(text_candidates) == 0:
            return None
        # Pick column with longest average text
        avg_lengths = {
            col: df[col].astype(str).str.len().mean() for col in text_candidates
        }
        return max(avg_lengths, key=avg_lengths.get)

    def _find_title_column(self, df: pd.DataFrame) -> Optional[str]:
        """Find a title column if present."""
        for candidate in ["title", "Title", "name", "Name", "heading", "subject"]:
            if candidate in df.columns:
                return candidate
        return None

    def supported_extensions(self) -> List[str]:
        return ["csv"]


# =============================================================================
# Parquet Parser — Wraps Existing pd.read_parquet Logic
# =============================================================================

class ParquetParser(BaseParser):
    """
    Parses Parquet files using pandas.

    Keyword args:
        text_column (str): Name of the text column (default: auto-detect)
    """

    def extract(self, filepath: Path, **kwargs) -> List[Dict[str, Any]]:
        try:
            df = pd.read_parquet(filepath)
        except Exception as e:
            logger.error(f"Failed to read Parquet file {filepath.name}: {e}")
            return []

        text_column = kwargs.get("text_column")
        if text_column and text_column in df.columns:
            text_col = text_column
        else:
            # Auto-detect using same strategy as CSV
            text_candidates = df.select_dtypes(include=["object"]).columns
            if len(text_candidates) == 0:
                logger.warning(f"No text column found in Parquet file {filepath.name}")
                return []
            avg_lengths = {
                col: df[col].astype(str).str.len().mean() for col in text_candidates
            }
            text_col = max(avg_lengths, key=avg_lengths.get)

        records = []
        title_col = None
        for candidate in ["title", "Title", "name", "Name"]:
            if candidate in df.columns:
                title_col = candidate
                break

        for idx, row in df.iterrows():
            text = str(row[text_col]).strip()
            if len(text) >= MIN_SECTION_LENGTH:
                record = {
                    "text": text,
                    "title": str(row[title_col]).strip() if title_col else filepath.stem,
                    "metadata": {"source_file": filepath.name, "row_index": idx},
                }
                if "lang" in df.columns:
                    record["lang"] = str(row["lang"]).strip().upper()
                records.append(record)

        return records

    def supported_extensions(self) -> List[str]:
        return ["parquet"]


# =============================================================================
# Default Registry
# =============================================================================

def create_default_registry() -> ParserRegistry:
    """Create a ParserRegistry with all built-in parsers registered."""
    registry = ParserRegistry()
    registry.register(MarkdownParser())
    registry.register(YAMLParser())
    registry.register(XMLParser())
    registry.register(TextParser())
    registry.register(CSVParser())
    registry.register(ParquetParser())
    return registry
