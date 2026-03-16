# Gemini API Integration Plan

> **Purpose**: This document provides a comprehensive, in-depth guide for integrating Google Gemini API support into the MIND project. It is designed to be read by implementing agents and serves as the authoritative specification for this feature.

## Table of Contents

1. [Overview](#overview)
2. [Current Architecture Analysis](#current-architecture-analysis)
3. [Gemini API Specifications](#gemini-api-specifications)
4. [Implementation Changes](#implementation-changes)
5. [Configuration Schema](#configuration-schema)
6. [API Key & Credentials Management](#api-key--credentials-management)
7. [Backwards Compatibility Guarantees](#backwards-compatibility-guarantees)
8. [Batch Processing Support](#batch-processing-support)
9. [Error Handling & Rate Limiting](#error-handling--rate-limiting)
10. [Testing Strategy](#testing-strategy)
11. [Rollout Checklist](#rollout-checklist)

---

## Overview

### Objective

Add Google Gemini API as a new backend provider to the existing `Prompter` class, enabling users to use Gemini models (e.g., `gemini-2.0-flash`, `gemini-1.5-pro`) for all LLM-based operations in the MIND pipeline.

### Constraints

- **Backwards Compatibility**: All existing backends (OpenAI, Ollama, vLLM, llama_cpp) must continue to work unchanged
- **Modular Design**: Gemini integration follows the same pattern as existing backends
- **No Technology Changes**: Use only existing dependencies plus the official Google Gemini library (`google-genai`)
- **Prompt Compatibility**: Existing prompt templates (`.txt` files) must work without modification

### Key Files Affected

| File | Purpose |
|------|---------|
| `src/mind/prompter/prompter.py` | Add Gemini backend handler |
| `config/config.yaml` | Add Gemini configuration section |
| `requirements.txt` | Add `google-genai` dependency |
| `.env` (user-created) | Store Gemini API key |

---

## Current Architecture Analysis

### Backend Selection Pattern

The `Prompter` class uses a model-type-based backend selection pattern in `__init__`:

```python
# Current pattern (lines 79-125 of prompter.py)
if model_type in self.GPT_MODELS:
    self.backend = "openai"
elif model_type in self.OLLAMA_MODELS:
    self.backend = "ollama"
elif model_type in self.VLLM_MODELS:
    self.backend = "vllm"
elif model_type == "llama_cpp":
    self.backend = "llama_cpp"
else:
    raise ValueError("Unsupported model_type specified.")
```

### API Call Delegation Pattern

Each backend has a corresponding static method:

- `_call_openai_api_vllm()` - Handles OpenAI and vLLM
- `_call_ollama_api()` - Handles Ollama
- `_call_llama_cpp_api()` - Handles llama_cpp

The cached implementation in `_cached_prompt_impl()` (lines 127-181) routes to the appropriate handler based on `backend` string.

### Configuration Structure

LLM configuration in `config/config.yaml` follows this pattern:

```yaml
llm:
  parameters:
    temperature: 0
    top_p: 0.1
    frequency_penalty: 0.0
    random_seed: 1234
    seed: 1234
  <backend_name>:
    available_models: { ... }
    host: <endpoint>  # for self-hosted
    path_api_key: <env_file>  # for API-based
```

### Prompt Loading

Prompts are loaded from `.txt` files and passed to the LLM as:
- **System prompt**: The template loaded from file
- **User prompt**: The formatted question/content

---

## Gemini API Specifications

### Official Library

**Library**: `google-genai` (Google AI Python SDK)

**Installation**: 
```bash
pip install google-genai
```

**Documentation**: https://googleapis.github.io/python-genai/

### API Endpoints

| Endpoint | URL |
|----------|-----|
| Google AI Studio | `generativelanguage.googleapis.com` (default) |
| Vertex AI | `{LOCATION}-aiplatform.googleapis.com` |

The implementation will support both endpoints via configuration.

### Available Models

| Model | Description |
|-------|-------------|
| `gemini-2.0-flash` | Fast, efficient model for most tasks |
| `gemini-2.0-flash-lite` | Lightweight variant |
| `gemini-1.5-pro` | High capability model |
| `gemini-1.5-flash` | Balanced speed/capability |

### API Request Structure

```python
from google import genai
from google.genai import types

client = genai.Client(api_key="YOUR_API_KEY")

response = client.models.generate_content(
    model="gemini-2.0-flash",
    contents="Your prompt here",
    config=types.GenerateContentConfig(
        system_instruction="System prompt here",
        temperature=0.0,
        top_p=0.1,
        max_output_tokens=1000,
    ),
)
result = response.text
```

### Response Structure

```python
# Successful response
response.text  # The generated text content
response.candidates[0].finish_reason  # STOP, MAX_TOKENS, SAFETY, etc.

# For token-level logprobs (if enabled)
response.candidates[0].logprobs_result  # May not be available for all models
```

> [!IMPORTANT]
> Gemini API does not provide token-level logprobs in the same way as OpenAI. The implementation should return `None` for logprobs when using the Gemini backend.

---

## Implementation Changes

### 1. Update `requirements.txt`

Add the Google Gemini library:

```diff
# requirements.txt
ollama==0.5.3
openai==1.106.1
+google-genai>=1.0.0
pandas==2.3.2
```

---

### 2. Update `config/config.yaml`

Add Gemini configuration section under `llm`:

```yaml
llm:
  parameters:
    temperature: 0
    top_p: 0.1
    frequency_penalty: 0.0
    random_seed: 1234
    seed: 1234
  
  # ... existing gpt, ollama, vllm, llama_cpp sections ...

  gemini:
    available_models:
      - "gemini-2.0-flash"
      - "gemini-2.0-flash-lite"
      - "gemini-1.5-pro"
      - "gemini-1.5-flash"
      - "gemini-1.5-flash-8b"
    path_api_key: .env
    # Optional: For Vertex AI endpoint
    # vertex_project: your-gcp-project-id
    # vertex_location: us-central1
```

**Configuration Parameters**:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `available_models` | list | Required | List of allowed Gemini model names |
| `path_api_key` | string | `.env` | Path to file containing `GOOGLE_API_KEY` |
| `vertex_project` | string | null | GCP project ID (for Vertex AI only) |
| `vertex_location` | string | null | GCP region (for Vertex AI only) |

---

### 3. Update `.env` File Format

Document the expected environment variable:

```bash
# .env file
OPENAI_API_KEY=sk-...         # Existing OpenAI key
GOOGLE_API_KEY=AIza...        # New: Google Gemini API key
# Optional for Vertex AI:
# GOOGLE_CLOUD_PROJECT=your-project-id
```

> [!NOTE]
> The `GOOGLE_API_KEY` is obtained from Google AI Studio (https://aistudio.google.com/apikey). For Vertex AI, use service account authentication instead.

---

### 4. Modify `src/mind/prompter/prompter.py`

#### 4.1 Add Imports

At the top of the file (after line 14):

```python
# Existing imports
from ollama import Client
from openai import OpenAI

# Add Gemini imports
try:
    from google import genai
    from google.genai import types as genai_types
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
```

#### 4.2 Load Gemini Models in `__init__`

Inside `__init__` (after line 51, where `self.VLLM_MODELS` is set):

```python
self.GEMINI_MODELS = self.config.get(
    "gemini", {}).get("available_models", [])
# Convert to set for consistent lookup
if isinstance(self.GEMINI_MODELS, list):
    self.GEMINI_MODELS = set(self.GEMINI_MODELS)
```

#### 4.3 Add Gemini Backend Initialization

Add a new `elif` branch in the backend selection logic (after vLLM, before the `else` on line 124):

```python
elif model_type in self.GEMINI_MODELS:
    if not GEMINI_AVAILABLE:
        raise ImportError(
            "google-genai package is required for Gemini models. "
            "Install with: pip install google-genai"
        )
    
    load_dotenv(self.config.get("gemini", {}).get("path_api_key", ".env"))
    gemini_api_key = os.getenv("GOOGLE_API_KEY")
    
    if gemini_api_key is None:
        raise ValueError(
            "GOOGLE_API_KEY not found. Please set it in the .env file."
        )
    
    # Check for Vertex AI configuration
    vertex_project = self.config.get("gemini", {}).get("vertex_project")
    vertex_location = self.config.get("gemini", {}).get("vertex_location")
    
    if vertex_project and vertex_location:
        # Vertex AI endpoint
        Prompter.gemini_client = genai.Client(
            vertexai=True,
            project=vertex_project,
            location=vertex_location,
        )
        self._logger.info(
            f"Using Vertex AI with project: {vertex_project}, location: {vertex_location}"
        )
    else:
        # Google AI Studio endpoint (default)
        Prompter.gemini_client = genai.Client(api_key=gemini_api_key)
        self._logger.info(f"Using Google AI Studio with model: {model_type}")
    
    self.backend = "gemini"
```

#### 4.4 Handle max_tokens Parameter

In the `__init__` method where `max_tokens` is handled (around line 64-77), add Gemini handling:

```python
# After the existing elif for OLLAMA_MODELS (line 73-76):
elif model_type in self.GEMINI_MODELS:
    self.params["max_output_tokens"] = max_tokens
    self._logger.info(f"Setting max_output_tokens to: {max_tokens}")
```

#### 4.5 Add Gemini API Call Handler

Create a new static method (add after `_call_llama_cpp_api`, around line 271):

```python
@staticmethod
def _call_gemini_api(template, question, model_type, params):
    """Handles the Google Gemini API call.
    
    Parameters
    ----------
    template : str or None
        The system prompt template.
    question : str
        The user question/content.
    model_type : str
        The Gemini model name (e.g., 'gemini-2.0-flash').
    params : dict
        Generation parameters.
        
    Returns
    -------
    tuple
        (result_text, logprobs) where logprobs is always None for Gemini.
    """
    if Prompter.gemini_client is None:
        raise ValueError(
            "Gemini client is not initialized. Check the model type configuration."
        )
    
    # Build generation config
    gen_config = genai_types.GenerateContentConfig(
        temperature=params.get("temperature", 0),
        top_p=params.get("top_p", 0.1),
        max_output_tokens=params.get("max_output_tokens", 1000),
    )
    
    # Add system instruction if template is provided
    if template is not None:
        gen_config.system_instruction = template
    
    # Make API call
    response = Prompter.gemini_client.models.generate_content(
        model=model_type,
        contents=question,
        config=gen_config,
    )
    
    result = response.text
    logprobs = None  # Gemini does not provide logprobs in the same format
    
    return result, logprobs
```

#### 4.6 Update `_cached_prompt_impl`

In the `_cached_prompt_impl` method (around line 127), add routing to the Gemini handler:

```python
# After the elif for llama_cpp (around line 158-164):
elif backend == "gemini":
    result, logprobs = Prompter._call_gemini_api(
        template=template,
        question=question,
        model_type=model_type,
        params=dict(params),
    )
```

#### 4.7 Initialize Class Variable

Add at class level (after line 25, where `Prompter` class is defined):

```python
class Prompter:
    # Class-level client instances (initialized on first use)
    ollama_client = None
    gemini_client = None  # Add this line
```

---

### 5. Update Other Files Using LLM

#### 5.1 `src/mind/topic_modeling/topic_label.py`

This file already uses `Prompter` correctly via dependency injection. **No changes required.**

#### 5.2 `src/mind/pipeline/pipeline.py`

This file already uses `Prompter` correctly via dependency injection. **No changes required.**

---

## Configuration Schema

### Complete Updated `config.yaml` LLM Section

```yaml
llm:
  parameters:
    temperature: 0
    top_p: 0.1
    frequency_penalty: 0.0
    random_seed: 1234
    seed: 1234
    
  gpt:
    available_models:
      - "gpt-4o-2024-08-06"
      - "gpt-4o-mini-2024-07-18"
      - "chatgpt-4o-latest"
      - "gpt-4-turbo"
      - "gpt-4"
      - "gpt-3.5-turbo"
      - "gpt-4o-mini"
      - "gpt-4o"
    path_api_key: .env
    
  ollama:
    available_models:
      - "qwen2.5:72b"
      - "llama3.2"
      - "llama3.1:8b-instruct-q8_0"
      - "qwen:32b"
      - "llama3.3:70b"
    host: http://kumo01.tsc.uc3m.es:11434
    
  vllm:
    available_models:
      - "Qwen/Qwen3-8B"
      - "Qwen/Qwen3-0.6B"
      - "meta-llama/Meta-Llama-3-8B-Instruct"
    host: http://kumo01.tsc.uc3m.es:6000/v1
    
  llama_cpp:
    host: http://kumo01:11435/v1/chat/completions
    
  # NEW: Google Gemini configuration
  gemini:
    available_models:
      - "gemini-2.0-flash"
      - "gemini-2.0-flash-lite"
      - "gemini-1.5-pro"
      - "gemini-1.5-flash"
      - "gemini-1.5-flash-8b"
    path_api_key: .env
    # Uncomment for Vertex AI:
    # vertex_project: your-gcp-project-id
    # vertex_location: us-central1
```

---

## API Key & Credentials Management

### Google AI Studio (Recommended for Development)

1. **Obtain API Key**:
   - Visit https://aistudio.google.com/apikey
   - Create a new API key
   - Copy the key (format: `AIza...`)

2. **Store in `.env` file**:
   ```bash
   GOOGLE_API_KEY=AIzaSyB...your-key-here
   ```

3. **Update `.gitignore`** (if not already present):
   ```
   .env
   ```

### Vertex AI (Recommended for Production)

1. **Set up GCP Project**:
   - Enable the Vertex AI API
   - Create a service account with Vertex AI User role

2. **Configure in `config.yaml`**:
   ```yaml
   gemini:
     vertex_project: your-gcp-project-id
     vertex_location: us-central1
   ```

3. **Authenticate**:
   ```bash
   gcloud auth application-default login
   ```

---

## Backwards Compatibility Guarantees

### Guaranteed Behaviors

| Aspect | Guarantee |
|--------|-----------|
| Existing configurations | All existing config files work without modification |
| OpenAI backend | Unchanged behavior and API |
| Ollama backend | Unchanged behavior and API |
| vLLM backend | Unchanged behavior and API |
| llama_cpp backend | Unchanged behavior and API |
| Prompt templates | All `.txt` prompt files work with Gemini |
| Caching | Gemini responses are cached identically to other backends |
| Batch processing | `prompt_batch()` works with Gemini |

### Expected Differences

| Aspect | Difference |
|--------|------------|
| Logprobs | Gemini returns `None` for logprobs (not supported in same format) |
| Context | Gemini does not support Ollama-style context passing |

### Migration Path

Users can switch to Gemini by simply:

1. Adding `google-genai` to their environment
2. Adding `GOOGLE_API_KEY` to `.env`
3. Changing `llm_model` parameter to a Gemini model name

No code changes required in application code.

---

## Batch Processing Support

### OPT-010 Compatibility

The existing `prompt_batch()` method (lines 327-391) works with Gemini out of the box because it internally calls `prompt()`, which routes to the correct backend handler.

```python
# This existing code works for Gemini automatically:
def prompt_batch(self, questions: List[str], ...):
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_question = {
            executor.submit(process_single, q): q for q in questions
        }
        # ... collection logic
```

### Rate Limiting Considerations

Google Gemini has the following rate limits (as of 2024):

| Plan | RPM (Requests/Minute) | TPM (Tokens/Minute) |
|------|----------------------|---------------------|
| Free tier | 15 | 1,000,000 |
| Pay-as-you-go | 1,000+ | 4,000,000+ |

> [!WARNING]
> For batch processing with Gemini, consider reducing `max_workers` to 4-8 if using the free tier to avoid rate limit errors.

---

## Error Handling & Rate Limiting

### Recommended Error Handling

Add exception handling in `_call_gemini_api`:

```python
@staticmethod
def _call_gemini_api(template, question, model_type, params):
    """Handles the Google Gemini API call."""
    if Prompter.gemini_client is None:
        raise ValueError(
            "Gemini client is not initialized. Check the model type configuration."
        )
    
    try:
        gen_config = genai_types.GenerateContentConfig(
            temperature=params.get("temperature", 0),
            top_p=params.get("top_p", 0.1),
            max_output_tokens=params.get("max_output_tokens", 1000),
        )
        
        if template is not None:
            gen_config.system_instruction = template
        
        response = Prompter.gemini_client.models.generate_content(
            model=model_type,
            contents=question,
            config=gen_config,
        )
        
        result = response.text
        logprobs = None
        
        return result, logprobs
        
    except Exception as e:
        # Handle Gemini-specific errors
        error_msg = str(e)
        
        if "RESOURCE_EXHAUSTED" in error_msg or "429" in error_msg:
            raise RuntimeError(
                f"Gemini rate limit exceeded. Consider reducing batch size. Error: {e}"
            )
        elif "PERMISSION_DENIED" in error_msg or "403" in error_msg:
            raise RuntimeError(
                f"Gemini API key invalid or lacks permission. Check GOOGLE_API_KEY. Error: {e}"
            )
        elif "INVALID_ARGUMENT" in error_msg or "400" in error_msg:
            raise RuntimeError(
                f"Invalid request to Gemini API. Check model name and parameters. Error: {e}"
            )
        else:
            raise RuntimeError(f"Gemini API error: {e}")
```

---

## Testing Strategy

### Manual Testing Procedure

Since the project does not have a formal test suite for the prompter, testing should be performed manually:

#### Test 1: Basic Gemini Call

```python
# Create a file: test_gemini_integration.py
from pathlib import Path
from mind.prompter.prompter import Prompter

# Initialize with Gemini model
prompter = Prompter(
    model_type="gemini-2.0-flash",
    config_path=Path("config/config.yaml"),
)

# Test basic prompt
result, logprobs = prompter.prompt(
    question="What is 2 + 2?",
    system_prompt_template_path=None,
)

print(f"Result: {result}")
print(f"Logprobs: {logprobs}")  # Should be None for Gemini
assert result is not None
assert "4" in result or "four" in result.lower()
print("✓ Basic Gemini call works!")
```

#### Test 2: Gemini with System Prompt

```python
# Test with a system prompt template
result, _ = prompter.prompt(
    question="Explain quantum computing in one sentence.",
    system_prompt_template_path="src/mind/pipeline/prompts/question_answering.txt",
)
print(f"Result with system prompt: {result}")
assert result is not None
print("✓ Gemini works with system prompts!")
```

#### Test 3: Batch Processing

```python
# Test batch processing
questions = [
    "Is the sky blue?",
    "Is water wet?",
    "Is fire cold?",
]

results = prompter.prompt_batch(questions, max_workers=2)
print(f"Batch results: {results}")
assert len(results) == 3
print("✓ Batch processing works!")
```

#### Test 4: Backwards Compatibility

```python
# Verify existing backends still work
prompter_openai = Prompter(
    model_type="gpt-4o-mini",
    config_path=Path("config/config.yaml"),
)
assert prompter_openai.backend == "openai"
print("✓ OpenAI backend still works!")
```

### Running Tests

```bash
cd /home/alonso/Projects/Mind-Industry
python -m test_gemini_integration
```

---

## Rollout Checklist

### Pre-Implementation

- [ ] Verify user has Google AI Studio API key or Vertex AI access
- [ ] Confirm `google-genai` can be installed in the environment

### Implementation Steps

1. [ ] Add `google-genai>=1.0.0` to `requirements.txt`
2. [ ] Run `pip install -r requirements.txt`
3. [ ] Add Gemini section to `config/config.yaml`
4. [ ] Add `GOOGLE_API_KEY` to `.env` file
5. [ ] Update `src/mind/prompter/prompter.py`:
   - [ ] Add Gemini imports with graceful fallback
   - [ ] Add `gemini_client` class variable
   - [ ] Load `GEMINI_MODELS` from config
   - [ ] Add Gemini backend initialization in `__init__`
   - [ ] Add `max_output_tokens` handling for Gemini
   - [ ] Add `_call_gemini_api` static method
   - [ ] Update `_cached_prompt_impl` to route to Gemini handler

### Post-Implementation Verification

- [ ] Run manual test with Gemini model
- [ ] Verify existing OpenAI models still work
- [ ] Verify existing Ollama models still work
- [ ] Test batch processing with Gemini
- [ ] Verify caching works with Gemini

---

## Summary of Changes

| File | Change Type | Lines Changed |
|------|-------------|---------------|
| `requirements.txt` | Add dependency | +1 line |
| `config/config.yaml` | Add gemini section | +12 lines |
| `src/mind/prompter/prompter.py` | Add Gemini backend | ~80 lines |

Total estimated changes: **~95 lines of code**

---

## References

- [Google Gemini API Documentation](https://ai.google.dev/gemini-api/docs)
- [google-genai Python SDK](https://googleapis.github.io/python-genai/)
- [Vertex AI Gemini](https://cloud.google.com/vertex-ai/generative-ai/docs/model-reference/gemini)
