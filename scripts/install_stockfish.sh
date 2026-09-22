#!/bin/bash
# Install the latest Stockfish chess engine from official GitHub releases.
# Uses the same universal builds as the Docker image.

set -euo pipefail

echo "Installing latest Stockfish from GitHub..."

TMP_DIR=$(mktemp -d)
trap 'rm -rf "$TMP_DIR"' EXIT

# Stockfish 19 publishes one universal build per platform. It picks its code
# path (AVX2, AVX-512, ...) from the CPU at runtime, unlike the old
# stockfish-ubuntu-* assets, which were the generic SSE2 build.
ARCH=$(uname -m)
case "$OSTYPE" in
    linux-gnu*)
        case "$ARCH" in
            x86_64)          STOCKFISH_EXEC="stockfish-linux-x86-64-universal" ;;
            aarch64|arm64)   STOCKFISH_EXEC="stockfish-linux-arm64-universal" ;;
            riscv64)         STOCKFISH_EXEC="stockfish-linux-riscv64-universal" ;;
            *) echo "Unsupported Linux architecture: $ARCH" >&2; exit 1 ;;
        esac
        ;;
    darwin*)
        # One universal build covers both Intel and Apple Silicon.
        STOCKFISH_EXEC="stockfish-macos-universal"
        ;;
    *)
        echo "Unsupported OS: $OSTYPE" >&2
        echo "Download manually from: https://github.com/official-stockfish/Stockfish/releases" >&2
        exit 1
        ;;
esac

STOCKFISH_ARCHIVE="${STOCKFISH_EXEC}.tar.gz"
INSTALL_PATH="/usr/local/bin/stockfish"

echo "Detected: $OSTYPE on $ARCH"
echo "Downloading: $STOCKFISH_ARCHIVE"

DOWNLOAD_URL=$(curl -fsS https://api.github.com/repos/official-stockfish/Stockfish/releases/latest \
    | grep -o "\"browser_download_url\": \"[^\"]*${STOCKFISH_ARCHIVE}\"" \
    | cut -d'"' -f4)

if [ -z "$DOWNLOAD_URL" ]; then
    echo "Error: could not find a download URL for $STOCKFISH_ARCHIVE" >&2
    echo "Available releases: https://github.com/official-stockfish/Stockfish/releases" >&2
    exit 1
fi

# The URL comes from an API response and ends up executable, so confirm the
# host before fetching it.
case "$DOWNLOAD_URL" in
    https://github.com/official-stockfish/Stockfish/*) ;;
    *) echo "Refusing to download from unexpected URL: $DOWNLOAD_URL" >&2; exit 1 ;;
esac

echo "Downloading from: $DOWNLOAD_URL"

cd "$TMP_DIR"
wget -q --show-progress "$DOWNLOAD_URL" -O stockfish.tar.gz
tar -xzf stockfish.tar.gz

# Locate by search: the archive's directory layout has changed between releases.
EXTRACTED_BINARY=$(find . -name "$STOCKFISH_EXEC" -type f | head -1)

if [ -z "$EXTRACTED_BINARY" ]; then
    echo "Error: could not find $STOCKFISH_EXEC after extraction" >&2
    exit 1
fi

echo "Found binary: $EXTRACTED_BINARY"
echo "Installing to $INSTALL_PATH"
# Root-owned and 755: every user can run the engine, only root can replace
# it. The tarball carries the uploader's uid, so ownership is set here.
sudo install -o root -g root -m 755 "$EXTRACTED_BINARY" "$INSTALL_PATH"

echo ""
echo "✓ Stockfish installed successfully!"
echo "Location: $INSTALL_PATH"
"$INSTALL_PATH" --version 2>&1 | head -1
# Shows which code path this CPU gets. A VM with a generic CPU model hides
# AVX2, so a slow build is visible here rather than only in search speed.
"$INSTALL_PATH" compiler 2>&1 | grep -i "Compilation settings" || true
