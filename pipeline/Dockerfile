FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY config.toml .
COPY src/ ./src/

# Scheduler entrypoint: two clocks + on-demand trigger (see docs/v1-architecture.md §5).
CMD ["python", "-m", "src.main"]
