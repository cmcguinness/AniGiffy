FROM python:3.13-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Generating an animation is a long synchronous request: a dozen full-size
# photos have to be decoded, resampled, and palette-quantised once per output
# frame, which runs to a minute or more on a shared vCPU. Gunicorn's default
# 30s timeout kills that mid-render, so the browser only ever sees "generation
# failed". Threads rather than extra workers keep the memory profile of a
# single process -- these are large images -- while still letting a preview or
# a health check be served while a render is in flight.
CMD ["sh", "-c", "gunicorn app:app --bind 0.0.0.0:${PORT:-8080} --worker-class gthread --workers 1 --threads 4 --timeout 300 --graceful-timeout 30"]
