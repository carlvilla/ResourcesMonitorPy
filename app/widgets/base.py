"""Abstract base class for all monitoring widgets.

To add a new widget
-------------------
1. Create ``app/widgets/my_widget.py`` with a class that inherits ``BaseWidget``.
2. Implement ``title``, ``description``, ``get_data()``, and ``render()``.
3. Import and add an instance to the ``WIDGETS`` list in ``app/main.py``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseWidget(ABC):
    """Contract every monitoring widget must fulfill."""

    def __init__(self, db: Any, default_time_range: str = "5m") -> None:
        self.db = db
        self.default_time_range = default_time_range

    # ── Identity ───────────────────────────────────────────────────────────

    @property
    @abstractmethod
    def title(self) -> str:
        """Short human-readable title shown as the widget header."""

    @property
    @abstractmethod
    def description(self) -> str:
        """One-line description of what this widget visualises."""

    # ── Data & rendering ───────────────────────────────────────────────────

    @abstractmethod
    def get_data(self, time_range: str) -> Any:
        """Fetch the data required for this widget from the database.

        Parameters
        ----------
        time_range:
            One of the keys defined in ``config.TIME_RANGES``
            (e.g. ``"5m"``, ``"1h"``).
        """

    @abstractmethod
    def render(self, container: Any, time_range: str) -> None:
        """Draw the widget into *container* (a Streamlit container or module).

        Parameters
        ----------
        container:
            Any Streamlit container: ``st``, ``st.container()``, a column, etc.
        time_range:
            Key from ``config.TIME_RANGES``.
        """
