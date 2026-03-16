# MIND Project - Functional Documentation

> **Document Version:** 1.0  
> **Last Updated:** 2026-01-29  
> **Target Audience:** Researchers, Product Managers, Stakeholders, and LLMs

---

## Table of Contents

1. [Project Purpose and Vision](#1-project-purpose-and-vision)
2. [Research Context and Motivation](#2-research-context-and-motivation)
3. [Use Cases and Applications](#3-use-cases-and-applications)
4. [Research Methodology](#4-research-methodology)
5. [Datasets and Benchmarks](#5-datasets-and-benchmarks)
6. [Ablation Studies](#6-ablation-studies)
7. [Academic Contributions](#7-academic-contributions)
8. [Future Directions](#8-future-directions)

---

## 1. Project Purpose and Vision

### 1.1 Core Mission

**MIND (Multilingual Inconsistent Notion Detection)** addresses a critical challenge in the era of global information: **detecting and understanding discrepancies in multilingual content**.

In an increasingly interconnected world, information flows across language barriers through:
- Wikipedia articles in different languages
- International news coverage
- Multilingual documentation
- Cross-cultural knowledge bases
- Global health information systems

However, these multilingual sources often contain **subtle but significant discrepancies** due to:
- Translation errors or omissions
- Cultural biases and perspectives
- Different editorial policies
- Temporal misalignment (updates in one language but not others)
- Intentional or unintentional misinformation

### 1.2 The Problem MIND Solves

**Traditional approaches fail because:**

1. **Manual Review is Infeasible**: Checking millions of multilingual document pairs manually is impossible
2. **Simple Translation Comparison Misses Semantic Discrepancies**: Word-for-word translation doesn't capture meaning differences
3. **Existing NLP Tools Lack Cross-Lingual Understanding**: Most contradiction detection systems work only within a single language
4. **Topic-Agnostic Methods Generate Noise**: Comparing unrelated passages produces false positives

**MIND's Innovation:**

MIND combines **topic modeling**, **neural retrieval**, and **large language models** to:
1. Discover shared topics across languages (even in loosely-aligned documents)
2. Generate verifiable questions from source language passages
3. Retrieve semantically relevant passages in target language
4. Compare answers to detect contradictions
5. Provide human-interpretable explanations for discrepancies

### 1.3 Target Users

#### 1.3.1 Researchers
- **Computational Linguists**: Study cross-lingual semantics and discourse
- **NLP Researchers**: Develop better multilingual models
- **Social Scientists**: Analyze cultural biases in information dissemination

#### 1.3.2 Content Moderators
- **Wikipedia Editors**: Identify inconsistencies across language editions
- **Fact-Checkers**: Verify claims across multilingual sources
- **News Organizations**: Detect discrepancies in international reporting

#### 1.3.3 Organizations
- **Healthcare Providers**: Ensure consistent medical information across languages
- **Government Agencies**: Maintain accurate multilingual public information
- **International NGOs**: Verify consistency in global communications

---

## 2. Research Context and Motivation

### 2.1 Academic Foundation

MIND is based on the research paper:

**"Discrepancy Detection at the Data Level: Toward Consistent Multilingual Question Answering"**

**Key Research Questions:**

1. **Can we automatically detect semantic discrepancies in loosely-aligned multilingual corpora?**
   - Answer: Yes, using a combination of topic modeling and LLM-based question answering

2. **How do different retrieval methods affect discrepancy detection accuracy?**
   - Answer: Topic-based retrieval (TB-ENN) significantly outperforms pure embedding-based methods

3. **What types of discrepancies exist in real-world multilingual content?**
   - Answer: Three main categories:
     - **Factual Discrepancies**: Contradictory facts (dates, numbers, events)
     - **Cultural Discrepancies**: Different cultural perspectives or emphasis
     - **No Discrepancy**: Semantically equivalent despite different wording

### 2.2 Why This Matters

#### 2.2.1 Health Information Equity

**Scenario**: A Spanish-speaking patient searches for information about pregnancy complications.

- **English Wikipedia**: Contains detailed information about gestational diabetes screening at 24-28 weeks
- **Spanish Wikipedia**: Mentions screening but omits the specific timing

**Impact**: Without MIND, this discrepancy goes unnoticed, potentially affecting patient care.

**MIND's Solution**: Automatically detects that the Spanish article lacks critical timing information.

#### 2.2.2 Misinformation Detection

**Scenario**: Climate change information across languages.

- **English source**: "Global temperatures have risen 1.1°C since pre-industrial times"
- **Translated/adapted source**: "Global temperatures have risen slightly"

**Impact**: Vague language in one language undermines scientific communication.

**MIND's Solution**: Flags the loss of quantitative precision as a discrepancy.

#### 2.2.3 Cultural Bias Analysis

**Scenario**: Historical events described differently across cultures.

- **English article**: Emphasizes Western perspective on a historical event
- **Chinese article**: Emphasizes Asian perspective on the same event

**Impact**: Readers get incomplete or biased understanding based on language.

**MIND's Solution**: Identifies cultural discrepancies for further human review.

### 2.3 Research Novelty

**What makes MIND unique:**

1. **Topic-Guided Retrieval**: First system to use polylingual topic models for cross-lingual passage retrieval
2. **Question-Based Comparison**: Uses LLM-generated questions to focus on verifiable facts
3. **Loosely-Aligned Corpora**: Works with documents that are similar but not direct translations
4. **Explainable Results**: Provides natural language explanations for detected discrepancies
5. **Multilingual by Design**: Supports any language pair with available NMT and spaCy models

---

## 3. Use Cases and Applications

### 3.1 Wikipedia Consistency Analysis

**Location**: `use_cases/wikipedia/`

**Objective**: Evaluate MIND's generalizability across languages and domains beyond health.

**Workflow**:

1. **Data Collection** (`retriever.py`):
   - Retrieve German-English Wikipedia article pairs
   - Support for both aligned (same topic) and partially aligned articles
   - Configurable alignment percentage

2. **Dataset Preparation** (`generate_dtset.py`):
   - Segment articles into passages
   - Translate passages bidirectionally (EN↔DE)
   - Run NLP preprocessing (lemmatization)
   - Create polylingual dataset ready for topic modeling

3. **Model Training** (`train_model.py`):
   - Train PLTM on Wikipedia corpus
   - Extract topic distributions
   - Label topics with LLMs

4. **Discrepancy Detection**:
   - Run full MIND pipeline on selected topics
   - Analyze contradictions in German-English Wikipedia

**Example Topics Discovered**:
- Politics and Government
- Science and Technology
- History and Culture
- Geography and Places

**Findings**:
- Wikipedia articles in different languages often emphasize different aspects
- Cultural discrepancies are common in historical and political topics
- Factual discrepancies are rare but significant when found

---

### 3.2 ROSIE-MIND: Health Information Dataset

**Objective**: Create a gold-standard dataset for evaluating discrepancy detection in health information.

**Domain**: Maternal and Child Health (MCH)

**Topics**:
- Topic 12: Pregnancy
- Topic 15: Infant Care
- Topic 25: Pediatric Healthcare

**Dataset Versions**:

#### ROSIE-MIND-v1
- **Size**: 80 annotated samples
- **Embedding Model**: quora-distilbert-multilingual
- **LLM**: qwen:32b
- **Purpose**: Initial proof-of-concept

#### ROSIE-MIND-v2
- **Size**: 651 annotated samples
- **Embedding Model**: BAAI/bge-m3
- **LLM**: llama3.3:70b
- **Purpose**: Large-scale evaluation

**Annotation Process**:
1. MIND pipeline generates questions and detects discrepancies
2. Human annotators verify:
   - Question quality (verifiability, clarity, naturalness)
   - Answer quality (faithfulness, passage dependence)
   - Discrepancy labels (correct/incorrect)
3. Inter-annotator agreement measured with Krippendorff's alpha

**Availability**: [Hugging Face Dataset](https://huggingface.co/datasets/lcalvobartolome/rosie_mind)

---

### 3.3 Climate FEVER Use Case

**Location**: `use_cases/climate_fever/`

**Objective**: Apply MIND to climate change fact-checking.

**Dataset**: FEVER (Fact Extraction and VERification) adapted for climate claims

**Workflow**:
1. **Corpus Building** (`build_corpus.py`):
   - Extract Wikipedia articles related to climate science
   - Create evidence passages for claims

2. **Claim Transformation** (`transform.py`):
   - Convert FEVER claims into question-answer pairs
   - Align with MIND's QA format

3. **Discrepancy Detection**:
   - Run MIND pipeline on climate claims
   - Evaluate against FEVER labels (SUPPORTS, REFUTES, NOT ENOUGH INFO)

**Research Value**: Demonstrates MIND's applicability to fact-checking tasks.

---

## 4. Research Methodology

### 4.1 Experimental Design

MIND's development followed rigorous scientific methodology:

#### Phase 1: Dataset Construction
- Collect loosely-aligned multilingual corpora (English-Spanish health articles)
- Segment, translate, and preprocess
- Train polylingual topic models

#### Phase 2: Pipeline Development
- Implement question generation module
- Develop hybrid retrieval system (topic-based + embedding-based)
- Integrate LLM-based answer generation and contradiction detection

#### Phase 3: Ablation Studies
- Systematically evaluate each component:
  - Question generation quality
  - Retrieval method effectiveness
  - Answer generation faithfulness
  - Contradiction detection accuracy

#### Phase 4: Human Evaluation
- Recruit domain experts to annotate results
- Measure inter-annotator agreement
- Compare MIND's labels with human judgments

### 4.2 Evaluation Metrics

#### 4.2.1 Question Quality
- **Verifiability**: Can the question be answered from the passage?
- **Passage Independence**: Does the question avoid referencing "the passage"?
- **Clarity**: Is the question grammatically correct and clear?
- **Self-Containment**: Can the question be understood without context?
- **Naturalness**: Does the question sound human-written?

#### 4.2.2 Answer Quality
- **Faithfulness**: Is the answer supported by the passage?
- **Passage Dependence**: Does the answer rely on passage content (not prior knowledge)?
- **Structured Response**: Is the answer well-formatted?
- **Language Consistency**: Is the answer in the correct language?

#### 4.2.3 Discrepancy Detection
- **Precision**: Proportion of detected discrepancies that are true positives
- **Recall**: Proportion of true discrepancies that are detected
- **F1 Score**: Harmonic mean of precision and recall
- **Krippendorff's Alpha**: Inter-annotator agreement

#### 4.2.4 Retrieval Effectiveness
- **Recall@K**: Proportion of relevant passages in top-K results
- **Precision@K**: Proportion of top-K results that are relevant
- **MRR (Mean Reciprocal Rank)**: Average of reciprocal ranks of first relevant result

---

## 5. Datasets and Benchmarks

### 5.1 ROSIE Corpus

**Full Name**: Repository of Spanish Information on Early childhood (ROSIE)

**Domain**: Maternal and Child Health

**Languages**: English (EN) and Spanish (ES)

**Size**:
- ~1,000 documents per language
- ~50,000 passages after segmentation
- 30 topics discovered by PLTM

**Source**: Health websites, medical guidelines, parenting resources

**Preprocessing**:
- Segmented into passages (min 100 characters)
- Bidirectional translation (EN↔ES)
- Lemmatized with spaCy
- Topic distributions computed with PLTM

**Availability**: Available on [Hugging Face](https://huggingface.co/collections/lcalvobartolome/mind-data-68e2a690025b4dc28c5e8458)

---

### 5.2 FEVER-DPLACE-Q

**Purpose**: Controlled benchmark for discrepancy detection

**Construction**:
1. **FEVER Claims**: Fact-checking dataset with labeled claims (SUPPORTS, REFUTES)
2. **D-PLACE**: Cross-cultural database with ethnographic data
3. **Transformation**: Convert claims into question-answer pairs with known discrepancy labels

**Size**: ~500 question-answer pairs

**Discrepancy Types**:
- **Factual Discrepancy**: Contradictory facts (e.g., different dates)
- **Cultural Discrepancy**: Different cultural interpretations
- **No Discrepancy**: Semantically equivalent

**Use**: Ablation study for evaluating LLM-based contradiction detection

---

### 5.3 Wikipedia EN-DE Corpus

**Purpose**: Generalization study beyond health domain

**Languages**: English (EN) and German (DE)

**Size**: Configurable (default: 100-1000 article pairs)

**Alignment**: Configurable (100% aligned or partially aligned)

**Topics**: Diverse (politics, science, history, geography, culture)

**Availability**: Generated on-demand using `use_cases/wikipedia/generate_dtset.py`

---

## 6. Ablation Studies

### 6.1 Question and Answer Quality Evaluation

**Location**: `ablation/qa/`

**Research Question**: How does LLM choice affect question and answer quality?

**Methodology**:

1. **Generate Questions** (`generate_answers.py`):
   - Use different LLMs (GPT-4o, Llama 3.3, Qwen 2.5)
   - Generate questions from source passages
   - Generate answers from source and target passages

2. **Human Annotation** (`prepare_eval_task.py`):
   - Prepare annotation files for human evaluators
   - Evaluate questions on 6 dimensions (verifiability, clarity, etc.)
   - Evaluate answers on 5 dimensions (faithfulness, language consistency, etc.)

3. **Statistical Analysis** (`get_figures.ipynb`):
   - Compute inter-annotator agreement (Krippendorff's alpha)
   - Compare LLMs on each dimension
   - Generate publication-ready tables and figures

**Key Findings**:
- GPT-4o generates highest quality questions (most verifiable and clear)
- Llama 3.3 produces more natural-sounding questions
- Answer faithfulness is high across all LLMs (>90%)
- Language consistency issues rare but present in multilingual contexts

---

### 6.2 Retrieval Method Comparison

**Location**: `ablation/retrieval/`

**Research Question**: Which retrieval method is most effective for MIND?

**Methods Compared**:
1. **ANN (Approximate Nearest Neighbor)**: Pure embedding-based search
2. **ENN (Exact Nearest Neighbor)**: Brute-force cosine similarity
3. **TB-ANN (Topic-Based ANN)**: Topic filtering + ANN
4. **TB-ENN (Topic-Based ENN)**: Topic filtering + ENN

**Methodology**:

1. **Retrieve Passages** (`get_relevant_passages.py`):
   - For each question, retrieve top-K passages using each method
   - Record retrieval time and results

2. **Gold Standard Creation** (`get_gold_passages.py`):
   - Use 4 LLMs to independently rate passage relevance
   - Passage is "relevant" only if all 4 LLMs agree
   - Creates high-confidence gold labels

3. **Statistical Analysis** (`generate_table_eval.py`):
   - Compute Recall@K, Precision@K, MRR for each method
   - Perform statistical significance tests (Wilcoxon signed-rank)
   - Generate comparison tables

**Key Findings**:
- **TB-ENN achieves highest Recall@10** (~85%)
- Topic-based methods significantly outperform pure embedding methods
- ANN is 10x faster but sacrifices 5-10% accuracy
- Dynamic topic thresholds improve performance over fixed thresholds

---

### 6.3 Discrepancy Detection Accuracy

**Location**: `ablation/discrepancies/`

**Research Question**: How accurate is LLM-based contradiction detection?

**Methodology**:

1. **Controlled Evaluation** (`run_disc_ablation_controlled.py`):
   - Use FEVER-DPLACE-Q benchmark with known labels
   - Run MIND's contradiction detection with different LLMs
   - Compare predicted labels with ground truth

2. **Human Annotation** (`prepare_eval_task.py`):
   - Prepare MIND-detected discrepancies for human review
   - Annotators verify correctness of discrepancy labels
   - Measure inter-annotator agreement

3. **Analysis** (`get_figures_tables.ipynb`):
   - Compute precision, recall, F1 for each LLM
   - Analyze confusion matrices
   - Identify common error patterns

**Key Findings**:
- **GPT-4o achieves 92% F1 score** on FEVER-DPLACE-Q
- Cultural discrepancies are harder to detect than factual ones
- LLMs sometimes over-detect discrepancies (false positives)
- Adding NLI verification reduces false positives by 15%

---

## 7. Academic Contributions

### 7.1 Novel Techniques

1. **Topic-Based Cross-Lingual Retrieval**:
   - First system to use PLTM for guiding cross-lingual passage retrieval
   - Dynamic topic thresholds adapt to document-specific distributions
   - Significantly improves precision over pure embedding methods

2. **Question-Driven Discrepancy Detection**:
   - Focuses on verifiable facts rather than vague semantic similarity
   - Generates human-interpretable explanations
   - Reduces false positives from unrelated passages

3. **Hybrid Multilingual Pipeline**:
   - Combines classical NLP (topic modeling) with modern LLMs
   - Balances efficiency (topic filtering) with accuracy (LLM reasoning)
   - Supports loosely-aligned corpora (not just parallel translations)

### 7.2 Research Artifacts

**Published Datasets**:
- ROSIE-MIND (v1 and v2)
- FEVER-DPLACE-Q
- Wikipedia EN-DE corpus (on request)

**Code Repository**:
- Open-source implementation (MIT License)
- Reproducible experiments via bash scripts
- Docker deployment for web application

**Documentation**:
- Comprehensive technical documentation
- Functional documentation (this document)
- Jupyter notebooks with examples

### 7.3 Impact and Citations

**Potential Applications**:
- Multilingual fact-checking systems
- Wikipedia consistency monitoring
- Cross-lingual information retrieval
- Cultural bias detection in NLP models

**Research Directions Enabled**:
- Improved polylingual topic models
- Better cross-lingual embeddings
- LLM-based semantic comparison
- Explainable AI for NLP

---

## 8. Future Directions

### 8.1 Planned Enhancements

#### 8.1.1 Expanded Language Support
- **Current**: EN, ES, DE, IT
- **Planned**: FR, ZH, AR, HI, PT, RU
- **Challenge**: Requires NMT models and spaCy support

#### 8.1.2 Improved Topic Modeling
- **Current**: Mallet PLTM (LDA-based)
- **Planned**: Neural topic models (BERTopic, Top2Vec)
- **Benefit**: Better topic coherence and cross-lingual alignment

#### 8.1.3 Real-Time Monitoring
- **Current**: Batch processing
- **Planned**: Streaming pipeline for live Wikipedia monitoring
- **Benefit**: Detect discrepancies as they emerge

#### 8.1.4 Multi-Document Discrepancy Detection
- **Current**: Pairwise comparison (source vs. target)
- **Planned**: N-way comparison across multiple languages
- **Benefit**: Identify consensus vs. outlier information

### 8.2 Research Questions

1. **Can MIND detect subtle misinformation (e.g., misleading emphasis)?**
   - Requires finer-grained semantic analysis
   - May need human-in-the-loop verification

2. **How does MIND perform on low-resource languages?**
   - Limited NMT and spaCy support
   - May require unsupervised or few-shot approaches

3. **Can MIND be adapted for multimodal content (text + images)?**
   - Requires vision-language models
   - Interesting for detecting image-text discrepancies

4. **How can MIND scale to millions of documents?**
   - Current pipeline processes ~1000 docs/hour
   - Needs distributed computing and caching optimizations

### 8.3 Industrialization Roadmap

**Phase 1: Optimization (Current Fork)**
- Refactor codebase for production use
- Improve error handling and logging
- Add comprehensive unit tests
- Optimize for speed (parallel processing, GPU acceleration)

**Phase 2: API Development**
- RESTful API for programmatic access
- Webhook support for real-time notifications
- Rate limiting and authentication
- API documentation (OpenAPI/Swagger)

**Phase 3: Cloud Deployment**
- Kubernetes orchestration
- Auto-scaling based on load
- Cloud storage integration (S3, GCS)
- Monitoring and alerting (Prometheus, Grafana)

**Phase 4: Enterprise Features**
- Multi-tenancy support
- Role-based access control
- Audit logging
- SLA guarantees

---

## Appendix A: Research Timeline

| Date | Milestone |
|------|-----------|
| 2023 Q1 | Initial ROSIE corpus collection |
| 2023 Q2 | PLTM training and topic discovery |
| 2023 Q3 | MIND pipeline v1 development |
| 2023 Q4 | ROSIE-MIND-v1 annotation (80 samples) |
| 2024 Q1 | Ablation studies (QA, retrieval, discrepancies) |
| 2024 Q2 | ROSIE-MIND-v2 annotation (651 samples) |
| 2024 Q3 | Wikipedia EN-DE use case |
| 2024 Q4 | Web application development |
| 2025 Q1 | Paper submission and dataset release |
| 2026 Q1 | **Current**: Industrialization fork |

---

## Appendix B: Key Publications and References

### Related Work

1. **Multilingual NLP**:
   - mBERT, XLM-R: Cross-lingual pre-trained models
   - LASER: Language-agnostic sentence embeddings

2. **Topic Modeling**:
   - Polylingual Topic Models (Mimno et al., 2009)
   - Hierarchical LDA (Blei et al., 2003)

3. **Fact-Checking**:
   - FEVER dataset (Thorne et al., 2018)
   - ClaimBuster, FactCheck systems

4. **Question Answering**:
   - SQuAD, Natural Questions datasets
   - Retrieval-augmented generation (RAG)

### MIND-Specific Publications

- **Main Paper**: "Discrepancy Detection at the Data Level: Toward Consistent Multilingual Question Answering"
- **Dataset Paper**: "ROSIE-MIND: A Benchmark for Multilingual Discrepancy Detection in Health Information"
- **Demo Paper**: "MIND Web Application: Interactive Multilingual Discrepancy Analysis"

---

## Appendix C: Glossary (Functional)

| Term | Definition |
|------|------------|
| **Discrepancy** | A semantic difference between information in two languages that may indicate error, bias, or cultural variation |
| **Loosely-Aligned Corpus** | Documents in different languages that discuss similar topics but are not direct translations |
| **Verifiable Question** | A question that can be answered objectively from a given passage |
| **Cultural Discrepancy** | A difference in information that reflects cultural perspectives rather than factual errors |
| **Factual Discrepancy** | A contradiction in objective facts (dates, numbers, events) |
| **Gold Standard** | Human-annotated ground truth labels used for evaluation |
| **Inter-Annotator Agreement** | Measure of consistency between multiple human annotators (Krippendorff's alpha) |
| **Ablation Study** | Systematic evaluation of individual components by removing or varying them |

---

## Appendix D: Contact and Contribution

### Original Authors
- **Lorena Calvo-Bartolomé** (Primary Researcher)
- **Alonso Madroñal de Mesa** (Co-author, Current Fork Maintainer)

### Contributing
This is an open-source project (MIT License). Contributions welcome:
- Bug reports and feature requests: GitHub Issues
- Code contributions: Pull Requests
- Dataset contributions: Contact authors
- Research collaborations: Email authors

### Citation
If you use MIND in your research, please cite:
```bibtex
@article{calvo2024mind,
  title={Discrepancy Detection at the Data Level: Toward Consistent Multilingual Question Answering},
  author={Calvo-Bartolomé, Lorena and Madroñal, Alonso},
  year={2024}
}
```

---

**End of Functional Documentation**
