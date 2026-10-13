# Security Policy

## Supported Versions

This project is maintained by one person as a hobby project. Only the latest
published version receives fixes — there are no maintained release branches.

| Version | Supported |
| ------- | --------- |
| latest  | ✅        |
| older   | ❌        |

## Reporting a Vulnerability

Please report security issues **privately**, not as a public issue.

Use GitHub's private vulnerability reporting:
<https://github.com/pavlojs/chess-bot/security/advisories/new>

Expect a first response within 7 days. Since this is a single-maintainer
project, a fix may take longer than that — you will be told where it stands.

Please include:

- what the issue is and how it can be triggered,
- the version or commit you tested,
- what an attacker gains.

## Scope

The bot holds a **Lichess API token** with the `bot:play` scope. Anything that
can read that token, or make the bot act outside a game it is playing, is in
scope. So is anything that causes the bot to fetch and execute untrusted code:
outside the container the engine installer downloads and runs a binary. It runs
when you start `scripts/install_stockfish.sh`, and at each start of the bot only
if you set `AUTO_UPDATE_STOCKFISH=true`. It takes the binary only from the
Stockfish project's GitHub releases and installs it only if it matches the
SHA-256 the release publishes.

The container image does not contain the installer. Its engine is one named
release, checked against its SHA-256 when the image is built. The image has no
shell and no package manager, and the bot runs in it as an unprivileged user
that owns nothing but its log directory. A way around any of that is in scope.

Out of scope: the strength of the bot's chess, rate limits imposed by Lichess,
and vulnerabilities in Stockfish itself (report those to
[official-stockfish/Stockfish](https://github.com/official-stockfish/Stockfish)).

## What the scans report

Every push and a weekly run scan the Python dependencies (pip-audit), the
repository and the built image (Trivy), and the code (CodeQL). The image scan
files an alert for a HIGH or CRITICAL vulnerability once a fixed package
exists, since that is when an update of the base image can close it. What
Debian has not fixed yet is listed in the log of the scan job, not filed as an
alert.

## Handling the token

The token is read from `TOKEN` in the environment or a local `.env` file.
`.env` is gitignored and excluded from the Docker build context. If you ever
commit one, revoke the token at
<https://lichess.org/account/oauth/token> before doing anything else —
rewriting history does not un-publish it.
