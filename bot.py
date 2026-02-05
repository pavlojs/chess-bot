"""
Axiom Chess Bot – stable BOT API architecture using Berserk and Stockfish
"""

import signal
import threading
import logging
import chess
import berserk

from stockfish import Stockfish, StockfishException
from typing import Dict, Any

from config import (
    TOKEN,
    STOCKFISH_PATH,
    STOCKFISH_TIME,
    UCI_OPTIONS,
    ACCEPT_CHALLENGES,
    MIN_RATING,
    MAX_RATING,
    TIME_CONTROL,
    DYNAMIC_STRENGTH,
    STRENGTH_ADVANTAGE,
)

from logging_config import setup_logger

logger = setup_logger(__name__)
shutdown_requested = False


# ─────────────────────────────────────────────
# SIGNAL HANDLING
# ─────────────────────────────────────────────

def handle_shutdown(signum, frame):
    global shutdown_requested
    shutdown_requested = True
    logger.warning("Shutdown signal received")


signal.signal(signal.SIGINT, handle_shutdown)
signal.signal(signal.SIGTERM, handle_shutdown)


# ─────────────────────────────────────────────
# UTILS
# ─────────────────────────────────────────────

def determine_time_category(limit: int, increment: int) -> str:
    total = limit + increment * 40
    if total < 180:
        return "bullet"
    elif total < 480:
        return "blitz"
    elif total < 1500:
        return "rapid"
    return "classical"


def should_accept_challenge(challenge: Dict[str, Any]) -> bool:
    if not ACCEPT_CHALLENGES:
        return False

    challenger = challenge.get("challenger", {})
    rating = challenger.get("rating", 1500)

    clock = challenge.get("timeControl", {})
    limit = clock.get("limit", 0)
    increment = clock.get("increment", 0)

    category = determine_time_category(limit, increment)

    if not (MIN_RATING <= rating <= MAX_RATING):
        return False

    if category not in TIME_CONTROL:
        return False

    logger.info(f"Accepting challenge from {rating} ({category})")
    return True


def init_stockfish(opponent_rating: int | None = None) -> Stockfish:
    sf = Stockfish(
        path=STOCKFISH_PATH,
        parameters=UCI_OPTIONS.copy(),
    )

    if DYNAMIC_STRENGTH and opponent_rating:
        elo = min(max(opponent_rating + STRENGTH_ADVANTAGE, 800), 2850)
        sf.update_engine_parameters({
            "UCI_LimitStrength": True,
            "UCI_Elo": elo,
        })
        logger.info(f"Stockfish strength set to {elo}")

    return sf


# ─────────────────────────────────────────────
# GAME THREAD
# ─────────────────────────────────────────────

def play_game(client: berserk.Client, game_id: str):
    logger.info(f"Starting game thread {game_id}")

    board = chess.Board()
    stockfish: Stockfish | None = None
    bot_is_white: bool | None = None

    try:
        stream = client.bots.stream_game_state(game_id)

        for event in stream:
            if shutdown_requested:
                break

            if event["type"] == "gameFull":
                board.reset()

                moves = event["state"]["moves"].split()
                for move in moves:
                    board.push_uci(move)

                white_id = event["white"]["id"]
                bot_id = event.get("botId")
                bot_is_white = (white_id == bot_id)

                opponent = event["black"] if bot_is_white else event["white"]
                opponent_rating = opponent.get("rating")

                stockfish = init_stockfish(opponent_rating)

                logger.info(
                    f"Game {game_id}: playing as "
                    f"{'white' if bot_is_white else 'black'} "
                    f"vs {opponent_rating}"
                )

            elif event["type"] == "gameState":
                if event.get("moves"):
                    last_move = event["moves"].split()[-1]
                    board.push_uci(last_move)

            else:
                continue

            if board.is_game_over():
                logger.info(f"Game {game_id} finished")
                break

            if bot_is_white is None or stockfish is None:
                continue

            is_my_turn = (
                (board.turn == chess.WHITE and bot_is_white) or
                (board.turn == chess.BLACK and not bot_is_white)
            )

            if not is_my_turn:
                continue

            try:
                stockfish.set_fen_position(board.fen())
                move = stockfish.get_best_move_time(STOCKFISH_TIME)

                if move:
                    client.bots.make_move(game_id, move)
                    board.push_uci(move)
                    logger.info(f"[{game_id}] Played {move}")

            except StockfishException as e:
                logger.error(f"Stockfish error in game {game_id}: {e}")
                break

    except Exception as e:
        logger.error(f"Game {game_id} crashed: {e}", exc_info=True)

    finally:
        if stockfish and hasattr(stockfish, "_stockfish"):
            stockfish._stockfish.terminate()
        logger.info(f"Game thread {game_id} exited")


# ─────────────────────────────────────────────
# MAIN LOOP
# ─────────────────────────────────────────────

def main():
    session = berserk.TokenSession(TOKEN)
    client = berserk.Client(session)

    account = client.account.get()
    
    is_bot = account.get("title") == "BOT"
    if not is_bot:
        raise RuntimeError("This account is NOT a BOT account")

    logger.info("Bot account verified: %s", account.get("username"))

    active_games: Dict[str, threading.Thread] = {}

    for event in client.bots.stream_incoming_events():
        if shutdown_requested:
            break

        try:
            if event["type"] == "challenge":
                challenge = event["challenge"]
                cid = challenge["id"]

                if should_accept_challenge(challenge):
                    client.bots.accept_challenge(cid)
                else:
                    client.bots.decline_challenge(cid)

            elif event["type"] == "gameStart":
                game_id = event["game"]["id"]

                thread = threading.Thread(
                    target=play_game,
                    args=(client, game_id),
                    daemon=True,
                )
                active_games[game_id] = thread
                thread.start()

                logger.info(f"Game {game_id} started")

        except Exception as e:
            logger.error(f"Main loop error: {e}", exc_info=True)

    logger.info("Shutting down bot")


if __name__ == "__main__":
    main()
