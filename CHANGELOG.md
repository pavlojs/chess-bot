# Changelog

All notable changes to Axiom Chess Bot are documented in this file.

## [2.8.0] - 2026-04-13

### Fixed

- **First-move clock cap not applied for black (game EGoLgicZ):** The condition `board.fullmove_number <= 1 and len(board.move_stack) == 0` was only true for white on an empty board. When playing as black, `len(board.move_stack) == 1` after the opponent's first move, so the 15-second cap never applied. Stockfish allocated 48 seconds for move 1, Lichess aborted after ~31 seconds. Fixed by checking `len(board.move_stack) == 1` for black's first move.
- **SyzygyPath not configured despite docs claiming it was:** Both `README.md` and `syzygy/README.md` stated that `SyzygyPath` was "already configured" in `config.py`'s `UCI_OPTIONS`, but it was never actually set. Added auto-detection: if `./syzygy/` (or `SF_SYZYGY_PATH` env var) contains `.rtbw`/`.rtbz` tablebase files, `SyzygyPath` is automatically added to Stockfish's UCI options. Updated both docs to reflect the new auto-detection behavior.
- **Time control comment wrong for 15+10:** Config comment labeled `{"limit": 900, "increment": 10}` as "classical", but `determine_time_category()` classifies it as "rapid" (total = 900 + 10×40 = 1300 < 1500).
- **Misleading "No active games" log in challenge loop:** Log message said "No active games — looking for a bot to challenge..." even when games were active (just below the concurrent limit).
- **Misleading "Opponent played" log on reconnect:** `gameState` events include ALL moves from the start of the game. On reconnect, the bot's own moves were logged as "Opponent played". Changed to neutral "Move received".

### Changed

- **`requirements.txt` modernized:** Replaced `python-chess` shim with `chess` (the actual library). Added `requests` (was used but not listed). Added minimum version pins for all dependencies.

### Added

- **14 new tests (189 total):** `TestFirstMoveClockCap` (5 tests — black first move, white first move, second move not capped, btime cap applied), `TestSyzygyPathConfig` (4 tests), `TestTimeCategoryClassification` (5 tests).

## [2.7.0] - 2026-04-13

### Fixed

- **Game stuck in "started" blocking all other games indefinitely:** When an opponent never made a move (e.g. game IrnHNCsK stuck for 14+ hours), the watchdog kept logging "game still active (started)" but never took action. The bot was permanently blocked because `MAX_CONCURRENT_GAMES` was exhausted. The watchdog now tracks how long a game stays in "started" status and forcefully aborts it after `GAME_WATCHDOG_ABORT_TIMEOUT` seconds (default: 600). Falls back to resign if abort fails.
- **Challenge loop never challenged with any game active:** `challenge_loop` used `active_count > 0` to skip challenging, which meant with `MAX_CONCURRENT_GAMES=2` the bot would never send challenges while any game was running. Fixed to `active_count >= MAX_CONCURRENT_GAMES` so the bot challenges when slots are available.
- **Stockfish Python package 5.0.0 crash (`stockfish.info()` removed):** The `stockfish` PyPI wrapper v5.0.0 removed the `.info()` method, replaced by `raw_stockfish_output(func)`. The bot crashed on every game start. Created `_get_last_info_line()` and `_get_last_eval_cp()` helpers that use the new API. Pinned `stockfish>=5.0.0` in `requirements.txt`.
- **Chess960 and variant games accepted and crashing:** `should_accept_challenge()` did not check the `variant` field, causing the bot to accept Chess960, antichess, atomic, etc. The bot then crashed because Stockfish was not in Chess960 mode and the board assumed standard starting position. Now rejects all variants except `standard`.
- **First move as white aborted on long time controls:** In native clock mode (full-strength, opponent ≥ 2800 ELO), Stockfish received the full remaining time (e.g. 20 minutes) and could think for several minutes on move 1. Lichess aborts games with no move after ~30 seconds. First-move clock values are now capped at 15 seconds so Stockfish responds quickly.

### Changed

- **`MAX_CONCURRENT_GAMES` now configurable via `.env`:** Was hardcoded to `1` in `bot.py`. Now loaded from environment variable `MAX_CONCURRENT_GAMES` (default: `2`). Moved to `config.py`.

