# GHI CHÚ VIP — KIẾN TRÚC & TÀI LIỆU MODULE
# Cập nhật: 2026-03-05 (session chiều — thêm RUN_VIP.bat)
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
    1. Gửi FEN hiện tại cho Pikafish (qua AIController)
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
    Precision:  95.5%  |  Recall: 99.2%  |  mAP50: 95.4%
    Weights:    runs/detect/chess_vision/yolo26_occupancy_run/weights/best.pt

### A4. CÁC RỦI RO & GIẢI PHÁP

  [R1] YOLO nhấp nháy → Pattern filter xử lý (Recall 99.2%, ít xảy ra)
  [R2] Xếp bàn cờ ban đầu sai → Xếp đúng chuẩn
  [R3] Perspective calibrate sai → Bấm V để calibrate lại
  [R4] Ăn quân (ambiguous) → Blind Capture Resolution (pixel absdiff)
  [R5] Bấm SPACE trước khi đi xong → Bỏ qua, hiển thị thông báo
  [R6] Khi ăn quân, YOLO detect quân đỏ tại ô đích → occupancy không đổi
       → Đã fix bằng Loại 3 dst_candidates_capture_stable (xem B6)
  [R7] Lỗi MoveCart 101 khi go_to_home_chess() làm robot.connected=False sai
       → Đã fix: tách connect() và go_to_home_chess() thành 2 try riêng

### A5. PHÍM TẮT

  SPACE  → Chụp T2 snapshot, detect nước đi người chơi
  Z      → Rollback về trước SPACE vừa bấm (undo 1 nước)
  V      → Calibrate lại camera (click 4 góc bàn cờ)
  Q      → Thoát cửa sổ camera

### A6. CHECKLIST

  [x] Train YOLO26 (Precision 95.5%, Recall 99.2%)
  [x] Chuyển board sang FEN string (fen_utils.py)
  [x] Tích hợp Pikafish engine (thay ai.py PVS, qua ai_controller.py)
  [x] Phím SPACE để chụp snapshot
  [x] Xử lý pattern di chuyển thường + ăn quân (Blind Capture Resolution)
  [x] Chỉnh PICK_Z/PLACE_Z (PICK_Z=180, PLACE_Z=190 — cập nhật 2026-03-05)
  [x] Pikafish config (PIKAFISH_EXE, PIKAFISH_NNUE, PIKAFISH_THINK_MS)
  [x] Tải Pikafish 2026-01-02 → pikafish/pikafish-avx2.exe + pikafish.nnue
  [x] Rollback (phím Z)
  [x] robot_VIP.py — Controller DO2 thay Tool DO1
  [x] Tách fen_utils.py và ai_controller.py khỏi main_VIP.py
  [x] Fix robot.connected bị set False sai khi go_to_home_chess lỗi (2026-03-05)
  [x] Fix snapshot_detector: detect ăn quân khi YOLO thấy quân đỏ tại ô đích (2026-03-05)
  [x] Tạo RUN_VIP.bat — double-click để chạy, không cần cmd (2026-03-05)
  [ ] Verify bàn cờ lúc bắt đầu game (tùy chọn)

================================================================================
## PHẦN B: TÀI LIỆU CÁC MODULE VIP (theo thứ tự import trong main_VIP.py)
================================================================================

### B1. VIP/fen_utils.py  ← import đầu tiên

Module thuần (pure functions), không có side effect, dễ test độc lập.

EXPORT:
  INITIAL_FEN             → FEN vị trí ban đầu chuẩn
  board_array_to_fen(board, color='r', move_number=1) → str
  fen_to_board_array(fen) → (board, color)

MAPPING:
  r_K↔K  r_A↔A  r_E↔B  r_N↔N  r_R↔R  r_C↔C  r_P↔P
  b_K↔k  b_A↔a  b_E↔b  b_N↔n  b_R↔r  b_C↔c  b_P↔p

---

### B2. VIP/ai_controller.py  ← import sau fen_utils

Wrapper cho Pikafish engine, tách logic AI khỏi main_VIP.py.

CLASS AIController:
  __init__(engine, config)
    → Nhận PikafishEngine instance và config module

  pick_move(board_snapshot, color="b") → (src, dst) | None
    → Blocking — phải gọi trong thread riêng
    → Gọi engine.pick_best_move(board, color, movetime_ms=PIKAFISH_THINK_MS)
    → Tự xử lý exception, return None nếu engine=None hoặc lỗi

DÙNG TRONG main_VIP.py:
  ai_ctrl = AIController(engine, config)
  # Trong _ai_worker() thread:
  ai_result = ai_ctrl.pick_move(board_snapshot, color="b")

---

### B3. VIP/robot_VIP.py  ← import sau ai_controller

