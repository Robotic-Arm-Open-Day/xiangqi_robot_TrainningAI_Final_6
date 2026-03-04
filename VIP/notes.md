# GHI CHÚ VIP — KIẾN TRÚC & TÀI LIỆU MODULE
# Cập nhật: 2026-03-05
# Tổng hợp từ discussion_notes.txt — không trùng lặp, sắp xếp theo module

================================================================================
## PHẦN A: KIẾN TRÚC TỔNG THỂ (VIP v3)
================================================================================

### A1. LUỒNG GAME

  Khởi động → FEN bộ nhớ = vị trí ban đầu

  [Lượt Người]
    1. Di chuyển quân thật trên bàn
    2. Bấm SPACE
    3. Camera chụp T2 → YOLO detect → so sánh với T1 (FEN bộ nhớ)
    4. Phát hiện nước đi (src→dst) → validate luật cờ
    5. Cập nhật FEN bộ nhớ

  [Lượt AI]
    1. Gửi FEN hiện tại cho Pikafish
    2. Pikafish trả về nước đi tốt nhất (UCI)
    3. Robot thực hiện nước đi (robot_VIP.py)
    4. Cập nhật FEN bộ nhớ → chụp T1 baseline mới
    5. Quay lại lượt Người

  [Rollback — phím Z]
    → Khôi phục toàn bộ state (board, FEN, T1 baseline) về trước SPACE vừa bấm

### A2. BOARD & FEN

  Board lưu dạng list 10x9: board[row][col] = "r_P", "b_K", "."
  FEN string dùng trực tiếp cho Pikafish (gửi qua UCI: "position fen ...")

  MAPPING QUÂN CỜ (ARRAY → FEN):
    r_K→K   b_K→k
    r_A→A   b_A→a
    r_E→B   b_E→b   (Elephant = Bishop)
    r_N→N   b_N→n
    r_R→R   b_R→r
    r_C→C   b_C→c
    r_P→P   b_P→p

### A3. NHẬN DIỆN YOLO (1-CLASS OCCUPANCY MODEL)

  Chỉ detect "có quân cờ" hay "ô trống" (1 class duy nhất).
  Bộ nhớ FEN đã biết quân gì ở đâu → không cần YOLO nói màu/loại.

  KẾT QUẢ TRAINING YOLO26:
    Model:      yolo26m.pt | 80 epochs | imgsz=640
    Precision:  95.5%
    Recall:     99.2%
    mAP50:      95.4%
    mAP50-95:   82.4%
    Weights:    runs/detect/chess_vision/yolo26_occupancy_run/weights/best.pt

### A4. CÁC RỦI RO & GIẢI PHÁP

  [R1] YOLO nhấp nháy (miss 1 quân đang yên)
       → Mức thấp (Recall 99.2%). Pattern filter xử lý.

  [R2] Xếp bàn cờ ban đầu sai
       → Xếp đúng chuẩn. Có thể thêm bước verify đầu game.

  [R3] Perspective calibrate sai → quân map sang ô kế bên
       → Calibrate chính xác (bấm V khi chạy main_VIP.py).

  [R4] Ăn quân (captured piece pattern)
       → Xử lý riêng: T1=có đỏ+có đen, T2=trống+vẫn có quân
       → Dùng Blind Capture Resolution (pixel absdiff) nếu ambiguous.

  [R5] Bấm SPACE trước khi đi xong
       → Không phát hiện thay đổi → bỏ qua, hiển thị thông báo.

### A5. CHECKLIST

  [x] Train YOLO26 (Precision 95.5%, Recall 99.2%)
  [x] Chuyển board sang FEN string (board_array_to_fen / fen_to_board_array)
  [x] Tích hợp Pikafish engine (thay ai.py PVS)
  [x] Phím SPACE để chụp snapshot (bỏ auto-snapshot 1s)
  [x] Xử lý pattern di chuyển thường (1 mất + 1 xuất hiện)
  [x] Xử lý pattern ăn quân (Blind Capture Resolution)
  [x] Chỉnh PICK_Z/PLACE_Z (PICK_Z=190 tránh đập bàn)
  [x] Pikafish config (PIKAFISH_EXE, PIKAFISH_NNUE, PIKAFISH_THINK_MS)
  [x] Rollback (phím Z để hoàn tác nước đi sai)
  [x] robot_VIP.py — Controller DO2 thay Tool DO1 (mất dây đầu cánh tay)
  [ ] Verify bàn cờ lúc bắt đầu game (tùy chọn)

================================================================================
## PHẦN B: TÀI LIỆU CÁC MODULE VIP
================================================================================

### B1. VIP/snapshot_detector.py

Phát hiện nước đi bằng so sánh 2 snapshot camera (T1/T2).
KHÔNG truy cập camera trực tiếp — nhận frame + detections từ CameraMonitor.

PUBLIC API:
  capture_baseline(frame, detections)
    → Lưu T1: occupancy grid (10x9 bool) + raw frame BGR
    → Gọi sau khi AI đi xong, bàn cờ đã ổn định

  detect_move(frame, detections, board) → (src, dst, piece_name)
    → Chụp T2, so sánh với T1
    → Gọi khi người chơi bấm SPACE

  has_baseline() / clear_baseline() / get_baseline_grid()

