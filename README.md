# GHI CHÚ DỰ ÁN — KIẾN TRÚC MODULAR
# Cập nhật: 2026-03-06 (Sửa Tool DO0, fix MoveJ singularity, Auto T1 baseline)
# Tổng hợp từ discussion_notes.txt — không trùng lặp, sắp xếp theo module

================================================================================
## PHẦN 0: HƯỚNG DẪN CÀI ĐẶT DÀNH CHO NGƯỜI MỚI (STANDALONE REPO)
================================================================================
Repository này có thể hoạt động ĐỘC LẬP không cần phụ thuộc vào mã nguồn gốc. Để chạy được hệ thống, bạn cần làm đúng 3 bước:

[BƯỚC 1] CÀI ĐẶT THƯ VIỆN PYTHON
```bash
pip install pygame numpy opencv-python ultralytics
```

[BƯỚC 2] TẢI MÔ HÌNH NHẬN DIỆN BÀN CỜ (YOLO)
File trọng số AI đã được đính kèm sẵn trong mã nguồn tại: `models/best.pt`. (Nếu bạn là người phát triển, hãy đảm bảo file này đã được commit lên Git).

[BƯỚC 3] TẢI CHESS ENGINE (PIKAFISH) - RẤT QUAN TRỌNG
Vì file này rất nặng nên KHÔNG ĐƯỢC PUSH lên Git. Bạn bắt buộc phải tự tải:
1. Tải **Pikafish 2026-01-02 AVX2** (cho Windows/Linux) từ: https://github.com/official-pikafish/Pikafish/releases
   -> Giải nén file 7z vừa tải thẳng vào thư mục: `pikafish/` (giữ nguyên thư mục con `Windows/`)
2. Tải **Neural Network (.nnue)** trực tiếp từ API: https://pikafish.org/api/nnue/download/latest
   -> Bỏ riêng file pikafish.nnue tải được vào thư mục `pikafish/`.
Kết quả cấu trúc chuẩn sẽ như sau:
   Dự-án-gốc/
   ├── pikafish/
   │   ├── pikafish.nnue
   │   └── Windows/
   │       └── pikafish-avx2.exe

Đã xong! Giờ bạn có thể chạy `main.py` hoặc double click `RUN.bat` để bắt đầu.

================================================================================
## PHẦN 1: CẤU TRÚC THƯ MỤC CỐT LÕI
================================================================================

Dự án được tổ chức theo kiến trúc Modular, chia nhỏ logic theo từng domain con:

```text
Dự-án-gốc/
├── main.py                   # Điểm vào chính của chương trình (Game Loop)
├── config.py                 # File cấu hình trung tâm (Camera, Robot, Path, Constants)
├── RUN.bat                   # Script khởi động nhanh toàn bộ hệ thống
├── notes.md                  # Tài liệu hướng dẫn & kiến trúc hệ thống
├── perspective.npy           # Dữ liệu ma trận góc nhìn Camera (Calibrate data)
│
├── models/                   # Chứa trọng số mô hình AI nhận dạng hình ảnh
│   └── best.pt               # File weights YOLO26 đã train (nhận diện 1 class)
│
├── pikafish/                 # Thư mục bắt buộc chứa engine AI Cờ Tướng 
│   ├── pikafish.nnue         # Mạng Neural Network của Pikafish
│   └── Windows/              # Thư mục con chứa file thực thi exe của Pikafish
│
├── src/                      # MÃ NGUỒN CHÍNH (CORE SOURCE CODE)
│   ├── ai/                   # Module Trí Tuệ Nhân Tạo
│   │   ├── pikafish_engine.py# Bộ giao tiếp biên dịch lệnh UCI trực tiếp với file Exe (Local)
│   │   ├── cloud_engine.py   # Kết nối REST API lên tuongkydaisu.com (Cloud)
│   │   └── ai_controller.py  # Wrapper quản lý tầng cao giao tiếp với Game (Worker Thread)
│   │
│   ├── core/                 # Module Xử lý Thể thức & Logic Game
│   │   ├── xiangqi.py        # Trái tim của Luật cờ tướng (Move validation, Check/Checkmate)
│   │   ├── fen_utils.py      # Chuyển đổi qua lại giữa mảng Board Array và chuỗi FEN chuẩn
│   │   └── game_state.py     # Quản lý vòng đời trạng thái Game (State Management)
│   │
│   ├── hardware/             # Module phần cứng & thiết bị ngoại vi
│   │   ├── hardware_manager.py# Khởi tạo tổng hợp An toàn cho Robot, AI, Camera
│   │   ├── robot_VIP.py      # Bộ thư viện điều khiển các khớp tay máy Fairino FR5
│   │   └── robot_sdk_core.*  # Các file mã C/Python biên dịch cấp thấp của hãng Fairino
│   │
│   ├── ui/                   # Module Giao diện người dùng đồ họa
│   │   ├── board_renderer.py # Vẽ và cập nhật Game Board lên màn hình qua Pygame
│   │   └── input_handler.py  # Lắng nghe & Xử lý sự kiện Phím/Chuột từ người dùng
│   │
│   └── vision/               # Module Thị giác máy tính (Computer Vision)
│       ├── calibrate_camera.py  # Module căn chỉnh góc tọa độ bàn cờ
│       ├── camera_monitor.py    # Chạy luồng nền xả Queue OpenCV để lấy frame thời gian thực
│       └── snapshot_detector.py # So sánh điểm khác biệt 2 snapshot để xuất ra nước cờ
│
└── tests/                    # Thư mục Test kỹ thuật
    └── test_*.py             # Kịch bản test độc lập từng thành phần (Mocking)
```

