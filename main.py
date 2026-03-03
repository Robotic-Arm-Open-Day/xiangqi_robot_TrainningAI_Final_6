# ===================================================================================
# === FILE: main.py (FINAL VERSION: STABLE & ROBUST) ===
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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pygame
from ultralytics import YOLO

import config  # Đảm bảo file config.py có biến DRY_RUN
import xiangqi
import ai
import sound_player

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
# 1. KHỞI TẠO
# ==========================================
pygame.init()
pygame.font.init()

SCREEN_WIDTH = 800
SCREEN_HEIGHT = 600
SQUARE_SIZE = 40
NUM_COLS = xiangqi.NUM_COLS
NUM_ROWS = xiangqi.NUM_ROWS
BOARD_WIDTH = (NUM_COLS - 1) * SQUARE_SIZE
START_X = (SCREEN_WIDTH - BOARD_WIDTH) / 2
START_Y = (SCREEN_HEIGHT - ((NUM_ROWS - 1) * SQUARE_SIZE)) / 2 - 20
LINE_COLOR = (0, 0, 0)
BOARD_COLOR = (252, 230, 201)
PIECE_RADIUS = SQUARE_SIZE // 2 - 4
PIECE_FONT = pygame.font.SysFont("simsun", 20, bold=True)
GAME_FONT = pygame.font.SysFont("times new roman", 36, bold=True)
UI_FONT = pygame.font.SysFont("arial", 16, bold=True)

BTN_SURRENDER_RECT = pygame.Rect(SCREEN_WIDTH / 2 - 150, SCREEN_HEIGHT - 60, 120, 40)
BTN_NEW_GAME_RECT = pygame.Rect(SCREEN_WIDTH / 2 + 30, SCREEN_HEIGHT - 60, 120, 40)
BTN_COLOR = (200, 50, 50)
BTN_NEW_GAME_COLOR = (50, 150, 200)

PIECE_DISPLAY_NAMES = {
    "r_K": "帥", "r_A": "仕", "r_E": "相", "r_R": "俥", "r_N": "傌", "r_C": "炮", "r_P": "兵",
    "b_K": "將", "b_A": "士", "b_E": "象", "b_R": "車", "b_N": "馬", "b_C": "砲", "b_P": "卒",
}

screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
pygame.display.set_caption(
    f"Xiangqi Robot - Mode: {'MOUSE (DRY)' if ALLOW_MOUSE_MOVE else 'CAMERA (REAL)'}"
)

# ==========================================
# 2. TRẠNG THÁI GAME
# ==========================================
board = xiangqi.get_board()
turn = "r"
game_over = False
winner = None
last_move = None
selected_pos = None
r_captured = []
b_captured = []
move_history = []

# --- UI FEEDBACK ---
status_message = ""          # text shown on screen
status_color   = (0, 0, 0)   # colour of that text
status_expiry  = 0.0         # time.time() after which it disappears
invalid_flash_pos = None     # (col, row) to flash red on invalid move
invalid_flash_expiry = 0.0

# --- AI THREAD STATE ---
ai_thread        = None       # background thread running pick_best_move
ai_result        = None       # move returned by AI thread
ai_thinking      = False      # True while thread is running
ai_think_start   = 0.0        # time the thread was launched (for dot animation)

# --- ROBOT & CAMERA CONFIG ---
robot = FR5Robot()

# Chỉ kết nối Robot nếu KHÔNG phải DRY_RUN
try:
    if not config.DRY_RUN:
        robot.connect()
        robot.go_to_home_chess()   # ← go to HOMECHESS on startup
    else:
        print("[MAIN] DRY_RUN: Skipping physical robot connection.")
        robot.connected = False  # Giả lập trạng thái
except Exception as e:
    print(f"[MAIN] Robot connection error: {e}")
    if not config.DRY_RUN:
        sys.exit()

