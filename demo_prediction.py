"""
Shows what the engine predicts in three positions, using the bot's own search
code. Needs a Stockfish binary (STOCKFISH_PATH, or one the bot can find).

Run by hand: python demo_prediction.py
"""
import os

os.environ.setdefault('TOKEN', 'not_used_by_this_script')

from bot import get_move_prediction, init_stockfish

POSITIONS = [
    ("Italian Game, black to move", "r1bqkbnr/pppp1ppp/2n5/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R b KQkq - 3 3"),
    ("Queen's Gambit Declined structure, white to move", "r1bq1rk1/ppp2ppp/2n2n2/3p4/1b1P4/2NBP3/PPP2PPP/R1BQ1RK1 w - - 0 8"),
    ("Back-rank mate in one (Rd8#)", "6k1/5ppp/8/8/8/8/5PPP/3R2K1 w - - 0 1"),
]


def main():
    # An opponent rated 2000 gets the strength limit, as in a real game.
    stockfish = init_stockfish(opponent_rating=2000)

    for name, fen in POSITIONS:
        stockfish.set_fen_position(fen)
        move, mate, cp = get_move_prediction(stockfish, "demo", move_time_ms=1000)
        if move is None:
            print(f"{name}: the search returned no move")
            continue
        score = f"mate in {mate}" if mate is not None else f"{cp:+d} cp for the side to move"
        print(f"{name}: {move} ({score})")


if __name__ == "__main__":
    main()
