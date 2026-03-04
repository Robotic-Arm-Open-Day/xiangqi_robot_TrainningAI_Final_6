# ===================================================================================
# === FILE: main_VIP.py (VIP VERSION: FEN + PIKAFISH + SPACE KEY SNAPSHOT) ===
# ===================================================================================
import sys
import os
import time
import numpy as np
import cv2
import traceback
import json
import math
import random
import threading
from pathlib import Path

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_DIR = os.path.dirname(_THIS_DIR)  # thư mục gốc project
sys.path.insert(0, _THIS_DIR)
sys.path.insert(0, _PROJECT_DIR)

import pygame
from ultralytics import YOLO

import config
import xiangqi
import sound_player

# IMPORT PIKAFISH (thay thế ai.py)
from pikafish_engine import PikafishEngine

# IMPORT BOOK
try:
    import ai_book
except ImportError:
    try:
        import opening_book as ai_book
    except ImportError:
        print("❌ ERROR: Could not find book file (ai_book.py)")
        sys.exit()

from robot import FR5Robot

# ==========================================
# 0. CẤU HÌNH CHẾ ĐỘ (CONFIG)
# ==========================================
ALLOW_MOUSE_MOVE = config.DRY_RUN

print(
    f"\n=== MODE: {'🛠️ DRY RUN (MOUSE & LOG)' if config.DRY_RUN else '🤖 REAL RUN (CAMERA & ROBOT)'} ==="
)

# ==========================================
# 1. FEN CONVERSION FUNCTIONS
# ==========================================

# Mapping: internal piece name → FEN character
_PIECE_TO_FEN = {
    'r_K': 'K', 'r_A': 'A', 'r_E': 'B', 'r_N': 'N',
    'r_R': 'R', 'r_C': 'C', 'r_P': 'P',
    'b_K': 'k', 'b_A': 'a', 'b_E': 'b', 'b_N': 'n',
    'b_R': 'r', 'b_C': 'c', 'b_P': 'p',
}

# Reverse mapping: FEN character → internal piece name
_FEN_TO_PIECE = {v: k for k, v in _PIECE_TO_FEN.items()}

