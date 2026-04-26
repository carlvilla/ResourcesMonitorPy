"""LLM-powered analysis of collected system metrics."""

from __future__ import annotations

import logging
import os

import litellm
from config import PROMPT_LLM_ANALYZER
from database import DatabaseManager

log = logging.getLogger(__name__)

LLM_API_KEY = os.getenv("LLM_API_KEY")
LLM_MODEL = os.getenv("LLM_MODEL")

# Default lookback for the summary query, in minutes.
DEFAULT_WINDOW_MINUTES = 5


def _fmt(val, decimals: int = 1, suffix: str = "") -> str:
    if val is None:
        return "N/A"
    return f"{float(val):.{decimals}f}{suffix}"


def build_prompt(
    db: DatabaseManager,
    process_name: str,
    minutes: int = DEFAULT_WINDOW_MINUTES,
) -> str | None:
    """Render the analyst prompt for *process_name*, or None if data is sparse."""
    df = db.get_summary_for_llm(minutes=minutes, process_name=process_name)
    if df.empty or df.iloc[0]["avg_cpu"] is None:
        return None

    m = df.iloc[0]
    return PROMPT_LLM_ANALYZER.format(
        minutes=minutes,
        evaluated_process=process_name,
        avg_cpu=_fmt(m["avg_cpu"]),
        max_cpu=_fmt(m["max_cpu"]),
        avg_load=_fmt(m["avg_load"], 2),
        avg_ram_pct=_fmt(m["avg_ram_pct"]),
        avg_irqs=_fmt(m["avg_irqs"], 0),
        avg_ctx=_fmt(m["avg_ctx"], 0),
        ws_avg_cpu=_fmt(m["proc_avg_cpu"]),
        ws_max_cpu=_fmt(m["proc_max_cpu"]),
        ws_avg_mem_mb=_fmt(m["proc_avg_mem_mb"], 0),
        ws_threads=_fmt(m["proc_threads"], 0),
    )


def analyze(db: DatabaseManager, process_name: str) -> str:
    """Run an LLM analysis of *process_name* over the last few minutes of metrics."""
    if not LLM_API_KEY or not LLM_MODEL:
        return (
            "Set `LLM_API_KEY` and `LLM_MODEL` in `.env` to enable LLM analysis. "
            "Model names follow LiteLLM format (see docs.litellm.ai)."
        )

    prompt = build_prompt(db, process_name)
    if prompt is None:
        return (
            "Insufficient data for analysis. "
            "Please wait a few seconds for metrics to be collected."
        )

    try:
        response = litellm.completion(
            model=LLM_MODEL,
            api_key=LLM_API_KEY,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content or "(empty response)"
    except Exception as exc:
        log.error("LLM call failed: %s", exc)
        return f"LLM analysis failed: {exc}"
