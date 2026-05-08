FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    gcc \
    python3-dev \
    libpq-dev && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY monitor/ monitor/
COPY main.py .
COPY .env .

RUN mkdir -p /app/logs
ENV LOG_DIR=/app/logs

CMD ["uv", "run", "python", "main.py"]
