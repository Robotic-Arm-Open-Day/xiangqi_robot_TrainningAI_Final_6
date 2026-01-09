import cv2
import numpy as np
import threading
import queue
import time

# ==========================================
# CẤU HÌNH CAMERA
# ==========================================
VIDEO_SOURCE = 0   # Index camera (Thử 0 nếu không lên hình)
SAVE_PATH = "perspective.npy"

print(f"📷 Đang mở Camera {VIDEO_SOURCE}...")
cap = cv2.VideoCapture(VIDEO_SOURCE, cv2.CAP_DSHOW)
# Set độ phân giải cao để click cho chuẩn
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

if not cap.isOpened():
    print("❌ Lỗi: Không mở được Camera! Hãy thử đổi VIDEO_SOURCE thành 0.")
    exit()

# --- Thread đọc Camera (Giúp hình mượt hơn) ---
frame_q = queue.Queue(maxsize=1)
def capture_thread():
    while True:
        ret, frm = cap.read()
        if ret:
            if not frame_q.empty():
                try: frame_q.get_nowait()
                except queue.Empty: pass
            frame_q.put(frm)
        time.sleep(0.01)

threading.Thread(target=capture_thread, daemon=True).start()
time.sleep(1.0) # Chờ camera khởi động

# ==========================================
# XỬ LÝ CHUỘT VÀ VẼ
# ==========================================
points = []
def mouse_callback(event, x, y, flags, param):
    if event == cv2.EVENT_LBUTTONDOWN and len(points) < 4:
        points.append((x, y))

cv2.namedWindow("CALIBRATE")
cv2.setMouseCallback("CALIBRATE", mouse_callback)

print("\n=== HƯỚNG DẪN CLICK (QUAN TRỌNG) ===")
print("👉 Click lần lượt 4 góc bàn cờ thật trên màn hình:")
print("   1️⃣  Góc Xe Đen (Trái)")
print("   2️⃣  Góc Xe Đen (Phải)")
print("   3️⃣  Góc Xe Đỏ (Phải)")
print("   4️⃣  Góc Xe Đỏ (Trái)")
print("---------------------------------------------")
print("⌨️  Phím tắt: 'R'=Làm lại | 'S'=Lưu file | 'Q'=Thoát")

while True:
    try:
        frame = frame_q.get(timeout=1.0)
    except queue.Empty:
        continue

    display = frame.copy()

    # Vẽ các điểm đã click
    for i, p in enumerate(points):
        cv2.circle(display, p, 5, (0, 0, 255), -1)
        cv2.putText(display, str(i+1), (p[0]+10, p[1]), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)

    # Khi đủ 4 điểm, tính toán và vẽ lưới
    if len(points) == 4:
        # Tọa độ Logic: Đen(0,0 & 8,0) -> Đỏ(8,9 & 0,9)
        src = np.array(points, dtype=np.float32)
        dst = np.array([
            [0, 0],   # 1. Đen Trái
            [8, 0],   # 2. Đen Phải
            [8, 9],   # 3. Đỏ Phải
            [0, 9]    # 4. Đỏ Trái
        ], dtype=np.float32)
        
        M = cv2.getPerspectiveTransform(src, dst)

        # Vẽ lưới màu vàng để kiểm tra độ khớp
        try:
            inv_M = np.linalg.inv(M)
            # Vẽ 10 hàng ngang
            for r in range(10):
                p1 = cv2.perspectiveTransform(np.array([[[0, r]]], dtype=np.float32), inv_M)[0][0]
                p2 = cv2.perspectiveTransform(np.array([[[8, r]]], dtype=np.float32), inv_M)[0][0]
                cv2.line(display, (int(p1[0]), int(p1[1])), (int(p2[0]), int(p2[1])), (0, 255, 255), 1)
            # Vẽ 9 cột dọc
            for c in range(9):
                p1 = cv2.perspectiveTransform(np.array([[[c, 0]]], dtype=np.float32), inv_M)[0][0]
                p2 = cv2.perspectiveTransform(np.array([[[c, 9]]], dtype=np.float32), inv_M)[0][0]
                cv2.line(display, (int(p1[0]), int(p1[1])), (int(p2[0]), int(p2[1])), (0, 255, 255), 1)
            
            cv2.putText(display, "OK? Bam 'S' de Luu", (20, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
        except:
            pass

    cv2.imshow("CALIBRATE", display)
    
    key = cv2.waitKey(1)
    if key == ord('q'):
        break
    elif key == ord('r'): # Reset
        points = []
        print("🔄 Đã xóa điểm, hãy click lại.")
    elif key == ord('s') and len(points) == 4: # Save
        np.save(SAVE_PATH, M)
        print(f"✅ ĐÃ LƯU THÀNH CÔNG: {SAVE_PATH}")
        print("👉 Bây giờ bạn có thể đóng file này và chạy main.py")
        break

cap.release()
cv2.destroyAllWindows()