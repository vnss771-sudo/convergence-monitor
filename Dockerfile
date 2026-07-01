FROM python:3.11-slim

WORKDIR /app

# Install dependencies first (layer cache)
COPY pyproject.toml constraints.txt ./
RUN pip install --no-cache-dir -c constraints.txt -e .

# Copy source
COPY . .

# Create data directories
RUN mkdir -p data/raw data/processed data/runs data/baselines

ENV LOG_LEVEL=INFO \
    REFRESH_INTERVAL_HOURS=6 \
    CONVERGENCE_STATUS_JSON=data/runs/convergence_latest_status.json

EXPOSE 8080

CMD ["python", "main.py"]
