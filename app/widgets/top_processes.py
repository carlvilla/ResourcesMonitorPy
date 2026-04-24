from __future__ import annotations

import pandas as pd
import streamlit as st

from widgets.base import BaseWidget


class TopProcessesWidget(BaseWidget):
    """Table of the top 10 CPU-consuming processes (rolling 10-second window).

    WindowServer rows are highlighted. The ``time_range`` parameter is accepted
    for interface consistency but this widget always shows the most recent
    snapshot so it reflects the current live state.
    """

    @property
    def title(self) -> str:
        return "Top 10 Processes by CPU"

    @property
    def description(self) -> str:
        return "Processes consuming the most CPU right now."

    def get_data(self, time_range: str) -> pd.DataFrame:
        return self.db.get_top_processes()

    def render(self, container, time_range: str) -> None:
        df = self.get_data(time_range)

        with container:
            if df.empty:
                st.info("No process data yet. Waiting for collector…")
                return

            display = df.rename(
                columns={
                    "pid": "PID",
                    "name": "Process",
                    "cpu_percent": "CPU %",
                    "memory_mb": "Memory MB",
                    "status": "Status",
                    "num_threads": "Threads",
                }
            ).copy()

            display["CPU %"] = display["CPU %"].round(1)
            display["Memory MB"] = display["Memory MB"].round(1)
            display["Threads"] = display["Threads"].astype(int)

            def _row_style(row):
                if row["Process"] == "WindowServer":
                    return ["background-color: rgba(255,107,107,0.18)"] * len(row)
                return [""] * len(row)

            styled = (
                display.style.apply(_row_style, axis=1)
                .format({"CPU %": "{:.1f}%", "Memory MB": "{:.1f}"})
                .set_properties(**{"text-align": "right"}, subset=["CPU %", "Memory MB", "Threads"])
            )

            st.dataframe(styled, use_container_width=True, height=390, hide_index=True)
            st.caption("WindowServer rows are highlighted in red. Refreshed every ~2 s.")
