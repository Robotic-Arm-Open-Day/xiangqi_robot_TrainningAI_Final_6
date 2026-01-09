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

# --- ROBOT & CAMERA CONFIG ---
robot = FR5Robot()

# Chỉ kết nối Robot nếu KHÔNG phải DRY_RUN
try:
    if not config.DRY_RUN:
        robot.connect()
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
    # LƯU Ý: KIỂM TRA LẠI ĐƯỜNG DẪN MODEL TRÊN MÁY BẠN
    MODEL_PATH = r"D:\xiangqi_robot_TrainningAI_Final_6\models_chinesechess1\content\runs\detect\train\weights\best.pt"
    try:
        model = YOLO(MODEL_PATH)
    except:
        print("⚠️ Warning: Could not load model. Check the path!")
        # sys.exit() # Uncomment if model is required

    cap = cv2.VideoCapture(int(os.environ.get("VIDEO_INDEX", "1")), cv2.CAP_DSHOW)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

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

def calibrate_perspective_camera(cap, save_path):
    if config.DRY_RUN: return 
    pts = []
    window = "CALIBRATE"
    cv2.namedWindow(window)
    cv2.setMouseCallback(window, lambda e, x, y, f, p: pts.append((x, y)) if e == 1 and len(pts) < 4 else None)
    print("⚠️ Click 4 corners: TopLeft -> TopRight -> BotRight -> BotLeft")
    while True:
        ret, frame = cap.read()
        if not ret: break
        for i, p in enumerate(pts):
            cv2.circle(frame, p, 6, (0, 255, 0), -1)
            cv2.putText(frame, str(i + 1), p, 1, 2, (0, 255, 0))
        cv2.imshow(window, frame)
        if cv2.waitKey(1) == 27 or len(pts) == 4: break
    if len(pts) == 4:
        dst = np.array([[0, 0], [8, 0], [8, 9], [0, 9]], dtype=np.float32)
        M = cv2.getPerspectiveTransform(np.array(pts, dtype=np.float32), dst)
        np.save(save_path, M)
        print(f"Saved calibration file: {save_path}")
    cv2.destroyWindow(window)

# Hàm này dùng để chuyển đổi tọa độ YOLO sang ô cờ
def detections_to_grid_occupancy(detections, M, original_w=1280, original_h=720, model_input_w=640):
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
    print("[GAME] 🔄 New game started!")

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
    key = ai_book.board_to_key(board)
    move_history.append({"turn": "r", "key": key, "src": src, "dst": dst})
    
    cap_p = board[dst[1]][dst[0]]
    if cap_p != ".": b_captured.append(cap_p)
    
    board, _ = xiangqi.make_temp_move(board, (src, dst))
    last_move = (src, dst)
    
    attacker_sound = piece_str_to_sound(p_name)
    if cap_p != ".":
        target_sound = piece_str_to_sound(cap_p)
        if attacker_sound and target_sound:
            sound_player.play_capture_sound(attacker_sound, target_sound)
    else:
        if attacker_sound: sound_player.play_move_sound(attacker_sound)

    if xiangqi.get_king_pos("b", board) is None: handle_game_over("r")
    else: turn = "b"

