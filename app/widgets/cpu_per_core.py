from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from widgets.base import BaseWidget

# Distinct colours for up to 16 cores
_CORE_COLOURS = [
    "#FF6B6B", "#4ECDC4", "#45B7D1", "#96CEB4",
    "#FFEAA7", "#DDA0DD", "#98D8C8", "#F7DC6F",
    "#AED6F1", "#A9DFBF", "#F1948A", "#85C1E9",
    "#FAD7A0", "#D7BDE2", "#A3E4D7", "#F9E79F",
]


class CpuPerCoreWidget(BaseWidget):
    """Multi-line chart: one line per CPU core, showing utilisation over time.

    The query window is always [now − time_range, now], so historical data
    from before an app restart is included alongside live samples.
    """

    @property
    def title(self) -> str:
        return "CPU Usage per Core"

    @property
    def description(self) -> str:
        return "Individual core utilisation over time (historical + live)."

    def get_data(self, time_range: str) -> pd.DataFrame:
        return self.db.get_cpu_cores(time_range)

    def render(self, container, time_range: str) -> None:
        df = self.get_data(time_range)

        with container:
            if df.empty:
                st.info("No CPU core data yet. Waiting for collector…")
                return

            fig = go.Figure()
            for core_id in sorted(df["core_id"].unique()):
                core_df = df[df["core_id"] == core_id].sort_values("ts")
                colour = _CORE_COLOURS[int(core_id) % len(_CORE_COLOURS)]
                fig.add_trace(
                    go.Scatter(
                        x=core_df["ts"],
                        y=core_df["cpu_percent"],
                        mode="lines",
                        name=f"Core {core_id}",
                        line=dict(color=colour, width=1.5),
                        hovertemplate=(
                            f"Core {core_id}<br>"
                            "%{x|%H:%M:%S}<br>"
                            "CPU: %{y:.1f}%<extra></extra>"
                        ),
                    )
                )

            num_cores = df["core_id"].nunique()
            fig.update_layout(
                xaxis_title="Time",
                yaxis_title="CPU %",
                yaxis=dict(range=[0, 100]),
                height=320,
                margin=dict(l=50, r=10 + num_cores * 8, t=10, b=40),
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
                legend=dict(
                    orientation="v",
                    yanchor="top",
                    y=1.0,
                    xanchor="left",
                    x=1.01,
                    font=dict(size=11),
                ),
                xaxis=dict(showgrid=True, gridcolor="rgba(128,128,128,0.2)"),
                yaxis_gridcolor="rgba(128,128,128,0.2)",
            )
            st.plotly_chart(fig, use_container_width=True, key=f"cpu_cores_{time_range}")