### Added

- **`GAME_WATCHDOG_ABORT_TIMEOUT` config:** New environment variable (default: `600` seconds / 10 minutes) controlling how long a game can stay in "started" status before the watchdog forces an abort.

## [2.6.0] - 2026-03-19

### Fixed

- **502/503/504 errors killing game threads:** `berserk.exceptions.ResponseError` with HTTP 502, 503, or 504 in the game stream was caught by the generic `except Exception` handler which broke out of the stream loop, silently killing the game thread. Added a dedicated `except ResponseError` handler that detects retriable gateway errors and reconnects with a 5-second delay instead of abandoning the game.
- **Idle game blocking concurrent slot:** When an opponent left or bugged out mid-game, the game stream hung indefinitely with no events. Since `MAX_CONCURRENT_GAMES = 1`, this blocked **all** new games. Fixed by introducing the game watchdog (see below).
- **Hard stream timeout breaking classical games:** The initial fix used a 5-minute hard timeout on the game stream, which could prematurely kill legitimate classical games where the opponent thinks for extended periods. Replaced with an API-polling watchdog that only terminates the stream when the Lichess API confirms the game has actually ended.
- **Unnecessary rating loss on concurrent game limit:** When a `gameStart` event arrived while a game was already running, the bot immediately resigned the new game (causing rating loss). Changed to attempt `abort_game` first (no rating loss for games with < 2 moves), falling back to `resign_game` only if the abort fails.
- **Watchdog silently swallowing API failures:** If `games.export()` raised an exception on every check, the error was logged at DEBUG level and the watchdog continued forever without ever detecting the game status. Now tracks consecutive failures: logs at WARNING after 3 failures and force-ends the game after 10 consecutive failures (~10 minutes) since the game status cannot be reliably determined.

### Added

- **Game stream watchdog (`_stream_with_watchdog`):** Replaces the naive hard-timeout approach. A daemon reader thread forwards game events via a `queue.Queue`. When no event arrives within `GAME_WATCHDOG_INTERVAL` seconds (default: 60), the main thread polls `client.games.export(game_id)` to check the game's actual status via the Lichess API. If the game has ended (status in `_TERMINAL_STATUSES`), a `_GameStuck` exception breaks the stream loop cleanly. If the game is still active, the watchdog continues waiting — safe for long classical thinks.
- **`opponentGone` event handling:** Detects when Lichess reports the opponent has disconnected (`opponentGone: true`). Starts a `threading.Timer` that automatically claims victory via `POST /api/bot/game/{id}/claim-victory` after the Lichess-specified `claimWinInSeconds` delay. If the opponent reconnects (`gone: false`), the timer is cancelled.
- **No-first-move abort timer:** When the bot plays as black and the opponent never makes their first move, a 120-second safety timer automatically aborts the game. This is a client-side backup for the Lichess-side `noStart` mechanism. The timer is cancelled as soon as any move arrives.
- **Startup stuck game cleanup:** On bot startup, `main()` now calls `client.games.get_ongoing()` to detect any games left running from a previous session. Games with fewer than 2 moves are aborted (no rating impact); games with more moves are left to be resumed naturally via the event stream.
- **`_TERMINAL_STATUSES` constant:** Centralised `frozenset` of terminal game statuses (`mate`, `resign`, `stalemate`, `timeout`, `draw`, `outoftime`, `aborted`, `noStart`, `unknownFinish`) — replaces three duplicated inline lists.
- **`GAME_WATCHDOG_INTERVAL` config:** New environment variable (default: `60` seconds) controlling how often the watchdog polls the Lichess API when the game stream is idle.

## [2.5.0] - 2026-03-14

### Fixed