================================================================================
## PHẦN 2: KIẾN TRÚC TỔNG THỂ & LUỒNG GAME
================================================================================

### 2.1. LUỒNG GAME

  Khởi động → FEN bộ nhớ = vị trí ban đầu

  [Lượt Người]
    1. Di chuyển quân thật trên bàn
    2. Bấm SPACE
    3. Camera chụp T2 → YOLO detect → so sánh với T1 (FEN bộ nhớ)
    4. Phát hiện nước đi (src→dst) → validate luật cờ
    5. Cập nhật FEN bộ nhớ

  [Lượt AI]
    1. Gửi FEN hiện tại cho AIController
    2. Ưu tiên gọi Cloud Engine API (tuongkydaisu.com) để lấy nước đi tốt nhất
    3. Tự động Fallback sang Local Pikafish nếu Cloud gặp sự cố (Lỗi mạng/Timeout)
    4. Nhận kết quả và ra lệnh cho Robot thực hiện thao tác gắp nhả (src/hardware/robot_VIP.py)
    5. Cập nhật FEN bộ nhớ → chụp T1 baseline mới
    6. Quay lại lượt Người

  [Rollback — phím Z]
    → Khôi phục toàn bộ state (board, FEN, T1 baseline) về trước SPACE vừa bấm

### 2.2. BOARD & FEN

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

### 2.3. NHẬN DIỆN YOLO (1-CLASS OCCUPANCY MODEL)

  Chỉ detect "có quân cờ" hay "ô trống" (1 class duy nhất).
  Bộ nhớ FEN đã biết quân gì ở đâu → không cần YOLO nói màu/loại.

  KẾT QUẢ TRAINING YOLO26:
    Model:      yolo26m.pt | 80 epochs | imgsz=640
    Precision:  95.5%  |  Recall: 99.2%  |  mAP50: 95.4%
    Weights:    runs/detect/chess_vision/yolo26_occupancy_run/weights/best.pt

### 2.4. CÁC RỦI RO & GIẢI PHÁP

  [R1] YOLO nhấp nháy → Pattern filter xử lý (Recall 99.2%, ít xảy ra)
  [R2] Xếp bàn cờ ban đầu sai → Xếp đúng chuẩn
  [R3] Perspective calibrate sai → Bấm V để calibrate lại
  [R4] Ăn quân (ambiguous) → Blind Capture Resolution (pixel absdiff)
  [R5] Bấm SPACE trước khi đi xong → Bỏ qua, hiển thị thông báo
  [R6] Khi ăn quân, YOLO detect quân đỏ tại ô đích → occupancy không đổi
       → Đã fix bằng Loại 3 dst_candidates_capture_stable (xem Phần 3.4.3)
  [R7] Lỗi MoveCart 101 khi go_to_home_chess() làm robot.connected=False sai
       → Đã fix: tách connect() và go_to_home_chess() thành 2 try riêng

