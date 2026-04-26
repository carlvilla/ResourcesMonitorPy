"""macOS WindowServer Monitor — Streamlit frontend."""

from __future__ import annotations

import logging
import os

import llm_analyzer
import streamlit as st
from config import TIME_RANGES
from database import DatabaseManager
from streamlit_autorefresh import st_autorefresh
from utils import _fmt, generate_pdf_report
from widgets import (
    CpuBreakdownWidget,
    CpuCoreHeatmapWidget,
    CpuPerCoreWidget,
    InterruptsCtxSwitchesWidget,
    InterruptSourcesWidget,
    ProcessCpuWidget,
    TopProcessesWidget,
)

log = logging.getLogger(__name__)

# Persist across Streamlit reruns (auto-refresh re-executes this script).
if "last_report" not in st.session_state:
    st.session_state["last_report"] = ""
# Auto-refresh is paused while the a call is performed to the LLM
if "autorefresh_paused" not in st.session_state:
    st.session_state["autorefresh_paused"] = False


@st.cache_resource
def _start_debugpy() -> tuple[str, int] | None:
    if os.environ.get("DEBUGPY") != "1":
        return None
    import debugpy

    port = int(os.environ["DEBUGPY_PORT"])
    debugpy.listen(("0.0.0.0", port))
    log.warning("debugpy listening on 0.0.0.0:%d", port)
    return ("0.0.0.0", port)


_start_debugpy()

