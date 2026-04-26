from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from widgets.base import BaseWidget


class InterruptSourcesWidget(BaseWidget):
    """Top 5 hardware interrupt sources (named) by avg rate over the window.

    Data comes from `powermetrics --samplers interrupts` sampled every ~10s
    by the collector. If powermetrics isn't running (sudo not configured,
    macOS only feature), the table will stay empty.
    """

    @property
    def title(self) -> str:
        return "Top 5 Interrupt Sources"

    @property
    def description(self) -> str:
        return "Hardware interrupt sources by average rate (events/s)."

    def get_data(self, time_range: str) -> pd.DataFrame:
        return self.db.get_top_interrupt_sources(time_range, top_n=5)

    def render(self, container, time_range: str) -> None:
        df = self.get_data(time_range)

        with container:
            if df.empty:
                st.info(
                    "No interrupt source data yet. "
                    "Confirm `powermetrics` is running via passwordless sudo "
                    "(see README) and the collector has had at least one cycle."
                )
                return

            df_sorted = df.sort_values("avg_rate", ascending=True)

            fig = go.Figure(
                go.Bar(
                    x=df_sorted["avg_rate"],
                    y=df_sorted["source"],
                    orientation="h",
                    marker_color="#4ECDC4",
                    text=[f"{v:,.0f}/s" for v in df_sorted["avg_rate"]],
                    textposition="outside",
                    hovertemplate=(
                        "%{y}<br>"
                        "Avg: %{x:,.0f}/s<br>"
                        "Peak: %{customdata:,.0f}/s<extra></extra>"
                    ),
                    customdata=df_sorted["peak_rate"],
                )
            )
            fig.update_layout(
                xaxis_title="Events / second (avg)",
                yaxis_title="",
                height=260,
                margin=dict(l=10, r=60, t=10, b=40),
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
                xaxis=dict(showgrid=True, gridcolor="rgba(128,128,128,0.2)"),
            )
            st.plotly_chart(
                fig, use_container_width=True, key=f"interrupt_sources_{time_range}"
            )
