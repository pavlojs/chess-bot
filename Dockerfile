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

# Make setup script executable
RUN chmod +x setup_venv.sh

# Run setup (though venv not needed in Docker)
RUN ./setup_venv.sh

# Set environment variable for Lichess token (override at runtime)
ENV TOKEN="your_lichess_token"

# Expose any ports if needed (not for this bot)

# Command to run the bot
CMD ["python", "bot.py"]