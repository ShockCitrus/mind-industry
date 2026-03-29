"""Pydantic v2 models for validating MIND CLI run configuration."""

from pathlib import Path
from typing import Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


class CorpusConfig(BaseModel):
    corpus_path: str
    thetas_path: str
    id_col: str = "doc_id"
    passage_col: str = "text"
    full_doc_col: str = "full_doc"
    lang_filter: str
    filter_ids_path: Optional[str] = None
    index_path: Optional[str] = None  # required for target corpus


class DetectConfig(BaseModel):
    monolingual: bool = False
    topics: List[int]
    sample_size: Optional[int] = None
    path_save: str = "data/results"
    method: str = "TB-ENN"
    do_weighting: bool = True
    do_check_entailment: bool = False
    selected_categories: Optional[list] = None
    source: CorpusConfig
    target: CorpusConfig

    @field_validator("topics")
    @classmethod
    def topics_must_be_positive(cls, v: List[int]) -> List[int]:
        for t in v:
            if t < 1:
                raise ValueError(f"Topics must be >= 1 (1-indexed). Got: {t}")
        return v


class SegmentConfig(BaseModel):
    input: str
    output: str
    text_col: str = "text"
    id_col: str = "id_preproc"
    min_length: int = 100
    separator: str = "\n"


class TranslateConfig(BaseModel):
    input: str
    output: str
    src_lang: str
    tgt_lang: str
    text_col: str = "text"
    lang_col: str = "lang"
    bilingual: bool = False  # True: split mixed dataset, translate both directions


class SchemaMapping(BaseModel):
    chunk_id: str = "id_preproc"
    text: str = "text"
    lang: str = "lang"
    full_doc: str = "full_doc"
    doc_id: str = "doc_id"


class PrepareConfig(BaseModel):
    model_config = {"populate_by_name": True}

    anchor: str
    comparison: Optional[str] = None  # None for monolingual
    output: str
    col_schema: SchemaMapping = Field(default_factory=SchemaMapping, alias="schema")
    nlpipe_script: Optional[str] = None
    nlpipe_config: Optional[str] = None
    stw_path: Optional[str] = None
    spacy_models: Optional[Dict[str, str]] = None
    monolingual: bool = False


class TMTrainConfig(BaseModel):
    input: str
    lang1: str
    lang2: Optional[str] = None  # None for monolingual (LDATM)
    model_folder: str
    num_topics: int = 30
    alpha: float = 1.0
    mallet_path: str = "externals/Mallet-202108/bin/mallet"
    stops_path: str = "src/mind/topic_modeling/stops"


class TMLabelConfig(BaseModel):
    model_folder: str
    lang1: str
    lang2: Optional[str] = None


class LLMConfig(BaseModel):
    default: Optional[dict] = None


class RunConfig(BaseModel):
    """Top-level run configuration file model."""
    llm: Optional[LLMConfig] = None
    detect: Optional[DetectConfig] = None
    data: Optional[dict] = None  # validated per-command
    tm: Optional[dict] = None    # validated per-command
