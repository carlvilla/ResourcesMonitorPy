CREATE TABLE IF NOT EXISTS system_metrics (
    id         BIGINT AUTO_INCREMENT PRIMARY KEY,
    timestamp  DATETIME(3) NOT NULL,
    cpu_total_percent      FLOAT,
    cpu_user_percent       FLOAT,
    cpu_system_percent     FLOAT,
    cpu_softirq_percent    FLOAT,
    irqs_per_sec           FLOAT,
    ctx_switches_per_sec   FLOAT,
    load_avg_1m            FLOAT,
    io_wait_percent        FLOAT,
    total_ram_used_mb      FLOAT,
    total_ram_percent      FLOAT,
    processes_running      INT,
    processes_blocked      INT,
    INDEX idx_ts (timestamp)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS cpu_core_metrics (
    timestamp    DATETIME(3) NOT NULL,
    core_id      INT NOT NULL,
    cpu_percent  FLOAT,
    PRIMARY KEY (timestamp, core_id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS interrupt_sources (
    timestamp     DATETIME(3) NOT NULL,
    source        VARCHAR(255) NOT NULL,
    count_per_sec FLOAT,
    PRIMARY KEY (timestamp, source)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS process_metrics (
    id                       BIGINT AUTO_INCREMENT PRIMARY KEY,
    timestamp                DATETIME(3) NOT NULL,
    pid                      INT,
    name                     VARCHAR(255),
    cpu_percent              FLOAT,
    memory_mb                FLOAT,
    status                   VARCHAR(50),
    num_threads              INT,
    voluntary_ctx_switches   BIGINT DEFAULT 0,
    involuntary_ctx_switches BIGINT DEFAULT 0,
    INDEX idx_ts (timestamp),
    INDEX idx_name (name)
) ENGINE=InnoDB;

