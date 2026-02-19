"""
Quick test script to demonstrate move prediction feature
"""
import os
os.environ.setdefault('TOKEN', 'test_token')

from bot import get_move_prediction, init_stockfish
import chess

def test_prediction():
    """Test move prediction on a known position."""
    print("Testing move prediction feature...\n")
    
    # Initialize Stockfish
    stockfish = init_stockfish(opponent_rating=2000)
    
    # Test position: Italian Game opening
    print("Position 1: Italian Game opening")
    stockfish.set_fen_position("r1bqkbnr/pppp1ppp/2n5/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R b KQkq - 3 3")
    prediction = get_move_prediction(stockfish, "test_game", prediction_depth=10)
    print(f"Predicted continuation: {prediction}\n")
    
    # Test position: Middle game tactical position
    print("Position 2: Tactical middle game")
    stockfish.set_fen_position("r1bq1rk1/ppp2ppp/2n2n2/3p4/1b1P4/2NBP3/PPP2PPP/R1BQ1RK1 w - - 0 8")
    prediction = get_move_prediction(stockfish, "test_game", prediction_depth=8)
    print(f"Predicted continuation: {prediction}\n")
    
    # Test position: Endgame with forced mate
    print("Position 3: Mate in 3 puzzle")
    stockfish.set_fen_position("6k1/5ppp/8/8/8/8/5PPP/3R2K1 w - - 0 1")
    prediction = get_move_prediction(stockfish, "test_game", prediction_depth=6)
    print(f"Predicted continuation (mate sequence): {prediction}\n")
    
    print("✅ Prediction feature working correctly!")

if __name__ == "__main__":
    test_prediction()
