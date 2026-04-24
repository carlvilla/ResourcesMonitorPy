from widgets.base import BaseWidget
from widgets.cpu_heatmap import CpuCoreHeatmapWidget
from widgets.cpu_per_core import CpuPerCoreWidget
from widgets.top_processes import TopProcessesWidget
from widgets.windowserver_cpu import WindowServerCpuWidget

__all__ = [
    "BaseWidget",
    "WindowServerCpuWidget",
    "CpuCoreHeatmapWidget",
    "CpuPerCoreWidget",
    "TopProcessesWidget",
]
