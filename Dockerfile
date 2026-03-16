FROM python:3.12-slim

# Run as non-root user
RUN groupadd -r botuser && useradd -r -g botuser botuser

WORKDIR /app

# System deps for compiling native extensions (PyNaCl etc.)
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps before copying source — maximizes Docker layer cache
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy bot source
COPY bot/ ./bot/

RUN chown -R botuser:botuser /app
USER botuser

# No EXPOSE — Fargate task only needs outbound port 443 to Discord and AWS APIs
CMD ["python", "-m", "bot.main"]
