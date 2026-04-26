"""Database access layer for the Streamlit app (uses SQLAlchemy + pandas)."""

import logging
from datetime import datetime, timedelta, timezone

import pandas as pd
from config import DB_CONFIG, TIME_RANGES
from sqlalchemy import create_engine, text

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
        return f"FROM_UNIXTIME(FLOOR(UNIX_TIMESTAMP({col}) / {bucket}) * {bucket})"

    # ── Diagnostics ────────────────────────────────────────────────────────

    def get_table_row_counts(self) -> dict[str, int]:
        """Row count for each metrics table (used by the sidebar diagnostics)."""
        tables = (
            "system_metrics",
            "cpu_core_metrics",
            "interrupt_sources",
            "process_metrics",
        )
        counts: dict[str, int] = {}
        for table in tables:
            df = self._query(f"SELECT COUNT(*) AS n FROM {table}")
            counts[table] = int(df.iloc[0]["n"]) if not df.empty else 0
        return counts

    # ── Latest snapshots (top panel) ───────────────────────────────────────

    def get_system_latest(self) -> pd.Series | None:
        df = self._query("SELECT * FROM system_metrics ORDER BY timestamp DESC LIMIT 1")
        return df.iloc[0] if not df.empty else None

    def get_process_latest(self, name: str) -> pd.Series | None:
        df = self._query(
            """
            SELECT *
            FROM process_metrics
            WHERE name = :name
            ORDER BY timestamp DESC
            LIMIT 1
            """,
            {"name": name},
        )
        return df.iloc[0] if not df.empty else None

    def get_process_names(self, lookback_seconds: int = 60) -> list[str]:
        """Distinct process names seen in the last *lookback_seconds*.

        WindowServer (when present) is sorted to the top so it can be
        offered as the default selection.
        """
        df = self._query(
            """
            SELECT name, MAX(cpu_percent) AS peak_cpu
            FROM process_metrics
            WHERE timestamp >= DATE_SUB(UTC_TIMESTAMP(), INTERVAL :lookback SECOND)
              AND name IS NOT NULL AND name <> ''
            GROUP BY name
            ORDER BY peak_cpu DESC
            """,
            {"lookback": lookback_seconds},
        )
        if df.empty:
            return []
        names = df["name"].tolist()
        if "WindowServer" in names:
            names.remove("WindowServer")
            names.insert(0, "WindowServer")
        return names

    # ── Time-series ────────────────────────────────────────────────────────

    def get_process_cpu(self, name: str, time_range_key: str) -> pd.DataFrame:
        since, _ = self._since(time_range_key)
        return self._query(
            """
            SELECT
                timestamp,
                AVG(cpu_percent) AS cpu_percent,
                SUM(voluntary_ctx_switches)   AS voluntary_ctx_switches,
                SUM(involuntary_ctx_switches) AS involuntary_ctx_switches
            FROM process_metrics
            WHERE timestamp >= :since AND name = :name
            GROUP BY timestamp
            ORDER BY timestamp
            """,
            {"since": since, "name": name},
        )

    def get_cpu_cores(self, time_range_key: str) -> pd.DataFrame:
        since, _ = self._since(time_range_key)
        return self._query(
            """
            SELECT
                timestamp,
                core_id,
                cpu_percent
            FROM cpu_core_metrics
            WHERE timestamp >= :since
            ORDER BY timestamp, core_id
            """,
            {"since": since},
        )

    def get_top_interrupt_sources(
        self, time_range_key: str, top_n: int = 5
    ) -> pd.DataFrame:
        since, _ = self._since(time_range_key)
        return self._query(
            f"""
            SELECT
                source,
                AVG(count_per_sec) AS avg_rate,
                MAX(count_per_sec) AS peak_rate
            FROM interrupt_sources
            WHERE timestamp >= :since
            GROUP BY source
            ORDER BY avg_rate DESC
            LIMIT {int(top_n)}
            """,
            {"since": since},
        )

    def get_system_rates(self, time_range_key: str) -> pd.DataFrame:
        since, _ = self._since(time_range_key)
        return self._query(
            """
            SELECT
                timestamp,
                irqs_per_sec,
                ctx_switches_per_sec
            FROM system_metrics
            WHERE timestamp >= :since
            ORDER BY timestamp
            """,
            {"since": since},
        )

    def get_system_history(self, time_range_key: str) -> pd.DataFrame:
        since, _ = self._since(time_range_key)
        return self._query(
            """
            SELECT
                AVG(cpu_user_percent)     AS cpu_user_percent,
                AVG(cpu_system_percent)   AS cpu_system_percent,
                AVG(cpu_softirq_percent)  AS cpu_softirq_percent,
                AVG(io_wait_percent)      AS io_wait_percent
            FROM system_metrics
            WHERE timestamp >= :since
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

    def get_summary_for_llm(
        self, minutes: int = 5, process_name: str = "WindowServer"
    ) -> pd.DataFrame:
        return self._query(
            """
            SELECT
                AVG(sm.cpu_total_percent)    AS avg_cpu,
                MAX(sm.cpu_total_percent)    AS max_cpu,
                AVG(sm.load_avg_1m)          AS avg_load,
                AVG(sm.total_ram_percent)    AS avg_ram_pct,
                AVG(sm.irqs_per_sec)         AS avg_irqs,
                AVG(sm.ctx_switches_per_sec) AS avg_ctx,
                (SELECT AVG(cpu_percent) FROM process_metrics
                 WHERE name = :process_name
                   AND timestamp >= DATE_SUB(UTC_TIMESTAMP(), INTERVAL :minutes MINUTE)
                ) AS proc_avg_cpu,
                (SELECT MAX(cpu_percent) FROM process_metrics
                 WHERE name = :process_name
                   AND timestamp >= DATE_SUB(UTC_TIMESTAMP(), INTERVAL :minutes MINUTE)
                ) AS proc_max_cpu,
                (SELECT AVG(memory_mb) FROM process_metrics
                 WHERE name = :process_name
                   AND timestamp >= DATE_SUB(UTC_TIMESTAMP(), INTERVAL :minutes MINUTE)
                ) AS proc_avg_mem_mb,
                (SELECT AVG(num_threads) FROM process_metrics
                 WHERE name = :process_name
                   AND timestamp >= DATE_SUB(UTC_TIMESTAMP(), INTERVAL :minutes MINUTE)
                ) AS proc_threads
            FROM system_metrics sm
            WHERE sm.timestamp >= DATE_SUB(UTC_TIMESTAMP(), INTERVAL :minutes MINUTE)
            """,
            {"minutes": minutes, "process_name": process_name},
        )
