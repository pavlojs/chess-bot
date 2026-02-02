# Use Python 3.11 slim image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    wget \
    tar \
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
    # Find and download the Ubuntu x86-64 binary
    ASSET_URL=$(curl -s "https://api.github.com/repos/official-stockfish/Stockfish/releases/tags/$VERSION" | grep -o '"browser_download_url": ".*stockfish-ubuntu-x86-64.tar"' | cut -d'"' -f4) && \
    wget -O stockfish/stockfish.tar "$ASSET_URL" && \
    tar -xf stockfish/stockfish.tar -C stockfish && \
    # Find and move the Stockfish executable
    if [ -f stockfish/stockfish-ubuntu-x86-64/stockfish ]; then \
        mv stockfish/stockfish-ubuntu-x86-64/stockfish stockfish/stockfish; \
    else \
        # Check if the extracted directory has a different name
        EXTRACTED_DIR=$(ls -1 stockfish | grep -E 'stockfish.*x86.*64' | head -1); \
        if [ -n "$EXTRACTED_DIR" ] && [ -f "stockfish/$EXTRACTED_DIR/stockfish" ]; then \
            mv "stockfish/$EXTRACTED_DIR/stockfish" stockfish/stockfish; \
        fi; \
    fi && \
    # Cleanup and make executable
    rm -rf stockfish/stockfish.tar stockfish/stockfish-ubuntu-x86-64 stockfish/stockfish-*-x86-64 && \
    chmod +x stockfish/stockfish

# Expose any ports if needed (not for this bot)

# Command to run the bot
CMD ["python", "bot.py"]