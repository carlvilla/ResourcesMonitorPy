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

            df_display = df.rename(
                columns={
                    "pid": "PID",
                    "name": "Process",
                    "cpu_percent": "CPU %",
                    "memory_mb": "Memory MB",
                    "status": "Status",
                    "num_threads": "Threads",
                }
            ).copy()

            df_display["CPU %"] = df_display["CPU %"].round(1)
            df_display["Memory MB"] = df_display["Memory MB"].round(1)
            df_display["Threads"] = df_display["Threads"].astype(int)
            st.dataframe(
                df_display, use_container_width=True, height=390, hide_index=True
            )
