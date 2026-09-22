# =========================
# Base image
# =========================
FROM ubuntu:24.04

# =========================
# System dependencies
# =========================
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-venv \
    ca-certificates \
    curl \
    wget \
    tar \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# =========================
# Python deps (in a venv, so the system interpreter stays untouched)
# =========================
ENV VIRTUAL_ENV=/opt/venv
ENV PATH="$VIRTUAL_ENV/bin:$PATH"
RUN python3 -m venv "$VIRTUAL_ENV"

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# =========================
# Stockfish install (root-owned, read-only to the bot at runtime)
# =========================
RUN mkdir -p /tmp/stockfish && \
    curl -s https://api.github.com/repos/official-stockfish/Stockfish/releases/latest \
      | grep -o '"browser_download_url": ".*stockfish-ubuntu-x86-64.tar"' \
      | cut -d'"' -f4 \
      | xargs wget -O /tmp/stockfish/stockfish.tar && \
    tar -xf /tmp/stockfish/stockfish.tar -C /tmp/stockfish && \
    mv /tmp/stockfish/stockfish/stockfish-ubuntu-x86-64 /usr/local/bin/stockfish && \
    chmod 755 /usr/local/bin/stockfish && \
    rm -rf /tmp/stockfish

RUN /usr/local/bin/stockfish bench 1 || true

# =========================
# App code
# =========================
COPY . .

# =========================
# Unprivileged runtime user
# =========================
# The engine is already installed and /usr/local/bin is not writable here, so
# the bot points straight at the binary and skips the self-updater. That keeps
# the container from fetching and executing a new binary at runtime.
ENV STOCKFISH_PATH=/usr/local/bin/stockfish
ENV AUTO_UPDATE_STOCKFISH=false

RUN useradd --system --create-home --uid 10001 axiom && \
    mkdir -p /app/logs && \
    chown -R axiom:axiom /app

USER axiom

# =========================
# Health check
# =========================
HEALTHCHECK --interval=60s --timeout=10s --retries=3 --start-period=30s \
  CMD python3 -c "import os,time,sys; f='/tmp/axiom_heartbeat'; sys.exit(0 if os.path.exists(f) and time.time()-float(open(f).read())<300 else 1)"

# =========================
# Run bot
# =========================
CMD ["python3", "bot.py"]