# ==========================================
# 5. VÒNG LẶP CHÍNH
# ==========================================
running = True
last_sync_time = time.time()
SYNC_INTERVAL = 1.5
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

    # --- LOGIC CAMERA ---
    if not ALLOW_MOUSE_MOVE and cap is not None:
        ret, frame = cap.read()
        detections = []
        if ret:
            try:
                results = model.predict(frame, conf=0.35, iou=0.45, verbose=False)
                for box in results[0].boxes:
                    cls = int(box.cls[0])
                    if cls in CLASS_ID_TO_INTERNAL_NAME:
                        x1, y1, x2, y2 = map(int, box.xyxy[0])
                        detections.append((cls, (x1, y1, x2, y2)))
                        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                
                # Debug Grid
                if os.path.exists(str(PERSPECTIVE_PATH)):
                    M_debug = np.load(str(PERSPECTIVE_PATH))
                    M_inv = np.linalg.inv(M_debug)
                    for r_debug in range(NUM_ROWS):
                        for c_debug in range(NUM_COLS):
                            pt_grid = np.array([[[float(c_debug), float(r_debug)]]], dtype=np.float32)
                            pt_pixel = cv2.perspectiveTransform(pt_grid, M_inv)[0][0]
                            cv2.circle(frame, (int(pt_pixel[0]), int(pt_pixel[1])), 3, (0, 0, 255), -1)
                cv2.imshow("Camera Monitor", frame)
            except: pass
        if cv2.waitKey(1) == ord("q"): running = False

        if time.time() - last_sync_time > SYNC_INTERVAL and turn == "r" and not game_over:
            last_sync_time = time.time()
            M_cam = np.load(str(PERSPECTIVE_PATH)) if os.path.exists(str(PERSPECTIVE_PATH)) else None
            if M_cam is not None:
                cam_grid = detections_to_grid_occupancy(detections, M_cam)
                disappeared = []; appeared = []
                for r in range(NUM_ROWS):
                    for c in range(NUM_COLS):
                        if board[r][c] != "." and (cam_grid[r][c] == "." or cam_grid[r][c] != board[r][c]):
                            disappeared.append({"pos": (c, r), "piece": board[r][c]})
                        if cam_grid[r][c] != "." and cam_grid[r][c] != board[r][c]:
                            appeared.append({"pos": (c, r), "piece": cam_grid[r][c]})

                valid_move = None
                for app in appeared:
                    for dis in disappeared:
                        if app["piece"].startswith("r"):
                            if dis["piece"] == app["piece"] and dis["pos"] != app["pos"]:
                                valid_move = (dis["pos"], app["pos"], app["piece"])
                                break
                    if valid_move: break

                if valid_move:
                    src, dst, p_name = valid_move
                    if xiangqi.is_valid_move(src, dst, board, "r"):
                        process_human_move(src, dst, p_name)
                    else: print(f"[IGN] ⚠️ Detected {src}->{dst} but INVALID MOVE")

    # ==========================================
    # --- AI TURN (ĐÃ SỬA LỖI LẶP) ---
    # ==========================================
    # ==========================================
    # --- AI TURN (ĐÃ SỬA LỖI: CHECK AN TOÀN) ---
    # ==========================================
    if turn == "b" and not game_over:
        
        # --- [NEW] CHỐT CHẶN AN TOÀN: KIỂM TRA LẠI CAMERA TRƯỚC KHI NGHĨ ---
        # Mục đích: Đảm bảo AI không bao giờ đánh dựa trên bàn cờ cũ
        if cap is not None and not config.DRY_RUN:
             # Lấy dữ liệu mới nhất từ camera
             ret, frame_check = cap.read()
             if ret:
                 try:
                     # Quét lại bàn cờ
                     results = model.predict(frame_check, conf=0.35, iou=0.45, verbose=False)
                     detections_check = []
                     for box in results[0].boxes:
                         cls = int(box.cls[0])
                         if cls in CLASS_ID_TO_INTERNAL_NAME:
                             x1, y1, x2, y2 = map(int, box.xyxy[0])
                             detections_check.append((cls, (x1, y1, x2, y2)))
                     
                     M_check = np.load(str(PERSPECTIVE_PATH))
                     cam_grid_now = detections_to_grid_occupancy(detections_check, M_check)
                     
                     # Đếm số quân cờ trong mỗi bàn cờ để validation
                     def count_pieces(grid):
                         count = {"r": 0, "b": 0, "total": 0}
                         for r in range(NUM_ROWS):
                             for c in range(NUM_COLS):
                                 if grid[r][c] != ".":
                                     count["total"] += 1
                                     if grid[r][c].startswith("r"):
                                         count["r"] += 1
                                     elif grid[r][c].startswith("b"):
                                         count["b"] += 1
                         return count
                     
                     board_count = count_pieces(board)
                     cam_count = count_pieces(cam_grid_now)
                     
                     # So sánh: Nếu bàn cờ ảo khác bàn cờ thật -> KIỂM TRA TRƯỚC KHI ĐỒNG BỘ
                     diff_count = 0
                     diff_details = []
                     for r in range(NUM_ROWS):
                         for c in range(NUM_COLS):
                             if board[r][c] != cam_grid_now[r][c]:
                                 if cam_grid_now[r][c] != ".":
                                     diff_count += 1
                                     diff_details.append((c, r, board[r][c], cam_grid_now[r][c]))
                     
                     # VALIDATION: Chỉ đồng bộ khi:
                     # 1. Số khác biệt hợp lý (≤ 4) - tránh nhiễu
                     # 2. Số quân cờ không quá chênh lệch (≤ 2 quân)
                     # 3. Cả hai bên đều có quân cờ (tránh trường hợp camera nhận diện sai hoàn toàn)
                     piece_diff = abs(board_count["total"] - cam_count["total"])
                     
                     if diff_count > 0:
                         print(f"⚠️ [SAFETY] Detected {diff_count} position differences. Board: {board_count['total']} pieces, Camera: {cam_count['total']} pieces")

                         # Chỉ đồng bộ khi thỏa mãn điều kiện
                         if diff_count <= 4 and piece_diff <= 2 and cam_count["r"] > 0 and cam_count["b"] > 0:
                             print(f"✅ [SAFETY] Valid conditions. Syncing from camera...")
                             # Copy bàn cờ camera vào não AI
                             board = [row[:] for row in cam_grid_now]
                             draw_pieces() # Vẽ lại ngay cho người xem thấy
                             pygame.display.flip()
                         else:
                             print(f"⚠️ [SAFETY] Skipping sync - Difference too large or invalid (diff={diff_count}, piece_diff={piece_diff}, r={cam_count['r']}, b={cam_count['b']})")
                             # KHÔNG đồng bộ - giữ nguyên bàn cờ ảo để tránh làm sai
                         
                 except Exception as e:
                     print(f"Camera safety check error: {e}")
        # -------------------------------------------------------------------

        print(f"[AI] Thinking...")
        pygame.display.flip()
        # ... (Code cũ của AI ở dưới giữ nguyên) ...
        pygame.display.flip()
        try:
            best = ai.pick_best_move(board, "b")
            
            # --- [XỬ LÝ LẶP] Panic Mode: Random move nếu AI bị kẹt ---
            if best:
                try: s, d = best
                except: s, d = best[0], best[1]
                
                # Check lặp 3 lần
                if len(move_history) > 8:
                    last_srcs = [m['src'] for m in move_history[-6:]]
                    if last_srcs.count(s) >= 3:
                        print(f"⚠️ AI DETECTED LOOP ({s}->{d}) -> ACTIVATING PANIC MODE (Random Move)!")
                        valid_moves = xiangqi.find_all_valid_moves("b", board)
                        if valid_moves:
                            best = random.choice(valid_moves)
                            s, d = best
                            print(f"👉 Alternative move: {s}->{d}")
            # --------------------------------------------------------

            if best:
                try: s, d = best
                except: s, d = best[0], best[1]

                key = ai_book.board_to_key(board)
                move_history.append({"turn": "b", "key": key, "src": s, "dst": d})
                cap_p = board[d[1]][d[0]]
                is_cap = cap_p != "."
                if is_cap: r_captured.append(cap_p)

                robot_success = True 
                
                # Xử lý âm thanh chung
                attacker_sound = piece_str_to_sound(board[s[1]][s[0]])
                if is_cap:
                    target_sound = piece_str_to_sound(cap_p)
                    if attacker_sound and target_sound:
                        sound_player.play_capture_sound(attacker_sound, target_sound)
                else:
                    if attacker_sound: sound_player.play_move_sound(attacker_sound)

                # Thực hiện nước đi
                if config.DRY_RUN:
                    pass # Chỉ log, không làm gì
                else:
                    print(f"[AI] Robot executing move: {s}->{d}")
                    if robot.connected:
                        try:
                            robot.move_piece(s[0], s[1], d[0], d[1], is_cap)
                        except Exception as e:
                            # --- CODE SỬA: BỎ QUA LỖI 112 ĐỂ TRÁNH LẶP ---
                            error_str = str(e)
                            print(f"⚠️ Robot reported error: {error_str}")

                            # Nếu lỗi chứa "112" (Lỗi kẹt khớp) hoặc "MoveCart" 
                            # nghĩa là robot đã gắp thả xong nhưng không về được Home.
                            # -> Ta chấp nhận nước đi này là THÀNH CÔNG (True).
                            if "112" in error_str or "MoveCart" in error_str:
                                print("✅ Light error (home return stuck). Still counting as successful move!")
                                robot_success = True
                            else:
                                # Các lỗi khác (Mất kết nối, va chạm mạnh...) thì mới báo lỗi thật
                                print(f"❌ [CRITICAL] ROBOT CRITICAL ERROR, STOPPING GAME.")
                                robot_success = False
                                time.sleep(2)

                if robot_success:
                    board, _ = xiangqi.make_temp_move(board, best)
                    last_move = best
                    if xiangqi.get_king_pos('r', board) is None: handle_game_over('b') 
                    else: 
                        turn = 'r'
                        print("[GAME] Your turn..."); last_sync_time = time.time() + 4.0
                else:
                    print("⚠️ SKIPPING BOARD UPDATE DUE TO ROBOT ERROR.")
            else:
                print("[AI] No moves available -> AI Lost")
                handle_game_over("r")
        except Exception as e:
            print(f"AI Error: {e}")
            traceback.print_exc()
            turn = "r" # Trả turn để tránh treo game

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