# --- HIỆU CHỈNH ROBOT ---
print("\n--- ROBOT CALIBRATION ---")
dst_pts_logic = np.array([[0, 0], [8, 0], [8, 9], [0, 9]], dtype=np.float32)
try:
    if config.DRY_RUN:
        # Fake matrix cho chế độ test chuột
        src_pts_fake = np.array([[200, -100], [520, -100], [520, 260], [200, 260]], dtype=np.float32)
        robot.set_perspective_matrix(cv2.getPerspectiveTransform(dst_pts_logic, src_pts_fake))
    else:
        print("Reading coordinates from robot...")
        # Lấy điểm teaching (Giả sử robot đã được dạy 4 điểm R1-R4 tương ứng 4 góc bàn cờ)
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
    print(f"[MAIN] Robot calibration error: {e}")
    if not config.DRY_RUN:
        sys.exit()

# --- LOAD MODEL YOLO ---
model = None
cap = None
if not config.DRY_RUN:
    # Use path relative to this script file
    MODEL_PATH = str(Path(__file__).parent / "models_chinesechess1" / "content" / "runs" / "detect" / "train" / "weights" / "best.pt")
    try:
        model = YOLO(MODEL_PATH)
        print(f"✅ Model loaded: {MODEL_PATH}")
    except Exception as e:
        print(f"⚠️ Warning: Could not load model: {e}")
        # sys.exit() # Uncomment if model is required

    # Try camera indices from config, then fallback to 0, 1, 2
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
        print("❌ Lỗi: Không mở được Camera! Kiểm tra lại kết nối webcam.")
        sys.exit() # Added sys.exit() for consistency with other error handling
    else:
        # Ép khung hình về 1280x720 chuẩn
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        actual_w = cap.get(cv2.CAP_PROP_FRAME_WIDTH)
        actual_h = cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
        print(f"📷 Actual camera resolution set to: {actual_w} x {actual_h}")

PERSPECTIVE_PATH = Path(__file__).parent / "perspective.npy"
CLASS_ID_TO_INTERNAL_NAME = {
    0: "b_A", 1: "b_C", 2: "b_R", 3: "b_E", 4: "b_K", 5: "b_N", 6: "b_P",
    8: "r_A", 9: "r_C", 10: "r_R", 11: "r_E", 12: "r_K", 13: "r_N", 14: "r_P",
}

# ==========================================
# 4. HÀM HỖ TRỢ
# ==========================================
def grid_to_pixel(col, row):
    return int(START_X + col * SQUARE_SIZE), int(START_Y + row * SQUARE_SIZE)

def pixel_to_grid(px, py):
    col = int(round((px - START_X) / SQUARE_SIZE))
    row = int(round((py - START_Y) / SQUARE_SIZE))
    return col, row