### 2.5. PHÍM TẮT

  SPACE  → Chụp T2 snapshot, detect nước đi người chơi
  Z      → Rollback về trước SPACE vừa bấm (undo 1 nước)
  V      → Calibrate lại camera (click 4 góc bàn cờ)
  Q      → Thoát cửa sổ camera

### 2.6. CHECKLIST

  [x] Train YOLO26 (Precision 95.5%, Recall 99.2%)
  [x] Chuyển board sang FEN string
  [x] Tích hợp Pikafish engine
  [x] Phím SPACE để chụp snapshot
  [x] Xử lý pattern di chuyển thường + ăn quân (Blind Capture Resolution)
  [x] Chỉnh PICK_Z/PLACE_Z (PICK_Z=183, PLACE_Z=190 — cập nhật 2026-03-06)
  [x] Pikafish config (PIKAFISH_EXE, PIKAFISH_NNUE, PIKAFISH_THINK_MS)
  [x] Tải Pikafish 2026-01-02
  [x] Rollback (phím Z)
  [x] robot_VIP.py — Tool DO0
  [x] Tách file logic khỏi main.py vào kiến trúc Modular src/
  [x] Fix robot.connected bị set False sai khi go_to_home_chess lỗi
  [x] Fix snapshot_detector: detect ăn quân khi YOLO thấy quân đỏ tại ô đích
  [x] Thiết kế RUN.bat — double-click để chạy, tự động check thư viện
  [x] Khắc phục tay máy bị Singularity (Lỗi 101/14/112) bằng MoveJ + GetInverseKin
  [x] Gỡ bỏ yêu cầu bấm SPACE tạo baseline lần 2 sau lượt AI (Auto Snapshot)
  [x] Tích hợp bộ thư viện Robot SDK `robot_sdk_core.*` vào module phần cứng `src/hardware/`
  [ ] Xác định và lưu điểm HOMECHESS lên bộ nhớ Robot để sửa lỗi err=143
  [ ] Verify bàn cờ lúc bắt đầu game (tùy chọn)

================================================================================
## PHẦN 3: TÀI LIỆU CÁC MODULE (CHI TIẾT THEO THƯ MỤC)
================================================================================

### 3.1. MODULE CORE (`src/core/`)
Đảm nhiệm logic cờ và lưu trữ trạng thái Game. Không phụ thuộc Pygame.

#### 3.1.1. `xiangqi.py`
Chứa toàn bộ "Luật Cờ Tướng" (Game Rules) cốt lõi của hệ thống.
EXPORT:
  - `initial_board`: Mảng 2D (10x9) định nghĩa vị trí quân cờ lúc bắt đầu.
  - `is_valid_move(src, dst, board, color)`: Trái tim của file. Validate quy tắc di chuyển cho từng loại quân cờ (Xe đi thẳng, Mã đi chữ L có cản, Pháo ăn qua ngòi, Tướng không xuất tướng...).
  - `is_king_in_check(color, board)`: Kiểm tra trạng thái "Bị chiếu tướng".
  - Zobrist Hashing (`get_zobrist_key`): Băm trạng thái bàn cờ hiện tại thành chuỗi mã hóa để tối ưu lưu vết bộ nhớ.

#### 3.1.2. `fen_utils.py`
Module thuần (pure functions), không có side effect, dễ test độc lập.
EXPORT:
  - `INITIAL_FEN`: FEN vị trí ban đầu chuẩn
  - `board_array_to_fen(board, color='r', move_number=1)` → str
  - `fen_to_board_array(fen)` → (board, color)

#### 3.1.3. `game_state.py`
Chứa class `GameState`. Quản lý toàn bộ vòng đời data, xóa bỏ biến Global.
Lưu giữ: `board`, `turn`, `current_fen`, `move_history`, `game_over`
Method chính: `update_fen_from_board()`, `reset_game()`, `handle_rollback()`, `process_human_move()`, `handle_game_over()`.

---

### 3.2. MODULE AI (`src/ai/`)
Giao tiếp với Engine cờ tướng bên ngoài. Hỗ trợ hệ thống HYBRID (Cloud first, Local fallback).

