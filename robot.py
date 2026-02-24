# ==================================
# === BẮT ĐẦU FILE: robot.py (ĐÃ SỬA VÒNG LẶP) ===
# ==================================
import time
import config
import json
import numpy as np
import cv2
# XÓA BỎ: import main (Đây là nguyên nhân gây lỗi)

try:
    import robot_sdk_core
except ImportError:
    print("LỖI: Không tìm thấy module 'robot_sdk'...")
    robot_sdk_core = None

class FR5Robot:
    def __init__(self, ip=None):
        self.ip = ip or config.ROBOT_IP
        self.robot = None
        self.connected = False
        self.dry = config.DRY_RUN
        self.tool_num = 0 
        self.user_num = 1 
        self.default_vel = config.MOVE_SPEED
        self.gripper_do_id = 1 
        
        # THÊM MỚI: Tạo một biến để LƯU ma trận
        self.perspective_matrix = None

    # THÊM MỚI: Hàm này để main.py "gửi" ma trận vào
    def set_perspective_matrix(self, matrix):
        """Nhận ma trận hiệu chỉnh từ main.py và lưu nó."""
        print("[ROBOT] Đã nhận và lưu Ma trận Hiệu chỉnh.")
        self.perspective_matrix = matrix

    def connect(self):
        if self.dry:
            print("[ROBOT] DRY RUN - không kết nối thực tế")
            self.connected = True
            return
        
        if robot_sdk_core is None:
            raise Exception("Module robot_sdk (SDK) chưa được import.")
            
        try:
            self.robot = robot_sdk_core.RPC(self.ip)
            time.sleep(2) 
            self.connected = self.robot.SDK_state
            if not self.connected:
                raise Exception("SDK không thể kết nối tới robot")
            
            print(f"[ROBOT] Đã kết nối tới {self.ip} qua RPC SDK")
            
            print("[ROBOT] Enabling robot...")
            err = self.robot.RobotEnable(1)
            if err != 0:
                print(f"[ROBOT] Cảnh báo: RobotEnable thất bại, code={err}")
            
            print("[ROBOT] Chuyển sang chế độ tự động (Auto Mode)...")
            err = self.robot.Mode(0)
            if err != 0:
                print(f"[ROBOT] Cảnh báo: Set Mode(0) thất bại, code={err}")
            
        except Exception as e:
            print(f"[ROBOT] Lỗi connect: {e}")
            self.connected = False
            raise

    def board_to_pose(self, col, row, z_height):
        """
        Chuyển đổi (cột, hàng) BÀN CỜ LOGIC -> Tọa độ (x,y,z) ROBOT
        """
        # 1. Kiểm tra Ma trận
        M = self.perspective_matrix
        
        if M is None:
            # [AN TOÀN] Nếu chưa có ma trận, DỪNG NGAY, không được đoán mò tọa độ!
            error_msg = "CRITICAL ERROR: Robot chưa có Ma trận hiệu chỉnh (G1-G4). Không thể di chuyển!"
            print(error_msg)
            raise Exception(error_msg)

        # 2. Tạo điểm logic (col, row) đúng chuẩn OpenCV (1 điểm, 1 hàng, 2 tọa độ)
        # Lưu ý: Đảm bảo col, row là float
        logic_pt = np.array([[[float(col), float(row)]]], dtype=np.float32)

        # 3. Biến đổi Ma trận: Logic (0..8) -> Robot (mm)
        try:
            real_pt = cv2.perspectiveTransform(logic_pt, M)
        except Exception as e:
            print(f"Lỗi tính toán OpenCV: {e}")
            raise

        # 4. Lấy kết quả
        x_mm = float(real_pt[0][0][0])
        y_mm = float(real_pt[0][0][1])

        # [TÙY CHỌN] Kiểm tra tọa độ có "điên rồ" không?
        # Ví dụ: Robot FR5 thường chỉ vươn tới tầm 800mm-900mm. 
        # Nếu tính ra > 1000mm hoặc < -1000mm thì chắc chắn ma trận sai -> Dừng lại.
        if abs(x_mm) > 900 or abs(y_mm) > 900:
             print(f"CẢNH BÁO: Tọa độ tính toán quá xa ({x_mm}, {y_mm}). Kiểm tra lại hiệu chỉnh!")
             # raise Exception("Tọa độ quá giới hạn an toàn")

        # 5. Trả về Pose đầy đủ [x, y, z, rx, ry, rz]
        # config.ROTATION phải là list [rx, ry, rz], ví dụ [180, 0, 0]
        pose = [x_mm, y_mm, z_height] + list(config.ROTATION)
        return pose

    # ... (Các hàm còn lại: movej_pose, movel_pose, gripper_ctrl, pick_at, place_at, ... giữ nguyên) ...
    
    def movej_pose(self, pose, speed=None):
        """Di chuyển an toàn (MoveJ/MoveCart) đến một pose"""
        vel = speed or self.default_vel
        if self.dry:
            print(f"[ROBOT] DRY MoveJ (MoveCart) -> {pose} vel={vel}")
            time.sleep(0.2)
            return 0 

        err = self.robot.MoveCart(
            desc_pos=pose,
            tool=self.tool_num,
            user=self.user_num,
            vel=vel,
            acc=0.0,
            ovl=100.0,
            blendT=-1.0,
            config=-1 
        )
        
        if err != 0:
            print(f"[ROBOT] Lỗi MoveCart: {err}")
            raise Exception(f"Robot MoveCart error code: {err}") 
        
        return err

    def go_to_idle_home(self):
        """Đưa robot về vị trí chờ an toàn"""
        print("[ROBOT] Đang di chuyển về vị trí chờ (Idle)...")
        pose = [config.IDLE_X, config.IDLE_Y, config.IDLE_Z] + config.ROTATION
        self.movej_pose(pose)
    
    def movel_pose(self, pose, speed=None):
        """Di chuyển thẳng (ĐÃ SỬA: Dùng MoveCart thay vì MoveL)"""
        vel = speed or self.default_vel
        if self.dry:
            print(f"[ROBOT] DRY MoveL (using MoveCart) -> {pose} vel={vel}")
            time.sleep(0.2)
            return 0

        err = self.robot.MoveCart(
            desc_pos=pose,
            tool=self.tool_num,
            user=self.user_num,
            vel=vel,
            acc=0.0,
            ovl=100.0,
            blendT=-1.0,
            config=-1
        )
        
        if err != 0:
            print(f"[ROBOT] Lỗi MoveCart (khi gọi từ movel_pose): {err}")
            raise Exception(f"Robot MoveCart error code: {err}")
        
        return err

    def gripper_ctrl(self, val):
        """Điều khiển gripper. Giả định dùng Tool DO."""
        if self.dry:
            print(f"[ROBOT] DRY Gripper (SetToolDO) -> ID={self.gripper_do_id}, val={val}")
            time.sleep(0.3)
            return 0 # Giả lập thành công

        err = self.robot.SetToolDO(
            id=self.gripper_do_id,
            status=val, # val sẽ là 1 (Đóng) hoặc 0 (Mở) từ config
            block=1 # 1 = Chờ lệnh hoàn tất
        )
        if err != 0:
            print(f"[ROBOT] Lỗi SetToolDO: {err}")
        return err

    def pick_at(self, col, row):
        """Quy trình gắp một quân cờ tại (col, row)"""
        print(f"[ROBOT] Bắt đầu gắp tại ({col},{row})")
        pose_safe = self.board_to_pose(col, row, config.SAFE_Z)
        pose_pick = self.board_to_pose(col, row, config.PICK_Z)
        
        # Sửa logic gắp cho khóa điện (Thả = 0, Gắp = 1)
        self.gripper_ctrl(config.GRIPPER_OPEN)  # 1. Mở gripper (Tắt điện)
        self.movej_pose(pose_safe)              # 2. Đi đến vị trí an toàn
        self.movel_pose(pose_pick)              # 3. Hạ thẳng xuống
        self.gripper_ctrl(config.GRIPPER_CLOSE) # 4. Đóng gripper (Bật điện)
        time.sleep(0.5)                         # (Chờ khóa điện/gripper đóng)
        self.movel_pose(pose_safe)              # 5. Nhấc thẳng lên
        print(f"[ROBOT] Đã gắp xong tại ({col},{row})")

    def place_at(self, col, row):
        """Quy trình đặt một quân cờ tại (col, row)"""
        print(f"[ROBOT] Bắt đầu đặt tại ({col},{row})")
        pose_safe = self.board_to_pose(col, row, config.SAFE_Z)
        pose_place = self.board_to_pose(col, row, config.PLACE_Z)

        # (Đang giữ cờ, gripper đang CLOSE, val=1)
        self.movej_pose(pose_safe)              # 1. Đi đến vị trí an toàn
        self.movel_pose(pose_place)             # 2. Hạ thẳng xuống
        self.gripper_ctrl(config.GRIPPER_OPEN)  # 3. Mở gripper (Tắt điện để thả)
        time.sleep(0.5)                         # (Chờ thả quân cờ)
        self.movel_pose(pose_safe)              # 4. Nhấc thẳng lên
        print(f"[ROBOT] Đã đặt xong tại ({col},{row})")

    def place_in_capture_bin(self):
        """Đặt quân cờ bị ăn vào bãi thải"""
        print("[ROBOT] Đặt quân cờ bị ăn vào bãi...")
        pose_safe = [config.CAPTURE_BIN_X, config.CAPTURE_BIN_Y, config.SAFE_Z] + config.ROTATION
        pose_place = [config.CAPTURE_BIN_X, config.CAPTURE_BIN_Y, config.CAPTURE_BIN_Z] + config.ROTATION

        # (Đang giữ cờ, gripper đang CLOSE, val=1)
        self.movej_pose(pose_safe)
        self.movel_pose(pose_place)
        self.gripper_ctrl(config.GRIPPER_OPEN) # 3. Mở gripper (Tắt điện để thả)
        time.sleep(0.5)
        self.movel_pose(pose_safe)
        print("[ROBOT] Đã thả quân bị ăn")

    def move_piece(self, s_col, s_row, d_col, d_row, is_capture):
        """Quy trình di chuyển quân cờ hoàn chỉnh, BAO GỒM xử lý ăn quân"""
        print(f"[ROBOT] Thực hiện: ({s_col},{s_row}) -> ({d_col},{d_row})")
        if not self.connected and not self.dry:
            try:
                self.connect()
            except Exception as e:
                print(f"Không thể kết nối robot, hủy nước đi: {e}")
                return

        # 1. Nếu là ăn quân, gắp quân ở đích và thả vào bãi
        if is_capture:
            print("[ROBOT] Nước đi này là ĂN QUÂN.")
            self.pick_at(d_col, d_row)
            self.place_in_capture_bin()
        
        # 2. Gắp quân ở nguồn
        self.pick_at(s_col, s_row)

        # 3. Đặt quân ở đích
        self.place_at(d_col, d_row)
        
        self.go_to_idle_home() # Đưa robot về góc chờ
        
        print("[ROBOT] Hoàn tất di chuyển.")

    def load_perspective(self, path):
        try:
            self.perspective_matrix = np.load(path)
            print("[ROBOT] Loaded perspective:", path)
            return True
        except Exception as e:
            print("[ROBOT] load_perspective error:", e)
            return False

    def pixel_to_grid(self, px, py):
        """Convert image pixel -> (col,row) using perspective_matrix (image->grid units).
           Rounds to nearest integer grid cell, clamps to valid range."""
        if getattr(self, "perspective_matrix", None) is None:
            raise RuntimeError("No perspective_matrix; run calibration first")
        src = np.array([[[float(px), float(py)]]], dtype=np.float32)
        dst = cv2.perspectiveTransform(src, self.perspective_matrix)[0][0]  # (x_grid, y_grid)
        col = int(round(dst[0])); row = int(round(dst[1]))
        col = max(0, min(8, col)); row = max(0, min(9, row))
        return col, row

    def apply_move_from_file(self, path):
        import json
        try:
            with open(path, "r") as fh:
                data = json.load(fh)
        except Exception as e:
            print("[ROBOT] cannot open move file:", e); return False
        sx, sy = data.get("src_px"), data.get("src_py")
        dx, dy = data.get("dst_px"), data.get("dst_py")
        if None in (sx,sy,dx,dy):
            print("[ROBOT] invalid move file"); return False
        try:
            s_col, s_row = self.pixel_to_grid(sx, sy)
            d_col, d_row = self.pixel_to_grid(dx, dy)
        except Exception as e:
            print("[ROBOT] pixel->grid failed:", e); return False
        print(f"[ROBOT] executing move ({s_col},{s_row})->({d_col},{d_row})")
        try:
            self.move_piece(int(s_col), int(s_row), int(d_col), int(d_row), is_capture=False)
            return True
        except Exception as e:
            print("[ROBOT] move_piece error:", e); return False
# ==================================
# === KẾT THÚC FILE: robot.py ===
# ==================================