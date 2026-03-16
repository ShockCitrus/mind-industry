"""
Unit and integration tests for the data ingestion pipeline.

Tests parsers against real example files in instruction_examples/,
validates language detection, min-length filtering, archive extraction,
and full pipeline integration.
"""

import os
import tempfile
import zipfile
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

# Adjust these if the project root differs
PROJECT_ROOT = Path(__file__).resolve().parent.parent
EXAMPLES_DIR = PROJECT_ROOT / "instruction_examples"

from mind.ingestion.parsers import (
    MIN_SECTION_LENGTH,
    CSVParser,
    MarkdownParser,
    ParquetParser,
    ParserRegistry,
    TextParser,
    XMLParser,
    YAMLParser,
    create_default_registry,
)
from mind.ingestion.schema_mapper import (
    SUPPORTED_LANGUAGES,
    detect_language,
    records_to_dataframe,
)
from mind.ingestion.traversal import FileInfo, walk_files
from mind.ingestion.archive_handler import extract_archive, is_archive


# =============================================================================
# Parser Tests
# =============================================================================


class TestMarkdownParser:
    """Tests for MarkdownParser using instruction_examples/md/"""

    def setup_method(self):
        self.parser = MarkdownParser()

    def test_supported_extensions(self):
        assert self.parser.supported_extensions() == ["md"]

    def test_parse_analyst_md(self):
        filepath = EXAMPLES_DIR / "md" / "analyst.md"
        if not filepath.exists():
            pytest.skip(f"Example file not found: {filepath}")

        records = self.parser.extract(filepath)
        assert len(records) > 0
        for record in records:
            assert "text" in record
            assert len(record["text"]) >= MIN_SECTION_LENGTH

    def test_parse_step_02_context_md(self):
        filepath = EXAMPLES_DIR / "md" / "step-02-context.md"
        if not filepath.exists():
            pytest.skip(f"Example file not found: {filepath}")

        records = self.parser.extract(filepath)
        assert len(records) > 0
        for record in records:
            assert "text" in record
            assert "title" in record

    def test_min_length_filter(self):
        """Sections shorter than MIN_SECTION_LENGTH should be dropped."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write("# Short\nHi\n# Long Section\n" + "A" * 200 + "\n")
            f.flush()
            filepath = Path(f.name)

        try:
            records = self.parser.extract(filepath)
            # "Short" section ("Hi") should be filtered out
            for record in records:
                assert len(record["text"]) >= MIN_SECTION_LENGTH
        finally:
            os.unlink(filepath)

    def test_all_short_sections_fallback(self):
        """If all sections are too short, fallback to full file if long enough."""
        long_content = "# A\nShort.\n# B\nAlso short.\n"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write(long_content)
            f.flush()
            filepath = Path(f.name)

        try:
            records = self.parser.extract(filepath)
            # Full content is < 100 chars, so should return empty
            assert len(records) == 0
        finally:
            os.unlink(filepath)

    def test_all_short_fallback_long_file(self):
        """If all sections are short but combined is long enough, return as one record."""
        content = "# A\n" + ("x " * 20) + "\n# B\n" + ("y " * 20) + "\n" + ("z " * 50) + "\n"
        # Ensure total content >= MIN_SECTION_LENGTH
        if len(content.strip()) < MIN_SECTION_LENGTH:
            content = "# A\nShort.\n# B\nShort.\n" + "Extra padding. " * 20
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write(content)
            f.flush()
            filepath = Path(f.name)

        try:
            records = self.parser.extract(filepath)
            # Should have at least the fallback record if content is long enough
            if len(content.strip()) >= MIN_SECTION_LENGTH:
                assert len(records) >= 1
        finally:
            os.unlink(filepath)


class TestYAMLParser:
    """Tests for YAMLParser using instruction_examples/yaml/"""

    def setup_method(self):
        self.parser = YAMLParser()

    def test_supported_extensions(self):
        assert set(self.parser.supported_extensions()) == {"yaml", "yml"}

    def test_parse_bmm_dev_yaml(self):
        filepath = EXAMPLES_DIR / "yaml" / "bmm-dev.customize.yaml"
        if not filepath.exists():
            pytest.skip(f"Example file not found: {filepath}")

        records = self.parser.extract(filepath)
        # YAML values may be short, so records could be empty
        for record in records:
            assert "text" in record
            assert len(record["text"]) >= MIN_SECTION_LENGTH

    def test_parse_workflow_yaml(self):
        filepath = EXAMPLES_DIR / "yaml" / "workflow.yaml"
        if not filepath.exists():
            pytest.skip(f"Example file not found: {filepath}")

        records = self.parser.extract(filepath)
        for record in records:
            assert "text" in record

    def test_invalid_yaml(self):
        """Invalid YAML should return empty list, not crash."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("{{invalid yaml::: [")
            f.flush()
            filepath = Path(f.name)

        try:
            records = self.parser.extract(filepath)
            assert records == []
        finally:
            os.unlink(filepath)


class TestXMLParser:
    """Tests for XMLParser using instruction_examples/xml/"""

    def setup_method(self):
        self.parser = XMLParser()

    def test_supported_extensions(self):
        assert self.parser.supported_extensions() == ["xml"]

    def test_parse_instructions_xml(self):
        filepath = EXAMPLES_DIR / "xml" / "instructions.xml"
        if not filepath.exists():
            pytest.skip(f"Example file not found: {filepath}")

        records = self.parser.extract(filepath)
        assert len(records) > 0
        for record in records:
            assert "text" in record
            assert len(record["text"]) >= MIN_SECTION_LENGTH

    def test_parse_shard_doc_xml(self):
        filepath = EXAMPLES_DIR / "xml" / "shard-doc.xml"
        if not filepath.exists():
            pytest.skip(f"Example file not found: {filepath}")

        records = self.parser.extract(filepath)
        for record in records:
            assert "text" in record

    def test_invalid_xml(self):
        """Invalid XML should return empty list, not crash."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".xml", delete=False) as f:
            f.write("<broken><xml")
            f.flush()
            filepath = Path(f.name)

        try:
            records = self.parser.extract(filepath)
            assert records == []
        finally:
            os.unlink(filepath)


class TestTextParser:
    """Tests for TextParser."""

    def setup_method(self):
        self.parser = TextParser()

    def test_supported_extensions(self):
        assert self.parser.supported_extensions() == ["txt"]

    def test_short_file_returns_empty(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("Too short.")
            f.flush()
            filepath = Path(f.name)

        try:
            records = self.parser.extract(filepath)
            assert len(records) == 0
        finally:
            os.unlink(filepath)

    def test_single_record_for_short_content(self):
        content = "A" * 200  # > MIN_SECTION_LENGTH but < PARAGRAPH_SPLIT_THRESHOLD
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write(content)
            f.flush()
            filepath = Path(f.name)

        try:
            records = self.parser.extract(filepath)
            assert len(records) == 1
            assert records[0]["text"] == content
        finally:
            os.unlink(filepath)

    def test_paragraph_splitting(self):
        para1 = "First paragraph. " * 20
        para2 = "Second paragraph. " * 20
        content = para1 + "\n\n" + para2
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write(content)
            f.flush()
            filepath = Path(f.name)

        try:
            records = self.parser.extract(filepath)
            assert len(records) == 2
        finally:
            os.unlink(filepath)


# =============================================================================
# Parser Registry Tests
# =============================================================================


class TestParserRegistry:
    def test_default_registry(self):
        registry = create_default_registry()
        expected = {"md", "yaml", "yml", "xml", "txt", "csv", "parquet"}
        assert set(registry.supported_extensions()) == expected

    def test_get_parser(self):
        registry = create_default_registry()
        assert isinstance(registry.get_parser("md"), MarkdownParser)
        assert isinstance(registry.get_parser("yaml"), YAMLParser)
        assert isinstance(registry.get_parser("yml"), YAMLParser)
        assert isinstance(registry.get_parser("xml"), XMLParser)
        assert isinstance(registry.get_parser("txt"), TextParser)
        assert isinstance(registry.get_parser("csv"), CSVParser)
        assert isinstance(registry.get_parser("parquet"), ParquetParser)

    def test_unsupported_returns_none(self):
        registry = create_default_registry()
        assert registry.get_parser("rar") is None
        assert registry.get_parser("exe") is None


# =============================================================================
# Language Detection Tests
# =============================================================================


class TestLanguageDetection:
    def test_english(self):
        text = ("This is a comprehensive English text about the history of "
                "computing and technology. It needs to be long enough for "
                "reliable language detection to work properly.")
        assert detect_language(text) == "EN"

    def test_spanish(self):
        text = ("Este es un texto completo en español sobre la historia de "
                "la computación y la tecnología. Necesita ser lo suficientemente "
                "largo para que la detección de idioma funcione correctamente.")
        assert detect_language(text) == "ES"

    def test_german(self):
        text = ("Dies ist ein umfassender deutscher Text über die Geschichte "
                "der Informatik und Technologie. Er muss lang genug sein, "
                "damit die Spracherkennung zuverlässig funktioniert.")
        assert detect_language(text) == "DE"

    def test_italian(self):
        text = ("Questo è un testo completo in italiano sulla storia "
                "dell'informatica e della tecnologia. Deve essere abbastanza "
                "lungo affinché il rilevamento della lingua funzioni correttamente.")
        assert detect_language(text) == "IT"

    def test_unsupported_language_raises(self):
        text = ("Ceci est un texte complet en français sur l'histoire de "
                "l'informatique et de la technologie. Il doit être assez long "
                "pour que la détection de la langue fonctionne correctement.")
        with pytest.raises(ValueError, match="Unsupported language"):
            detect_language(text)


# =============================================================================
# Schema Mapper Tests
# =============================================================================


class TestRecordsToDataframe:
    def test_basic_mapping(self):
        records = [
            {
                "text": "This is a long enough English text for testing. " * 5,
                "title": "Test Title",
            }
        ]
        df = records_to_dataframe(records, "test_source")
        assert list(df.columns) == ["id_preproc", "text", "lang", "title"]
        assert df.iloc[0]["id_preproc"] == "test_source_0"
        assert df.iloc[0]["title"] == "Test Title"
        assert df.iloc[0]["lang"] in SUPPORTED_LANGUAGES

    def test_preserves_existing_lang(self):
        records = [
            {
                "text": "Anything here. " * 10,
                "title": "Test",
                "lang": "ES",
            }
        ]
        df = records_to_dataframe(records, "test")
        assert df.iloc[0]["lang"] == "ES"

    def test_unsupported_lang_raises(self):
        records = [
            {
                "text": ("Ceci est un texte complet en français. " * 5),
                "title": "French",
            }
        ]
        with pytest.raises(ValueError, match="Language detection failed"):
            records_to_dataframe(records, "french_source")


# =============================================================================
# Traversal Tests
# =============================================================================


class TestWalkFiles:
    def test_walk_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)

            # Create various files
            (root / "test.md").write_text("# Hello")
            (root / ".hidden").write_text("hidden")
            (root / ".DS_Store").write_text("junk")

            subdir = root / "subdir"
            subdir.mkdir()
            (subdir / "data.yaml").write_text("key: value")

            macosx = root / "__MACOSX"
            macosx.mkdir()
            (macosx / "junk.txt").write_text("junk")

            files = list(walk_files(root))
            extensions = {f.extension for f in files}
            paths = {f.relative_path for f in files}

            assert "md" in extensions
            assert "yaml" in extensions
            # Hidden files and junk should be excluded
            assert not any(".hidden" in f.relative_path for f in files)
            assert not any(".DS_Store" in f.relative_path for f in files)
            assert not any("__MACOSX" in f.relative_path for f in files)


# =============================================================================
# Archive Handler Tests
# =============================================================================


class TestArchiveHandler:
    def test_is_archive(self):
        assert is_archive("zip") is True
        assert is_archive("tar") is True
        assert is_archive("7z") is True
        assert is_archive("gz") is True
        assert is_archive("md") is False
        assert is_archive("csv") is False
        assert is_archive("rar") is False

    def test_extract_zip(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a test zip
            zip_path = Path(tmpdir) / "test.zip"
            with zipfile.ZipFile(zip_path, "w") as zf:
                zf.writestr("test.md", "# Test\n" + "Content. " * 30)
                zf.writestr("subdir/data.yaml", "key: value\n")

            extracted = extract_archive(zip_path)
            try:
                assert extracted.exists()
                assert (extracted / "test.md").exists()
                assert (extracted / "subdir" / "data.yaml").exists()
            finally:
                import shutil
                shutil.rmtree(extracted)

    def test_unsupported_format_raises(self):
        with tempfile.NamedTemporaryFile(suffix=".rar", delete=False) as f:
            f.write(b"not a real rar")
            filepath = Path(f.name)
        try:
            with pytest.raises(ValueError, match="Unsupported archive format"):
                extract_archive(filepath)
        finally:
            os.unlink(filepath)


# =============================================================================
# Integration Tests
# =============================================================================


class TestFullPipeline:
    """Integration test: create zip → extract → parse → schema map."""

    def test_zip_with_mixed_content(self):
        from mind.ingestion.pipeline import ingest_file

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a zip with mixed file types
            zip_path = Path(tmpdir) / "mixed_content.zip"
            md_content = "# Analysis\n" + ("This is a detailed analysis section with plenty of text for testing. " * 5) + "\n"
            xml_content = "<root><section>" + ("Detailed XML content for testing purposes. " * 5) + "</section></root>"

            with zipfile.ZipFile(zip_path, "w") as zf:
                zf.writestr("doc.md", md_content)
                zf.writestr("data.xml", xml_content)
                # Add a junk file that should be skipped
                zf.writestr(".DS_Store", "junk")

            df = ingest_file(zip_path)

            # Basic schema validation
            assert set(df.columns) == {"id_preproc", "text", "lang", "title"}
            assert len(df) > 0
            assert all(df["lang"].isin(SUPPORTED_LANGUAGES))
            assert all(df["text"].str.len() >= MIN_SECTION_LENGTH)

    def test_single_md_file(self):
        from mind.ingestion.pipeline import ingest_file

        md_path = EXAMPLES_DIR / "md" / "analyst.md"
        if not md_path.exists():
            pytest.skip(f"Example file not found: {md_path}")

        df = ingest_file(md_path)
        assert set(df.columns) == {"id_preproc", "text", "lang", "title"}
        assert len(df) > 0

    def test_unsupported_format_raises(self):
        from mind.ingestion.pipeline import ingest_file

        with tempfile.NamedTemporaryFile(suffix=".exe", delete=False) as f:
            f.write(b"binary content")
            filepath = Path(f.name)

        try:
            with pytest.raises(ValueError, match="Unsupported file format"):
                ingest_file(filepath)
        finally:
            os.unlink(filepath)

    def test_empty_archive_raises(self):
        from mind.ingestion.pipeline import ingest_file

        with tempfile.TemporaryDirectory() as tmpdir:
            zip_path = Path(tmpdir) / "empty.zip"
            with zipfile.ZipFile(zip_path, "w") as zf:
                pass  # Empty zip

            with pytest.raises(ValueError, match="No parseable content"):
                ingest_file(zip_path)
