# =============================================================================
# === FILE: snapshot_detector.py (T1/T2 Snapshot Move Detection System) ===
# === So sánh 2 snapshot camera (trước/sau khi đi) để phát hiện nước đi ===
# =============================================================================
import cv2
import numpy as np
import os
import time


class SnapshotDetector:
    """
    Hệ thống phát hiện nước đi bằng so sánh 2 snapshot (T1/T2).
    
    Flow:
        1. capture_baseline()  → Chụp T1 (bàn cờ trước khi người đi)
        2. Người chơi di chuyển quân trên bàn thật
        3. detect_move()       → Chụp T2 + so sánh T1 vs T2 → trả về nước đi
        4. AI đi quân
        5. capture_baseline()  → Chụp T1 mới (sau khi AI đi)
        6. Lặp lại từ bước 2
    """

    def __init__(self, cap, model, perspective_path, class_id_map, num_cols=9, num_rows=10):
        """
        Args:
            cap:              cv2.VideoCapture đã mở
            model:            YOLO model đã load
            perspective_path: đường dẫn file perspective.npy
            class_id_map:     dict {class_id: "r_P", "b_N", ...}
            num_cols:         số cột bàn cờ (9)
            num_rows:         số hàng bàn cờ (10)
        """
        self.cap = cap
        self.model = model
        self.perspective_path = str(perspective_path)
        self.class_id_map = class_id_map
        self.num_cols = num_cols
        self.num_rows = num_rows

        # T1 baseline snapshot (10x9 grid with piece names)
        self._baseline = None
        self._baseline_time = None

    # -------------------------------------------------------------------------
    # PUBLIC API
    # -------------------------------------------------------------------------

    def capture_baseline(self):
        """Chụp T1 — snapshot baseline trước khi người chơi đi.
        
        Returns:
            True nếu chụp thành công, False nếu thất bại.
        """
        grid = self._take_snapshot()
        if grid is None:
            print("[SNAPSHOT] ❌ Không chụp được T1 baseline!")
            return False

        self._baseline = grid
        self._baseline_time = time.time()

        # Debug: đếm quân detect được
        n_pieces = sum(1 for r in grid for p in r if p != ".")
        n_red = sum(1 for r in grid for p in r if p.startswith("r"))
        n_black = sum(1 for r in grid for p in r if p.startswith("b"))
        print(f"[SNAPSHOT] 📸 T1 Baseline captured: {n_pieces} quân (Đỏ={n_red}, Đen={n_black})")
        return True

    def detect_move(self):
        """Chụp T2 và so sánh với T1 để phát hiện nước đi của quân ĐỎ.
        
        Returns:
            (src, dst, piece_name) nếu phát hiện nước đi hợp lệ
            (None, None, None) nếu không phát hiện được
        """
        if self._baseline is None:
            print("[SNAPSHOT] ⚠️ Chưa có T1 baseline! Gọi capture_baseline() trước.")
            return None, None, None

        # Chụp T2
        current = self._take_snapshot()
        if current is None:
            print("[SNAPSHOT] ❌ Không chụp được T2!")
            return None, None, None

        # Debug: đếm quân T2
        n_pieces = sum(1 for r in current for p in r if p != ".")
        print(f"[SNAPSHOT] 📸 T2 captured: {n_pieces} quân")

        # So sánh T1 vs T2
        return self._compare_snapshots(self._baseline, current)

    def has_baseline(self):
        """Kiểm tra đã có T1 baseline chưa."""
        return self._baseline is not None

    def clear_baseline(self):
        """Xóa T1 baseline (dùng khi reset game)."""
        self._baseline = None
        self._baseline_time = None
        print("[SNAPSHOT] 🗑️ Baseline cleared.")

    def get_baseline_grid(self):
        """Trả về grid T1 hiện tại (hoặc None)."""
        return self._baseline

    # -------------------------------------------------------------------------
    # INTERNAL: Chụp 1 snapshot từ camera
    # -------------------------------------------------------------------------

    def _take_snapshot(self):
        """Chụp 1 ảnh từ camera, chạy YOLO, trả về 10x9 grid piece names."""
        if self.cap is None or self.model is None:
            return None

        # Xả buffer camera để lấy frame mới nhất
        for _ in range(5):
            self.cap.grab()

        ret, frame = self.cap.read()
        if not ret:
            print("[SNAPSHOT] ❌ Camera read failed!")
            return None

        # Chạy YOLO
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = self.model.predict(frame_rgb, conf=0.35, iou=0.35, imgsz=1280, verbose=False)

        # Thu thập detections
        detections = []
        for box in results[0].boxes:
            cls = int(box.cls[0])
            if cls in self.class_id_map:
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                detections.append((cls, (x1, y1, x2, y2)))

        # Hiển thị detection lên camera window
        for (cls, (x1, y1, x2, y2)) in detections:
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
        cv2.imshow("Camera Monitor", frame)
        cv2.waitKey(1)

        # Load perspective matrix
        if not os.path.exists(self.perspective_path):
            print("[SNAPSHOT] ⚠️ perspective.npy không tồn tại!")
            return None
        M_cam = np.load(self.perspective_path)

        # Convert detections → grid
        return self._detections_to_grid(detections, M_cam)

    # -------------------------------------------------------------------------
    # INTERNAL: Convert YOLO detections → 10x9 grid
    # -------------------------------------------------------------------------

    def _detections_to_grid(self, detections, M):
        """Convert YOLO detections → 10x9 grid với tên quân."""
        grid = [["." for _ in range(self.num_cols)] for _ in range(self.num_rows)]
        if M is None:
            return grid

        for cls_id, (x1, y1, x2, y2) in detections:
            name = self.class_id_map.get(cls_id)
            if not name:
                continue

            cx = (x1 + x2) / 2
            cy = y1 + (y2 - y1) * 0.85  # Gần chân quân cờ

            try:
                dst = cv2.perspectiveTransform(
                    np.array([[[float(cx), float(cy)]]], dtype=np.float32), M
                )[0][0]
                c, r = int(round(dst[0])), int(round(dst[1]))
                if 0 <= c < self.num_cols and 0 <= r < self.num_rows:
                    grid[r][c] = name
            except:
                pass

        return grid

    # -------------------------------------------------------------------------
    # INTERNAL: So sánh 2 snapshot T1 vs T2
    # -------------------------------------------------------------------------

    def _compare_snapshots(self, t1_grid, t2_grid):
        """So sánh T1 (trước khi đi) vs T2 (sau khi đi).
        
        Tìm sự thay đổi của quân ĐỎ:
          - missing_reds: ô T1 có đỏ nhưng T2 không có đỏ → src
          - new_reds:     ô T1 không có đỏ nhưng T2 có đỏ → dst
        
        Returns:
            (src, dst, piece_name) hoặc (None, None, None)
        """
        missing_reds = []  # T1 có đỏ, T2 không có đỏ
        new_reds = []      # T1 không có đỏ, T2 có đỏ

        for r in range(self.num_rows):
            for c in range(self.num_cols):
                t1_piece = t1_grid[r][c]
                t2_piece = t2_grid[r][c]

                t1_is_red = t1_piece.startswith("r")
                t2_is_red = t2_piece.startswith("r") if t2_piece != "." else False

                if t1_is_red and not t2_is_red:
                    # Quân đỏ biến mất → src
                    missing_reds.append((c, r, t1_piece))
                elif not t1_is_red and t2_is_red:
                    # Quân đỏ xuất hiện → dst
                    new_reds.append((c, r, t2_piece))

        # Debug log
        print(f"[SNAPSHOT] 🔍 Compare: missing_reds={len(missing_reds)}, new_reds={len(new_reds)}")
        if missing_reds:
            print(f"  T1→T2 mất đỏ: {[(c, r, p) for c, r, p in missing_reds]}")
        if new_reds:
            print(f"  T1→T2 có đỏ mới: {[(c, r, p) for c, r, p in new_reds]}")

        # --- Pattern 1: Di chuyển thường (1 mất, 1 xuất hiện) ---
        if len(missing_reds) == 1 and len(new_reds) == 1:
            src = (missing_reds[0][0], missing_reds[0][1])
            dst = (new_reds[0][0], new_reds[0][1])
            piece = missing_reds[0][2]
            print(f"[SNAPSHOT] ✅ Pattern 1 (di chuyển): {piece} {src}→{dst}")
            return src, dst, piece

        # --- Pattern 2: Ăn quân đen (1 mất, 0 xuất hiện) ---
        # Quân đỏ thay thế vị trí quân đen → camera có thể nhận nhầm đỏ thành đen
        if len(missing_reds) == 1 and len(new_reds) == 0:
            src_c, src_r, piece = missing_reds[0]
            # Tìm ô MỚI: T1 có đen nhưng T2 thấy quân khác (có thể đỏ bị nhận nhầm)
            candidates = []
            for r in range(self.num_rows):
                for c in range(self.num_cols):
                    t1_p = t1_grid[r][c]
                    t2_p = t2_grid[r][c]
                    # T1 có quân đen, T2 có quân nhưng KHÔNG phải quân đen đó
                    if t1_p.startswith("b") and t2_p != "." and t1_p != t2_p:
                        candidates.append((c, r))
            if len(candidates) == 1:
                dst = candidates[0]
                print(f"[SNAPSHOT] ✅ Pattern 2 (ăn quân): {piece} ({src_c},{src_r})→{dst}")
                return (src_c, src_r), dst, piece

        # --- Pattern 3: Nhiều quân bị nhận sai → chọn cặp gần nhất ---
        if len(missing_reds) >= 1 and len(new_reds) >= 1:
            best_pair = None
            best_dist = 999
            for mc, mr, mp in missing_reds:
                for nc, nr, np_ in new_reds:
                    dist = abs(mc - nc) + abs(mr - nr)
                    if dist < best_dist:
                        best_dist = dist
                        best_pair = ((mc, mr, mp), (nc, nr, np_))
            if best_pair and best_dist <= 10:
                src = (best_pair[0][0], best_pair[0][1])
                dst = (best_pair[1][0], best_pair[1][1])
                piece = best_pair[0][2]
                print(f"[SNAPSHOT] ✅ Pattern 3 (multi, dist={best_dist}): {piece} {src}→{dst}")
                return src, dst, piece

        print("[SNAPSHOT] ❌ Không phát hiện được nước đi.")
        return None, None, None
