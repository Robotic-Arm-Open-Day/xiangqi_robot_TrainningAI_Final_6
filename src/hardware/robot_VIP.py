# ==================================
# === FILE: VIP/robot_VIP.py ===
# === Điều khiển cánh tay robot FR5 — phiên bản VIP ===
# === Dựa trên robot.py gốc, dùng Controller DO2 (bộ điều khiển) ===
# ==================================
import time
import sys
import os
import json
import numpy as np
import cv2

# Đảm bảo import được config từ thư mục gốc project
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_DIR = os.path.dirname(os.path.dirname(_THIS_DIR))
sys.path.insert(0, _PROJECT_DIR)
import config

try:
    from src.hardware import robot_sdk_core
except ImportError:
    print("LỖI: Không tìm thấy module 'robot_sdk_core'...")
    robot_sdk_core = None


class FR5Robot:
    def __init__(self, ip=None):
        self.ip          = ip or config.ROBOT_IP
        self.robot       = None
        self.connected   = False
        self.dry         = config.DRY_RUN
        self.tool_num    = 0
        self.user_num    = 1
        self.default_vel = config.MOVE_SPEED

        # ⚙️ Kẹp: dùng Tool DO0 (Đầu cánh tay - cáp M12)
        self.gripper_do_id = 0

        # Ma trận hiệu chỉnh perspective (được set từ main_VIP.py)
        self.perspective_matrix = None

    # -------------------------------------------------------------------------
    # SET MA TRẬN TỪ NGOÀI
    # -------------------------------------------------------------------------

    def set_perspective_matrix(self, matrix):
        """Nhận ma trận hiệu chỉnh từ main_VIP.py và lưu nó."""
        print("[ROBOT] ✅ Đã nhận và lưu Ma trận Hiệu chỉnh.")
        self.perspective_matrix = matrix

    # -------------------------------------------------------------------------
    # KẾT NỐI
    # -------------------------------------------------------------------------

    def connect(self):
        if self.dry:
            print("[ROBOT] DRY RUN — không kết nối thực tế")
            self.connected = True
            return

        if robot_sdk_core is None:
            raise Exception("Module robot_sdk_core chưa được import.")

        try:
            self.robot = robot_sdk_core.RPC(self.ip)
            time.sleep(2)
            self.connected = self.robot.SDK_state
            if not self.connected:
                raise Exception("SDK không thể kết nối tới robot")

            print(f"[ROBOT] ✅ Đã kết nối tới {self.ip}")

            err = self.robot.RobotEnable(1)
            if err != 0:
                print(f"[ROBOT] ⚠️ RobotEnable thất bại, code={err}")

            err = self.robot.Mode(0)
            if err != 0:
                print(f"[ROBOT] ⚠️ Set Mode(0) thất bại, code={err}")

        except Exception as e:
            print(f"[ROBOT] ❌ Lỗi connect: {e}")
            self.connected = False
            raise

    # -------------------------------------------------------------------------
    # CHUYỂN ĐỔI TỌA ĐỘ BÀN CỜ → ROBOT
    # -------------------------------------------------------------------------

    def board_to_pose(self, col, row, z_height):
        """Chuyển đổi (col, row) bàn cờ logic → tọa độ [x,y,z,rx,ry,rz] robot (mm) bằng Toán Cứng."""
        
        # 1. Tính delta khoảng cách từ ô gốc (0,0)
        delta_x = col * config.CELL_SIZE_X
        delta_y = row * config.CELL_SIZE_Y
        
        # Bù thêm khe hở Sông (River gap) cho các quân nằm phía Đỏ (row >= 5)
        if row >= 5:
            delta_y += config.RIVER_GAP_Y
            
        # 2. Áp dụng hướng (Direction) và cộng với Tọa độ gốc R1
        x_mm = config.BOARD_ORIGIN_X + (delta_x * config.ROBOT_DIR_X)
        y_mm = config.BOARD_ORIGIN_Y + (delta_y * config.ROBOT_DIR_Y)

        if abs(x_mm) > 900 or abs(y_mm) > 900:
            print(f"[ROBOT] ⚠️ Tọa độ quá xa ({x_mm:.1f}, {y_mm:.1f}) — cẩn thận đập máy!")

        # DEBUG: in ra console để dễ kiểm soát
        print(f"[ROBOT] 📐 HARDCODED: board({col},{row}) → X={x_mm:.1f}mm, Y={y_mm:.1f}mm, Z={z_height:.1f}mm")

        return [x_mm, y_mm, z_height] + list(config.ROTATION)

    # -------------------------------------------------------------------------
    # DI CHUYỂN ROBOT
    # -------------------------------------------------------------------------

    def move_safe_pose(self, pose, speed=None):
        """Di chuyển tự do (MoveCart) đến pose."""
        vel = speed or self.default_vel
        if self.dry:
            print(f"[ROBOT] DRY MoveJ → {[round(v,1) for v in pose]} vel={vel}")
            time.sleep(0.2)
            return 0

        err = self.robot.MoveCart(
            desc_pos=pose, tool=self.tool_num, user=self.user_num,
            vel=vel, acc=0.0, ovl=100.0, blendT=-1.0, config=-1
        )
        if err not in (0, 112):
            print(f"[ROBOT] ❌ Lỗi MoveCart: {err}")
            raise Exception(f"Robot MoveCart error code: {err}")
        return err

    def movej_joint(self, joint_pos, desc_pos, speed=None):
        """Di chuyển trực tiếp bằng góc joint (MoveJ) nếu đã biết."""
        vel = speed or self.default_vel
        if self.dry:
            print(f"[ROBOT] DRY MoveJ_Joint → vel={vel}")
            time.sleep(0.2)
            return 0
            
        err = self.robot.MoveJ(
            joint_pos=joint_pos, desc_pos=desc_pos, tool=self.tool_num, user=self.user_num,
            vel=vel, acc=0.0, ovl=100.0, exaxis_pos=[0]*4, blendT=-1.0, offset_flag=0, offset_pos=[0]*6
        )
        if err not in (0, 112):
            print(f"[ROBOT] ❌ Lỗi movej_joint MoveJ: {err}")
            raise Exception(f"Robot movej_joint error code: {err}")
        return err

    def movel_pose(self, pose, speed=None):
        """Di chuyển thẳng đứng (MoveCart) đến pose."""
        vel = speed or self.default_vel
        if self.dry:
            print(f"[ROBOT] DRY MoveL → {[round(v,1) for v in pose]} vel={vel}")
            time.sleep(0.2)
            return 0

        err = self.robot.MoveCart(
            desc_pos=pose, tool=self.tool_num, user=self.user_num,
            vel=vel, acc=0.0, ovl=100.0, blendT=-1.0, config=-1
        )
        if err not in (0, 112):
            print(f"[ROBOT] ❌ Lỗi MoveCart (movel): {err}")
            raise Exception(f"Robot MoveCart error code: {err}")
        return err

    # -------------------------------------------------------------------------
    # VỀ NHÀ
    # -------------------------------------------------------------------------

    def go_to_idle_home(self):
        """Đưa robot về vị trí chờ an toàn (IDLE)."""
        print("[ROBOT] Về vị trí IDLE...")
        pose = [config.IDLE_X, config.IDLE_Y, config.IDLE_Z] + list(config.ROTATION)
        try:
            self.move_safe_pose(pose)
        except Exception as e:
            print(f"[ROBOT] ⚠️ Lỗi khi về IDLE trực tiếp: {e}. Thử nâng Z lên cao...")
            # Nâng Z an toàn trước khi di chuyển
            try:
                high_z_pose = [config.IDLE_X, config.IDLE_Y, config.IDLE_Z + 100.0] + list(config.ROTATION)
                self.move_safe_pose(high_z_pose)
                self.move_safe_pose(pose)
            except Exception as e2:
                print(f"[ROBOT] ❌ Lỗi cả khi qua điểm trung gian Z cao: {e2}")

    def go_to_home_chess(self):
        """Về vị trí HOMECHESS đã dạy trên bộ điều khiển."""
        print("[ROBOT] Về vị trí HOMECHESS...")
        if self.dry:
            print("[ROBOT] DRY RUN — bỏ qua HOMECHESS")
            return
        if self.robot is None:
            print("[ROBOT] Chưa kết nối — không thể về HOMECHESS")
            return
        try:
            err, data = self.robot.GetRobotTeachingPoint("HOMECHESS")
            if err != 0:
                print(f"[ROBOT] ⚠️ Không đọc được HOMECHESS (err={err}) → về IDLE")
                self.go_to_idle_home()
                return
                
            # If data contains joint pos, use it directly (data is typically >= 12 elements)
            pose = list(data[:6])
            
            if len(data) >= 12:
                joints = list(data[6:12])
                print(f"[ROBOT] Đọc được joints HOMECHESS: {joints}")
                try:
                    self.movej_joint(joints, pose)
                    print("[ROBOT] ✅ Đã về HOMECHESS (bằng Joint).")
                    return
                except Exception as je:
                    print(f"[ROBOT] ⚠️ Lỗi MoveJ bằng khớp: {je}. Tiếp tục thử MoveJ Pose...")
                    
            # Fallback to MoveJ with pose
            self.move_safe_pose(pose)
            print("[ROBOT] ✅ Đã về HOMECHESS (bằng Pose).")
            
        except Exception as e:
            print(f"[ROBOT] ⚠️ go_to_home_chess lỗi: {e} → về IDLE")
            self.go_to_idle_home()

    # -------------------------------------------------------------------------
    # GRIPPER — Controller DO2
    # -------------------------------------------------------------------------

    def gripper_ctrl(self, val):
        """Điều khiển kẹp qua Controller DO2 (bộ điều khiển, không phải Tool DO).
        
        val = config.GRIPPER_CLOSE (1) → Đóng kẹp
        val = config.GRIPPER_OPEN  (0) → Mở kẹp
        """
        if self.dry:
            action = "ĐÓNG" if val == config.GRIPPER_CLOSE else "MỞ"
            print(f"[ROBOT] DRY Gripper (SetDO ID={self.gripper_do_id}) → {action}")
            time.sleep(0.3)
            return 0

        # NẾU CẮM CÁP M12 8-PIN VÀO ĐẦU CÁNH TAY (Tool DO):
        # 1. Hãy dò tìm ID bằng file test_tool_do2.py trước (Thử ID=0, rồi ID=1)
        # 2. Sau khi biết ID thực (VD: 1), sửa self.gripper_do_id = 1 ở đầu file.
        # 3. Đổi hàm SetDO (dưới đây) thành SetToolDO:
        err = self.robot.SetToolDO(
            id=self.gripper_do_id,
            status=val,
            block=1
        )
        if err != 0:
            print(f"[ROBOT] ❌ Lỗi SetToolDO (gripper): {err}")
        return err

    # -------------------------------------------------------------------------
    # QUY TRÌNH GẮP / ĐẶT / ĂN QUÂN
    # -------------------------------------------------------------------------

    def pick_at(self, col, row):
        """Gắp 1 quân cờ tại (col, row)."""
        pose_safe = self.board_to_pose(col, row, config.SAFE_Z)
        pose_pick = self.board_to_pose(col, row, config.PICK_Z)
        print(f"[ROBOT] 🤏 Gắp tại grid=({col},{row}) → X={pose_safe[0]:.1f}, Y={pose_safe[1]:.1f}, Z={pose_safe[2]:.1f}")

        self.gripper_ctrl(config.GRIPPER_OPEN)   # Mở kẹp
        self.move_safe_pose(pose_safe)                # Đi đến vị trí an toàn trên ô
        self.movel_pose(pose_pick)                # Hạ xuống
        self.gripper_ctrl(config.GRIPPER_CLOSE)  # Đóng kẹp (gắp)
        time.sleep(0.5)                           # Đợi kẹp đóng
        self.movel_pose(pose_safe)                # Nhấc lên
        print(f"[ROBOT] ✅ Gắp xong ({col},{row})")

    def place_at(self, col, row):
        """Đặt 1 quân cờ tại (col, row)."""
        pose_safe  = self.board_to_pose(col, row, config.SAFE_Z)
        pose_place = self.board_to_pose(col, row, config.PLACE_Z)
        print(f"[ROBOT] 📍 Đặt tại grid=({col},{row}) → X={pose_safe[0]:.1f}, Y={pose_safe[1]:.1f}, Z={pose_safe[2]:.1f}")

        self.move_safe_pose(pose_safe)                # Đến vị trí an toàn
        self.movel_pose(pose_place)               # Hạ xuống
        self.gripper_ctrl(config.GRIPPER_OPEN)   # Mở kẹp (thả)
        time.sleep(0.5)                           # Đợi thả
        self.movel_pose(pose_safe)                # Nhấc lên
        print(f"[ROBOT] ✅ Đặt xong ({col},{row})")

    def place_in_capture_bin(self):
        """Thả quân bị ăn vào bãi thải."""
        print("[ROBOT] 🗑️ Thả quân bị ăn vào bãi...")
        pose_safe  = [config.CAPTURE_BIN_X, config.CAPTURE_BIN_Y, config.SAFE_Z]  + list(config.ROTATION)
        pose_place = [config.CAPTURE_BIN_X, config.CAPTURE_BIN_Y, config.CAPTURE_BIN_Z] + list(config.ROTATION)

        self.move_safe_pose(pose_safe)
        self.movel_pose(pose_place)
        self.gripper_ctrl(config.GRIPPER_OPEN)
        time.sleep(0.5)
        self.movel_pose(pose_safe)
        print("[ROBOT] ✅ Đã thả quân bị ăn.")

    # -------------------------------------------------------------------------
    # HÀM CHÍNH — GỌI TỪ main_VIP.py
    # -------------------------------------------------------------------------

    def move_piece(self, s_col, s_row, d_col, d_row, is_capture):
        """Quy trình di chuyển hoàn chỉnh, bao gồm xử lý ăn quân.
        
        Args:
            s_col, s_row: ô nguồn
            d_col, d_row: ô đích
            is_capture:   True nếu ăn quân đối phương
        """
        print(f"[ROBOT] ♟️ Di chuyển: ({s_col},{s_row}) → ({d_col},{d_row})"
              + (" [ĂN QUÂN]" if is_capture else ""))

        if not self.connected and not self.dry:
            try:
                self.connect()
            except Exception as e:
                print(f"[ROBOT] ❌ Không thể kết nối, hủy nước đi: {e}")
                return

        # 1. Nếu ăn quân: gắp quân địch → thả vào bãi thải
        if is_capture:
            self.pick_at(d_col, d_row)
            self.place_in_capture_bin()

        # 2. Gắp quân mình ở nguồn
        self.pick_at(s_col, s_row)

        # 3. Đặt quân mình vào đích
        self.place_at(d_col, d_row)

        # 4. Về vị trí chờ
        self.go_to_home_chess()

        print("[ROBOT] ✅ Hoàn tất di chuyển.")

    # -------------------------------------------------------------------------
    # TIỆN ÍCH
    # -------------------------------------------------------------------------

    def load_perspective(self, path):
        """Load ma trận perspective từ file .npy."""
        try:
            self.perspective_matrix = np.load(path)
            print(f"[ROBOT] ✅ Loaded perspective: {path}")
            return True
        except Exception as e:
            print(f"[ROBOT] ❌ load_perspective error: {e}")
            return False

    def pixel_to_grid(self, px, py):
        """Convert tọa độ pixel ảnh → (col, row) bàn cờ."""
        if self.perspective_matrix is None:
            raise RuntimeError("Chưa có perspective_matrix — hãy calibrate camera trước.")
        src = np.array([[[float(px), float(py)]]], dtype=np.float32)
        dst = cv2.perspectiveTransform(src, self.perspective_matrix)[0][0]
        col = max(0, min(8, int(round(dst[0]))))
        row = max(0, min(9, int(round(dst[1]))))
        return col, row


# ==================================
# === KẾT THÚC FILE: robot_VIP.py ===
# ==================================
