FROM python:3.11-slim

# Install core utilities
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Pre-install dependencies to cache layer
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Create volume target dirs
RUN mkdir -p /app/data /root/.mitmproxy

# Configure storage destinations
ENV DB_DIR=/app/data
ENV MITMPROXY_CERT_PATH=/root/.mitmproxy/mitmproxy-ca-cert.pem

# Copy codebase
COPY . .

# Expose FastAPI (8000) and mitmproxy listener (8080)
EXPOSE 8000 8080

# Run orchestrator
CMD ["python", "start.py"]
