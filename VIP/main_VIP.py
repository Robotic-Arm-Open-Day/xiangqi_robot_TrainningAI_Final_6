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
import atexit
import signal
import subprocess
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

# IMPORT FEN UTILITIES
from fen_utils import board_array_to_fen, fen_to_board_array, INITIAL_FEN

# IMPORT AI CONTROLLER
from ai_controller import AIController

# IMPORT BOOK
try:
    import ai_book
except ImportError:
    try:
        import opening_book as ai_book
    except ImportError:
        print("❌ ERROR: Could not find book file (ai_book.py)")
        sys.exit()

from robot_VIP import FR5Robot

# ==========================================
# 0. CẤU HÌNH CHẾ ĐỘ (CONFIG)
# ==========================================
ALLOW_MOUSE_MOVE = config.DRY_RUN

_mode_label = '🛠️ DRY RUN (MOUSE & LOG)' if config.DRY_RUN else '🤖 REAL RUN (CAMERA & ROBOT)'
print(f"\n=== MODE: {_mode_label} ===")

# ==========================================
# 0.5. KILL ZOMBIE PROCESSES TỪ LẦN CHẠY TRƯỚC
# ==========================================
def _kill_zombie_processes():
    """Kill các process pikafish còn sót lại từ lần chạy trước."""
    try:
        # Tìm và kill các process pikafish zombie
        result = subprocess.run(
            ['tasklist', '/FI', 'IMAGENAME eq pikafish*', '/FO', 'CSV', '/NH'],
            capture_output=True, text=True, timeout=5
        )
        if result.stdout.strip() and 'pikafish' in result.stdout.lower():
            print("[CLEANUP] ⚠️ Phát hiện pikafish zombie process — đang kill...")
            subprocess.run(
                ['taskkill', '/F', '/IM', 'pikafish*'],
                capture_output=True, timeout=5
            )
            print("[CLEANUP] ✅ Killed zombie pikafish processes.")
            time.sleep(0.5)  # Đợi process tắt hẳn
    except Exception as e:
        print(f"[CLEANUP] ⚠️ Không thể kiểm tra zombie processes: {e}")

_kill_zombie_processes()

# (FEN functions được tách ra file fen_utils.py)

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

# --- ROLLBACK STATE (lưu trước khi bấm SPACE) ---
_pre_space_state = None   # dict chứa toàn bộ trạng thái game

# --- ROBOT & CAMERA CONFIG ---
robot = FR5Robot()

if not config.DRY_RUN:
    # --- Bước 1: Kết nối robot (lỗi ở đây mới dừng robot) ---
    try:
        robot.connect()
        print("[MAIN] ✅ Robot kết nối thành công.")
    except Exception as e:
        print(f"⚠️ [MAIN] Robot connection error: {e}")
        print("   → Tiếp tục chạy KHÔNG có robot (camera + calibrate vẫn hoạt động)")
        robot.connected = False

    # --- Bước 2: Về home (lỗi ở đây KHÔNG làm mất kết nối) ---
    if robot.connected:
        try:
            robot.go_to_home_chess()
        except Exception as e:
            print(f"⚠️ [MAIN] go_to_home_chess lỗi: {e} → bỏ qua, robot vẫn CONNECTED")
else:
    print("[MAIN] DRY_RUN: Skipping physical robot connection.")
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
            if err != 0:
                raise Exception(f"Error getting teaching point R{i} (err={err})")
            x, y = float(data[0]), float(data[1])
            print(f"  ✅ R{i}: X={x:.3f}, Y={y:.3f}")
            pts_data.append([x, y])

        src_pts_robot = np.array(pts_data, dtype=np.float32)
        M_rob = cv2.getPerspectiveTransform(dst_pts_logic, src_pts_robot)
        robot.set_perspective_matrix(M_rob)
        print("=== ROBOT CALIBRATION OK ===")
