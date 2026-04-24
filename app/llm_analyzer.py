"""LLM-powered analysis of collected system metrics."""

import logging

import anthropic
from database import DatabaseManager
from openai import OpenAI

log = logging.getLogger(__name__)


def build_prompt(db: DatabaseManager) -> str:
    df = db.get_summary_for_llm(minutes=5)
    if df.empty or df.iloc[0]["avg_cpu"] is None:
        return ""

    m = df.iloc[0]

    def fmt(val, decimals=1, suffix=""):
        if val is None:
            return "N/A"
        return f"{float(val):.{decimals}f}{suffix}"

    return f"""You are a macOS system performance analyst. Analyze the metrics below
(collected over the last 5 minutes) and provide:
1. A concise health assessment of the overall system.
2. WindowServer-specific analysis — WindowServer manages all macOS GUI rendering,
   so high CPU or many threads often indicates GPU pressure or compositing load.
3. Any anomalies or concerns.
4. Actionable recommendations (3–5 bullet points).

## System Metrics (5-minute averages)
- Total CPU: avg {fmt(m["avg_cpu"])}%, peak {fmt(m["max_cpu"])}%
- Load avg (1 min): {fmt(m["avg_load"], 2)}
- RAM: {fmt(m["avg_ram_pct"])}% used
- Interrupts/s: {fmt(m["avg_irqs"], 0)}
- Context switches/s: {fmt(m["avg_ctx"], 0)}

## WindowServer Process
- CPU: avg {fmt(m["ws_avg_cpu"])}%, peak {fmt(m["ws_max_cpu"])}%
- Memory: {fmt(m["ws_avg_mem_mb"], 0)} MB
- Active threads: {fmt(m["ws_threads"], 0)}

Keep the response under 300 words and use markdown formatting."""


def analyze(
    db: DatabaseManager,
    model: str,
    anthropic_key: str,
) -> str:
    prompt = build_prompt(db)
    if not prompt:
        return (
            "Insufficient data for analysis. "
            "Please wait a few seconds for metrics to be collected."
        )

    try:
        if not anthropic_key:
            return "Set `ANTHROPIC_API_KEY` in `.env` to enable LLM analysis."
        client = anthropic.Anthropic(api_key=anthropic_key)
        msg = client.messages.create(
            model=model,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        return msg.content[0].text

    except Exception as exc:
        log.error("LLM call failed: %s", exc)
        return f"LLM analysis failed: {exc}"
