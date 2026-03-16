# Detection Cost Profiling & Validation Guide

> **Document Version:** 1.0  
> **Last Updated:** 2026-03-01  
> **Target Audience:** AI Agents implementing and validating optimizations, human reviewers  
> **Companion:** [detection_cost_optimization_guide.md](file:///home/alonso/Projects/Mind-Industry/docs/implementation_artifacts/detection_cost_optimization_guide.md)  
> **Existing Profiling Infrastructure:** [aux_scripts/profiling/](file:///home/alonso/Projects/Mind-Industry/aux_scripts/profiling/)

---

## Table of Contents

1. [Objective](#1-objective)
2. [Instrumentation Layer](#2-instrumentation-layer)
3. [Test Fixture Design](#3-test-fixture-design)
4. [Profiler Script Design](#4-profiler-script-design)
5. [Quality Regression Tests](#5-quality-regression-tests)
6. [Execution Protocol](#6-execution-protocol)
7. [Acceptance Criteria](#7-acceptance-criteria)
8. [Integration with Existing Profiling Suite](#8-integration-with-existing-profiling-suite)

---

## 1. Objective

Provide a reproducible, automated way to:

1. **Count exactly** how many LLM API calls the detection pipeline makes per run
2. **Compare baseline vs optimized** call counts side-by-side
3. **Validate that detection quality is preserved** after optimization
4. **Track cost-per-run** across pipeline versions

> [!IMPORTANT]
> All profiling runs must use a **fixed, deterministic dataset** so results are comparable. The profiler must capture call counts **per pipeline step**, not just totals, to pinpoint which optimizations have effect.

---

## 2. Instrumentation Layer

### 2.1 Call Counter Mixin

Add a lightweight instrumentation layer to `Prompter` that tracks calls by category without affecting behavior.

#### [MODIFY] [prompter.py](file:///home/alonso/Projects/Mind-Industry/src/mind/prompter/prompter.py)

Add these attributes and methods to the `Prompter` class:

```python
# --- Call Instrumentation (add to __init__) ---
self._call_log = []          # List of {"step": str, "tokens_in": int, "tokens_out": int, "ts": float}
self._call_counts = {}       # {"step_name": count}
self._instrumentation = False

def enable_instrumentation(self):
    """Enable call counting and logging."""
    self._instrumentation = True
    self._call_log = []
    self._call_counts = {}

def disable_instrumentation(self):
    """Disable call counting."""
    self._instrumentation = False

def log_call(self, step: str, tokens_in: int = 0, tokens_out: int = 0):
    """Record a call under a named step."""
    if not self._instrumentation:
        return
    import time
    self._call_counts[step] = self._call_counts.get(step, 0) + 1
    self._call_log.append({
        "step": step,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "ts": time.time()
    })

@property
def call_summary(self) -> dict:
    """Return a summary of all instrumented calls."""
    return {
        "total_calls": len(self._call_log),
        "calls_by_step": dict(self._call_counts),
        "total_tokens_in": sum(c["tokens_in"] for c in self._call_log),
        "total_tokens_out": sum(c["tokens_out"] for c in self._call_log),
    }

def reset_instrumentation(self):
    """Clear all recorded call data."""
    self._call_log = []
    self._call_counts = {}
```

### 2.2 Pipeline Call Tagging

Each LLM-calling method in `pipeline.py` must tag its calls with a step name. This is how the profiler distinguishes *where* calls come from.

#### [MODIFY] [pipeline.py](file:///home/alonso/Projects/Mind-Industry/src/mind/pipeline/pipeline.py)

Add `self._prompter.log_call("step_name")` after each `self._prompter.prompt()` call:

```python
# In _generate_questions():
response, _ = self._prompter.prompt(question=template_formatted, dry_run=self.dry_run)
self._prompter.log_call("question_generation")   # ← ADD

# In _generate_subqueries():
response, _ = self._prompter.prompt(question=template_formatted, dry_run=self.dry_run)
self._prompter.log_call("subquery_generation")    # ← ADD

# In _generate_answer():
response, _ = self._prompter_answer.prompt(question=template_formatted, dry_run=self.dry_run)
self._prompter_answer.log_call("answer_generation") # ← ADD (note: uses _prompter_answer)

# In _check_is_relevant():
response, _ = self._prompter.prompt(question=template_formatted, dry_run=self.dry_run)
self._prompter.log_call("relevance_check")         # ← ADD

# In _check_contradiction():
response, _ = self._prompter.prompt(question=template_formatted, dry_run=self.dry_run)
self._prompter.log_call("contradiction_check")     # ← ADD
```

> [!TIP]
> Because the pipeline uses TWO Prompter instances (`self._prompter` and `self._prompter_answer`), the profiler must aggregate counts from **both**. Add a helper method to `MIND`:

```python
# In MIND class:
@property
def total_call_summary(self) -> dict:
    """Aggregate call summaries from all prompter instances."""
    s1 = self._prompter.call_summary
    s2 = self._prompter_answer.call_summary
    merged_by_step = dict(s1["calls_by_step"])
    for k, v in s2["calls_by_step"].items():
        merged_by_step[k] = merged_by_step.get(k, 0) + v
    return {
        "total_calls": s1["total_calls"] + s2["total_calls"],
        "calls_by_step": merged_by_step,
        "total_tokens_in": s1["total_tokens_in"] + s2["total_tokens_in"],
        "total_tokens_out": s1["total_tokens_out"] + s2["total_tokens_out"],
    }
```

---

## 3. Test Fixture Design

### 3.1 Fixed Benchmark Dataset

Create a **small, deterministic** dataset that is fast to run but exercises all pipeline paths.

#### [NEW] `aux_scripts/profiling/fixtures/detection_benchmark.py`

```python
"""
Generate a fixed benchmark corpus for detection cost profiling.

Output: Two Parquet files (source + target corpora) with known content,
plus a pre-built FAISS index.

Design:
- 20 source chunks across 2 topics (10 per topic)
- 40 target chunks with known relevance distribution
- Deterministic content so LLM outputs are roughly consistent across runs
"""

import pandas as pd
import numpy as np
from pathlib import Path

FIXTURE_DIR = Path(__file__).parent / "detection_fixtures"

def generate_detection_benchmark():
    """Generate the fixed benchmark dataset for detection profiling."""
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)

    np.random.seed(42)
    
    # Source corpus: 20 chunks, 2 topics
    source_records = []
    for i in range(20):
        topic = i // 10  # 0 or 1
        source_records.append({
            "doc_id": f"src_{i:03d}",
            "chunk_text": f"Source passage {i} about topic {topic}. "
                          f"This is a factual claim that can be verified.",
            "full_doc": f"Full document {i} with extended context...",
            "main_topic_thetas": topic,
            "top_k": [topic],
        })
    
    # Target corpus: 40 chunks
    target_records = []
    for i in range(40):
        target_records.append({
            "doc_id": f"tgt_{i:03d}",
            "chunk_text": f"Target passage {i} with related content.",
            "full_doc": f"Full target document {i}...",
            "main_topic_thetas": i % 2,
            "top_k": [i % 2],
        })
    
    pd.DataFrame(source_records).to_parquet(FIXTURE_DIR / "source_corpus.parquet")
    pd.DataFrame(target_records).to_parquet(FIXTURE_DIR / "target_corpus.parquet")
    
    # Save config
    config = {
        "source_chunks": len(source_records),
        "target_chunks": len(target_records),
        "topics": [0, 1],
        "expected_questions_per_chunk": "2-4 (depends on LLM)",
        "seed": 42,
    }
    import json
    with open(FIXTURE_DIR / "benchmark_config.json", "w") as f:
        json.dump(config, f, indent=2)
    
    print(f"Benchmark fixture created at {FIXTURE_DIR}")
    return FIXTURE_DIR

if __name__ == "__main__":
    generate_detection_benchmark()
```

### 3.2 Dataset Size Tiers

The profiler should run on multiple sizes to observe scaling:

| Tier | Source Chunks | Topics | Estimated Calls (baseline) | Purpose |
|------|--------------|--------|----------------------------|---------|
| **Micro** | 5 | 1 | ~365 | Quick smoke test |
| **Small** | 20 | 2 | ~1,460 | Standard profiling |
| **Medium** | 50 | 3 | ~5,475 | Realistic workload |

> [!WARNING]
> For actual profiling, use the **real LLM** (not mocked), as the full pipeline including de-duplication, filtering, and relevance behavior depends on actual LLM responses. Mock profiling is only useful for validating instrumentation code.

---

## 4. Profiler Script Design

### 4.1 Main Profiler

#### [NEW] `aux_scripts/profiling/detection_cost_profiler.py`

Following the same pattern as [opt_010_llm_profiler.py](file:///home/alonso/Projects/Mind-Industry/aux_scripts/profiling/opt_010_llm_profiler.py):

```python
#!/usr/bin/env python3
"""
Detection Cost Profiler

Measures the number of LLM API calls made during detection pipeline runs.
Supports A/B comparison between baseline and optimized pipeline configurations.

Usage:
    # Run baseline profiling
    python -m aux_scripts.profiling.detection_cost_profiler --mode baseline

    # Run optimized profiling  
    python -m aux_scripts.profiling.detection_cost_profiler --mode optimized

    # Compare results
    python -m aux_scripts.profiling.detection_cost_profiler --mode compare

    # Full A/B test (baseline + optimized + compare)
    python -m aux_scripts.profiling.detection_cost_profiler --mode full
"""

import sys
import json
import time
import argparse
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "src"))

RESULTS_DIR = Path(__file__).parent / "profiling" / "results"
FIXTURE_DIR = Path(__file__).parent / "fixtures" / "detection_fixtures"


class Colors:
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    BLUE = "\033[94m"
    BOLD = "\033[1m"
    END = "\033[0m"


class DetectionCostProfiler:
    """
    Profiles the total number of LLM API calls in the MIND detection pipeline.
    
    Collects:
    - Total call count
    - Calls broken down by step (question_generation, subquery_generation, etc.)
    - Tokens consumed (input + output)
    - Wall-clock time
    - Calls per source chunk (efficiency metric)
    """

    def __init__(self, results_dir: Path = RESULTS_DIR, verbose: bool = True):
        self.results_dir = results_dir
        self.results_dir.mkdir(parents=True, exist_ok=True)
        self.verbose = verbose

    def _log(self, msg: str, color: str = ""):
        if self.verbose:
            print(f"{color}{msg}{Colors.END}")

    def run_pipeline(self, config_overrides: dict = None, tag: str = "baseline") -> dict:
        """
        Run the detection pipeline with instrumentation enabled.
        
        Parameters
        ----------
        config_overrides : dict
            Config values to override for this run (e.g., cost_optimization flags).
        tag : str
            Label for this run ('baseline' or 'optimized').
        
        Returns
        -------
        dict
            Profiling results including call counts and timing.
        """
        from mind.pipeline.pipeline import MIND
        
        # Load standard profiling config
        config = self._load_profiling_config()
        if config_overrides:
            config.update(config_overrides)

        self._log(f"\n{'='*60}", Colors.BOLD)
        self._log(f"  Detection Cost Profiler — {tag.upper()} RUN", Colors.BOLD)
        self._log(f"{'='*60}", Colors.BOLD)

        # Initialize MIND with instrumentation
        mind = MIND(
            source_corpus=config["source_corpus"],
            target_corpus=config["target_corpus"],
            config_path=config.get("config_path", "/src/config/config.yaml"),
            **{k: v for k, v in config.items() 
               if k not in ("source_corpus", "target_corpus", "config_path", "topics", "sample_size")}
        )
        
        # Enable call counting on both prompter instances
        mind._prompter.enable_instrumentation()
        mind._prompter_answer.enable_instrumentation()

        # Run pipeline with timing
        t0 = time.perf_counter()
        mind.run_pipeline(
            topics=config.get("topics", [0]),
            sample_size=config.get("sample_size"),
            path_save=str(self.results_dir / f"detection_{tag}")
        )
        elapsed = time.perf_counter() - t0

        # Collect results
        summary = mind.total_call_summary
        results = {
            "tag": tag,
            "timestamp": datetime.now().isoformat(),
            "elapsed_seconds": round(elapsed, 2),
            "total_calls": summary["total_calls"],
            "calls_by_step": summary["calls_by_step"],
            "total_tokens_in": summary["total_tokens_in"],
            "total_tokens_out": summary["total_tokens_out"],
            "source_chunks_processed": len(mind.results),
            "calls_per_result": round(summary["total_calls"] / max(len(mind.results), 1), 2),
            "config_overrides": config_overrides or {},
        }

        self._print_results(results)
        self._save_results(results, tag)
        return results

    def run_baseline(self) -> dict:
        """Run the pipeline with NO cost optimizations (current behavior)."""
        return self.run_pipeline(
            config_overrides={
                "cost_optimization.use_merged_evaluation": False,
                "cost_optimization.skip_subquery_generation": False,
                "cost_optimization.relevance_method": "llm",
                "cost_optimization.max_questions_per_chunk": 99,  # No limit
            },
            tag="baseline"
        )

    def run_optimized(self) -> dict:
        """Run the pipeline with cost optimizations enabled."""
        return self.run_pipeline(
            config_overrides={
                "cost_optimization.use_merged_evaluation": True,
                "cost_optimization.skip_subquery_generation": True,
                "cost_optimization.relevance_method": "local",
                "cost_optimization.max_questions_per_chunk": 2,
                "cost_optimization.retrieval_min_similarity": 0.35,
            },
            tag="optimized"
        )

    def compare(self, baseline_path: str = None, optimized_path: str = None) -> dict:
        """
        Compare baseline vs optimized profiling results.
        
        Loads from JSON files if paths not given.
        """
        baseline_path = baseline_path or self.results_dir / "detection_cost_baseline.json"
        optimized_path = optimized_path or self.results_dir / "detection_cost_optimized.json"

        with open(baseline_path) as f:
            baseline = json.load(f)
        with open(optimized_path) as f:
            optimized = json.load(f)

        comparison = self._build_comparison(baseline, optimized)
        self._print_comparison(comparison)
        self._save_results(comparison, "comparison")
        return comparison

    def _build_comparison(self, baseline: dict, optimized: dict) -> dict:
        """Build a structured comparison between two runs."""
        b_total = baseline["total_calls"]
        o_total = optimized["total_calls"]
        reduction_pct = round((1 - o_total / max(b_total, 1)) * 100, 1)

        # Per-step comparison
        all_steps = set(baseline.get("calls_by_step", {}).keys()) | \
                    set(optimized.get("calls_by_step", {}).keys())
        step_comparison = {}
        for step in sorted(all_steps):
            b_count = baseline.get("calls_by_step", {}).get(step, 0)
            o_count = optimized.get("calls_by_step", {}).get(step, 0)
            step_reduction = round((1 - o_count / max(b_count, 1)) * 100, 1) if b_count > 0 else 0
            step_comparison[step] = {
                "baseline": b_count,
                "optimized": o_count,
                "reduction_pct": step_reduction,
            }

        return {
            "baseline_tag": baseline["tag"],
            "optimized_tag": optimized["tag"],
            "baseline_timestamp": baseline["timestamp"],
            "optimized_timestamp": optimized["timestamp"],
            "total_calls_baseline": b_total,
            "total_calls_optimized": o_total,
            "total_reduction_pct": reduction_pct,
            "time_baseline_s": baseline["elapsed_seconds"],
            "time_optimized_s": optimized["elapsed_seconds"],
            "time_reduction_pct": round(
                (1 - optimized["elapsed_seconds"] / max(baseline["elapsed_seconds"], 0.01)) * 100, 1
            ),
            "step_comparison": step_comparison,
            "tokens_baseline": baseline.get("total_tokens_in", 0) + baseline.get("total_tokens_out", 0),
            "tokens_optimized": optimized.get("total_tokens_in", 0) + optimized.get("total_tokens_out", 0),
            "passes_acceptance": reduction_pct >= 50,  # Target: ≥50% reduction
        }

    def _print_results(self, results: dict):
        """Print a single run's results to terminal."""
        self._log(f"\n{'─'*50}")
        self._log(f"  Run: {results['tag'].upper()}", Colors.BOLD)
        self._log(f"{'─'*50}")
        self._log(f"  Total LLM calls:    {results['total_calls']}", Colors.BLUE)
        self._log(f"  Wall-clock time:    {results['elapsed_seconds']}s")
        self._log(f"  Calls per result:   {results['calls_per_result']}")
        self._log(f"  Tokens (in+out):    {results['total_tokens_in'] + results['total_tokens_out']}")
        self._log(f"\n  Calls by step:")
        for step, count in sorted(results["calls_by_step"].items(), key=lambda x: -x[1]):
            pct = round(count / max(results["total_calls"], 1) * 100, 1)
            self._log(f"    {step:<25s} {count:>6d}  ({pct:>5.1f}%)")

    def _print_comparison(self, comp: dict):
        """Print comparison results with color-coded pass/fail."""
        self._log(f"\n{'='*60}", Colors.BOLD)
        self._log(f"  A/B COMPARISON RESULTS", Colors.BOLD)
        self._log(f"{'='*60}", Colors.BOLD)

        color = Colors.GREEN if comp["passes_acceptance"] else Colors.RED
        status = "✅ PASS" if comp["passes_acceptance"] else "❌ FAIL"

        self._log(f"\n  Total calls:  {comp['total_calls_baseline']} → {comp['total_calls_optimized']}"
                  f"  ({color}-{comp['total_reduction_pct']}%{Colors.END})")
        self._log(f"  Wall time:    {comp['time_baseline_s']}s → {comp['time_optimized_s']}s"
                  f"  (-{comp['time_reduction_pct']}%)")
        self._log(f"  Tokens:       {comp['tokens_baseline']} → {comp['tokens_optimized']}")

        self._log(f"\n  Per-step breakdown:")
        self._log(f"  {'Step':<25s} {'Baseline':>8s} {'Optimized':>9s} {'Reduction':>10s}")
        self._log(f"  {'─'*55}")
        for step, data in sorted(comp["step_comparison"].items()):
            c = Colors.GREEN if data["reduction_pct"] > 0 else Colors.YELLOW
            self._log(f"  {step:<25s} {data['baseline']:>8d} {data['optimized']:>9d}"
                      f"  {c}{data['reduction_pct']:>8.1f}%{Colors.END}")

        self._log(f"\n  Acceptance (≥50% reduction): {color}{status}{Colors.END}")

    def _save_results(self, results: dict, tag: str):
        """Save results to JSON."""
        path = self.results_dir / f"detection_cost_{tag}.json"
        with open(path, "w") as f:
            json.dump(results, f, indent=2, default=str)
        self._log(f"  Results saved to: {path}", Colors.BLUE)

    def _load_profiling_config(self) -> dict:
        """Load the standard profiling run config."""
        config_path = FIXTURE_DIR / "benchmark_config.json"
        if not config_path.exists():
            # Auto-generate fixtures if missing
            from aux_scripts.profiling.fixtures.detection_benchmark import generate_detection_benchmark
            generate_detection_benchmark()
        
        with open(config_path) as f:
            bench = json.load(f)
        
        return {
            "source_corpus": {
                "corpus_path": str(FIXTURE_DIR / "source_corpus.parquet"),
                "id_col": "doc_id",
                "passage_col": "chunk_text",
                "full_doc_col": "full_doc",
                "load_thetas": False,
            },
            "target_corpus": {
                "corpus_path": str(FIXTURE_DIR / "target_corpus.parquet"),
                "id_col": "doc_id",
                "passage_col": "chunk_text",
                "full_doc_col": "full_doc",
                "load_thetas": False,
            },
            "topics": bench["topics"],
            "sample_size": bench["source_chunks"],
        }

    def run_full(self) -> dict:
        """Run baseline, optimized, and comparison."""
        self._log("Phase 1/3: Running BASELINE...", Colors.YELLOW)
        baseline = self.run_baseline()

        self._log("\nPhase 2/3: Running OPTIMIZED...", Colors.YELLOW)
        optimized = self.run_optimized()

        self._log("\nPhase 3/3: Comparing results...", Colors.YELLOW)
        comparison = self.compare()

        return comparison


def main():
    parser = argparse.ArgumentParser(description="Detection Cost Profiler")
    parser.add_argument(
        "--mode", 
        choices=["baseline", "optimized", "compare", "full"],
        default="full",
        help="Profiling mode to run"
    )
    parser.add_argument("--results-dir", type=str, default=None,
                        help="Override results directory")
    parser.add_argument("--quiet", action="store_true",
                        help="Suppress verbose output")
    args = parser.parse_args()

    profiler = DetectionCostProfiler(
        results_dir=Path(args.results_dir) if args.results_dir else RESULTS_DIR,
        verbose=not args.quiet,
    )

    if args.mode == "baseline":
        profiler.run_baseline()
    elif args.mode == "optimized":
        profiler.run_optimized()
    elif args.mode == "compare":
        profiler.compare()
    elif args.mode == "full":
        profiler.run_full()


if __name__ == "__main__":
    main()
```

---

## 5. Quality Regression Tests

Call reduction is meaningless if the pipeline misses contradictions. These tests validate detection quality alongside cost.

### 5.1 Label Distribution Test

Compare the distribution of output labels between baseline and optimized runs. The optimized pipeline should produce a **similar distribution** (within tolerance).

```python
def validate_label_distribution(baseline_results_dir: Path, optimized_results_dir: Path,
                                 tolerance: float = 0.10) -> dict:
    """
    Compare label distributions between baseline and optimized runs.
    
    Parameters
    ----------
    tolerance : float
        Maximum allowed difference in label proportion (e.g., 0.10 = 10%).
    
    Returns
    -------
    dict with 'passed', 'baseline_dist', 'optimized_dist', 'diffs'
    """
    import pandas as pd
    from pathlib import Path
    import glob

    def load_results(d):
        files = glob.glob(str(d / "results_topic_*.parquet"))
        if not files:
            raise FileNotFoundError(f"No results in {d}")
        return pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)

    df_b = load_results(baseline_results_dir)
    df_o = load_results(optimized_results_dir)

    dist_b = df_b["label"].value_counts(normalize=True).to_dict()
    dist_o = df_o["label"].value_counts(normalize=True).to_dict()

    all_labels = set(dist_b.keys()) | set(dist_o.keys())
    diffs = {}
    passed = True
    for label in all_labels:
        b_pct = dist_b.get(label, 0)
        o_pct = dist_o.get(label, 0)
        diff = abs(b_pct - o_pct)
        diffs[label] = {"baseline": round(b_pct, 3), "optimized": round(o_pct, 3), 
                        "diff": round(diff, 3), "within_tolerance": diff <= tolerance}
        if diff > tolerance:
            passed = False

    return {"passed": passed, "diffs": diffs, "tolerance": tolerance,
            "baseline_total": len(df_b), "optimized_total": len(df_o)}
```

### 5.2 Contradiction Recall Test

The most critical test: ensure the optimized pipeline **does not miss genuine contradictions** found by the baseline.

```python
def validate_contradiction_recall(baseline_results_dir: Path, optimized_results_dir: Path,
                                   target_recall: float = 0.90) -> dict:
    """
    Check that the optimized pipeline catches at least `target_recall` of
    the contradictions found by the baseline.
    
    Logic:
    - Baseline contradictions = set of (question, source_chunk_id, target_chunk_id) 
      where label == "CONTRADICTION"
    - Optimized contradictions = same structure
    - Recall = |intersection| / |baseline contradictions|
    """
    import pandas as pd
    import glob

    def load_results(d):
        files = glob.glob(str(d / "results_topic_*.parquet"))
        return pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)

    df_b = load_results(baseline_results_dir)
    df_o = load_results(optimized_results_dir)

    # Build contradiction sets
    def get_contradiction_keys(df):
        contradictions = df[df["label"] == "CONTRADICTION"]
        return set(zip(contradictions["question"], 
                       contradictions["source_chunk_id"],
                       contradictions["target_chunk_id"]))

    baseline_contras = get_contradiction_keys(df_b)
    optimized_contras = get_contradiction_keys(df_o)

    if len(baseline_contras) == 0:
        return {"passed": True, "recall": 1.0, "note": "No baseline contradictions to compare"}

    found = baseline_contras & optimized_contras
    missed = baseline_contras - optimized_contras
    new = optimized_contras - baseline_contras  # New contradictions found by optimized

    recall = len(found) / len(baseline_contras)

    return {
        "passed": recall >= target_recall,
        "recall": round(recall, 3),
        "target_recall": target_recall,
        "baseline_contradictions": len(baseline_contras),
        "optimized_contradictions": len(optimized_contras),
        "matched": len(found),
        "missed": len(missed),
        "new_in_optimized": len(new),
        "missed_keys": list(missed)[:10],  # Sample for debugging
    }
```

### 5.3 Comprehensive Quality Report

Chain both quality tests into a single report:

```python
def run_quality_validation(baseline_dir: Path, optimized_dir: Path) -> dict:
    """Run all quality validation tests and produce a pass/fail report."""
    
    dist_result = validate_label_distribution(baseline_dir, optimized_dir)
    recall_result = validate_contradiction_recall(baseline_dir, optimized_dir)

    overall_pass = dist_result["passed"] and recall_result["passed"]

    report = {
        "overall_passed": overall_pass,
        "label_distribution": dist_result,
        "contradiction_recall": recall_result,
        "timestamp": datetime.now().isoformat(),
    }

    # Print summary
    status = "✅ ALL PASS" if overall_pass else "❌ QUALITY REGRESSION"
    print(f"\n{'='*50}")
    print(f"  Quality Validation: {status}")
    print(f"{'='*50}")
    print(f"  Label distribution within tolerance: {'✅' if dist_result['passed'] else '❌'}")
    print(f"  Contradiction recall ≥ {recall_result['target_recall']}: "
          f"{'✅' if recall_result['passed'] else '❌'} ({recall_result['recall']})")
    print(f"  Baseline results:  {dist_result['baseline_total']} entries")
    print(f"  Optimized results: {dist_result['optimized_total']} entries")

    return report
```

---

## 6. Execution Protocol

### 6.1 Step-by-Step Profiling Workflow

```
┌──────────────────────────────────────────────────────┐
│  STEP 1: Generate benchmark fixtures                 │
│  python -m aux_scripts.profiling.fixtures.            │
│          detection_benchmark                          │
├──────────────────────────────────────────────────────┤
│  STEP 2: Run BASELINE profiling                      │
│  python -m aux_scripts.profiling.                     │
│          detection_cost_profiler --mode baseline      │
├──────────────────────────────────────────────────────┤
│  STEP 3: Implement optimization strategies           │
│  (See detection_cost_optimization_guide.md)           │
├──────────────────────────────────────────────────────┤
│  STEP 4: Run OPTIMIZED profiling                     │
│  python -m aux_scripts.profiling.                     │
│          detection_cost_profiler --mode optimized     │
├──────────────────────────────────────────────────────┤
│  STEP 5: Compare results                             │
│  python -m aux_scripts.profiling.                     │
│          detection_cost_profiler --mode compare       │
├──────────────────────────────────────────────────────┤
│  STEP 6: Run quality validation                      │
│  (Uses output Parquet files from Steps 2 & 4)        │
└──────────────────────────────────────────────────────┘
```

### 6.2 Quick Full Run

```bash
# Run everything: baseline, optimized, compare, and quality validation
python -m aux_scripts.profiling.detection_cost_profiler --mode full
```

### 6.3 Incremental Strategy Testing

To test each strategy independently, run baseline once, then test each strategy in isolation:

```bash
# 1. Baseline (run once, reuse)
python -m aux_scripts.profiling.detection_cost_profiler --mode baseline

# 2. Test Strategy 1 only (merged prompt)
python -m aux_scripts.profiling.detection_cost_profiler --mode optimized \
    --override "cost_optimization.use_merged_evaluation=true"

# 3. Test Strategy 2 only (skip subqueries)
python -m aux_scripts.profiling.detection_cost_profiler --mode optimized \
    --override "cost_optimization.skip_subquery_generation=true"

# 4. Compare each
python -m aux_scripts.profiling.detection_cost_profiler --mode compare
```

---

## 7. Acceptance Criteria

### 7.1 Cost Reduction Thresholds

| Metric | Minimum Acceptable | Target | Stretch Goal |
|--------|--------------------|--------|--------------|
| **Total call reduction** | ≥ 40% | ≥ 60% | ≥ 80% |
| **Calls per source chunk** | ≤ 25 | ≤ 15 | ≤ 10 |
| **Wall-clock time reduction** | ≥ 30% | ≥ 50% | ≥ 70% |
| **Token cost reduction** | ≥ 30% | ≥ 50% | ≥ 70% |

### 7.2 Quality Preservation Thresholds

| Metric | Threshold | Rationale |
|--------|-----------|-----------|
| **Label distribution drift** | ≤ 10% per category | Ensures no systematic bias shift |
| **Contradiction recall** | ≥ 90% | Must catch most real contradictions |
| **CULTURAL_DISCREPANCY recall** | ≥ 85% | Acceptable slightly lower (harder category) |
| **False positive rate change** | ≤ +5% | Acceptable minor increase in FP |

### 7.3 Pass/Fail Decision Matrix

| Cost Result | Quality Result | Decision |
|-------------|---------------|----------|
| ✅ ≥ 40% reduction | ✅ All quality tests pass | **✅ Accept optimization** |
| ✅ ≥ 40% reduction | ❌ Quality regression | **⚠️ Tune thresholds / revise strategy** |
| ❌ < 40% reduction | ✅ All quality tests pass | **⚠️ Add more strategies** |
| ❌ < 40% reduction | ❌ Quality regression | **❌ Reject — back to design** |

---

## 8. Integration with Existing Profiling Suite

### 8.1 Registration in `run_profiling.py`

Add the detection cost profiler to the main orchestrator at [run_profiling.py](file:///home/alonso/Projects/Mind-Industry/aux_scripts/profiling/run_profiling.py):

```python
# In run_profiling.py, add to suite selection:
def run_detection_cost_suite(results_dir: Path):
    """Run detection cost profiling."""
    from aux_scripts.profiling.detection_cost_profiler import DetectionCostProfiler
    profiler = DetectionCostProfiler(results_dir=results_dir)
    return profiler.run_full()

# In main(), add to the --suite choices:
# parser.add_argument("--suite", choices=[..., "detection_cost", ...])
```

### 8.2 Results Directory Structure

```
aux_scripts/profiling/
├── profiling/
│   └── results/
│       ├── profiling_results_baseline.json       # Existing
│       ├── detection_cost_baseline.json           # NEW
│       ├── detection_cost_optimized.json          # NEW
│       ├── detection_cost_comparison.json         # NEW
│       └── detection_quality_report.json          # NEW
├── fixtures/
│   └── detection_fixtures/                        # NEW
│       ├── source_corpus.parquet
│       ├── target_corpus.parquet
│       └── benchmark_config.json
├── detection_cost_profiler.py                     # NEW
└── fixtures/
    └── detection_benchmark.py                     # NEW
```

### 8.3 Expected Output Example

```
══════════════════════════════════════════════════════════
  A/B COMPARISON RESULTS
══════════════════════════════════════════════════════════

  Total calls:  1,460 → 520  (-64.4%)
  Wall time:    142.3s → 51.7s  (-63.7%)
  Tokens:       876,000 → 312,000  (-64.4%)

  Per-step breakdown:
  Step                       Baseline  Optimized  Reduction
  ───────────────────────────────────────────────────────────
  answer_generation               180         40     -77.8%
  contradiction_check             108         40     -63.0%
  merged_evaluation                 0         40       NEW
  question_generation              20         20      0.0%
  relevance_check                 180          0   -100.0%
  subquery_generation              60          0   -100.0%

  Acceptance (≥50% reduction): ✅ PASS

══════════════════════════════════════════════════════════
  Quality Validation: ✅ ALL PASS
══════════════════════════════════════════════════════════
  Label distribution within tolerance: ✅
  Contradiction recall ≥ 0.90: ✅ (0.94)
  Baseline results:  288 entries
  Optimized results: 80 entries
```