THUẬT TOÁN _compare_snapshots (4 lớp ưu tiên):

  [LỚP 1] valid_moves == 1
    → Occupancy grid cho thấy đúng 1 cặp src/dst hợp lệ → return ngay

  [LỚP 2] valid_moves > 1 (Ambiguous)
    → Pixel absdiff tiebreaker: ô đích thay đổi pixel nhiều nhất = ô thật
    → Fallback: Manhattan distance nếu frame=None

  [LỚP 3] YOLO miss hoàn toàn (cả đỏ src + đen dst đều biến mất)
    → 1 đỏ mất + 1 đen mất → kết luận ngay (ăn quân)

  [LỚP 4] YOLO miss dst (chỉ thấy đỏ src biến mất)
    → Quét toàn bộ quân đen hợp lệ → pixel absdiff → Blind Capture Resolution

  [THẤT BẠI] → return (None, None, None), yêu cầu bấm SPACE lại

DST CANDIDATES (thiết kế mới — không false positive):
  Loại 1: Ô T1 trống → T2 có quân (di chuyển thường)
  Loại 2: Ô quân đen THỰC SỰ biến mất ở T2 (bị ăn, YOLO miss quân đỏ)
  KHÔNG quét toàn bộ quân đen trên board (gây false capture detection)

PIXEL ABSDIFF (_resolve_capture_ambiguity):
  1. Load perspective.npy → tính inverse matrix (grid → pixel)
  2. Với mỗi candidate (col, row):
     - Map tọa độ ô → bounding box pixel (_get_pixel_box_from_grid)
     - Crop từ baseline_frame (T1) và curr_frame (T2)
     - Chuyển Grayscale → cv2.absdiff → tổng pixel thay đổi (score)
  3. Ô có score cao nhất = ô đích thực sự

LỊCH SỬ THAY ĐỔI:
  v1: Occupancy grid + Manhattan tiebreaker
  v2: Thêm Blind Capture Resolution (pixel absdiff) cho lớp 4
  v3: Thay Manhattan tiebreaker (lớp 2) bằng pixel absdiff
      → Manhattan chỉ còn là safety fallback khi frame=None

LÝ DO BỎ MANHATTAN:
  - Không có trong thiết kế gốc (chỉ có pixel absdiff)
  - Heuristic sai: Xe đi 6 ô thẳng là bình thường, Manhattan sẽ sai
  - Pixel absdiff dựa vào thực tế camera, không cần giả định

---

### B2. VIP/camera_monitor.py

SINGLE CAMERA OWNER — module duy nhất truy cập cv2.VideoCapture.
Background thread đọc camera + YOLO liên tục.

CƠ CHẾ THREAD-SAFE (2 Lock):
  _lock      → bảo vệ _last_frame / _last_detections (shared cache)
  _cam_lock  → bảo vệ cap.read() / cap.grab() (tránh race condition)

PUBLIC API:
  start()                         → Chạy background thread
  stop()                          → Dừng thread, release camera
  reload_perspective()            → Reload perspective.npy sau calibrate
  get_fresh_snapshot()            → [BLOCKING ~200-500ms] Flush 5 frame + YOLO mới
  get_latest_frame_and_detections() → [NON-BLOCKING] Lấy cache mới nhất
  update_display()                → Vẽ overlay + cv2.imshow() trong game loop

get_fresh_snapshot vs get_latest:
  fresh_snapshot:   flush + đọc mới + YOLO blocking → chính xác, chậm hơn
                    Dùng: bấm SPACE, chụp T1 baseline
  get_latest:       lấy cache, trả về ngay, có thể lệch vài trăm ms
                    Dùng: hiển thị, debug

---

### B3. VIP/robot_VIP.py

Điều khiển cánh tay robot FR5 — riêng cho phiên bản VIP.
main_VIP.py import: from robot_VIP import FR5Robot

THAY ĐỔI SO VỚI robot.py GỐC:
  Tool DO1 (đầu cánh tay) → Controller DO2 (bộ điều khiển)
  Nguyên nhân: mất dây nối đến đầu cánh tay
  Config:  self.gripper_do_id = 2
  API:     SetToolDO(id=1) → SetDO(id=2)

CÁC HÀM:
  connect()              → Kết nối robot qua RPC SDK (config.ROBOT_IP)
  board_to_pose()        → (col, row) → [x, y, z, rx, ry, rz] mm
  movej_pose()           → Di chuyển tự do: MoveCart()
  movel_pose()           → Di chuyển thẳng: MoveCart()
  go_to_idle_home()      → Về vị trí IDLE (config.IDLE_X/Y/Z)
  go_to_home_chess()     → Về điểm dạy "HOMECHESS" trên bộ điều khiển
  gripper_ctrl(val)      → SetDO(id=2) ← Controller DO2
  pick_at(col, row)      → Mở kẹp → đến ô → hạ → đóng kẹp → nhấc lên
  place_at(col, row)     → Đến ô → hạ → mở kẹp → nhấc lên
  place_in_capture_bin() → Thả quân bị ăn vào bãi (CAPTURE_BIN_*)
  move_piece(s,d,capture) → HÀM CHÍNH gọi từ main_VIP.py

