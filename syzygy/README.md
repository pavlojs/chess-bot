# Syzygy tablebases

Syzygy tablebases hold the exact result of every chess position with up to 7 pieces on the board, kings included. With them Stockfish plays those endgames perfectly, and steers towards or away from them during the search of positions with more pieces.

They come as two kinds of file. `.rtbw` files (WDL) say whether a position is won, drawn or lost; the search uses them. `.rtbz` files (DTZ) say how far the next capture or pawn move is; the engine uses them to convert a won position without running into the 50-move rule. Stockfish needs both to play a tablebase win out.

## Getting the files

The tables are published as individual files, not as archives. The Lichess mirror at https://tablebase.lichess.ovh/tables/standard/ has them by piece count, and https://syzygy-tables.info/ links to further sources.

| Tables | Size (WDL and DTZ together) |
| --- | --- |
| 3, 4 and 5 pieces | about 1 GB |
| 6 pieces | about 160 GB |
| 7 pieces | 17 to 18 TB |

Start with the 3-, 4- and 5-piece tables. The 6-piece set is worth having only on an SSD, and the 7-piece set is out of reach for most machines.

## Using them with the bot

1. Put the `.rtbw` and `.rtbz` files in this directory, next to this file.
2. Restart the bot.

On startup the bot looks into `./syzygy` and, if it finds any `.rtbw` or `.rtbz` file there, hands the directory to Stockfish as `SyzygyPath`. With no files the option is left unset and the bot plays without tablebases. To keep the files elsewhere, set `SF_SYZYGY_PATH` to that directory.

In the container the directory is `/app/syzygy`: mount your files there read-only, for example `./syzygy:/app/syzygy:ro`. They are not part of the image.

The bot writes `Syzygy tablebases enabled: <path>` to its log when it has found files. Whether Stockfish could read them shows in the engine itself: start `stockfish`, enter `setoption name SyzygyPath value <path>`, and it answers with the number of tablebases found.
