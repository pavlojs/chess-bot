# Two stages. The first has the tools: a package manager, pip, a shell, curl.
# The second is the image that ships, and has none of them: the Python runtime
# on a distroless base, the bot's modules, its libraries and the engine.
# Whatever gets to run inside it finds no shell to start and nothing to install
# with.

# =========================
# Build stage
# =========================
FROM debian:13.7-slim@sha256:a29215f6a35e51e22adffa17f89e9d2ef06214e64a2bad10d765c46aea49f11f AS build

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        python3 \
        python3-pip \
    && rm -rf /var/lib/apt/lists/*

# Libraries go into a plain directory that the runtime stage takes as it is.
# Debian's Python here is the same minor version as the one in the runtime base.
COPY requirements.txt /src/requirements.txt
RUN python3 -m pip install --no-cache-dir --no-compile --target /out/deps -r /src/requirements.txt

# The engine is one named release, checked against its SHA-256 before it is
# unpacked. The update_stockfish workflow moves both values when Stockfish
# publishes a new release; nothing else changes them.
ARG STOCKFISH_TAG=sf_19
ARG STOCKFISH_SHA256=9defc0d4e55d49c65a6d042f3e571a39fcea499ade6dbe741b53b8c65e03611f
RUN set -eux; \
    asset=stockfish-linux-x86-64-universal; \
    curl -fsSL -o /tmp/stockfish.tar.gz \
      "https://github.com/official-stockfish/Stockfish/releases/download/${STOCKFISH_TAG}/${asset}.tar.gz"; \
    echo "${STOCKFISH_SHA256}  /tmp/stockfish.tar.gz" | sha256sum -c -; \
    mkdir /tmp/stockfish; \
    tar -xzf /tmp/stockfish.tar.gz -C /tmp/stockfish; \
    # Found by name, not by path: the archive's layout has changed between releases.
    bin="$(find /tmp/stockfish -type f -name "$asset" | head -1)"; \
    test -n "$bin"; \
    install -D -m 755 "$bin" /out/stockfish; \
    # Fail the build if the engine cannot run, and record the code path it picked.
    /out/stockfish compiler | head -20; \
    /out/stockfish bench 1 > /dev/null

# An empty log directory, to be handed to the bot's user below.
RUN mkdir /out/logs

# =========================
# Runtime stage
# =========================
# Distroless carries no version tags, so the digest is the whole pin.
FROM gcr.io/distroless/python3-debian13:nonroot@sha256:64e54c4b1200da244d80181d98e86fc01d73c8101f107d5baf472152d8e119a2

WORKDIR /app

# The engine is in the image and the bot cannot replace it, so the self-updater
# is switched off and its module is not shipped.
ENV PYTHONPATH=/app/deps \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    STOCKFISH_PATH=/usr/local/bin/stockfish \
    AUTO_UPDATE_STOCKFISH=false

# Everything below is owned by root and read-only to the bot, except the log
# directory: the one place it writes, besides its heartbeat stamp in /tmp.
COPY --from=build /out/stockfish /usr/local/bin/stockfish
COPY --from=build /out/deps /app/deps
COPY bot.py config.py healthcheck.py logging_config.py /app/
COPY --from=build --chown=65532:65532 /out/logs /app/logs

USER 65532:65532

# Healthy while Lichess has been heard from in the last minute; see healthcheck.py.
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD ["python3", "/app/healthcheck.py"]

# The base image's entrypoint is the Python interpreter.
CMD ["bot.py"]
