import os
import cv2
import time

# ==========================================
# CONFIG
# ==========================================
CAMERA_INDEX = 1
SAVE_DIR     = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                             "newdata", "images")   # → project_root/rawdata/images/

os.makedirs(SAVE_DIR, exist_ok=True)

# ==========================================
# OPEN CAMERA
# ==========================================
print(f"📷 Opening camera {CAMERA_INDEX}...")
cap = cv2.VideoCapture(CAMERA_INDEX, cv2.CAP_DSHOW)
cap.set(cv2.CAP_PROP_FRAME_WIDTH,  1280)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

if not cap.isOpened():
    raise RuntimeError(f"Cannot open camera index {CAMERA_INDEX}!")

# Count existing images so we don't overwrite
existing = [f for f in os.listdir(SAVE_DIR) if f.lower().endswith(('.jpg', '.png'))]
count    = len(existing)

print(f"📁 Save folder : {SAVE_DIR}")
print(f"🖼️  Existing     : {count} image(s) already in folder")
print()
print("  SPACE  → capture image")
print("  Q      → quit")
print("=" * 40)

WIN = "Chessboard Capture  |  SPACE=save  Q=quit"
cv2.namedWindow(WIN, cv2.WINDOW_NORMAL)
cv2.resizeWindow(WIN, 960, 600)

flash_until = 0   # timestamp until which to show green flash overlay

while True:
    ret, frame = cap.read()
    if not ret:
        continue

    display = frame.copy()

    # Green flash feedback after saving
    if time.time() < flash_until:
        overlay = display.copy()
        cv2.rectangle(overlay, (0, 0), (display.shape[1], display.shape[0]), (0, 220, 80), -1)
        cv2.addWeighted(overlay, 0.25, display, 0.75, 0, display)

    # HUD
    cv2.putText(display,
                f"Saved: {count} imgs  |  SPACE=capture  Q=quit",
                (12, 36), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 255), 2)

    cv2.imshow(WIN, display)

    key = cv2.waitKey(1) & 0xFF

    if key == ord('q') or key == 27:   # Q or ESC
        break

    elif key == ord(' '):              # SPACEBAR — capture
        count += 1
        filename = f"capture_{count:04d}.jpg"
        filepath  = os.path.join(SAVE_DIR, filename)
        cv2.imwrite(filepath, frame)
        flash_until = time.time() + 0.3  # 300ms green flash
        print(f"  ✅ [{count:>4}] Saved → {filename}")

cap.release()
cv2.destroyAllWindows()
print(f"\n✅ Done. {count} total image(s) saved to:\n   {SAVE_DIR}")
