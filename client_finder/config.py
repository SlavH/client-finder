"""Configuration loading for client-finder."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml


def load_env(env_path: str | Path | None = None) -> None:
    """Load environment variables from a .env file (simple parser)."""
    if env_path is None:
        env_path = Path(".env")
    env_path = Path(env_path)
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def load_config(config_path: str | Path | None = None) -> dict[str, Any]:
    """Load config.yaml, merging with defaults and env overrides."""
    defaults: dict[str, Any] = {
        "llm": {
            "provider": "openai",
            "model": "gpt-4o-mini",
            "api_key_env": "OPENAI_API_KEY",
            "base_url": None,
            "temperature": 0.7,
            "max_tokens": 1500,
        },
        "outreach": {
            "mode": "email_only",
            "humanize": True,
            "dry_run": True,
            "channels": ["email", "linkedin", "twitter", "webform"],
            "max_per_run": 20,
            "daily_caps": {
                "email": 20,
                "linkedin": 5,
                "twitter": 10,
                "webform": 10,
            },
            "send_hours": [9, 10, 11, 14, 15, 16],
            "timezone": "UTC",
        },
        "work_first": {
            "output_dir": "work/",
            "deliverable_types": ["mockup", "audit", "code_sample"],
            "max_deliverables_per_run": 5,
        },
        "sources": {
            "github_jobs": True,
            "google_maps": True,
            "linkedin": True,
            "job_boards": True,
            "respect_robots_txt": True,
            "rate_limit_seconds": 5,
        },
        "state": {"db_path": ".client_finder_state.db"},
    }

    if config_path is None:
        config_path = Path("config.yaml")
    config_path = Path(config_path)

    user_cfg: dict[str, Any] = {}
    if config_path.exists():
        with open(config_path, encoding="utf-8") as f:
            user_cfg = yaml.safe_load(f) or {}

    return _deep_merge(defaults, user_cfg)


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = dict(base)
    for key, value in override.items():
        if (
            key in result
            and isinstance(result[key], dict)
            and isinstance(value, dict)
        ):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def get_api_key(config: dict[str, Any]) -> str | None:
    """Resolve the LLM API key from config -> env."""
    llm_cfg = config.get("llm", {})
    env_name = llm_cfg.get("api_key_env", "OPENAI_API_KEY")
    return os.environ.get(env_name)