FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim

# Install curl for the healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    libcairo2 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf2.0-0 \
    libglib2.0-0 \
    shared-mime-info \
    fonts-dejavu \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies into a venv outside /app so the runtime bind-mount
# of ./app over /app (see docker-compose.yml) can't hide it.
WORKDIR /opt/project
COPY pyproject.toml uv.lock ./
ENV UV_PROJECT_ENVIRONMENT=/opt/venv
RUN uv sync --frozen --no-dev

# Activate the venv for every subsequent command
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /app

# App source is bind-mounted at runtime (see docker-compose) but also
# copied here so the image works standalone.
COPY app/ .

EXPOSE ${STREAMLIT_SERVER_PORT}

HEALTHCHECK --interval=10s --timeout=5s --retries=5 \
    CMD curl -sf http://localhost:${STREAMLIT_SERVER_PORT}/_stcore/health || exit 1

CMD ["streamlit", "run", "main.py", \
     "--server.address=0.0.0.0", \
     "--server.headless=true", \
     "--browser.gatherUsageStats=false"]
