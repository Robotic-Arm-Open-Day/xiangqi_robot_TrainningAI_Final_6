# =============================================================================
# === FILE: snapshot_detector.py (T1/T2 Snapshot Move Detection System) ===
# === So sánh 2 snapshot camera (trước/sau khi đi) để phát hiện nước đi ===
# === KHÔNG truy cập camera trực tiếp — nhận frame+detections từ ngoài ===
# =============================================================================
import cv2
import numpy as np
import os
import time


class SnapshotDetector:
    """
    Hệ thống phát hiện nước đi bằng so sánh 2 snapshot (T1/T2).
    
    Dùng OCCUPANCY GRID (có quân / trống) kết hợp với MEMORY BOARD
    để phát hiện nước đi. KHÔNG dựa vào YOLO để phân loại quân đỏ/đen.
    
    Flow:
        1. capture_baseline(frame, detections, board)  → Lưu T1 occupancy + board
        2. Người chơi di chuyển quân trên bàn thật
        3. detect_move(frame, detections)               → So sánh T1 vs T2 → nước đi
        4. AI đi quân
        5. capture_baseline(frame, detections, board)   → Lưu T1 mới
        6. Lặp lại từ bước 2
    
    ⚠️ Module này KHÔNG truy cập camera trực tiếp.
       Frame + detections được truyền vào từ CameraMonitor.
    """

    def __init__(self, perspective_path, class_id_map, num_cols=9, num_rows=10):
        """
        Args:
            perspective_path: đường dẫn file perspective.npy
            class_id_map:     dict {class_id: "r_P", "b_N", ...} (dùng để filter valid detections)
            num_cols:         số cột bàn cờ (9)
            num_rows:         số hàng bàn cờ (10)
        """
        self.perspective_path = str(perspective_path)
        self.class_id_map = class_id_map
        self.num_cols = num_cols
        self.num_rows = num_rows

        # T1 baseline
        self._baseline_occ = None    # occupancy grid: True/False
        self._baseline_time = None

    # -------------------------------------------------------------------------
    # PUBLIC API
    # -------------------------------------------------------------------------

    def capture_baseline(self, frame, detections):
        """Lưu T1 — snapshot baseline trước khi người chơi đi.
        
        Args:
            frame:      OpenCV frame (BGR) từ CameraMonitor
            detections: list of (cls_id, conf, (x1, y1, x2, y2)) từ CameraMonitor
        
        Returns:
            True nếu thành công, False nếu thất bại.
        """
        if frame is None:
            print("[SNAPSHOT] ❌ Không có frame cho T1 baseline!")
            return False

        occ = self._build_occupancy(detections)
        self._baseline_occ = occ
        self._baseline_time = time.time()

        # Debug: đếm quân detect được
        n_occupied = sum(1 for r in occ for cell in r if cell)
        print(f"[SNAPSHOT] 📸 T1 Baseline captured: {n_occupied} quân detected by camera")
        return True

    def detect_move(self, frame, detections, board):
        """Chụp T2 và so sánh với T1 để phát hiện nước đi của quân ĐỎ.
        
        Args:
            frame:      OpenCV frame (BGR) từ CameraMonitor
            detections: list of (cls_id, conf, (x1, y1, x2, y2)) từ CameraMonitor
            board:      memory board hiện tại (10x9 list, biết quân nào ở đâu)
        
        Returns:
            (src, dst, piece_name) nếu phát hiện nước đi hợp lệ
            (None, None, None) nếu không phát hiện được
        """
        if self._baseline_occ is None:
            print("[SNAPSHOT] ⚠️ Chưa có T1 baseline! Gọi capture_baseline() trước.")
            return None, None, None

        if frame is None:
            print("[SNAPSHOT] ❌ Không có frame cho T2!")
            return None, None, None

        # Build T2 occupancy
        t2_occ = self._build_occupancy(detections)

        # Debug
        n_occupied = sum(1 for r in t2_occ for cell in r if cell)
        print(f"[SNAPSHOT] 📸 T2 captured: {n_occupied} quân detected")

        # So sánh T1 vs T2 (dùng occupancy + memory board)
        return self._compare_snapshots(self._baseline_occ, t2_occ, board)

    def has_baseline(self):
        """Kiểm tra đã có T1 baseline chưa."""
        return self._baseline_occ is not None

    def clear_baseline(self):
        """Xóa T1 baseline (dùng khi reset game)."""
        self._baseline_occ = None
        self._baseline_time = None
        print("[SNAPSHOT] 🗑️ Baseline cleared.")

    def get_baseline_grid(self):
        """Trả về occupancy grid T1 hiện tại (hoặc None)."""
        return self._baseline_occ

    # -------------------------------------------------------------------------
    # INTERNAL: Build occupancy grid từ detections
    # -------------------------------------------------------------------------

    def _build_occupancy(self, detections):
        """Convert detections → 10x9 occupancy grid (True/False).
        
        Không dựa vào class_id để phân loại quân — chỉ check "có quân / trống".
        
        Args:
            detections: list of (cls_id, conf, (x1, y1, x2, y2))
        
        Returns:
            10x9 grid of booleans (True = occupied, False = empty)
        """
        M = None
        if os.path.exists(self.perspective_path):
            M = np.load(self.perspective_path)

        grid = [[False for _ in range(self.num_cols)] for _ in range(self.num_rows)]
        if M is None:
            return grid

        for cls_id, conf, (x1, y1, x2, y2) in detections:
            # Chấp nhận tất cả detections (occupancy model chỉ có 1 class)
            cx = (x1 + x2) / 2
            cy = y1 + (y2 - y1) * 0.85  # Gần chân quân cờ

            try:
                dst = cv2.perspectiveTransform(
                    np.array([[[float(cx), float(cy)]]], dtype=np.float32), M
                )[0][0]
                c, r = int(round(dst[0])), int(round(dst[1]))
                if 0 <= c < self.num_cols and 0 <= r < self.num_rows:
                    grid[r][c] = True
            except:
                pass

        return grid

    # -------------------------------------------------------------------------
    # INTERNAL: So sánh 2 snapshot T1 vs T2
    # -------------------------------------------------------------------------

    def _compare_snapshots(self, t1_occ, t2_occ, board):
        """So sánh T1 vs T2 occupancy, dùng memory board để xác định quân.
        
        Logic:
          - disappeared: T1 có quân nhưng T2 trống → check board: nếu đỏ → src
          - appeared:    T1 trống nhưng T2 có quân → dst
        
        Args:
            t1_occ: 10x9 bool grid (T1 occupancy)
            t2_occ: 10x9 bool grid (T2 occupancy)
            board:  10x9 memory board (tại thời điểm T1)
        
        Returns:
            (src, dst, piece_name) hoặc (None, None, None)
        """
        disappeared = []  # Ô T1 có quân → T2 trống
        appeared = []     # Ô T1 trống → T2 có quân

        for r in range(self.num_rows):
            for c in range(self.num_cols):
                t1_has = t1_occ[r][c]
                t2_has = t2_occ[r][c]

                if t1_has and not t2_has:
                    # Quân biến mất
                    piece = board[r][c]
                    disappeared.append((c, r, piece))
                elif not t1_has and t2_has:
                    # Quân xuất hiện
                    appeared.append((c, r))

        # Debug log
        print(f"[SNAPSHOT] 🔍 Compare: disappeared={len(disappeared)}, appeared={len(appeared)}")
        if disappeared:
            print(f"  Biến mất: {[(c, r, p) for c, r, p in disappeared]}")
        if appeared:
            print(f"  Xuất hiện: {[(c, r) for c, r in appeared]}")

        # Lọc: chỉ quan tâm quân ĐỎ biến mất (người chơi đỏ di quân)
        red_disappeared = [(c, r, p) for c, r, p in disappeared if p.startswith("r")]
        
        if red_disappeared:
            print(f"  Quân đỏ biến mất: {red_disappeared}")

        # --- Pattern 1: Di chuyển thường (1 đỏ mất, 1 xuất hiện) ---
        if len(red_disappeared) == 1 and len(appeared) == 1:
            src = (red_disappeared[0][0], red_disappeared[0][1])
            dst = (appeared[0][0], appeared[0][1])
            piece = red_disappeared[0][2]
            print(f"[SNAPSHOT] ✅ Pattern 1 (di chuyển): {piece} {src}→{dst}")
            return src, dst, piece

        # --- Pattern 2: Ăn quân (1 đỏ mất, 0 xuất hiện mới) ---
        # Quân đỏ di chuyển đến ô có quân đen → T2 vẫn occupied ở dst
        # → appeared = 0 vì ô đó vẫn có quân (đỏ thay đen)
        if len(red_disappeared) == 1 and len(appeared) == 0:
            src_c, src_r, piece = red_disappeared[0]
            # Tìm ô mà T1 có quân ĐEN nhưng T2 vẫn có quân
            # (quân đỏ đã thế chỗ quân đen)
            # Cách khác: tìm ô biến mất quân đen
            black_disappeared = [(c, r, p) for c, r, p in disappeared if p.startswith("b")]
            if len(black_disappeared) == 1:
                # Quân đen cũng biến mất → nhưng thực ra đỏ đã ăn đen
                # Nhưng camera nên thấy quân đỏ ở vị trí đen cũ... 
                # Trường hợp: cả đỏ src và đen dst đều "biến mất" → YOLO miss
                dst = (black_disappeared[0][0], black_disappeared[0][1])
                print(f"[SNAPSHOT] ✅ Pattern 2a (ăn quân, cả 2 biến mất): {piece} ({src_c},{src_r})→{dst}")
                return (src_c, src_r), dst, piece
            
            # Nếu không có đen biến mất → tìm ô đen mà quân vẫn còn
            # (quân đỏ thay thế quân đen, camera vẫn thấy occupied)
            candidates = []
            for r in range(self.num_rows):
                for c in range(self.num_cols):
                    mem_piece = board[r][c]
                    if mem_piece.startswith("b") and t2_occ[r][c]:
                        # Ô này: memory = đen, T2 vẫn có quân → có thể đỏ đã ăn đen ở đây
                        candidates.append((c, r))
            
            if len(candidates) > 0:
                # Chọn candidate gần src nhất
                best = min(candidates, key=lambda p: abs(p[0]-src_c) + abs(p[1]-src_r))
                print(f"[SNAPSHOT] ✅ Pattern 2b (ăn quân, dst vẫn occupied): {piece} ({src_c},{src_r})→{best}")
                return (src_c, src_r), best, piece

        # --- Pattern 3: Nhiều thay đổi → chọn cặp đỏ gần nhất ---
        if len(red_disappeared) >= 1 and len(appeared) >= 1:
            best_pair = None
            best_dist = 999
            for mc, mr, mp in red_disappeared:
                for nc, nr in appeared:
                    dist = abs(mc - nc) + abs(mr - nr)
                    if dist < best_dist:
                        best_dist = dist
                        best_pair = ((mc, mr, mp), (nc, nr))
            if best_pair and best_dist <= 10:
                src = (best_pair[0][0], best_pair[0][1])
                dst = (best_pair[1][0], best_pair[1][1])
                piece = best_pair[0][2]
                print(f"[SNAPSHOT] ✅ Pattern 3 (multi, dist={best_dist}): {piece} {src}→{dst}")
                return src, dst, piece

        print("[SNAPSHOT] ❌ Không phát hiện được nước đi.")
        return None, None, None
