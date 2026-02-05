# ♟️ Axiom Chess Bot

A powerful Lichess bot powered by the Stockfish engine with dynamic strength adjustment and intelligent game handling.

![Chess Icon](https://img.shields.io/badge/Chess-♟️-black) ![Stockfish](https://img.shields.io/badge/Powered%20by-Stockfish-blue) ![Lichess](https://img.shields.io/badge/Platform-Lichess-green)

## Play Against the Bot

🤖 **Official Bot Account**: [@Axiom_BOT](https://lichess.org/@/Axiom_BOT)

[![Challenge Axiom_BOT](https://img.shields.io/badge/Challenge-Axiom__BOT-orange?style=for-the-badge&logo=lichess)](https://lichess.org/?user=Axiom_BOT#friend)

The bot accepts challenges in **Bullet**, **Blitz**, **Rapid**, and **Classical** time controls. 

**Note:** The bot automatically rejects:
- ❌ Correspondence games (days per move)
- ❌ Unlimited time games (no clock)
- ✅ Accepts challenges from both human players and other bots

The bot automatically adjusts its strength to match your rating for competitive games!

## Requirements

- Python 3.10 or higher
- Lichess BOT account

## Setup

1. Clone this repository.
2. Install Python dependencies: `pip install -r requirements.txt`
3. Get a Lichess API token from https://lichess.org/account/oauth/token with board:play and bot:play scopes.
4. Set environment variable: `export TOKEN="your_lichess_token"`
5. Run the bot: `python bot.py`

**Stockfish Auto-Update**: The bot automatically downloads and installs the latest Stockfish from GitHub on first run (same method as Docker build). This ensures you're always using the newest version.

- To disable auto-update: set `AUTO_UPDATE_STOCKFISH=false` in your environment or `.env` file
- To use a custom Stockfish binary: set `STOCKFISH_PATH=/path/to/stockfish`

Manual Stockfish installation (if auto-update is disabled):
```bash
./scripts/install_stockfish.sh
```

### How It Works

The bot uses the same Stockfish installation method as the Docker build:
1. On first run, `config.py` calls `stockfish_updater.py`
2. Downloads latest Stockfish from [official GitHub releases](https://github.com/official-stockfish/Stockfish/releases)
3. Extracts and installs to `/usr/local/bin/stockfish`
4. On subsequent runs, checks for updates and upgrades if available

This ensures consistency between local development and Docker deployment.

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
2. Copy `axiom-bot.service` to `/etc/systemd/system/` (adjust paths in the file for your user and directory).
3. Reload systemd: `sudo systemctl daemon-reload`
4. Enable the service: `sudo systemctl enable axiom-bot`
5. Start the service: `sudo systemctl start axiom-bot`
6. Check status: `sudo systemctl status axiom-bot`
7. View logs: `tail -f logs/axiom_bot.log`

### Docker Deployment

[![Build and Push Docker Image](https://github.com/whiteravens20/chess-bot/actions/workflows/build-and-push-docker.yml/badge.svg)](https://github.com/whiteravens20/chess-bot/actions/workflows/build-and-push-docker.yml)

#### Option 1: Using Pre-built Image from GitHub Container Registry

After each successful test run, a Docker image is automatically built and pushed to GitHub Container Registry. You can pull and run it directly:

```bash
# Set your Lichess token
export TOKEN="your_lichess_token"

# Pull and run the latest image
docker run -e TOKEN=$TOKEN ghcr.io/whiteravens20/axiom-chess-bot:latest
```

Or using Docker Compose:

```yaml
services:
  axiom-bot:
    image: ghcr.io/whiteravens20/axiom-chess-bot:latest
    environment:
      - TOKEN=${TOKEN}  # Set TOKEN in .env file or environment
    volumes:
      - ./config.py:/app/config.py  # Mount config for easy editing
    restart: unless-stopped
```

#### Option 2: Build Locally

1. Build and run with Docker Compose: `docker-compose up --build`
2. Or manually: `docker build -t axiom-bot .` then `docker run -e TOKEN=your_token axiom-bot`
3. For persistent config, mount the volume as in `docker-compose.yml`.


## Modifying Playstyle

The bot's playstyle can be modified by changing settings in `config.py`:

- `STOCKFISH_TIME`: Time per move in milliseconds.
- `TIME_CONTROL`: List of accepted time controls. Available options: `bullet`, `blitz`, `rapid`, `classical`.
- `UCI_OPTIONS`: Dictionary of UCI options for Stockfish 18+:
  - `"Threads"`: Number of CPU threads to use (1-1024).
  - `"Hash"`: Hash table size in MB (1-33554432).
  - `"Move Overhead"`: Network latency compensation in ms (0-5000). **Note:** space in key name.
  - `"Ponder"`: True/False to enable pondering.
  - `"UCI_LimitStrength"`: True/False to limit strength (used with dynamic strength feature).
  - `"UCI_Elo"`: Target Elo rating when UCI_LimitStrength is True (800-2850).
  
  For full list of available options, run: `/usr/local/bin/stockfish` and type `uci`

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

The bot supports all major real-time Lichess time control modes:

- **Bullet**: Ultra-fast games (typically < 3 minutes total)
- **Blitz**: Fast games (typically 3-8 minutes total)
- **Rapid**: Medium-paced games (typically 10-25 minutes total)
- **Classical**: Slow games (typically 30+ minutes per side)

**Automatically rejected:**
- ❌ **Correspondence**: Games with days per move (limit ≥ 259200 seconds)
- ❌ **Unlimited**: Games with no time control (0+0)

You can customize which real-time time controls the bot accepts by editing `TIME_CONTROL` in `config.py`. For example:

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

Based on the current configuration in `config.py`, the bot is configured as follows:

- **Difficulty**: Dynamic - automatically adjusts to be ~100 Elo stronger than each opponent (configurable via `STRENGTH_ADVANTAGE`)
- **Playstyle**: Balanced, adapts strength to create competitive games
- **Endgame**: Uses Syzygy tablebases for perfect play in endgames with up to 7 pieces (if configured)
- **Draw Offers**: Evaluates position and accepts if losing badly (< -300 centipawns)
- **Game Handling**: Properly detects and handles all game endings (resignation, timeout, mate, etc.)

This makes the bot suitable for players of all levels, as it automatically adjusts to provide challenging but fair games.

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
