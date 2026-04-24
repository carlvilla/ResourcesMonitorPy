"""Database access layer for the Streamlit app (uses SQLAlchemy + pandas)."""

import logging
from datetime import datetime, timedelta, timezone

import pandas as pd
from sqlalchemy import create_engine, text

from config import DB_CONFIG, TIME_RANGES

log = logging.getLogger(__name__)


class DatabaseManager:
    def __init__(self):
        url = (
            f"mysql+mysqlconnector://{DB_CONFIG['user']}:{DB_CONFIG['password']}"
            f"@{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}"
        )
        self.engine = create_engine(
            url,
            pool_pre_ping=True,
            pool_recycle=1800,
            pool_size=5,
        )

    # ── Internals ──────────────────────────────────────────────────────────

    def _query(self, sql: str, params: dict | None = None) -> pd.DataFrame:
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text(sql), params or {})
                rows = result.fetchall()
                cols = list(result.keys())
            return pd.DataFrame(rows, columns=cols)
        except Exception as exc:
            log.error("DB query failed: %s", exc)
            return pd.DataFrame()

    @staticmethod
    def _since(time_range_key: str) -> tuple[datetime, int]:
        cfg = TIME_RANGES.get(time_range_key, TIME_RANGES["5m"])
        since = datetime.now(timezone.utc) - timedelta(seconds=cfg["seconds"])
        return since, cfg["bucket"]

    @staticmethod
    def _bucket_expr(col: str, bucket: int) -> str:
        """MySQL expression that floors timestamp to bucket-second intervals."""
        return (
            f"FROM_UNIXTIME(FLOOR(UNIX_TIMESTAMP({col}) / {bucket}) * {bucket})"
        )

    # ── Latest snapshots (top panel) ───────────────────────────────────────

    def get_system_latest(self) -> pd.Series | None:
        df = self._query(
            "SELECT * FROM system_metrics ORDER BY timestamp DESC LIMIT 1"
        )
        return df.iloc[0] if not df.empty else None

    def get_windowserver_latest(self) -> pd.Series | None:
        df = self._query(
            "SELECT * FROM windowserver_metrics ORDER BY timestamp DESC LIMIT 1"
        )
        return df.iloc[0] if not df.empty else None

    # ── Time-series ────────────────────────────────────────────────────────

    def get_windowserver_cpu(self, time_range_key: str) -> pd.DataFrame:
        since, bucket = self._since(time_range_key)
        ts_expr = self._bucket_expr("timestamp", bucket)
        return self._query(
            f"""
            SELECT
                {ts_expr} AS ts,
                AVG(cpu_percent) AS cpu_percent
            FROM windowserver_metrics
            WHERE timestamp >= :since
            GROUP BY FLOOR(UNIX_TIMESTAMP(timestamp) / {bucket})
            ORDER BY ts
            """,
            {"since": since},
        )

    def get_cpu_cores(self, time_range_key: str) -> pd.DataFrame:
        since, bucket = self._since(time_range_key)
        ts_expr = self._bucket_expr("timestamp", bucket)
        return self._query(
            f"""
            SELECT
                {ts_expr} AS ts,
                core_id,
                AVG(cpu_percent) AS cpu_percent
            FROM cpu_core_metrics
            WHERE timestamp >= :since
            GROUP BY FLOOR(UNIX_TIMESTAMP(timestamp) / {bucket}), core_id
            ORDER BY ts, core_id
            """,
            {"since": since},
        )

    def get_system_history(self, time_range_key: str) -> pd.DataFrame:
        since, bucket = self._since(time_range_key)
        ts_expr = self._bucket_expr("timestamp", bucket)
        return self._query(
            f"""
            SELECT
                {ts_expr} AS ts,
                AVG(cpu_total_percent)    AS cpu_total_percent,
                AVG(irqs_per_sec)         AS irqs_per_sec,
                AVG(ctx_switches_per_sec) AS ctx_switches_per_sec,
                AVG(load_avg_1m)          AS load_avg_1m,
                AVG(io_wait_percent)      AS io_wait_percent,
                AVG(total_ram_used_mb)    AS total_ram_used_mb,
                AVG(total_ram_percent)    AS total_ram_percent
            FROM system_metrics
            WHERE timestamp >= :since
            GROUP BY FLOOR(UNIX_TIMESTAMP(timestamp) / {bucket})
            ORDER BY ts
            """,
            {"since": since},
        )

    # ── Top processes (always current) ─────────────────────────────────────

    def get_top_processes(self) -> pd.DataFrame:
        return self._query(
            """
            SELECT
                pid, name,
                AVG(cpu_percent)  AS cpu_percent,
                AVG(memory_mb)    AS memory_mb,
                status,
                ROUND(AVG(num_threads)) AS num_threads
            FROM process_metrics
            WHERE timestamp >= DATE_SUB(UTC_TIMESTAMP(), INTERVAL 10 SECOND)
            GROUP BY pid, name, status
            ORDER BY cpu_percent DESC
            LIMIT 10
            """
        )

    # ── LLM context ────────────────────────────────────────────────────────

    def get_summary_for_llm(self, minutes: int = 5) -> pd.DataFrame:
        return self._query(
            """
            SELECT
                AVG(sm.cpu_total_percent)    AS avg_cpu,
                MAX(sm.cpu_total_percent)    AS max_cpu,
                AVG(sm.load_avg_1m)          AS avg_load,
                AVG(sm.total_ram_percent)    AS avg_ram_pct,
                AVG(sm.irqs_per_sec)         AS avg_irqs,
                AVG(sm.ctx_switches_per_sec) AS avg_ctx,
                AVG(wm.cpu_percent)          AS ws_avg_cpu,
                MAX(wm.cpu_percent)          AS ws_max_cpu,
                AVG(wm.memory_mb)            AS ws_avg_mem_mb,
                AVG(wm.num_threads)          AS ws_threads
            FROM system_metrics sm
            LEFT JOIN windowserver_metrics wm
                ON ABS(TIMESTAMPDIFF(SECOND, sm.timestamp, wm.timestamp)) < 2
            WHERE sm.timestamp >= DATE_SUB(UTC_TIMESTAMP(), INTERVAL :minutes MINUTE)
            """,
            {"minutes": minutes},
        )
