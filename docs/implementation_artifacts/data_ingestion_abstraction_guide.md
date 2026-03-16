# Data Ingestion Abstraction Guide

## Overview

This guide details the implementation of a modular and scalable data ingestion pipeline designed to expand the application's current upload capabilities. The goal is to support compressed archives (`.tar`, `.zip`, `.7zip`, `.rar`) containing unstructured/semi-structured files (`.md`, `.xml`, `.yaml`, `.txt`), and to unify all ingestion flows under a single extensible architecture.

**Current State:** The upload flow only supports `.csv` and `.parquet`:

- **Frontend upload:** [profile.html](file:///home/alonso/Projects/Mind-Industry/app/frontend/templates/profile.html) — accepts file uploads with a 10MB limit (`MAX_SIZE_BYTES = 10 * 1024 * 1024`).
- **Frontend route:** [profile.py](file:///home/alonso/Projects/Mind-Industry/app/frontend/profile.py) `upload_dataset()` (L60–116) — forwards the file with metadata (stage, sep, textColumn, extension) to the backend.
- **Backend handler:** [dataset.py](file:///home/alonso/Projects/Mind-Industry/app/backend/dataset.py) `upload_dataset()` (L147–215) — saves the raw file to `/data/<email>/<stage>/<dataset_name>/dataset`, converts `.csv` → `.parquet` if needed, and registers the dataset in the `DATASETS_STAGE` parquet registry.
- **Dataset registry:** A global parquet file at `DATASETS_STAGE` env var, with schema: `Usermail`, `Dataset`, `OriginalDataset`, `Stage`, `Path`, `textColumn`.
- **Target schema:** Based on downstream usage in [data_preparer.py](file:///home/alonso/Projects/Mind-Industry/src/mind/corpus_building/data_preparer.py) and [segmenter.py](file:///home/alonso/Projects/Mind-Industry/src/mind/corpus_building/segmenter.py), the final dataset parquet must contain at minimum: `id_preproc`, `text`, `lang`, and optionally `title`.
- **Supported languages:** The application currently supports **EN, ES, DE, IT** (English, Spanish, German, Italian). Language detection must be limited to these four languages.

**Instruction examples** for parser development are in [instruction_examples/](file:///home/alonso/Projects/Mind-Industry/instruction_examples):
- `instruction_examples/md/` — 2 markdown files (analyst.md, step-02-context.md)
- `instruction_examples/yaml/` — 2 YAML files (bmm-dev.customize.yaml, workflow.yaml)
- `instruction_examples/xml/` — 2 XML files (instructions.xml, shard-doc.xml)

---

## Implementation Steps Overview

| Step | Phase Concept | Description | Completed |
| :--- | :--- | :--- | :---: |
| **1** | **Archive Extraction** | Implement safe decompression for `.tar`, `.zip`, `.7zip`, and `.rar` files to a secure temporary directory. | [x] |
| **2** | **Directory Traversal** | Build a directory walker to iterate through nested hierarchical structures of the extracted archives. | [x] |
| **3** | **Modular File Parsers** | Develop a registry/strategy system for format-specific parsers (`.md`, `.yaml`, `.xml`, etc.). | [x] |
| **4** | **Intelligent Parsing Engine** | Implement parsing logic with section chunking for `.md`, validation for `.yaml`/`.xml`, and minimum content filtering. | [x] |
| **5** | **Schema Integration** | Map the parsed data into the `Dataset` schema with mandatory language detection (EN/ES/DE/IT). | [x] |
| **6** | **Refactor Legacy Flow** | Migrate existing `.csv` and `.parquet` uploads to use the new unified modular flow. | [x] |
| **7** | **Testing & Cleanup** | Add unit tests and ensure temporary files are cleaned up. | [x] |

---

## Detailed Implementation Steps

### Step 1: Archive Extraction

**Objective:** Securely decompress uploaded archives to a temporary directory.

**Target file:** Create `src/mind/ingestion/archive_handler.py` (new module).

#### Tasks

1. **Create the `src/mind/ingestion/` package** with `__init__.py`.
2. **Implement `extract_archive(file_path: Path, dest_dir: Path) -> Path`:**
   - Detect archive type by extension.
   - Use the appropriate Python library for extraction:

     | Format | Library | Notes |
     |--------|---------|-------|
     | `.zip` | `zipfile` (stdlib) | Use `ZipFile.extractall()` |
     | `.tar`, `.tar.gz`, `.tar.bz2`, `.tar.xz` | `tarfile` (stdlib) | Use `TarFile.extractall()` |
     | `.7z` | `py7zr` (PyPI) | Requires `pip install py7zr` |
     | `.rar` | `rarfile` (PyPI) | Requires `pip install rarfile` + `unrar` binary |

3. **Return** the `dest_dir` path (where extracted contents reside).

#### Security & Safety

> [!CAUTION]
> Even with the 10MB upload limit, mitigate these risks:

- **Zip bomb protection:** Before extraction, check the total uncompressed size. For `.zip`, iterate `ZipFile.infolist()` and sum `file_size`. Reject if total exceeds 100MB (10x the upload limit).
- **Path traversal:** For `.tar`, use `tarfile.data_filter` (Python 3.12+) or manually check that no member starts with `/` or contains `..`. For `.zip`, check `ZipInfo.filename` similarly.
- **Extraction size cap:** `MAX_EXTRACTED_SIZE = 100 * 1024 * 1024` (100MB).
- **File count cap:** `MAX_EXTRACTED_FILES = 5000`.

#### Temporary Directory Strategy

```python
import tempfile
from pathlib import Path

def extract_archive(file_path: Path) -> Path:
    """Extract archive to a temporary directory. Caller must clean up."""
    temp_dir = Path(tempfile.mkdtemp(prefix="mind_ingest_"))
    # ... extraction logic ...
    return temp_dir
```

> [!TIP]
> Use `tempfile.mkdtemp()` instead of `tempfile.TemporaryDirectory()` context manager because the lifecycle of the temp dir spans multiple pipeline steps. Clean up explicitly in the orchestrator's `finally` block.

---

### Step 2: Directory Traversal

**Objective:** Recursively scan the extracted directory for parseable files.

**Target file:** Add to `src/mind/ingestion/traversal.py`.

#### Tasks

1. **Implement `walk_files(root: Path) -> Generator[FileInfo, None, None]`:**
   ```python
   from dataclasses import dataclass
   
   @dataclass
   class FileInfo:
       path: Path
       extension: str      # lowercase, without dot (e.g., "md", "yaml")
       size_bytes: int
       relative_path: str  # relative to archive root, for metadata
   
   JUNK_FILES = {'.DS_Store', 'Thumbs.db', 'desktop.ini', '.gitkeep'}
   JUNK_DIRS = {'__MACOSX', '.git', '__pycache__', 'node_modules', '.svn'}
   
   def walk_files(root: Path) -> Generator[FileInfo, None, None]:
       for dirpath, dirnames, filenames in os.walk(root):
           # Prune junk directories in-place
           dirnames[:] = [d for d in dirnames if d not in JUNK_DIRS]
           
           for filename in filenames:
               if filename in JUNK_FILES or filename.startswith('.'):
                   continue
               filepath = Path(dirpath) / filename
               ext = filepath.suffix.lstrip('.').lower()
               yield FileInfo(
                   path=filepath,
                   extension=ext,
                   size_bytes=filepath.stat().st_size,
                   relative_path=str(filepath.relative_to(root))
               )
   ```

2. **Considerations:**
   - Use `os.walk` (not `rglob`) for in-place directory pruning.
   - Yield `FileInfo` objects to decouple traversal from parsing.
   - Ignore hidden files (starting with `.`).

---

### Step 3: Modular File Parsers

**Objective:** Abstract file reading into an extensible registry pattern.

**Target file:** `src/mind/ingestion/parsers.py`.

#### Tasks

1. **Define the `BaseParser` abstract class:**
   ```python
   from abc import ABC, abstractmethod
   from typing import List, Dict, Any
   
   class BaseParser(ABC):
       """Base interface for all file parsers."""
       
       @abstractmethod
       def extract(self, filepath: Path) -> List[Dict[str, Any]]:
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
   ```

2. **Implement specific parsers:**

   | Parser Class | Extensions | Strategy |
   |--------------|-----------|----------|
   | `MarkdownParser` | `md` | Split by headings (`## `, `### `), each section = 1 record |
   | `YAMLParser` | `yaml`, `yml` | Parse with `yaml.safe_load()`, extract text fields recursively |
   | `XMLParser` | `xml` | Parse with `xml.etree.ElementTree`, extract text from leaf nodes |
   | `TextParser` | `txt` | Read entire file as single record, or split by blank lines for long files |
   | `CSVParser` | `csv` | Wrap existing `pd.read_csv()` logic from `upload_dataset()` |
   | `ParquetParser` | `parquet` | Wrap existing `pd.read_parquet()` logic |

3. **Create `ParserRegistry`:**
   ```python
   class ParserRegistry:
       """Maps file extensions to parser instances."""
       
       def __init__(self):
           self._parsers: Dict[str, BaseParser] = {}
       
       def register(self, parser: BaseParser):
           for ext in parser.supported_extensions():
               self._parsers[ext.lower()] = parser
       
       def get_parser(self, extension: str) -> Optional[BaseParser]:
           return self._parsers.get(extension.lower())
       
       def supported_extensions(self) -> List[str]:
           return list(self._parsers.keys())
   
   # Default registry instance
   def create_default_registry() -> ParserRegistry:
       registry = ParserRegistry()
       registry.register(MarkdownParser())
       registry.register(YAMLParser())
       registry.register(XMLParser())
       registry.register(TextParser())
       registry.register(CSVParser())
       registry.register(ParquetParser())
       return registry
   ```

> [!TIP]
> **Extensibility:** To add a new format in the future, the developer only needs to: (1) implement a `BaseParser` subclass, (2) call `registry.register(NewParser())`. No other code changes needed.

---

### Step 4: Intelligent Parsing Engine

**Objective:** Extract meaningful text from varied file formats, handling both structured and unstructured content.

**Target file:** Enhance parsers from Step 3 in `src/mind/ingestion/parsers.py`.

> [!NOTE]
> Use the example files in [instruction_examples/](file:///home/alonso/Projects/Mind-Industry/instruction_examples) as reference inputs when developing and testing parsers.

#### 4a. Markdown Parser — Section-Based Chunking with Minimum Length Filter

The existing [segmenter.py](file:///home/alonso/Projects/Mind-Industry/src/mind/corpus_building/segmenter.py) already applies a `min_length=100` character filter (L72: `df["_paragraphs"].str.len() > min_length`). However, the ingestion parser should also apply this filter **at parse time** to prevent tiny sections from even entering the pipeline.

```python
MIN_SECTION_LENGTH = 100  # characters — consistent with segmenter.py

class MarkdownParser(BaseParser):
    def extract(self, filepath: Path) -> List[Dict[str, Any]]:
        content = filepath.read_text(encoding='utf-8', errors='replace')
        sections = []
        current_title = filepath.stem
        current_text = []
        
        for line in content.splitlines():
            if line.startswith('#'):
                # Flush previous section
                if current_text:
                    text = '\n'.join(current_text).strip()
                    if len(text) >= MIN_SECTION_LENGTH:
                        sections.append({
                            "text": text,
                            "title": current_title,
                            "metadata": {"source_file": filepath.name}
                        })
                current_title = line.lstrip('#').strip()
                current_text = []
            else:
                current_text.append(line)
        
        # Flush last section
        if current_text:
            text = '\n'.join(current_text).strip()
            if len(text) >= MIN_SECTION_LENGTH:
                sections.append({
                    "text": text,
                    "title": current_title,
                    "metadata": {"source_file": filepath.name}
                })
        
        # If all sections were too short, fall back to entire file as one record
        if not sections:
            full_text = content.strip()
            if len(full_text) >= MIN_SECTION_LENGTH:
                sections = [{"text": full_text, "title": filepath.stem}]
        
        return sections
```

> [!IMPORTANT]
> The `MIN_SECTION_LENGTH = 100` filter prevents short sections (e.g., a heading with just a single sentence) from becoming noise in the dataset. This aligns with the existing segmenter's `min_length` parameter. Sections shorter than 100 characters are silently dropped. If **all** sections in a file are too short, a fallback combines the entire file content into one record (if above the threshold).

#### 4b. YAML Parser — Recursive Walk with Strict Validation

```python
class YAMLParser(BaseParser):
    def extract(self, filepath: Path) -> List[Dict[str, Any]]:
        import yaml
        content = filepath.read_text(encoding='utf-8', errors='replace')
        
        try:
            data = yaml.safe_load(content)
        except yaml.YAMLError:
            return []
        
        records = []
        self._walk_yaml(data, filepath.stem, records, filepath.name)
        return records
    
    def _walk_yaml(self, node, title: str, records: list, source: str):
        if isinstance(node, str) and len(node.strip()) >= MIN_SECTION_LENGTH:
            records.append({
                "text": node.strip(),
                "title": title,
                "metadata": {"source_file": source}
            })
        elif isinstance(node, dict):
            for key, value in node.items():
                self._walk_yaml(value, str(key), records, source)
        elif isinstance(node, list):
            for item in node:
                self._walk_yaml(item, title, records, source)
```

> [!WARNING]
> YAML files may contain empty string fields, `null` values, or very short labels. The parser MUST skip these — the `MIN_SECTION_LENGTH` check and the `node.strip()` call handle this. Empty strings will break downstream lemmatization in `data_preparer.py`.

#### 4c. XML Parser — Leaf-Node Text Extraction

```python
class XMLParser(BaseParser):
    def extract(self, filepath: Path) -> List[Dict[str, Any]]:
        import xml.etree.ElementTree as ET
        
        try:
            tree = ET.parse(filepath)
        except ET.ParseError:
            return []
        
        root = tree.getroot()
        records = []
        
        for elem in root.iter():
            text = (elem.text or '').strip()
            if len(text) >= MIN_SECTION_LENGTH:
                records.append({
                    "text": text,
                    "title": elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag,
                    "metadata": {"source_file": filepath.name, "tag": elem.tag}
                })
        
        return records
```

#### 4d. Standardized Output

All parsers output a list of dicts with this normalized structure:
```python
{
    "text": str,             # Required — the content to analyze (≥ 100 chars)
    "title": str,            # Optional — section/doc title
    "lang": str | None,      # Optional — if detectable from the file
    "metadata": {            # Optional — preserved for traceability
        "source_file": str,
        ...
    }
}
```

---

### Step 5: Schema Integration

**Objective:** Convert the intermediate parsed records into the application's `Dataset` schema with mandatory language detection.

**Target file:** `src/mind/ingestion/schema_mapper.py`.

#### Target Schema

| Column | Type | Description |
|--------|------|-------------|
| `id_preproc` | `str` | Unique identifier per record (e.g., `MD_0`, `YAML_1`) |
| `text` | `str` | The extracted textual content (≥ 100 chars) |
| `lang` | `str` | Language code: `EN`, `ES`, `DE`, or `IT`. **Mandatory.** |
| `title` | `str` | Document or section title (optional, defaults to filename) |

#### Language Detection — Mandatory, Limited to 4 Languages

> [!IMPORTANT]
> Language detection is **mandatory**. If detection fails or returns a language outside the supported set (`EN`, `ES`, `DE`, `IT`), the system must raise an error — **not silently default to EN**.

```python
SUPPORTED_LANGUAGES = {'EN', 'ES', 'DE', 'IT'}

def detect_language(text: str) -> str:
    """Detect language of text. Raises ValueError if unsupported."""
    try:
        from langdetect import detect
        lang = detect(text).upper()
        # langdetect returns ISO 639-1 codes, map to our conventions
        lang_map = {'EN': 'EN', 'ES': 'ES', 'DE': 'DE', 'IT': 'IT'}
        mapped = lang_map.get(lang)
        if mapped is None:
            raise ValueError(
                f"Unsupported language detected: '{lang}'. "
                f"This software supports: {', '.join(sorted(SUPPORTED_LANGUAGES))}. "
                f"Text sample: '{text[:80]}...'"
            )
        return mapped
    except ImportError:
        raise ImportError("langdetect package is required. Install with: pip install langdetect")
    except Exception as e:
        if "unsupported" in str(e).lower():
            raise  # Re-raise our ValueError
        raise ValueError(
            f"Language detection failed for text: '{text[:80]}...'. Error: {e}"
        )

def records_to_dataframe(records: List[Dict], source_name: str) -> pd.DataFrame:
    rows = []
    errors = []
    for i, record in enumerate(records):
        try:
            lang = record.get("lang") or detect_language(record["text"])
            rows.append({
                "id_preproc": f"{source_name}_{i}",
                "text": record["text"],
                "lang": lang,
                "title": record.get("title", source_name),
            })
        except ValueError as e:
            errors.append(str(e))
    
    if errors:
        raise ValueError(
            f"Language detection errors in {len(errors)} records:\n" + 
            "\n".join(errors[:5])  # Show first 5 errors
        )
    
    df = pd.DataFrame(rows)
    df = df[df['text'].str.strip().astype(bool)]
    return df.reset_index(drop=True)
```

---

### Step 6: Refactor Legacy Flow

**Objective:** Ensure all ingestion paths (CSV, parquet, archives) go through the unified pipeline.

#### Current Flow
```
profile.html → profile.py (upload_dataset) → backend/dataset.py (upload_dataset)
    ↓ saves raw file
    ↓ if CSV: pd.read_csv() → pd.to_parquet()
    ↓ registers in DATASETS_STAGE
```

#### New Flow
```
profile.html → profile.py (upload_dataset) → backend/dataset.py (upload_dataset)
    ↓ detect file type by extension
    ├── .csv / .parquet → CSVParser / ParquetParser (from registry)
    ├── .zip / .tar / .7z / .rar → extract → walk_files → parser per file → merge
    └── .md / .yaml / .xml / .txt → direct parser
    ↓ records_to_dataframe() with mandatory language detection
    ↓ save as /data/<email>/<stage>/<dataset_name>/dataset (parquet)
    ↓ register in DATASETS_STAGE
```

#### Tasks

1. **Modify `upload_dataset()` in [dataset.py](file:///home/alonso/Projects/Mind-Industry/app/backend/dataset.py)** (L147–215):
   - Detect archive extensions and route to the new pipeline.
   - Keep the existing CSV/parquet handling but wrap it in `CSVParser`/`ParquetParser`.
   
2. **Update `profile.html`** to accept new file extensions in the upload form:
   ```html
   accept=".csv,.parquet,.zip,.tar,.tar.gz,.7z,.rar,.md,.yaml,.yml,.xml,.txt"
   ```

3. **Create the main ingestion orchestrator:**
   ```python
   # src/mind/ingestion/pipeline.py
   def ingest_file(file_path: Path, registry: ParserRegistry) -> pd.DataFrame:
       ext = file_path.suffix.lstrip('.').lower()
       
       if ext in ('zip', 'tar', 'gz', '7z', 'rar'):
           temp_dir = extract_archive(file_path)
           try:
               all_records = []
               for file_info in walk_files(temp_dir):
                   parser = registry.get_parser(file_info.extension)
                   if parser:
                       records = parser.extract(file_info.path)
                       all_records.extend(records)
               if not all_records:
                   raise ValueError("No parseable content found in archive.")
               return records_to_dataframe(all_records, file_path.stem)
           finally:
               shutil.rmtree(temp_dir, ignore_errors=True)
       else:
           parser = registry.get_parser(ext)
           if not parser:
               raise ValueError(f"Unsupported file format: .{ext}")
           records = parser.extract(file_path)
           if not records:
               raise ValueError(f"No content extracted from file: {file_path.name}")
           return records_to_dataframe(records, file_path.stem)
   ```

> [!IMPORTANT]
> When refactoring the legacy flow, maintain backward compatibility. Existing `.csv` and `.parquet` uploads must continue to work exactly as before. The `CSVParser` and `ParquetParser` should replicate the existing behavior (including the `sep` parameter for CSV).

---

### Step 7: Testing & Cleanup

#### Tests

1. **Unit tests for each parser** using files from `instruction_examples/`:
   - `test_markdown_parser.py`: Parse `instruction_examples/md/analyst.md` and `step-02-context.md`. Assert sections are extracted with titles. Assert sections shorter than 100 chars are filtered out.
   - `test_yaml_parser.py`: Parse `instruction_examples/yaml/bmm-dev.customize.yaml` and `workflow.yaml`. Assert non-empty text values ≥ 100 chars are extracted.
   - `test_xml_parser.py`: Parse `instruction_examples/xml/instructions.xml` and `shard-doc.xml`. Assert meaningful text nodes are extracted.

2. **Integration test for archive ingestion:**
   - Create a test `.zip` containing a mix of `.md`, `.yaml`, `.xml` files.
   - Run the full pipeline: extract → walk → parse → schema map.
   - Assert the output DataFrame has correct schema, non-empty records, and valid language codes.

3. **Language detection tests:**
   - Test with known EN, ES, DE, IT texts → correct detection.
   - Test with unsupported language (e.g., French, Chinese) → `ValueError` raised.
   - Test with very short text → error raised (not silent default).

4. **Min length filter tests:**
   - Parse a markdown file with sections of varying lengths.
   - Assert sections < 100 chars are excluded from output.
   - Assert file with all-short sections either produces fallback or empty result.

5. **Regression test for CSV/parquet:**
   - Ensure existing uploads produce identical results through the new pipeline.

#### Cleanup

- Temporary directory cleanup via `finally` blocks in `ingest_file()`.
- Log cleanup actions: `logger.info(f"Cleaned up temp dir: {temp_dir}")`.

---

## Architecture Summary

```
src/mind/ingestion/
├── __init__.py
├── archive_handler.py    # Step 1: extract_archive()
├── traversal.py          # Step 2: walk_files(), FileInfo
├── parsers.py            # Step 3+4: BaseParser, specific parsers, ParserRegistry
├── schema_mapper.py      # Step 5: records_to_dataframe(), detect_language()
└── pipeline.py           # Step 6: ingest_file() orchestrator
```

## Verification Plan

### Automated Tests
- Parse each file in `instruction_examples/` through its respective parser and validate output schema.
- Test archive extraction with a crafted `.zip` containing nested directories and junk files.
- Test zip bomb protection (create a small zip with > 100MB uncompressed claim).
- Test language detection with all 4 supported languages and unsupported ones.
- Test min_length filtering edge cases.
- Test backward compatibility of CSV and parquet uploads.

### Manual Verification
- Upload a `.zip` archive via the profile page and verify the dataset appears in the preprocessing pipeline.
- Upload a single `.md` file and verify it produces a valid parquet dataset.
- Run the full preprocessing pipeline (Segmenter → Translator → Data Preparer → Topic Modeling) on an archive-ingested dataset.
- Attempt to upload a file in an unsupported language → verify clear error message is shown.
