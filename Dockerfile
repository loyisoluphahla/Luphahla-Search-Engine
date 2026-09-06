FROM python:3.12-slim

# Build deps needed to compile trafilatura/lxml, then removed to keep image slim
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libxml2-dev libxslt1-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Non-root user for safety
RUN useradd -m appuser
COPY --chown=appuser:appuser . .
RUN chmod +x /app/startup.sh

USER appuser

EXPOSE 8080
CMD ["/app/startup.sh"]
