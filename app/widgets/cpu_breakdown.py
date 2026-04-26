from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from widgets.base import BaseWidget

# (column, label, fill color)
_SERIES = [
    ("cpu_user_percent", "User", "#4ECDC4"),
    ("cpu_system_percent", "System", "#FF6B6B"),
    ("io_wait_percent", "IOWait", "#FFD166"),
    ("cpu_softirq_percent", "SoftIRQ", "#A78BFA"),
]


class CpuBreakdownWidget(BaseWidget):
    """Single stacked bar showing average CPU time split for the selected window.

    Series whose value is effectively zero are hidden — on macOS, IOWait and
    SoftIRQ are not exposed and will be omitted automatically.
    """

    @property
    def title(self) -> str:
        return "CPU Global (User/System/IOWait/SoftIRQ)"

    @property
    def description(self) -> str:
        return "Average User / System / IOWait / SoftIRQ CPU time over the window."

    def get_data(self, time_range: str) -> pd.DataFrame:
        return self.db.get_system_history(time_range)

    def render(self, container, time_range: str) -> None:
        df = self.get_data(time_range)

        with container:
            if df.empty:
                st.info("No CPU breakdown data yet. Waiting for collector…")
                return

            row = df.iloc[0]

            fig = go.Figure()
            shown: list[str] = []
            total = 0.0
            for col, label, color in _SERIES:
                if col not in row.index:
                    continue
                value = float(row[col] or 0.0)
                print(f"SHOW {label}, VALUE {value}")
                if value < 0.05:  # treat <0.05% as "not exposed"
                    continue
                fig.add_trace(
                    go.Bar(
                        x=["CPU"],
                        y=[value],
                        name=label,
                        marker_color=color,
                        text=[f"{value:.1f}%"],
                        textposition="inside",
                        hovertemplate=f"{label}: {value:.2f}%<extra></extra>",
                    )
                )
                shown.append(label)
                total += value

            if not shown:
                st.info("No non-zero CPU breakdown series in this window.")
                return

            fig.update_layout(
                barmode="stack",
                xaxis=dict(visible=False),
                yaxis=dict(title="CPU %", range=[0, max(total * 1.1, 5)]),
                height=320,
                margin=dict(l=50, r=20, t=10, b=20),
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
                legend=dict(orientation="h", yanchor="bottom", y=1.0, x=0),
                bargap=0.6,
            )
            st.plotly_chart(
                fig, use_container_width=True, key=f"cpu_breakdown_{time_range}"
            )
            hidden = [s for _, s, _ in _SERIES if s not in shown]
            if hidden:
                st.caption(f"Hidden (not exposed by this kernel): {', '.join(hidden)}.")
