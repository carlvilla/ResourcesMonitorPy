from widgets.base import BaseWidget
from widgets.cpu_breakdown import CpuBreakdownWidget
from widgets.cpu_heatmap import CpuCoreHeatmapWidget
from widgets.cpu_per_core import CpuPerCoreWidget
from widgets.interrupt_sources import InterruptSourcesWidget
from widgets.interrupts_ctx_switches import InterruptsCtxSwitchesWidget
from widgets.process_cpu import ProcessCpuWidget
from widgets.top_processes import TopProcessesWidget

__all__ = [
    "BaseWidget",
    "ProcessCpuWidget",
    "CpuCoreHeatmapWidget",
    "CpuPerCoreWidget",
    "CpuBreakdownWidget",
    "InterruptsCtxSwitchesWidget",
    "InterruptSourcesWidget",
    "TopProcessesWidget",
]