def board_array_to_fen(board, color='r', move_number=1):
    """Convert 10x9 board array + active color → FEN string.
    
    Args:
        board: 10x9 list-of-lists (our format)
        color: 'r' for Red to move, 'b' for Black to move
        move_number: full move counter
    Returns:
        FEN string, e.g. "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1"
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
                fen_char = _PIECE_TO_FEN.get(p)
                if fen_char is None:
                    raise ValueError(f"Unknown piece: '{p}' at board[{r}][{c}]")
                row_str += fen_char
        if empty:
            row_str += str(empty)
        rows.append(row_str)

    fen_color = 'w' if color == 'r' else 'b'
    return f"{'/'.join(rows)} {fen_color} - - 0 {move_number}"

def fen_to_board_array(fen):
    """Convert FEN string → 10x9 board array + active color.
    
    Returns:
        (board, color) where board is 10x9 list, color is 'r' or 'b'
    """
    parts = fen.split(' ')
    ranks = parts[0].split('/')
    color = 'r' if parts[1] == 'w' else 'b'
    
    board = []
    for rank_str in ranks:
        row = []
        for ch in rank_str:
            if ch.isdigit():
                row.extend(['.'] * int(ch))
            else:
                piece = _FEN_TO_PIECE.get(ch)
                if piece is None:
                    raise ValueError(f"Unknown FEN character: '{ch}'")
                row.append(piece)
        if len(row) != 9:
            raise ValueError(f"Invalid rank length: {len(row)} (expected 9)")
        board.append(row)
    
    if len(board) != 10:
        raise ValueError(f"Invalid number of ranks: {len(board)} (expected 10)")
    
    return board, color

# FEN vị trí ban đầu chuẩn
INITIAL_FEN = "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1"

# ==========================================
# 2. KHỞI TẠO PYGAME + RENDERER
# ==========================================
pygame.init()
pygame.font.init()

from board_renderer import BoardRenderer, SCREEN_WIDTH, SCREEN_HEIGHT
from board_renderer import BTN_SURRENDER_RECT, BTN_NEW_GAME_RECT
from board_renderer import NUM_COLS, NUM_ROWS

screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
pygame.display.set_caption(
    f"Xiangqi Robot VIP - Mode: {'MOUSE (DRY)' if ALLOW_MOUSE_MOVE else 'CAMERA (REAL)'}"
)
renderer = BoardRenderer(screen)

# ==========================================
# 3. TRẠNG THÁI GAME (FEN-based)
# ==========================================
current_fen = INITIAL_FEN
board, turn = fen_to_board_array(current_fen)
game_over = False
winner = None
last_move = None
selected_pos = None
r_captured = []
b_captured = []
move_history = []
move_number = 1

# --- UI FEEDBACK ---
status_message = ""
status_color   = (0, 0, 0)
status_expiry  = 0.0
invalid_flash_pos = None
invalid_flash_expiry = 0.0

# --- AI THREAD STATE ---
ai_thread        = None
ai_result        = None
ai_thinking      = False
ai_think_start   = 0.0

# --- ROBOT & CAMERA CONFIG ---
robot = FR5Robot()

try:
    if not config.DRY_RUN:
        robot.connect()
        robot.go_to_home_chess()
    else:
        print("[MAIN] DRY_RUN: Skipping physical robot connection.")
        robot.connected = False
except Exception as e:
    print(f"⚠️ [MAIN] Robot connection error: {e}")
    print("   → Tiếp tục chạy KHÔNG có robot (camera + calibrate vẫn hoạt động)")
    robot.connected = False

# --- HIỆU CHỈNH ROBOT ---
print("\n--- ROBOT CALIBRATION ---")
dst_pts_logic = np.array([[0, 0], [8, 0], [8, 9], [0, 9]], dtype=np.float32)
try:
    if config.DRY_RUN:
        src_pts_fake = np.array([[200, -100], [520, -100], [520, 260], [200, 260]], dtype=np.float32)
        robot.set_perspective_matrix(cv2.getPerspectiveTransform(dst_pts_logic, src_pts_fake))
    else:
        print("Reading coordinates from robot...")
        pts_data = []
        for i in range(1, 5):
            err, data = robot.robot.GetRobotTeachingPoint(f"R{i}")
            if err: raise Exception(f"Error getting point R{i}")
            pts_data.append([float(data[0]), float(data[1])])

        src_pts_robot = np.array(pts_data, dtype=np.float32)
        M_rob = cv2.getPerspectiveTransform(dst_pts_logic, src_pts_robot)
        robot.set_perspective_matrix(M_rob)
        print("=== ROBOT CALIBRATION OK ===")
except Exception as e:
    print(f"⚠️ [MAIN] Robot calibration error: {e}")
    print("   → Bỏ qua robot calibration, dùng fake matrix.")
    src_pts_fake = np.array([[200, -100], [520, -100], [520, 260], [200, 260]], dtype=np.float32)
    robot.set_perspective_matrix(cv2.getPerspectiveTransform(dst_pts_logic, src_pts_fake))

# --- KHỞI TẠO PIKAFISH ENGINE ---
engine = None
if not config.DRY_RUN or True:  # Pikafish hoạt động cả DRY_RUN
    try:
        _pikafish_exe = getattr(config, 'PIKAFISH_EXE', None)
        _pikafish_nnue = getattr(config, 'PIKAFISH_NNUE', None)
        
        if _pikafish_exe and os.path.isfile(_pikafish_exe):
            engine = PikafishEngine(_pikafish_exe)
            engine.start(nnue_path=_pikafish_nnue)
            print("✅ Pikafish engine started!")
        else:
            print(f"⚠️ Pikafish exe not found at: {_pikafish_exe}")
            print("   → Fallback: sẽ dùng ai.py nếu có")
            try:
                import ai as ai_fallback
                print("   → ai.py loaded as fallback")
            except ImportError:
                print("   ❌ Không có ai.py fallback. AI sẽ không hoạt động!")
    except Exception as e:
        print(f"⚠️ Pikafish init error: {e}")
        engine = None

# --- LOAD MODEL YOLO ---
model = None
cap = None
if not config.DRY_RUN:
    MODEL_PATH = str(Path(_PROJECT_DIR) / "runs" / "detect" / "chess_vision" / "yolo26_occupancy_run" / "weights" / "best.pt")
    try:
        model = YOLO(MODEL_PATH)
        print(f"✅ Model loaded: {MODEL_PATH}")
    except Exception as e:
        print(f"⚠️ Warning: Could not load model: {e}")

    _cam_index = int(os.environ.get("VIDEO_INDEX", str(config.VIDEO_SOURCE)))
    cap = None
    for _idx in [_cam_index] + [i for i in [0, 1, 2] if i != _cam_index]:
        _cap_try = cv2.VideoCapture(_idx, cv2.CAP_DSHOW)
        if _cap_try.isOpened():
            cap = _cap_try
            print(f"✅ Camera opened at index {_idx}")
            break
        else:
            _cap_try.release()
            print(f"⚠️ Camera index {_idx} failed, trying next...")
    if cap is None:
        print("❌ Lỗi: Không mở được Camera!")
        sys.exit()
    else:
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        actual_w = cap.get(cv2.CAP_PROP_FRAME_WIDTH)
        actual_h = cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
        print(f"📷 Actual camera resolution: {actual_w} x {actual_h}")

PERSPECTIVE_PATH = Path(__file__).parent / "perspective.npy"
CLASS_ID_TO_INTERNAL_NAME = {
    0: "b_A", 1: "b_C", 2: "b_R", 3: "b_E", 4: "b_K", 5: "b_N", 6: "b_P",
    8: "r_A", 9: "r_C", 10: "r_R", 11: "r_E", 12: "r_K", 13: "r_N", 14: "r_P",
}

# --- CALIBRATE: Import từ file riêng ---
from calibrate_camera import calibrate_perspective_camera

# --- AUTO-CALIBRATE: Chạy calibrate camera ngay khi khởi động (REAL RUN) ---
if not config.DRY_RUN and cap is not None:
    print("\n" + "=" * 60)
    print("  📐  CAMERA CALIBRATION — BẮT BUỘC KHI KHỞI ĐỘNG")
    print("=" * 60)
    if os.path.exists(str(PERSPECTIVE_PATH)):
        print(f"⚠️  Đã có file cũ: {PERSPECTIVE_PATH}")
        print("   Bấm 'S' để dùng lại hoặc calibrate lại bằng cách click 4 góc.")
    calibrate_perspective_camera(cap, str(PERSPECTIVE_PATH))
    
    if not os.path.exists(str(PERSPECTIVE_PATH)):
        print("❌ Chưa có perspective.npy! Không thể detect nước đi.")
        print("   Hãy chạy lại và calibrate camera.")
        sys.exit()
    else:
        print("✅ Camera calibration OK!")
    print("=" * 60 + "\n")

# --- KHỚI TẠO CAMERA MONITOR (liên tục) ---
from camera_monitor import CameraMonitor
cam_monitor = None
if not config.DRY_RUN and cap is not None and model is not None:
    cam_monitor = CameraMonitor(cap, model, PERSPECTIVE_PATH)
    cam_monitor.start()

# --- KHỞI TẠO SNAPSHOT DETECTOR (T1/T2) ---
from snapshot_detector import SnapshotDetector
snapshot_detector = None
if not config.DRY_RUN and cap is not None and model is not None:
    snapshot_detector = SnapshotDetector(cap, model, PERSPECTIVE_PATH, CLASS_ID_TO_INTERNAL_NAME)
    print("[INIT] ✅ SnapshotDetector initialized.")

# ==========================================
# 4. HÀM HỖ TRỢ
# ==========================================
def pixel_to_grid(px, py):
    return BoardRenderer.pixel_to_grid(px, py)

def update_fen_from_board():
    """Cập nhật current_fen từ board array hiện tại."""
    global current_fen
    current_fen = board_array_to_fen(board, turn, move_number)

def get_game_state():
    """Tạo dict game state cho renderer."""
    return {
        "game_over": game_over,
        "turn": turn,
        "allow_mouse": ALLOW_MOUSE_MOVE,
        "ai_thinking": ai_thinking,
        "ai_think_start": ai_think_start,
        "status_message": status_message,
        "status_color": status_color,
        "status_expiry": status_expiry,
    }


# --- SNAPSHOT: Chụp 1 ảnh, detect occupancy ---
def detections_to_grid_occupancy(detections, M):
    """Convert YOLO detections → 10x9 grid ('occupied' / '.')"""
    grid = [["." for _ in range(NUM_COLS)] for _ in range(NUM_ROWS)]
    if M is None: return grid
    
    for cls_id, (x1, y1, x2, y2) in detections:
        name = CLASS_ID_TO_INTERNAL_NAME.get(cls_id)
        if not name: continue
        
        cx = (x1 + x2) / 2
        cy = y1 + (y2 - y1) * 0.85
        
        try:
            dst = cv2.perspectiveTransform(np.array([[[float(cx), float(cy)]]], dtype=np.float32), M)[0][0]
            c, r = int(round(dst[0])), int(round(dst[1]))
            if 0 <= c < NUM_COLS and 0 <= r < NUM_ROWS:
                grid[r][c] = name  # Giữ tên quân nếu model 14 class
        except: pass
    return grid

def get_snapshot_board():
    """Chụp 1 snapshot, chạy YOLO, trả về occupancy grid 10x9."""
    if cap is None or model is None:
        return None
        
    print("[CAM] 📸 Chụp Snapshot bàn cờ...")
    for _ in range(5):
        cap.grab()
        
    ret, frame = cap.read()
    if not ret:
        return None
        
    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    results = model.predict(frame_rgb, conf=0.35, iou=0.35, imgsz=1280, verbose=False)
    
    detections = []
    for box in results[0].boxes:
        cls = int(box.cls[0])
        if cls in CLASS_ID_TO_INTERNAL_NAME:
            x1, y1, x2, y2 = map(int, box.xyxy[0])
            detections.append((cls, (x1, y1, x2, y2)))
            
    # View port
    for (cls, (x1, y1, x2, y2)) in detections:
        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
    cv2.imshow("Camera Monitor", frame)
    cv2.waitKey(1)
            
    M_cam = np.load(str(PERSPECTIVE_PATH)) if os.path.exists(str(PERSPECTIVE_PATH)) else None
    if M_cam is None: return None
    
    return detections_to_grid_occupancy(detections, M_cam)

def detect_move_from_snapshot(cam_grid):
    """So sánh snapshot camera với board trong bộ nhớ.
    
    Trả về (src, dst, piece_name) hoặc (None, None, None).
    Logic: So sánh quân ĐỎ giữa memory và camera:
      - src: ô memory có quân đỏ nhưng camera KHÔNG thấy quân đỏ
      - dst: ô memory KHÔNG có quân đỏ nhưng camera thấy quân đỏ
    """
    missing_reds = []  # Memory có quân đỏ, camera không thấy đỏ ở đó
    new_reds = []      # Memory không có quân đỏ, camera thấy đỏ ở đó
    
    for r in range(NUM_ROWS):
        for c in range(NUM_COLS):
            mem_piece = board[r][c]
            cam_piece = cam_grid[r][c]
            
            mem_is_red = mem_piece.startswith("r")
            cam_is_red = cam_piece.startswith("r") if cam_piece != "." else False
            
            if mem_is_red and not cam_is_red:
                # Quân đỏ biến mất khỏi ô này → có thể là src
                missing_reds.append((c, r, mem_piece))
            elif not mem_is_red and cam_is_red:
                # Quân đỏ xuất hiện ở ô mới → có thể là dst
                new_reds.append((c, r, cam_piece))
    
    # Debug log
    print(f"[DETECT] missing_reds={len(missing_reds)}, new_reds={len(new_reds)}")
    if missing_reds:
        print(f"  missing: {[(c,r,p) for c,r,p in missing_reds]}")
    if new_reds:
        print(f"  new:     {[(c,r,p) for c,r,p in new_reds]}")
    
    # Pattern 1: Di chuyển thường — 1 quân đỏ mất, 1 quân đỏ xuất hiện
    if len(missing_reds) == 1 and len(new_reds) == 1:
        src = (missing_reds[0][0], missing_reds[0][1])
        dst = (new_reds[0][0], new_reds[0][1])
        piece = missing_reds[0][2]
        return src, dst, piece
    
    # Pattern 2: Ăn quân đen — 1 quân đỏ mất ở src, quân đỏ thay thế quân đen ở dst
    # Camera thấy đỏ ở vị trí cũ là đen → new_reds bắt được dst
    # Nếu new_reds == 0, có thể camera nhận nhầm quân đỏ thành đen ở dst
    if len(missing_reds) == 1 and len(new_reds) == 0:
        src_c, src_r, piece = missing_reds[0]
        # Tìm ô mà memory có quân đen nhưng camera thấy quân (có thể đỏ bị nhận nhầm)
        candidates = []
        for r in range(NUM_ROWS):
            for c in range(NUM_COLS):
                mem_p = board[r][c]
                cam_p = cam_grid[r][c]
                if mem_p.startswith("b") and cam_p != "." and not cam_p.startswith("b"):
                    # Ô này: memory = đen, camera = không phải đen (có thể đỏ)
                    candidates.append((c, r))
        if len(candidates) == 1:
            dst = candidates[0]
            print(f"[DETECT] Pattern ăn quân: {piece} ({src_c},{src_r})→{dst}")
            return (src_c, src_r), dst, piece
    
    # Pattern 3: Nhiều quân bị nhận sai → chọn cặp gần nhất
    if len(missing_reds) >= 1 and len(new_reds) >= 1:
        # Chọn cặp (missing, new) có khoảng cách gần nhất (hợp lý nhất)
        best_pair = None
        best_dist = 999
        for mc, mr, mp in missing_reds:
            for nc, nr, np_ in new_reds:
                dist = abs(mc - nc) + abs(mr - nr)
                if dist < best_dist:
                    best_dist = dist
                    best_pair = ((mc, mr, mp), (nc, nr, np_))
        if best_pair and best_dist <= 10:  # Khoảng cách hợp lý
            src = (best_pair[0][0], best_pair[0][1])
            dst = (best_pair[1][0], best_pair[1][1])
            piece = best_pair[0][2]
            print(f"[DETECT] Pattern multi (dist={best_dist}): {piece} {src}→{dst}")
            return src, dst, piece
    
    return None, None, None

# --- GAME LOGIC ---
def reset_game():
    global board, turn, game_over, winner, last_move, selected_pos
    global r_captured, b_captured, move_history, move_number
    global current_fen
    global status_message, status_expiry, invalid_flash_pos, invalid_flash_expiry
    global ai_thread, ai_result, ai_thinking, ai_think_start
    
    current_fen = INITIAL_FEN
    board, turn = fen_to_board_array(current_fen)
    game_over = False
    winner = None
    last_move = None
    selected_pos = None
    r_captured = []
    b_captured = []
    move_history = []
    move_number = 1
    status_message = ""
    status_expiry  = 0.0
    invalid_flash_pos = None
    invalid_flash_expiry = 0.0
    ai_thread = None
    ai_result = None
    ai_thinking = False
    ai_think_start = 0.0
    print("[GAME] 🔄 New game started!")
    print(f"[FEN] {current_fen}")
    
    # Chụp T1 baseline cho game mới
    if snapshot_detector is not None:
        time.sleep(1)  # Đợi bàn cờ ổn định
        if cam_monitor is not None: cam_monitor.pause()
        try:
            snapshot_detector.capture_baseline()
        finally:
            if cam_monitor is not None: cam_monitor.resume()

def set_status(msg, color=(200, 0, 0), duration=2.5):
    global status_message, status_color, status_expiry
    status_message = msg
    status_color   = color
    status_expiry  = time.time() + duration

def set_invalid_flash(col, row, duration=0.6):
    global invalid_flash_pos, invalid_flash_expiry
    invalid_flash_pos    = (col, row)
    invalid_flash_expiry = time.time() + duration

def handle_game_over(the_winner):
    global game_over, winner
    winner, game_over = the_winner, True
    if the_winner == "b":
        print("\n[LEARN] 🧠 AI Wins! Saving data to book...")
        ai_book.learn_game(move_history, the_winner)
    else:
        print("\n[LEARN] 🗑️ AI Lost! NOT saving this data.")

def process_human_move(src, dst, p_name):
    global board, last_move, turn, current_fen, move_number
    print(f"[HUMAN] ✅ Moved: {p_name} {src}->{dst}")
    set_status("✅  Move accepted — AI thinking...", color=(0, 120, 0), duration=5.0)
    
    key = ai_book.board_to_key(board)
    move_history.append({"turn": "r", "key": key, "src": src, "dst": dst})
    
    cap_p = board[dst[1]][dst[0]]
    if cap_p != ".": b_captured.append(cap_p)
    
    board, _ = xiangqi.make_temp_move(board, (src, dst))
    last_move = (src, dst)
    
    # Cập nhật FEN
    turn = "b"  # Chuyển lượt trước khi tạo FEN
    move_number += 1
    update_fen_from_board()
    print(f"[FEN] {current_fen}")
    
    if xiangqi.get_king_pos("b", board) is None:
        handle_game_over("r")
        turn = "r"  # game over, reset turn display

def handle_space_key():
    """Xử lý khi người chơi bấm SPACE — chụp T2 và so sánh với T1."""
    if turn != "r" or game_over:
        return
    
    print("\n[SPACE] 🎯 Người chơi bấm SPACE — đang chụp T2 snapshot...")
    set_status("📸  Đang chụp và phân tích...", color=(0, 100, 180), duration=3.0)
    
    # Kiểm tra đã có T1 baseline chưa
    if snapshot_detector is None:
        set_status("❌  Snapshot detector chưa khởi tạo!", color=(180, 0, 0))
        return
    
    # ⏸️ Tạm dừng CameraMonitor để tránh tranh camera
    if cam_monitor is not None:
        cam_monitor.pause()
        time.sleep(0.3)  # Đợi thread dừng hẳn
    
    try:
        if not snapshot_detector.has_baseline():
            print("[SPACE] ⚠️ Chưa có T1 baseline — chụp ngay...")
            if snapshot_detector.capture_baseline():
                set_status("📸 Đã chụp T1 baseline. Đi quân rồi bấm SPACE lại!", color=(0, 100, 180), duration=5.0)
            else:
                set_status("❌ Không chụp được baseline!", color=(180, 0, 0))
            return
        
        # Chụp T2 và so sánh với T1
        src, dst, piece = snapshot_detector.detect_move()
    finally:
        # ▶️ Luôn resume CameraMonitor dù có lỗi hay không
        if cam_monitor is not None:
            cam_monitor.resume()
    
    if src is None or dst is None:
        set_status("❌  Không phát hiện nước đi! Bấm SPACE lại.", color=(180, 0, 0))
        print("[SPACE] ❌ No valid move detected from T1/T2 comparison")
        return
    
    print(f"[SPACE] 👀 Phát hiện: {piece} {src}->{dst}")
    
    if xiangqi.is_valid_move(src, dst, board, "r"):
        process_human_move(src, dst, piece)
    else:
        print(f"[SPACE] ❌ Nước đi không hợp lệ: {src}->{dst}")
        set_status("❌  Nước đi không hợp lệ!", color=(180, 0, 0))
        set_invalid_flash(dst[0], dst[1])

# ==========================================
# 5. VÒNG LẶP CHÍNH
# ==========================================
running = True
clock = pygame.time.Clock()

print(f"\n[GAME] === GAME STARTED ===")
print(f"[FEN] {current_fen}")

# --- Chụp T1 baseline ban đầu ---
if snapshot_detector is not None:
    print("[INIT] 📸 Chụp T1 baseline ban đầu...")
    time.sleep(1)  # Đợi camera ổn định
    if cam_monitor is not None: cam_monitor.pause()
    try:
        snapshot_detector.capture_baseline()
    finally:
        if cam_monitor is not None: cam_monitor.resume()

try:
    while running:
        renderer.draw_ui(get_game_state())
        renderer.draw_pieces(board)
        renderer.draw_highlight(last_move, selected_pos, invalid_flash_pos, invalid_flash_expiry)

        for event in pygame.event.get():
            if event.type == pygame.QUIT: running = False
            if event.type == pygame.KEYDOWN:
                # === SPACE KEY: Chụp snapshot và detect nước đi ===
                if event.key == pygame.K_SPACE and not ALLOW_MOUSE_MOVE:
                    handle_space_key()

            if event.type == pygame.MOUSEBUTTONDOWN:
                mx, my = event.pos
                if BTN_SURRENDER_RECT.collidepoint(mx, my) and not game_over:
                    print("[GAME] YOU SURRENDER!")
                    handle_game_over("b")
                    continue

                if BTN_NEW_GAME_RECT.collidepoint(mx, my):
                    reset_game()
                    continue

                # Mouse move (DRY RUN only)
                if ALLOW_MOUSE_MOVE and turn == "r" and not game_over:
                    c, r = pixel_to_grid(mx, my)
                    if 0 <= c < NUM_COLS and 0 <= r < NUM_ROWS:
                        clicked_piece = board[r][c]
                        if clicked_piece.startswith("r"):
                            selected_pos = (c, r)
                        elif selected_pos:
                            src, dst = selected_pos, (c, r)
                            p_name = board[src[1]][src[0]]
                            if xiangqi.is_valid_move(src, dst, board, "r"):
                                process_human_move(src, dst, p_name)
                                selected_pos = None
                            else:
                                print(f"Invalid move: {src}->{dst}")
                                set_status("❌  Invalid move!", color=(180, 0, 0))
                                set_invalid_flash(dst[0], dst[1])
                                selected_pos = None

        # --- Camera Monitor: cập nhật hiển thị mỗi frame ---
        if cam_monitor is not None:
            key = cam_monitor.update_display()
            if key == ord("q"): running = False

        # ==========================================
        # --- AI TURN (THREADED — NON-BLOCKING UI) ---
        # ==========================================
        if turn == "b" and not game_over:

            # --- STEP 1: SPAWN AI THREAD ---
            if not ai_thinking and ai_thread is None:
                board_snapshot = [row[:] for row in board]
                fen_snapshot = current_fen
                ai_result = None
                ai_thinking = True
                ai_think_start = time.time()

                def _ai_worker():
                    global ai_result
                    try:
                        if engine is not None:
                            # Pikafish: gửi FEN trực tiếp
                            _think_ms = getattr(config, 'PIKAFISH_THINK_MS', 3000)
                            ai_result = engine.pick_best_move(board_snapshot, "b", movetime_ms=_think_ms)
                        else:
                            # Fallback ai.py
                            try:
                                ai_result = ai_fallback.pick_best_move(board_snapshot, "b")
                            except:
                                print("[AI] ❌ No AI engine available!")
                                ai_result = None
                    except Exception as e:
                        print(f"[AI Thread] Error: {e}")
                        traceback.print_exc()
                        ai_result = None

                ai_thread = threading.Thread(target=_ai_worker, daemon=True)
                ai_thread.start()
                print("[AI] 🧵 Thinking thread started...")

            # --- STEP 2: CHECK IF THREAD DONE ---
            elif ai_thinking and ai_thread is not None:
                if not ai_thread.is_alive():
                    ai_thinking = False
                    ai_thread = None
                    best = ai_result
                    ai_result = None

                    # Loop detection
                    if best:
                        try: s, d = best
                        except: s, d = best[0], best[1]
                        if len(move_history) > 8:
                            last_srcs = [m['src'] for m in move_history[-6:]]
                            if last_srcs.count(s) >= 3:
                                print(f"⚠️ AI LOOP DETECTED ({s}->{d}) -> PANIC MODE!")
                                valid_moves = xiangqi.find_all_valid_moves("b", board)
                                if valid_moves:
                                    best = random.choice(valid_moves)
                                    s, d = best

                    if best:
                        try: s, d = best
                        except: s, d = best[0], best[1]

                        key = ai_book.board_to_key(board)
                        move_history.append({"turn": "b", "key": key, "src": s, "dst": d})
                        cap_p = board[d[1]][d[0]]
                        is_cap = cap_p != "."
                        if is_cap: r_captured.append(cap_p)

                        robot_success = True

                        if not config.DRY_RUN:
                            if robot.connected:
                                print(f"[AI] Robot executing move: {s}->{d}")
                                try:
                                    robot.move_piece(s[0], s[1], d[0], d[1], is_cap)
                                except Exception as e:
                                    error_str = str(e)
                                    print(f"⚠️ Robot error: {error_str}")
                                    if "112" in error_str or "MoveCart" in error_str:
                                        print("✅ Light error — counting as successful.")
                                        robot_success = True
                                    else:
                                        print("❌ [CRITICAL] Robot critical error, stopping game.")
                                        robot_success = False
                                        time.sleep(2)
                            else:
                                # --- KHÔNG CÓ ROBOT: hiển thị nước đi để người chơi tự di ---
                                piece_name = board[s[1]][s[0]]
                                cap_msg = f" ĂN {board[d[1]][d[0]]}" if is_cap else ""
                                print(f"\n{'='*50}")
                                print(f"🤖 AI đi: {piece_name} ({s[0]},{s[1]}) → ({d[0]},{d[1]}){cap_msg}")
                                print(f"👉 Hãy di quân này trên bàn thật, rồi bấm SPACE!")
                                print(f"{'='*50}\n")

                        if robot_success:
                            board, _ = xiangqi.make_temp_move(board, best)
                            last_move = best
                            turn = 'r'
                            update_fen_from_board()
                            print(f"[FEN] {current_fen}")
                            
                            if xiangqi.get_king_pos('r', board) is None:
                                handle_game_over('b')
                            else:
                                # --- Chụp T1 mới SAU khi AI đi xong ---
                                if snapshot_detector is not None:
                                    time.sleep(1.0)  # Đợi bàn cờ ổn định sau robot di chuyển
                                    if cam_monitor is not None: cam_monitor.pause()
                                    try:
                                        snapshot_detector.capture_baseline()
                                    finally:
                                        if cam_monitor is not None: cam_monitor.resume()
                                
                                if robot.connected:
                                    set_status("Your turn! Bấm SPACE sau khi đi.", color=(0, 100, 180), duration=5.0)
                                else:
                                    # Hiển thị rõ nước đi AI trên Pygame
                                    piece_moved = board[d[1]][d[0]]  # quân đã di chuyển
                                    move_txt = f"🤖 AI: ({s[0]},{s[1]})→({d[0]},{d[1]}) | Di quân rồi bấm SPACE"
                                    set_status(move_txt, color=(0, 80, 160), duration=30.0)
                                print("[GAME] Your turn...")
                        else:
                            print("⚠️ Skipping board update due to robot error.")
                    else:
                        print("[AI] No moves available -> AI Lost")
                        handle_game_over("r")

        if game_over:
            renderer.draw_game_over(winner)

        pygame.display.flip()
        clock.tick(30)

except (KeyboardInterrupt, SystemExit):
    print("\n[MAIN] ⛔ Interrupted — cleaning up...")
except Exception as e:
    print(f"\n[MAIN] ❌ Unexpected error: {e}")
    traceback.print_exc()
finally:
    # ==========================================
    # CLEANUP — LUÔN CHẠY dù crash hay tắt bình thường
    # ==========================================
    print("[CLEANUP] Đang dọn dẹp...")
    if cam_monitor is not None:
        cam_monitor.stop()
    if engine:
        engine.stop()
    if cap:
        cap.release()
    cv2.destroyAllWindows()
    if robot.connected and not config.DRY_RUN:
        robot.robot.RobotEnable(0)
    pygame.quit()
    print("[CLEANUP] ✅ Xong!")
    sys.exit()
