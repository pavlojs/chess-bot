# Syzygy Tablebases for Chess Bot

## What are Syzygy Tablebases?

Syzygy tablebases are precomputed databases that provide perfect play in chess endgames with a limited number of pieces on the board. They cover all positions with up to 7 pieces total (including both kings), allowing the engine to know the exact outcome (win, loss, or draw) and the optimal moves for each position.

### Key Features
- **Perfect Accuracy**: Eliminates guesswork in endgames; the engine plays flawlessly in covered positions.
- **Coverage**: Supports 3 to 7 pieces. For example:
  - 3 pieces: King vs King + piece (e.g., KQK)
  - 4 pieces: King + piece vs King + piece
  - Up to 7 pieces for complex endgames
- **File Types**:
  - **WDL (Win/Draw/Loss)**: Indicates if a position is a win, draw, or loss.
  - **DTZ (Distance to Zero)**: Shows the number of moves to reach a zeroing move (e.g., capture or pawn move that resets the 50-move rule).
- **Integration**: When enabled, Stockfish probes the tablebases during its search. If a position is found, it uses the tablebase result; otherwise, it falls back to normal evaluation.

### Benefits for the Bot
- **Stronger Endgame Play**: The bot becomes unbeatable in endgames with 7 or fewer pieces.
- **No Impact on Middlegame**: Tablebases only activate in endgames, so opening and middlegame play remains unchanged.
- **Draw Awareness**: Helps avoid or force draws in theoretically drawn positions.

### Limitations
- **Storage**: Files are large; 3-5 pieces require ~10 GB, 6 pieces ~100 GB, 7 pieces ~1 TB.
- **No Middlegame Help**: Does not improve play in complex positions.
- **Hardware Requirements**: Faster storage (SSD) improves probe speed.

## How to Use with This Chess Bot

The bot is configured to use Syzygy tablebases if available. Follow these steps to set them up.

### Step 1: Download Tablebases
1. Visit the official Syzygy Tables website: https://syzygy-tables.info/
2. Go to the Downloads page: https://syzygy-tables.info/downloads/
3. Download the required archives:
   - Start with **3-4-5 pieces** (smaller, ~1-10 GB total) for basic coverage.
   - Optionally add **6 pieces** (~100 GB) for more endgames.
   - **7 pieces** is optional and very large (~1 TB).
4. Choose both WDL and DTZ variants for full functionality.
5. Note: Downloads may be via direct links or torrents for large files.

### Step 2: Extract Files
1. Create this `syzygy` directory if it doesn't exist (it should be at the project root, next to `config.py`).
2. Extract the downloaded `.7z` or `.zip` files directly into this directory.
3. Ensure the files are named correctly (e.g., `KQvK.rtbw`, `KQvK.rtbz`).
4. The directory structure should look like:
   ```
   syzygy/
   ├── README.md (this file)
   ├── KQvK.rtbw
   ├── KQvK.rtbz
   ├── KQk.rtbw
   ├── ... (other .rtbw and .rtbz files)
   ```

### Step 3: Verify Configuration
- The bot **auto-detects** Syzygy tablebases: if `./syzygy/` contains `.rtbw`/`.rtbz` files, `SyzygyPath` is added to Stockfish's UCI options automatically.
- To use a custom path, set the `SF_SYZYGY_PATH` environment variable (e.g. `SF_SYZYGY_PATH=/data/syzygy`).
- Restart the bot after adding files for Stockfish to load them.

### Step 4: Test the Setup
1. Run the bot: `python bot.py`
2. Check the console output for messages like "info string Found 1234 tablebases" (indicating successful loading).
3. Play a game and reach an endgame with few pieces; the bot should play perfectly.

### Troubleshooting
- **Files Not Found**: Ensure the tablebase files are in `./syzygy/` or set `SF_SYZYGY_PATH` to the correct directory. The bot runs safely without tablebases.
- **Slow Loading**: Tablebases load at startup; large sets may take time.
- **Incomplete Coverage**: If a position isn't in the tables, Stockfish uses normal evaluation.
- **Errors**: Check Stockfish logs for issues; ensure files are not corrupted.

### Advanced Usage
- **Partial Downloads**: You can download only certain piece counts (e.g., just 5 pieces) to save space.
- **Custom Paths**: Set the `SF_SYZYGY_PATH` environment variable to point to another directory.
- **Performance**: Use SSD storage for faster probes.

For more information, visit the Syzygy Tables website or Stockfish documentation.