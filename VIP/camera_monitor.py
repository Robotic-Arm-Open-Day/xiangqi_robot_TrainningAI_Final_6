# =============================================================================
# === FILE: camera_monitor.py (Tách từ main_VIP.py) ===
# === Hiển thị Camera Monitor liên tục với YOLO occupancy detection + lưới ===
# === YOLO chỉ detect "có quân" / "không có" — quân gì thì tra bộ nhớ ===
# =============================================================================
import cv2
import numpy as np
import time
import threading
import os

# Màu hiển thị
_PIECE_COLOR = (0, 255, 0)     # BGR - xanh lá cho tất cả quân detect được
_GRID_COLOR = (0, 255, 255)    # BGR - vàng cho lưới perspective


class CameraMonitor:
    """Hiển thị camera feed liên tục với YOLO detections + perspective grid."""

    def __init__(self, cap, model, perspective_path, window_name="Camera Monitor"):
        """
        Args:
            cap: cv2.VideoCapture đã mở
            model: YOLO model đã load
            perspective_path: đường dẫn file perspective.npy
            window_name: tên cửa sổ OpenCV
        """
        self.cap = cap
        self.model = model
        self.perspective_path = str(perspective_path)
        self.window_name = window_name
        self._M = None  # perspective matrix (camera → grid)
        self._inv_M = None  # inverse (grid → camera pixel, để vẽ lưới)
        self._last_frame = None
        self._last_detections = []
        self._running = False
        self._thread = None
        self._lock = threading.Lock()

        self._load_perspective()

    def _load_perspective(self):
        """Load perspective matrix từ file."""
        if os.path.exists(self.perspective_path):
            self._M = np.load(self.perspective_path)
            try:
                self._inv_M = np.linalg.inv(self._M)
            except:
                self._inv_M = None
            print(f"[CAM MONITOR] ✅ Perspective loaded: {self.perspective_path}")
        else:
            print(f"[CAM MONITOR] ⚠️ Không tìm thấy perspective.npy")

    def reload_perspective(self):
        """Reload perspective sau khi calibrate lại."""
        self._load_perspective()

    def _capture_and_detect(self):
        """Thread: đọc camera + chạy YOLO detect liên tục."""
        while self._running:
            if self.cap is None or not self.cap.isOpened():
                time.sleep(0.1)
                continue

            ret, frame = self.cap.read()
            if not ret:
                time.sleep(0.01)
                continue

            # Chạy YOLO (giảm tải: predict mỗi ~200ms)
            detections = []
            if self.model is not None:
                try:
                    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    results = self.model.predict(
                        frame_rgb, conf=0.35, iou=0.35,
                        imgsz=1280, verbose=False
                    )
                    for box in results[0].boxes:
                        conf = float(box.conf[0])
                        x1, y1, x2, y2 = map(int, box.xyxy[0])
                        detections.append((conf, (x1, y1, x2, y2)))
                except:
                    pass

            with self._lock:
                self._last_frame = frame.copy()
                self._last_detections = detections

            time.sleep(0.15)  # ~6-7 FPS cho monitor (đủ mượt, không quá nặng)

    def _draw_overlay(self, frame, detections):
        """Vẽ bounding box + lưới perspective lên frame."""
        display = frame.copy()

        # --- Vẽ bounding box YOLO (occupancy: chỉ "có quân" / "không") ---
        for (conf, (x1, y1, x2, y2)) in detections:
            cv2.rectangle(display, (x1, y1), (x2, y2), _PIECE_COLOR, 2)

            # Nhãn: confidence %
            text = f"piece {conf:.0%}"
            (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)
            cv2.rectangle(display, (x1, y1 - th - 6), (x1 + tw + 4, y1), _PIECE_COLOR, -1)
            cv2.putText(display, text, (x1 + 2, y1 - 4),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 1)

        # --- Vẽ lưới perspective ---
        if self._inv_M is not None:
            try:
                # 10 hàng ngang
                for r in range(10):
                    p1 = cv2.perspectiveTransform(
                        np.array([[[0, r]]], dtype=np.float32), self._inv_M)[0][0]
                    p2 = cv2.perspectiveTransform(
                        np.array([[[8, r]]], dtype=np.float32), self._inv_M)[0][0]
                    cv2.line(display, (int(p1[0]), int(p1[1])),
                             (int(p2[0]), int(p2[1])), _GRID_COLOR, 1)
                # 9 cột dọc
                for c in range(9):
                    p1 = cv2.perspectiveTransform(
                        np.array([[[c, 0]]], dtype=np.float32), self._inv_M)[0][0]
                    p2 = cv2.perspectiveTransform(
                        np.array([[[c, 9]]], dtype=np.float32), self._inv_M)[0][0]
                    cv2.line(display, (int(p1[0]), int(p1[1])),
                             (int(p2[0]), int(p2[1])), _GRID_COLOR, 1)
            except:
                pass

        # --- Info text ---
        n_pieces = len(detections)
        info = f"Detected: {n_pieces} pieces | SPACE=confirm move"
        cv2.putText(display, info, (10, 25),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

        return display

    def pause(self):
        """Tạm dừng thread capture (để SnapshotDetector dùng camera)."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
            self._thread = None
        print("[CAM MONITOR] ⏸️ Paused.")

    def resume(self):
        """Tiếp tục thread capture sau khi pause."""
        if not self._running:
            self._running = True
            self._thread = threading.Thread(target=self._capture_and_detect, daemon=True)
            self._thread.start()
            print("[CAM MONITOR] ▶️ Resumed.")

    def start(self):
        """Bắt đầu thread capture + detect."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._capture_and_detect, daemon=True)
        self._thread.start()
        print("[CAM MONITOR] 🎥 Camera Monitor started (background thread)")

    def stop(self):
        """Dừng thread."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
        try:
            cv2.destroyWindow(self.window_name)
        except cv2.error:
            pass  # Window may not exist yet

    def update_display(self):
        """Gọi mỗi frame trong game loop — hiển thị camera window.
        
        Returns:
            key pressed in OpenCV window (or -1)
        """
        with self._lock:
            frame = self._last_frame
            detections = self._last_detections

        if frame is not None:
            display = self._draw_overlay(frame, detections)
            cv2.imshow(self.window_name, display)

        return cv2.waitKey(1)

    def get_latest_frame_and_detections(self):
        """Lấy frame + detections mới nhất (cho handle_space_key dùng)."""
        with self._lock:
            return (
                self._last_frame.copy() if self._last_frame is not None else None,
                list(self._last_detections)
            )
