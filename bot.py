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

def determine_time_category(limit: int, increment: int) -> str | None:
    # Reject unlimited time games (limit = 0 and increment = 0)
    if limit == 0 and increment == 0:
        return None
    
    # Reject correspondence games (days per move > 0)
    # In Lichess API, correspondence games have very large limits
    # or are marked differently in variant/speed fields
    if limit >= 259200:  # 3+ days in seconds = correspondence
        return None
    
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
    
    # Check if challenge has speed field (more reliable than calculating)
    speed = challenge.get("speed")
    if speed:
        # Reject correspondence and unlimited time games
        if speed in ["correspondence", "unlimited"]:
            logger.info(f"Rejecting {speed} challenge")
            return False

    clock = challenge.get("timeControl", {})
    limit = clock.get("limit", 0)
    increment = clock.get("increment", 0)

    category = determine_time_category(limit, increment)
    
    # Reject if category is None (unlimited or correspondence)
    if category is None:
        logger.info(f"Rejecting challenge with no valid time category")
        return False

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
        elo = min(max(opponent_rating + STRENGTH_ADVANTAGE, 1320), 2850)
        sf.update_engine_parameters({
            "UCI_LimitStrength": True,
            "UCI_Elo": elo,
        })
        logger.info(f"Stockfish strength set to {elo}")

    return sf


# ─────────────────────────────────────────────
# GAME THREAD
# ─────────────────────────────────────────────

def play_game(client: berserk.Client, game_id: str, bot_username: str):
    logger.info(f"Starting game thread {game_id}")

    board = chess.Board()
    stockfish: Stockfish | None = None
    bot_is_white: bool | None = None
    last_move_count = 0  # Track number of moves processed

    try:
        stream = client.bots.stream_game_state(game_id)

        for event in stream:
            if shutdown_requested:
                break

            if event["type"] == "gameFull":
                board.reset()

                moves = event["state"]["moves"].split() if event["state"]["moves"] else []
                for move in moves:
                    board.push_uci(move)
                
                last_move_count = len(moves)

                white_username = event["white"].get("name", event["white"].get("id", "")).lower()
                black_username = event["black"].get("name", event["black"].get("id", "")).lower()
                bot_is_white = (white_username == bot_username.lower())

                logger.debug(
                    f"[{game_id}] White: {white_username}, Black: {black_username}, "
                    f"Bot: {bot_username.lower()}, Bot is white: {bot_is_white}"
                )

                opponent = event["black"] if bot_is_white else event["white"]
                opponent_rating = opponent.get("rating")

                stockfish = init_stockfish(opponent_rating)

                logger.info(
                    f"Game {game_id}: playing as "
                    f"{'white' if bot_is_white else 'black'} "
                    f"vs {opponent_rating}"
                )
                # Don't continue here - we need to check if it's our turn

            if event["type"] == "gameState":
                moves = event["moves"].split() if event.get("moves") else []
                current_move_count = len(moves)
                
                # Check if game ended (resignation, timeout, etc.)
                status = event.get("status")
                if status in ["mate", "resign", "stalemate", "timeout", "draw", "outoftime", "cheat", "noStart", "unknownFinish", "variantEnd"]:
                    logger.info(f"[{game_id}] Game ended: {status}")
                    break
                
                # Only process new moves
                if current_move_count > last_move_count:
                    new_moves = moves[last_move_count:]
                    for move in new_moves:
                        board.push_uci(move)
                        logger.debug(f"[{game_id}] Applied move {move}, board turn: {board.turn}")
                    last_move_count = current_move_count

                # Handle draw offers
                if event.get("wdraw") or event.get("bdraw"):
                    logger.info(f"[{game_id}] Draw offer received")
                    
                    if stockfish:
                        try:
                            # Evaluate position to decide
                            stockfish.set_fen_position(board.fen())
                            eval_info = stockfish.get_evaluation()
                            
                            # Get centipawn evaluation (positive = bot winning, negative = bot losing)
                            accept_draw = False
                            
                            if eval_info["type"] == "cp":
                                evaluation = eval_info["value"]
                                # Adjust for color (Stockfish always evaluates from white's perspective)
                                if not bot_is_white:
                                    evaluation = -evaluation
                                
                                logger.info(f"[{game_id}] Position evaluation: {evaluation} centipawns")
                                
                                # Accept draw only if position is close to equal (±200 centipawns)
                                # Decline if we have advantage OR disadvantage - let the engine play it out
                                if -200 <= evaluation <= 200:
                                    accept_draw = True
                                    logger.info(f"[{game_id}] Accepting draw offer (balanced position: {evaluation}cp)")
                                elif evaluation > 200:
                                    logger.info(f"[{game_id}] Declining draw offer (we're winning: {evaluation}cp)")
                                else:
                                    logger.info(f"[{game_id}] Declining draw offer (we're losing but engine can play: {evaluation}cp)")
                            else:
                                # If mate evaluation, always decline - let the engine play
                                mate_value = eval_info["value"]
                                if mate_value < 0:
                                    logger.info(f"[{game_id}] Declining draw offer (getting mated in {abs(mate_value)}, but will fight)")
                                else:
                                    logger.info(f"[{game_id}] Declining draw offer (we have mate in {mate_value})")
                            
                            # Send decision via API
                            try:
                                if accept_draw:
                                    client.bots.accept_draw(game_id)
                                else:
                                    client.bots.decline_draw(game_id)
                            except Exception as api_error:
                                logger.error(f"[{game_id}] Failed to respond to draw offer: {api_error}")
                                
                        except Exception as e:
                            logger.error(f"[{game_id}] Error evaluating draw offer: {e}")
                            # On error, decline draw and continue playing
                            try:
                                client.bots.decline_draw(game_id)
                            except:
                                pass

            # After processing event, check if game is over
            if board.is_game_over():
                logger.info(f"Game {game_id} finished")
                break

            # Skip if game not initialized yet
            if bot_is_white is None or stockfish is None:
                logger.debug(f"[{game_id}] Waiting for game initialization...")
                continue

            is_my_turn = (
                (board.turn == chess.WHITE and bot_is_white) or
                (board.turn == chess.BLACK and not bot_is_white)
            )

            if not is_my_turn:
                logger.debug(
                    f"[{game_id}] Not my turn (board.turn={board.turn}, "
                    f"bot_is_white={bot_is_white})"
                )
                continue

            try:
                logger.debug(f"[{game_id}] Calculating move for position: {board.fen()}")
                stockfish.set_fen_position(board.fen())
                move = stockfish.get_best_move_time(STOCKFISH_TIME)

                if move:
                    client.bots.make_move(game_id, move)
                    board.push_uci(move)
                    last_move_count += 1  # Increment move count after our move
                    logger.info(f"[{game_id}] Played {move}")
                else:
                    logger.warning(f"[{game_id}] Stockfish returned no move")

            except StockfishException as e:
                logger.error(f"Stockfish error in game {game_id}: {e}")
                break

    except Exception as e:
        logger.error(f"Game {game_id} crashed: {e}", exc_info=True)

    finally:
        if stockfish:
            try:
                if hasattr(stockfish, "_stockfish") and stockfish._stockfish:
                    stockfish._stockfish.kill()
                    stockfish._stockfish.wait()
            except Exception as e:
                logger.debug(f"[{game_id}] Error during Stockfish cleanup: {e}")
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

    bot_username = account.get("username")
    logger.info("Bot account verified: %s", bot_username)

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
                    args=(client, game_id, bot_username),
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
