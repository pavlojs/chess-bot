# Testing Guide

## Running Tests

This project includes comprehensive unit tests using pytest.

### Prerequisites

#### Using Virtual Environment (Recommended)

Setup virtual environment and install dependencies:
```bash
bash scripts/setup_venv.sh
source venv/bin/activate
```

#### System-wide Installation

For Docker or systems without venv restrictions:
```bash
pip install -r requirements.txt
```

### Run All Tests

```bash
pytest
```

### Run Tests with Verbose Output

```bash
pytest -v
```

### Run Tests with Coverage Report

```bash
pytest --cov=bot --cov=logging_config
```

### Run Specific Test Class

```bash
pytest test_bot.py::TestChallengeAcceptance -v
```

### Run Specific Test

```bash
pytest test_bot.py::TestChallengeAcceptance::test_accept_challenge_valid_rating_and_timecontrol -v
```

### Generate HTML Coverage Report

```bash
pytest --cov=bot --cov=logging_config --cov-report=html
```

Coverage report will be generated in `htmlcov/index.html`

## Test Coverage

Current test coverage includes:

### Challenge Acceptance Tests (9 tests)
- ✅ Valid challenges (correct rating and time control)
- ✅ Challenges with rating too low
- ✅ Challenges with rating too high
- ✅ Challenges with unsupported time controls
- ✅ Challenges with classical time control
- ✅ Behavior when challenges are disabled
- ✅ Handling of missing rating data
- ✅ Rejection of correspondence challenges
- ✅ Rejection of unlimited time challenges

### Bullet Challenge Acceptance Tests (4 tests)
- ✅ Accept 1+0 bullet challenge
- ✅ Accept 1+1 bullet challenge
- ✅ Accept 2+1 bullet challenge
- ✅ Reject bullet challenges when `TIME_CONTROL` excludes bullet

### Board State Tests (5 tests)
- ✅ Board initialization
- ✅ Single move application
- ✅ Multiple move sequencing
- ✅ Invalid move rejection
- ✅ Game over detection (checkmate)

### Stockfish Initialization Tests (4 tests)
- ✅ Successful initialization
- ✅ UCI_LimitStrength for weak opponents (< 1800 ELO)
- ✅ UCI_LimitStrength for intermediate opponents (1800–2799 ELO)
- ✅ Full strength for elite opponents (≥ 2800 ELO)

### Move Time Calculation Tests — Opponent Scaling (4 tests)
- ✅ Full thinking time for strong opponents (≥ 2200 ELO)
- ✅ 40% movetime for weak opponents (< 1800 ELO, UCI_LimitStrength active)
- ✅ Scaled time for intermediate opponents (1800–2199 ELO)
- ✅ Consistent time when dynamic strength is disabled

### Move Time Calculation Tests — Signature (2 tests)
- ✅ `calculate_move_time` signature has exactly `(opponent_rating, base_time)` — no time-pressure args
- ✅ Return value is `int`

### Time Parsing Tests (10 tests)
- ✅ `None` input returns `None`
- ✅ Integer passthrough
- ✅ Float truncated to int
- ✅ String integer (`"120000"`)
- ✅ Timedelta string `"0:01:00.000000"` (minutes + seconds)
- ✅ Timedelta string `"0:08:44.640000"` (hours + minutes + seconds + microseconds)
- ✅ Timedelta string without microseconds `"0:03:00"`
- ✅ `datetime.timedelta` object
- ✅ `datetime.timedelta` with microseconds
- ✅ Invalid string returns `None`

### Info Line Parsing Tests — `_extract_cp_from_info` (7 tests)
- ✅ Positive centipawn score
- ✅ Negative centipawn score
- ✅ Score with bound token (`upperbound`/`lowerbound`) between `cp` and value
- ✅ Mate score → `+30000`
- ✅ Losing mate score → `−30000`
- ✅ Empty string returns `None`
- ✅ No score token returns `None`

### Info Line Parsing Tests — `_parse_pv_from_info` (6 tests)
- ✅ Positive cp eval and full PV
- ✅ Negative cp eval formatting
- ✅ Mate eval formatting
- ✅ PV truncated to requested depth
- ✅ No PV section → empty string
- ✅ Empty info line → empty strings

### Game End Reason Tests (5 tests)
- ✅ Checkmate (black wins)
- ✅ Stalemate
- ✅ Insufficient material
- ✅ Threefold repetition
- ✅ Fifty-move rule

### Error Handling Tests (2 tests)
- ✅ `ApiError` importable from `berserk.exceptions`
- ✅ `ResponseError` importable from `berserk.exceptions`

### Logging Tests (1 test)
- ✅ Logger configuration and handler setup

### Challenge Tracker Tests (4 tests)
- ✅ Initial state: no challenges recorded
- ✅ Recording challenges reduces remaining count
- ✅ Challenges older than 1 hour are pruned automatically
- ✅ `filter_suitable_bots` excludes self and out-of-range bots

