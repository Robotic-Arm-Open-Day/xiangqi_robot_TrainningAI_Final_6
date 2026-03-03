import os
import cv2
import time
import threading
import queue
import torch
from ultralytics import YOLO

# ==========================================
# CONFIG
# ==========================================
VIDEO_SOURCE  = 1          # Camera index
DISPLAY_SCALE = 1.5        # Display zoom
CONF          = 0.4        # Detection confidence threshold
IOU           = 0.45       # NMS IoU threshold

# Path to the newly trained YOLO26 model (relative to this script)
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH  = os.path.join(
    _SCRIPT_DIR, "..", "runs", "detect", "chess_vision",
    "yolo26_occupancy_run6", "weights", "best.pt"
)

# ==========================================
# LOAD MODEL
# ==========================================
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
print(f"🚀 Device  : {DEVICE}")
print(f"🧠 Model   : {os.path.normpath(MODEL_PATH)}")

if not os.path.exists(MODEL_PATH):
    raise FileNotFoundError(f"best.pt not found at:\n  {MODEL_PATH}\nRun trainyolo26.py first.")

model = YOLO(MODEL_PATH)
if DEVICE == "cuda":
    model.to(DEVICE)

print(f"✅ Classes  : {model.names}")

# ==========================================
# CAMERA + CAPTURE THREAD
# ==========================================
print(f"\n📷 Opening Camera Index: {VIDEO_SOURCE} ...")
cap = cv2.VideoCapture(VIDEO_SOURCE, cv2.CAP_DSHOW)
cap.set(cv2.CAP_PROP_FRAME_WIDTH,  1920)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)
cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

if not cap.isOpened():
    raise RuntimeError(f"Cannot open camera index {VIDEO_SOURCE}!")

# Verify the driver actually accepted the resolution
actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
print(f"📐 Camera resolution: {actual_w}x{actual_h} {'✅' if actual_w == 1920 else '⚠ driver overrode to this'}")

frame_q   = queue.Queue(maxsize=1)
stop_event = threading.Event()

def capture_thread():
    while not stop_event.is_set():
        ret, frm = cap.read()
        if not ret:
            time.sleep(0.01)
            continue
        # Discard old frame, keep only the latest
        if not frame_q.empty():
            try: frame_q.get_nowait()
            except queue.Empty: pass
        frame_q.put(frm)
    cap.release()

t = threading.Thread(target=capture_thread, daemon=True)
t.start()
print("✅ Camera thread started. Warming up...")
time.sleep(1.0)

# ==========================================
# MAIN DETECTION LOOP
# ==========================================
WIN_NAME = "YOLO26 Chess Detection"
cv2.namedWindow(WIN_NAME, cv2.WINDOW_NORMAL)

prev_time = time.time()
fps       = 0.0
alpha     = 0.2   # EMA smoothing for FPS

print(f"\n=== RUNNING AI DETECTION (Press 'Q' to quit) ===\n")

try:
    while True:
        # Get latest frame
        try:
            frame = frame_q.get(timeout=1.0)
        except queue.Empty:
            continue

        # Warn if frame is black (all zeros)
        if frame is not None and frame.mean() < 2.0:
            cv2.putText(frame, "⚠ BLACK FRAME - check camera!", (10, 60),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)

        # ---- YOLO Inference ----
        results = model.predict(
            frame,
            conf=CONF,
            iou=IOU,
            device=DEVICE,
            imgsz=640,
            verbose=False
        )

        # ---- Draw detections ----
        annotated = frame.copy()
        for result in results:
            for box in result.boxes:
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                cls_id     = int(box.cls[0])
                label      = model.names.get(cls_id, str(cls_id))
                conf_score = float(box.conf[0])

                # Color by class name
                color = (0, 200, 50)   # default green
                if "piece" in label.lower():
                    color = (0, 200, 255)  # orange-yellow for chess pieces

                cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)
                tag = f"{label} {conf_score:.2f}"
                cv2.putText(annotated, tag, (x1, y1 - 6),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2)

        # ---- FPS overlay ----
        now  = time.time()
        fps  = fps * (1 - alpha) + (1.0 / (now - prev_time + 1e-6)) * alpha
        prev_time = now
        cv2.putText(annotated, f"FPS: {fps:.1f}  |  Press Q to quit",
                    (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)

        # ---- Display ----
        h, w = annotated.shape[:2]
        disp = cv2.resize(annotated, (int(w * DISPLAY_SCALE), int(h * DISPLAY_SCALE)))
        cv2.imshow(WIN_NAME, disp)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            print("Quit requested.")
            break

except KeyboardInterrupt:
    print("\nInterrupted.")

finally:
    stop_event.set()
    t.join(timeout=2)
    if cap.isOpened():
        cap.release()
    cv2.destroyAllWindows()
    print("✅ Exited cleanly.")
