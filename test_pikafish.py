"""
Test nhanh Pikafish engine — không cần camera/robot/pygame.
Chạy: py test_pikafish.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config
import xiangqi
from pikafish_engine import PikafishEngine

print("=" * 55)
print("  PIKAFISH ENGINE TEST")
print("=" * 55)
print(f"EXE  : {config.PIKAFISH_EXE}")
print(f"NNUE : {config.PIKAFISH_NNUE}")
print(f"Think: {config.PIKAFISH_THINK_MS} ms")
print("-" * 55)

# Kiểm tra file tồn tại
if not os.path.isfile(config.PIKAFISH_EXE):
    print(f"❌ Không tìm thấy file exe: {config.PIKAFISH_EXE}")
    sys.exit(1)
if not os.path.isfile(config.PIKAFISH_NNUE):
    print(f"⚠️  Không tìm thấy file nnue: {config.PIKAFISH_NNUE}")
    print("   → Pikafish sẽ dùng evaluation mặc định (yếu hơn)")

# Khởi động engine
try:
    engine = PikafishEngine(config.PIKAFISH_EXE)
    engine.start(nnue_path=config.PIKAFISH_NNUE if os.path.isfile(config.PIKAFISH_NNUE) else None)
    print("✅ Engine started!")
except Exception as e:
    print(f"❌ Lỗi khởi động engine: {e}")
    sys.exit(1)

# Test với thế cờ ban đầu — Pikafish đi quân ĐEN
board = xiangqi.get_board()
print(f"\n🎯 Đang hỏi Pikafish nước đi tốt nhất cho Đen ({config.PIKAFISH_THINK_MS}ms)...")

try:
    fen = engine.board_to_fen(board, 'b')
    print(f"📋 FEN: {fen}")
    move = engine.pick_best_move(board, 'b', movetime_ms=config.PIKAFISH_THINK_MS)
    if move:
        src, dst = move
        piece = board[src[1]][src[0]]
        print(f"\n✅ PIKAFISH HOẠT ĐỘNG!")
        print(f"   Nước đi: {piece}  ({src[0]},{src[1]}) → ({dst[0]},{dst[1]})")
    else:
        print("⚠️ Pikafish không trả về nước đi (None).")
except Exception as e:
    print(f"❌ Lỗi khi lấy nước đi: {e}")
finally:
    engine.stop()
    print("\n🔚 Engine stopped.")
    print("=" * 55)