File điều khiển cánh tay robot FR5 — riêng cho phiên bản VIP.
from robot_VIP import FR5Robot

THAY ĐỔI SO VỚI robot.py GỐC:
  Tool DO1 (đầu cánh tay) → Controller DO2 (bộ điều khiển)
  Nguyên nhân: mất dây nối đến đầu cánh tay
  self.gripper_do_id = 2
  SetToolDO(id=1) → SetDO(id=2)

📍 HƯỚNG DẪN TÌM PORT TRÊN ĐẦU CÁNH TAY (Cáp M12 8-pin):
  Cổng Tool Flange của Fairino FR3 mặc định chỉ hỗ trợ DO0 và DO1 (Số 0 và Số 1). Việc test cũ dùng `ID=2` có thể do nhầm lẫn hoặc firmware riêng.
  **Để tìm đúng chân kẹp trên cáp M12 8-pin, BẮT BUỘC TEST BẰNG FILE `test_tool_do2.py`:**
  1. Vào file `test_tool_do2.py`, sửa `TOOL_DO_ID = 0` rồi chạy thử. Kẹp giật/tắt => Chân M12 đó là **DO0**.
  2. Nếu không chạy, đổi `TOOL_DO_ID = 1` rồi chạy lại. Nếu OK => Chân đó là **DO1**.
  3. Nếu bước 2 vẫn thất bại, đổi `TOOL_DO_ID = 2` (File cũ) rồi chạy lại.

  **Sau khi test ra con số hoạt động (Giả sử là ID=1):**
  Vào file `robot_VIP.py` sửa lại đúng 2 chỗ:
  1. Khai báo ban đầu (Dòng 37): `self.gripper_do_id = 1`
  2. Hàm `gripper_ctrl` (Dòng 201): `err = self.robot.SetToolDO(id=self.gripper_do_id, status=val, block=1)`

CÁC HÀM:
  connect()              → Kết nối robot qua RPC SDK
  board_to_pose()        → (col, row) → [x, y, z, rx, ry, rz] mm
  movej_pose()           → Di chuyển tự do: MoveCart()
  movel_pose()           → Di chuyển thẳng: MoveCart()
  go_to_idle_home()      → Về IDLE (config.IDLE_X/Y/Z)
  go_to_home_chess()     → Về điểm dạy "HOMECHESS"
  gripper_ctrl(val)      → SetDO(id=2) — Controller DO2
  pick_at(col, row)      → Mở kẹp → đến ô → hạ → đóng kẹp → nhấc lên
  place_at(col, row)     → Đến ô → hạ → mở kẹp → nhấc lên
  place_in_capture_bin() → Thả quân bị ăn vào bãi
  move_piece(s,d,capture) → HÀM CHÍNH gọi từ main_VIP.py

CONFIG: ROBOT_IP, DRY_RUN, SAFE_Z=217.227, PICK_Z=180.0, PLACE_Z=190.0  ← cập nhật 2026-03-05
        CAPTURE_BIN_X=-226.123, CAPTURE_BIN_Y=225.024, CAPTURE_BIN_Z=291.68

FIX (2026-03-05): Tách robot.connect() và go_to_home_chess() thành 2 khối
  try riêng trong main_VIP.py. Trước đây lỗi MoveCart 101 khi về HOMECHESS
  (do điểm chưa dạy) lan sang làm robot.connected=False → robot không chạy.
  Nay: lỗi go_to_home_chess chỉ in cảnh báo, KHÔNG ảnh hưởng connected.

⚠️ GHI CHÚ QUAN TRỌNG VỀ LỖI SINGULARITY KHI ĐI CHÉO BÀN CỜ (Góc R2):
  Hiện tại `movej_pose()` đang dùng hàm SDK `MoveCart` (di chuyển theo đường thẳng). Khi vươn tới các góc xa (như R2), tay máy dễ bị duỗi thẳng băng gây kẹt góc (Singularity) hoặc chạm không không gian làm việc, dẫn đến báo lỗi từ chối di chuyển.
  → Nếu trong quá trình test lại gặp lỗi này, **hãy mở `robot_VIP.py` và sửa hàm `movej_pose` sang bản chất gốc của `MoveJ`** (tay máy quặp tự do để né giới hạn trần/tường) như sau:
  ```python
  # Trong hàm movej_pose(self, pose, speed), thay lệnh err = MoveCart bằng:
  err = self.robot.MoveJ(
      joint_pos=[0]*6, desc_pos=pose, tool=self.tool_num, user=self.user_num,
      vel=vel, acc=0.0, ovl=100.0, exaxis_pos=[0]*4, blendT=-1.0, offset_flag=0, offset_pos=[0]*6
  )
  ```
  (Lưu ý: riêng hàm `movel_pose` khi dập kẹp xuống vuông góc bàn cờ thì BUỘC PHẢI GIỮ LÀ `MoveCart`).

