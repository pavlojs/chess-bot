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
    env_file: .env  # Load environment variables from .env file
    volumes:
      - ./config.py:/app/config.py  # Optional: mount config for time-control/challenge customisation
    restart: unless-stopped
```

#### Option 2: Build Locally

1. Copy `.env.example` to `.env` and fill in your `TOKEN` and any settings you want to change.
2. Build and run: `docker-compose up --build`
3. **After changing `.env`** (e.g. `MAX_CHALLENGES_PER_HOUR`): just `docker-compose up -d` — **no rebuild needed**. `env_file` is read fresh on every container start.
4. To rebuild the image (only needed after code changes): `docker-compose up --build`.


### Modifying Playstyle

Most settings can be changed via a `.env` file (copy `.env.example` to `.env`) **without editing any code**. A few options that require a list (e.g. `TIME_CONTROL`, `CHALLENGE_TIME_CONTROLS`) still need to be set in `config.py`.

**Available via `.env` or environment variable:**

- `STOCKFISH_TIME`: Base thinking time per move in ms (default: `3000`). Higher = stronger play.
- `SF_THREADS`: CPU threads for Stockfish (default: `4`).
- `SF_HASH`: Hash table size in MB (default: `2048`).
- `SF_MOVE_OVERHEAD`: Network latency compensation in ms (default: `30`).
- `ENABLE_MOVE_PREDICTION`: Show predicted continuation in logs (default: `true`).
- `PREDICTION_DEPTH`: Half-moves to show in predicted line (default: `10`).
- `DYNAMIC_STRENGTH` / `LIMIT_STRENGTH_THRESHOLD` / `FULL_STRENGTH_THRESHOLD` / `STRENGTH_ADVANTAGE`: see *Dynamic Strength* section below.

**Requires editing `config.py`:**

- `TIME_CONTROL`: List of accepted time control categories. Options: `bullet`, `blitz`, `rapid`, `classical`.
- `CHALLENGE_TIME_CONTROLS`: List of time controls used when auto-challenging bots.
- `UCI_OPTIONS`: Any extra Stockfish UCI options not covered above.

For full Stockfish UCI options, run `/usr/local/bin/stockfish` and type `uci`.

### Dynamic Strength Based on Opponent Rating

The bot uses a **HYBRID APPROACH** that combines the best of both worlds for fair, competitive games at all levels. This feature is **enabled by default**.

**How the Hybrid System Works:**

**Two key rules drive all tiers:**
1. **`UCI_LimitStrength`** (engine quality cap) — active for ALL opponents below `FULL_STRENGTH_THRESHOLD`. The engine plays at `opponent_rating + STRENGTH_ADVANTAGE` ELO, choosing high-quality moves without deliberate blunders.
2. **`go movetime`** (time per move) — fixed budget for all capped opponents. Native clock mode (`go wtime`) **cannot** be used together with `UCI_LimitStrength` (Stockfish would time-manage like a limited human and could hang 30+ seconds on move 1). Native clocks are reserved for full-strength mode only.

---

👶 **Beginners & Intermediates (< 1800 ELO):**
- `UCI_LimitStrength` at opponent+100 ELO
- Minimal `go movetime` (40 % of base, ~1200 ms) — fast moves that don’t intimidate
- Example: 1500-rated player faces a ~1600 strength bot with quick, natural play
- **Result: Fair, winnable games** ✅

🎯 **Advanced Players (1800–2799 ELO):**
- `UCI_LimitStrength` at opponent+100 ELO (same cap, same rule — **no intentional blunders**)
- Scaled `go movetime` (40–95 % of base, proportional to rating)
- More thinking time = plays closer to its ELO ceiling
- Example: 2000-rated player faces a ~2100 strength bot
- **Result: Challenging but humanly beatable chess** ✅

👑 **Elite & Super-GM (2800+ ELO):**
- **No `UCI_LimitStrength`** — full engine quality, maximum depth
- **Native clocks** (`go wtime btime winc binc`) — Stockfish manages time optimally
- Effective strength: ~3200–3500 ELO
- **Result: Ultimate challenge** 🔥

**Why this approach is better:**
- ✅ Fair, winnable games for beginners (ELO-capped at opponent+100, quick moves)
- ✅ Competitive but beatable for advanced players (same ELO cap, more thinking time)
- ✅ Maximum challenge for elite players (full power + native clocks at 2800+)
- ✅ No game aborts — `go movetime` guarantees a reply within the budget

**Configuration options — all settable via `.env` file:**
- `DYNAMIC_STRENGTH`: Enable/disable feature (default: `true`)
- `LIMIT_STRENGTH_THRESHOLD`: Divides minimal-time and scaled-time movetime zones (default: `1800`). Below: 40 % movetime. Above (up to `FULL_STRENGTH_THRESHOLD`): 40–95 % scaled.
- `FULL_STRENGTH_THRESHOLD`: At or above, `UCI_LimitStrength` is disabled and native clocks are used (default: `2800`)
- `STRENGTH_ADVANTAGE`: ELO bonus bot plays above opponent for all below `FULL_STRENGTH_THRESHOLD` (default: `100`)
- `STOCKFISH_TIME`: Base thinking time in ms — movetime budget is a fraction of this (default: `3000`)

**Move timing by tier:**

| Opponent Rating | UCI_LimitStrength | Movetime | Effective Strength |
|----------------|-------------------|----------|--------------------|
| **1200 ELO** | ✅ at ~1300 ELO | 40 % (~1200 ms) | ~1300 ELO ✅ |
| **1500 ELO** | ✅ at ~1600 ELO | 40 % (~1200 ms) | ~1600 ELO ✅ |
| **1800 ELO** | ✅ at ~1900 ELO | 40 % (~1200 ms) | ~1900 ELO ✅ |
| **2000 ELO** | ✅ at ~2100 ELO | 51 % (~1530 ms) | ~2100 ELO ✅ |
| **2500 ELO** | ✅ at ~2600 ELO | 79 % (~2360 ms) | ~2600 ELO ✅ |
| **2800 ELO** | ❌ FULL POWER | native clocks | **~3200 ELO** 🔥 |
| **3000 ELO** | ❌ FULL POWER | native clocks | **~3400 ELO** 🔥 |

**To customize (`.env` file — no code changes needed):**
```bash
# Adjust thresholds
LIMIT_STRENGTH_THRESHOLD=1600   # UCI_LimitStrength below 1600
FULL_STRENGTH_THRESHOLD=2600    # Full power at 2600+

