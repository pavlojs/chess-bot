# 🐦‍⬛ White Raven Chess Bot

A powerful Lichess bot powered by the Stockfish engine, brought to you by the White Ravens team.

![Chess Icon](https://img.shields.io/badge/Chess-♟️-black) ![Stockfish](https://img.shields.io/badge/Powered%20by-Stockfish-blue) ![Lichess](https://img.shields.io/badge/Platform-Lichess-green)

## Setup

1. Clone this repository.
2. Install dependencies: `pip install -r requirements.txt`
3. Get a Lichess API token from https://lichess.org/account/oauth/token with board:play and bot:play scopes.
4. Set environment variable: `export TOKEN="your_lichess_token"`
5. Run the bot: `python bot.py`

## Testing

[![Tests](https://github.com/whiteravens20/chess-bot/actions/workflows/tests.yml/badge.svg)](https://github.com/whiteravens20/chess-bot/actions/workflows/tests.yml)

Run the comprehensive test suite:
```bash
pytest              # Run all tests
pytest -v           # Verbose output
pytest --cov        # With coverage report
```

See [TESTING.md](TESTING.md) for detailed testing guide.

## Deployment

### Running Automatically on System Startup (Linux)

1. Run `./setup_venv.sh` to set up the virtual environment.
2. Copy `chess-bot.service` to `/etc/systemd/system/` (adjust paths in the file for your user and directory).
3. Reload systemd: `sudo systemctl daemon-reload`
4. Enable the service: `sudo systemctl enable chess-bot`
5. Start the service: `sudo systemctl start chess-bot`
6. Check status: `sudo systemctl status chess-bot`
7. View logs: `tail -f logs/chess_bot.log`

### Docker Deployment

[![Build and Push Docker Image](https://github.com/whiteravens20/chess-bot/actions/workflows/build-and-push-docker.yml/badge.svg)](https://github.com/whiteravens20/chess-bot/actions/workflows/build-and-push-docker.yml)

#### Option 1: Using Pre-built Image from GitHub Container Registry

After each successful test run, a Docker image is automatically built and pushed to GitHub Container Registry. You can pull and run it directly:

```bash
# Set your Lichess token
export TOKEN="your_lichess_token"

# Pull and run the latest image
docker run -e TOKEN=$TOKEN ghcr.io/whiteravens-lichess:latest
```

Or using Docker Compose:

```yaml
services:
  chess-bot:
    image: ghcr.io/whiteravens-lichess:latest
    environment:
      - TOKEN=${TOKEN}  # Set TOKEN in .env file or environment
    volumes:
      - ./config.py:/app/config.py  # Mount config for easy editing
    restart: unless-stopped
```

#### Option 2: Build Locally

1. Build and run with Docker Compose: `docker-compose up --build`
2. Or manually: `docker build -t chess-bot .` then `docker run -e TOKEN=your_token chess-bot`
3. For persistent config, mount the volume as in `docker-compose.yml`.


## Modifying Playstyle

The bot's playstyle can be modified by changing settings in `config.py`:

- `STOCKFISH_DEPTH`: Search depth for Stockfish (higher = stronger but slower).
- `STOCKFISH_TIME`: Time per move in milliseconds.
- `TIME_CONTROL`: List of accepted time controls. Available options: `blitz`, `rapid`, `classical` (default: all three).
- `UCI_OPTIONS`: Dictionary of UCI options for Stockfish, such as:
  - `"Skill Level"`: 0-20 (20 is strongest).
  - `"Threads"`: Number of CPU threads to use.
  - `"Hash"`: Hash table size in MB.
  - `"UCI_LimitStrength"`: True/False to limit strength.
  - `"UCI_Elo"`: Target Elo when limiting strength (800-2850).
  - `"Move Overhead"`: Time overhead in ms per move.
  - `"Slow Mover"`: Time management factor (10-1000).
  - `"Contempt"`: Draw avoidance in centipawns.

Other options can be added as needed. Refer to Stockfish documentation for available UCI options.

### Dynamic Strength Based on Opponent Rating

The bot can automatically adjust its strength to be slightly stronger than each opponent, creating more competitive and engaging games. This feature is **enabled by default**.

**How it works:**
- When a challenge is accepted, the bot extracts the opponent's ELO rating
- At game start, the bot calculates its own ELO: `bot_elo = opponent_elo + STRENGTH_ADVANTAGE`
- The bot limits its strength to this calculated rating using Stockfish's `UCI_Elo` option
- All ELO values are automatically bounded between Stockfish's minimum (800) and maximum (2850)

**Configuration options in `config.py`:**
- `DYNAMIC_STRENGTH`: Enable/disable feature (default: `True`)
- `STRENGTH_ADVANTAGE`: How many ELO points stronger than opponent (default: `100`)

**Examples:**
- 1400-rated opponent → bot plays at ~1500 ELO
- 1800-rated opponent → bot plays at ~1900 ELO
- 2800-rated opponent → bot plays at 2850 ELO (capped at maximum)

**To customize:**
```python
# In config.py

# Make bot even stronger relative to opponents
STRENGTH_ADVANTAGE = 150

# Or disable dynamic strength to use static settings from UCI_OPTIONS
DYNAMIC_STRENGTH = False
```

### Supported Time Controls

The bot supports all major Lichess time control modes:

- **Blitz**: Fast games (typically 3+0 to 5+3 minutes)
- **Rapid**: Medium-paced games (typically 10+0 to 25+10 minutes)
- **Classical**: Slow games (typically 30+ minutes per side)

You can customize which time controls the bot accepts by editing `TIME_CONTROL` in `config.py`. For example:

```python
TIME_CONTROL = ["classical"]  # Only accept classical games
TIME_CONTROL = ["blitz", "rapid"]  # Accept blitz and rapid only
TIME_CONTROL = ["blitz", "rapid", "classical"]  # Accept all (default)
```

## Using Syzygy Tablebases

Syzygy tablebases provide perfect play in endgames with up to 7 pieces. To use them:

1. Download tablebases from https://syzygy-tables.info/downloads/
2. Extract files to `./syzygy/` directory in the project root
3. Ensure `SyzygyPath` is set in `config.py` (already configured as `"./syzygy"`)
4. Restart the bot to apply changes

Note: Tablebases are large; start with 3-5 piece files (~10 GB).

## Current Playstyle and Difficulty

Based on the current UCI options in `config.py`, the bot is configured as follows:

- **Difficulty**: Intermediate (limited to approximately 1600 Elo)
- **Playstyle**: Aggressive, with a tendency to avoid draws (Contempt set to 20 centipawns)
- **Endgame**: Uses Syzygy tablebases for perfect play in endgames with up to 7 pieces

This makes the bot suitable for players looking for a challenging but not overwhelming opponent.

## Updating Stockfish

Stockfish is updated regularly in its [official repository](https://github.com/official-stockfish/Stockfish).

### Automated Update
The bot includes a GitHub Actions workflow that automatically checks for new Stockfish releases daily and updates the binary. The workflow downloads the latest Linux x64 binary, places it in `./stockfish/`, and updates `config.py` to use it. Commits are made automatically if an update is found.

To enable this, ensure the repository has GitHub Actions enabled (default for public repos).

### Manual Update
If you prefer to update manually:

1. Download the latest Stockfish binary from the [releases page](https://github.com/official-stockfish/Stockfish/releases).
2. Place the binary in a directory (e.g., `./stockfish/`).
3. In `config.py`, set `STOCKFISH_PATH` to the path of the binary, e.g., `"./stockfish/stockfish"`.
4. Alternatively, update the `stockfish` Python package: `pip install --upgrade stockfish` (this may download a newer version automatically).

Note: Ensure the binary is executable and compatible with your system.

## Credits

This bot is powered by [Stockfish](https://stockfishchess.org/), the strongest open-source chess engine in the world.

**Stockfish License:** Stockfish is released under the GNU General Public License v3.0 (GPL-3.0). You can find the full license text at [https://www.gnu.org/licenses/gpl-3.0.html](https://www.gnu.org/licenses/gpl-3.0.html).

Stockfish is a product of the Stockfish community, with contributions from many developers worldwide. For more information, visit the [official Stockfish website](https://stockfishchess.org/) or the [GitHub repository](https://github.com/official-stockfish/Stockfish).
