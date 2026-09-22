# Contributing

Thanks for taking an interest in Axiom Chess Bot.

## Branch model

`dev` is the default branch and where all work lands. `main` is the released
line: it only ever moves by promotion from `dev`, and only when `dev`'s CI is
green.

```
dev   ──●──●──●──●──────────●───────►   all work, CI runs on every push
                            │ promote (manual, refuses on red CI)
main  ──●───────────────────●───────►   released line, images built from here
```

| Change | How it lands |
| ------ | ------------ |
| Maintainer's routine work | Pushed straight to `dev`. No branch, no PR. |
| Anything tracked by an issue | Branch off `dev`, PR into `dev`, reference the issue. |
| Outside contribution | Fork, branch off `dev`, PR into `dev`. |
| Dependency bumps | Straight to `dev`, or merge the Dependabot PR if one is open. |
| `dev` → `main` | The **Promote dev to main** workflow, run manually. |

Never commit to `main` directly, and never force-push either branch.

## Getting set up

```bash
./scripts/setup_venv.sh          # creates venv/ and installs requirements
source venv/bin/activate
cp .env.example .env             # then put your Lichess token in it
```

You need a [Lichess BOT account](https://lichess.org/api#tag/Bot) and a token
with the `board:play` and `bot:play` scopes.

## Before you push

```bash
pytest
```

The suite must be green. CI runs it on Python 3.11, 3.12 and 3.13, so avoid
syntax that only works on the newest of those.

Never commit `.env`, a token, or anything else secret. If you do, revoke the
token immediately — see [SECURITY.md](SECURITY.md).

## Commits

One topic per commit, and the message is a single
[Conventional Commits](https://www.conventionalcommits.org/) subject line with
no body:

```
fix: cap first-move time to prevent game abort
ci: add codeql analysis
docs: correct the tablebase path
```

Common types: `feat`, `fix`, `docs`, `ci`, `build`, `chore`, `refactor`, `test`.

If a change covers four topics, it is four commits.

## Pull requests

Only needed for issue-driven and outside work. Keep the description to what the
change does and how it was verified, and link the issue it closes.

A PR needs green CI before it is merged. Mark a breaking change with the
`breaking` label.

## Reporting bugs

Open an issue using the bug report template. Include the bot version, how the
bot is running (venv or Docker), the relevant lines from `logs/axiom_bot.log`,
and the Lichess game URL if a specific game is involved.

Security problems do **not** go in a public issue — see [SECURITY.md](SECURITY.md).
