# MIND Project - Technical Documentation

> **Document Version:** 1.0  
> **Last Updated:** 2026-01-29  
> **Target Audience:** Developers, Software Architects, and LLMs

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Technology Stack](#2-technology-stack)
3. [Architecture](#3-architecture)
4. [Core Modules (`src/mind`)](#4-core-modules-srcmind)
5. [Web Application (`app/`)](#5-web-application-app)
6. [Configuration Management](#6-configuration-management)
7. [Coding Conventions and Design Decisions](#7-coding-conventions-and-design-decisions)
8. [Data Flow and Processing Pipeline](#8-data-flow-and-processing-pipeline)
9. [Deployment](#9-deployment)

---

## 1. Project Overview

**MIND (Multilingual Inconsistent Notion Detection)** is a research-driven system designed to detect discrepancies and contradictions in multilingual text corpora. The system uses a combination of:

- **Polylingual Topic Modeling (PLTM)** to discover shared topics across languages
- **Neural Information Retrieval** for semantic search
- **Large Language Models (LLMs)** for question generation, answering, and contradiction detection
- **NLP preprocessing** for text segmentation, translation, and lemmatization

The project serves both as a **research platform** (for academic experiments and ablation studies) and as a **production web application** (for end-users to analyze multilingual datasets).

### Key Capabilities

- Detect semantic discrepancies between loosely-aligned multilingual documents
- Generate questions from source language passages
- Retrieve relevant passages in target language using hybrid retrieval (topic-based + embedding-based)
- Compare answers across languages to identify contradictions
- Provide a web interface for dataset management, preprocessing, topic modeling, and discrepancy analysis

---

## 2. Technology Stack

### 2.1 Core Python Dependencies

| Category | Technology | Version | Purpose |
|----------|-----------|---------|---------|
| **Language** | Python | 3.12.* | Core runtime |
| **ML/NLP** | PyTorch | 2.8.0 | Deep learning framework |
| | Transformers | 4.56.0 | Hugging Face models (NMT, embeddings, NLI) |
| | Sentence Transformers | 5.1.0 | Semantic embeddings (BGE-M3, MiniLM) |
| | NLTK | 3.9.1 | NLP utilities |
| | spaCy | (via NLPipe) | Lemmatization and linguistic preprocessing |
| **Topic Modeling** | Mallet | 202108 | Polylingual LDA implementation |
| | pyLDAvis | 3.4.1 | Topic visualization |
| **Retrieval** | FAISS | (CPU/GPU) | Approximate nearest neighbor search |
| **LLM Integration** | OpenAI | 1.106.1 | GPT-4, GPT-3.5 API |
| | Ollama | 0.5.3 | Local LLM inference (Llama, Qwen) |
| **Data** | Pandas | 2.3.2 | DataFrame operations |
| | PyArrow | 16.1.0 | Parquet I/O |
| | NumPy | <2.0.0 | Numerical computing |
| | SciPy | (via scikit-learn) | Sparse matrices |
| **Web Framework** | Flask | (implicit) | Backend and frontend services |
| | Flask-CORS | (implicit) | Cross-origin resource sharing |
| | Flask-Session | (implicit) | Session management |
| **Database** | PostgreSQL | 15 | User authentication and metadata |
| | SQLAlchemy | (implicit) | ORM for database access |
| **Utilities** | python-dotenv | 1.1.1 | Environment variable management |
| | tqdm | 4.67.1 | Progress bars |
| | joblib | 1.4.2 | Caching and parallelization |
| | colorama | 0.4.6 | Terminal color output |

### 2.2 External Tools

- **Mallet**: Java-based polylingual topic modeling (located in `externals/Mallet-202108/`)
- **NLPipe**: Custom NLP preprocessing pipeline (submodule in `externals/NLPipe/`)
- **Docker**: Containerization for deployment
- **uv**: Fast Python package installer (recommended for development)

### 2.3 Supported LLM Backends

1. **OpenAI API**: GPT-4, GPT-4o, GPT-3.5-turbo
2. **Ollama**: Llama 3.x, Qwen 2.5/3, local inference
3. **vLLM**: High-throughput inference server
4. **llama.cpp**: Lightweight C++ inference

---

## 3. Architecture

### 3.1 High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      MIND System                             │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────┐      ┌──────────────┐      ┌───────────┐ │
│  │   Frontend   │─────▶│   Backend    │─────▶│   Auth    │ │
│  │  (Flask UI)  │      │ (Flask API)  │      │ (Flask)   │ │
│  │  Port 5050   │      │  Port 5001   │      │ Port 5002 │ │
│  └──────────────┘      └──────────────┘      └───────────┘ │
│         │                      │                     │      │
│         │                      │                     │      │
│         └──────────────────────┴─────────────────────┘      │
│                                │                            │
│                                ▼                            │
│                        ┌──────────────┐                     │
│                        │  PostgreSQL  │                     │
│                        │   Database   │                     │
│                        │  Port 5444   │                     │
│                        └──────────────┘                     │
│                                                              │
├─────────────────────────────────────────────────────────────┤
│                     Core Library (src/mind)                  │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────────┐  ┌──────────────────┐                │
│  │ corpus_building  │  │ topic_modeling   │                │
│  │ - Segmenter      │  │ - PolylingualTM  │                │
│  │ - Translator     │  │ - TopicLabeler   │                │
│  │ - DataPreparer   │  │ - Hierarchical   │                │
│  └──────────────────┘  └──────────────────┘                │
│                                                              │
│  ┌──────────────────┐  ┌──────────────────┐                │
│  │    pipeline      │  │    prompter      │                │
│  │ - MIND (main)    │  │ - Prompter       │                │
│  │ - Corpus         │  │ - LLM backends   │                │
│  │ - Retriever      │  │ - Caching        │                │
│  └──────────────────┘  └──────────────────┘                │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 Architectural Patterns

#### 3.2.1 Microservices Architecture (Web App)

The web application follows a **microservices pattern** with three independent Flask services:

1. **Frontend Service** (`app/frontend/`)
   - Serves HTML templates (Jinja2)
   - Handles user sessions
   - Proxies requests to backend and auth services
   - Manages file uploads and downloads

2. **Backend Service** (`app/backend/`)
   - Executes MIND pipeline in background processes
   - Manages dataset preprocessing (segmentation, translation, data preparation)
   - Trains topic models
   - Handles discrepancy detection
   - Enforces concurrency limits (max users, max tasks per user)

3. **Auth Service** (`app/auth/`)
   - User registration and login
   - JWT token generation and validation
   - PostgreSQL database for user credentials

#### 3.2.2 Pipeline Architecture (Core Library)

The core MIND pipeline follows a **component-based architecture** where each stage is modular and reusable:

```
Input Corpus (Parquet)
    │
    ├─▶ Segmenter ─────▶ Passages
    │
    ├─▶ Translator ────▶ Bilingual Passages
    │
    ├─▶ DataPreparer ──▶ Preprocessed Dataset (with lemmas)
    │
    ├─▶ PolylingualTM ─▶ Topic Model + Document-Topic Distributions (θ)
    │
    └─▶ MIND Pipeline
         │
         ├─▶ Question Generation (LLM)
         │
         ├─▶ Subquery Generation (LLM)
         │
         ├─▶ Retrieval (IndexRetriever: TB-ENN, ANN, ENN)
         │
         ├─▶ Answer Generation (LLM) for source and target
         │
         ├─▶ Contradiction Detection (LLM + optional NLI)
         │
         └─▶ Results (Parquet with discrepancy labels)
```

#### 3.2.3 Design Patterns

- **Factory Pattern**: `Corpus.from_parquet_and_thetas()` for flexible corpus initialization
- **Strategy Pattern**: `IndexRetriever` supports multiple retrieval methods (ANN, ENN, TB-ANN, TB-ENN)
- **Template Method Pattern**: `Prompter` class abstracts LLM backends (OpenAI, Ollama, vLLM, llama.cpp)
- **Caching Pattern**: `joblib.Memory` for LLM response caching (reduces API costs)
- **Observer Pattern**: `StreamForwarder` for real-time log streaming to web UI

---

## 4. Core Modules (`src/mind`)

### 4.1 `corpus_building/`

Responsible for preparing raw multilingual corpora for the MIND pipeline.

#### 4.1.1 `segmenter.py`

**Purpose**: Split long documents into smaller passages (chunks) for fine-grained analysis.

**Class**: `Segmenter`

**Key Method**: `segment(path_df, path_save, text_col, id_col, min_length, sep)`

**Algorithm**:
1. Load input DataFrame (Parquet)
2. Split each document by separator (default: `\n`)
3. Filter paragraphs shorter than `min_length` (default: 100 characters)
4. Assign unique IDs: `{original_id}_{paragraph_index}`
5. Preserve original metadata + add `full_doc` column
6. Save segmented DataFrame to Parquet

**Design Decision**: Segmentation is done **before** translation to ensure alignment between source and target passages.

---

#### 4.1.2 `translator.py`

**Purpose**: Translate passages from source language to target language (and vice versa) using Hugging Face NMT models.

**Class**: `Translator`

**Supported Language Pairs**:
- `en ↔ es` (English ↔ Spanish)
- `en ↔ de` (English ↔ German)
- `en ↔ it` (English ↔ Italian)

**Key Method**: `translate(path_df, src_lang, tgt_lang, text_col, lang_col, save_path)`

**Algorithm**:
1. Load segmented DataFrame
2. **Split** paragraphs into sentences (to avoid exceeding model max length)
3. **Translate** sentences in batches using Hugging Face `pipeline`
4. **Reassemble** translated sentences back into paragraphs
5. **Append** translated paragraphs to original DataFrame
6. Mark translated rows with `T_` prefix in `id_preproc` column

**Design Decision**: 
- Sentence-level translation prevents truncation errors
- Preserves all metadata columns from original data
- Uses Hugging Face Datasets for efficient batch processing

---

#### 4.1.3 `data_preparer.py`

**Purpose**: Final preprocessing step before topic modeling. Runs NLP preprocessing (lemmatization) and formats data for Mallet.

**Class**: `DataPreparer`

**Key Method**: `format_dataframes(anchor_path, comparison_path, path_save)`

**Algorithm**:
1. Load anchor and comparison DataFrames
2. **Normalize** column names according to schema (configurable mapping)
3. **Run NLPipe** on both languages to extract lemmas
   - Calls external Python script: `externals/NLPipe/nlpipe.py`
   - Uses spaCy models for lemmatization
   - Adds `lemmas` column to DataFrame
4. **Merge** lemmas back into original DataFrame
5. **Create pair keys** to link original and translated passages
6. Save final preprocessed DataFrame

**Design Decision**:
- Schema mapping allows flexibility in input column names
- NLPipe is run as a subprocess to isolate spaCy dependencies
- Lemmas are stored as space-separated strings for Mallet compatibility

---

### 4.2 `topic_modeling/`

#### 4.2.1 `polylingual_tm.py`

**Purpose**: Wrapper around Mallet's Polylingual Topic Model (PLTM) for discovering shared topics across languages.

**Class**: `PolylingualTM`

**Key Methods**:
- `_create_mallet_input_corpus(df_path)`: Converts Parquet to Mallet text format
- `_prepare_mallet_input()`: Runs Mallet's `import-dir` command
- `train(df_path)`: Trains PLTM model
- `save_model_info()`: Extracts topic-word distributions, document-topic distributions (θ), and topic keys

**Algorithm**:
1. Create `corpus_{lang1}.txt` and `corpus_{lang2}.txt` from DataFrame
2. Import corpora into Mallet format (`.mallet` files)
3. Run Mallet's `train-topics-parallel` command with specified parameters:
   - `--num-topics`: Number of topics
   - `--alpha`: Dirichlet prior for document-topic distribution
   - `--beta`: Dirichlet prior for topic-word distribution
   - `--num-iterations`: Training iterations
   - `--optimize-interval`: Hyperparameter optimization frequency
4. Parse output files:
   - `topickeys.txt`: Top words per topic
   - `output-state.gz`: Full model state
   - `doc-topics.txt`: Document-topic distributions
5. Save θ (thetas) as sparse matrix (`.npz`)

**Design Decision**:
- Uses subprocess to call Java-based Mallet (no Python bindings available)
- Stores thetas as sparse matrices to save memory (most values are near-zero)
- Supports custom stopword lists per language

---

#### 4.2.2 `topic_label.py`

**Purpose**: Assign human-readable labels to topics using LLMs.

**Algorithm**:
1. Load topic model metadata (top words, top documents)
2. For each topic:
   - Construct prompt with top words and representative documents
   - Query LLM (e.g., GPT-4) for a short label
3. Save labels to `topic_labels.json`

**Design Decision**: Labels are optional but improve interpretability in the web UI.

---

### 4.3 `pipeline/`

#### 4.3.1 `corpus.py`

**Purpose**: Abstraction layer for managing document collections.

**Classes**:

##### `Chunk`
Represents a single text passage with metadata.

**Attributes**:
- `id`: Unique identifier
- `text`: Passage text
- `full_doc`: Full document text (context)
- `metadata`: Dictionary with `top_k` topics, `questions`, `answers`, `score`

##### `Corpus`
Manages a collection of chunks with topic distributions.

**Key Methods**:
- `from_parquet_and_thetas()`: Factory method to load corpus from files
- `chunks_with_topic(topic_id, sample_size)`: Iterator over chunks assigned to a topic
- `retrieve_relevant_chunks(query, theta_query)`: Retrieve chunks using IndexRetriever

**Design Decision**:
- Lazy loading: Chunks are yielded on-demand to save memory
- Supports filtering by language and topic
- Integrates with retrieval system via `IndexRetriever`

---

#### 4.3.2 `retriever.py`

**Purpose**: Hybrid retrieval system combining topic-based and embedding-based search.

**Class**: `IndexRetriever`

**Retrieval Methods**:

1. **ANN (Approximate Nearest Neighbor)**:
   - Pure embedding-based search using FAISS
   - Fast but ignores topic structure

2. **ENN (Exact Nearest Neighbor)**:
   - Brute-force cosine similarity
   - Slower but more accurate

3. **TB-ANN (Topic-Based ANN)**:
   - Filters candidates by topic distribution before ANN search
   - Uses dynamic thresholds on θ to identify relevant topics

4. **TB-ENN (Topic-Based ENN)**:
   - Combines topic filtering with exact search
   - Best accuracy for MIND pipeline

**Key Methods**:
- `index(source_path, thetas_path, method)`: Build FAISS index
- `retrieve(query, theta_query, top_k)`: Retrieve top-k passages
- `dynamic_thresholds(mat)`: Compute per-document topic thresholds using knee detection

**Algorithm (TB-ENN)**:
1. Compute query embedding
2. Compute query topic distribution (θ_query) using topic model
3. For each document:
   - Check if any topic in θ_query overlaps with θ_doc (above threshold)
   - If yes, add to candidate set
4. Compute cosine similarity between query and candidates
5. Return top-k by similarity

**Design Decision**:
- Topic-based filtering reduces search space by 10-100x
- Dynamic thresholds adapt to document-specific topic distributions
- Supports both CPU and GPU FAISS indices

---

#### 4.3.3 `pipeline.py`

**Purpose**: Main MIND pipeline orchestrating all components.

**Class**: `MIND`

**Constructor Parameters**:
- `llm_model`: LLM identifier (e.g., "gpt-4o", "llama3.3:70b")
- `llm_server`: Backend server URL (for Ollama/vLLM)
- `source_corpus`: Corpus object for source language
- `target_corpus`: Corpus object for target language
- `retrieval_method`: One of ["ANN", "ENN", "TB-ANN", "TB-ENN"]
- `multilingual`: Whether to use multilingual embeddings
- `do_check_entailment`: Enable NLI-based contradiction verification

**Key Method**: `run_pipeline(topics, sample_size, path_save)`

**Algorithm**:
1. For each topic in `topics`:
   - Sample chunks from source corpus
   - For each source chunk:
     - **Generate questions** using LLM
     - Filter bad questions (too long, too short, contains "passage", etc.)
     - For each question:
       - **Generate subqueries** (decompose complex questions)
       - For each subquery:
         - **Retrieve** top-k target chunks using IndexRetriever
         - For each target chunk:
           - **Check relevance** (is target chunk relevant to question?)
           - If relevant:
             - **Generate answer** from source chunk (answer_s)
             - **Generate answer** from target chunk (answer_t)
             - **Check contradiction** between answer_s and answer_t
             - If contradiction detected:
               - (Optional) Verify with NLI model
               - Log discrepancy with label and reason
2. Save results to Parquet

**Design Decision**:
- **Dry-run mode**: Skips LLM calls for testing
- **Caching**: LLM responses are cached to avoid redundant API calls
- **Logging**: Detailed logs for debugging and reproducibility
- **Normalization**: Unicode normalization for robust text comparison

---

### 4.4 `prompter/`

#### 4.4.1 `prompter.py`

**Purpose**: Unified interface for interacting with multiple LLM backends.

**Class**: `Prompter`

**Supported Backends**:
1. **OpenAI API**: GPT models via REST API
2. **Ollama**: Local models via HTTP API
3. **vLLM**: High-throughput inference server
4. **llama.cpp**: Lightweight C++ inference

**Key Method**: `prompt(question, system_prompt_template_path, use_context, temperature, dry_run)`

**Algorithm**:
1. Load system prompt template from file
2. Format template with question (and optional context)
3. Call appropriate backend API
4. Parse response and return text
5. Cache result using `joblib.Memory`

**Design Decision**:
- **Caching**: Responses are cached based on hash of (template, question, model, params)
- **Template-based prompts**: All prompts are stored in `pipeline/prompts/` for easy modification
- **Configurable parameters**: Temperature, seed, max_tokens can be overridden per call
- **Error handling**: Retries on API failures, logs errors

---

### 4.5 `utils/`

#### 4.5.1 `utils.py`

**Purpose**: Shared utility functions.

**Key Functions**:
- `init_logger(config_path, name)`: Initialize logger with file and console handlers
- `load_yaml_config_file(path)`: Load YAML configuration
- `load_prompt(path)`: Load prompt template from text file
- `file_lines(path)`: Count lines in a file (for Mallet output parsing)

---

## 5. Web Application (`app/`)

### 5.1 Architecture Overview

The web application is a **multi-service Flask application** deployed via Docker Compose. It provides a user-friendly interface for:

1. **User Management**: Sign up, login, profile editing
2. **Dataset Management**: Upload, view, download datasets
3. **Preprocessing**: Segmentation, translation, data preparation
4. **Topic Modeling**: Train PLTM models, label topics
5. **Discrepancy Detection**: Run MIND pipeline, visualize results

---

### 5.2 Frontend Service (`app/frontend/`)

**Framework**: Flask + Jinja2 templates

**Key Files**:
- `__init__.py`: App factory, registers blueprints
- `auth.py`: Login, signup, logout routes
- `profile.py`: User profile, dataset upload
- `datasets.py`: Dataset listing and preview
- `preprocessing.py`: Preprocessing UI and task management
- `detection.py`: Discrepancy detection UI
- `views.py`: Home, about pages

**Templates** (`templates/`):
- `base.html`: Base template with navigation
- `home.html`: Landing page
- `login.html`, `sign_up.html`: Authentication forms
- `profile.html`: User profile and dataset upload
- `datasets.html`: Dataset listing
- `preprocessing.html`: Preprocessing controls
- `detection.html`: Topic visualization and discrepancy configuration
- `detection_results.html`: Results table with filtering and editing

**Design Decisions**:
- **Session-based auth**: User sessions stored in filesystem
- **CORS enabled**: Allows cross-origin requests for API calls
- **Cache control**: Disables browser caching for dynamic content
- **Async task management**: Long-running tasks (preprocessing, detection) run in background threads
- **Progress tracking**: Tasks have unique IDs, status checked via polling

---

### 5.3 Backend Service (`app/backend/`)

**Framework**: Flask (REST API)

**Key Files**:
- `main.py`: App initialization, registers blueprints
- `dataset.py`: Dataset upload, listing, deletion
- `preprocessing.py`: Segmentation, translation, data preparation, topic modeling
- `detection.py`: MIND pipeline execution, results retrieval
- `utils.py`: Helper functions (cleanup, aggregation)

**Key Routes**:

#### Dataset Management
- `POST /upload_dataset`: Upload raw or preprocessed dataset
- `GET /get_datasets`: List user's datasets
- `DELETE /delete_dataset`: Delete dataset

#### Preprocessing
- `POST /preprocessing/segmenter`: Run segmentation
- `POST /preprocessing/translator`: Run translation
- `POST /preprocessing/preparer`: Run data preparation
- `POST /preprocessing/topicmodelling`: Train topic model
- `POST /preprocessing/labeltopic`: Label topics
- `GET /preprocessing/status/<step_id>`: Check task status
- `GET /preprocessing/download_data`: Download dataset or model

#### Detection
- `POST /analyse_contradiction`: Run MIND pipeline
- `GET /pipeline_status`: Check pipeline status
- `GET /get_results_mind`: Retrieve discrepancy results
- `POST /update_result_mind`: Update result labels
- `GET /getTopicKeys`: Get topic metadata for visualization
- `POST /doc_representation`: Compute MDS projection for topic visualization

**Design Decisions**:
- **Concurrency control**: Max 2 users can run detection simultaneously (configurable)
- **Process isolation**: Each detection task runs in a separate process
- **Log streaming**: Real-time logs sent to frontend via `StreamForwarder`
- **Ollama server pooling**: Multiple Ollama servers used to avoid conflicts
- **Data persistence**: User data stored in `/data/{email}/` directory structure

---

### 5.4 Auth Service (`app/auth/`)

**Framework**: Flask + SQLAlchemy + PostgreSQL

**Key Files**:
- `app/main.py`: App initialization
- `app/routes.py`: Authentication routes
- `app/models.py`: User model
- `app/database.py`: Database connection

**Key Routes**:
- `POST /auth/signup`: Create new user
- `POST /auth/login`: Authenticate user, return JWT token
- `POST /auth/validate`: Validate JWT token
- `GET /auth/user/<email>`: Get user info

**Database Schema**:

```sql
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    password VARCHAR(255) NOT NULL,  -- bcrypt hashed
    created_at TIMESTAMP DEFAULT NOW()
);
```

**Design Decisions**:
- **JWT tokens**: Stateless authentication
- **bcrypt hashing**: Secure password storage
- **PostgreSQL**: Reliable, ACID-compliant database
- **Health checks**: Docker Compose waits for DB to be ready before starting auth service

---

## 6. Configuration Management

### 6.1 `config/config.yaml`

Central configuration file for the MIND library.

**Sections**:

#### Logger
```yaml
logger:
  dir_logger: data/logs
  console_log: True
  file_log: True
  log_level: INFO
  logger_name: mind
  N_log_keep: 5
```

#### MIND Pipeline
```yaml
mind:
  top_k: 10                    # Number of passages to retrieve
  batch_size: 32               # Batch size for embeddings
  min_clusters: 8              # Min clusters for FAISS
  do_weighting: True           # Enable topic-based weighting
  nprobe_fixed: False          # Dynamic nprobe for FAISS
  cannot_answer_dft: "I cannot answer the question given the context."
  cannot_answer_personal: "I cannot answer the question since the context only contains personal opinions."
  prompts:
    question_generation: src/mind/pipeline/prompts/question_generation.txt
    subquery_generation: src/mind/pipeline/prompts/query_generation.txt
    answer_generation: src/mind/pipeline/prompts/question_answering.txt
    contradiction_checking: src/mind/pipeline/prompts/discrepancy_detection.txt
    relevance_checking: src/mind/pipeline/prompts/relevance_checking.txt
  embedding_models:
    multilingual:
      model: BAAI/bge-m3
      do_norm: True
    monolingual:
      en:
        model: sentence-transformers/all-MiniLM-L6-v2
        do_norm: True
  nli_model_name: potsawee/deberta-v3-large-mnli
```

#### LLM Configuration
```yaml
llm:
  parameters:
    temperature: 0
    top_p: 0.1
    frequency_penalty: 0.0
    random_seed: 1234
    seed: 1234
  gpt:
    available_models: [gpt-4o, gpt-4o-mini, gpt-4-turbo, ...]
    path_api_key: .env
  ollama:
    available_models: [qwen2.5:72b, llama3.3:70b, ...]
    host: http://kumo01.tsc.uc3m.es:11434
  vllm:
    available_models: [Qwen/Qwen3-8B, ...]
    host: http://kumo01.tsc.uc3m.es:6000/v1
```

### 6.2 Environment Variables

#### Frontend (`.env`)
```bash
WEB_APP_KEY=<secret_key>
MAX_CONCURRENT_TASKS=20
MAX_CONCURRENT_TASKS_PER_USER=4
```

#### Backend (`.env`)
```bash
MAX_USERS_DETECTION=2
```

#### Auth (`.env`)
```bash
DATABASE_URL=postgresql://auth_user:auth_pass@db:5432/auth_db
SECRET_KEY=<jwt_secret>
```

#### Root (`.env`)
```bash
OPENAI_API_KEY=<your_openai_key>
```

---

## 7. Coding Conventions and Design Decisions

### 7.1 Python Style

- **PEP 8 compliant**: Standard Python style guide
- **Type hints**: Used in function signatures (e.g., `def segment(path_df: Path, ...)`)
- **Docstrings**: Google-style docstrings for classes and methods
- **Logging**: Extensive use of `logging` module (not `print()`)
- **Error handling**: Try-except blocks with informative error messages

### 7.2 Data Formats

#### Parquet
- **Primary format** for all datasets
- **Compression**: gzip
- **Advantages**: Columnar storage, fast I/O, schema preservation

#### Sparse Matrices (`.npz`)
- Used for document-topic distributions (θ)
- Saves memory (most values are near-zero)

#### JSON
- Configuration files (topic labels, model metadata)

#### Text Files
- Prompt templates (`.txt`)
- Mallet input corpora

### 7.3 Naming Conventions

#### Files
- `snake_case.py` for Python modules
- `PascalCase` for class names
- `snake_case` for functions and variables

#### Columns (DataFrames)
- `chunk_id`: Unique identifier for passages
- `chunk_text`: Passage text
- `full_doc`: Full document text
- `lang`: Language code (EN, ES, DE)
- `lemmas`: Space-separated lemmas
- `top_k`: List of (topic_id, weight) tuples
- `main_topic_thetas`: Primary topic ID

#### Prefixes
- `T_`: Translated passages (e.g., `T_EN_12_3`)
- `id_preproc`: Preprocessing ID (before final ID assignment)

### 7.4 Key Design Decisions

#### 1. **Parquet over CSV**
- **Reason**: Faster I/O, schema preservation, compression
- **Trade-off**: Requires PyArrow dependency

#### 2. **Subprocess for Mallet**
- **Reason**: Mallet is Java-based, no Python bindings
- **Trade-off**: Slower than native Python, requires Java installation

#### 3. **Subprocess for NLPipe**
- **Reason**: Isolates spaCy dependencies, allows custom preprocessing
- **Trade-off**: Slower than in-process calls

#### 4. **Caching LLM Responses**
- **Reason**: Reduces API costs, speeds up repeated experiments
- **Trade-off**: Disk space usage, cache invalidation complexity

#### 5. **Topic-Based Retrieval**
- **Reason**: Improves precision by filtering irrelevant documents
- **Trade-off**: Requires topic model training

#### 6. **Microservices for Web App**
- **Reason**: Separation of concerns, independent scaling
- **Trade-off**: Increased deployment complexity

#### 7. **Background Processes for Long Tasks**
- **Reason**: Prevents HTTP timeouts, allows concurrent users
- **Trade-off**: Requires polling for status updates

#### 8. **Sparse Matrices for θ**
- **Reason**: Most topic weights are near-zero
- **Trade-off**: Slightly slower access than dense arrays

#### 9. **Dynamic Topic Thresholds**
- **Reason**: Adapts to document-specific topic distributions
- **Trade-off**: More complex than fixed thresholds

#### 10. **Multilingual Embeddings (BGE-M3)**
- **Reason**: Supports cross-lingual retrieval without translation
- **Trade-off**: Larger model size, slower inference

---

## 8. Data Flow and Processing Pipeline

### 8.1 End-to-End Workflow

```
┌─────────────────────────────────────────────────────────────────┐
│ Step 1: Data Collection                                         │
│ - Collect loosely-aligned documents (e.g., Wikipedia articles)  │
│ - Format: Parquet with columns [id, text, lang, ...]           │
└─────────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│ Step 2: Segmentation (segmenter.py)                            │
│ - Split documents into passages                                 │
│ - Filter short paragraphs                                       │
│ - Output: segmented.parquet                                     │
└─────────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│ Step 3: Translation (translator.py)                            │
│ - Translate passages to target language                         │
│ - Append translations to DataFrame                              │
│ - Output: translated.parquet                                    │
└─────────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│ Step 4: Data Preparation (data_preparer.py)                    │
│ - Run NLPipe for lemmatization                                  │
│ - Format for Mallet (lemmas column)                             │
│ - Output: prepared.parquet                                      │
└─────────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│ Step 5: Topic Modeling (polylingual_tm.py)                     │
│ - Train PLTM model                                              │
│ - Extract θ (document-topic distributions)                      │
│ - Output: model_folder/ with thetas.npz, topickeys.txt         │
└─────────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│ Step 6: (Optional) Topic Labeling (topic_label.py)             │
│ - Generate human-readable labels for topics                     │
│ - Output: topic_labels.json                                     │
└─────────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│ Step 7: MIND Pipeline (pipeline.py)                            │
│ - Load source and target corpora                                │
│ - Build retrieval indices                                       │
│ - For each topic:                                               │
│   - Generate questions from source passages                     │
│   - Retrieve target passages                                    │
│   - Generate answers                                            │
│   - Detect contradictions                                       │
│ - Output: results.parquet with discrepancy labels               │
└─────────────────────────────────────────────────────────────────┘
```

### 8.2 Data Schema Evolution

#### Input (Raw Corpus)
```
id | text | lang | title | url | ...
```

#### After Segmentation
```
id | id_preproc | text | full_doc | lang | title | url | ...
```

#### After Translation
```
id | id_preproc | text | full_doc | lang | title | url | ...
(original rows)
id | id_preproc | text | full_doc | lang | title | url | ...
(translated rows with T_ prefix in id_preproc)
```

#### After Data Preparation
```
chunk_id | chunk_text | full_doc | lang | lemmas | title | url | ...
```

#### After Topic Modeling
```
chunk_id | chunk_text | full_doc | lang | lemmas | top_k | main_topic_thetas | ...
```

#### After MIND Pipeline
```
topic | source_chunk_id | target_chunk_id | question | source_answer | target_answer | discrepancy_label | reason | ...
```

---

## 9. Deployment

### 9.1 Docker Compose Architecture

**Services**:
1. **frontend**: Flask UI (port 5050)
2. **backend**: Flask API (port 5001)
3. **auth**: Flask auth service (port 5002)
4. **db**: PostgreSQL database (port 5444 → 5432)

**Volumes**:
- `auth_db_data`: Persistent PostgreSQL data
- `backend_data`: User datasets and models

**Networks**:
- Default bridge network for inter-service communication

### 9.2 Deployment Commands

```bash
# Build containers
docker compose build

# Start services
docker compose up -d

# View logs
docker compose logs -f

# Stop services
docker compose down

# Remove volumes (WARNING: deletes data)
docker compose down -v
```

### 9.3 Local Development (without Docker)

```bash
# Clone repository with submodules
git clone --recurse-submodules https://github.com/lcalvobartolome/mind.git
cd mind

# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# Create virtual environment
uv venv .venv
source .venv/bin/activate

# Install dependencies
uv pip install -e .

# Verify installation
python -c "import mind; print(mind.__version__)"
```

### 9.4 Production Considerations

1. **Environment Variables**: Store secrets in `.env` files (not in version control)
2. **Database Backups**: Regular backups of PostgreSQL data
3. **Log Rotation**: Limit log file sizes (`N_log_keep: 5`)
4. **Concurrency Limits**: Adjust `MAX_USERS_DETECTION` based on server resources
5. **LLM API Keys**: Secure storage, rate limiting
6. **HTTPS**: Use reverse proxy (nginx) for SSL termination
7. **Monitoring**: Track API usage, error rates, task completion times

---

## Appendix A: File Structure

```
mind/
├── src/mind/                      # Core library
│   ├── corpus_building/
│   │   ├── segmenter.py
│   │   ├── translator.py
│   │   └── data_preparer.py
│   ├── topic_modeling/
│   │   ├── polylingual_tm.py
│   │   ├── topic_label.py
│   │   ├── lda_tm.py
│   │   ├── classifier.py
│   │   ├── cleaning.py
│   │   ├── hierarchical/
│   │   └── stops/
│   ├── pipeline/
│   │   ├── pipeline.py
│   │   ├── corpus.py
│   │   ├── retriever.py
│   │   ├── utils.py
│   │   └── prompts/
│   ├── prompter/
│   │   └── prompter.py
│   └── utils/
│       └── utils.py
├── app/                           # Web application
│   ├── frontend/
│   │   ├── __init__.py
│   │   ├── main.py
│   │   ├── auth.py
│   │   ├── profile.py
│   │   ├── datasets.py
│   │   ├── preprocessing.py
│   │   ├── detection.py
│   │   ├── views.py
│   │   ├── templates/
│   │   └── static/
│   ├── backend/
│   │   ├── main.py
│   │   ├── dataset.py
│   │   ├── preprocessing.py
│   │   ├── detection.py
│   │   └── utils.py
│   └── auth/
│       └── app/
│           ├── main.py
│           ├── routes.py
│           ├── models.py
│           └── database.py
├── config/
│   └── config.yaml
├── externals/
│   ├── Mallet-202108/
│   └── NLPipe/
├── ablation/                      # Research experiments
├── use_cases/                     # Example workflows
├── notebooks/                     # Jupyter notebooks
├── bash_scripts/                  # Automation scripts
├── docker-compose.yml
├── pyproject.toml
└── requirements.txt
```

---

## Appendix B: Key Algorithms

### B.1 Dynamic Topic Threshold Calculation

```python
def dynamic_thresholds(mat, poly_degree=3, smoothing_window=5):
    """
    Compute per-document topic thresholds using knee detection.
    
    Algorithm:
    1. Sort topic weights in descending order
    2. Apply polynomial smoothing
    3. Detect "knee" point (elbow in curve)
    4. Set threshold at knee value
    """
    thresholds = []
    for row in mat:
        sorted_weights = np.sort(row)[::-1]
        smoothed = uniform_filter1d(sorted_weights, size=smoothing_window)
        
        knee = KneeLocator(
            range(len(smoothed)), 
            smoothed, 
            curve='convex', 
            direction='decreasing',
            polynomial_degree=poly_degree
        )
        
        threshold = smoothed[knee.knee] if knee.knee else 0.0
        thresholds.append(threshold)
    
    return np.array(thresholds)
```

### B.2 Question Filtering

```python
def _filter_bad_questions(questions: List[str]) -> List[str]:
    """
    Remove low-quality questions.
    
    Criteria:
    - Too short (< 10 chars)
    - Too long (> 200 chars)
    - Contains "passage", "text", "document"
    - Starts with participle ("Based on", "According to")
    - Contains personal pronouns ("I", "you", "we")
    """
    filtered = []
    for q in questions:
        if len(q) < 10 or len(q) > 200:
            continue
        if any(word in q.lower() for word in ["passage", "text", "document"]):
            continue
        if re.match(r"^(Based on|According to|As mentioned)", q):
            continue
        if any(word in q.lower() for word in [" i ", " you ", " we "]):
            continue
        filtered.append(q)
    return filtered
```

---

## Appendix C: Glossary

| Term | Definition |
|------|------------|
| **PLTM** | Polylingual Topic Model - LDA variant for multilingual corpora |
| **θ (theta)** | Document-topic distribution (probability vector) |
| **Chunk** | A passage or segment of text (typically 1-3 paragraphs) |
| **Anchor Language** | Source language for comparison (e.g., English) |
| **Comparison Language** | Target language for comparison (e.g., Spanish) |
| **TB-ENN** | Topic-Based Exact Nearest Neighbor retrieval |
| **NLI** | Natural Language Inference (entailment detection) |
| **Lemma** | Base form of a word (e.g., "running" → "run") |
| **Discrepancy** | Semantic contradiction between source and target answers |
| **ROSIE-MIND** | Annotated dataset for evaluating MIND pipeline |

---

**End of Technical Documentation**
