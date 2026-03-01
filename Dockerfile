FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    tzdata \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code and other files
COPY src/ /app/src/
COPY BLUEPRINT.md /app/
# Note: .env and data/ are mounted via docker-compose

# Ensure python can find our src package
ENV PYTHONPATH=/app

CMD ["python", "src/main.py"]
