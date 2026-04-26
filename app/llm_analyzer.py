"""LLM-powered analysis of collected system metrics."""

from __future__ import annotations

import logging
import os

import litellm
from config import PROMPT_LLM_ANALYZER
from database import DatabaseManager
from utils import _fmt

log = logging.getLogger(__name__)

LLM_API_KEY = os.getenv("LLM_API_KEY")
LLM_MODEL = os.getenv("LLM_MODEL")

# Default number of minutes to analyze by the LLM
DEFAULT_WINDOW_MINUTES = 5


def build_prompt(
    db: DatabaseManager,
    process_name: str,
) -> str | None:
    """Render the analyst prompt for *process_name*, or None if data is sparse."""

    # Retrieve the summary of system metrics for the last DEFAULT_WINDOW_MINUTES minutes and for the given process
    df_system_summary = db.get_summary_for_llm(
        minutes=DEFAULT_WINDOW_MINUTES, process_name=process_name
    )

    system_summary = df_system_summary.iloc[0]

    # Add information about the process that have the current highest average CPU usage
    df_top_usage_processes = db.get_top_processes()

    top_cpu_usage_processes = ""
    for _, row in df_top_usage_processes.iterrows():
        top_cpu_usage_processes += f"\n- {row['name']} (CPU: {_fmt(row['cpu_percent'])}%, Mem: {_fmt(row['memory_mb'], 0)} MB, Threads: {row['num_threads']}, Status: {row['status']})"

    prompt = PROMPT_LLM_ANALYZER.format(
        minutes=DEFAULT_WINDOW_MINUTES,
        evaluated_process=process_name,
        avg_cpu=_fmt(system_summary["avg_cpu"]),
        max_cpu=_fmt(system_summary["max_cpu"]),
        avg_load=_fmt(system_summary["avg_load"]),
        avg_ram_pct=_fmt(system_summary["avg_ram_pct"]),
        avg_irqs=_fmt(system_summary["avg_irqs"]),
        avg_ctx=_fmt(system_summary["avg_ctx"]),
        ws_avg_cpu=_fmt(system_summary["proc_avg_cpu"]),
        ws_max_cpu=_fmt(system_summary["proc_max_cpu"]),
        ws_avg_mem_mb=_fmt(system_summary["proc_avg_mem_mb"]),
        ws_threads=_fmt(system_summary["proc_threads"]),
        top_cpu_usage_processes=top_cpu_usage_processes,
    )

    return prompt


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
        return (
            response.choices[0].message.content
            or "There was an error while calling the LLM APuI"
        )
    except Exception as exc:
        log.error("LLM call failed: %s", exc)
        return f"LLM analysis failed: {exc}"
