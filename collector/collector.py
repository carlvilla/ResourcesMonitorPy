"""Host-side metric collector — runs natively on macOS to access WindowServer."""

import datetime
import logging
import os
import re
import subprocess
import time
from zoneinfo import ZoneInfo

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
INTERRUPTS_EVERY = 10  # main-loop ticks between powermetrics samples

# Number of logical cores — used to normalize per-process CPU% so a value
# of 100% always means "fully loading the entire system", never one core.
NUM_CORES = psutil.cpu_count(logical=True) or 1


def normalize_process_cpu(cpu_raw: float, num_cores: int = NUM_CORES) -> float:
    """Convert per-core CPU% (psutil/`ps` convention) to whole-system 0-100%.

    Always returns a value in [0, 100] regardless of input — the explicit
    upper clamp is defensive: even if num_cores is miscounted or a sample
    momentarily reports more than num_cores × 100%, the spec ("never
    superar en ninguna gráfica ese 100%") still holds.
    """
    if num_cores < 1:
        num_cores = 1
    return min(max(cpu_raw / num_cores, 0.0), 100.0)


# ── Per-process sample builders ────────────────────────────────────────────
# Both functions return the same `(pid, name, cpu, mem_mb, status, threads)`
# tuple shape so callers (and tests) can treat them interchangeably.
ProcessSample = tuple[int, str, float, float, str, int]


def sample_process_via_psutil(proc) -> ProcessSample | None:
    """Build a homogeneous process sample from a `psutil.Process`-like object.

    Returns None if the process is gone or access-denied. CPU% is always
    normalized to whole-system 0-100% before being returned.
    """
    try:
        info = proc.info
        cpu_raw = info.get("cpu_percent") or 0.0
        mem_info = info.get("memory_info")
        return (
            info.get("pid"),
            (info.get("name") or "")[:255],
            normalize_process_cpu(cpu_raw),
            (mem_info.rss / 1024 / 1024) if mem_info else 0.0,
            (info.get("status") or "")[:50],
            info.get("num_threads") or 0,
        )
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return None


def sample_process_via_ps(
    pid: int, name: str, status: str = "running"
) -> ProcessSample | None:
    """Build a homogeneous process sample for processes psutil cannot read.

    Used for WindowServer (SIP-blocked under macOS). Returns None on failure.
    CPU% is always normalized to whole-system 0-100% before being returned.
    """
    stats = read_process_via_ps(pid)
    if stats is None:
        return None
    cpu_raw, mem_mb, threads = stats
    return (
        pid,
        name[:255],
        normalize_process_cpu(cpu_raw),
        mem_mb,
        status[:50],
        threads,
    )

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


def find_pid_by_name(name: str) -> int | None:
    for p in psutil.process_iter(["pid", "name"]):
        if p.info["name"] == name:
            return p.info["pid"]
    return None


def read_process_via_ps(pid: int) -> tuple[float, float, int] | None:
    """Return (cpu_pct, rss_mb, num_threads) for *pid* via `ps`.

    Used as a fallback for processes that psutil cannot inspect — most
    notably WindowServer, where macOS SIP blocks task_for_pid.
    """
    try:
        out = subprocess.run(
            ["ps", "-o", "%cpu=,rss=", "-p", str(pid)],
            capture_output=True,
            text=True,
            check=True,
            timeout=2,
        ).stdout.strip()
        if not out:
            return None
        cpu_str, rss_str = out.split()
        threads_out = subprocess.run(
            ["ps", "-M", "-p", str(pid)],
            capture_output=True,
            text=True,
            check=True,
            timeout=2,
        ).stdout.splitlines()
        return (
            float(cpu_str),
            float(rss_str) / 1024,  # ps reports RSS in KB
            max(0, len(threads_out) - 1),  # minus header row
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, ValueError):
        return None


# Match lines like:
#   Vector 0x40 (TIMER): 1234 interrupts ...
#   TIMER: 1234
#   IOPMrootDomain: 567 interrupts ...
# Across CPUs the same source name appears multiple times; we sum.
_INTERRUPT_LINE_RE = re.compile(
    r"^\s*(?:Vector\s+0x[0-9a-fA-F]+\s+\(([^)]+)\)|([A-Za-z_][\w\s\-/.]*?))\s*:\s*(\d+)"
)