### Draw Offer Handling Tests (8 tests)
- ✅ Accept draw in balanced position (±200 cp)
- ✅ Decline draw when winning (> 200 cp)
- ✅ Decline draw when losing (< −200 cp)
- ✅ Decline draw when bot has mate
- ✅ Evaluation correctly derived from `board.turn` when no cache (fallback path)
- ✅ Cached `last_eval_cp` used directly (already bot's perspective — no colour flip)
- ✅ Cached positive eval as black → accept draw correctly
- ✅ Fallback eval when bot is side-to-move → no flip applied

### Stockfish Updater Tests (3 tests)
- ✅ Binary name detection (platform-specific)
- ✅ Version detection from installed binary
- ✅ Latest release info retrieval from GitHub API

### Terminal Statuses Constant Tests (3 tests)
- ✅ `_TERMINAL_STATUSES` is a `frozenset`
- ✅ Contains all expected terminal statuses (mate, resign, stalemate, etc.)
- ✅ Non-terminal statuses (started, created) are excluded

### GameStuck Exception Tests (2 tests)
- ✅ `_GameStuck` is a subclass of `Exception`
- ✅ Preserves custom message

### Stream Watchdog Tests (4 tests)
- ✅ Events pass through from reader thread to main thread
- ✅ Raises `_GameStuck` when queue times out and API reports terminal status
- ✅ Continues waiting when API reports game is still active
- ✅ Re-raises exceptions from the stream reader thread

### Game Watchdog Config Tests (2 tests)
- ✅ `GAME_WATCHDOG_INTERVAL` is importable from `config`
- ✅ Default value is `60`

### Get Last Info Line Tests (4 tests)
- ✅ Returns penultimate line from `raw_stockfish_output` (last non-empty info line)
- ✅ Returns `None` when no output is cached (exception swallowed)
- ✅ Returns `None` when output has fewer than 2 lines
- ✅ Returns `None` when output is empty

### Get Last Eval CP Tests (4 tests)
- ✅ Returns centipawn value from cached info line
- ✅ Converts mate score to ±30000 sentinel
- ✅ Returns `None` when no function key produces output
- ✅ Returns `None` when info line cannot be parsed

### Watchdog Abort Timeout Config Tests (3 tests)
- ✅ `GAME_WATCHDOG_ABORT_TIMEOUT` is importable from `config`
- ✅ Default value is `600` seconds (10 minutes)
- ✅ Terminal statuses (mate, aborted, etc.) are never treated as stuck

### Max Concurrent Games Config Tests (4 tests)
- ✅ `MAX_CONCURRENT_GAMES` is importable from `config`
- ✅ Default value is `2`
- ✅ `bot` module imports `MAX_CONCURRENT_GAMES` from config (not hardcoded)
- ✅ Value is an integer

### Stream Watchdog Abort Tests (2 tests)
- ✅ Stuck game in "started" status for ≥ `GAME_WATCHDOG_ABORT_TIMEOUT` raises `_GameStuck`
- ✅ `_GameStuck` exception class is importable and preserves message

### Opponent Gone Handling Tests (4 tests)
- ✅ Parses `opponentGone` event with `claimWinInSeconds`
- ✅ Cancels timer when opponent returns (`gone: false`)
- ✅ Claim-victory timer runs as daemon thread
- ✅ Timer is properly cancelled on game end

### Startup Game Cleanup Tests (5 tests)
- ✅ Empty ongoing games list — no action taken
- ✅ Finished games are skipped (not aborted)
- ✅ Games with < 2 moves are aborted
- ✅ Games with ≥ 2 moves are left for event stream to resume
- ✅ String status values handled correctly

### Game Stream Reconnect 502 Tests (2 tests)
- ✅ `ResponseError` with HTTP 502 triggers reconnect (retriable)
- ✅ `ResponseError` with HTTP 404 is not retriable

### Watchdog Consecutive Failures Tests (2 tests)
- ✅ Force-ends game after N consecutive API failures
- ✅ Failure counter resets on successful API check

### No First Move Abort Tests (3 tests)
- ✅ Timer starts when bot is black and opponent hasn't moved
- ✅ Timer does NOT start when bot is white (bot moves first)
- ✅ Timer does NOT start when moves already exist on the board

**Total: 169 tests, 100% pass rate**

### Network Error Handling & Retry Logic
The bot now includes robust error handling for network issues:

**Features:**
- ✅ Exponential backoff retry logic for transient network errors
- ✅ Automatic reconnection after stream disconnects
- ✅ Special handling for Lichess API errors (502, 503, 504)
- ✅ Game state preservation during reconnections
- ✅ Graceful shutdown on persistent errors

**Handled Exceptions:**
- `ChunkedEncodingError` - Stream prematurely ended
- `ProtocolError` - HTTP protocol violations
- `ConnectionError` - Network connectivity issues 
- `Timeout` - Connection timeouts
- `ResponseError` - API errors (502, 503, 504)

**Retry Parameters:**
- Account info: 10 retries with 2s base delay
- Event stream: Infinite retries with 10s delay
- Game stream: Infinite retries with 5s delay
- API errors (5xx): 15s delay before retry

These improvements ensure the bot maintains stable connections even during:
- Network instability
- Lichess server maintenance
- Temporary API outages
- Internet connection issues

## Continuous Integration

Run the test suite before committing:

```bash
pytest && git add .
```

## Test Structure

Tests are organized in `test_bot.py` with separate test classes for different functionality:

```python
class TestChallengeAcceptance(unittest.TestCase)           #  9 tests
class TestBulletChallengeAcceptance(unittest.TestCase)     #  4 tests
class TestBoardState(unittest.TestCase)                    #  5 tests
class TestStockfishInitialization(unittest.TestCase)       #  4 tests
class TestMoveTimeCalculation(unittest.TestCase)           #  4 tests
class TestMoveTimeCalculationSignature(unittest.TestCase)  #  2 tests
class TestParseTimeToMilliseconds(unittest.TestCase)       # 10 tests
class TestExtractCpFromInfo(unittest.TestCase)             #  7 tests
class TestParsePvFromInfo(unittest.TestCase)               #  6 tests
class TestGameEndReason(unittest.TestCase)                 #  5 tests
class TestErrorHandling(unittest.TestCase)                 #  2 tests
class TestLogging(unittest.TestCase)                       #  1 test
class TestChallengeTracker(unittest.TestCase)              #  4 tests
class TestDrawOfferHandling(unittest.TestCase)             #  8 tests
class TestStockfishUpdater(unittest.TestCase)              #  3 tests
class TestExtractMateFromInfo(unittest.TestCase)           #  6 tests
class TestGetMovePredictionSignature(unittest.TestCase)    #  5 tests
class TestDrawOfferFallback(unittest.TestCase)             #  6 tests
class TestPredictionRecoverThreshold(unittest.TestCase)    # 11 tests
class TestMatingPvLogic(unittest.TestCase)                 #  4 tests
class TestFullPowerMateMove(unittest.TestCase)             #  5 tests
class TestClockAdjustedSecondarySearch(unittest.TestCase)  #  5 tests
class TestTimeoutHTTPAdapter(unittest.TestCase)            #  3 tests
class TestHealthcheck(unittest.TestCase)                   #  2 tests
class TestGracefulShutdown(unittest.TestCase)              #  2 tests
class TestConcurrentGameLimit(unittest.TestCase)           #  2 tests
class TestTerminalStatuses(unittest.TestCase)               #  3 tests
class TestGameStuckException(unittest.TestCase)             #  2 tests
class TestStreamWithWatchdog(unittest.TestCase)             #  4 tests
class TestGameWatchdogConfig(unittest.TestCase)             #  2 tests
class TestOpponentGoneHandling(unittest.TestCase)           #  4 tests
class TestStartupGameCleanup(unittest.TestCase)             #  5 tests
class TestGameStreamReconnect502(unittest.TestCase)         #  2 tests
class TestWatchdogConsecutiveFailures(unittest.TestCase)    #  2 tests
class TestNoFirstMoveAbort(unittest.TestCase)               #  3 tests
class TestGetLastInfoLine(unittest.TestCase)                #  4 tests
class TestGetLastEvalCp(unittest.TestCase)                  #  4 tests
class TestWatchdogAbortTimeout(unittest.TestCase)           #  3 tests
class TestMaxConcurrentGamesConfig(unittest.TestCase)       #  4 tests
class TestStreamWithWatchdogAbort(unittest.TestCase)        #  2 tests
# Total: 169 tests
```

## Mocking

Tests use `unittest.mock` to mock external dependencies:
- Lichess API calls
- Stockfish engine
- Configuration values

This allows tests to run without requiring actual API credentials or engine binaries.

Also covers all new classes added in v2.5.0:

### Timeout HTTP Adapter Tests (3 tests)
- ✅ `TimeoutHTTPAdapter` stores the configured timeout tuple
- ✅ `send()` injects the default timeout into every request
- ✅ Explicit `timeout=` kwarg passed by caller is not overridden

### Healthcheck Tests (2 tests)
- ✅ `HEALTHCHECK_FILE` constant equals `/tmp/axiom_heartbeat`
- ✅ Heartbeat file is writable on the target filesystem

### Graceful Shutdown Tests (2 tests)
- ✅ First signal sets `shutdown_requested = True`
- ✅ Second signal raises `SystemExit(1)` immediately

### Concurrent Game Limit Tests (2 tests)
- ✅ Dead thread is cleaned up, freeing a slot for a new game
- ✅ Alive game thread blocks a new game from starting

## Performance

All tests complete in under 3 seconds (~2.2 s on typical hardware).
