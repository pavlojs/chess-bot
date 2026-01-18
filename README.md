# 🐦‍⬛ White Raven Chess Bot

A powerful Lichess bot powered by the Stockfish engine, brought to you by the White Ravens team.

![Chess Icon](https://img.shields.io/badge/Chess-♟️-black) ![Stockfish](https://img.shields.io/badge/Powered%20by-Stockfish-blue) ![Lichess](https://img.shields.io/badge/Platform-Lichess-green)

## Setup

1. Clone this repository.
2. Install dependencies: `pip install -r requirements.txt`
3. Get a Lichess API token from https://lichess.org/account/oauth/token with board:play and bot:play scopes.
4. Edit `config.py` and set your `TOKEN`.
5. Run the bot: `python bot.py`

## Deployment

### Running Automatically on System Startup (Linux)

1. Run `./setup_venv.sh` to set up the virtual environment.
2. Copy `chess-bot.service` to `/etc/systemd/system/` (adjust paths in the file for your user and directory).
3. Reload systemd: `sudo systemctl daemon-reload`
4. Enable the service: `sudo systemctl enable chess-bot`
5. Start the service: `sudo systemctl start chess-bot`
6. Check status: `sudo systemctl status chess-bot`

### Docker Deployment

1. Build and run with Docker Compose: `docker-compose up --build`
2. Or manually: `docker build -t chess-bot .` then `docker run -e TOKEN=your_token chess-bot`
3. For persistent config, mount the volume as in `docker-compose.yml`.

## Modifying Playstyle

The bot's playstyle can be modified by changing settings in `config.py`:

- `STOCKFISH_DEPTH`: Search depth for Stockfish (higher = stronger but slower).
- `STOCKFISH_TIME`: Time per move in milliseconds.
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
