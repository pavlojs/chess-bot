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
6. To stop the bot gracefully: Press `Ctrl+C` (once for clean shutdown, twice for immediate exit)

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


### Modifying Playstyle

The bot's playstyle can be modified by changing settings in `config.py`:

- `STOCKFISH_TIME`: Base thinking time per move in milliseconds (default: `3000` = 3 seconds). Higher values = stronger play.
- `TIME_CONTROL`: List of accepted time controls. Available options: `bullet`, `blitz`, `rapid`, `classical`.
- `ENABLE_MOVE_PREDICTION`: Show Stockfish's predicted continuation (default: `true`). Displays best line analysis.
- `PREDICTION_DEPTH`: Number of moves to predict ahead (default: `10`). Shows strategic plan.
- `UCI_OPTIONS`: Dictionary of UCI options for Stockfish 18+:
  - `"Threads"`: Number of CPU threads to use (1-1024). Default: `4`
  - `"Hash"`: Hash table size in MB (1-33554432). Default: `2048` (2 GB)
  - `"Move Overhead"`: Network latency compensation in ms (0-5000). **Note:** space in key name.
  - `"Ponder"`: True/False to enable pondering.
  
  For full list of available options, run: `/usr/local/bin/stockfish` and type `uci`

Other options can be added as needed. Refer to Stockfish documentation for available UCI options.

### Dynamic Strength Based on Opponent Rating

The bot uses a **HYBRID APPROACH** that combines the best of both worlds for fair, competitive games at all levels. This feature is **enabled by default**.

**How the Hybrid System Works:**

👶 **Beginners & Intermediates (< 1800 ELO):**
- Uses `UCI_LimitStrength` to play at opponent_rating + 100
- Intentionally limits engine to fair playing level
- Example: 1500-rated player faces ~1600 strength bot
- **Result: Fair, winnable games** ✅

🎯 **Advanced Players (1800–2799 ELO):**
- Uses **full-strength Stockfish** (no intentional mistakes)
- Passes real game clocks (`wtime`/`btime`/`winc`/`binc`) directly to Stockfish via native UCI `go` command
- Stockfish manages its own time — accounts for game phase, position complexity, and increment automatically
- **Result: Challenging, high-quality chess** ✅

👑 **Elite & Super-GM (2800+ ELO):**
- **MAXIMUM POWER**: Full strength + native clock management
- No handicaps, no compromises
- Effective strength: ~3200–3500 ELO
- **Result: Ultimate challenge** 🔥

**Why this approach is better:**
- ✅ Fair games for beginners (UCI_LimitStrength ensures balanced play)
- ✅ No blunders for advanced players (full engine quality)
- ✅ Maximum challenge for strong players (full power unlocked)
- ✅ Smooth difficulty progression across all levels

**Configuration options in `config.py`:**
- `DYNAMIC_STRENGTH`: Enable/disable feature (default: `True`)
- `LIMIT_STRENGTH_THRESHOLD`: Below this rating, use UCI_LimitStrength (default: `1800`)
- `FULL_STRENGTH_THRESHOLD`: At or above this rating, use full power (default: `2800`)
- `STRENGTH_ADVANTAGE`: ELO bonus for weak opponents (default: `100`)
- `STOCKFISH_TIME`: Base thinking time in milliseconds (default: `3000`)

**Effective Strength Examples:**

| Opponent Rating | Method | Effective Bot Strength | Notes |
|----------------|--------|----------------------|-------|
| **1200 ELO** | UCI_LimitStrength + movetime | ~1300 ELO | +100 ELO fair play ✅ |
| **1500 ELO** | UCI_LimitStrength + movetime | ~1600 ELO | +100 ELO fair play ✅ |
| **1800 ELO** | Full strength, native clock | ~2000+ ELO | Stockfish manages time ✅ |
| **2000 ELO** | Full strength, native clock | ~2200+ ELO | Stockfish manages time ✅ |
| **2500 ELO** | Full strength, native clock | ~2700+ ELO | Stockfish manages time ✅ |
| **2800 ELO** | **FULL POWER**, native clock | **~3200 ELO** | Maximum power 🔥 |
| **3000 ELO** | **FULL POWER**, native clock | **~3400 ELO** | Maximum power 🔥 |

