# MIND Project - Quick Wins Implementation Guide

> **Document Version:** 2.1  
> **Last Updated:** 2026-02-07  
> **Target Audience:** Developers implementing quick wins  
> **Focus:** CPU-only optimizations (no GPU required)

---

## Table of Contents

1. [Overview](#1-overview)
2. [Implementation Status](#2-implementation-status)
3. [Next Quick Wins](#3-next-quick-wins)
4. [Testing & Verification](#4-testing--verification)
5. [Rollout Checklist](#5-rollout-checklist)

---

## 1. Overview

This guide provides a streamlined workflow for implementing CPU-based quick win optimizations. For detailed code specifications, see the [Optimization Guide Appendix A](./optimization-guide.md#appendix-a-implementation-specifications).

### Completed Optimizations

| Optimization | Status | Verified Performance |
|--------------|--------|---------------------|
| **OPT-001: Vectorized Segmentation** | ✅ COMPLETE | 16,351 docs/sec |
| **OPT-002: Batched Embedding Queries** | ✅ COMPLETE | 3-5x speedup (batch) |
| **OPT-003: Chunked DataFrame Loading** | ✅ COMPLETE | 40-60% RAM reduction |
| **OPT-004: Async Checkpoint Writes** | ✅ COMPLETE | 99.9% blocking reduction |
| **OPT-008: Vectorized Sentence Splitting** | ✅ COMPLETE | 13,396 sent/sec (6x speedup) |

### Prerequisites

- Python 3.12+ environment
- All existing project dependencies installed
- Access to `.venv` virtual environment
- Test corpus data (generate with `aux_scripts/profiling/data_generator.py`)

---

### Week 2 (COMPLETED ✓)

- ✅ **OPT-002**: Batched Embedding Queries
  - **File**: `src/mind/pipeline/retriever.py`
  - **Methods**: `encode_queries()`, `_retrieve_enn_with_embedding()`, `_retrieve_topic_with_embedding()`
  - **Impact**: 3-5x speedup for batch retrieval
  - **Usage**: Opt-in API for callers needing batch embedding

- ✅ **OPT-003**: Chunked DataFrame Loading
  - **File**: `src/mind/pipeline/corpus.py`
  - **Methods**: `from_parquet_lazy()`, `chunks_with_topic_lazy()`
  - **Impact**: 40-60% RAM reduction
  - **Usage**: Opt-in alternative to `from_parquet_and_thetas()`

- ✅ **OPT-005**: Zstd Compression
  - **Status**: Already implemented in config system
  - **Verification**: Check `config/config.yaml` optimization settings

### Enabling OPT-002 & OPT-003 via Config

Optimizations are controlled via `config/config.yaml` optimization profiles:

```yaml
optimization:
  profile: balanced  # or memory_optimized, speed_optimized
  
  profiles:
    balanced:
      batched_embeddings: true   # OPT-002: Batch encode queries
      lazy_corpus_loading: false # OPT-003: Lazy Parquet loading
      chunk_size: 10000          # Batch size for lazy loading
      
    memory_optimized:
      batched_embeddings: true   # OPT-002
      lazy_corpus_loading: true  # OPT-003: Enabled for memory savings
      chunk_size: 5000
```

**Integration Points:**
| Optimization | File | Config Key | Behavior |
|--------------|------|------------|----------|
| OPT-002 | `retriever.py` | `batched_embeddings` | Enables `encode_queries()` method; logged at init |
| OPT-003 | `corpus.py` | `lazy_corpus_loading` | Auto-delegates `from_parquet_and_thetas()` → `from_parquet_lazy()` |

**Switching Profiles:**
- `balanced`: Standard mode, batched embeddings ON, lazy loading OFF
- `memory_optimized`: Both ON for 40-60% RAM reduction
- `speed_optimized`: Batched embeddings ON, lazy loading OFF for throughput

---

## 3. Next Quick Wins

### Recommended Implementation Order

```
Week 3 (Medium Priority):
├── OPT-010: Batched LLM Calls
└── OPT-006: Lazy Theta Loading
```

### OPT-010: Batched LLM Calls

**Impact**: Reduce LLM API overhead  
**Effort**: Medium  
**Implementation**: Batch multiple prompts for efficiency

---

### OPT-006: Lazy Theta Loading

**Impact**: Reduce memory for topic distributions  
**Effort**: Medium  
**Implementation**: Load thetas on-demand during iteration

---

## 4. Testing & Verification

### 4.1 Run Profiling Tests

```bash
# Activate virtual environment
source .venv/bin/activate

# Run quick wins profiler
python -m aux_scripts.profiling.quick_wins_profiler --all

# Or run specific optimization tests
python -m aux_scripts.profiling.quick_wins_profiler --opt OPT-001
python -m aux_scripts.profiling.quick_wins_profiler --opt OPT-004
python -m aux_scripts.profiling.quick_wins_profiler --opt OPT-008
```

### 4.2 Integration Tests

Create a test script to verify end-to-end functionality:

```python
import sys
sys.path.insert(0, 'src')
import pandas as pd
import tempfile
from pathlib import Path

# Test OPT-001: Segmenter
from mind.corpus_building.segmenter import Segmenter
seg = Segmenter()
# ... test with sample data

# Test OPT-004: AsyncCheckpointer
from mind.pipeline.pipeline import AsyncCheckpointer
checkpointer = AsyncCheckpointer()
# ... test async writes

# Test OPT-008: Translator
from mind.corpus_building.translator import Translator
trans = Translator()
# ... test sentence splitting
```

### 4.3 Regression Testing

Ensure optimizations don't break existing functionality:

1. **Output Consistency**: Compare output DataFrames before/after optimization
2. **Column Integrity**: Verify all expected columns present
3. **ID Format**: Check `id_preproc` follows expected pattern
4. **Data Integrity**: Validate no data loss during transformations

---

## 5. Rollout Checklist

### Pre-Implementation

- [ ] Review [optimization-guide.md](./optimization-guide.md) for strategic context
- [ ] Check [Appendix A](./optimization-guide.md#appendix-a-implementation-specifications) for detailed specs
- [ ] Ensure `.venv` environment is active
- [ ] Backup current codebase

### During Implementation

- [ ] Follow code specifications exactly as documented
- [ ] Add logging statements for performance monitoring
- [ ] Update configuration files if needed
- [ ] Write unit tests for new functionality

### Post-Implementation

- [ ] Run profiling tests to verify improvements
- [ ] Run regression tests to ensure no breakage
- [ ] Update documentation with actual results
- [ ] Commit changes with descriptive message

### Verification

- [ ] Performance metrics match expected ranges
- [ ] No errors in test suite
- [ ] Memory usage within acceptable limits
- [ ] Output format unchanged

---

## Additional Resources

- **Main Guide**: [optimization-guide.md](./optimization-guide.md) - Strategic overview and profiling results
- **Detailed Specs**: [optimization-guide.md Appendix A](./optimization-guide.md#appendix-a-implementation-specifications) - Code-level implementation details
- **Profiling Suite**: `aux_scripts/profiling/` - Performance testing tools
- **Configuration**: `config/config.yaml` - Optimization settings

---

**For detailed implementation specifications, always refer to [optimization-guide.md Appendix A](./optimization-guide.md#appendix-a-implementation-specifications).**