#### 3.2.1. `pikafish_engine.py`
Hoạt động như một "Phiên dịch viên" (UCI Bridge) trực tiếp nói chuyện với phần mềm Pikafish độc lập thông qua Subprocess. Đóng gói các tác vụ giao tiếp luồng (stdin/stdout).
CLASS PikafishEngine:
  - `start() / stop() / _atexit_cleanup()`: Quản lý vòng đời tiến trình con chạy `pikafish-avx2.exe`. Bắt buộc dùng `atexit` để dọn rác tiến trình khi luồng game chính bị sập, tránh rác RAM.
  - `board_to_fen()`: Tự động lật hệ tọa độ (Rank 0-9 Array của mình sang Rank 9-0 của UCI FEN).
  - `pick_best_move(board, color, movetime_ms)`: Gửi lệnh `go movetime...` để ép AI suy nghĩ, block luồng chờ kết quả `bestmove`, tự bóc tách chuỗi tọa độ `a0`-`i9` trả về index lưới game.

#### 3.2.2. `cloud_engine.py`
Module tương tác với REST API `tuongkydaisu.com/api/engine/bestmove`.
CLASS CloudEngine:
  - Không cần duy trì subprocess con.
  - Sử dụng chung phương thức `board_to_fen` và xử lý kết quả bóc tách chuỗi tọa độ (Ví dụ `"h2e2"`).
  - Cực kỳ tiết kiệm hiệu năng CPU / Memory cho thiết bị Local.

#### 3.2.3. `ai_controller.py`
Wrapper quản lý Pikafish engine và Cloud engine, tách logic UCI khỏi luồng chính.
CLASS AIController:
  - Nhận Local / Cloud engines instance và config module.
  - `pick_move(board_snapshot, color="b")`: Chạy Engine lấy nước cờ tốt nhất ở dạng chuỗi. Áp dụng cơ chế bắt lỗi Error Catching, tự động luân chuẩn chuyển quyền cho Local `PikafishEngine` nếu gọi `CloudEngine` thất bại (Timeout/Error). Chạy trong Thread phụ để không khóa render GUI.

---

### 3.3. MODULE HARDWARE (`src/hardware/`)
Thư viện quản lý thiết bị cứng và điều phối tín hiệu.

#### 3.3.1. `robot_VIP.py`
File điều khiển cánh tay robot FR5.
CÁC HÀM:
  - `connect()`: Kết nối robot qua RPC SDK.
  - `board_to_pose()`: Đổi tọa độ cờ sang trục xyz (mm).
  - `move_safe_pose()`: Di chuyển ngang an toàn (MoveCart). Vượt qua quân cờ khác nhờ Z cố định.
  - `go_to_home_chess()`: Dùng MoveJ thực thụ để vớt tay khỏi điểm Singularity (Lỗi 101/14/112).
  - `pick_at()` / `place_at()` / `place_in_capture_bin()` / `gripper_ctrl()`.
  - Hàm Chính: `move_piece(s,d,capture)` được main gọi trực tiếp.

#### 3.3.2. `robot_sdk_core.py` & `robot_sdk_core.c`
Bộ SDK điều khiển Robot nguyên bản do hãng Fairino cung cấp.
  - `robot_sdk_core.py`: File mã nguồn Python chứa toàn bộ giao thức mạng để nói chuyện với tụ điện điều khiển của tay máy FR5. Dùng XML-RPC (port 20003) để gửi lệnh và dùng TCP Socket (port 20004) để nhận dữ liệu thời gian thực. Định nghĩa sẵn cấu trúc dữ liệu khổng lồ `RobotStatePkg`.
  - `robot_sdk_core.c`: File mã C được sinh ra bởi công cụ Cython (biên dịch Python sang C). Phục vụ cho việc tăng tốc độ thực thi của SDK, giúp Python chạy tiệm cận tốc độ máy.

#### 3.3.3. `hardware_manager.py`
Chứa class `HardwareManager`. Điểm chạm kết nối thiết bị vật lý và trí tuệ nhân tạo.
Gói gọn: `FR5Robot`, `PikafishEngine`, `CameraMonitor`, `YoloSnapshotDetector`. Khởi tạo tất cả theo nguyên tắc bật thiết bị và dọn bộ nhớ tự động với `initialize_all()` và `cleanup()`.

---

### 3.4. MODULE VISION (`src/vision/`)
Thị giác máy tính. Tính toán góc camera và xuất tọa độ nước đi người dùng.