---

### B4. VIP/calibrate_camera.py  ← chạy khi bấm V

Hiệu chỉnh perspective camera, click 4 góc bàn cờ thật.
Output: perspective.npy (ma trận 3x3 float32, M: pixel → grid).

LUỒNG:
  Warm up camera (60 frame) → Live feed → Click 4 góc theo thứ tự:
    [1] Góc Xe Đen Trái (0,0) → [2] Xe Đen Phải (8,0)
    [3] Góc Xe Đỏ Phải (8,9)  → [4] Xe Đỏ Trái (0,9)
  → Tính M → Preview lưới → R=reset, S=lưu, Q=thoát

LƯU Ý: Thứ tự click PHẢI đúng, warm up TRƯỚC thread. DRY_RUN → return None.

---

### B5. VIP/camera_monitor.py  ← start() sau calibrate

SINGLE CAMERA OWNER — background thread đọc camera + YOLO liên tục.

CƠ CHẾ (2 Lock):
  _lock     → bảo vệ cache (_last_frame, _last_detections)
  _cam_lock → bảo vệ cap.read() / cap.grab()

PUBLIC API:
  start() / stop() / reload_perspective()
  get_fresh_snapshot()               → [BLOCKING ~200-500ms] chính xác nhất
  get_latest_frame_and_detections()  → [NON-BLOCKING] lấy cache
  update_display()                   → vẽ overlay + imshow() trong game loop

DÙNG KHI NÀO:
  get_fresh_snapshot:   bấm SPACE, chụp T1 baseline
  get_latest:           hiển thị, debug

FIX (2026-03-05): Giải quyết triệt để lỗi Snapshot Queuing (Trễ hình/Lag Delay)
  Nguyên nhân: OpenCV tự tạo Buffer hàng đợi (queue), nhưng suy luận YOLO mất ~200ms khiến ảnh bị dồn ứ, `cap.read()` luôn lấy ra ảnh cũ trong quá khứ dẫn đến hình ảnh hiển thị trễ hơn thực tế nhiều giây.
  Giải pháp: Dùng `cap.grab()` 5 lần liên tục trước mỗi `cap.read()` để xả trôi hết đống buffer cũ, ép OpenCV lấy đúng tấm ảnh tươi mới nhất của hiện tại (Zero Delay Real-Time). Đồng thời gỡ bỏ `time.sleep` vì bản thân YOLO chạy đủ chậm để nhường CPU rồi.

---

### B6. VIP/snapshot_detector.py  ← detect_move() khi bấm SPACE

Phát hiện nước đi bằng so sánh T1/T2 occupancy grid.
KHÔNG truy cập camera trực tiếp.

PUBLIC API:
  capture_baseline(frame, detections)        → Lưu T1 (sau khi AI đi xong)
  detect_move(frame, detections, board)      → (src, dst, piece) khi bấm SPACE
  has_baseline() / clear_baseline()

THUẬT TOÁN (4 lớp ưu tiên):
  [1] valid_moves == 1 → return ngay (chắc nhất)
  [2] valid_moves > 1  → pixel absdiff tiebreaker (fallback: Manhattan)
  [3] Cả đỏ src + đen dst biến mất → ăn quân trực tiếp
  [4] Chỉ đỏ src biến mất → Blind Capture Resolution (pixel absdiff quét quân đen)

DST CANDIDATES — 3 loại (cập nhật 2026-03-05):
  Loại 1: Ô T1 trống → T2 có quân (di chuyển thường)
  Loại 2: Ô quân đen THỰC SỰ biến mất (bị ăn, YOLO miss quân đỏ)
  Loại 3: Ô quân đen trong memory board, T1=True & T2=True (stable)
           → Trường hợp ăn quân PHỔ BIẾN NHẤT: YOLO detect quân đỏ đang
             đứng tại ô đích sau khi ăn → occupancy không đổi → bị bỏ sót.
             Fix: chủ động add tất cả ô đen "stable" vào candidate,
             validate rule cờ sẽ loại những ô không hợp lệ.

PIXEL ABSDIFF (_resolve_capture_ambiguity):
  Load inv_M → crop từng candidate (T1 vs T2) → Grayscale → absdiff
  → Ô score cao nhất = ô đích thực sự

---

### B7. VIP/game_state.py  ← Quản lý Dữ liệu

Chứa class `GameState`. Quản lý toàn bộ vòng đời data, xóa bỏ biến Global.
* Lưu giữ: `board`, `turn`, `current_fen`, `move_history`, `game_over`
* Method chính: `update_fen_from_board()`, `reset_game()`, `handle_rollback()`, `process_human_move()`, `handle_game_over()`.

---

### B8. VIP/hardware_manager.py  ← Bật AI, Camera, Robot

