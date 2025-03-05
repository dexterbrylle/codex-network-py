FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    gcc \
    python3-dev \
    libpq-dev && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY network_monitor.py .
COPY .env .

# Create directory for logs
RUN mkdir -p /app/logs

# Set environment variable for logs directory
ENV LOG_DIR=/app/logs

# Run the application
CMD ["python", "network_monitor.py"] 