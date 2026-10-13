# Testing

## Running the tests

```bash
./scripts/setup_venv.sh          # once: creates venv/ and installs requirements-dev.txt
source venv/bin/activate
pytest
```

The suite needs a Stockfish binary: a handful of tests run the real engine, and importing the bot resolves one. It looks at `STOCKFISH_PATH`, then at `stockfish` on the `PATH` and the usual install locations. It never installs or updates an engine: `conftest.py` switches the self-updater off for the test run and supplies a placeholder token, so no test talks to Lichess.

```bash
pytest test_game.py                                   # one file
pytest test_events.py::TestChallengeLoop              # one class
pytest test_bot.py::TestGameWatchdog -k "long_think"  # by name
pytest --no-cov -q                                    # without the coverage report
```

`pytest` prints coverage for every module and writes an HTML report to `htmlcov/index.html`.

## What is where

| File | What it tests | How |
| --- | --- | --- |
| `test_bot.py` | The pieces a game is built from: which challenges are accepted, speed categories, clock parsing, thinking time, engine output parsing, the challenge limits, how long a bot is left alone, what is written down for the next run, the game watchdog, cleanup on startup, the engine updater | Direct calls, with a mock where Lichess or the engine would be |
| `test_events.py` | What the bot does with the events Lichess sends: games starting and ending, challenges arriving, the challenge loop under its limits, the bots it leaves alone, what a restart takes over | The real event handling and challenge loop, driven event by event against a recording client |
| `test_game.py` | A whole game thread: first move to last, reconnects, refused moves, draw offers, an opponent who leaves, an engine that fails | Scripted games served by `lichess_stub.py`; a fake engine, and the real one for the last class |
| `test_resilience.py` | Staying connected: timeouts, a stream that goes silent, reconnects during games, the heartbeat, the stall watchdog, shutdown, the reports to Uptime Kuma | The bot's real HTTP stack against `lichess_stub.py`; real signals sent to a real process |
| `test_config.py` | Defaults and overrides of every setting, log rotation, tablebase detection | A fresh interpreter per case, compared with `.env.example` |

`lichess_stub.py` is a local HTTP server that plays back scripted streams and canned replies over a real socket. It can go silent in the middle of a stream, refuse a connection, answer with any status, and hold a stream until the bot has made a given request, which is what lets a whole game be scripted without timing it.

## Conventions

- A test calls the code it is about. Logic copied into a test proves nothing about the bot, however it is asserted.
- Anything about connections is tested over a real socket. The failures that matter there (a read that never returns, a stream reopened mid-game) do not exist when the HTTP layer is mocked.
- A new setting goes into `.env.example` with its default. `test_config.py` fails when the file and the code disagree.
- A fix comes with the scenario that failed before it.

## In CI

Every push to `dev` and `main` runs the suite on Python 3.11, 3.12, 3.13 and 3.14 with the Stockfish that Ubuntu packages, builds the container image, and runs `scripts/check_image.sh` against it. That script tries, from inside a container started the way `docker-compose.yml` starts it, what the image promises: no shell, no package manager, an unprivileged user, nothing writable but the log directory, an engine that still plays, a health check that tells a fresh heartbeat from a stale one.
