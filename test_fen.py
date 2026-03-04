"""Quick FEN test: verify initial FEN length and format for Pikafish compatibility."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import xiangqi

# ============================================================
# 1. Test FEN from main_VIP.py (standalone function)
# ============================================================
_PIECE_TO_FEN = {
    'r_K': 'K', 'r_A': 'A', 'r_E': 'B', 'r_N': 'N',
    'r_R': 'R', 'r_C': 'C', 'r_P': 'P',
    'b_K': 'k', 'b_A': 'a', 'b_E': 'b', 'b_N': 'n',
    'b_R': 'r', 'b_C': 'c', 'b_P': 'p',
}

def board_array_to_fen(board, color='r', move_number=1):
    rows = []
    for r in range(10):
        row_str = ''
        empty = 0
        for c in range(9):
            p = board[r][c]
            if p == '.':
                empty += 1
            else:
                if empty:
                    row_str += str(empty)
                    empty = 0
                fen_char = _PIECE_TO_FEN.get(p)
                if fen_char is None:
                    raise ValueError(f"Unknown piece: '{p}' at board[{r}][{c}]")
                row_str += fen_char
        if empty:
            row_str += str(empty)
        rows.append(row_str)

    fen_color = 'w' if color == 'r' else 'b'
    return f"{'/'.join(rows)} {fen_color} - - 0 {move_number}"

# ============================================================
# 2. Test FEN from pikafish_engine.py (class method)
# ============================================================
from pikafish_engine import PikafishEngine

# Get the standard initial board
board = xiangqi.get_board()

print("=" * 70)
print("BOARD STATE (10x9):")
for r, row in enumerate(board):
    print(f"  row {r}: {row}")

print("\n" + "=" * 70)

# FEN from main_VIP.py function
fen_main = board_array_to_fen(board, 'r', 1)
print(f"\n[main_VIP.py] FEN: {fen_main}")
print(f"  Length: {len(fen_main)} chars")
print(f"  Parts: {fen_main.split(' ')}")
print(f"  Num parts: {len(fen_main.split(' '))}")
print(f"  Position part: '{fen_main.split(' ')[0]}'")
print(f"  Ranks: {fen_main.split(' ')[0].split('/')}")
print(f"  Num ranks: {len(fen_main.split(' ')[0].split('/'))}")

# FEN from pikafish_engine.py
# We can't call board_to_fen without an instance, so create a dummy
class DummyEngine:
    _PIECE_TO_FEN = PikafishEngine._PIECE_TO_FEN
    board_to_fen = PikafishEngine.board_to_fen

dummy = DummyEngine()
fen_pikafish = dummy.board_to_fen(board, 'r')
print(f"\n[pikafish_engine.py] FEN: {fen_pikafish}")
print(f"  Length: {len(fen_pikafish)} chars")
print(f"  Parts: {fen_pikafish.split(' ')}")
print(f"  Num parts: {len(fen_pikafish.split(' '))}")

# ============================================================
# 3. Compare with standard initial FEN
# ============================================================
STANDARD_FEN = "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1"
print(f"\n[Standard] FEN: {STANDARD_FEN}")
print(f"  Length: {len(STANDARD_FEN)} chars")

INITIAL_FEN_IN_CODE = "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1"
print(f"\n[INITIAL_FEN in code] FEN: {INITIAL_FEN_IN_CODE}")
print(f"  Length: {len(INITIAL_FEN_IN_CODE)} chars")

print("\n" + "=" * 70)
print("COMPARISON:")
print(f"  main_VIP == standard?    : {fen_main == STANDARD_FEN}")
print(f"  pikafish == standard?    : {fen_pikafish == STANDARD_FEN}")
print(f"  main_VIP == pikafish?    : {fen_main == fen_pikafish}")
print(f"  main_VIP == INITIAL_FEN? : {fen_main == INITIAL_FEN_IN_CODE}")

# ============================================================
# 4. Simulate a move and check FEN
# ============================================================
print("\n" + "=" * 70)
print("SIMULATING: Red Pawn (4,6) -> (4,5)")
import copy
board2 = copy.deepcopy(board)
board2[5][4] = board2[6][4]  # move pawn up
board2[6][4] = '.'
fen_after = board_array_to_fen(board2, 'b', 2)
print(f"  FEN after move: {fen_after}")
print(f"  Length: {len(fen_after)} chars")
print(f"  Num parts: {len(fen_after.split(' '))}")

# Validate each rank
position = fen_after.split(' ')[0]
for i, rank in enumerate(position.split('/')):
    total = 0
    for ch in rank:
        if ch.isdigit():
            total += int(ch)
        else:
            total += 1
    print(f"  Rank {i}: '{rank}' → width={total} {'✅' if total == 9 else '❌ WRONG!'}")

print("\n✅ Test complete!")