**To customize:**
```python
# In config.py

# Adjust thresholds
LIMIT_STRENGTH_THRESHOLD = 1600  # Use UCI_LimitStrength below 1600
FULL_STRENGTH_THRESHOLD = 2600   # Full power at 2600+

# Adjust advantage for weak opponents
STRENGTH_ADVANTAGE = 150  # Play 150 ELO above opponent

# Increase base thinking time for stronger play
STOCKFISH_TIME = 5000  # 5 seconds (very strong)

# Or disable dynamic strength for consistent maximum strength
DYNAMIC_STRENGTH = False
```

### Automatic Bot Challenging

The bot can automatically challenge other bots on Lichess when it has no active games. This feature **runs in a separate background thread** and operates independently of the main event stream.

**How it works:**
- ✅ Runs in background thread — doesn't block event processing
- ✅ Automatically challenges online bots when idle (no active games)
- ✅ Respects rate limits (max **5** challenges per hour by default)
- ✅ Only challenges bots within specified ELO range (1500–2900 by default)
- ✅ Uses a variety of time controls (bullet, blitz, rapid, and classical)
- ✅ Also accepts challenges from other bots and human players
- ✅ **Event-driven retry** — reacts immediately to declined/canceled challenges instead of waiting
- ✅ **Decline reason logged** — shows Lichess's reason (e.g. `tooFast`, `later`, `noBot`)
- ✅ **90-second acceptance timeout** — if the opponent never responds, moves on after 90 s
- ✅ **30-second back-off** after a decline before trying a different bot
- ✅ **Instant retry after game ends** — looks for the next challenge the moment a game finishes

**Configuration options in `config.py`:**
- `ENABLE_AUTO_CHALLENGE`: Enable/disable auto-challenge feature (default: `True`)
- `MAX_CHALLENGES_PER_HOUR`: Maximum challenges to send per hour (default: `5`)
- `CHALLENGE_MIN_RATING`: Minimum ELO to challenge (default: `1500`)
- `CHALLENGE_MAX_RATING`: Maximum ELO to challenge (default: `2900`)
- `CHALLENGE_CHECK_INTERVAL`: Idle poll interval when no challenge is pending (default: `60` seconds)
- `CHALLENGE_TIME_CONTROLS`: List of time controls to use when challenging

**Environment variables** (can be set in `.env` file):
```bash
ENABLE_AUTO_CHALLENGE=true
MAX_CHALLENGES_PER_HOUR=5
CHALLENGE_MIN_RATING=1500
CHALLENGE_MAX_RATING=2900
CHALLENGE_CHECK_INTERVAL=60
```

**To customize time controls:**
```python
# In config.py
CHALLENGE_TIME_CONTROLS = [
    {"limit": 60, "increment": 0},    # 1+0 bullet (NEW!)
    {"limit": 60, "increment": 1},    # 1+1 bullet (NEW!)
    {"limit": 120, "increment": 1},   # 2+1 bullet (NEW!)
    {"limit": 180, "increment": 0},   # 3+0 blitz
    {"limit": 300, "increment": 3},   # 5+3 blitz
    {"limit": 600, "increment": 5},   # 10+5 rapid
    {"limit": 900, "increment": 10},  # 15+10 classical
    {"limit": 1800, "increment": 0},  # 30+0 classical
]
```

**Features:**
- 🤖 **Handles manual invitations**: If you log into the bot account on Lichess and manually invite a bot to play, the bot will accept it (if within rating/time control criteria)
- 🎯 **Smart targeting**: Only challenges bots within your specified ELO range
- ⏱️ **Rate limiting**: Respects Lichess API limits with configurable hourly cap
- 🎲 **Variety**: Randomly selects bots and time controls for diverse games
- ⚡ **Event-driven**: Reacts instantly to declines, cancels, and game-end events — no unnecessary waiting
- 📝 **Decline reason**: Logs the Lichess decline reason (e.g. `tooFast`, `later`, `noBot`) for every outgoing challenge that is declined

**To disable auto-challenging:**
```python
# In config.py
ENABLE_AUTO_CHALLENGE = False
```

Or set environment variable:
```bash
export ENABLE_AUTO_CHALLENGE=false
```

### Move Prediction & Analysis

