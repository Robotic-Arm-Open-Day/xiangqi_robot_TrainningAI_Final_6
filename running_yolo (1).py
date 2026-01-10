import os
import cv2
import time
import threading
import queue

import inp
import numpy as np
import torch
from ultralytics import YOLO
import ctypes

# ==========================================
# 1. CẤU HÌNH NGƯỜI DÙNG
# ==========================================
VIDEO_SOURCE = 1            # Camera index
DISPLAY_SCALE = 1.5         # Zoom hiển thị
TARGET_WIDTH = 320          # Resize để AI chạy nhanh
CONF = 0.5
IOU = 0.45
MODEL_PATH = r"C:\FPTU\7\xiangqi_robot_TrainningAI_Final_6\xiangqi_robot_TrainningAI_Final_6\models_chinesechess1\content\runs\detect\train\weights\best.pt"

# ==========================================
# 2. LOAD MODEL
# ==========================================
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
print(f"🚀 Using device: {DEVICE}")

print("🧠 Đang load Model YOLO...")
try:
    model = YOLO(MODEL_PATH)
    if DEVICE == "cuda":
        model.to(DEVICE)
        #try: model.model.half()
        #except: pass
except Exception as e:
    print(f"❌ Lỗi load model custom: {e}")
    model = YOLO("yolov8n.pt")

# ==========================================
# 3. KHỞI TẠO CAMERA & THREAD
# ==========================================
print(f"📷 Đang mở Camera Index: {VIDEO_SOURCE}")
cap = cv2.VideoCapture(VIDEO_SOURCE, cv2.CAP_DSHOW)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

if not cap.isOpened():
    print(f"❌ KHÔNG THỂ MỞ CAMERA SỐ {VIDEO_SOURCE}!")
    exit()

# --- Thread đọc Camera ---
frame_q = queue.Queue(maxsize=1)
stop_event = threading.Event()

def capture_thread():
    while not stop_event.is_set():
        ret, frm = cap.read()
        if not ret:
            time.sleep(0.01)
            continue
        frm = cv2.cvtColor(frm, cv2.COLOR_BGR2RGB)
        if not frame_q.empty():
            try: frame_q.get_nowait()
            except queue.Empty: pass
        frame_q.put(frm)
    cap.release()

t = threading.Thread(target=capture_thread, daemon=True)
t.start()
print("✅ Camera thread started...")

# Chờ 1 chút để camera kịp lên hình
time.sleep(1.0)

# ==========================================
# 4. PHẦN HIỆU CHỈNH (CALIBRATION) - ĐÃ SỬA LỖI
# ==========================================
print("\n--- BẮT ĐẦU HIỆU CHỈNH ---")
print("⚠️ Click 4 góc: TopLeft -> TopRight -> BotRight -> BotLeft")

points = []
def mouse_callback(event, x, y, flags, param):
    if event == cv2.EVENT_LBUTTONDOWN:
        points.append((x, y))
        print(f"👉 Đã chọn điểm {len(points)}: ({x}, {y})")

cv2.namedWindow("CALIBRATE")
cv2.setMouseCallback("CALIBRATE", mouse_callback)

while len(points) < 4:
    # 1. Lấy ảnh từ hàng đợi (QUAN TRỌNG ĐỂ KHÔNG BỊ TRẮNG MÀN HÌNH)
    try:
        frame = frame_q.get(timeout=0.1)
    except queue.Empty:
        continue

    display_frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)

    # 2. Vẽ điểm đã chọn
    #display_frame = frame.copy()
    for i, p in enumerate(points):
        cv2.circle(display_frame, p, 5, (0, 0, 255), -1)
        cv2.putText(display_frame, str(i+1), (p[0]+10, p[1]), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
    
    cv2.putText(display_frame, f"Choose 4 edges: {len(points)}/4", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 255), 2)

    # 3. HIỂN THỊ (FIX LỖI CŨ)
    cv2.imshow("CALIBRATE", display_frame)

    if cv2.waitKey(1) == ord('q'):
        print("Đã hủy hiệu chỉnh.")
        break

cv2.destroyWindow("CALIBRATE")
print(f"✅ Đã chọn xong 4 điểm: {points}")

# ==========================================
# 5. VÒNG LẶP CHÍNH (YOLO AI)
# ==========================================
cv2.namedWindow("YOLOv8 Inference", cv2.WINDOW_NORMAL)

# Lấy kích thước màn hình
try:
    user32 = ctypes.windll.user32
    screen_w, screen_h = user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
except:
    screen_w, screen_h = 1366, 768

initial_w = min(int(TARGET_WIDTH * DISPLAY_SCALE), screen_w - 100)
initial_h = min(int(480 * DISPLAY_SCALE), screen_h - 100)
cv2.resizeWindow("YOLOv8 Inference", initial_w, initial_h)

prev_time = time.time()
fps = 0.0
alpha_fps = 0.2

print("\n=== ĐANG CHẠY AI (Bấm 'Q' để thoát) ===")

try:
    while True:
        try:
            frame = frame_q.get(timeout=1.0)
        except queue.Empty:
            continue

        display_frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)

        h, w = display_frame.shape[:2]
        if w != TARGET_WIDTH:
            scale = TARGET_WIDTH / float(w)
            new_h = int(h * scale)
            inp = cv2.resize(frame, (TARGET_WIDTH, new_h), interpolation=cv2.INTER_LINEAR)
        else:
            inp = display_frame

        # Predict
        results = model.predict(inp, conf=CONF, iou=IOU, device=DEVICE, imgsz=TARGET_WIDTH, verbose=False)

        # Draw
        for result in results:
            for box in result.boxes:
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                cls_id = int(box.cls[0])
                name = model.names.get(cls_id, str(cls_id))
                conf_score = float(box.conf[0])

                if "r_" in name: color = (0, 0, 255)
                elif "b_" in name: color = (0, 0, 0)
                else: color = (0, 255, 0)

                cv2.rectangle(inp, (x1, y1), (x2, y2), color, 2)
                cv2.putText(inp, f"{name} {conf_score:.2f}", (x1, y1 - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)

        # FPS
        curr_time = time.time()
        fps = fps * (1 - alpha_fps) + (1.0 / (curr_time - prev_time + 1e-6)) * alpha_fps
        prev_time = curr_time
        cv2.putText(inp, f"FPS: {fps:.1f}", (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)

        # Show
        try:
            disp_h = int(inp.shape[0] * DISPLAY_SCALE)
            disp_w = int(inp.shape[1] * DISPLAY_SCALE)
            disp = cv2.resize(inp, (disp_w, disp_h))
            display_frame = cv2.cvtColor(disp, cv2.COLOR_RGB2BGR)
            cv2.imshow("YOLOv8 Inference", display_frame)
        except:
            cv2.imshow("YOLOv8 Inference", inp)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

except KeyboardInterrupt:
    pass
finally:
    stop_event.set()
    t.join()
    if cap.isOpened():
        cap.release()
    cv2.destroyAllWindows()
    print("Đã thoát chương trình.")