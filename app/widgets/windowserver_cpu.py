from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from widgets.base import BaseWidget


class WindowServerCpuWidget(BaseWidget):
    """Line/area chart of WindowServer CPU % over the selected time range."""

    @property
    def title(self) -> str:
        return "WindowServer — CPU Usage"

    @property
    def description(self) -> str:
        return "CPU % consumed by the WindowServer process over time."

    def get_data(self, time_range: str) -> pd.DataFrame:
        return self.db.get_windowserver_cpu(time_range)

    def render(self, container, time_range: str) -> None:
        df = self.get_data(time_range)

        with container:
            if df.empty:
                st.info(
                    "No WindowServer data yet. "
                    "Make sure the collector is running on the host."
                )
                return

            peak = df["cpu_percent"].max()
            avg = df["cpu_percent"].mean()

            col_a, col_b = st.columns(2)
            col_a.metric("Average CPU", f"{avg:.1f}%")
            col_b.metric("Peak CPU", f"{peak:.1f}%")

            fig = go.Figure(
                go.Scatter(
                    x=df["ts"],
                    y=df["cpu_percent"],
                    mode="lines",
                    line=dict(color="#FF6B6B", width=2),
                    fill="tozeroy",
                    fillcolor="rgba(255,107,107,0.15)",
                    hovertemplate="%{x|%H:%M:%S}<br>CPU: %{y:.1f}%<extra></extra>",
                )
            )
            fig.update_layout(
                xaxis_title="Time",
                yaxis_title="CPU %",
                yaxis=dict(range=[0, max(peak * 1.25, 10)]),
                height=280,
                margin=dict(l=50, r=20, t=10, b=40),
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
                showlegend=False,
                xaxis=dict(showgrid=True, gridcolor="rgba(128,128,128,0.2)"),
                yaxis_gridcolor="rgba(128,128,128,0.2)",
            )
            st.plotly_chart(fig, use_container_width=True, key=f"ws_cpu_{time_range}")
