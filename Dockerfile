# Use Python 3.11 slim image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    wget \
    tar \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Download and extract Stockfish
RUN mkdir -p stockfish && \
    # Get Stockfish version from last_version.txt
    if [ -f last_version.txt ]; then \
        VERSION=$(cat last_version.txt); \
    else \
        VERSION=$(curl -s https://api.github.com/repos/official-stockfish/Stockfish/releases/latest | grep -o '"tag_name": ".*"' | cut -d'"' -f4); \
        echo "$VERSION" > last_version.txt; \
    fi && \
    echo "Downloading Stockfish version: $VERSION" && \
    # Find and download the Ubuntu x86-64 binary
    ASSET_URL=$(curl -s "https://api.github.com/repos/official-stockfish/Stockfish/releases/tags/$VERSION" | grep -o '"browser_download_url": ".*stockfish-ubuntu-x86-64.tar"' | cut -d'"' -f4) && \
    echo "Download URL: $ASSET_URL" && \
    wget -O stockfish/stockfish.tar "$ASSET_URL" && \
    tar -tf stockfish/stockfish.tar && \
    tar -xf stockfish/stockfish.tar -C stockfish && \
    # Find and list extracted contents
    ls -la stockfish/ && \
    # Find and move the Stockfish executable
    STOCKFISH_EXEC=$(find stockfish -name "stockfish" -type f | head -1) && \
    if [ -n "$STOCKFISH_EXEC" ]; then \
        echo "Found Stockfish at: $STOCKFISH_EXEC" && \
        mv "$STOCKFISH_EXEC" stockfish/stockfish; \
    fi && \
    # Cleanup and make executable
    rm -rf stockfish/stockfish.tar stockfish/stockfish-ubuntu-x86-64 stockfish/stockfish-*-x86-64 && \
    chmod +x stockfish/stockfish && \
    ls -la stockfish/stockfish && \
    echo "Stockfish installed successfully"

# Expose any ports if needed (not for this bot)

# Command to run the bot
CMD ["python", "bot.py"]