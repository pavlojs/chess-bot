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
    # Find and download the Ubuntu x86-64 binary (modern version)
    wget -O stockfish/stockfish.tar.xz "https://github.com/official-stockfish/Stockfish/releases/download/$VERSION/stockfish-ubuntu-x86-64-modern.tar.xz" && \
    # Extract the archive
    tar -xf stockfish/stockfish.tar.xz -C stockfish && \
    # Move the stockfish binary to the expected location
    mv stockfish/stockfish-ubuntu-x86-64-modern/stockfish stockfish/stockfish && \
    # Cleanup
    rm -rf stockfish/stockfish.tar.xz stockfish/stockfish-ubuntu-x86-64-modern && \
    chmod +x stockfish/stockfish && \
    echo "Stockfish installed successfully"

# Expose any ports if needed (not for this bot)

# Command to run the bot
CMD ["python", "bot.py"]