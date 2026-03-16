# Kumo & LLM Refactoring Guide

## Overview
This document tracks the current locations of hardcoded `Kumo` host URLs within the Mind-Industry project and identifies all points where LLMs are invoked to perform tasks. The goal is to facilitate a future refactoring effort to centralize the LLM backend configuration and abstract away environment-specific URLs from the application logic.

---

## Part 1: Hardcoded `Kumo` Instances

The following files contain hardcoded references to instances of `Kumo` (e.g., `kumo01`, `kumo02`, `kumo`, and their respective IPs/ports):

### Source Code
- **`src/mind/prompter/prompter.py`**
  - Line 116: `("host", "http://kumo01.tsc.uc3m.es:11434")`
  - Line 140: `("host", "http://kumo01:11435/v1/chat/completions")`
  - Line 314: `def _call_llama_cpp_api(..., llama_cpp_host="http://kumo01:11435/v1/chat/completions"):`
- **`app/backend/detection.py`**
  - Lines 27-28: `"kumo01": "http://kumo01.tsc.uc3m.es:11434", "kumo02": "http://kumo02.tsc.uc3m.es:11434"`
- **`app/backend/preprocessing.py`**
  - Line 16: `"kumo02": "http://kumo02.tsc.uc3m.es:11434"`

### Configuration Files
- **`config/config.yaml`**
  - Line 133 & 140 & 142: `host: http://kumo01...` implementations for Ollama, vLLM, and Llama.cpp.
- **`app/config/config.yaml`**
  - Line 135 & 142 & 144: `host: http://kumo...` and `http://kumo02...` for various LLM backends.

### Frontend Code (Templates and JS)
- **`app/frontend/templates/detection.html`**: Line 491 check for `kumo02`.
- **`app/frontend/templates/preprocessing.html`**: Line 302 check for `kumo02`.
- **`app/frontend/static/js/detection.js`**: Line 1190 Toast message text.
- **`app/frontend/static/js/preprocessing.js`**: Line 350 Toast message text.

### Scripts
- **`bash_scripts/run_en_de.sh`** & **`bash_scripts/run_rosie2.sh`**: `LLM_SERVER="http://kumo02.tsc.uc3m.es:11434"`
- **`aux_scripts/create_dplace_dtset.py`**: Line 51 `ollama_host="http://kumo01.tsc.uc3m.es:11434"`
- **`aux_scripts/create_fever_dtset.py`**: Line 13 `ollama_host="http://kumo01.tsc.uc3m.es:11434"`

### Documentation
- `docs/knowledge/technical-documentation.md`
- `docs/implementation_artifacts/gemini-api-integration-plan.md`

---

## Part 2: Instances of LLM Orchestration & Tasks

The project uses a central wrapper, `Prompter` (`src/mind/prompter/prompter.py`), to interface with LLMs via its `prompt()` and `prompt_batch()` methods. The orchestrations utilizing this wrapper to perform intelligent tasks are located in the following areas:

### Core Pipeline (`src/mind/pipeline/pipeline.py`)
This file coordinates the core intelligent processing. All of the following sub-components initialize a `Prompter` class with their respective prompt template files defined in `config.yaml`:
- `QuestionGeneration`
- `SubqueryGeneration`
- `AnswerGeneration`
- `ContradictionChecking`
- `RelevanceChecking`

### Topic Labeling (`src/mind/topic_modeling/topic_label.py`)
- The `TopicLabeler` uses `Prompter` to generate semantic labels for clusters of documents.

### Auxiliary Experimentation and Orchestration Scripts
- **`aux_scripts/create_dplace_dtset.py`** & **`aux_scripts/create_fever_dtset.py`**: Call `Prompter` directly to generate training/testing datasets based on existing corpuses.
- **`use_cases/climate_fever/transform.py`**: Interacts with `Prompter` to formulate verification responses against climate claims.
- **`aux_scripts/profiling/gemini_real_test.py`**: Used for testing the integration of the Gemini API wrapper logic in `Prompter`.

### Recommended Refactoring Strategy
1. **Remove Hardcoded Default kwargs:** Strip the hardcoded default URLs from `Prompter` methods and arguments in `src/mind/prompter/prompter.py`.
2. **Environment Substitution:** Replace hardcoded `config.yaml` values with substitution strings (`${LLM_HOST}`) parsed via the loading mechanism.
3. **Backend Injection:** Update `app/backend/detection.py` and frontend UI logic to stop assuming `kumo0X` names and instead fetch available hosts from the application state or environment configurations.
