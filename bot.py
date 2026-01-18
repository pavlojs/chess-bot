import asyncio
import berserk
from stockfish import Stockfish
import chess
from config import *

async def main():
    session = berserk.TokenSession(TOKEN)
    client = berserk.Client(session)

    # Initialize Stockfish
    stockfish = Stockfish(path=STOCKFISH_PATH, depth=STOCKFISH_DEPTH, parameters=UCI_OPTIONS)

    async for event in client.board.stream_incoming_events():
        if event['type'] == 'challenge':
            challenge = event['challenge']
            if should_accept_challenge(challenge):
                await client.board.accept_challenge(challenge['id'])
                print(f"Accepted challenge: {challenge['id']}")
        elif event['type'] == 'gameStart':
            game = event['game']
            game_id = game['id']
            bot_color = game['color']  # 'white' or 'black'
            asyncio.create_task(play_game(client, stockfish, game_id, bot_color))

def should_accept_challenge(challenge):
    if not ACCEPT_CHALLENGES:
        return False
    challenger_rating = challenge.get('challenger', {}).get('rating', 1500)
    if challenger_rating < MIN_RATING or challenger_rating > MAX_RATING:
        return False
    time_control = challenge.get('timeControl', {}).get('type', 'unknown')
    if time_control not in TIME_CONTROL:
        return False
    return True

async def play_game(client, stockfish, game_id, bot_color):
    game_stream = client.board.stream_game_state(game_id)
    board = chess.Board()

    async for event in game_stream:
        if event['type'] == 'gameFull':
            # Initial game state
            state = event['state']
            moves = state.get('moves', '').split()
            for move in moves:
                board.push_uci(move)
        elif event['type'] == 'gameState':
            # Update moves
            moves = event.get('moves', '').split()
            board = chess.Board()
            for move in moves:
                board.push_uci(move)

            # Check if it's bot's turn
            is_white_turn = board.turn == chess.WHITE
            bot_is_white = bot_color == 'white'
            if is_white_turn == bot_is_white:
                # Bot's turn
                stockfish.set_fen_position(board.fen())
                best_move = stockfish.get_best_move_time(STOCKFISH_TIME)
                if best_move:
                    await client.board.make_move(game_id, best_move)
                    print(f"Made move: {best_move}")
                else:
                    print("No move found")

            if event['status'] != 'started':
                print(f"Game ended: {event['status']}")
                break

if __name__ == "__main__":
    asyncio.run(main())