# Adjust ELO bonus
STRENGTH_ADVANTAGE=150          # Play 150 ELO above opponent

# Increase base thinking time for stronger play
STOCKFISH_TIME=5000             # 5 seconds (very strong)

# Or disable dynamic strength for consistent maximum power
DYNAMIC_STRENGTH=false
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

**Configuration (`.env` file — no code changes needed):**
```bash
ENABLE_MOVE_PREDICTION=true   # Enable/disable prediction display
PREDICTION_DEPTH=10           # Number of half-moves to predict ahead
```

**Behaviour detail:**
- The bot **logs** Stockfish's predicted continuation (PV) when `ENABLE_MOVE_PREDICTION` is true.
- To avoid unintentionally strengthening play for lower-rated opponents, the prediction is
  only allowed to *decide the actual played move* when the opponent's rating is at or above
  `PREDICTION_MIN_USE_ELO` (default: 2200). For weaker opponents the PV is logged but the
  engine's regular search result is used for the move.

Behavior for mating predictions:
- If the predicted principal variation contains a mate in N for our side, the bot will prefer to follow the mating continuation (execute the mating pattern) when possible.
- If the predicted principal variation contains a mate in N against our side, the bot will avoid using the predicted continuation as the played move and will instead choose an alternative (defensive) move from the engine search.
- If the predicted evaluation for the bot is worse than `PREDICTION_RECOVER_THRESHOLD` centipawns (default: 400), the bot will attempt a recovery search (longer movetime or alternative engine search) to seek counterplay.

You can override the default thresholds in your `.env`:

```bash
# Only allow predicted moves to be used as the played move vs opponents >= 2200
PREDICTION_MIN_USE_ELO=2200

# Trigger recovery search when predicted eval is worse than -400cp for the bot
PREDICTION_RECOVER_THRESHOLD=400
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

**Move Search** ⏱️

`UCI_LimitStrength` is active for all opponents below `FULL_STRENGTH_THRESHOLD` (2800). Because native clock mode (`go wtime`) combined with `UCI_LimitStrength` causes Stockfish to time-manage like a limited human (potentially hanging 30+ seconds on move 1 and triggering Lichess abort), all capped opponents use **`go movetime`** with a rating-proportional budget instead.

- ✅ All capped opponents (< 2800): `UCI_LimitStrength` at opponent+100 + `go movetime` (40–95 % of base)
- ✅ Full-strength opponents (2800+): no cap, native clocks (`go wtime btime winc binc`)
- ✅ No-clock fallback: `go movetime` used when game has no clock data

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
  - **Advanced (1800-2799)**: UCI_LimitStrength at opponent+100 with scaled movetime (challenging but beatable)
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
- **Advanced** (1800-2799): ~1900-2900 ELO (opponent+100 via UCI_LimitStrength)
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