The bot can display Stockfish's predicted continuation (Principal Variation) - showing the best sequence of moves from the current position. This is enabled by default and provides valuable insight into the engine's strategic thinking.

**Example Log Output:**
```
[game123] 🔮 Predicted line (+125 cp): e2e4 e7e5 g1f3 b8c6 f1c4 f8c5
[game456] 🔮 Predicted line (Mate in 3): d1d8 g8h7 d8h8 h7g8 h8g7
```

**What it shows:**
- 🎯 **Move sequence**: The best continuation according to Stockfish
- 📊 **Evaluation**: Position score in centipawns (cp) or mate announcement
- 🧠 **Strategic plan**: Understanding of the engine's multi-move strategy

**Configuration:**
```python
# In config.py
ENABLE_MOVE_PREDICTION = True  # Enable/disable prediction display
PREDICTION_DEPTH = 10          # Number of half-moves to predict ahead
```

**Use cases:**
- 📚 **Learning**: Understand what the engine is planning
- 🐛 **Debugging**: See if engine is calculating correctly
- 📈 **Analysis**: Review games to understand strategic decisions
- 🎓 **Education**: Study engine's long-term plans

**Note:** The prediction is extracted for free from the info line Stockfish already produces during the move search — no second engine call is made. It does not affect move quality, playing strength, or time usage.

### Supported Time Controls

The bot supports all major real-time Lichess time control modes:

- **Bullet**: ⚡ Ultra-fast games (typically < 3 minutes total)
- **Blitz**: Fast games (typically 3-8 minutes total)
- **Rapid**: Medium-paced games (typically 10-25 minutes total)
- **Classical**: Slow games (typically 30+ minutes per side)

**Native Clock Management** ⏱️

For all rated opponents Stockfish receives the real clock values (`wtime`, `btime`, `winc`, `binc`) directly via the UCI `go wtime … btime … winc … binc …` command — the same protocol used by every chess GUI. Stockfish's internal time manager accounts for position complexity, game phase, and increment automatically.

- ✅ Weak opponents (< 1800): fixed `go movetime` budget so `UCI_LimitStrength` keeps games fair
- ✅ All other opponents: native clock mode — Stockfish decides how long to think
- ✅ No-clock fallback: `go movetime` used when game has no clock data

This is strictly better than any manual emergency/pressure formula for bullet, blitz, rapid, and classical alike.

**Automatically rejected:**
- ❌ **Correspondence**: Games with days per move (limit ≥ 259200 seconds)
- ❌ **Unlimited**: Games with no time control (0+0)

You can customize which real-time time controls the bot accepts by editing `TIME_CONTROL` in `config.py`. For example:

```python
TIME_CONTROL = ["classical"]  # Only accept classical games
TIME_CONTROL = ["blitz", "rapid"]  # Accept blitz and rapid only
TIME_CONTROL = ["bullet", "blitz"]  # Fast games only
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

- **Difficulty**: Hybrid dynamic system - adapts method to opponent level
  - **Beginners (< 1800)**: UCI_LimitStrength at opponent+100 ELO (fair games)
  - **Advanced (1800-2799)**: Full strength with scaled time (challenging)
  - **Elite (2800+)**: **MAXIMUM POWER** - full strength + full time
- **Playstyle**: 
  - Fair and balanced for learning players
  - Aggressive and precise for strong opponents
  - Never "gives up" - fights in all positions
- **Endgame**: Uses Syzygy tablebases for perfect play in endgames with up to 7 pieces (if configured)
- **Draw Offers**: Intelligent evaluation system
  - **Accepts** draws only in balanced positions (±200 centipawns)
  - **Declines** draws when winning or losing significantly
  - **Declines** all mate positions - trusts engine calculation
  - Philosophy: Utilize calculation advantage, especially against strong opponents
- **Game Handling**: Properly detects and handles all game endings (resignation, timeout, mate, etc.)

**Effective Strength by Opponent Level:**
- **Beginners to Intermediate** (< 1800): Plays at opponent's level + 100 ELO
- **Advanced** (1800-2799): ~2000-2900 ELO depending on rating and time scaling
- **Elite and Super-GM** (2800+): **~3200-3500 ELO** (Maximum power)

This makes the bot suitable and fair for players of all levels!

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
