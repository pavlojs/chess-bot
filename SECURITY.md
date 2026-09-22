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

The bot holds a **Lichess API token** with `board:play` and `bot:play` scopes.
Anything that can read that token, or make the bot act outside a game it is
playing, is in scope. So is anything that causes the bot to fetch and execute
untrusted code — the engine self-updater downloads and runs a binary.

Out of scope: the strength of the bot's chess, rate limits imposed by Lichess,
and vulnerabilities in Stockfish itself (report those to
[official-stockfish/Stockfish](https://github.com/official-stockfish/Stockfish)).

## Handling the token

The token is read from `TOKEN` in the environment or a local `.env` file.
`.env` is gitignored and excluded from the Docker build context. If you ever
commit one, revoke the token at
<https://lichess.org/account/oauth/token> before doing anything else —
rewriting history does not un-publish it.
