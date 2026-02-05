#!/bin/bash
# Install latest Stockfish chess engine from official GitHub releases
# This script uses the same method as the Docker build

set -e

echo "Installing latest Stockfish from GitHub..."

# Create temporary directory
TMP_DIR=$(mktemp -d)
trap "rm -rf $TMP_DIR" EXIT

# Detect OS and architecture
if [[ "$OSTYPE" == "linux-gnu"* ]]; then
    # Detect architecture
    ARCH=$(uname -m)
    if [[ "$ARCH" == "x86_64" ]]; then
        STOCKFISH_BINARY="stockfish-ubuntu-x86-64.tar"
        STOCKFISH_EXEC="stockfish-ubuntu-x86-64"
    elif [[ "$ARCH" == "aarch64" ]] || [[ "$ARCH" == "arm64" ]]; then
        STOCKFISH_BINARY="stockfish-ubuntu-aarch64.tar"
        STOCKFISH_EXEC="stockfish-ubuntu-aarch64"
    else
        echo "Unsupported Linux architecture: $ARCH"
        exit 1
    fi
    INSTALL_PATH="/usr/local/bin/stockfish"
elif [[ "$OSTYPE" == "darwin"* ]]; then
    # macOS
    ARCH=$(uname -m)
    if [[ "$ARCH" == "x86_64" ]]; then
        STOCKFISH_BINARY="stockfish-macos-x86-64.tar"
        STOCKFISH_EXEC="stockfish-macos-x86-64"
    elif [[ "$ARCH" == "arm64" ]]; then
        STOCKFISH_BINARY="stockfish-macos-m1-apple-silicon.tar"
        STOCKFISH_EXEC="stockfish-macos-m1-apple-silicon"
    else
        echo "Unsupported macOS architecture: $ARCH"
        exit 1
    fi
    INSTALL_PATH="/usr/local/bin/stockfish"
else
    echo "Unsupported OS: $OSTYPE"
    echo "Please download manually from: https://github.com/official-stockfish/Stockfish/releases"
    exit 1
fi

echo "Detected: $OSTYPE on $ARCH"
echo "Downloading: $STOCKFISH_BINARY"

# Get latest release download URL
DOWNLOAD_URL=$(curl -s https://api.github.com/repos/official-stockfish/Stockfish/releases/latest \
    | grep -o "\"browser_download_url\": \".*${STOCKFISH_BINARY}\"" \
    | cut -d'"' -f4)

if [ -z "$DOWNLOAD_URL" ]; then
    echo "Error: Could not find download URL for $STOCKFISH_BINARY"
    echo "Available releases: https://github.com/official-stockfish/Stockfish/releases"
    exit 1
fi

echo "Downloading from: $DOWNLOAD_URL"

# Download and extract
cd "$TMP_DIR"
wget -q --show-progress "$DOWNLOAD_URL" -O stockfish.tar
tar -xf stockfish.tar

# Find the extracted stockfish binary
EXTRACTED_BINARY=$(find . -name "$STOCKFISH_EXEC" -type f | head -1)

if [ -z "$EXTRACTED_BINARY" ]; then
    echo "Error: Could not find stockfish binary after extraction"
    ls -la
    exit 1
fi

echo "Found binary: $EXTRACTED_BINARY"

# Install to system
echo "Installing to $INSTALL_PATH"
sudo mv "$EXTRACTED_BINARY" "$INSTALL_PATH"
sudo chmod 755 "$INSTALL_PATH"

# Verify installation
echo ""
echo "✓ Stockfish installed successfully!"
echo "Location: $INSTALL_PATH"
"$INSTALL_PATH" --version 2>&1 | head -1 || "$INSTALL_PATH" compiler 2>&1 | head -1

# Add to config if .env exists
if [ -f .env ]; then
    if ! grep -q "STOCKFISH_PATH" .env; then
        echo "" >> .env
        echo "# Stockfish installation path" >> .env
        echo "STOCKFISH_PATH=\"$INSTALL_PATH\"" >> .env
        echo "Added STOCKFISH_PATH to .env"
    fi
fi

echo ""
echo "To test: $INSTALL_PATH bench 1"
