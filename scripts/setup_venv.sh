#!/bin/bash

# Setup virtual environment for the chess bot

echo "Setting up virtual environment..."

# Create venv if it doesn't exist
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi

# Activate venv and install dependencies
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

echo "Virtual environment setup complete."
echo "To activate: source venv/bin/activate"
echo "To run the bot: python bot.py"