"""Host-side metric collector — runs natively on macOS to access WindowServer."""

import logging
import os
import subprocess
import time
from datetime import datetime

import mysql.connector
import psutil
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "127.0.0.1"),
    "port": int(os.getenv("DB_PORT", "3307")),
    "database": os.getenv("DB_NAME", "macmonitor"),
    "user": os.getenv("DB_USER", "monitor"),
    "password": os.getenv("DB_PASSWORD", "monitor123"),
}

COLLECT_INTERVAL = 1.0
TOP_N = 10
CLEANUP_EVERY = 3600  # seconds

_ws_warned = False  # log WindowServer access failure only once

# Rolling counters for rate calculations
_prev_interrupts: int | None = None
_prev_ctx_switches: int | None = None
_prev_mono: float | None = None


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------


def connect_with_retry() -> mysql.connector.MySQLConnection:
    while True:
        try:
            conn = mysql.connector.connect(**DB_CONFIG)
            log.info(
                "Connected to MySQL at %s:%s", DB_CONFIG["host"], DB_CONFIG["port"]
            )
            return conn
        except mysql.connector.Error as exc:
            log.warning("MySQL not ready (%s), retrying in 5 s…", exc)
            time.sleep(5)


def ensure_connected(conn):
    try:
        if not conn.is_connected():
            conn.reconnect(attempts=3, delay=2)
    except Exception:
        pass
    return conn


# ---------------------------------------------------------------------------
# Metric helpers
# ---------------------------------------------------------------------------


def find_windowserver_pid() -> int | None:
    for p in psutil.process_iter(["pid", "name"]):
        try:
            if p.info["name"] == "WindowServer":
                return p.info["pid"]
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return None


def read_windowserver_stats(pid: int) -> tuple[float, float, int] | None:
    """Return (cpu_percent, rss_mb, num_threads) via `ps` — works without root.

    psutil's Process.cpu_percent/memory_info/threads() require task_for_pid,
    which macOS SIP blocks for WindowServer even when running as root.
    `ps` reads KERN_PROC via sysctl and is not SIP-gated.
    """
    try:
        out = subprocess.run(
            ["ps", "-o", "%cpu=,rss=", "-p", str(pid)],
            capture_output=True, text=True, check=True, timeout=2,
        ).stdout.strip()
        if not out:
            return None
        cpu_str, rss_str = out.split()
        cpu_pct = float(cpu_str)
        rss_mb = float(rss_str) / 1024  # ps reports RSS in KB

        threads_out = subprocess.run(
            ["ps", "-M", "-p", str(pid)],
            capture_output=True, text=True, check=True, timeout=2,
        ).stdout.splitlines()
        num_threads = max(0, len(threads_out) - 1)  # minus header
        return cpu_pct, rss_mb, num_threads
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, ValueError):
        return None


def compute_rates(stats):
    """Return (irqs/s, ctx/s) since last call, update globals."""
    global _prev_interrupts, _prev_ctx_switches, _prev_mono

    now = time.monotonic()
    irqs_s = ctx_s = 0.0

    if _prev_mono is not None:
        dt = now - _prev_mono
        if dt > 0:
            irqs_s = max(0.0, (stats.interrupts - _prev_interrupts) / dt)
            ctx_s = max(0.0, (stats.ctx_switches - _prev_ctx_switches) / dt)

    _prev_interrupts = stats.interrupts
    _prev_ctx_switches = stats.ctx_switches
    _prev_mono = now
    return irqs_s, ctx_s


# ---------------------------------------------------------------------------
# Collection & insertion
# ---------------------------------------------------------------------------


