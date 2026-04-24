"""macOS WindowServer Monitor — Streamlit frontend."""

from __future__ import annotations

import streamlit as st
from config import (
    ANTHROPIC_API_KEY,
    LLM_MODEL,
    TIME_RANGES,
)
from database import DatabaseManager
from llm_analyzer import analyze
from streamlit_autorefresh import st_autorefresh
from widgets import (
    CpuCoreHeatmapWidget,
    CpuPerCoreWidget,
    TopProcessesWidget,
    WindowServerCpuWidget,
)

# ── Page config ────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="macOS Monitor",
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
    st.caption(
        "Charts always show **[now − window, now]**, "
        "merging historical DB rows with live data. "
        "Restarting the app does **not** lose past metrics."
    )

    st.markdown("---")
    st.markdown("**LLM Analysis**")
    run_llm = st.button("🔍 Analyse now", use_container_width=True)

# ── Auto-refresh ───────────────────────────────────────────────────────────
# Fires a JS timer that increments a counter, causing Streamlit to rerun.
# Only active while the checkbox is checked.

if auto_refresh:
    st_autorefresh(interval=2_000, limit=None, key="autorefresh")

# ── Helper: safe float ────────────────────────────────────────────────────


def _f(val, decimals: int = 1, suffix: str = "") -> str:
    if val is None:
        return "—"
    try:
        return f"{float(val):.{decimals}f}{suffix}"
    except TypeError, ValueError:
        return "—"


# ── Top panel (8 real-time metrics) ───────────────────────────────────────

st.markdown("## 🖥️ macOS WindowServer Monitor")
st.markdown('<div class="top-panel">', unsafe_allow_html=True)

sys_latest = db.get_system_latest()
ws_latest = db.get_windowserver_latest()

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
    ws_irqs = irqs_s * (ws_cpu / max(cpu_total, 1))

    c1.metric("Total CPU %", _f(cpu_total, suffix="%"))
    c2.metric("IRQs/s", _f(irqs_s, 0))
    c3.metric("Ctx Switches/s", _f(ctx_s, 0))
    c4.metric("Load Avg (1m)", _f(load_1m, 2))
    c5.metric("IO Wait %", _f(io_wait, suffix="%") if io_wait else "N/A (macOS)")
    c6.metric("RAM Used", f"{ram_mb / 1024:.1f} GB ({_f(ram_pct)}%)")
    c7.metric("Processes (R/D)", f"{p_run} / {p_blk}")
    c8.metric("WS IRQs/s (est.)", _f(ws_irqs, 0))
else:
    for col in (c1, c2, c3, c4, c5, c6, c7, c8):
        col.metric("—", "—")
    st.warning("No data yet — is the collector running on the host?", icon="⚠️")

st.markdown("</div>", unsafe_allow_html=True)

# ── Widget registry ────────────────────────────────────────────────────────
# Add new widgets here — they automatically receive `db` and the selected
# time range.  Order determines render order on the page.

WIDGETS = [
    WindowServerCpuWidget(db),
    CpuCoreHeatmapWidget(db),
    CpuPerCoreWidget(db),
    TopProcessesWidget(db),
]

# ── Widget rendering ───────────────────────────────────────────────────────

# WindowServer CPU gets a dedicated time-range dropdown
ws_widget = WIDGETS[0]
with st.container():
    header_col, sel_col = st.columns([4, 1])
    with header_col:
        st.markdown(
            f'<p class="widget-header">{ws_widget.title}</p>', unsafe_allow_html=True
        )
    with sel_col:
        ws_range = st.selectbox(
            "Range",
            options=list(TIME_RANGES.keys()),
            format_func=lambda k: TIME_RANGES[k]["label"],
            index=list(TIME_RANGES.keys()).index(time_range),
            key="ws_cpu_range",
            label_visibility="collapsed",
        )
    ws_widget.render(st.container(), ws_range)

st.divider()

# Heatmap + per-core side by side
col_left, col_right = st.columns(2)

heatmap_widget = WIDGETS[1]
per_core_widget = WIDGETS[2]

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

# Top processes — full width
top_widget = WIDGETS[3]
st.markdown(f'<p class="widget-header">{top_widget.title}</p>', unsafe_allow_html=True)
top_widget.render(st.container(), time_range)

# Any extra widgets added to WIDGETS beyond index 3 render here automatically
for widget in WIDGETS[4:]:
    st.divider()
    st.markdown(f'<p class="widget-header">{widget.title}</p>', unsafe_allow_html=True)
    widget.render(st.container(), time_range)

# ── LLM Analysis ──────────────────────────────────────────────────────────

st.divider()
st.markdown("### 🤖 LLM Analysis & Recommendations")

if run_llm:
    with st.spinner("Analysing metrics…"):
        result = analyze(
            db,
            model=LLM_MODEL,
            anthropic_key=ANTHROPIC_API_KEY,
        )
    st.markdown(result)
else:
    st.info(
        "Click **Analyse now** in the sidebar to get AI-powered insights "
        "based on the last 5 minutes of metrics.",
        icon="💡",
    )
