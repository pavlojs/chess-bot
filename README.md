# Axiom Chess Bot

A Lichess bot built on the Stockfish engine. It limits its strength to the opponent's rating, plays on its own account around the clock, and challenges other bots when it has nothing to do.

[![CI](https://github.com/pavlojs/chess-bot/actions/workflows/ci.yml/badge.svg?branch=dev)](https://github.com/pavlojs/chess-bot/actions/workflows/ci.yml)
[![CodeQL](https://github.com/pavlojs/chess-bot/actions/workflows/codeql.yml/badge.svg?branch=dev)](https://github.com/pavlojs/chess-bot/actions/workflows/codeql.yml)
[![Security](https://github.com/pavlojs/chess-bot/actions/workflows/security.yml/badge.svg?branch=dev)](https://github.com/pavlojs/chess-bot/actions/workflows/security.yml)

## Play against the bot

The bot's account is [@Axiom_BOT](https://lichess.org/@/Axiom_BOT).

[![Challenge Axiom_BOT](https://img.shields.io/badge/Challenge-Axiom__BOT-orange?style=for-the-badge&logo=lichess)](https://lichess.org/?user=Axiom_BOT#friend)

It accepts a challenge when all of these hold:

- standard chess, rated or casual, from a human or from another bot;
- a clock in bullet, blitz, rapid or classical (no correspondence, no unlimited games);
- a challenger rated between 1320 and 2800 at that speed;
- a free game slot. It plays two games at a time by default and declines the rest with "later".

A challenge it does not take is declined with the reason Lichess has for it, so the challenger reads what to change: standard chess only, another time control, a slower or a faster game, or later. A rating outside the range gets Lichess's general "not accepting challenges at the moment", the closest there is. The speeds and the rating range are settings: `TIME_CONTROL`, `MIN_RATING` and `MAX_RATING`.

## Requirements

- Python 3.11 or newer (CI runs the tests on 3.11 to 3.14)
- A Lichess [BOT account](https://lichess.org/api#tag/Bot) and an API token for it with the `bot:play` scope
- Stockfish. `./scripts/install_stockfish.sh` installs the latest release; the container image brings its own.

## Setup

1. Clone this repository.
2. Create the virtual environment: `./scripts/setup_venv.sh`
3. Install Stockfish: `./scripts/install_stockfish.sh`. Skip this if there is a `stockfish` on your `PATH` already.
4. Copy `.env.example` to `.env` and put your token in `TOKEN`. Create the token at https://lichess.org/account/oauth/token.
5. Run the bot: `./scripts/run_bot.sh`
6. Stop it with `Ctrl+C`. The bot gives its game threads up to 15 seconds to wind down and then exits; a second `Ctrl+C` exits at once. A game that is still going is not resigned: it is picked up again if the bot is back before its clock runs out.

### Stockfish

`./scripts/install_stockfish.sh` looks at the [official Stockfish releases](https://github.com/official-stockfish/Stockfish/releases). If `/usr/local/bin/stockfish` is missing or is not the latest release, it downloads the build for this platform, checks the archive against the SHA-256 the release publishes, and installs it, asking for `sudo` when `/usr/local/bin` is not writable. Run it again to update.

- To use a binary you chose yourself: set `STOCKFISH_PATH=/path/to/stockfish`. Without it the bot takes the `stockfish` on the `PATH`.
- To have the bot do the same each time it starts: set `AUTO_UPDATE_STOCKFISH=true`. It is off by default, because it puts a downloaded binary into a system directory and may ask for `sudo`, and that is yours to decide.

## Testing

```bash
pip install -r requirements-dev.txt   # done already by scripts/setup_venv.sh
pytest
```

See [TESTING.md](TESTING.md) for what the suite covers and how it is built.

## Deployment

### Docker

`ghcr.io/pavlojs/axiom-chess-bot:latest` is built from `main` each time `dev` is promoted, after the tests and the image checks have passed on that commit. Every build is also tagged `main-<commit>`.

```yaml
services:
  axiom-bot:
    image: ghcr.io/pavlojs/axiom-chess-bot:latest
    container_name: axiom-bot
    env_file: .env
    restart: unless-stopped
    stop_grace_period: 30s
    read_only: true
    tmpfs:
      - /tmp:size=1m,noexec,nosuid,nodev
    volumes:
      - logs:/app/logs
    cap_drop:
      - ALL
    security_opt:
      - no-new-privileges:true
    pids_limit: 128
    logging:
      driver: json-file
      options:
        max-size: 10m
        max-file: "3"

volumes:
  logs:
```

Put your token in a `.env` file beside it (copy [.env.example](.env.example)) and run `docker compose up -d`. A change to `.env` takes effect with the next `docker compose up -d`.

To build the image yourself, use the [docker-compose.yml](docker-compose.yml) in this repository, which is the same file with `build: .` in place of `image:`: `docker compose up -d --build`.

What the image is and how it is meant to run:

- **Nothing but the bot.** The runtime is a [distroless](https://github.com/GoogleContainerTools/distroless) Python base: no shell, no package manager, no `curl`. `/app` holds the bot's four modules and its libraries.
- **An unprivileged user.** The bot runs as uid 65532. Its code and the engine belong to root and it cannot change them.
- **A read-only root filesystem.** The bot writes in two places: `/app/logs`, the volume above, for its log and for `state.json` (what it [remembers across restarts](#challenging-other-bots)), and a heartbeat stamp in `/tmp`.
- **A pinned engine.** The image carries one named Stockfish release, checked against its SHA-256 when the image is built. The bot's self-updater is not in the image.
- **A bounded log.** `logs/axiom_bot.log` records everything from DEBUG up and is rotated, 60 MB in all by default (`LOG_FILE_MAX_MB`, `LOG_FILE_BACKUPS`). What the bot prints (INFO and up) goes to `docker logs`, capped by the `logging` options above.
- **Memory is yours to limit.** Each game runs an engine of its own, with `SF_HASH` MB of hash on top of the engine's own networks. Add a `mem_limit` that fits `SF_HASH × MAX_CONCURRENT_GAMES` with room to spare.

`scripts/check_image.sh <image>` tries each of these from inside a container, and CI runs it on every push.

**Health.** Lichess sends a line on the bot's event stream at least every 7 seconds, an empty one when nothing is happening. The bot stamps a file each time one arrives, and the image's health check passes while the stamp is younger than a minute. So `healthy` means "Lichess has been heard from in the last minute", whether or not a game is on. Docker does not restart an unhealthy container, and the bot does not wait for it to: a connection that goes silent is noticed after 30 seconds and reopened, and if the bot's event loop stops moving for five minutes the process exits with an error so that `restart: unless-stopped` starts a new one.

**Alerts.** Docker tells nobody that a container is unhealthy. To be told, create a monitor of the type *Push* in [Uptime Kuma](https://github.com/louislam/uptime-kuma) and put the address it shows in `KUMA_PUSH_URL`. The bot then reports to it every `KUMA_PUSH_INTERVAL` seconds (60): `up` while Lichess has been heard from within the last minute, `down` with the length of the silence otherwise, and nothing at all once it has stopped or hangs, which Kuma notices by itself. In Kuma, set the monitor's *Heartbeat Interval* to a little over twice the bot's interval (130 seconds for the default) and leave *Retries* at 0: one lost report or a restart of the bot then raises no alarm. The address contains the monitor's token, so the bot never writes it to its log. None of this needs Docker; it works the same under systemd.

To play with tablebases or change `config.py`, add a read-only mount: `./syzygy:/app/syzygy:ro` or `./config.py:/app/config.py:ro`.

### systemd

1. Run `./scripts/setup_venv.sh`.
2. Copy `scripts/axiom-bot.service` to `/etc/systemd/system/` and adjust `User`, `Group`, `WorkingDirectory`, `ExecStart`, `EnvironmentFile` and `ReadWritePaths` to your user and directory.
3. `sudo systemctl daemon-reload && sudo systemctl enable --now axiom-bot`
4. Status: `sudo systemctl status axiom-bot`. Log: `tail -f logs/axiom_bot.log`.

The unit restarts the bot when it exits with an error, which is what the bot does when its event loop is stuck.

## Configuration

Settings come from the environment or from a `.env` file. [.env.example](.env.example) lists every one of them with its default, and a test keeps that file in step with the code. The ones most often changed:

| Variable | Default | What it sets |
| --- | --- | --- |
| `SF_THREADS` | `4` | Engine threads, per game |
| `SF_HASH` | `2048` | Engine hash in MB, per game |
| `MAX_CONCURRENT_GAMES` | `2` | Games played at the same time |
| `MIN_RATING` / `MAX_RATING` | `1320` / `2800` | Rating range of the challengers it accepts |
| `TIME_CONTROL` | `bullet,blitz,rapid,classical` | Speeds it accepts challenges at |
| `STOCKFISH_TIME` | `3000` | Base thinking time per move in ms against a limited opponent |
| `STRENGTH_ADVANTAGE` | `100` | How far above the opponent's rating the engine's limit is set |
| `FULL_STRENGTH_THRESHOLD` | `2800` | Opponent rating from which the bot plays at full strength |
| `ENABLE_AUTO_CHALLENGE` | `true` | Challenge other bots when a game slot is free |
| `MAX_CHALLENGES_PER_HOUR` | `5` | Challenges created per hour |
| `MAX_CHALLENGES_PER_DAY` | `180` | Challenges created in any 24 hours |
| `CHALLENGE_MIN_RATING` / `CHALLENGE_MAX_RATING` | `1500` / `2900` | Rating range of the bots it challenges |
| `AUTO_UPDATE_STOCKFISH` | `false` | Install and update the engine at startup; see [Stockfish](#stockfish) |
| `KUMA_PUSH_URL` | empty | Uptime Kuma push monitor to report to; see [Docker](#docker), *Alerts* |

A few settings are lists or fixed values and live in `config.py`:

- `CHALLENGE_TIME_CONTROLS`: the clocks the bot offers when it challenges, from 1+0 to 30+0.
- `UCI_OPTIONS`: any further Stockfish option. `stockfish` followed by `uci` lists what the engine has.

## How it plays

### Strength

Stockfish has a strength limit of its own, `UCI_LimitStrength`, which makes the engine choose weaker moves on purpose to play at a given rating. The bot sets it per opponent:

| Opponent's rating | Engine | Thinking time |
| --- | --- | --- |
| below `LIMIT_STRENGTH_THRESHOLD` (1800) | limited to the opponent's rating + `STRENGTH_ADVANTAGE` | 40 % of `STOCKFISH_TIME` per move |
| from there to `FULL_STRENGTH_THRESHOLD` (2800) | limited the same way | 40 % rising to 95 % of `STOCKFISH_TIME` |
| at or above `FULL_STRENGTH_THRESHOLD`, or no rating | full strength | the game clock, managed by Stockfish |

The limit is never set below 1320, the lowest Stockfish accepts, nor above 2850. With the defaults a 1500-rated opponent meets an engine limited to 1600 that answers within 1.2 seconds, and a 2500-rated one an engine limited to 2600 that takes up to 2.4 seconds. An opponent without a rating, such as an anonymous player or Lichess's own AI, gets full strength.

`DYNAMIC_STRENGTH=false` switches the whole scheme off: full strength against everyone.

Limited games are searched with a fixed time per move so that the bot answers quickly. Left to manage the clock itself, Stockfish 19 spends 20 to 30 seconds on the first move of a 5+3 game, with the limit or without it.

### Thinking time and the clock

The rating-based time is a ceiling. It is cut down whenever the bot's remaining clock calls for less:

```
moves_left = max(MOVETIME_MIN_MOVES_LEFT, MOVETIME_ESTIMATED_MOVES − fullmove_number // 2)
clock_cap  = (remaining_ms / moves_left + increment_ms) × MOVETIME_CLOCK_SAFETY
move_time  = min(rating_based_time, max(MOVETIME_MIN_MS, clock_cap))
```

With the defaults (40 moves estimated, never fewer than 10, safety 0.8):

| Game | Rating-based time | Clock cap | Time used |
| --- | --- | --- | --- |
| 1+0, move 32, 8 s left, opponent 1500 | 1200 ms | (8000 / 24) × 0.8 = 266 ms | 266 ms |
| 5+3, move 10, 60 s left, opponent 1500 | 1200 ms | (60000 / 35 + 3000) × 0.8 = 3771 ms | 1200 ms |
| 5+3, move 10, 60 s left, opponent 2200 | 1860 ms | 3771 ms | 1860 ms |

At full strength the bot hands Stockfish the real clock, with one exception: for its very first move it reports at most 15 seconds, so that the game gets going.

### Second searches

In a limited game the first search of a move can lead to a second one:

| What the first search found | Second search |
| --- | --- |
| a forced mate for the bot | at full strength, to play the mate out correctly |
| a forced mate against the bot | at full strength, for the best defence |
| the bot is worse by `PREDICTION_RECOVER_THRESHOLD` (400 cp) or more | 1.5 times as long, with the limit raised by `PREDICTION_RECOVER_ELO_BOOST` (200); at full strength if that reaches `FULL_STRENGTH_THRESHOLD` |
| anything else | none |

The second search is budgeted from the clock left after the first, and the opponent's limit is put back afterwards.

### Draw offers

The bot accepts a draw when the position is within 200 centipawns of level, by the evaluation of its last search. It declines when it is clearly better, when it is clearly worse, and whenever a mate is on the board. It never offers a draw, and it does not resign a game it is playing.

### Predicted line

With `ENABLE_MOVE_PREDICTION=true` the log shows the line the engine expects, taken from the search that chose the move:

```
[game123] 🔮 Predicted line (+125 cp): e2e4 e7e5 g1f3 b8c6 f1c4 f8c5
```

The score is from the side to move, which is the bot. `PREDICTION_DEPTH` sets how many half-moves are shown. It costs no extra search.

## Challenging other bots

While a game slot is free and `ENABLE_AUTO_CHALLENGE` is on, a background thread looks for an opponent:

1. It draws a clock from `CHALLENGE_TIME_CONTROLS`.
2. From the bots online it keeps those whose rating **at that speed** is within `CHALLENGE_MIN_RATING`–`CHALLENGE_MAX_RATING`, leaves out the ones it is leaving alone (below), and challenges one of the rest at random, rated.
3. It waits up to 90 seconds for an answer. After a decline it tries another bot 30 seconds later; with no answer at all it withdraws the challenge first.

Lichess allows an account 200 challenges a day and counts every request, including the ones it refuses. The bot counts the same way and stops at `MAX_CHALLENGES_PER_HOUR` and `MAX_CHALLENGES_PER_DAY`. If Lichess answers HTTP 429 anyway, the bot waits for as long as the answer says, or for 5 minutes doubling up to an hour when it does not say.

The bot does not challenge while its event stream is down, because it could not see the challenge being accepted and the game would start without it.

A challenge spent on a bot that will not play is one fewer for a bot that would. So a bot that did not play is left alone for a while, and for how long depends on what it did:

| What the other bot did | Left alone for |
| --- | --- |
| Answered "later" | 15 minutes |
| Did not answer within the 90 seconds, or declined without a reason | 1 hour, then 2, 4, 8 and 16, then a day each time, until it plays |
| Declined the speed: too fast, too slow, or not this time control | a day, at that speed only |
| Declined because it takes no bots, no rated games or no standard chess | a week |
| Lichess would not create the challenge: the other bot takes none, or has played its 100 games against bots for the day | as long as Lichess says, 6 hours when it does not say |

A bot that starts a game with this one is cleared at once, whichever of the two sent the challenge.

The challenges of the last 24 hours and the bots being left alone are written to `logs/state.json` and read again at startup. Lichess goes on counting while the bot restarts, so the bot has to as well: without the file a restart would hand it a full allowance that Lichess does not share, and send it straight back to the bots that just said no. Deleting the file makes the bot start from nothing.

## Staying connected

- **Event stream.** Every request has a 10-second connect and a 30-second read timeout. A stream on which nothing arrives for 30 seconds, not even a keep-alive, is closed and reopened.
- **Games after a reconnect.** Lichess announces every game in progress again when the event stream reopens. The bot recognises the games it is already playing and leaves them alone.
- **Game stream.** A game stream that drops, or answers 502, 503 or 504, is reopened after 5 seconds; a 429 after 60. Lichess sends the whole game again, and play continues from the position on the board with a fresh engine.
- **A move Lichess refuses, an engine that dies.** The bot rereads the game from Lichess and carries on from what it finds: the game over, the move already made, or a position to move in. After three rereads in a row without a move it gives up on the game.
- **A game with no events.** When a game stream is silent for `GAME_WATCHDOG_INTERVAL` seconds (60), the bot asks Lichess about the game. A game that has ended closes its thread. A game in which a side has still not made its first move after `GAME_WATCHDOG_ABORT_TIMEOUT` seconds (600) is aborted, which costs neither side anything. A game under way is never ended from the bot's side, however long the opponent thinks.
- **An opponent who never starts.** If the opponent has the first move and does not make it within 120 seconds, the bot aborts the game.
- **An opponent who leaves.** When Lichess reports the opponent gone, the bot claims the win as soon as Lichess allows it, unless the opponent comes back first.
- **A game beyond the limit.** If a game starts although every slot is taken, the bot aborts it, and resigns it only if Lichess refuses the abort.
- **Games left over from the last run.** On startup the bot aborts its games in which fewer than two moves were played. The others resume when the event stream announces them.
- **Shutdown.** `SIGTERM` and `SIGINT` end the bot within 15 seconds.

## Syzygy tablebases

With tablebases Stockfish plays endgames of up to 7 pieces perfectly. If `./syzygy` (or the directory in `SF_SYZYGY_PATH`) holds `.rtbw` or `.rtbz` files, the bot passes it to the engine. See [syzygy/README.md](syzygy/README.md) for where to get the files and how large they are; the 3-, 4- and 5-piece tables together are about 1 GB.

## Updating Stockfish

The container image installs the Stockfish release named in the [Dockerfile](Dockerfile), checked against the SHA-256 written beside it. The [Update Stockfish](.github/workflows/update_stockfish.yml) workflow looks for a new release every day and, when there is one, moves both values on `dev` and runs CI on the result. The new engine reaches `ghcr.io/pavlojs/axiom-chess-bot:latest` with the next promotion to `main`.

Outside the container, run `./scripts/install_stockfish.sh` again, or set `AUTO_UPDATE_STOCKFISH=true` to have the bot do it each time it starts; see [Stockfish](#stockfish).

## Development

`dev` is the default branch and where work lands; `main` is the released line
and only moves through the **Promote dev to main** workflow, which refuses to
run unless `dev`'s CI is green. Container images are built from `main` only,
so `ghcr.io/pavlojs/axiom-chess-bot:latest` never points at unpromoted code.

See [CONTRIBUTING.md](CONTRIBUTING.md) for the full branch model, commit style
and local setup, and [SECURITY.md](SECURITY.md) for reporting vulnerabilities.

## Credits

The bot plays with [Stockfish](https://stockfishchess.org/), which is developed by the Stockfish community and released under the GNU General Public License v3.0. It talks to Lichess through [berserk](https://github.com/lichess-org/berserk) and keeps its board with [python-chess](https://github.com/niklasf/python-chess).

## License

Axiom Chess Bot is released under the [GNU General Public License v3.0](LICENSE).