def collect_interrupt_sources(window_ms: int = 1000) -> dict[str, float]:
    """Sample per-source interrupt rates for *window_ms* via powermetrics.

    Requires passwordless sudo for /usr/bin/powermetrics (configure once via
    /etc/sudoers.d/). Returns {source: events_per_sec}; empty on failure.
    """
    try:
        result = subprocess.run(
            [
                "sudo",
                "-n",
                "powermetrics",
                "--samplers",
                "interrupts",
                "-i",
                str(window_ms),
                "-n",
                "1",
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=window_ms / 1000 + 4,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        log.warning("powermetrics interrupts sampler failed: %s", exc)
        return {}

    seconds = window_ms / 1000.0
    sources: dict[str, float] = {}
    in_block = False
    for line in result.stdout.splitlines():
        if "Interrupt distribution" in line:
            in_block = True
            continue
        if in_block and line.startswith("***") and "Interrupt" not in line:
            in_block = False
            continue
        if not in_block:
            continue
        m = _INTERRUPT_LINE_RE.match(line)
        if not m:
            continue
        name = (m.group(1) or m.group(2) or "").strip()
        if not name or name.lower() in ("cpu", "type", "mode"):
            continue
        count = int(m.group(3))
        sources[name] = sources.get(name, 0.0) + count / seconds
    return sources


def insert_interrupt_sources(cursor, ts, sources: dict[str, float]) -> None:
    if not sources:
        return
    cursor.executemany(
        """
        INSERT INTO interrupt_sources (timestamp, source, count_per_sec)
        VALUES (%s, %s, %s)
        """,
        [(ts, name[:255], rate) for name, rate in sources.items()],
    )


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


def insert_system_metrics(
    cursor,
    ts,
    cpu_total,
    cpu_user,
    cpu_system,
    cpu_softirq,
    irqs_s,
    ctx_s,
    load_avg,
    io_wait,
    vm,
    procs_running,
    procs_blocked,
) -> None:
    cursor.execute(
        """
        INSERT INTO system_metrics
            (timestamp, cpu_total_percent, cpu_user_percent, cpu_system_percent,
                cpu_softirq_percent, irqs_per_sec, ctx_switches_per_sec,
                load_avg_1m, io_wait_percent, total_ram_used_mb, total_ram_percent,
                processes_running, processes_blocked)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """,
        (
            ts,
            cpu_total,
            cpu_user,
            cpu_system,
            cpu_softirq,
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


def insert_process_metrics(cursor, ts, pid, name, cpu, mem, status, threads) -> None:
    cursor.execute(
        """
        INSERT INTO process_metrics
            (timestamp, pid, name, cpu_percent, memory_mb, status, num_threads)
        VALUES (%s,%s,%s,%s,%s,%s,%s)
        """,
        (ts, pid, name, cpu, mem, status, threads),
    )


def collect_and_store(cursor):
    ts = datetime.datetime.now(datetime.UTC)  # .astimezone(ZoneInfo("Europe/Madrid"))

    # ── System ──────────────────────────────────────────────────────────────
    cpu_total = psutil.cpu_percent(interval=None)
    stats = psutil.cpu_stats()
    irqs_s, ctx_s = compute_rates(stats)

    load_avg = psutil.getloadavg()[0]

    try:
        cpu_times = psutil.cpu_times_percent(interval=None)
        io_wait = float(getattr(cpu_times, "iowait", 0.0))
        cpu_user = float(getattr(cpu_times, "user", 0.0))
        cpu_system = float(getattr(cpu_times, "system", 0.0))
        cpu_softirq = float(getattr(cpu_times, "softirq", 0.0))
    except Exception:
        io_wait = cpu_user = cpu_system = cpu_softirq = 0.0

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

    insert_system_metrics(
        cursor,
        ts,
        cpu_total,
        cpu_user,
        cpu_system,
        cpu_softirq,
        irqs_s,
        ctx_s,
        load_avg,
        io_wait,
        vm,
        procs_running,
        procs_blocked,
    )

    # ── CPU per core ────────────────────────────────────────────────────────
    for core_id, pct in enumerate(psutil.cpu_percent(percpu=True, interval=None)):
        cursor.execute(
            "INSERT INTO cpu_core_metrics (timestamp, core_id, cpu_percent) VALUES (%s,%s,%s)",
            (ts, core_id, pct),
        )

    # ── Processes ──────────────────────────────────────────────────────────
    # psutil iteration covers everything it can read; macOS SIP blocks
    # task_for_pid for some system processes (notably WindowServer), so we
    # inject those via `ps` afterwards so they're always represented.
    rows: list[ProcessSample] = []
    for p in psutil.process_iter(
        ["pid", "name", "cpu_percent", "memory_info", "status", "num_threads"]
    ):
        sample = sample_process_via_psutil(p)
        if sample is not None:
            rows.append(sample)

    top = sorted(rows, key=lambda r: r[2], reverse=True)[:TOP_N]
    seen_pids = {r[0] for r in top}
    for sample in top:
        insert_process_metrics(cursor, ts, *sample)

    # Always include WindowServer (psutil cannot read it under SIP in macOS)
    ws_pid = find_pid_by_name("WindowServer")
    if ws_pid and ws_pid not in seen_pids:
        ws_sample = sample_process_via_ps(ws_pid, "WindowServer")
        if ws_sample is not None:
            insert_process_metrics(cursor, ts, *ws_sample)


def cleanup_old_data(cursor):
    log.info("Running data cleanup (keeping 30 days)…")
    for table, days in [
        ("system_metrics", 30),
        ("cpu_core_metrics", 30),
        ("process_metrics", 7),
        ("interrupt_sources", 7),
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
    interrupts_counter = 0

    while True:
        tick_start = time.monotonic()
        try:
            conn = ensure_connected(conn)
            cursor = conn.cursor()
            # Collect CPU and processes information
            collect_and_store(cursor)
            conn.commit()

            # Collect information of interruption sources
            interrupts_counter += 1
            if interrupts_counter >= INTERRUPTS_EVERY:
                ts = datetime.datetime.now(datetime.UTC)
                sources = collect_interrupt_sources()
                insert_interrupt_sources(cursor, ts, sources)
                conn.commit()
                interrupts_counter = 0

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