Chứa class `HardwareManager`. Điểm chạm kết nối thiết bị vật lý và trí tuệ nhân tạo.
* Gói gọn: `FR5Robot`, `PikafishEngine` (qua `AIController`), `CameraMonitor`, `YoloSnapshotDetector`.
* Method chính: `initialize_all()` (kết nối r, m, c theo thứ tự an toàn), `cleanup()`, `capture_baseline_if_needed()`.

---

### B9. VIP/input_handler.py  ← Lắng nghe Phím/Chuột

Chứa class `InputHandler`. Điều hướng thao tác người dùng Pygame vào `GameState` và `HardwareManager`.
* `handle_mouse_down()`: Kiểm tra vùng click Surrender, New Game, Kéo thả chuột (Override).
* `handle_keyboard(key)`: Phím SPACE (gọi YOLO detect_move), Phím Z (gọi Rollback).

---

### B10. VIP/board_renderer.py  ← Vẽ màn hình mỗi frame

Render giao diện bàn cờ Pygame. Không chứa logic game, chỉ nhận state từ `GameState`.

HẰNG SỐ: SCREEN_WIDTH=800, SCREEN_HEIGHT=600, SQUARE_SIZE=40
          BTN_SURRENDER_RECT, BTN_NEW_GAME_RECT

METHODS:
  draw_ui(game_state_dict)     → nền, lưới, cung tướng, nút, status bar, AI banner
  draw_pieces(board)      → vòng tròn + viền + chữ Hán
  draw_highlight(...)     → last_move (xanh lá), selected (xanh), invalid (đỏ nhấp)
  draw_game_over(winner)  → thông báo lớn giữa màn hình

---

### B11. VIP/main_VIP.py  ← Điểm vào chính

Vòng lặp game chính (Game Loop). Rất gọn nhẹ nhờ kiến trúc SRP.

KHỞI TẠO THEO THỨ TỰ:
  _kill_zombie_processes() → Pygame 
  → hw = HardwareManager(...).initialize_all()
  → state = GameState(...)
  → input_mgr = InputHandler(state, hw)

CHỨC NĂNG LOOP (30 FPS):
  1. Gọi `renderer` vẽ frame.
  2. Truyền event Pygame vào `input_mgr`.
  3. Cập nhật Camera View.
  4. Nếu lượt AI (`turn == b`), nháy Thread chờ Engine đánh, đánh xong gọi `robot.move_piece()`.

DRY_RUN mode (config.DRY_RUN=True):
  → Trình quản lý phần cứng tự động Mock Robot/Camera → Vào thẳng chế độ chuột (Mouse Drag).

---

### B9. VIP/RUN_VIP.bat  ← khởi động nhanh (tạo 2026-03-05)

File batch script để chạy hệ thống bằng double-click, không cần mở cmd thủ công.

TÍNH NĂNG:
  - Tự cd vào đúng thư mục VIP/ (dùng %~dp0)
  - Kiểm tra venv/Scripts/python.exe trước khi chạy
  - Kiểm tra main_VIP.py tồn tại
  - Cảnh báo nếu thiếu pikafish-avx2.exe (cho tiếp tục)
  - Giữ cửa sổ mở sau khi thoát (pause) để xem log lỗi

CÁCH DÙNG:
  Double-click RUN_VIP.bat → hệ thống khởi động
  Có thể tạo shortcut ra Desktop để tiện hơn.

LƯU Ý: KHÔNG build .exe vì PyTorch/CUDA + subprocess pikafish không tương thích
  tốt với PyInstaller, và config.py sẽ không sửa được sau khi build.

---

### B10. VIP/perspective.npy  ← file data

Ma trận 3x3 float32: pixel (px,py) → ô cờ (col,row).
Tạo bởi calibrate_camera.py (bấm V → click 4 góc → S).
Dùng bởi: camera_monitor, snapshot_detector, robot_VIP.
Mất file → phải calibrate lại, robot báo CRITICAL ERROR.

================================================================================
## PHẦN C: PIKAFISH ENGINE
================================================================================

  Config (config.py):
    PIKAFISH_EXE      = pikafish/pikafish-avx2.exe
    PIKAFISH_NNUE     = pikafish/pikafish.nnue
    PIKAFISH_THINK_MS = 3000   (ms mỗi nước)

  Phiên bản đang dùng: Pikafish 2026-01-02 (tải 2026-03-05)
  Source: https://github.com/official-pikafish/Pikafish/releases/tag/Pikafish-2026-01-02
  File: Pikafish.2026-01-02.7z → giải nén → copy Windows/pikafish-avx2.exe vào pikafish/

  File exe + nnue KHÔNG push git (.gitignore).
  Tải: https://github.com/official-pikafish/Pikafish/releases
  Test: py test_pikafish.py

================================================================================
