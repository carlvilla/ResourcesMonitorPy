from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from widgets.base import BaseWidget


class ProcessCpuWidget(BaseWidget):
    """Line/area chart of a single process's CPU % over the selected time range.

    A dropdown lists every process seen in `process_metrics` recently;
    WindowServer is the default when present, otherwise the first available.
    """

    @property
    def title(self) -> str:
        return "Process CPU Usage"

    @property
    def description(self) -> str:
        return "CPU % consumed by the selected process over time."

    def get_data(self, time_range: str, name: str) -> pd.DataFrame:  # type: ignore[override]
        return self.db.get_process_cpu(name, time_range)

    def render(self, container, time_range: str) -> None:
        with container:
            names = self.db.get_process_names()
            if not names:
                st.info(
                    "No process data yet. Make sure the collector is running on the host."
                )
                return

            # Stable key (no time_range suffix) so the selection persists across
            # time-range changes AND is readable by other parts of the app
            # (e.g. `main.py` passes it to the LLM analyzer).
            selected = st.selectbox(
                "Process",
                options=names,
                index=0,  # names is sorted with WindowServer first when available
                key="selected_process",
            )

            df = self.get_data(time_range, selected)
            if df.empty:
                st.info(f"No CPU samples for **{selected}** in this window.")
                return

            peak = df["cpu_percent"].max()
            avg = df["cpu_percent"].mean()

            col_a, col_b = st.columns(2)
            col_a.metric("Average CPU", f"{avg:.1f}%")
            col_b.metric("Peak CPU", f"{peak:.1f}%")

            fig = go.Figure(
                go.Scatter(
                    x=df["timestamp"],
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
                yaxis_title="CPU % (of whole system)",
                yaxis=dict(range=[0, 100]),
                height=280,
                margin=dict(l=50, r=20, t=10, b=40),
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
                showlegend=False,
                xaxis=dict(showgrid=True, gridcolor="rgba(128,128,128,0.2)"),
                yaxis_gridcolor="rgba(128,128,128,0.2)",
            )
            st.plotly_chart(
                fig,
                use_container_width=True,
                key=f"process_cpu_{selected}_{time_range}",
            )
