from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from widgets.base import BaseWidget


class InterruptsCtxSwitchesWidget(BaseWidget):
    """Time-series chart of hardware interrupts and context switches per second.

    Both lines share the same y-axis since their magnitudes are comparable on
    typical systems (kernel-event rates in the low thousands).
    """

    @property
    def title(self) -> str:
        return "Interrupts & Context Switches /s"

    @property
    def description(self) -> str:
        return "Hardware interrupts and context switches per second over time."

    def get_data(self, time_range: str) -> pd.DataFrame:
        return self.db.get_system_rates(time_range)

    def render(self, container, time_range: str) -> None:
        df = self.get_data(time_range)

        with container:
            if df.empty:
                st.info("No interrupt/context-switch data yet. Waiting for collector…")
                return

            avg_irqs = df["irqs_per_sec"].mean()
            avg_ctx = df["ctx_switches_per_sec"].mean()
            peak_irqs = df["irqs_per_sec"].max()
            peak_ctx = df["ctx_switches_per_sec"].max()

            col_a, col_b, col_c, col_d = st.columns(4)
            col_a.metric("Avg IRQs/s", f"{avg_irqs:,.0f}")
            col_b.metric("Peak IRQs/s", f"{peak_irqs:,.0f}")
            col_c.metric("Avg Ctx Switches/s", f"{avg_ctx:,.0f}")
            col_d.metric("Peak Ctx Switches/s", f"{peak_ctx:,.0f}")

            fig = go.Figure()
            fig.add_trace(
                go.Scatter(
                    x=df["timestamp"],
                    y=df["irqs_per_sec"],
                    mode="lines",
                    name="IRQs/s",
                    line=dict(color="#4ECDC4", width=2),
                    hovertemplate="%{x|%H:%M:%S}<br>IRQs/s: %{y:,.0f}<extra></extra>",
                )
            )
            fig.add_trace(
                go.Scatter(
                    x=df["timestamp"],
                    y=df["ctx_switches_per_sec"],
                    mode="lines",
                    name="Ctx switches/s",
                    line=dict(color="#FF6B6B", width=2),
                    hovertemplate="%{x|%H:%M:%S}<br>Ctx/s: %{y:,.0f}<extra></extra>",
                )
            )
            fig.update_layout(
                xaxis_title="Time",
                yaxis_title="Events / second",
                height=300,
                margin=dict(l=60, r=20, t=10, b=40),
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
                legend=dict(orientation="h", yanchor="bottom", y=1.0, x=0),
                xaxis=dict(showgrid=True, gridcolor="rgba(128,128,128,0.2)"),
                yaxis_gridcolor="rgba(128,128,128,0.2)",
            )
            st.plotly_chart(
                fig, use_container_width=True, key=f"interrupts_ctx_{time_range}"
            )
