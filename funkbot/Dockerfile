# FunkBot — offline agent runtime.
# The model runs on the host (Ollama/llama.cpp); this image is just the agent.
#
#   docker build -t funkbot .
#   docker run --rm -it --network host -v funkbot-data:/app/data funkbot
#
# --network host lets it reach the model server on localhost. No egress needed
# beyond that; nothing here calls out to the internet on its own.

FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
# faster-whisper is optional and heavy; install the core first so a slow wheel
# never blocks a rebuild.
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN git init -q 2>/dev/null || true

ENV FUNKBOT_DATA=/app/data \
    FUNKBOT_BASE_URL=http://localhost:11434/v1 \
    FUNKBOT_MODEL=qwen3:32b \
    FUNKBOT_HOST=0.0.0.0 \
    FUNKBOT_UNATTENDED=deny

EXPOSE 8800
HEALTHCHECK --interval=30s --timeout=5s \
    CMD python -c "import llm,sys; sys.exit(0 if 'UNREACHABLE' not in llm.health() else 1)"

CMD ["python", "server.py"]