except Exception as e:
    print(f"\n{'='*60}")
    print(f"❌ [CRITICAL] Robot calibration THẤT BẠI: {e}")
    print(f"   Lý do thường gặp:")
    print(f"   1. Chưa dạy điểm R1-R4 trên bộ điều khiển robot")
    print(f"   2. Tên teaching point sai (phải đặt tên R1, R2, R3, R4)")
    print(f"   3. Mất kết nối robot khi đọc")
    print(f"")
    print(f"   ⚠️  Robot sẽ bị VÔ HIỆU HÓA để tránh di chuyển sai vị trí.")
    print(f"   Hãy dạy đúng 4 điểm rồi chạy lại:")
    print(f"     R1 = (col=0, row=0) — Xe Đen Trái  (góc trái-trên)")
    print(f"     R2 = (col=8, row=0) — Xe Đen Phải  (góc phải-trên)")
    print(f"     R3 = (col=8, row=9) — Xe Đỏ Phải   (góc phải-dưới)")
    print(f"     R4 = (col=0, row=9) — Xe Đỏ Trái   (góc trái-dưới)")
    print(f"{'='*60}\n")
    # ⚠️ QUAN TRỌNG: Vô hiệu hóa robot thay vì dùng fake matrix
    # (fake matrix cho tọa độ gần capture bin → robot bay sai vị trí!)
    robot.connected = False
    print("   Robot đã bị vô hiệu hóa. Game tiếp tục ở chế độ KHÔNG CÓ ROBOT.")

# --- KHỜI TẠO PIKAFISH ENGINE (bắt buộc) ---
engine = None
try:
    _pikafish_exe  = config.PIKAFISH_EXE
    _pikafish_nnue = config.PIKAFISH_NNUE

    if os.path.isfile(_pikafish_exe):
        engine = PikafishEngine(_pikafish_exe)
        engine.start(nnue_path=_pikafish_nnue)
        print(f"✅ Pikafish engine started! (think={config.PIKAFISH_THINK_MS}ms)")
    else:
        print(f"❌ Pikafish exe KHÔNG tìm thấy: {_pikafish_exe}")
        print("   ↳ Hãy tải Pikafish vào thư mục pikafish/ rồi chạy lại!")
        print("   ↳ https://github.com/official-pikafish/Pikafish/releases")
except Exception as e:
    print(f"⚠️ Pikafish init error: {e}")
    engine = None

# Wrap engine trong AIController
ai_ctrl = AIController(engine, config)

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

        # Đăng ký atexit handler để LUÔN release camera khi thoát,
        # kể cả khi thoát giữa lúc calibrate (trước try/finally block)
        def _release_camera_atexit():
            try:
                if cap and cap.isOpened():
                    cap.release()
                    print("[ATEXIT] ✅ Camera released.")
            except Exception:
                pass
        atexit.register(_release_camera_atexit)

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
    snapshot_detector = SnapshotDetector(PERSPECTIVE_PATH, CLASS_ID_TO_INTERNAL_NAME)
    print("[INIT] ✅ SnapshotDetector initialized (no direct camera access).")

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


# (Legacy functions get_snapshot_board / detect_move_from_snapshot đã được xóa.
#  Toàn bộ camera access giờ qua CameraMonitor.get_fresh_snapshot())

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
    if snapshot_detector is not None and cam_monitor is not None:
        time.sleep(1)  # Đợi bàn cờ ổn định
        frame, detections = cam_monitor.get_fresh_snapshot()
        snapshot_detector.capture_baseline(frame, detections)

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

