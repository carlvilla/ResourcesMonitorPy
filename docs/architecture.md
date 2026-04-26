## Container diagram

The collector runs natively
on the host (it needs `psutil`, `ps`, and `sudo powermetrics`), while MySQL and the
Streamlit app run in Docker.

```mermaid
flowchart LR
    subgraph host["Host machine"]
        direction TB
        collector["collector.py"]
        startsh["start.sh / stop.sh"]
        powermetrics
        psutil
    end

    subgraph docker["Docker network"]
        direction TB
        mysql[("mysql:8.4<br/>system_metrics<br/>cpu_core_metrics<br/>process_metrics<br/>interrupt_sources")]
        subgraph streamlit["streamlit container (app/)"]
            direction TB
            main["main.py<br/><i>(Streamlit script)</i>"]
            widgets["widgets/*<br/><i>(BaseWidget subclasses)</i>"]
            db["DatabaseManager<br/><i>(SQLAlchemy)</i>"]
            llm["llm_analyzer.py"]
        end
    end

    browser["Browser<br/><i>localhost:8088</i>"]
    anthropic["LiteLLM"]

    startsh -- "uv run" --> collector
    collector --> powermetrics
    collector --> psutil
    collector -- "INSERT every 1 sec." --> mysql

    main --> widgets
    widgets -- "get_data(time_range)" --> db
    db -- "SELECT (per rerun)" --> mysql
    main -- "LLM Analyse" --> llm
    llm -- "HTTPS" --> anthropic
    browser <-- "WebSocket / HTTP" --> main
```

## Widget class hierarchy

Every chart on the page is a `BaseWidget` subclass. `main.py` instantiates each one with the shared
`DatabaseManager` and calls `render(container, time_range)` to display the widget.

```mermaid
classDiagram
    class BaseWidget {
        <<abstract>>
        +db: DatabaseManager
        +default_time_range: str
        +title* str
        +description* str
        +get_data(time_range)*
        +render(container, time_range)*
    }

    class ProcessCpuWidget
    class CpuBreakdownWidget
    class CpuPerCoreWidget
    class CpuCoreHeatmapWidget
    class InterruptsCtxSwitchesWidget
    class InterruptSourcesWidget
    class TopProcessesWidget

    BaseWidget <|-- ProcessCpuWidget
    BaseWidget <|-- CpuBreakdownWidget
    BaseWidget <|-- CpuPerCoreWidget
    BaseWidget <|-- CpuCoreHeatmapWidget
    BaseWidget <|-- InterruptsCtxSwitchesWidget
    BaseWidget <|-- InterruptSourcesWidget
    BaseWidget <|-- TopProcessesWidget
```