def draw_ui():
    screen.fill(BOARD_COLOR)
    if not game_over:
        pygame.draw.rect(screen, BTN_COLOR, BTN_SURRENDER_RECT, border_radius=8)
        txt = UI_FONT.render("SURRENDER", True, (255, 255, 255))
        screen.blit(txt, txt.get_rect(center=BTN_SURRENDER_RECT.center))

        pygame.draw.rect(screen, BTN_NEW_GAME_COLOR, BTN_NEW_GAME_RECT, border_radius=8)
        txt_new = UI_FONT.render("NEW GAME", True, (255, 255, 255))
        screen.blit(txt_new, txt_new.get_rect(center=BTN_NEW_GAME_RECT.center))

        mode_str = "MOUSE (DRY RUN)" if ALLOW_MOUSE_MOVE else "CAMERA AI"
        mode_txt = UI_FONT.render(f"MODE: {mode_str}", True, (0, 0, 255))
        screen.blit(mode_txt, (10, 10))
    else:
        # Show New Game button when game is over
        pygame.draw.rect(screen, BTN_NEW_GAME_COLOR, BTN_NEW_GAME_RECT, border_radius=8)
        txt_new = UI_FONT.render("NEW GAME", True, (255, 255, 255))
        screen.blit(txt_new, txt_new.get_rect(center=BTN_NEW_GAME_RECT.center))

    # Vẽ bàn cờ
    for r in range(NUM_ROWS):
        pygame.draw.line(screen, LINE_COLOR, grid_to_pixel(0, r), grid_to_pixel(NUM_COLS - 1, r), 1)
    for c in range(NUM_COLS):
        if c in [0, NUM_COLS - 1]:
            pygame.draw.line(screen, LINE_COLOR, grid_to_pixel(c, 0), grid_to_pixel(c, NUM_ROWS - 1), 1)
        else:
            pygame.draw.line(screen, LINE_COLOR, grid_to_pixel(c, 0), grid_to_pixel(c, 4), 1)
            pygame.draw.line(screen, LINE_COLOR, grid_to_pixel(c, 5), grid_to_pixel(c, 9), 1)
    # Cung tướng
    pygame.draw.line(screen, LINE_COLOR, grid_to_pixel(3, 0), grid_to_pixel(5, 2), 1)
    pygame.draw.line(screen, LINE_COLOR, grid_to_pixel(5, 0), grid_to_pixel(5, 2), 1)
    pygame.draw.line(screen, LINE_COLOR, grid_to_pixel(3, 7), grid_to_pixel(5, 9), 1)
    pygame.draw.line(screen, LINE_COLOR, grid_to_pixel(5, 7), grid_to_pixel(3, 9), 1)

    # --- STATUS MESSAGE (timed, centred at top) ---
    if status_message and time.time() < status_expiry:
        msg_surf = UI_FONT.render(status_message, True, (255, 255, 255))
        padding  = 8
        bg_rect  = msg_surf.get_rect(centerx=SCREEN_WIDTH // 2, top=32)
        bg_rect.inflate_ip(padding * 2, padding * 2)
        bg_surf  = pygame.Surface((bg_rect.width, bg_rect.height), pygame.SRCALPHA)
        bg_surf.fill((*status_color, 200))
        screen.blit(bg_surf, bg_rect.topleft)
        screen.blit(msg_surf, msg_surf.get_rect(center=bg_rect.center))

    # --- AI THINKING BANNER ---
    if ai_thinking:
        dots = "." * (int(time.time() - ai_think_start) % 4)
        elapsed = time.time() - ai_think_start
        think_msg = f"🤖  AI is thinking{dots}  ({elapsed:.1f}s)"
        think_surf = UI_FONT.render(think_msg, True, (255, 255, 255))
        padding = 10
        bg_rect = think_surf.get_rect(centerx=SCREEN_WIDTH // 2, top=8)
        bg_rect.inflate_ip(padding * 2, padding * 2)
        bg_surf = pygame.Surface((bg_rect.width, bg_rect.height), pygame.SRCALPHA)
        bg_surf.fill((20, 100, 20, 210))
        screen.blit(bg_surf, bg_rect.topleft)
        screen.blit(think_surf, think_surf.get_rect(center=bg_rect.center))

def draw_pieces():
    for r in range(NUM_ROWS):
        for c in range(NUM_COLS):
            name = board[r][c]
            if name == ".": continue
            cx, cy = grid_to_pixel(c, r)
            color = (220, 20, 60) if name.startswith("r") else (0, 0, 0)
            pygame.draw.circle(screen, (255, 255, 255), (cx, cy), PIECE_RADIUS)
            pygame.draw.circle(screen, color, (cx, cy), PIECE_RADIUS, 2)
            text_surf = PIECE_FONT.render(PIECE_DISPLAY_NAMES.get(name, "?"), True, color)
            screen.blit(text_surf, text_surf.get_rect(center=(cx, cy)))

def draw_highlight():
    if last_move:
        (s, d) = last_move
        pygame.draw.circle(screen, (0, 255, 0, 100), grid_to_pixel(s[0], s[1]), PIECE_RADIUS + 2, 2)
        pygame.draw.circle(screen, (0, 255, 0, 150), grid_to_pixel(d[0], d[1]), PIECE_RADIUS + 2, 2)
    if selected_pos:
        c, r = selected_pos
        cx, cy = grid_to_pixel(c, r)
        pygame.draw.circle(screen, (0, 0, 255), (cx, cy), PIECE_RADIUS + 4, 2)
    # --- INVALID MOVE FLASH (red ring on target square) ---
    if invalid_flash_pos and time.time() < invalid_flash_expiry:
        fc, fr = invalid_flash_pos
        fx, fy = grid_to_pixel(fc, fr)
        pygame.draw.circle(screen, (220, 0, 0), (fx, fy), PIECE_RADIUS + 6, 4)

def calibrate_perspective_camera(cap, save_path):
    if config.DRY_RUN: return

    # --- Thread-based capture queue (same as calibrate_tool.py) ---
    import queue as _queue
    cal_q = _queue.Queue(maxsize=2)
    cal_stop = [False]
    def _cal_capture():
        while not cal_stop[0]:
            ret, frm = cap.read()
            if ret:
                if not cal_q.empty():
                    try: cal_q.get_nowait()
                    except _queue.Empty: pass
                cal_q.put(frm)
            time.sleep(0.005)
    import threading as _threading
    _threading.Thread(target=_cal_capture, daemon=True).start()
    time.sleep(0.5)  # Wait for camera to warm up

    points = []
    def mouse_callback(event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN and len(points) < 4:
            points.append((x, y))

    window = "CALIBRATE"
    cv2.namedWindow(window)
    cv2.setMouseCallback(window, mouse_callback)

    print("\n=== HƯỚNG DẪN CLICK (QUAN TRỌNG) ===")
    print("👉 Click lần lượt 4 góc bàn cờ thật trên màn hình:")
    print("   1️⃣  Góc Xe Đen (Trái)")
    print("   2️⃣  Góc Xe Đen (Phải)")
    print("   3️⃣  Góc Xe Đỏ (Phải)")
    print("   4️⃣  Góc Xe Đỏ (Trái)")
    print("---------------------------------------------")
    print("⌨️  Phím tắt: 'R'=Làm lại | 'S'=Lưu file | 'Q'=Thoát")

    M = None
    while True:
        try:
            frame = cal_q.get(timeout=0.1)
        except _queue.Empty:
            continue

        display = frame.copy()  # Camera is BGR; cv2.imshow expects BGR — display as-is

        # Draw clicked points
        for i, p in enumerate(points):
            cv2.circle(display, p, 5, (0, 0, 255), -1)
            cv2.putText(display, str(i + 1), (p[0] + 10, p[1]), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)

        # When 4 points are set, compute matrix and draw yellow grid overlay
        if len(points) == 4:
            src = np.array(points, dtype=np.float32)
            dst = np.array([
                [0, 0],  # 1. Đen Trái
                [8, 0],  # 2. Đen Phải
                [8, 9],  # 3. Đỏ Phải
                [0, 9],  # 4. Đỏ Trái
            ], dtype=np.float32)
            M = cv2.getPerspectiveTransform(src, dst)
            try:
                inv_M = np.linalg.inv(M)
                # Draw 10 horizontal rows
                for r in range(10):
                    p1 = cv2.perspectiveTransform(np.array([[[0, r]]], dtype=np.float32), inv_M)[0][0]
                    p2 = cv2.perspectiveTransform(np.array([[[8, r]]], dtype=np.float32), inv_M)[0][0]
                    cv2.line(display, (int(p1[0]), int(p1[1])), (int(p2[0]), int(p2[1])), (0, 255, 255), 1)
                # Draw 9 vertical columns
                for c in range(9):
                    p1 = cv2.perspectiveTransform(np.array([[[c, 0]]], dtype=np.float32), inv_M)[0][0]
                    p2 = cv2.perspectiveTransform(np.array([[[c, 9]]], dtype=np.float32), inv_M)[0][0]
                    cv2.line(display, (int(p1[0]), int(p1[1])), (int(p2[0]), int(p2[1])), (0, 255, 255), 1)
                cv2.putText(display, "OK? Bam 'S' de Luu", (20, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
            except:
                pass

        cv2.imshow(window, display)

        key = cv2.waitKey(1)
        if key == ord('q'):
            break
        elif key == ord('r'):  # Reset
            points.clear()
            M = None
            print("🔄 Đã xóa điểm, hãy click lại.")
        elif key == ord('s') and M is not None:  # Save
            np.save(save_path, M)
            print(f"✅ ĐÃ LƯU THÀNH CÔNG: {save_path}")
            break

    cal_stop[0] = True
    cv2.destroyWindow(window)

# Hàm này dùng để chuyển đổi tọa độ YOLO sang ô cờ
def detections_to_grid_occupancy(detections, M, original_w=1920, original_h=1080, model_input_w=640):
    grid = [["." for _ in range(NUM_COLS)] for _ in range(NUM_ROWS)]
    if M is None: return grid
    
    # Tính tỉ lệ scale (Nếu bạn resize ảnh trước khi đưa vào model)
    # Tuy nhiên, thư viện Ultralytics YOLO thường tự handle việc này nếu bạn truyền ảnh gốc vào model.predict
    # ĐỂ AN TOÀN NHẤT: Ta lấy trực tiếp tọa độ trên ảnh gốc.
    
    for cls_id, (x1, y1, x2, y2) in detections:
        name = CLASS_ID_TO_INTERNAL_NAME.get(cls_id)
        if not name: continue
        
        # --- [MỚI - ĐÚNG] Lấy gần chân quân cờ (Quan trọng) ---
        cx = (x1 + x2) / 2
        
        # Mẹo: Lấy 85% chiều cao hộp (gần đáy) thay vì 50% (ở giữa)
        # Điều này giúp loại bỏ lỗi nhìn nghiêng bị nhảy hàng
        cy = y1 + (y2 - y1) * 0.85
        
        # --- MẸO FIX LỆCH DO GÓC NGHIÊNG (PARALLAX FIX) ---
        # Nếu camera nhìn chéo, chân quân cờ thường thấp hơn tâm hộp một chút.
        # Bạn có thể cộng thêm vào Y một chút để nhắm vào chân quân cờ.
        # cy = cy + 10  (Thử bỏ comment dòng này và chỉnh số 10 nếu gắp toàn bị hụt phía trên)
        
        try:
            # Biến đổi Perspective (Dùng ma trận M đã lưu)
            dst = cv2.perspectiveTransform(np.array([[[float(cx), float(cy)]]], dtype=np.float32), M)[0][0]
            
            # Làm tròn để ra cột, hàng
            c, r = int(round(dst[0])), int(round(dst[1]))
            
            if 0 <= c < NUM_COLS and 0 <= r < NUM_ROWS:
                grid[r][c] = name
        except: pass
    return grid

PIECE_LETTER_TO_SOUND = {
    "N": "Ma", "C": "Phao", "R": "Xe", "P": "Tot", "A": "Si", "E": "Tuong", "K": None,
}

def piece_str_to_sound(piece_str):
    if not piece_str or piece_str == ".": return None
    try: return PIECE_LETTER_TO_SOUND.get(piece_str.split("_")[-1])
    except: return None

def reset_game():
    global board, turn, game_over, winner, last_move, selected_pos, r_captured, b_captured, move_history, last_sync_time
    global status_message, status_expiry, invalid_flash_pos, invalid_flash_expiry
    global ai_thread, ai_result, ai_thinking, ai_think_start
    board = xiangqi.get_board()
    turn = "r"
    game_over = False
    winner = None
    last_move = None
    selected_pos = None
    r_captured = []
    b_captured = []
    move_history = []
    last_sync_time = time.time()
    status_message = ""
    status_expiry  = 0.0
    invalid_flash_pos = None
    invalid_flash_expiry = 0.0
    ai_thread = None
    ai_result = None
    ai_thinking = False
    ai_think_start = 0.0
    print("[GAME] 🔄 New game started!")

def set_status(msg, color=(200, 0, 0), duration=2.5):
    """Show a timed message on screen."""
    global status_message, status_color, status_expiry
    status_message = msg
    status_color   = color
    status_expiry  = time.time() + duration

def set_invalid_flash(col, row, duration=0.6):
    """Flash the target square red briefly."""
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
    global board, last_move, turn
    print(f"[HUMAN] ✅ Moved: {p_name} {src}->{dst}")
    set_status("✅  Move accepted — AI thinking...", color=(0, 120, 0), duration=5.0)
    key = ai_book.board_to_key(board)
    move_history.append({"turn": "r", "key": key, "src": src, "dst": dst})
    
    cap_p = board[dst[1]][dst[0]]
    if cap_p != ".": b_captured.append(cap_p)
    
    board, _ = xiangqi.make_temp_move(board, (src, dst))
    last_move = (src, dst)
    


    if xiangqi.get_king_pos("b", board) is None: handle_game_over("r")
    else: turn = "b"

# ==========================================
# 5. SNAPSHOT MOVE DETECTION
# ==========================================

def get_snapshot_board():
    """Takes a single snapshot, runs YOLO, and returns a 10x9 board of detected piece names (or '.')."""
    if cap is None or model is None:
        return None
        
    print("[CAM] 📸 Đang chụp Snapshot bàn cờ...")
    # Clear the buffer to get the freshest frame
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
            
    # View port log
    for (cls, (x1, y1, x2, y2)) in detections:
        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
    cv2.imshow("Camera Monitor", frame)
    cv2.waitKey(1)
            
    M_cam = np.load(str(PERSPECTIVE_PATH)) if os.path.exists(str(PERSPECTIVE_PATH)) else None
    if M_cam is None: return None
    
    cam_grid = detections_to_grid_occupancy(detections, M_cam)
    return cam_grid

def compare_snapshots(old_b, new_b):
    """Compares two 10x9 virtual board states and returns (src, dst, piece) of the moved red piece, or (None, None, None)."""
    missing_reds = []
    new_reds = []
    
    for r in range(NUM_ROWS):
        for c in range(NUM_COLS):
            old_p = old_b[r][c]
            new_p = new_b[r][c]
            if old_p != new_p:
                if old_p.startswith("r") and (not new_p.startswith("r")):
                    missing_reds.append((c, r, old_p))
                elif (not old_p.startswith("r")) and new_p.startswith("r"):
                    new_reds.append((c, r, new_p))
                    
    # Basic logic: 1 piece missing, 1 piece appeared -> It's a move
    if len(missing_reds) == 1 and len(new_reds) == 1:
        src = (missing_reds[0][0], missing_reds[0][1])
        dst = (new_reds[0][0], new_reds[0][1])
        piece = missing_reds[0][2]
        # Ignore piece type mismatches if YOLO misclassified the destination box; rely on origin piece type.
        return src, dst, piece
    return None, None, None

baseline_snapshot = None  # Stores the T1 snapshot board
waiting_for_snapshot = False # Flag to trigger T2 snapshot interval

# ==========================================
# 5. VÒNG LẶP CHÍNH
# ==========================================
running = True
last_sync_time = time.time()
SYNC_INTERVAL = 3.0   # seconds between board-state sync checks
clock = pygame.time.Clock()

while running:
    draw_ui()
    draw_pieces()
    draw_highlight()

    for event in pygame.event.get():
        if event.type == pygame.QUIT: running = False
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_v and not config.DRY_RUN:
                calibrate_perspective_camera(cap, str(PERSPECTIVE_PATH))

        if event.type == pygame.MOUSEBUTTONDOWN:
            mx, my = event.pos
            if BTN_SURRENDER_RECT.collidepoint(mx, my) and not game_over:
                print("[GAME] YOU SURRENDER!")
                handle_game_over("b")
                continue

            if BTN_NEW_GAME_RECT.collidepoint(mx, my):
                reset_game()
                continue

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

    # --- LOGIC CAMERA (SNAPSHOT TĨNH) ---
    if not ALLOW_MOUSE_MOVE and cap is not None and not game_over:
        if cv2.waitKey(1) == ord("q"): running = False

        if turn == "r":
            # 1. Chụp ảnh cơ sở (T1) khi mới bắt đầu lượt
            if baseline_snapshot is None:
                baseline_snapshot = get_snapshot_board()
                if baseline_snapshot:
                    print("[SYNC] 🟢 Đã lưu Snapshot cơ sở (T1). Xin mời người chơi đi cờ...")
                    last_sync_time = time.time()
                    waiting_for_snapshot = False

            # 2. Định kỳ quét tìm sự thay đổi
            if baseline_snapshot is not None:
                # Nếu đang chờ T2 thì đợi 1s, nếu đang rảnh thì cứ 1.5s check 1 lần
                delay_required = 1.0 if waiting_for_snapshot else 1.5
                
                if time.time() - last_sync_time > delay_required:
                    last_sync_time = time.time()
                    current_snap = get_snapshot_board()
                    if current_snap:
                        src, dst, piece = compare_snapshots(baseline_snapshot, current_snap)
                        if src and dst:
                            if not waiting_for_snapshot:
                                print(f"👀 [CAMERA] Bàn cờ thay đổi ({src}->{dst}). Đợi 1s cho ổn định ảnh (T2)...")
                                waiting_for_snapshot = True
                            else:
                                # Đây chính là T2!
                                if xiangqi.is_valid_move(src, dst, board, "r"):
                                    print(f"[HUMAN] ✅ Chốt nước đi tĩnh: {piece} {src}->{dst}")
                                    process_human_move(src, dst, piece)
                                    baseline_snapshot = None # Chốt xong thì xóa ảnh cũ
                                    waiting_for_snapshot = False
                                else:
                                    print(f"[IGN] ⚠️ Nước đi không hợp lệ {src}->{dst}. Hủy chốt.")
                                    waiting_for_snapshot = False
                        else:
                            waiting_for_snapshot = False
                            
        elif turn == "b":
            # Đang lượt AI, phải xóa ảnh T1 để lượt người sau chụp lại T1 mới
            baseline_snapshot = None
            waiting_for_snapshot = False

    # ==========================================
    # --- AI TURN (THREADED — NON-BLOCKING UI) ---
    # ==========================================
    if turn == "b" and not game_over:

        # --- STEP 1: SPAWN AI THREAD (only once per turn) ---
        if not ai_thinking and ai_thread is None:

            # Capture board snapshot for the thread
            board_snapshot = [row[:] for row in board]
            ai_result = None
            ai_thinking = True
            ai_think_start = time.time()

            def _ai_worker():
                global ai_result
                try:
                    ai_result = ai.pick_best_move(board_snapshot, "b")
                except Exception as e:
                    print(f"[AI Thread] Error: {e}")
                    traceback.print_exc()
                    ai_result = None

            ai_thread = threading.Thread(target=_ai_worker, daemon=True)
            ai_thread.start()
            print("[AI] 🧵 Thinking thread started...")

        # --- STEP 2: WHILE THINKING — keep UI alive ---
        elif ai_thinking and ai_thread is not None:
            if not ai_thread.is_alive():
                # Thread finished — process result
                ai_thinking = False
                ai_thread = None
                best = ai_result
                ai_result = None

                # --- Loop detection: random move if stuck ---
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
                                print(f"👉 Alternative move: {s}->{d}")

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
                        print(f"[AI] Robot executing move: {s}->{d}")
                        if robot.connected:
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

                    if robot_success:
                        board, _ = xiangqi.make_temp_move(board, best)
                        last_move = best
                        if xiangqi.get_king_pos('r', board) is None:
                            handle_game_over('b')
                        else:
                            turn = 'r'
                            set_status("Your turn!", color=(0, 100, 180), duration=3.0)
                            print("[GAME] Your turn...")
                            last_sync_time = time.time() + 4.0
                    else:
                        print("⚠️ Skipping board update due to robot error.")
                else:
                    print("[AI] No moves available -> AI Lost")
                    handle_game_over("r")

    if game_over:
        msg = "AI WINS (SAVED)" if winner == "b" else "YOU WIN (NOT SAVED)"
        color = (0, 255, 0) if winner == "b" else (255, 0, 0)
        txt = GAME_FONT.render(msg, True, color)
        screen.blit(txt, txt.get_rect(center=(SCREEN_WIDTH / 2, SCREEN_HEIGHT / 2)))

    pygame.display.flip()
    clock.tick(30)

if cap: cap.release()
cv2.destroyAllWindows()
if robot.connected and not config.DRY_RUN: robot.robot.RobotEnable(0)
pygame.quit()
sys.exit()