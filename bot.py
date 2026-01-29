"""
Lichess Chess Bot powered by Stockfish
"""

import asyncio
import signal
import sys
from typing import Dict, Optional, Any
import logging

import berserk
from stockfish import Stockfish, StockfishException
import chess

from config import (
    TOKEN, STOCKFISH_PATH, STOCKFISH_DEPTH, STOCKFISH_TIME, 
    UCI_OPTIONS, ACCEPT_CHALLENGES, MIN_RATING, MAX_RATING, 
    TIME_CONTROL, STOCKFISH_TIMEOUT, DYNAMIC_STRENGTH, STRENGTH_ADVANTAGE
)
from logging_config import setup_logger

logger = setup_logger(__name__)

# Global flag for graceful shutdown
_shutdown_requested = False


def handle_shutdown_signal(signum: int, frame) -> None:
    """Handle shutdown signals gracefully."""
    global _shutdown_requested
    _shutdown_requested = True
    logger.warning(f"Shutdown signal received (signal {signum}). Cleaning up...")


def get_dynamic_uci_options(challenger_rating: int) -> Dict[str, Any]:
    """
    Calculate UCI options for Stockfish based on opponent rating.
    Bot will be set to slightly stronger than opponent.
    
    Args:
        challenger_rating: ELO rating of the challenger
        
    Returns:
        Dictionary of UCI options with dynamically adjusted strength
    """
    if not DYNAMIC_STRENGTH:
        return UCI_OPTIONS.copy()
    
    # Calculate bot ELO: opponent + advantage
    bot_elo = min(challenger_rating + STRENGTH_ADVANTAGE, 2850)  # Cap at Stockfish max
    bot_elo = max(bot_elo, 800)  # Floor at Stockfish min
    
    # Create modified UCI options
    dynamic_options = UCI_OPTIONS.copy()
    dynamic_options["UCI_Elo"] = bot_elo
    dynamic_options["UCI_LimitStrength"] = True
    
    logger.info(f"Dynamic strength enabled: opponent {challenger_rating} → bot {bot_elo} Elo")
    return dynamic_options


def should_accept_challenge(challenge: Dict) -> bool:
    """
    Determine if the bot should accept a challenge.
    
    Args:
        challenge: Challenge data from Lichess API
        
    Returns:
        True if challenge should be accepted, False otherwise
    """
    if not ACCEPT_CHALLENGES:
        logger.debug("Challenge rejected: bot not accepting challenges")
        return False
    
    try:
        challenger_rating = challenge.get('challenger', {}).get('rating', 1500)
        if challenger_rating < MIN_RATING or challenger_rating > MAX_RATING:
            logger.debug(f"Challenge rejected: rating {challenger_rating} outside range [{MIN_RATING}, {MAX_RATING}]")
            return False
        
        time_control = challenge.get('timeControl', {}).get('type', 'unknown')
        if time_control not in TIME_CONTROL:
            logger.debug(f"Challenge rejected: time control '{time_control}' not in {TIME_CONTROL}")
            return False
        
        logger.info(f"Challenge accepted from {challenger_rating} rated opponent ({time_control})")
        return True
    except Exception as e:
        logger.error(f"Error evaluating challenge: {e}", exc_info=True)
        return False


def initialize_stockfish() -> Optional[Stockfish]:
    """
    Initialize Stockfish engine with configured parameters.
    
    Returns:
        Initialized Stockfish instance or None if initialization fails
    """
    try:
        if not STOCKFISH_PATH:
            logger.error("Stockfish path not configured or binary not found")
            return None
        
        logger.info(f"Initializing Stockfish from {STOCKFISH_PATH}")
        stockfish = Stockfish(
            path=STOCKFISH_PATH,
            depth=STOCKFISH_DEPTH,
            parameters=UCI_OPTIONS
        )
        logger.info("Stockfish initialized successfully")
        return stockfish
    except Exception as e:
        logger.error(f"Failed to initialize Stockfish: {e}", exc_info=True)
        return None