#### 3.4.1. `calibrate_camera.py`
Hiệu chỉnh perspective camera, click 4 góc bàn cờ để map kích thước lên mảng 2D.
Xuất ra Output là file: `perspective.npy` (ma trận 3x3 float32, M: pixel → grid).
Luồng: Bấm 'V' → Warm up camera → Click 4 góc: Đen Trái, Đen Phải, Đỏ Phải, Đỏ Trái.

#### 3.4.2. `camera_monitor.py`
SINGLE CAMERA OWNER — Thread chạy ngầm thu hoạch hình ảnh liên tục.
FIX Lag Delay (2026-03-05): Dùng `cap.grab()` xả hàng đợi cũ của OpenCV để lấy chính xác tấm ảnh không trễ thời gian thực. Bỏ sleep() vì YOLO chạy đủ tốn CPU rồi.
API: `get_fresh_snapshot()` (blocking để phục vụ SPACE), `get_latest_frame_and_detections()` (non-blocking để debug/render).

#### 3.4.3. `snapshot_detector.py`
So sánh T1 (Baseline) và T2 (Sau khi đi) để đoán nước đi của người chơi.
Thuật toán chia ra thành 4 lớp độ ưu tiên. Tích hợp Blind Capture Resolution (Chụp ảnh và lấy absdiff để quét mảnh màu tìm thay đổi khi ăn quân).
Giải quyết lỗi loại 3: Ô đối phương T1=True & T2=True (Stable). Lấy ô đích nếu quân đỏ chèn lên đúng vị trí cũ mà occupancy không đổi.

---

### 3.5. MODULE UI (`src/ui/`)
Giao diện người dùng đồ họa bằng Pygame và trình quản lý sự kiện.

#### 3.5.1. `input_handler.py`
Điều phối tác vụ do người dùng tạo ra vào GameState và HardwareManager.
  - **Phím** (`SPACE` để chạy luồng Vision so sánh ảnh, `Z` để Rollback cả dữ liệu cờ lẫn ảnh Baseline gốc). Nếu vision thất bại, chặn đứng màn hình và bật mode Manual Override.
  - **Chuột** (Kéo thả Manual Override hoạt động độc lập không xài robot; Nút Surrender/New Game).

#### 3.5.2. `board_renderer.py`
Render giao diện bàn cờ Pygame màn hình 800x600. Vẽ Highlight ô đỏ/xanh biểu thị lỗi, nước đi gần nhất. Tính toán layout hiển thị Game Over Banner bằng Font.

---

### 3.6. CÁC FILE Lõi (ROOT FILES)

#### 3.6.1. `main.py`
Vòng lặp game chính (Game Loop 30FPS). Kiến trúc gọn nhẹ, đóng vai trò Controller trung tâm gọi Renderer, đưa Event vào InputHandler, và chạy Thread chờ AI đánh cờ. Hỗ trợ kích hoạt DRY_RUN tắt phụ thuộc phần mềm.

#### 3.6.2. `RUN.bat`
Script tự kích hoạt và xác minh Virtual Environment, kiểm tra sự tồn tại của Pikafish AI rồi mới khởi chạy ứng dụng tránh sập nguồn giữa trận.

#### 3.6.3. `perspective.npy`
File trọng số sinh ra bởi Calibrate Camera. Mất file → Hệ thống hỏng tính năng chụp ảnh AI.

================================================================================
## PHẦN 4: AI CHESS ENGINE (HYBRID / CLOUD / LOCAL)
================================================================================

  Config trung tâm lưu tại (config.py):
    ENGINE_TYPE       = "HYBRID" # Lựa chọn: "HYBRID", "CLOUD", "LOCAL"
    CLOUD_API_URL     = "https://tuongkydaisu.com/api/engine/bestmove"
    PIKAFISH_EXE      = pikafish/pikafish-avx2.exe
    PIKAFISH_NNUE     = pikafish/pikafish.nnue
    PIKAFISH_THINK_MS = 3000   (ms mỗi nước, dành cho Local)

  Phiên bản đang dùng: Pikafish 2026-01-02 (tải 2026-03-05)
  Source: https://github.com/official-pikafish/Pikafish/releases/tag/Pikafish-2026-01-02
  File: Pikafish.2026-01-02.7z → giải nén → copy Windows/pikafish-avx2.exe vào pikafish/

  File exe + nnue KHÔNG push git (.gitignore).
  Tải: https://github.com/official-pikafish/Pikafish/releases

================================================================================
