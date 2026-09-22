---
name: Bug report
about: Something the bot does wrong
title: ''
labels: bug
assignees: ''
---

## What happens

A clear description of the behaviour.

## What should happen instead

## How to reproduce

1.
2.

## Environment

The project publishes no version numbers, so identify the build you are on:

- Commit (`git rev-parse --short HEAD`) or image tag (`latest` / `main-<sha>`):
- Running as: venv / Docker / systemd
- Python version (`python3 --version`):
- Stockfish build (`stockfish compiler | grep "Compilation settings"`):
- CPU architecture (`uname -m`):

The Stockfish line matters: the engine is a universal binary that picks its code
path from the CPU, and a VM with a generic CPU model hides AVX2.

## Logs

Relevant lines from `logs/axiom_bot.log`. Remove your token if it appears.
Set the log level to DEBUG if the failure is intermittent — the best-effort
cleanup paths only report there.

```
paste here
```

## Game URL (if applicable)

https://lichess.org/...