- **Silent disconnect / bot going offline with no errors:** The event stream could get stuck indefinitely when a TCP connection to Lichess was silently dropped by a NAT/firewall (no RST or FIN packet). `requests` had no read timeout, so `for event in stream_incoming_events()` hung forever with no exception and no log output. Fixed by introducing `TimeoutHTTPAdapter(timeout=(10, 120))` — 10 s connect timeout, 120 s read timeout. Lichess sends keepalive newlines every ~30 s, so any silence beyond 2 minutes is treated as a dead connection and triggers reconnect.
- **Stream end → reconnect instead of exit:** A normal (non-error) end of the event stream iterator caused a `break` that exited the `while` loop and shut down the bot silently. Changed to `continue` with a 10 s sleep so the bot always reconnects.
- **HTTP 429 on event stream → reconnect:** `ResponseError` with status 429 previously fell through to the `else: break` branch, silently killing the bot. Now backed off for 60 s and retried. All other unrecognised `ResponseError` codes also reconnect (30 s) instead of exiting.
- **Draw offer evaluation colour bug:** `last_eval_cp` is produced by Stockfish on the bot's turn, so UCI `score cp` is already from the bot's perspective regardless of colour. The previous code incorrectly negated it for black (`evaluation = last_eval_cp if bot_is_white else -last_eval_cp`), causing the bot to accept draws when winning as black and reject them when losing. Fixed to use `last_eval_cp` directly. The fallback path (`get_evaluation()`) is now also flipped correctly using `board.turn` instead of `bot_is_white`.
- **`session.close()` in challenge loop killed the event stream:** After an HTTP 429, the challenge loop called `client.session.close()` to reset the connection pool. This closed shared TCP connections used by the main event stream, causing the stream to drop silently. The `session.close()` call was removed — the 5-minute backoff is sufficient.
- **Stockfish process leak on game stream reconnect:** When the game stream reconnected, a new `Stockfish` instance was created without killing the previous process, leaking OS processes. Fixed by adding an explicit `kill()`/`wait()` before reinitialising.

### Added

