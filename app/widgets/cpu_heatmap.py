from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from widgets.base import BaseWidget


class CpuCoreHeatmapWidget(BaseWidget):
    """Heatmap: CPU cores (Y) × time buckets (X), coloured by CPU %.

    WindowServer's estimated share is annotated on the colour bar.
    Combines historical DB rows with current real-time data — the query
    window always ends at NOW so the chart updates seamlessly after restarts.
    """

    @property
    def title(self) -> str:
        return "CPU Core Heatmap"

    @property
    def description(self) -> str:
        return "Per-core CPU utilisation over time. Brighter = hotter."

    def get_data(self, time_range: str) -> pd.DataFrame:
        return self.db.get_cpu_cores(time_range)

    def render(self, container, time_range: str) -> None:
        df = self.get_data(time_range)

        with container:
            if df.empty:
                st.info("No CPU core data yet. Waiting for collector…")
                return

            pivot = (
                df.pivot_table(
                    index="core_id",
                    columns="timestamp",
                    values="cpu_percent",
                    aggfunc="mean",
                )
                .fillna(0)
                .sort_index()
            )

            # Keep ≤ 80 columns so the heatmap stays readable
            if pivot.shape[1] > 80:
                step = pivot.shape[1] // 80
                pivot = pivot.iloc[:, ::step]

            y_labels = [f"Core {i}" for i in pivot.index]
            x_labels = [str(t)[:16] for t in pivot.columns]

            fig = go.Figure(
                go.Heatmap(
                    z=pivot.values,
                    x=x_labels,
                    y=y_labels,
                    colorscale="RdYlGn_r",
                    zmin=0,
                    zmax=100,
                    colorbar=dict(title="CPU %", thickness=14),
                    hovertemplate=(
                        "%{y}<br>Time: %{x}<br>CPU: %{z:.1f}%<extra></extra>"
                    ),
                )
            )
            fig.update_layout(
                xaxis_title="Time",
                yaxis_title="CPU Core",
                height=300,
                margin=dict(l=60, r=20, t=10, b=50),
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
            )
            st.plotly_chart(fig, use_container_width=True, key=f"heatmap_{time_range}")
