import os

from dotenv import load_dotenv

load_dotenv()

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "127.0.0.1"),
    "port": int(os.getenv("DB_PORT", "3307")),
    "database": os.getenv("DB_NAME", "macmonitor"),
    "user": os.getenv("DB_USER", "monitor"),
    "password": os.getenv("DB_PASSWORD", "monitor123"),
}

# Each entry: seconds of history, bucket size in seconds for grouping
TIME_RANGES: dict[str, dict] = {
    "1m": {"seconds": 60, "bucket": 1, "label": "Last 1 minute"},
    "5m": {"seconds": 300, "bucket": 5, "label": "Last 5 minutes"},
    "15m": {"seconds": 900, "bucket": 15, "label": "Last 15 minutes"},
    "30m": {"seconds": 1800, "bucket": 30, "label": "Last 30 minutes"},
    "1h": {"seconds": 3600, "bucket": 60, "label": "Last 1 hour"},
    "6h": {"seconds": 21600, "bucket": 360, "label": "Last 6 hours"},
    "24h": {"seconds": 86400, "bucket": 1440, "label": "Last 24 hours"},
    "7d": {"seconds": 604800, "bucket": 10080, "label": "Last 7 days"},
    "30d": {"seconds": 2592000, "bucket": 43200, "label": "Last 30 days"},
}

# --- LLM analyzer ------------------------------
PROMPT_LLM_ANALYZER = """You are a system performance analyst. Your objective is to analyze the metrics below (collected over the last 5 minutes) to analyze bootlenecks, detect issues and offer recommendations to a human user. You will generate a report with the following sections:
1. "System Health State": A health assessment of the overall system. Report in a table the most relevant metrics, which are at least, total CPU usage, total RAM usage and processes (R/D). Report any anomalies or concerns.
2. "Top Reasons for Interruptions and High Load": Explain if the number of interruptions and load are currently high and describe the main reasons for that behaviour.
3. "Impact of Process {evaluated_process}": Explain if the process {evaluated_process} is provoking interruptions and a high load in the system.
4. "Recommended solutions": Explain different actions that the user could take to improve the performance of the system given the provided metrics. Make a concise list (3–5 bullet points) to describe each action and the reason to be performed. 

## System Metrics (5-minute averages)
- Total CPU: avg {avg_cpu}%, peak {max_cpu}%
- Load avg: {avg_load}
- RAM: {avg_ram_pct}% used
- Interrupts/s: {avg_irqs}
- Context switches/s: {avg_ctx}

## Process {evaluated_process}
- CPU: avg {ws_avg_cpu}%, peak {ws_max_cpu}%
- Memory: {ws_avg_mem_mb} MB
- Active threads: {ws_threads}

Keep the response concise (under 300 words) and use markdown formatting."""