def collect_and_store(cursor):
    ts = datetime.utcnow()

    # ── System ──────────────────────────────────────────────────────────────
    cpu_total = psutil.cpu_percent(interval=None)
    stats = psutil.cpu_stats()
    irqs_s, ctx_s = compute_rates(stats)

    load_avg = psutil.getloadavg()[0]

    try:
        cpu_times = psutil.cpu_times_percent(interval=None)
        io_wait = float(getattr(cpu_times, "iowait", 0.0))
    except Exception:
        io_wait = 0.0

    vm = psutil.virtual_memory()

    procs_running = procs_blocked = 0
    for p in psutil.process_iter(["status"]):
        try:
            s = p.info["status"]
            if s == psutil.STATUS_RUNNING:
                procs_running += 1
            elif s in (psutil.STATUS_DISK_SLEEP, psutil.STATUS_WAITING):
                procs_blocked += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    cursor.execute(
        """
        INSERT INTO system_metrics
            (timestamp, cpu_total_percent, irqs_per_sec, ctx_switches_per_sec,
             load_avg_1m, io_wait_percent, total_ram_used_mb, total_ram_percent,
             processes_running, processes_blocked)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """,
        (
            ts,
            cpu_total,
            irqs_s,
            ctx_s,
            load_avg,
            io_wait,
            vm.used / 1024 / 1024,
            vm.percent,
            procs_running,
            procs_blocked,
        ),
    )

    # ── CPU per core ────────────────────────────────────────────────────────
    for core_id, pct in enumerate(psutil.cpu_percent(percpu=True, interval=None)):
        cursor.execute(
            "INSERT INTO cpu_core_metrics (timestamp, core_id, cpu_percent) VALUES (%s,%s,%s)",
            (ts, core_id, pct),
        )

    # ── WindowServer ────────────────────────────────────────────────────────
    global _ws_warned
    pid = find_windowserver_pid()
    stats = read_windowserver_stats(pid) if pid else None
    if stats:
        ws_cpu, ws_mem_mb, num_threads = stats
        ws_mem_pct = (ws_mem_mb * 1024 * 1024) / vm.total * 100
        cursor.execute(
            """
            INSERT INTO windowserver_metrics
                (timestamp, cpu_percent, memory_mb, memory_percent, num_threads)
            VALUES (%s,%s,%s,%s,%s)
            """,
            (ts, ws_cpu, ws_mem_mb, ws_mem_pct, num_threads),
        )
    elif not _ws_warned:
        log.warning("WindowServer stats unavailable (pid=%s)", pid)
        _ws_warned = True

    # ── Top processes ────────────────────────────────────────────────────────
    rows = []
    for p in psutil.process_iter(
        ["pid", "name", "cpu_percent", "memory_info", "status", "num_threads"]
    ):
        try:
            info = p.info
            rows.append(
                (
                    info["pid"],
                    (info["name"] or "")[:255],
                    info["cpu_percent"] or 0.0,
                    (info["memory_info"].rss / 1024 / 1024)
                    if info["memory_info"]
                    else 0.0,
                    (info["status"] or "")[:50],
                    info["num_threads"] or 0,
                )
            )
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    top = sorted(rows, key=lambda r: r[2], reverse=True)[:TOP_N]
    for pid, name, cpu, mem, status, threads in top:
        cursor.execute(
            """
            INSERT INTO process_metrics
                (timestamp, pid, name, cpu_percent, memory_mb, status, num_threads)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
            """,
            (ts, pid, name, cpu, mem, status, threads),
        )


def cleanup_old_data(cursor):
    log.info("Running data cleanup (keeping 30 days)…")
    for table, days in [
        ("system_metrics", 30),
        ("windowserver_metrics", 30),
        ("cpu_core_metrics", 30),
        ("process_metrics", 7),
        ("windowserver_thread_metrics", 7),
    ]:
        cursor.execute(
            f"DELETE FROM {table} WHERE timestamp < DATE_SUB(UTC_TIMESTAMP(), INTERVAL %s DAY)",
            (days,),
        )


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------


def main():
    log.info("macOS Monitor Collector starting…")

    # First calls always return 0 — warm up psutil counters
    psutil.cpu_percent(interval=None)
    psutil.cpu_percent(percpu=True, interval=None)
    time.sleep(0.5)

    conn = connect_with_retry()
    cursor = conn.cursor()

    cleanup_counter = 0

    while True:
        tick_start = time.monotonic()
        try:
            conn = ensure_connected(conn)
            cursor = conn.cursor()
            collect_and_store(cursor)
            conn.commit()

            cleanup_counter += 1
            if cleanup_counter >= CLEANUP_EVERY:
                cleanup_old_data(cursor)
                conn.commit()
                cleanup_counter = 0

        except mysql.connector.Error as exc:
            log.error("MySQL error: %s — reconnecting…", exc)
            try:
                conn.close()
            except Exception:
                pass
            conn = connect_with_retry()
            cursor = conn.cursor()
        except Exception as exc:
            log.error("Collection error: %s", exc, exc_info=True)

        elapsed = time.monotonic() - tick_start
        time.sleep(max(0.0, COLLECT_INTERVAL - elapsed))


if __name__ == "__main__":
    main()
