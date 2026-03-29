"""YAML configuration loading, deep-merge, and path resolution for the MIND CLI."""

import copy
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Optional

import yaml


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge *override* into a copy of *base*."""
    result = copy.deepcopy(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def resolve_system_config(
    cli_flag: Optional[str] = None,
) -> Path:
    """Resolve the path to ``config/config.yaml``.

    Priority:
    1. Explicit ``--system-config`` CLI flag
    2. ``MIND_CONFIG_PATH`` environment variable
    3. Walk up from this file's location looking for ``config/config.yaml``
    4. Fallback: ``config/config.yaml`` relative to CWD
    """
    if cli_flag:
        p = Path(cli_flag)
        if p.exists():
            return p.resolve()
        raise FileNotFoundError(f"System config not found: {cli_flag}")

    env = os.environ.get("MIND_CONFIG_PATH")
    if env:
        p = Path(env)
        if p.exists():
            return p.resolve()
        raise FileNotFoundError(f"MIND_CONFIG_PATH points to missing file: {env}")

    # Walk up from this file
    current = Path(__file__).resolve().parent
    for _ in range(10):
        candidate = current / "config" / "config.yaml"
        if candidate.exists():
            return candidate
        current = current.parent

    # Fallback: CWD
    cwd_candidate = Path.cwd() / "config" / "config.yaml"
    if cwd_candidate.exists():
        return cwd_candidate

    raise FileNotFoundError(
        "Could not locate config/config.yaml. "
        "Pass --system-config or set MIND_CONFIG_PATH."
    )


def load_run_config(path: Path) -> dict:
    """Load a user-provided run configuration YAML file."""
    if not path.exists():
        raise FileNotFoundError(f"Run config not found: {path}")
    with open(path) as f:
        data = yaml.safe_load(f) or {}
    return data


def load_system_config(path: Path) -> dict:
    """Load the system ``config/config.yaml``."""
    if not path.exists():
        raise FileNotFoundError(f"System config not found: {path}")
    with open(path) as f:
        return yaml.safe_load(f) or {}


def build_merged_config(
    run_config: dict,
    system_config_path: Path,
) -> tuple[dict, Path]:
    """Merge run config overrides into the system config and write a temp copy.

    This avoids mutating the real ``config/config.yaml`` (which the web backend
    does in-place). The returned path points to a temporary file that can be
    passed to ``MIND(config_path=...)``.

    Returns
    -------
    tuple[dict, Path]
        (merged_system_config_dict, path_to_temp_config_file)
    """
    system = load_system_config(system_config_path)

    # Apply LLM overrides from run config
    run_llm = run_config.get("llm")
    if run_llm:
        system["llm"] = _deep_merge(system.get("llm", {}), run_llm)

    # Apply detect-level overrides
    detect = run_config.get("detect", {})
    method = detect.get("method")
    if method is not None:
        system.setdefault("mind", {})["method"] = method

    do_weighting = detect.get("do_weighting")
    if do_weighting is not None:
        system.setdefault("mind", {})["do_weighting"] = do_weighting

    # Write to a temp file so the original is never mutated
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", prefix="mind_cfg_", delete=False
    )
    yaml.safe_dump(system, tmp, sort_keys=False)
    tmp.close()

    return system, Path(tmp.name)


def build_nlpipe_temp_config(
    original_config_path: Path,
    dataset_key: str,
    overrides: dict[str, Any],
) -> Path:
    """Create a temporary copy of the NLPipe ``config.json`` with patched keys.

    This avoids mutating the shared ``externals/NLPipe/config.json``.

    Returns the path to the temporary copy.
    """
    import json

    with open(original_config_path) as f:
        cfg = json.load(f)

    cfg[dataset_key] = _deep_merge(cfg.get(dataset_key, {}), overrides)

    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", prefix="nlpipe_cfg_", delete=False
    )
    json.dump(cfg, tmp, indent=2)
    tmp.close()
    return Path(tmp.name)