async def play_game(
    client: berserk.Client,
    stockfish: Stockfish,
    game_id: str,
    bot_color: str,
    challenger_rating: Optional[int] = None
) -> None:
    """
    Play a single game for the bot.
    
    Args:
        client: Berserk client for API communication
        stockfish: Initialized Stockfish engine
        game_id: ID of the game to play
        bot_color: Bot's color ('white' or 'black')
        challenger_rating: ELO rating of the challenger (optional)
    """
    board = chess.Board()
    
    # Apply dynamic strength settings if challenger rating is provided
    if challenger_rating is not None:
        dynamic_options = get_dynamic_uci_options(challenger_rating)
        try:
            for key, value in dynamic_options.items():
                if key != "SyzygyPath":  # Skip non-parameter options
                    stockfish.update_engine_parameters({key: value})
            logger.debug(f"Applied dynamic strength for game {game_id}")
        except Exception as e:
            logger.warning(f"Failed to apply dynamic strength: {e}")
    
    try:
        logger.info(f"Starting game {game_id} as {bot_color}")
        game_stream = client.board.stream_game_state(game_id)
        
        async for event in game_stream:
            if _shutdown_requested:
                logger.info(f"Shutdown requested, aborting game {game_id}")
                break
            
            try:
                if event['type'] == 'gameFull':
                    # Initial game state
                    state = event['state']
                    moves_str = state.get('moves', '')
                    
                    # Reset board and apply moves incrementally
                    board = chess.Board()
                    if moves_str.strip():
                        for move_uci in moves_str.split():
                            try:
                                board.push_uci(move_uci)
                            except ValueError as e:
                                logger.error(f"Invalid move in gameFull: {move_uci}, {e}")
                                continue
                    
                    logger.debug(f"Game state initialized: {board.fen()}")
                
                elif event['type'] == 'gameState':
                    # Update game state with new moves
                    moves_str = event.get('moves', '')
                    
                    # Rebuild board from moves
                    board = chess.Board()
                    if moves_str.strip():
                        for move_uci in moves_str.split():
                            try:
                                board.push_uci(move_uci)
                            except ValueError as e:
                                logger.error(f"Invalid move in gameState: {move_uci}, {e}")
                                continue
                    
                    # Check if it's bot's turn
                    is_white_turn = board.turn == chess.WHITE
                    bot_is_white = bot_color == 'white'
                    
                    if is_white_turn == bot_is_white and board.is_game_over() is False:
                        # Bot's turn - get best move
                        try:
                            stockfish.set_fen_position(board.fen())
                            logger.debug(f"Thinking for move (depth {STOCKFISH_DEPTH}, time {STOCKFISH_TIME}ms)")
                            
                            best_move = await asyncio.wait_for(
                                asyncio.to_thread(stockfish.get_best_move_time, STOCKFISH_TIME),
                                timeout=STOCKFISH_TIMEOUT
                            )
                            
                            if best_move:
                                await client.board.make_move(game_id, best_move)
                                logger.info(f"Played move: {best_move} in game {game_id}")
                            else:
                                logger.warning(f"No move found by Stockfish for game {game_id}")
                        
                        except asyncio.TimeoutError:
                            logger.error(f"Stockfish timeout while thinking for game {game_id}")
                        except StockfishException as e:
                            logger.error(f"Stockfish error: {e}", exc_info=True)
                        except Exception as e:
                            logger.error(f"Unexpected error during move calculation: {e}", exc_info=True)
                    
                    # Check game status
                    game_status = event.get('status', 'started')
                    if game_status != 'started':
                        result = event.get('winner', 'draw')
                        logger.info(f"Game {game_id} ended with status: {game_status} (winner: {result})")
                        break
            
            except Exception as e:
                logger.error(f"Error processing game event in {game_id}: {e}", exc_info=True)
                continue
    
    except Exception as e:
        logger.error(f"Unexpected error in play_game for {game_id}: {e}", exc_info=True)
    finally:
        logger.info(f"Game {game_id} finished")


async def main() -> None:
    """Main bot loop - connect to Lichess and process events."""
    
    logger.info("Chess Bot starting up")
    
    # Initialize Stockfish
    stockfish = initialize_stockfish()
    if not stockfish:
        logger.critical("Failed to initialize Stockfish engine. Exiting.")
        sys.exit(1)
    
    # Create API session
    try:
        session = berserk.TokenSession(TOKEN)
        client = berserk.Client(session)
        logger.info("Connected to Lichess API")
    except Exception as e:
        logger.error(f"Failed to connect to Lichess API: {e}", exc_info=True)
        sys.exit(1)
    
    active_games: Dict[str, asyncio.Task] = {}
    challenger_ratings: Dict[str, int] = {}  # Store challenger ratings by game_id
    
    try:
        logger.info("Listening for incoming events...")
        async for event in client.board.stream_incoming_events():
            if _shutdown_requested:
                logger.info("Shutdown requested, waiting for active games to finish...")
                break
            
            try:
                if event['type'] == 'challenge':
                    challenge = event['challenge']
                    challenge_id = challenge['id']
                    challenger_rating = challenge.get('challenger', {}).get('rating', 1500)
                    
                    if should_accept_challenge(challenge):
                        try:
                            await client.board.accept_challenge(challenge_id)
                            challenger_ratings[challenge_id] = challenger_rating
                            logger.info(f"Accepted challenge: {challenge_id} from {challenger_rating} rated opponent")
                        except Exception as e:
                            logger.error(f"Failed to accept challenge {challenge_id}: {e}", exc_info=True)
                    else:
                        try:
                            await client.board.decline_challenge(challenge_id, reason='later')
                            logger.debug(f"Declined challenge: {challenge_id}")
                        except Exception as e:
                            logger.debug(f"Failed to decline challenge {challenge_id}: {e}")
                
                elif event['type'] == 'gameStart':
                    game = event['game']
                    game_id = game['id']
                    bot_color = game['color']
                    
                    # Get challenger rating for this game
                    challenger_rating = challenger_ratings.get(game_id)
                    
                    # Create task for this game
                    task = asyncio.create_task(
                        play_game(client, stockfish, game_id, bot_color, challenger_rating)
                    )
                    active_games[game_id] = task
                    logger.info(f"Game started: {game_id} (playing as {bot_color})")
                    
                    # Clean up finished game tasks
                    active_games = {
                        gid: t for gid, t in active_games.items() 
                        if not t.done()
                    }
            
            except Exception as e:
                logger.error(f"Error processing incoming event: {e}", exc_info=True)
                continue
    
    except Exception as e:
        logger.error(f"Error in main loop: {e}", exc_info=True)
    
    finally:
        # Graceful shutdown
        logger.info("Shutting down gracefully...")
        
        # Cancel remaining game tasks
        for game_id, task in active_games.items():
            if not task.done():
                logger.info(f"Cancelling game task: {game_id}")
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        
        # Close Stockfish
        try:
            stockfish.quit()
            logger.info("Stockfish engine closed")
        except Exception as e:
            logger.error(f"Error closing Stockfish: {e}")
        
        logger.info("Chess Bot shut down successfully")


if __name__ == "__main__":
    # Setup signal handlers for graceful shutdown
    signal.signal(signal.SIGTERM, handle_shutdown_signal)
    signal.signal(signal.SIGINT, handle_shutdown_signal)
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as e:
        logger.critical(f"Unexpected error: {e}", exc_info=True)
        sys.exit(1)