# ── Page config ────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="ResourcesMonitorPy",
    page_icon="🖥️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    /* tighter metric cards */
    [data-testid="stMetric"] { background: #1e1e2e; border-radius: 8px; padding: 10px 14px; }
    [data-testid="stMetricLabel"] { font-size: 0.78rem !important; color: #a0a0b0 !important; }
    [data-testid="stMetricValue"] { font-size: 1.25rem !important; }
    /* section headers */
    .widget-header { font-size: 1.05rem; font-weight: 600; margin-bottom: 4px; color: #e0e0f0; }
    /* top panel background */
    .top-panel { background: #13131f; border-radius: 10px; padding: 12px 16px; margin-bottom: 16px; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ── Shared database (cached for the lifetime of the server process) ────────


@st.cache_resource
def get_db() -> DatabaseManager:
    return DatabaseManager()


db = get_db()

# ── Sidebar controls ───────────────────────────────────────────────────────


@st.cache_data(show_spinner=False)
def _generate_pdf(report: str):
    """Build a PDF from the given report text. Cached per-report to avoid
    regenerating on every auto-refresh tick."""
    return generate_pdf_report(report)


with st.sidebar:
    st.title("⚙️ Controls")

    auto_refresh = st.checkbox("Auto-refresh", value=True)

    time_range = st.selectbox(
        "Time window",
        options=list(TIME_RANGES.keys()),
        format_func=lambda k: TIME_RANGES[k]["label"],
        index=1,  # default: 5 m
    )

    st.markdown("---")
    st.markdown("**LLM Analysis**")
    run_llm = st.button("🔍 LLM Analyse", width="stretch")
    if st.session_state["last_report"]:
        st.download_button(
            label="⬇️ Download System Report",
            data=_generate_pdf(st.session_state["last_report"]),
            file_name="system_report.pdf",
            mime="application/pdf",
            width="stretch",
        )
    st.markdown("---")
    st.markdown("**Total data collected:**")
    row_counts = db.get_table_row_counts()
    st.markdown(
        "\n".join(
            f"- `{table}`: {count:,} samples" for table, count in row_counts.items()
        )
    )


# ── Auto-refresh ───────────────────────────────────────────────────────────
# Fires a JS timer that increments a counter, causing Streamlit to rerun.
# Only active while the checkbox is checked.

if auto_refresh and not st.session_state["autorefresh_paused"]:
    st_autorefresh(interval=1_000, limit=None, key="autorefresh")

st.markdown("## 🖥️ Resources Analyzer")
st.markdown('<div class="top-panel">', unsafe_allow_html=True)

# ── Top panel (8 real-time metrics) ───────────────────────────────────────

sys_latest = db.get_system_latest()
ws_latest = db.get_process_latest("WindowServer")

(c1, c2, c3, c4, c5, c6, c7, c8) = st.columns(8)

if sys_latest is not None:
    cpu_total = float(sys_latest["cpu_total_percent"] or 0)
    irqs_s = float(sys_latest["irqs_per_sec"] or 0)
    ctx_s = float(sys_latest["ctx_switches_per_sec"] or 0)
    load_1m = float(sys_latest["load_avg_1m"] or 0)
    io_wait = float(sys_latest["io_wait_percent"] or 0)
    ram_pct = float(sys_latest["total_ram_percent"] or 0)
    ram_mb = float(sys_latest["total_ram_used_mb"] or 0)
    p_run = int(sys_latest["processes_running"] or 0)
    p_blk = int(sys_latest["processes_blocked"] or 0)

    # Estimated WindowServer IRQs: proportional to its CPU share
    ws_cpu = float((ws_latest["cpu_percent"] if ws_latest is not None else None) or 0)

    c1.metric("Total CPU %", _fmt(cpu_total, suffix="%"))
    c2.metric("IRQs/s", _fmt(irqs_s, 0))
    c3.metric("Ctx Switches/s", _fmt(ctx_s, 0))
    c4.metric("Load Avg (1m)", _fmt(load_1m, 2))
    c5.metric("IO Wait %", _fmt(io_wait, suffix="%") if io_wait else "N/A (macOS)")
    c6.metric("RAM Used", f"{ram_mb / 1024:.1f} GB ({_fmt(ram_pct)}%)")
    c7.metric("Processes (R/D)", f"{p_run} / {p_blk}")
else:
    # There is no data in the database
    for col in (c1, c2, c3, c4, c5, c6, c7):
        col.metric("—", "—")
    st.warning("No data yet — is the collector running on the host?", icon="⚠️")

st.markdown("</div>", unsafe_allow_html=True)

# ── Widget registry ────────────────────────────────────────────────────────
# Add new widgets here — they automatically receive `db` and the selected
# time range.  Order determines render order on the page.

# ── Widget rendering ───────────────────────────────────────────────────────

# Process CPU usage — dropdown is rendered by the widget itself
process_widget = ProcessCpuWidget(db)
st.markdown(
    f'<p class="widget-header">{process_widget.title}</p>', unsafe_allow_html=True
)
process_widget.render(st.container(), time_range)
st.divider()

# Heatmap + per-core side by side
col_left, col_right = st.columns(2)

heatmap_widget = CpuCoreHeatmapWidget(db)
per_core_widget = CpuPerCoreWidget(db)

with col_left:
    st.markdown(
        f'<p class="widget-header">{heatmap_widget.title}</p>', unsafe_allow_html=True
    )
    heatmap_widget.render(st.container(), time_range)

with col_right:
    st.markdown(
        f'<p class="widget-header">{per_core_widget.title}</p>', unsafe_allow_html=True
    )
    per_core_widget.render(st.container(), time_range)
st.divider()

# CPU breakdown widget
cpu_breakdown_widget = CpuBreakdownWidget(db)
st.markdown(
    f'<p class="widget-header">{cpu_breakdown_widget.title}</p>', unsafe_allow_html=True
)
cpu_breakdown_widget.render(st.container(), time_range)
st.divider()

# Interrupts & context switches over time
interrupts_widget = InterruptsCtxSwitchesWidget(db)
st.markdown(
    f'<p class="widget-header">{interrupts_widget.title}</p>', unsafe_allow_html=True
)
interrupts_widget.render(st.container(), time_range)
st.divider()

# Top interrupt sources (powermetrics)
interrupt_sources_widget = InterruptSourcesWidget(db)
st.markdown(
    f'<p class="widget-header">{interrupt_sources_widget.title}</p>',
    unsafe_allow_html=True,
)
interrupt_sources_widget.render(st.container(), time_range)
st.divider()

# Top processes — full width
top_widget = TopProcessesWidget(db)
st.markdown(f'<p class="widget-header">{top_widget.title}</p>', unsafe_allow_html=True)
top_widget.render(st.container(), time_range)
st.divider()

# ── LLM Analysis ──────────────────────────────────────────────────────────
st.markdown("### 🤖 LLM Analysis & Recommendations")

if run_llm:
    # Decouple the click from the LLM call to avoid the auto-refresh race:
    # set a flag, pause auto-refresh, and trigger a clean rerun where the
    # block below runs without competing with a queued autorefresh tick.
    st.session_state["pending_analysis"] = True
    st.session_state["autorefresh_paused"] = True
    st.rerun()

if st.session_state.get("pending_analysis"):
    st.session_state["pending_analysis"] = False
    selected_process = st.session_state.get("selected_process", "WindowServer")
    with st.spinner(f"Analysing metrics for **{selected_process}**…"):
        report = llm_analyzer.analyze(db, process_name=selected_process)

    if report is None:
        st.error("LLM analysis failed — check the server logs for details.")
    else:
        st.markdown(report)
        st.session_state["last_report"] = report
    # Resume auto-refresh: flip the flag and force a clean rerun so the
    # `st_autorefresh()` call at the top re-installs the JS timer (the
    # paused rerun skipped it, so nothing is currently scheduled).
    st.session_state["autorefresh_paused"] = False
    st.rerun()

elif st.session_state["last_report"]:
    # Re-render the previous report so it persists across auto-refresh ticks.
    st.markdown(st.session_state["last_report"])
else:
    st.info(
        "Click **Analyse now** in the sidebar to get AI-powered insights "
        "based on the last 5 minutes of metrics and the selected process in the top dropdown.",
        icon="💡",
    )
