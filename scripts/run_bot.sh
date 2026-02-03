#!/bin/bash

# Script to run the Axiom bot in virtual environment

# Get the directory of this script
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"

# Activate virtual environment
source "$DIR/venv/bin/activate"

# Run the bot
python "$DIR/bot.py"