LUỒNG move_piece():
  1. [Nếu ăn quân] pick_at(dst) → place_in_capture_bin()
  2. pick_at(src)
  3. place_at(dst)
  4. go_to_home_chess()

CONFIG LIÊN QUAN:
  ROBOT_IP, DRY_RUN, MOVE_SPEED
  SAFE_Z=217.227, PICK_Z=190.0, PLACE_Z=176.578
  CAPTURE_BIN_X=-226.123, CAPTURE_BIN_Y=225.024, CAPTURE_BIN_Z=291.68
  ROTATION=[89.658, -0.394, 174.148]
  GRIPPER_CLOSE=1, GRIPPER_OPEN=0

---

### B4. VIP/calibrate_camera.py

Hiệu chỉnh perspective camera bằng cách click 4 góc bàn cờ thật.
Output: perspective.npy (ma trận 3x3 float32, M: pixel → grid).

LUỒNG:
  B1: Warm up camera (đọc 60 frame bỏ đi, ~2 giây)
  B2: Background thread hiển thị live feed lên cửa sổ "CALIBRATE"
  B3: Click 4 góc theo thứ tự:
        [1] Góc Xe Đen Trái  → grid (0,0)
        [2] Góc Xe Đen Phải  → grid (8,0)
        [3] Góc Xe Đỏ Phải   → grid (8,9)
        [4] Góc Xe Đỏ Trái   → grid (0,9)
  B4: Tính M = cv2.getPerspectiveTransform → preview lưới 10×9
  B5: R = reset, S = lưu perspective.npy, Q = thoát không lưu

LƯU Ý:
  - Thứ tự click PHẢI đúng (sai → lưới méo/lật → detect sai ô)
  - Warm up TRƯỚC khi chạy thread (tránh race condition frame đen)
  - DRY_RUN: return None ngay, không hiện cửa sổ

---

### B5. VIP/board_renderer.py

Render giao diện bàn cờ Tướng trên Pygame. Không chứa logic game.

HẰNG SỐ EXPORT:
  SCREEN_WIDTH=800, SCREEN_HEIGHT=600
  SQUARE_SIZE=40
  BTN_SURRENDER_RECT, BTN_NEW_GAME_RECT  ← dùng collidepoint() ở main_VIP

CLASS BoardRenderer:
  draw_ui(game_state)     → nền, lưới, cung tướng, nút bấm, status bar, AI banner
  draw_pieces(board)      → vẽ quân (vòng tròn + viền màu + chữ Hán)
  draw_highlight(...)     → last_move (xanh lá), selected (xanh đậm), invalid (đỏ nhấp nháy)
  draw_game_over(winner)  → thông báo lớn giữa màn hình

PIECE DISPLAY NAMES (chữ Hán):
  r_K→帥  r_A→仕  r_E→相  r_R→俥  r_N→傌  r_C→炮  r_P→兵
  b_K→將  b_A→士  b_E→象  b_R→車  b_N→馬  b_C→砲  b_P→卒

---

### B6. VIP/perspective.npy

File ma trận hiệu chỉnh camera (3×3 float32).
- Tạo bởi: calibrate_camera.py (bấm V → click 4 góc → bấm S)
- Ánh xạ: pixel (px, py) → ô cờ (col, row)
- Dùng bởi: camera_monitor.py, snapshot_detector.py, robot_VIP.py
- Nếu mất hoặc di chuyển camera → phải calibrate lại
- Nếu không có file → robot báo CRITICAL ERROR, không thể di chuyển

================================================================================
## PHẦN C: PIKAFISH ENGINE
================================================================================

### C1. CẤU HÌNH (config.py)

  import os as _os
  _PIKAFISH_DIR = <project_root>/pikafish/
  PIKAFISH_EXE      = pikafish/pikafish-avx2.exe
  PIKAFISH_NNUE     = pikafish/pikafish.nnue
  PIKAFISH_THINK_MS = 3000   # ms mỗi nước

  File exe + nnue KHÔNG push lên git (.gitignore).
  Tải tại: https://github.com/official-pikafish/Pikafish/releases
  Test:    py test_pikafish.py

### C2. TÍCH HỢP TRONG main_VIP.py

  from pikafish_engine import PikafishEngine
  engine = PikafishEngine(config.PIKAFISH_EXE)
  engine.start(nnue_path=config.PIKAFISH_NNUE)

  AI worker thread:
    ai_result = engine.pick_best_move(board, "b", movetime_ms=config.PIKAFISH_THINK_MS)

  Pikafish là bắt buộc — không còn fallback ai.py (PVS đã bị bỏ).

================================================================================
## PHẦN D: PHÍM TẮT TRONG main_VIP.py
================================================================================

  SPACE  → Chụp T2 snapshot, detect nước đi người chơi
  Z      → Rollback về trước SPACE vừa bấm (undo 1 nước)
  V      → Calibrate lại camera (click 4 góc bàn cờ)
  Q      → Thoát cửa sổ camera

================================================================================
