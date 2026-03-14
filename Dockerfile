# =========================
# Base image
# =========================
FROM ubuntu:24.04

# =========================
# System dependencies
# =========================
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    curl \
    wget \
    tar \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# =========================
# Workdir (UWAGA: noexec OK)
# =========================
WORKDIR /app

# =========================
# Python deps
# =========================
COPY requirements.txt .
RUN pip install --no-cache-dir --break-system-packages -r requirements.txt

# =========================
# App code
# =========================
COPY . .

# =========================
# Stockfish install
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

# =========================
# Sanity check
# =========================
RUN /usr/local/bin/stockfish bench 1 || true

# =========================
# Health check
# =========================
HEALTHCHECK --interval=60s --timeout=10s --retries=3 --start-period=30s \
  CMD python3 -c "import os,time,sys; f='/tmp/axiom_heartbeat'; sys.exit(0 if os.path.exists(f) and time.time()-float(open(f).read())<300 else 1)"

# =========================
# Run bot
# =========================
CMD ["python3", "bot.py"]