- **Docker healthcheck:** Bot writes the current timestamp to `/tmp/axiom_heartbeat` on every received event and on every reconnect attempt. Both `docker-compose.yml` and `Dockerfile` include a `HEALTHCHECK` that verifies the file is fresher than 5 minutes. Three consecutive failures mark the container `unhealthy`; combined with `restart: unless-stopped` this auto-restarts a stuck bot. Heartbeat file is removed on graceful shutdown so Docker does not restart a deliberately stopped container.
- **Graceful shutdown waits for game threads:** `handle_shutdown` previously called `sys.exit(0)` after a flat 2-second sleep, which killed daemon threads before their `finally:` blocks could clean up Stockfish processes. The handler now waits up to 15 seconds for all active game threads to finish (each thread's `finally:` block kills its Stockfish process), then exits. A second SIGTERM/SIGINT still triggers an immediate `sys.exit(1)`. Global `_active_games` and `_active_games_lock` references enable the shutdown handler to enumerate running threads without coupling to `main()`.
- **Concurrent game limit (`MAX_CONCURRENT_GAMES = 1`):** Prevents more than one simultaneous game thread. If a `gameStart` event arrives while a game is already running, the new game is immediately resigned. Dead threads are pruned from `active_games` before the limit is checked to avoid false positives from stale entries.
- **`active_games` thread-safety:** All reads and writes to the `active_games` dict (in main loop and `challenge_loop`) are now protected by `active_games_lock`. Prevents `RuntimeError: dictionary changed size during iteration` under concurrent access.

### Changed

- `gameFinish` always logs and signals `retry_event` regardless of whether the game ID was still in `active_games` (previously the log was inside the `if game_id in active_games` block).
- `challenge_loop` signature gains `active_games_lock: threading.Lock` parameter.
- `HEALTHCHECK_FILE` constant (`"/tmp/axiom_heartbeat"`) exported from `bot.py`.


### Fixed

- **Recovery / mate logic fires for all opponents:** The follow-mating-sequence, avoid-forced-mate and recovery-search behaviours were previously gated behind `PREDICTION_MIN_USE_ELO` (default: 2200) — for lower-rated opponents the PV was logged but the recovery and mate branches were silently skipped, causing the bot to play into losing continuations without attempting counterplay. All three behaviours now fire unconditionally regardless of opponent rating.
- **Removed `PREDICTION_MIN_USE_ELO`:** The variable is no longer used and has been removed from `config.py`, `.env.example`, `bot.py` imports, and documentation. The only remaining prediction gate is `ENABLE_MOVE_PREDICTION` (controls PV logging) and `PREDICTION_RECOVER_THRESHOLD` (controls recovery threshold).
- **`eval_for_bot` colour bug fixed (recovery never fired for black):** `score cp` in UCI is always from the **side-to-move** perspective. Because `get_move_prediction` is called exclusively on the bot's own turn, `pred_cp` is already the bot's score regardless of colour. The previous code applied `eval_for_bot = -pred_cp` for black, flipping a negative (losing) score to positive and preventing recovery from ever triggering when playing as black. Fixed to `eval_for_bot = pred_cp` with no colour negation.
- **Full-power mate execution:** Added `_get_full_power_move` helper. When a forced mate is detected (positive or negative), the engine temporarily disables `UCI_LimitStrength`, searches at full power to find the fastest/best mate or the strongest defensive resource, then restores the strength cap.
- **Recovery with ELO boost — automatic full-power escalation near 2800:** Added `PREDICTION_RECOVER_ELO_BOOST` (default: 200). Recovery search keeps `UCI_LimitStrength` active but raises the ELO cap by this amount (e.g. 1600 → 1800 during recovery), giving the bot a meaningfully stronger defensive resource while keeping the game winnable for the opponent. If the boosted ELO reaches or exceeds `FULL_STRENGTH_THRESHOLD` (i.e. opponent is near 2800 and the cap is already near its maximum), `UCI_LimitStrength` is disabled entirely and recovery uses full-power Stockfish — no meaningful restriction was being applied anyway at that level.
- **Clock budget correctness for secondary searches:** Wall-clock elapsed time (`time.monotonic()`) is now measured around the prediction search. Every follow-up search (full-power mate, recovery) receives a `clock_aware_move_time` budget computed from `remaining − elapsed_ms` rather than the original remaining clock. This prevents the total thinking time from exceeding the original clock budget in multi-search moves (e.g. mate detected → full-power confirmation). Fallback paths in exceptional cases use `MOVETIME_MIN_MS` instead of a full `move_time` budget to stay within the clock.


## [2.4.1] - 2026-02-20

### Fixed / Improved

- **Draw offer handling fallback:** When the library API endpoint is unavailable for BOT accounts, the bot now falls back to the BOT HTTP endpoint (`/api/bot/game/<id>/draw/<accept|decline>`). This improves reliability when responding to draw offers. (commit 8367bb0)
- **Prediction usage threshold:** Added `PREDICTION_MIN_USE_ELO` — predictions are logged for all opponents, but the engine's predicted move is only allowed to decide the played move when the opponent's rating is at-or-above this threshold. This prevents unintentionally strengthening play vs low-rated opponents. (commit 00d9282)
- **Follow / avoid mating PVs:** If the predictor reports a mate for our side in the PV, the bot will follow the mating continuation; if the predictor reports a mate against us, the bot will avoid playing the predicted (losing) continuation and selects a defensive alternative.
- **Prediction recovery threshold:** Added `PREDICTION_RECOVER_THRESHOLD` (default: 400 cp) — when the predicted evaluation is significantly worse for the bot, an alternative (recovery) search is attempted to find counterplay.
- **Misc:** Rename and demo changes — `test_prediction.py` → `demo_prediction.py` (commit 74a45ae)


## [2.4.0] - 2026-02-19

### Improved

#### 🔔 Challenge Loop — Event-Driven Retry & Full Feedback
- **Fixed**: No feedback when an outgoing challenge was ignored — the loop now logs
  `"No response from <bot> after 90s — they may be offline. Trying another bot in 30s..."`
- **Fixed**: 5-minute flat sleep after a decline/cancel — loop now uses `threading.Event`
  so it wakes up **immediately** on `challengeDeclined`, `challengeCanceled`, or `gameFinish`
- **Added**: `pending_challenge` shared dict tracks the in-flight challenge
  (`id`, `opponent`, `sent_at`) so events can be correlated back to our own challenge
- **Added**: `challengeDeclined` now logs the **decline reason** from Lichess
  (e.g. "later", "tooFast", "noBot", etc.) and whether it was our challenge
- **Added**: 30-second back-off after a decline before trying the next bot (avoids
  hammering the API if multiple bots decline in quick succession)
- **Added**: `gameFinish` now immediately wakes the challenge loop so the bot looks
  for the next game as soon as the current one ends (instead of waiting up to 1 minute)
- **Changed**: `challenge_bot()` now returns the challenge ID string (was `bool`)
- **Changed**: `try_challenge_random_bot()` now returns the challenge ID (was `bool`)
- **Changed**: `challenge_loop()` accepts two new arguments: `retry_event` and
  `pending_challenge`

#### ⚙️ Config defaults updated
- `MAX_CHALLENGES_PER_HOUR`: `3` → `5`
- `CHALLENGE_CHECK_INTERVAL`: `300` (5 min) → `60` (1 min)

**Timeline example (before vs. after):**

Before: declined at 14:24:19 → next attempt 14:29:19 (5-minute wait, silent)
After:  declined at 14:24:19 → "declined by X — reason: tooFast" logged instantly
        → retry at 14:24:49 (30-second back-off), reason printed

## [2.3.1] - 2026-02-19

### Performance

#### ⚡ Replace Manual Time Pressure with Native Stockfish Clock Management
- **Removed**: Manual "emergency" (≤20 s) and "moderate" (20–60 s) time-pressure branches
  from `calculate_move_time` — both had fundamental flaws:
  - Moderate branch used `remaining_seconds / 60` as a scaling factor, completely
    ignoring increment; with 30 s remaining on a 3+2 game the bot has ~90 s of
    effective budget but the formula gave only 50 % of `adjusted_time`
  - Emergency branch hardcoded `estimated_moves_remaining = 20` regardless of
    actual game phase (at move 50 of an endgame there may be only 5 moves left)
- **Added**: `_get_best_move_with_clocks(wtime, btime, winc, binc)` helper that sends
  the full UCI `go wtime … btime … winc … binc …` command — the same command all
  chess GUIs use. Stockfish's internal time manager accounts for position complexity,
  game phase, and increment far better than any manual heuristic
- **Changed**: `calculate_move_time` now returns only the opponent-strength-based
  movetime cap (used exclusively for weak opponents where `UCI_LimitStrength` is active)
- **Changed**: `get_move_prediction` extended with `wtime/btime/winc/binc` keyword
  arguments — selects movetime or native-clock search based on which args are supplied
- **Changed**: `play_game` now tracks `wtime_ms`, `btime_ms`, `winc_ms`, `binc_ms`
  (parsed for both sides) instead of a single `bot_time_remaining`/`increment` pair
- **Logic**: weak opponent (`< 1800`) → `go movetime` with strength cap;
  normal/strong opponent → `go wtime btime winc binc` (Stockfish manages everything);
  no clock data → `go movetime` fallback

## [2.3.0] - 2026-02-19

### Performance

#### ⚡ Zero-cost Draw Offer Evaluation
- **Removed**: `stockfish.get_evaluation()` (extra depth-13 engine search) from the draw offer handler
- **Added**: `_extract_cp_from_info()` helper — extracts centipawn or mate score from the
  Stockfish info line that was already produced by the move search
- **Added**: `last_eval_cp` cached in `play_game()` immediately after each move calculation
- **Result**: Draw offer evaluation is now free — zero extra engine calls per draw offer;
  the cached value is valid because it already accounts for the opponent's best response (PV)
- **Fallback**: `get_evaluation()` is still called on the very first move if no cache exists yet

#### ⚡ Eliminate Redundant `set_fen_position` Call
- **Removed**: `stockfish.set_fen_position(board.fen())` from the draw handler (was followed
  by another identical call in the move calculation block on the same turn)
- **Result**: Saves one full position-load roundtrip to the Stockfish process per draw offer

#### 🧹 Remove Dead Code in `get_online_bots`
- **Removed**: Outer `try/except` wrapping that was unreachable dead code — the inner
  `try/except` already caught and returned before the outer handler could ever fire
- **Result**: Cleaner control flow, single clear error path

## [2.2.1] - 2026-02-19

### Bug Fixes

#### 🐛 Time Management Type Error Fix
- **Fixed**: TypeError when comparing bot_time_remaining with integers
- **Fixed**: Proper parsing of timedelta strings from Lichess API (e.g., `"0:08:44.640000"`)
- **Added**: Robust `parse_time_to_milliseconds()` function supporting multiple formats:
  - Integers (milliseconds)
  - Floats (milliseconds)
  - String integers ("120000")
  - Timedelta strings ("0:08:44.640000")
  - Timedelta objects
- **Improved**: Graceful fallback when time data is invalid or malformed

**Issue:** Bot would crash with `TypeError: '<=' not supported between instances of 'datetime.timedelta' and 'int'` during time pressure calculations. Lichess API sometimes sends time values as timedelta-formatted strings instead of integers.

**Solution:** Created comprehensive time parsing function that handles all formats the Lichess API might send, with proper error handling and logging for debugging.

## [2.2.0] - 2026-02-18

### New Features

#### 🔮 Move Prediction Analysis
- **Added**: Stockfish now predicts and logs the best continuation (Principal Variation)
- **Added**: `ENABLE_MOVE_PREDICTION` config option (default: enabled)
- **Added**: `PREDICTION_DEPTH` to control how many moves ahead to predict (default: 10)
- **Show**: Displays evaluation (centipawns or mate) with predicted line
- **Format**: `🔮 Predicted line (+45 cp): e2e4 e7e5 g1f3 b8c6 f1c4`

**Example Log Output:**
```
[game123] 🔮 Predicted line (+125 cp): d7d5 c2c4 e7e6 b1c3 g8f6 c1g5
[game456] 🔮 Predicted line (Mate in 3): d1d8 g8h7 d8h8
```

**Configuration:**
```python
# In config.py or environment
ENABLE_MOVE_PREDICTION = True  # Enable/disable feature
PREDICTION_DEPTH = 10         # Number of moves to predict (half-moves)
```

**Benefits:**
- 📊 Better understanding of bot's strategic plan
- 🎯 Insight into engine evaluation and tactics
- 🐛 Useful for debugging and analysis
- 🎓 Educational value for reviewing games

## [2.1.2] - 2026-02-18

### New Features

#### ⚡ Bullet Game Support
- **Added**: Full support for bullet time controls (1+0, 1+1, 2+1)
- **Added**: Bullet games to `CHALLENGE_TIME_CONTROLS` for auto-challenging
- **Improved**: Bot now handles ultra-fast games professionally

#### ⏱️ Intelligent Time Management
- **Added**: Dynamic time management to prevent losses on time
- **Added**: Emergency mode for critical time situations (≤20 seconds remaining)
- **Added**: Moderate time pressure handling (20-60 seconds remaining)
- **Smart**: Automatically adjusts thinking time based on remaining clock
- **Balanced**: Maintains minimum 300ms move quality even in time pressure
- **Optimal**: Uses 60% of available time budget in emergency situations

**Time Management Thresholds:**
- **Critical (≤20s)**: Emergency mode - very fast moves (min 300ms)
- **Moderate (20-60s)**: Conservative time usage (min 500ms)
- **Normal (>60s)**: Standard opponent-based calculation

**Technical Details:**
- Tracks `wtime`/`btime` and `winc`/`binc` from game state
- Estimates ~20 moves remaining for time budgeting
- Accounts for increment in time pressure calculations
- Minimal impact on playing strength (smart minimums)

## [2.1.1] - 2026-02-13

### Bug Fixes & Improvements

#### 🔧 Auto-Challenge System Fixes
- **Fixed**: Auto-challenge now runs in separate background thread, no longer blocks event stream
- **Fixed**: Challenge checking now works reliably every `CHALLENGE_CHECK_INTERVAL` seconds
- **Fixed**: Bot correctly distinguishes between incoming and outgoing challenges
- **Fixed**: Graceful handling of 404 errors when challenges are canceled
- **Improved**: Uses berserk's built-in `client.bots.get_online_bots()` method

#### 🛑 Graceful Shutdown Improvements
- **Fixed**: Ctrl+C now properly shuts down the bot within 2 seconds
- **Added**: Press Ctrl+C twice for immediate force exit
- **Improved**: Better cleanup of background threads on shutdown

#### 📝 Documentation Updates
- **Updated**: README with background thread information for auto-challenging
- **Updated**: README with graceful shutdown instructions
- **Added**: Environment variable examples for aggressive challenging strategies

**Example Configuration for Active Play:**
```bash
MAX_CHALLENGES_PER_HOUR=40      # Up from default 3
CHALLENGE_CHECK_INTERVAL=90     # Check every 90 seconds instead of 5 minutes
```

## [2.1.0] - 2026-02-10

### Strength Balance Improvements

#### 🎯 Rebalanced ELO Thresholds for Better Challenge

**Changes:**
- **LIMIT_STRENGTH_THRESHOLD**: Raised from 1700 → **1800 ELO**
  - Below 1800: Bot uses UCI_LimitStrength for fair games
  
- **FULL_STRENGTH_THRESHOLD**: Raised from 2300 → **2800 ELO**
  - Full power now only activated at 2800+ (elite/super-GM level)
  - Previously activated at 2300+ (too strong for most advanced players)

- **Intermediate Scaling (1800-2799 ELO)**: Improved progression
  - Time scaling now 40% → 95% (was 50% → 99%)
  - Wider rating range (1000 points vs 600 points) for smoother difficulty curve
  - Example: 2500 ELO opponent now gets 79% time instead of full power

**Why These Changes:**
- Bot was too dominant against 2300-2799 rated players
- More balanced and enjoyable games across all skill levels
- Only true elite players (2800+) face maximum bot strength
- Better progression from intermediate to advanced levels

**New Effective Strength:**
- **< 1800 ELO**: Opponent rating + 100 ELO (fair learning games)
- **1800-2799 ELO**: ~2000-2900 ELO (challenging but beatable)
- **2800+ ELO**: ~3200-3500 ELO (maximum power for elite players)

## [2.0.0] - 2026-02-06

### Major Changes - Intelligence & Quality Improvements

#### 🎯 Hybrid Dynamic Strength System (Best of Both Worlds!)

**Problem with Pure Time-Based System:**
- Time-only approach was too strong for beginners (even 450ms = ~2200 ELO)
- Players below 1800 ELO had almost no chance to win

**Solution: HYBRID APPROACH**

**Three-Tier System:**

1. **Beginners & Intermediates (< 1800 ELO):**
   - Uses `UCI_LimitStrength` set to opponent_rating + 100
   - Bot plays at fair, balanced level
   - Example: 1500-rated player faces ~1600 strength
   - **Result: Winnable, educational games** ✅

2. **Advanced Players (1800-2199 ELO):**
   - **Full-strength Stockfish** (no intentional mistakes)
   - Thinking time scaled 50-99% based on rating
   - Example: 2000-rated gets 75% time = ~2400 ELO strength
   - **Result: Challenging, high-quality chess** ✅

3. **Expert & Master (2200+ ELO):**
   - **MAXIMUM POWER**: Full strength + Full time (3 seconds)
   - No compromises, no handicaps
   - Effective strength: ~3200-3500 ELO
   - **Result: Ultimate challenge** 🔥

**Benefits:**
- ✅ Fair games for beginners (UCI_LimitStrength ensures balance)
- ✅ No blunders for advanced players (full engine quality)
- ✅ Maximum challenge for strong players (full power unlocked)
- ✅ Smooth difficulty curve across all levels

#### 🤝 Intelligent Draw Offer Handling

**Old Logic:**
- Accepted draws when losing badly (< -300 centipawns)
- Gave up in difficult positions

**New Logic:**
- **Accepts** draws only in balanced positions (±200 centipawns)
- **Declines** draws when winning (let the advantage play out)
- **Declines** draws when losing (trust engine to find counterplay)
- **Declines** all draws in mate positions (engine knows best)
- Philosophy: Utilize superior calculation power, don't surrender easily

#### ⚙️ Configuration Updates

**Performance Improvements:**
- `STOCKFISH_TIME`: 1100ms → **3000ms** (3 seconds per move)
  - Depth increased from ~15-20 ply to ~25-30 ply
  - More accurate position evaluation
- `Hash`: 1024 MB → **2048 MB**
  - Better position caching
  - Faster repeat position detection

**New Configuration Options:**
- `LIMIT_STRENGTH_THRESHOLD`: Below this rating, use UCI_LimitStrength (default: 1800)
- `FULL_STRENGTH_THRESHOLD`: At or above this rating, use full power (default: 2200)
- `STRENGTH_ADVANTAGE`: ELO bonus for weak opponents (default: 100, restored with new purpose)

### Technical Changes

#### Hybrid System Implementation
- Added `LIMIT_STRENGTH_THRESHOLD` configuration parameter
- Restored `STRENGTH_ADVANTAGE` with new meaning (for weak opponents only)
- `init_stockfish()` now conditionally applies UCI_LimitStrength based on opponent rating
- `calculate_move_time()` uses three-tier time scaling (40% / 50-99% / 100%)

#### API Fixes
- Fixed draw response error: `'dict' object has no attribute 'raise_for_status'`
- Now uses proper Berserk API methods: `client.bots.accept_draw()` / `decline_draw()`

#### Code Improvements
- Better logging for draw decisions and strength adjustments
- Clear separation between fairness mode (UCI_LimitStrength) and challenge mode (time control)

#### Test Suite Updates
- Updated test count: 21 → **25 tests**
- Modified Stockfish initialization tests for hybrid approach
- Updated `TestMoveTimeCalculation` class with 4 tests:
  - Full time for strong opponents (≥ 2200)
  - Minimum time for weak opponents (< 1800, UCI_LimitStrength handles fairness)
  - Scaled time for intermediate opponents (1800-2199)
  - Dynamic strength disable functionality
- All tests passing ✅

### Documentation Updates

- ✅ [README.md](README.md) - Complete rewrite of dynamic strength section
- ✅ [TESTING.md](TESTING.md) - Updated test counts and descriptions
- ✅ [config.py](config.py) - Detailed comments explaining new parameters
- ✅ [CHANGELOG.md](CHANGELOG.md) - This file

### Breaking Changes

⚠️ **Configuration Changes:**
- `STRENGTH_ADVANTAGE` restored but with NEW meaning:
  - Old: Bot plays at opponent_elo + advantage (all opponents)
  - New: Bot plays at opponent_elo + advantage (only for opponents < 1800)
- `DYNAMIC_STRENGTH` now controls hybrid system (UCI_LimitStrength + time control)
- New threshold: `LIMIT_STRENGTH_THRESHOLD` determines when to switch from fairness to challenge mode

### Migration Guide

**No action needed for most users** - the hybrid system automatically provides better balance!

If you were using custom settings:

**Before (Time-Only):**
```python
DYNAMIC_STRENGTH = True
FULL_STRENGTH_THRESHOLD = 2200
STRENGTH_ADVANTAGE = 0  # Unused
```

**After (Hybrid - Recommended):**
```python
DYNAMIC_STRENGTH = True
LIMIT_STRENGTH_THRESHOLD = 1800  # Use UCI_LimitStrength below this
FULL_STRENGTH_THRESHOLD = 2200   # Full power at or above this
STRENGTH_ADVANTAGE = 100         # For opponents < 1800
```

To disable hybrid system (not recommended):
```python
DYNAMIC_STRENGTH = False  # Same time and strength for all opponents
```

### Performance Comparison

| Opponent ELO | Old System | Hybrid System | Method | Fairness |
|--------------|-----------|---------------|---------|----------|
| **1200** | ~1300 (UCI_Elo) | ~1300 (UCI_Elo) | UCI_LimitStrength | ✅ Fair |
| **1500** | ~1600 (UCI_Elo) | ~1600 (UCI_Elo) | UCI_LimitStrength | ✅ Fair |
| **1800** | ~1900 (UCI_Elo) | ~2000 (50% time) | Time Control | ✅ Challenging |
| **2000** | ~2100 (UCI_Elo) | ~2400 (75% time) | Time Control | ✅ Hard |
| **2200** | ~2300 (UCI_Elo) | **~3200 (100% time)** | **FULL POWER** | 🔥 Maximum |
| **2500** | 2600 (UCI_Elo) | **~3400 (100% time)** | **FULL POWER** | 🔥 Maximum |

**Key Improvement:** Strong opponents (2200+) now face ~1000 ELO stronger bot!

### Contributors

- Core changes by @pavlojs
- Inspired by feedback from real-game analysis

---

## [1.0.0] - 2025-01-XX

Initial release with basic functionality.
