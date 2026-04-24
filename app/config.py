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

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "claude-opus-4-5")

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
