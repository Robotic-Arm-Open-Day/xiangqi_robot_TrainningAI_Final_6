# =============================================================================
# === FILE: pikafish_engine.py ===
# === Bridge between our custom board format and the Pikafish UCI engine. ===
# =============================================================================
#
# SETUP:
#   1. Download Pikafish for Windows from: https://github.com/official-pikafish/Pikafish/releases
#      (e.g. pikafish-windows-x86-64-avx2.exe)
#   2. Download the NNUE network file from: http://test.pikafish.org
#      (e.g. pikafish.nnue)
#   3. Place BOTH files in:  <project_root>/pikafish/
#   4. Set PIKAFISH_PATH in config.py OR pass the path directly to PikafishEngine().
#
# USAGE (drop-in replacement for ai.pick_best_move):
#
#   from pikafish_engine import PikafishEngine
#   engine = PikafishEngine("pikafish/pikafish-windows-x86-64-avx2.exe")
#   engine.start()
#   move = engine.pick_best_move(board, "b", movetime_ms=3000)
#   engine.stop()

import subprocess
import threading
import time
import os
import atexit


class PikafishEngine:
    """
    UCI bridge for the Pikafish Xiangqi engine.

    Coordinate systems:
      - Our board  : board[row][col], row=0 is Black's back rank, row=9 is Red's back rank
      - UCI / FEN  : ranks 0-9 from RED's back rank upward → '0' == our row 9, '9' == our row 0
                     files a-i → columns 0-8 left-to-right
    """

    # -------------------------------------------------------------------------
    # Piece mapping: our token → FEN character  (upper=Red, lower=Black)
    # Note: Elephant = 'B' (bishop) in standard Pikafish FEN
    # -------------------------------------------------------------------------
    _PIECE_TO_FEN = {
        'r_K': 'K', 'r_A': 'A', 'r_E': 'B', 'r_N': 'N',
        'r_R': 'R', 'r_C': 'C', 'r_P': 'P',
        'b_K': 'k', 'b_A': 'a', 'b_E': 'b', 'b_N': 'n',
        'b_R': 'r', 'b_C': 'c', 'b_P': 'p',
    }

    def __init__(self, engine_path: str):
        """
        Args:
            engine_path: Absolute or relative path to the Pikafish .exe file.
        """
        if not os.path.isfile(engine_path):
            raise FileNotFoundError(
                f"[PIKAFISH] Engine not found at: {engine_path}\n"
                "Download from: https://github.com/official-pikafish/Pikafish/releases"
            )
        self.engine_path = engine_path
        self.process: subprocess.Popen | None = None
        self._lock = threading.Lock()
        self._ready = False

    # -------------------------------------------------------------------------
    # Lifecycle
    # -------------------------------------------------------------------------

    def start(self, nnue_path: str | None = None):
        """
        Launch the Pikafish subprocess and wait for 'uciok'.

        Args:
            nnue_path: Optional path to the .nnue network file.
                       If None, Pikafish will look for it next to the exe.
        """
        self.process = subprocess.Popen(
            [self.engine_path],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            encoding='utf-8',
            bufsize=1,            # line-buffered
            cwd=os.path.dirname(os.path.abspath(self.engine_path)),
        )

        # Đăng ký atexit handler để đảm bảo subprocess bị kill khi thoát
        atexit.register(self._atexit_cleanup)

        # Optionally tell the engine where the NNUE file is
        if nnue_path and os.path.isfile(nnue_path):
            self._send(f'setoption name EvalFile value {os.path.abspath(nnue_path)}')

        self._send('uci')

        # Wait for 'uciok' (with 10-second timeout)
        deadline = time.time() + 10
        while time.time() < deadline:
            line = self.process.stdout.readline().strip()
            if line == 'uciok':
                self._ready = True
                print("[PIKAFISH] ✅ Engine ready!")
                return
        raise RuntimeError("[PIKAFISH] Engine did not respond with 'uciok' in time.")

    def _atexit_cleanup(self):
        """Được gọi bởi atexit — force kill subprocess nếu vẫn còn chạy."""
        if self.process and self.process.poll() is None:
            try:
                self.process.kill()
                self.process.wait(timeout=2)
                print("[PIKAFISH] 🛑 atexit: subprocess killed.")
            except Exception:
                pass

    def stop(self):
        """Gracefully shut down the engine subprocess."""
        if self.process:
            try:
                self._send('quit')
                self.process.wait(timeout=3)
            except Exception:
                try:
                    self.process.terminate()
                    self.process.wait(timeout=2)
                except Exception:
                    self.process.kill()
            self.process = None
            self._ready = False
            print("[PIKAFISH] Engine stopped.")

    def __del__(self):
        self.stop()

    # -------------------------------------------------------------------------
    # Core public method — drop-in replacement for ai.pick_best_move()
    # -------------------------------------------------------------------------

    def pick_best_move(self, board: list, color: str, movetime_ms: int = 3000):
        """
        Ask Pikafish for the best move from the given board position.

        Args:
            board      : 10×9 list-of-lists (our custom format).
            color      : 'r' for Red, 'b' for Black.
            movetime_ms: Time allowed for search, in milliseconds.

        Returns:
            ((src_col, src_row), (dst_col, dst_row))  in our coordinate system,
            or None if the engine has no move.
        """
        if not self._ready:
            raise RuntimeError("[PIKAFISH] Engine is not started. Call engine.start() first.")

        with self._lock:
            fen = self.board_to_fen(board, color)
            print(f"[PIKAFISH] FEN: {fen}")

            self._send(f'position fen {fen}')
            self._send(f'go movetime {movetime_ms}')

            # Read lines until we get 'bestmove ...'
            best_move_str = None
            deadline = time.time() + (movetime_ms / 1000) + 5  # generous timeout
            while time.time() < deadline:
                line = self.process.stdout.readline().strip()
                if not line:
                    continue
                if line.startswith('bestmove'):
                    parts = line.split()
                    best_move_str = parts[1] if len(parts) > 1 else None
                    print(f"[PIKAFISH] bestmove: {best_move_str}")
                    break

            if best_move_str and best_move_str != '(none)' and best_move_str != 'null':
                return self._uci_to_move(best_move_str)

            print("[PIKAFISH] ⚠️ No valid move returned.")
            return None

    # -------------------------------------------------------------------------
    # Board → FEN conversion
    # -------------------------------------------------------------------------

    def board_to_fen(self, board: list, color: str) -> str:
        """
        Convert our 10×9 board to a Xiangqi FEN string.

        Our board[0] = Black's back rank = FEN rank 9 (top of string).
        Our board[9] = Red's  back rank = FEN rank 0 (bottom of string).

        FEN colour: 'w' = Red to move, 'b' = Black to move.
        """
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
                    fen_char = self._PIECE_TO_FEN.get(p)
                    if fen_char is None:
                        raise ValueError(f"Unknown piece token: '{p}' at board[{r}][{c}]")
                    row_str += fen_char
            if empty:
                row_str += str(empty)
            rows.append(row_str)

        fen_color = 'w' if color == 'r' else 'b'
        # FEN format: <position> <color> - - 0 1
        return f"{'/'.join(rows)} {fen_color} - - 0 1"

    # -------------------------------------------------------------------------
    # UCI move → our coordinate format
    # -------------------------------------------------------------------------

    def _uci_to_move(self, uci_move: str):
        """
        Convert a UCI move string to our ((src_col, src_row), (dst_col, dst_row)) format.

        UCI move format: <file><rank><file><rank>  e.g. 'h2e2', 'e9e8'
          - file: 'a'–'i' → column 0–8
          - rank: '0'–'9' → UCI rank (0 = Red's back rank = our row 9)
        """
        if len(uci_move) < 4:
            return None
        src_col = ord(uci_move[0]) - ord('a')      # 'a'=0 ... 'i'=8
        src_row = 9 - int(uci_move[1])             # UCI rank 0 → our row 9, rank 9 → our row 0
        dst_col = ord(uci_move[2]) - ord('a')
        dst_row = 9 - int(uci_move[3])
        return (src_col, src_row), (dst_col, dst_row)

    # -------------------------------------------------------------------------
    # Internal helper
    # -------------------------------------------------------------------------

    def _send(self, cmd: str):
        """Write a command line to the engine's stdin."""
        self.process.stdin.write(cmd + '\n')
        self.process.stdin.flush()


# =============================================================================
# Quick self-test  (run: python pikafish_engine.py)
# =============================================================================
if __name__ == '__main__':
    import sys
    import xiangqi

    exe = input("Enter path to pikafish exe: ").strip().strip('"')
    nnue = input("Enter path to .nnue file (or blank): ").strip().strip('"') or None

    engine = PikafishEngine(exe)
    engine.start(nnue_path=nnue)

    board = xiangqi.get_board()
    print("\nStarting position FEN:", engine.board_to_fen(board, 'r'))

    print("\nAsking Pikafish for best move for Black...")
    move = engine.pick_best_move(board, 'b', movetime_ms=2000)
    print(f"Best move: {move}")

    engine.stop()
    print("Done.")