def handle_rollback():
    """Rollback về trạng thái trước khi bấm SPACE lần cuối (phím Z)."""
    global board, turn, last_move, current_fen, move_number
    global r_captured, b_captured, move_history
    global _pre_space_state

    if _pre_space_state is None:
        print("[ROLLBACK] ⚠️ Không có state để rollback!")
        set_status("⚠️  Không có nước nào để rollback!", color=(180, 100, 0), duration=2.5)
        return

    print("[ROLLBACK] ↩️ Khôi phục trạng thái trước SPACE...")
    s = _pre_space_state
    board        = [row[:] for row in s["board"]]
    turn         = s["turn"]
    last_move    = s["last_move"]
    current_fen  = s["current_fen"]
    move_number  = s["move_number"]
    r_captured   = list(s["r_captured"])
    b_captured   = list(s["b_captured"])
    move_history = list(s["move_history"])

    # Khôi phục T1 baseline snapshot về trạng thái trước đó
    if snapshot_detector is not None and s["baseline_occ"] is not None:
        snapshot_detector._baseline_occ  = [row[:] for row in s["baseline_occ"]]
        snapshot_detector._baseline_time = s["baseline_time"]
        print("[ROLLBACK] 📸 T1 baseline restored.")

    _pre_space_state = None   # Xóa sau khi rollback (chỉ rollback 1 lần)
    set_status("↩️  Đã rollback! Di quân lại rồi bấm SPACE.", color=(180, 100, 0), duration=5.0)
    print(f"[ROLLBACK] ✅ Done. FEN: {current_fen}")

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
    if snapshot_detector is None or cam_monitor is None:
        set_status("❌  Snapshot detector chưa khởi tạo!", color=(180, 0, 0))
        return
    
    # Lấy snapshot mới từ CameraMonitor (không cần pause/resume)
    frame, detections = cam_monitor.get_fresh_snapshot()
    
    if not snapshot_detector.has_baseline():
        print("[SPACE] ⚠️ Chưa có T1 baseline — chụp ngay...")
        if snapshot_detector.capture_baseline(frame, detections):
            set_status("📸 Đã chụp T1 baseline. Đi quân rồi bấm SPACE lại!", color=(0, 100, 180), duration=5.0)
        else:
            set_status("❌ Không chụp được baseline!", color=(180, 0, 0))
        return
    
    # Chụp T2 và so sánh với T1
    src, dst, piece = snapshot_detector.detect_move(frame, detections, board)
    
    if src is None or dst is None:
        set_status("❌  Không phát hiện nước đi! Bấm SPACE lại.", color=(180, 0, 0))
        print("[SPACE] ❌ No valid move detected from T1/T2 comparison")
        return
    
    print(f"[SPACE] 👀 Phát hiện: {piece} {src}->{dst}")

    if xiangqi.is_valid_move(src, dst, board, "r"):
        # Lưu state TRƯỚC KHI thực hiện nước đi (để rollback nếu cần)
        global _pre_space_state
        _pre_space_state = {
            "board":        [row[:] for row in board],
            "turn":         turn,
            "last_move":    last_move,
            "current_fen":  current_fen,
            "move_number":  move_number,
            "r_captured":   list(r_captured),
            "b_captured":   list(b_captured),
            "move_history": list(move_history),
            "baseline_occ":  [row[:] for row in snapshot_detector._baseline_occ] if snapshot_detector and snapshot_detector._baseline_occ else None,
            "baseline_time": snapshot_detector._baseline_time if snapshot_detector else None,
        }
        print("[SPACE] 💾 State saved for rollback (Z to undo).")
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
if snapshot_detector is not None and cam_monitor is not None:
    print("[INIT] 📸 Chụp T1 baseline ban đầu...")
    time.sleep(1)  # Đợi camera ổn định
    frame, detections = cam_monitor.get_fresh_snapshot()
    snapshot_detector.capture_baseline(frame, detections)

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

                # === Z KEY: Rollback về trước khi bấm SPACE ===
                elif event.key == pygame.K_z and not ALLOW_MOUSE_MOVE:
                    handle_rollback()

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
                    ai_result = ai_ctrl.pick_move(board_snapshot, color="b")

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
                                if snapshot_detector is not None and cam_monitor is not None:
                                    time.sleep(1.0)  # Đợi bàn cờ ổn định sau robot di chuyển
                                    frame, detections = cam_monitor.get_fresh_snapshot()
                                    snapshot_detector.capture_baseline(frame, detections)
                                
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
    
    # 1. Dừng CameraMonitor (sẽ dừng thread + release camera)
    try:
        if cam_monitor is not None:
            cam_monitor.stop()
    except Exception as e:
        print(f"[CLEANUP] ⚠️ CameraMonitor stop error: {e}")
    
    # 2. Dừng Pikafish engine subprocess
    try:
        if engine:
            engine.stop()
    except Exception as e:
        print(f"[CLEANUP] ⚠️ Pikafish stop error: {e}")
    
    # 3. Release camera (phòng trường hợp cam_monitor.stop() không release)
    try:
        if cap and cap.isOpened():
            cap.release()
            print("[CLEANUP] ✅ Camera released (fallback).")
    except Exception as e:
        print(f"[CLEANUP] ⚠️ Camera release error: {e}")
    
    # 4. Dọn dẹp OpenCV + Robot + Pygame
    try:
        cv2.destroyAllWindows()
    except Exception:
        pass
    
    try:
        if robot.connected and not config.DRY_RUN:
            robot.robot.RobotEnable(0)
    except Exception as e:
        print(f"[CLEANUP] ⚠️ Robot disable error: {e}")
    
    try:
        pygame.quit()
    except Exception:
        pass
    
    print("[CLEANUP] ✅ Xong!")
    
    # 5. Force thoát — đảm bảo KHÔNG CÒN thread/process nào chạy ngầm
    os._exit(0)
